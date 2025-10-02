# generate_picks.py
import json, logging, os
from datetime import datetime
from fetch_pitching_stats import fetch_scoreboard, extract_probables, fetch_pitcher_advanced
from fetch_player_stats import build_player_stats_cache
from line_movement_tracker import snapshot_odds
from analytics_utils import safeget
from edge_calculator import compute_edge_for_game
from player_prop_predictor import predict_player_total_bases, predict_player_k_props

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("generate_picks")

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

def load_cached_stats():
    # For now we use simple caches; in production maintain DB or S3
    player_stats_path = os.path.join(DATA_DIR, "players_stats.json")
    pitcher_stats_path = os.path.join(DATA_DIR, "pitchers.json")
    players = {}
    pitchers = {}
    try:
        with open(player_stats_path, "r") as f:
            players = json.load(f)
    except:
        logger.info("No player cache found.")

    try:
        with open(pitcher_stats_path, "r") as f:
            pitchers = json.load(f)
    except:
        logger.info("No pitcher cache found.")
    return players, pitchers

def generate():
    # 1) Fetch scoreboard / probables
    try:
        sb = fetch_scoreboard()
    except Exception as e:
        logger.exception("Failed to fetch scoreboard: %s", e)
        return
    games = extract_probables(sb)

    # 2) Ensure cached stats exist
    build_player_stats_cache()  # create or update player cache (placeholder)
    players_cache, pitchers_cache = load_cached_stats()
    snapshot_odds()  # optional save of odds for market factors

    picks = []
    for g in games:
        home = g['home_team']
        away = g['away_team']
        home_pitcher_name = g.get("home_pitcher")
        away_pitcher_name = g.get("away_pitcher")
        # fetch pitcher metrics (cached or fetch)
        home_pitcher = pitchers_cache.get(home_pitcher_name) or fetch_pitcher_advanced(home_pitcher_name)
        away_pitcher = pitchers_cache.get(away_pitcher_name) or fetch_pitcher_advanced(away_pitcher_name)

        # team metrics placeholder
        home_team_metrics = {"wRC+": 105, "xFIP": home_pitcher.get("xFIP") or 3.5, "bullpen_xFIP": 3.7, "park_factor": 1.0, "rest_days": 0}
        away_team_metrics = {"wRC+": 100, "xFIP": away_pitcher.get("xFIP") or 3.8, "bullpen_xFIP": 4.0, "park_factor": 1.0, "rest_days": 0}

        # market delta stub (implement by reading odds snapshot)
        market_delta = 0.0

        prob_home = compute_edge_for_game(home_team_metrics, away_team_metrics, home_pitcher, away_pitcher, market_delta)
        # Convert probability to pick (moneyline)
        pick = f"{home} ML" if prob_home > 0.5 else f"{away} ML"
        edge_value = prob_home if prob_home > 0.5 else (1 - prob_home)

        # compute top player props for both teams (simplified)
        top_props = []
        # choose sample player names from cache if available
        home_players = players_cache.get(home, []) if isinstance(players_cache, dict) else []
        away_players = players_cache.get(away, []) if isinstance(players_cache, dict) else []

        # for demo, pick first available player on each side
        if home_players:
            p = home_players[0]
            prop = predict_player_total_bases(p, away_pitcher)
            top_props.append({"player": p.get("name","unknown"), "prop": "Total Bases", "expected": prop})
        if away_players:
            p = away_players[0]
            prop = predict_player_k_props(p, home_pitcher)
            top_props.append({"player": p.get("name","unknown"), "prop": "Strikeouts", "expected": prop})

        picks.append({
            "matchup": f"{away} vs {home}",
            "pick": pick,
            "edge": round(edge_value, 3),
            "probability": round(prob_home, 3),
            "reason": f"Model probability home_win={prob_home:.3f}",
            "team_stats": f"{home_team_metrics} | {away_team_metrics}",
            "player_stats": f"{top_props}",
            "odds_snapshot": None,
            "pitcher_matchup": f"{away_pitcher_name} vs {home_pitcher_name}"
        })

    out = {
        "date": datetime.utcnow().strftime("%Y-%m-%d"),
        "generated_at_utc": datetime.utcnow().isoformat(),
        "games": picks
    }

    out_path = os.path.join(DATA_DIR, "picks_today.json")
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)
    logger.info("Wrote picks to %s", out_path)
    return out_path

if __name__ == "__main__":
    generate()
