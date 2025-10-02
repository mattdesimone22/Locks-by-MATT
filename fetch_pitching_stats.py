"""
fetch_pitching_stats.py

Uses MLB Stats API (statsapi.mlb.com) to get today's schedule and probable pitchers.
Also fetches pitcher seasonal stats (K/9, BB/9, HR/9, xFIP if available via pybaseball later).

Outputs a cached JSON: data/pitchers_cache.json and data/games_probables.json
"""
import requests, json, os, logging
from datetime import datetime, timezone
from time import sleep

logger = logging.getLogger("fetch_pitching_stats")
logging.basicConfig(level=logging.INFO)

MLB_SCHEDULE_URL = "https://statsapi.mlb.com/api/v1/schedule"
MLB_PLAYER_URL = "https://statsapi.mlb.com/api/v1/people/{}"

CACHE_DIR = "data"
os.makedirs(CACHE_DIR, exist_ok=True)

def get_todays_games(date_str=None):
    # date_str in YYYY-MM-DD (UTC local). If None -> today
    params = {"sportId": 1}
    if date_str:
        params["date"] = date_str
    r = requests.get(MLB_SCHEDULE_URL, params=params, timeout=20)
    r.raise_for_status()
    return r.json()

def extract_probables(schedule_json):
    games = []
    for date in schedule_json.get("dates", []):
        for game in date.get("games", []):
            gamePk = game.get("gamePk")
            teams = game.get("teams", {})
            home = teams.get("home", {})
            away = teams.get("away", {})
            home_team = home.get("team", {}).get("name")
            away_team = away.get("team", {}).get("name")
            # probable pitchers may be nested in 'probablePitcher' or 'probablePitcherId'
            home_prob = home.get("probablePitcher", {})
            away_prob = away.get("probablePitcher", {})
            home_pitcher = None
            away_pitcher = None
            if home_prob:
                home_pitcher = home_prob.get("fullName") or home_prob.get("id")
            if away_prob:
                away_pitcher = away_prob.get("fullName") or away_prob.get("id")
            games.append({
                "gamePk": gamePk,
                "startTime": game.get("gameDate"),
                "home_team": home_team,
                "away_team": away_team,
                "home_pitcher": home_pitcher,
                "away_pitcher": away_pitcher
            })
    return games

def get_player_stats_from_mlb(person_id):
    """
    Use MLB People endpoint to get seasonal basic stats; can fetch current season pitching stats.
    """
    r = requests.get(MLB_PLAYER_URL.format(person_id), timeout=10)
    r.raise_for_status()
    data = r.json()
    return data

def build_pitcher_cache(games, out_path=os.path.join(CACHE_DIR, "pitchers_cache.json")):
    cache = {}
    for g in games:
        for pname in (g.get("home_pitcher"), g.get("away_pitcher")):
            if not pname:
                continue
            # MLB API sometimes returns fullName instead of id; try to get player id via search endpoint
            # We'll try to resolve by searching players by name via people endpoint using '?personIds' isn't direct.
            # Simpler approach: query Stats API people search is not public, so skip id resolution for now.
            # We'll store the name and leave advanced metrics to pybaseball in next step.
            if pname not in cache:
                cache[pname] = {"name": pname, "resolved": False}
    with open(out_path, "w") as f:
        json.dump({"updated": datetime.now(timezone.utc).isoformat(), "pitchers": cache}, f, indent=2)
    logger.info("Wrote pitcher cache to %s", out_path)
    return out_path

if __name__ == "__main__":
    today = datetime.now().strftime("%Y-%m-%d")
    sched = get_todays_games(today)
    games = extract_probables(sched)
    build_pitcher_cache(games)
    with open(os.path.join(CACHE_DIR, "games_probables.json"), "w") as f:
        json.dump({"updated": datetime.now(timezone.utc).isoformat(), "games": games}, f, indent=2)
    logger.info("Wrote games probables")

