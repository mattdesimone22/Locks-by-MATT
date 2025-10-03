#!/usr/bin/env python3
"""
fetch_data.py

Large single-script pipeline to fetch today's MLB games, advanced stats (Sav
ant/FanGraphs), sportsbook player-prop lines (TheOddsAPI), compute modelled
player prop probabilities and confidence, compare with market implied
probabilities, and write JSON outputs for your frontend to consume.

Outputs (written to ./data):
 - games_today.json        (list of games + probable pitchers + meta)
 - odds_snapshot.json      (raw prop odds aggregated from provider)
 - player_props.json       (modelled props, market comparison, edge score)

Usage:
  - create .env with ODDS_API_KEY and optionally FANGRAPHS_API_KEY, SAVANT_API_KEY
  - python fetch_data.py

Schedule:
  - Run daily at 09:00 America/New_York (9 AM EST). Use GitHub Actions or cron.

Notes:
 - This script is robust but depends on external endpoints. Some providers may not
   expose player props via their public API. TheOddsAPI is used as an example.
 - Baseball Savant leaderboard query parameters may need small adjustments if the
   endpoint changes. This script includes a sensible default CSV export attempt.
"""

# Standard library
import os
import sys
import time
import json
import math
import logging
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional

# Third-party
try:
    import requests
    import pandas as pd
    from retrying import retry
    from fuzzywuzzy import process as fw_process
    from fuzzywuzzy import fuzz as fw_fuzz
    from dotenv import load_dotenv
except Exception as e:
    print("Missing dependency:", e)
    print("Install requirements: pip install requests pandas retrying fuzzywuzzy python-dotenv python-Levenshtein")
    sys.exit(1)

# ----------------------------
# Configuration & Constants
# ----------------------------
BASE_DIR = Path(__file__).parent.resolve()
DATA_DIR = BASE_DIR / "data"
CACHE_DIR = DATA_DIR / "cache"
for d in (DATA_DIR, CACHE_DIR):
    d.mkdir(parents=True, exist_ok=True)

# ESPN scoreboard endpoint (public)
ESPN_SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard"

# Baseball Savant custom leaderboard CSV base (we will craft query params)
SAVANT_CSV_BASE = "https://baseballsavant.mlb.com/leaderboard/custom?{}"

# Example TheOddsAPI endpoints
THE_ODDS_API_BASE = "https://api.the-odds-api.com/v4"

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("fetch_data")

# Load .env
load_dotenv(BASE_DIR / ".env")

# Env values (fill .env)
ODDS_API_KEY = os.getenv("ODDS_API_KEY", "").strip()
ODDS_PROVIDER = os.getenv("ODDS_API_PROVIDER", "the_odds_api")
FANGRAPHS_API_KEY = os.getenv("FANGRAPHS_API_KEY", "").strip()
SAVANT_API_KEY = os.getenv("SAVANT_API_KEY", "").strip()  # not required for public CSV

# Time zone for scheduling / label (we'll use America/New_York)
LOCAL_TZ = "America/New_York"

# ----------------------------
# Utility helpers
# ----------------------------
def now_utc_iso():
    return datetime.now(timezone.utc).isoformat()

def safe_json_dumps(obj):
    return json.dumps(obj, default=str, indent=2)

def write_json(path: Path, data: Any):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    logger.info("Wrote %s", str(path))

def read_json(path: Path):
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def normalize_name(name: str) -> str:
    if not name:
        return ""
    s = name.strip()
    s = s.replace(".", "")
    s = s.replace(",", "")
    s = s.replace(" Jr", "")
    s = s.replace(" Jr.", "")
    s = s.replace(" II", "")
    s = s.replace(" III", "")
    s = s.replace(" IV", "")
    s = " ".join(s.split())  # squeeze whitespace
    return s.lower()

def best_fuzzy_match(name: str, candidates: List[str], min_score=75) -> Tuple[Optional[str], int]:
    """
    Return best match from candidates for name using fuzzywuzzy.
    """
    if not name or not candidates:
        return None, 0
    match, score = fw_process.extractOne(name, candidates, scorer=fw_fuzz.token_sort_ratio)
    if score >= min_score:
        return match, score
    return None, score

