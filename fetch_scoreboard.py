# fetch_scoreboard.py
import requests, json, os, time
from datetime import datetime, timezone
from retrying import retry

OUTDIR = "data"
os.makedirs(OUTDIR, exist_ok=True)

ESPN_SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard"

@retry(stop_max_attempt_number=3, wait_fixed=800)
def fetch_scoreboard():
    r = requests.get(ESPN_SCOREBOARD, timeout=20)
    r.raise_for_status()
    return r.json()

def extract_games(scoreboard_json):
    games = []
    for ev in scoreboard_json.get("events", []):
        comp = ev.get("competitions", [{}])[0]
        competitors = comp.get("competitors", [])
        home = next((c for c in competitors if c.get("homeAway") == "home"), None)
        away = next((c for c in competitors if c.get("homeAway") == "away"), None)
        game = {
            "game_id": ev.get("id"),
            "start_time_utc": comp.get("date"),
            "venue": comp.get("venue", {}).get("fullName"),
            "home": {
                "name": home['team']['displayName'],
                "abbr": home['team'].get('abbreviation'),
                "probable_pitcher": home.get('probablePitcher', {}).get('fullName')
            } if home else {},
            "away": {
                "name": away['team']['displayName'],
                "abbr": away['team'].get('abbreviation'),
                "probable_pitcher": away.get('probablePitcher', {}).get('fullName')
            } if away else {}
        }
        games.append(game)
    return games

def write_games_file(games):
    out = {"date": datetime.now(timezone.utc).isoformat(), "games": games}
    path = os.path.join(OUTDIR, "games_today.json")
    with open(path, "w") as f:
        json.dump(out, f, indent=2)
    print("Wrote", path)
    return path

def main():
    sb = fetch_scoreboard()
    games = extract_games(sb)
    return write_games_file(games)

if __name__ == "__main__":
    main()
