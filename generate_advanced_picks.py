"""
generate_advanced_picks.py

Orchestrator that:
- loads games + probables from MLB API cache
- loads pitcher & player advanced metrics (pybaseball / caches)
- fetches odds via The Odds API (optional; needs key)
- calculates:
    * Team edge probability (home team win prob)
    * Player props: HR probability, expected total bases, hits, RBIs, steals, batter K probability, pitcher K expectation, pitcher outs
- Writes: data/picks_today.json with detailed reason strings and numeric probabilities
"""
import os, json, math, logging, requests
from datetime import datetime, timezone
from analytics_utils import logistic  # small helper; add file if not present (simple logistic)
import numpy as np

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("generate_advanced_picks")

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

GAMES_FILE = os.path.join(DATA_DIR, "games_probables.json")
PITCHER_CACHE = os.path.join(DATA_DIR, "pitchers_cache.json")
PLAYER_CACHE = os.path.join(DATA_DIR, "players_stats.json")
OUT_PATH = os.path.join(DATA_DIR, "picks_today.json")

# Odds: The Odds API (the-odds-api.com) or another provider
ODDS_API_KEY = os.getenv("ODDS_API_KEY")
ODDS_API_URL = "https://api.the-odds-api.com/v4/sports/baseball_mlb/odds"

def load_json_safe(path):
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return {}

def fetch_odds_snapshot():
    if not ODDS_API_KEY:
        logger.warning("No ODDS_API_KEY set; skipping odds fetch.")
        return None
    params = {"regions":"us","markets":"h2h","oddsFormat":"american","apiKey":ODDS_API_KEY}
    r = requests.get(ODDS_API_URL, params=params, timeout=20)
    r.raise_for_status()
    return r.json()

def simple_pitcher_strength(pitcher_name, pitchers_cache):
    # Heuristic score using xFIP and CSW% from advanced cache (if available)
    data = pitchers_cache.get("pitchers", {}).get(pitcher_name) if pitchers_cache else None
    if not data:
        # return neutral defaults
        return {"xFIP": 4.0, "CSW": 0.27, "K9":8.5, "BB9":3.0, "HRFB":0.10}
    return {
        "xFIP": data.get("xFIP") or 4.0,
        "CSW": data.get("CSW%") or data.get("CSW",0.27),
        "K9": data.get("K9") or data.get("K/9") or 8.5,
        "BB9": data.get("BB9") or data.get("BB/9") or 3.0,
        "HRFB": data.get("HRFB") or data.get("HR/FB") or 0.10
    }

def simple_batter_profile(player_name, players_cache):
    data = players_cache.get("players", {}).get(player_name) if players_cache else None
    if not data:
        # neutral placeholder
        return {"xwOBA":0.310, "wOBA":0.320, "Barrel%":0.04, "HardHit%":0.38, "K%":0.20, "SB_rate":0.02}
    return {
        "xwOBA": data.get("xwOBA") or data.get("xwOBA", 0.310),
        "wRC+": data.get("wRC+",100) or data.get("wRC+",100),
        "Barrel%": data.get("barrel_pct") or data.get("Barrel%",0.04),
        "HardHit%": data.get("hardhit_pct") or data.get("HardHit%",0.38),
        "K%": data.get("K%",0.20),
        "SB_rate": data.get("SB_rate",0.02)
    }

def hr_probability_model(batter, pitcher, park_hr_factor=1.0):
    """
    Simple model for home run probability per plate appearance.
    Based on batter Barrel%, HardHit%, xwOBA vs league, and pitcher's HR/FB and CSW.
    """
    # batter_power = composite of barrel and hardhit
    batter_power = 0.6 * batter["Barrel%"] + 0.4 * batter["HardHit%"]
    # normalize scales
    b_score = batter_power * 10  # scale up
    p_score = pitcher["HRFB"] * 10  # scale
    csw_penalty = (0.30 - pitcher["CSW"])  # higher CSW reduces HR prob
    base_hr_prob = 0.02  # league PA -> HR baseline
    hr_prob = base_hr_prob + 0.6 * (b_score*0.01) + 0.4 * (p_score*0.01) - 0.15 * csw_penalty
    hr_prob *= park_hr_factor
    return max(0.0001, min(hr_prob, 0.5))  # bound

def total_bases_model(batter, pitcher, park_factor=1.0):
    """
    Expected total bases in a game: uses expected wOBA/xwOBA and hitter plate appearances.
    We'll estimate PA per game ~ 4.0 for top-lineups; scale by wRC+ relative to league.
    """
    league_xwoba = 0.315
    rel_xwoba = batter["xwOBA"] / league_xwoba
    expected_pa = 4.0  # could adjust by lineup spot and team run expectancy
    # map xwOBA to expected TB per PA roughly (linear approx)
    tb_per_pa = 0.8 * (batter["xwOBA"] / 0.300)  # baseline mapping
    exp_tb = tb_per_pa * expected_pa * rel_xwoba * park_factor
    # std dev heuristic
    sigma = max(0.6, exp_tb * 0.35)
    return {"exp_tb": exp_tb, "std": sigma}

def hits_model(batter, pitcher, park_factor=1.0):
    # approximate hits per game from xBA
    xBA = batter.get("xBA") or (batter["xwOBA"] * 0.30)  # rough mapping
    expected_pa = 4.0
    exp_hits = xBA * expected_pa * park_factor
    sigma = max(0.5, exp_hits * 0.5)
    return {"exp_hits": exp_hits, "std": sigma}

def rbi_model(batter, team_run_expectancy=0.85):
    # simple mapping: stronger hitters in middle of lineup have higher RBI chances; use wRC+
    exp_rbi = 0.35 * (batter.get("wRC+",100)/100.0) * team_run_expectancy
    return {"exp_rbi": exp_rbi}

def steal_prob_model(batter):
    # steal probability per game from SB rate (season SB / season PA) stored as SB_rate
    sb_rate = batter.get("SB_rate", 0.02)  # per game chance of steal
    return max(0.001, min(sb_rate, 0.6))

def pitcher_strikeouts_model(pitcher):
    # expected Ks for starting pitcher in a start: (K9 / 9) * estimated outs (e.g., 5 or 6 innings *3 outs)
    k9 = pitcher.get("K9", 8.5)
    expected_innings = 5.5
    exp_ks = k9 / 9.0 * expected_innings
    return max(0.0, exp_ks)

def batter_strikeout_prob(batter, pitcher):
    # Simple model: combine batter K% and pitcher's K9 to estimate batter K prob in game
    batter_k = batter.get("K%", 0.20)
    pitcher_k = pitcher.get("K9", 8.5)
    # assume batter faces this pitcher ~4 PA; compute chance of at least 1 K
    pa = 4.0
    per_pa_k_prob = max(0.02, min(0.5, (batter_k + (pitcher_k/20.0))/2.0))
    prob_at_least_1 = 1 - (1 - per_pa_k_prob)**pa
    return prob_at_least_1

def compute_team_edge(home_metrics, away_metrics, home_pitcher, away_pitcher, odds_home_ml=None):
    """
    Combine metrics into a numeric probability (home team win)
    We blend: pitcher advantage (xFIP), lineup strength (wRC+), bullpen_xFIP
    """
    # weight tuning
    w_pitch = 0.45
    w_hit = 0.30
    w_bullpen = 0.15
    w_market = 0.10

    # pitcher advantage: lower xFIP is better for that side
    p_adv = (away_pitcher["xFIP"]