# ----------------------------
# Step 1: Fetch today's MLB scoreboard (ESPN)
# ----------------------------
@retry(stop_max_attempt_number=3, wait_fixed=1000)
def fetch_espn_scoreboard() -> Dict[str, Any]:
    logger.info("Fetching ESPN scoreboard")
    res = requests.get(ESPN_SCOREBOARD_URL, timeout=20)
    res.raise_for_status()
    return res.json()

def extract_games_from_espn(sb_json: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Parse ESPN scoreboard JSON into simplified game objects:
     - game_id
     - start_time_utc
     - venue
     - home: name, abbr, probable_pitcher
     - away: name, abbr, probable_pitcher
    """
    games = []
    for ev in sb_json.get("events", []):
        comp = ev.get("competitions", [{}])[0]
        comps = comp.get("competitors", [])
        home = next((c for c in comps if c.get("homeAway") == "home"), None)
        away = next((c for c in comps if c.get("homeAway") == "away"), None)
        game = {
            "game_id": ev.get("id"),
            "start_time_utc": comp.get("date"),
            "venue": comp.get("venue", {}).get("fullName"),
            "status": ev.get("status", {}).get("type", {}).get("description"),
            "home": {
                "name": home["team"]["displayName"],
                "abbr": home["team"].get("abbreviation"),
                "probable_pitcher": home.get("probablePitcher", {}).get("fullName")
            } if home else {},
            "away": {
                "name": away["team"]["displayName"],
                "abbr": away["team"].get("abbreviation"),
                "probable_pitcher": away.get("probablePitcher", {}).get("fullName")
            } if away else {}
        }
        games.append(game)
    logger.info("Extracted %d games from ESPN", len(games))
    return games

# ----------------------------
# Step 2: Fetch advanced stats from Baseball Savant (leaderboard CSV)
# ----------------------------
@retry(stop_max_attempt_number=3, wait_fixed=1200)
def fetch_savant_csv(params: Dict[str, Any]) -> str:
    """
    Query Baseball Savant custom leaderboard CSV endpoint.
    The exact params may need tuning. We'll attempt to ask for CSV in multiple ways.
    """
    qs = []
    for k, v in params.items():
        qs.append(f"{k}={requests.utils.quote(str(v))}")
    url = SAVANT_CSV_BASE.format("&".join(qs))
    logger.debug("Requesting Savant CSV: %s", url)
    res = requests.get(url, timeout=30)
    res.raise_for_status()
    return res.text

def savant_hitter_leaderboard_csv(season: int= datetime.now().year) -> pd.DataFrame:
    """
    Attempt to download a hitters leaderboard CSV containing fields:
      player_name, xwOBA, Barrel%, HardHit%, xBA, xSLG, exit velocity fields
    Note: Baseball Savant's query parameters are tricky; adjust if needed.
    """
    # Example param set for Savant "custom" leaderboard + csv=1; fields may vary.
    params = {
        "type": "batter",
        "season": season,
        "csv": "1"
    }
    try:
        text = fetch_savant_csv(params)
        # If result contains HTML, bail and return empty DataFrame
        if "<html" in text.lower() and "player" not in text.lower():
            logger.warning("Savant returned HTML or unexpected content; returning empty df")
            return pd.DataFrame()
        df = pd.read_csv(pd.compat.StringIO(text))
        logger.info("Fetched Savant hitters dataframe shape %s", df.shape)
        return df
    except Exception as e:
        logger.exception("Savant hitter CSV fetch failed: %s", e)
        return pd.DataFrame()

def savant_pitcher_leaderboard_csv(season: int = datetime.now().year) -> pd.DataFrame:
    params = {
        "type": "pitcher",
        "season": season,
        "csv": "1"
    }
    try:
        text = fetch_savant_csv(params)
        if "<html" in text.lower() and "player" not in text.lower():
            logger.warning("Savant returned HTML or unexpected content; returning empty df")
            return pd.DataFrame()
        df = pd.read_csv(pd.compat.StringIO(text))
        logger.info("Fetched Savant pitchers dataframe shape %s", df.shape)
        return df
    except Exception as e:
        logger.exception("Savant pitcher CSV fetch failed: %s", e)
        return pd.DataFrame()

def build_hitter_mapping_from_savant(df: pd.DataFrame) -> Dict[str, Dict[str, Any]]:
    """
    Convert savant hitters dataframe to a mapping {normalized_name: stats_dict}
    Attempt to pick common columns; use .get with fallback column names.
    """
    mapping = {}
    if df is None or df.empty:
        return mapping
    # Normalize column names for robust access
    lower_cols = {c.lower(): c for c in df.columns}
    # helper to pick a column by possible aliases
    def pick(*aliases):
        for a in aliases:
            if a.lower() in lower_cols:
                return lower_cols[a.lower()]
        return None
    col_player = pick("player_name", "player", "Player", "name")
    col_xwoba = pick("xwoba", "xwOBA", "xwOBA/expected_wOBA", "xwob")
    col_barrel = pick("barrel", "barrel_percent", "barrel%")
    col_hard = pick("hard_hit_percent", "hardhit%", "hardhit")
    col_xba = pick("xba", "xBA")
    col_xslg = pick("xslg", "xSLG")
    col_babip = pick("babip", "BABIP")
    col_pa = pick("pa", "PA")
    col_iso = pick("iso", "ISO")
    for _, row in df.iterrows():
        name_raw = row.get(col_player) if col_player else None
        if not name_raw:
            continue
        name_n = normalize_name(str(name_raw))
        stats = {}
        # use try/except to avoid KeyErrors
        try:
            if col_xwoba and pd.notnull(row.get(col_xwoba)): stats['xwOBA'] = float(row.get(col_xwoba))
            if col_barrel and pd.notnull(row.get(col_barrel)): stats['Barrel%'] = float(row.get(col_barrel))
            if col_hard and pd.notnull(row.get(col_hard)): stats['HardHit%'] = float(row.get(col_hard))
            if col_xba and pd.notnull(row.get(col_xba)): stats['xBA'] = float(row.get(col_xba))
            if col_xslg and pd.notnull(row.get(col_xslg)): stats['xSLG'] = float(row.get(col_xslg))
            if col_babip and pd.notnull(row.get(col_babip)): stats['BABIP'] = float(row.get(col_babip))
            if col_pa and pd.notnull(row.get(col_pa)): stats['PA'] = float(row.get(col_pa))
            if col_iso and pd.notnull(row.get(col_iso)): stats['ISO'] = float(row.get(col_iso))
        except Exception:
            pass
        mapping[name_n] = stats
    logger.info("Built hitter mapping of %d players from Savant", len(mapping))
    return mapping

def build_pitcher_mapping_from_savant(df: pd.DataFrame) -> Dict[str, Dict[str, Any]]:
    mapping = {}
    if df is None or df.empty:
        return mapping
    lower_cols = {c.lower(): c for c in df.columns}
    def pick(*aliases):
        for a in aliases:
            if a.lower() in lower_cols:
                return lower_cols[a.lower()]
        return None
    col_player = pick("player_name", "player", "Player", "name")
    col_xfip = pick("xfip", "xFIP")
    col_siera = pick("siera", "SIERA")
    col_csw = pick("csw", "CSW%", "CSW")
    col_swstr = pick("swstr", "SwStr%", "SwStr")
    col_k9 = pick("k/9", "k9", "K/9")
    col_bb9 = pick("bb/9", "bb9", "BB/9")
    col_hrfb = pick("hr/fb", "hrfb", "HR/FB")
    for _, row in df.iterrows():
        name_raw = row.get(col_player)
        if not name_raw:
            continue
        name_n = normalize_name(str(name_raw))
        stats = {}
        try:
            if col_xfip and pd.notnull(row.get(col_xfip)): stats['xFIP'] = float(row.get(col_xfip))
            if col_siera and pd.notnull(row.get(col_siera)): stats['SIERA'] = float(row.get(col_siera))
            if col_csw and pd.notnull(row.get(col_csw)): stats['CSW'] = float(row.get(col_csw))
            if col_swstr and pd.notnull(row.get(col_swstr)): stats['SwStr%'] = float(row.get(col_swstr))
            if col_k9 and pd.notnull(row.get(col_k9)): stats['K9'] = float(row.get(col_k9))
            if col_bb9 and pd.notnull(row.get(col_bb9)): stats['BB9'] = float(row.get(col_bb9))
            if col_hrfb and pd.notnull(row.get(col_hrfb)): stats['HR/FB'] = float(row.get(col_hrfb))
        except Exception:
            pass
        mapping[name_n] = stats
    logger.info("Built pitcher mapping of %d players from Savant", len(mapping))
    return mapping

# ----------------------------
# Step 3: TheOddsAPI integration (player props)
# ----------------------------
@retry(stop_max_attempt_number=3, wait_fixed=800)
def fetch_oddsapi_playerprops(sport_key: str = "baseball_mlb", regions: str = "us", markets: str = "playerprops") -> List[Dict[str, Any]]:
    """
    Query TheOddsAPI for playerprops market if available.
    Note: TheOddsAPI's coverage may vary; some providers do not include detailed player props.
    """
    if not ODDS_API_KEY:
        logger.warning("No ODDS_API_KEY configured; skipping odds fetch")
        return []
    url = f"{THE_ODDS_API_BASE}/sports/{sport_key}/odds"
    params = {"apiKey": ODDS_API_KEY, "regions": regions, "markets": markets, "oddsFormat": "american"}
    logger.info("Fetching odds from TheOddsAPI (may include playerprops if offered by provider)")
    res = requests.get(url, params=params, timeout=30)
    res.raise_for_status()
    return res.json()

def extract_playerprops_from_odds_snapshot(odds_json: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Parse the TheOddsAPI response structure to extract anything that looks like player props:
    - iterate games -> bookmakers -> markets -> outcomes
    - if market key contains 'player' or 'playerprops', gather outcomes
    """
    props = []
    if not odds_json:
        return props
    for game in odds_json:
        home = game.get("home_team") or game.get("teams", ["",""])[1]
        away = game.get("away_team") or game.get("teams", ["",""])[0]
        game_label = f"{away} @ {home}"
        bookmakers = game.get("bookmakers", [])
        for book in bookmakers:
            book_name = book.get("title")
            for market in book.get("markets", []):
                mkey = market.get("key", "")
                # Accept player-like markets:
                if ("player" in mkey) or ("playerprops" in mkey) or ("player_prop" in mkey) or ("props" in mkey and "player" in market.get("key","")):
                    for outcome in market.get("outcomes", []):
                        label = outcome.get("name")
                        price = outcome.get("price", None)
                        props.append({
                            "game": game_label,
                            "site": book_name,
                            "market_key": mkey,
                            "label": label,
                            "price": price,
                            "raw": outcome
                        })
    logger.info("Extracted %d prop outcomes from odds snapshot", len(props))
    return props

# ----------------------------
# Step 4: Prop modeling functions (heuristics + calibrations)
# ----------------------------
def clamp(x, a=0.0, b=1.0):
    try:
        return max(a, min(b, float(x)))
    except Exception:
        return a

def hr_prob_model(batter: Dict[str, Any], pitcher: Dict[str, Any], park_factor: float = 1.0) -> Dict[str, Any]:
    """
    Estimate batter anytime-HR probability when facing a pitcher.
    Heuristic, Poisson-based mapping for readability and interpretability.
    """
    # baseline per-player HR "rate" used as lambda for Poisson
    BASE_RATE = 0.035  # baseline expected HR-count per game
    barrel = batter.get("Barrel%", 0.03) or 0.03
    xwoba = batter.get("xwOBA", 0.320) or 0.320
    pa = batter.get("PA", 4.0) or 4.0

    xfip = pitcher.get("xFIP", 4.0) or 4.0
    hrfb = pitcher.get("HR/FB", 0.10) or 0.10
    # power_score: scales with barrel and xwOBA above league baseline
    power_score = (barrel * 20.0) + max(0.0, (xwoba - 0.32) * 2.5)
    pitcher_suppress = 1.0 + ((xfip - 4.0) * 0.08) + max(0.0, (hrfb - 0.10))
    exp_rate = BASE_RATE * (1.0 + power_score) / pitcher_suppress * park_factor
    exp_rate = clamp(exp_rate, 0.002, 0.8)
    prob_any_hr = 1.0 - math.exp(-exp_rate)
    # confidence based on sample stability approximated by PA and barrel
    sample_stability = min(1.0, (pa / 600.0) + 0.1)  # 600 PA ~ full season
    confidence = clamp(0.25 + (barrel * 3.0) + (sample_stability * 0.2), 0.05, 0.98)
    return {"prob": prob_any_hr, "expected_rate": exp_rate, "confidence": confidence}

def tb_model(batter: Dict[str, Any], pitcher: Dict[str, Any], park_factor: float = 1.0) -> Dict[str, Any]:
    """
    Project expected total bases for a batter in a game and probability of exceeding common thresholds.
    Uses xwOBA -> TB-per-PA mapping.
    """
    pa = batter.get("PA", 4.0) or 4.0
    xwoba = batter.get("xwOBA", 0.320) or 0.320
    tb_per_pa = max(0.08, (xwoba - 0.18) * 1.6)  # calibrated mapping
    pitcher_csw = pitcher.get("CSW", 0.26) or pitcher.get("CSW%", 0.26) or 0.26
    pitcher_factor = 1.0 - (pitcher_csw - 0.26) * 0.6
    expected_tb = pa * tb_per_pa * pitcher_factor * park_factor
    std = max(0.5, expected_tb * 0.36)
    # compute probability over 1.5
    z = (expected_tb - 1.5) / std
    prob_over_1_5 = 0.5 * (1 + math.erf(z / math.sqrt(2)))
    return {"exp_tb": expected_tb, "std": std, "prob_over_1_5": prob_over_1_5}

def hits_model(batter: Dict[str, Any], pitcher: Dict[str, Any], park_factor: float = 1.0) -> Dict[str, Any]:
    xba = batter.get("xBA", batter.get("xwOBA", 0.24)) or 0.24
    pa = batter.get("PA", 4.0) or 4.0
    expected_hits = pa * xba * park_factor
    prob_at_least_one = 1.0 - math.exp(-expected_hits)
    conf = clamp(0.25 + min(pa/600.0, 0.5), 0.05, 0.98)
    return {"exp_hits": expected_hits, "prob_1plus": prob_at_least_one, "confidence": conf}

def walk_model(batter: Dict[str, Any], pitcher: Dict[str, Any]) -> Dict[str, Any]:
    bb = batter.get("BB%", 0.08) or batter.get("BB_rate", 0.08) or 0.08
    pb = pitcher.get("BB9", 3.0) or 3.0
    walk_prob = clamp(bb * (1.0 + (pb - 3.0) * 0.05), 0.01, 0.45)
    conf = clamp(0.2 + min(batter.get("PA",4.0)/600.0, 0.4), 0.05, 0.95)
    return {"prob": walk_prob, "confidence": conf}

def batter_ks_model(batter: Dict[str, Any], pitcher: Dict[str, Any]) -> Dict[str, Any]:
    k_pct = batter.get("K%", 0.22) or 0.22
    pa = batter.get("PA", 4.0) or 4.0
    k9 = pitcher.get("K9", pitcher.get("K/9", 8.5)) or 8.5
    pitcher_factor = 1.0 + ((k9 - 8.5) * 0.05)
    exp_ks = pa * k_pct * pitcher_factor
    # prob over 1.5 strikes using Poisson complement approx 1 - P(0)-P(1)
    import math
    lam = exp_ks
    prob_over_1_5 = 1 - (math.exp(-lam) * (1 + lam))
    conf = clamp(0.2 + min(pa/600.0,0.4), 0.05, 0.95)
    return {"exp_k": exp_ks, "prob_over_1_5": prob_over_1_5, "confidence": conf}

def pitcher_k_model(pitcher: Dict[str, Any], est_ip: float = 5.0) -> Dict[str, Any]:
    k9 = pitcher.get("K9", pitcher.get("K/9", 8.5)) or 8.5
    exp_k = (k9 / 9.0) * est_ip
    std = max(1.0, exp_k * 0.42)
    z = (exp_k - 7.5) / std
    prob_over_7_5 = 0.5 * (1 + math.erf(z / math.sqrt(2)))
    conf = clamp(0.25 + 0.3 * (pitcher.get("sample_stability", 0.6) or 0.6), 0.05, 0.98)
    return {"exp_k": exp_k, "prob_over_7_5": prob_over_7_5, "confidence": conf}

# ----------------------------
# Step 5: Market implied probabilities parsing
# ----------------------------
def parse_american_to_prob(odds) -> Optional[float]:
    try:
        if odds is None:
            return None
        o = float(odds)
        if o > 0:
            return 100.0 / (o + 100.0)
        else:
            return -o / (-o + 100.0)
    except Exception:
        # try parsing if odds string contains +/- characters
        try:
            s = str(odds).strip()
            if s.startswith('+') or s.startswith('-'):
                return parse_american_to_prob(int(s))
            if s.upper() == "EVEN":
                return 0.5
        except Exception:
            return None
    return None

# ----------------------------
# Step 6: Matching players in market to modelled players
# ----------------------------
def match_market_entry_to_player(player_name: str, market_entries: List[Dict[str, Any]], min_score=70) -> Optional[Dict[str, Any]]:
    """
    Attempt to find an entry in market_entries (from TheOddsAPI) that corresponds
    to the player_name (any label/outcome which contains player substring).
    Returns the matched market dict or None.
    """
    if not player_name or not market_entries:
        return None
    pname = normalize_name(player_name)
    labels = [m.get("label", "") or str(m.get("raw", "")) for m in market_entries]
    # fuzzy match
    match_label, score = best_fuzzy_match(pname, labels, min_score=min_score)
    if match_label:
        idx = labels.index(match_label)
        return market_entries[idx]
    # fallback: substring match
    for m in market_entries:
        lab = (m.get("label","") or "").lower()
        raw = (json.dumps(m.get("raw","")) or "").lower()
        if pname in lab or pname in raw:
            return m
    return None

# ----------------------------
# Step 7: Main orchestrator that ties everything together
# ----------------------------
def orchestrate(today_season: int = None):
    """
    Main pipeline orchestration.
    1) fetch scoreboard
    2) fetch savant leaderboards (hitters + pitchers) -> build caches
    3) fetch odds (TheOddsAPI playerprops)
    4) build modelled props for lineup players (or top hitters if lineups missing)
    5) match market entries & compute edge = model_prob - market_implied_prob (or model_ev)
    6) save JSON outputs
    """
    logger.info("Starting orchestration")
    if today_season is None:
        today_season = datetime.now().year

    # 1) scoreboard
    try:
        sb = fetch_espn_scoreboard()
        games = extract_games_from_espn(sb)
    except Exception as e:
        logger.exception("Failed to fetch scoreboard: %s", e)
        # fallback to previous games_today if exists
        prev = read_json(DATA_DIR / "games_today.json")
        if prev:
            games = prev.get("games", [])
            logger.warning("Using cached games_today.json with %d games", len(games))
        else:
            games = []
    write_json(DATA_DIR / "games_today.json", {"generated_at": now_utc_iso(), "games": games})

    # 2) Savant leaderboards -> caches
    hitters_map = {}
    pitchers_map = {}
    try:
        logger.info("Fetching Savant leaderboards (this can be slow)")
        df_hit = savant_hitter_leaderboard_csv(season=today_season)
        df_pitch = savant_pitcher_leaderboard_csv(season=today_season)
        hitters_map = build_hitter_mapping_from_savant(df_hit)
        pitchers_map = build_pitcher_mapping_from_savant(df_pitch)
        # Save caches
        write_json(CACHE_DIR / f"hitter_stats_{today_season}.json", hitters_map)
        write_json(CACHE_DIR / f"pitcher_stats_{today_season}.json", pitchers_map)
    except Exception as e:
        logger.exception("Savant leaderboards fetch failed: %s", e)
        # Try reading caches if available
        hm = read_json(CACHE_DIR / f"hitter_stats_{today_season}.json")
        pm = read_json(CACHE_DIR / f"pitcher_stats_{today_season}.json")
        hitters_map = hm or {}
        pitchers_map = pm or {}

    # 3) Odds provider (TheOddsAPI) -> extract player props snapshot
    odds_snapshot_raw = []
    odds_props = []
    if ODDS_API_KEY:
        try:
            odds_snapshot_raw = fetch_oddsapi_playerprops()
            # Save raw
            write_json(DATA_DIR / "odds_api_raw.json", odds_snapshot_raw)
            odds_props = extract_playerprops_from_odds_snapshot(odds_snapshot_raw)
            write_json(DATA_DIR / "odds_snapshot.json", {"generated_at": now_utc_iso(), "props": odds_props})
        except Exception as e:
            logger.exception("Odds fetch failed: %s", e)
            # fallback to previous snapshot
            odds_cached = read_json(DATA_DIR / "odds_snapshot.json")
            if odds_cached:
                odds_props = odds_cached.get("props", [])
    else:
        logger.warning("No ODDS_API_KEY provided. Skip fetching odds. Use .env to set ODDS_API_KEY.")
        odds_cached = read_json(DATA_DIR / "odds_snapshot.json")
        odds_props = odds_cached.get("props", []) if odds_cached else []

    # 4) Build modelled props
    # We need a list of players to evaluate. Ideally we have lineups; ESPN lineup scraping is brittle.
    # Use the probable pitchers + hitters from Savant caches as fallback top hitters to evaluate.
    modelled_props = []
    # Build a master list of candidate batters per game:
    for g in games:
        home = g.get("home", {})
        away = g.get("away", {})
        # Determine opponent pitchers stats
        home_pitch_name = home.get("probable_pitcher") or ""
        away_pitch_name = away.get("probable_pitcher") or ""
        home_pitch_norm = normalize_name(home_pitch_name)
        away_pitch_norm = normalize_name(away_pitch_name)
        home_pitch_stats = pitchers_map.get(home_pitch_norm, {"name": home_pitch_name})
        away_pitch_stats = pitchers_map.get(away_pitch_norm, {"name": away_pitch_name})
        # Determine batter list: if we have lineup scraping implemented, we'd use it.
        # For now, pick sensible candidate lists:
        # - If hitters_map includes players from these teams, prefer those players (top 9).
        # Build list of candidate batters by sampling hitters_map keys that contain team abbr if available
        def top_hitters_for_team(team_abbr):
            candidates = []
            if not team_abbr:
                return []
            team_abbr_lower = team_abbr.lower()
            # look for keys in hitters_map that contain the abbr (not always possible)
            for name in hitters_map.keys():
                # Some savant names include team abbreviations or we may use other heuristics
                if team_abbr_lower in name:
                    candidates.append(name)
            # fallback: take global top hitters mapping head
            if not candidates:
                # use first N hitters from mapping
                candidates = list(hitters_map.keys())[:9]
            return candidates[:9]

        away_candidates = top_hitters_for_team(away.get("abbr")) or list(hitters_map.keys())[:9]
        home_candidates = top_hitters_for_team(home.get("abbr")) or list(hitters_map.keys())[:9]

        # Evaluate away batters vs home pitcher
        for pname in away_candidates:
            batter_stats = hitters_map.get(pname, {})
            batter = {"name": pname, "team": away.get("abbr"), **batter_stats}
            prop_entry = {"game": f"{away.get('abbr')} @ {home.get('abbr')}", "player": pname, "team": away.get("abbr"), "opponent_pitcher": home_pitch_name}
            # compute prop models
            try:
                hr = hr_prob_model(batter, home_pitch_stats)
                tb = tb_model(batter, home_pitch_stats)
                hits = hits_model(batter, home_pitch_stats)
                walk = walk_model(batter, home_pitch_stats)
                ks = batter_ks_model(batter, home_pitch_stats)
            except Exception as e:
                logger.exception("Prop compute error for %s: %s", pname, e)
                continue
            prop_entry["model"] = {"hr": hr, "tb": tb, "hits": hits, "walk": walk, "ks": ks}
            # find market entry (if any)
            market = match_market_entry_to_player(pname, odds_props)
            prop_entry["market"] = market
            # compute edge where possible (simple model_prob - market_prob)
            if market and market.get("price") is not None:
                # attempt to parse a single price value; TheOdds API stores outcomes with "price" as numeric american
                market_prob = parse_american_to_prob(market.get("price"))
            else:
                market_prob = None
            prop_entry["market_implied_prob"] = market_prob
            prop_entry["edge"] = hr["prob"] - market_prob if market_prob else None
            modelled_props.append(prop_entry)

        # Evaluate home batters vs away pitcher
        for pname in home_candidates:
            batter_stats = hitters_map.get(pname, {})
            batter = {"name": pname, "team": home.get("abbr"), **batter_stats}
            prop_entry = {"game": f"{away.get('abbr')} @ {home.get('abbr')}", "player": pname, "team": home.get("abbr"), "opponent_pitcher": away_pitch_name}
            try:
                hr = hr_prob_model(batter, away_pitch_stats)
                tb = tb_model(batter, away_pitch_stats)
                hits = hits_model(batter, away_pitch_stats)
                walk = walk_model(batter, away_pitch_stats)
                ks = batter_ks_model(batter, away_pitch_stats)
            except Exception as e:
                logger.exception("Prop compute error for %s: %s", pname, e)
                continue
            prop_entry["model"] = {"hr": hr, "tb": tb, "hits": hits, "walk": walk, "ks": ks}
            market = match_market_entry_to_player(pname, odds_props)
            prop_entry["market"] = market
            if market and market.get("price") is not None:
                market_prob = parse_american_to_prob(market.get("price"))
            else:
                market_prob = None
            prop_entry["market_implied_prob"] = market_prob
            prop_entry["edge"] = hr["prob"] - market_prob if market_prob else None
            modelled_props.append(prop_entry)

    # 5) Summarize and sort modelled_props by best absolute edge where available (HR edge)
    # Keep only core fields in saved JSON to keep size acceptable
    serialized_props = []
    for p in modelled_props:
        serialized_props.append({
            "generated_at": now_utc_iso(),
            "game": p.get("game"),
            "player": p.get("player"),
            "team": p.get("team"),
            "opponent_pitcher": p.get("opponent_pitcher"),
            "model": p.get("model"),
            "market": p.get("market"),
            "market_implied_prob": p.get("market_implied_prob"),
            "edge": p.get("edge")
        })

    # Save player_props.json
    player_props_path = DATA_DIR / "player_props.json"
    write_json(player_props_path, {"generated_at": now_utc_iso(), "props": serialized_props})
    logger.info("Saved %d modelled props", len(serialized_props))

    # Save a slim games_today.json (already wrote earlier) - update to include basic edges per game (if possible)
    # Simple team-edge approximation: average modelled edge for players on each side
    game_edges = {}
    for p in serialized_props:
        g = p.get("game")
        edge = p.get("edge")
        if edge is None:
            continue
        entry = game_edges.setdefault(g, {"edges": [], "count": 0})
        entry["edges"].append(edge)
        entry["count"] += 1
    # compute mean edge per game
    edges_out = []
    for g, data in game_edges.items():
        avg_edge = sum(data["edges"]) / len(data["edges"]) if data["edges"] else None
        edges_out.append({"game": g, "avg_prop_edge": avg_edge, "num_props": data["count"]})
    write_json(DATA_DIR / "game_prop_edges.json", {"generated_at": now_utc_iso(), "edges": edges_out})
    logger.info("Wrote game_prop_edges.json with %d entries", len(edges_out))

    # Save odds snapshot (already written above). Also write a compact odds list
    write_json(DATA_DIR / "odds_compact.json", {"generated_at": now_utc_iso(), "num_props": len(odds_props)})

    logger.info("Orchestration complete. Data written to %s", DATA_DIR)
    return {
        "games_file": str(DATA_DIR / "games_today.json"),
        "player_props_file": str(player_props_path),
        "odds_snapshot_file": str(DATA_DIR / "odds_snapshot.json"),
        "game_prop_edges_file": str(DATA_DIR / "game_prop_edges.json")
    }

# ----------------------------
# CLI / Main
# ----------------------------
def main():
    parser = argparse.ArgumentParser(description="Fetch daily MLB games, advanced stats and player props (TheOddsAPI).")
    parser.add_argument("--season", type=int, default=None, help="Season year to fetch savant leaderboards for (default: current year)")
    parser.add_argument("--no-save-cache", dest="save_cache", action="store_false", help="Do not save caches to disk")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()
    if args.debug:
        logger.setLevel(logging.DEBUG)
    logger.info("fetch_data.py starting (debug=%s)", args.debug)
    start = time.time()
    try:
        result = orchestrate(today_season=args.season)
        logger.info("Result files: %s", result)
    except Exception as e:
        logger.exception("Main orchestration failed: %s", e)
        sys.exit(2)
    elapsed = time.time() - start
    logger.info("Completed in %.1f seconds", elapsed)

if __name__ == "__main__":
    main()
