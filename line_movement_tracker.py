# line_movement_tracker.py
import os, json, logging, time
from dotenv import load_dotenv
import requests

load_dotenv()
logger = logging.getLogger("line_movement_tracker")
logger.setLevel(logging.INFO)

# Example: odds providers (placeholder)
ODDS_API_URL = "https://api.the-odds-api.com/v4/sports/baseball_mlb/odds"

def fetch_odds(api_key, regions="us", markets="moneyline"):
    params = {"apiKey": api_key, "regions": regions, "markets": markets}
    r = requests.get(ODDS_API_URL, params=params, timeout=15)
    r.raise_for_status()
    return r.json()

def snapshot_odds(out_path="data/odds_snapshot.json"):
    api_key = os.getenv("ODDS_API_KEY")
    if not api_key:
        logger.warning("No ODDS_API_KEY set; skipping odds fetch.")
        return None
    data = fetch_odds(api_key)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(data, f, indent=2)
    return out_path

if __name__ == "__main__":
    snapshot_odds()
