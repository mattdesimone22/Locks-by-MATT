import requests, json
from datetime import datetime
import numpy as np

# -------------------------------
# 1. Fetch MLB scoreboard (ESPN)
# -------------------------------
url = "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard"
resp = requests.get(url).json()

games_list = []

for event in resp.get('events', []):
    try:
        comp = event['competitions'][0]
        home = comp['competitors'][0]['team']
        away = comp['competitors'][1]['team']
        home_pitcher = comp['competitors'][0].get('probablePitcher', {}).get('fullName', 'TBD')
        away_pitcher = comp['competitors'][1].get('probablePitcher', {}).get('fullName', 'TBD')

        # -------------------------------
        # 2. Generate dummy advanced stats (replace with real API later)
        # -------------------------------
        home_xFIP = round(np.random.uniform(3.0, 3.8),2)
        away_xFIP = round(np.random.uniform(3.2, 4.0),2)
        home_wRC = np.random.randint(100,120)
        away_wRC = np.random.randint(95,115)
        edge = round(np.random.uniform(0.08, 0.20),2)

        games_list.append({
            "matchup": f"{away['shortDisplayName']} vs {home['shortDisplayName']}",
            "pick": f"{home['shortDisplayName']} ML",
            "edge": edge,
            "reason": "Advanced metrics suggest home team advantage (xFIP, wRC+, CSW%)",
            "team_stats": f"{home['shortDisplayName']} xFIP {home_xFIP} | {away['shortDisplayName']} xFIP {away_xFIP} | {home['shortDisplayName']} wRC+ {home_wRC} | {away['shortDisplayName']} wRC+ {away_wRC}",
            "player_stats": "Top players xwOBA, Hard-Hit%, Barrel% (placeholder)",
            "odds": f"{home['shortDisplayName']} ML -135 | {away['shortDisplayName']} ML +115",
            "pitcher_matchup": f"{away_pitcher} ({away['shortDisplayName']}) vs {home_pitcher} ({home['shortDisplayName']})"
        })
    except:
        continue

# -------------------------------
# 3. Save today's picks
# -------------------------------
today = datetime.today().strftime('%Y-%m-%d')
picks = {"date": today, "games": games_list}

with open("picks_today.json", "w") as f:
    json.dump(picks, f, indent=2)

print(f"MLB picks generated for {today}!")
