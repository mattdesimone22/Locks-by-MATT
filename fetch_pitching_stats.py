# fetch_pitching_stats.py
import os, json, logging
from dotenv import load_dotenv
import requests
import pandas as pd
from ratelimit import limits, sleep_and_retry

load_dotenv()
logger = logging.getLogger("fetch_pitching_stats")
logger.setLevel(logging.INFO)

ESPN_SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard"

@sleep_and_retry
@limits(calls=60, period=60)
def fetch_scoreboard():
    r = requests.get(ESPN_SCOREBOARD, timeout=20)
    r.raise_for_status()
    return r.json()

def extract_probables(scoreboard_json):
    games = []
    for ev in scoreboard_json.get("events", []):
        try:
            comp = ev['competitions'][0]
            home = comp['competitors'][0]
            away = comp['competitors'][1]
            home_team = home['team']['shortDisplayName']
            away_team = away['team']['shortDisplayName']
            home_prob = home.get('probablePitcher', {}).get('fullName', None)
            away_prob = away.get('probablePitcher', {}).get('fullName', None)
            games.append({
                "game_id": ev.get("id"),
                "home_team": home_team,
                "away_team": away_team,
                "home_pitcher": home_prob,
                "away_pitcher": away_prob,
                "start_time": comp.get("date")
            })
        except Exception as e:
            logger.exception("Failed to parse event: %s", e)
            continue
    return games

def fetch_pitcher_advanced(pitcher_name):
    """
    Placeholder: implement retrieval from FanGraphs or Savant for pitcher metrics.
    We'll return a dict with a standard shape.
    """
    # Real impl: map name -> id, call API, or parse provider.
    return {
        "name": pitcher_name,
        "xFIP": None,
        "SIERA": None,
        "CSW%": None,
        "K9": None,
        "BB9": None,
        "HRFB": None,
        "StuffPlus": None
    }

def build_pitcher_dataset(out_path="data/pitchers.json"):
    sb = fetch_scoreboard()
    games = extract_probables(sb)
    pitchers = {}
    for g in games:
        for p in [g["home_pitcher"], g["away_pitcher"]]:
            if p and p not in pitchers:
                pitchers[p] = fetch_pitcher_advanced(p)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump({"games": games, "pitchers": pitchers}, f, indent=2)
    logger.info("Wrote pitchers dataset to %s", out_path)
    return out_path

if __name__ == "__main__":
    build_pitcher_dataset()
