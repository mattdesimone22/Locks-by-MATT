# odds_aggregator.py
import os, json, time, requests
from retrying import retry
from dotenv import load_dotenv

load_dotenv()
OUTDIR = "data"
os.makedirs(OUTDIR, exist_ok=True)

ODDS_PROVIDER = os.getenv("ODDS_API_PROVIDER", "the_odds_api")
ODDS_KEY = os.getenv("ODDS_API_KEY")
THE_ODDS_BASE = "https://api.the-odds-api.com/v4"

@retry(stop_max_attempt_number=3, wait_fixed=1000)
def fetch_odds_the_odds_api(sport_key="baseball_mlb", regions="us", markets="playerprops"):
    url = f"{THE_ODDS_BASE}/sports/{sport_key}/odds"
    params = {"apiKey": ODDS_KEY, "regions": regions, "markets": markets, "oddsFormat": "american"}
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    return r.json()

def collect_player_props():
    results = []
    if ODDS_PROVIDER == "the_odds_api" and ODDS_KEY:
        try:
            data = fetch_odds_the_odds_api()
            for game in data:
                # bookmakers -> markets -> outcomes
                for book in game.get("bookmakers", []):
                    title = book.get("title")
                    for market in book.get("markets", []):
                        if "playerprops" in (market.get("key") or "") or market.get("key","").startswith("player"):
                            for outcome in market.get("outcomes", []):
                                results.append({
                                    "game": game.get("home_team", "") + " vs " + game.get("away_team", ""),
                                    "site": title,
                                    "market_key": market.get("key"),
                                    "label": outcome.get("name"),
                                    "price": outcome.get("price"),
                                    "raw": outcome
                                })
        except Exception as e:
            print("Odds fetch error:", e)
    # Save snapshot
    outpath = os.path.join(OUTDIR, "odds_snapshot.json")
    with open(outpath, "w") as f:
        json.dump({"generated_at": time.time(), "props": results}, f, indent=2)
    print("Saved odds snapshot:", outpath)
    return results

if __name__ == "__main__":
    collect_player_props()
