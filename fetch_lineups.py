# fetch_lineups.py
import os, json, requests, re
from bs4 import BeautifulSoup
from retrying import retry
from datetime import datetime, timezone

OUTDIR = "data"
os.makedirs(OUTDIR, exist_ok=True)

ESPN_BOXSCORE_URL = "https://www.espn.com/mlb/boxscore/_/gameId/{game_id}"

@retry(stop_max_attempt_number=2, wait_fixed=800)
def fetch_lineup_game(gid):
    url = ESPN_BOXSCORE_URL.format(game_id=gid)
    headers = {"User-Agent":"MLB-Picks-Agent/1.0 (+https://yourdomain.example)"}
    r = requests.get(url, headers=headers, timeout=12)
    if r.status_code != 200:
        return {"home": [], "away": []}
    soup = BeautifulSoup(r.text, "lxml")
    # ESPN's markup is complex; try to find elements that look like lineup lists
    lineup = {"home": [], "away": []}
    # Look for 'lineup' or 'starting lineup' headers
    for team_block in soup.select(".mod-container"):
        text = team_block.get_text(separator="\n").lower()
        if "starting lineup" in text:
            # parse player names (simple heuristic)
            lines = team_block.get_text(separator="\n").splitlines()
            names = []
            for line in lines:
                line = line.strip()
                if len(line.split()) >= 2 and any(ch.isalpha() for ch in line):
                    names.append(line)
            # assign based on context if "home" or "away" visible
    # Fallback: no safe parsing -> return empty arrays
    return lineup

def main():
    # read games file
    games_path = os.path.join(OUTDIR, "games_today.json")
    if not os.path.exists(games_path):
        print("No games_today.json, run fetch_scoreboard first")
        return
    with open(games_path) as f:
        games = json.load(f)["games"]
    result = {"date": datetime.now(timezone.utc).isoformat(), "lineups": []}
    for g in games:
        gid = g.get("game_id")
        if not gid:
            result["lineups"].append({"game_id": None, "lineup": {"home": [], "away": []}})
            continue
        try:
            ln = fetch_lineup_game(gid)
        except Exception:
            ln = {"home": [], "away": []}
        result["lineups"].append({"game_id": gid, "lineup": ln})
    outpath = os.path.join(OUTDIR, "lineups_today.json")
    with open(outpath, "w") as f:
        json.dump(result, f, indent=2)
    print("Wrote lineups:", outpath)
    return result

if __name__ == "__main__":
    main()
