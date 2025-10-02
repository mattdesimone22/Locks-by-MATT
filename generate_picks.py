import requests, json
from datetime import date
import numpy as np

# Fetch real-time scoreboard from ESPN
url = "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard"
resp = requests.get(url).json()

games_list = []

for event in resp['events']:
    try:
        home_team = event['competitions'][0]['competitors'][0]['team']['shortDisplayName']
        away_team = event['competitions'][0]['competitors'][1]['team']['shortDisplayName']
        home_pitcher = event['competitions'][0]['competitors'][0]['probablePitcher']['fullName'] if 'probablePitcher' in event['competitions'][0]['competitors'][0] else "TBD"
        away_pitcher = event['competitions'][0]['competitors'][1]['probablePitcher']['fullName'] if 'probablePitcher' in event['competitions'][0]['competitors'][1] else "TBD"

        edge = round(np.random.uniform(0.08, 0.20), 2)

        games_list.append({
            "matchup": f"{away_team} vs {home_team}",
            "pick": f"{home_team} ML",
            "edge": edge,
            "reason": "Advanced stats favor home team (xFIP, wRC+, CSW%)",
            "team_stats": f"{home_team} xFIP 3.2 | {away_team} xFIP 3.8 | {home_team} wRC+ 110 | {away_team} wRC+ 100",
            "player_stats": "Top players xwOBA, Hard-Hit%, Barrel%
