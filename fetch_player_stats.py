# fetch_player_stats.py
import os, json, time, requests, pandas as pd
from retrying import retry
from datetime import datetime, timezone
from urllib.parse import urlencode

OUTDIR = "data"
CACHE = "data/cache"
os.makedirs(OUTDIR, exist_ok=True)
os.makedirs(CACHE, exist_ok=True)

# Baseball Savant leaderboard CSV base - we will call the custom leaderboard csv pattern.
# NOTE: Baseball Savant's query parameters are detailed; below is a robust attempt to use the 'leaderboard' csv export.
SAVANT_LEADERBOARD_CSV = "https://baseballsavant.mlb.com/leaderboard/custom?{}"

@retry(stop_max_attempt_number=3, wait_fixed=900)
def fetch_savant_leaderboard_csv(params):
    url = SAVANT_LEADERBOARD_CSV.format(urlencode(params))
    r = requests.get(url, timeout=25)
    r.raise_for_status()
    return r.text

def parse_csv_to_df(csv_text):
    from io import StringIO
    try:
        df = pd.read_csv(StringIO(csv_text))
        return df
    except Exception:
        return pd.DataFrame()

def build_hitter_cache(season=2025):
    # Params below are a template. Depending on Savant's exact query param names, tweak as needed.
    params = {
        "type": "batter",
        "season": season,
        "page": "1",
        "csv": "1",  # attempt to ask for CSV
    }
    try:
        csv_text = fetch_savant_leaderboard_csv(params)
        df = parse_csv_to_df(csv_text)
    except Exception as e:
        print("Savant hitter fetch failed:", e)
        df = pd.DataFrame()

    mapping = {}
    if not df.empty:
        # Try to pick standard columns, fallback if not
        for _, row in df.iterrows():
            name = row.get("player_name") or row.get("Player") or row.get("Name")
            if not name: continue
            mapping[name] = {
                "xwOBA": row.get("xwOBA", None),
                "Barrel%": row.get("barrel_percent") or row.get("Barrel%"),
                "HardHit%": row.get("HardHit%") or row.get("hard_hit_percent"),
                "xBA": row.get("xBA", None),
                "xSLG": row.get("xSLG", None),
                "ISO": row.get("ISO", None),
                "BABIP": row.get("BABIP", None),
                "PA": row.get("PA", None)
            }
    # write cache
    path = os.path.join(CACHE, f"hitter_stats_{season}.json")
    with open(path, "w") as f:
        json.dump(mapping, f, indent=2)
    print("Wrote hitter cache:", path)
    return mapping

def build_pitcher_cache(season=2025):
    params = {"type": "pitcher", "season": season, "csv": "1"}
    try:
        csv_text = fetch_savant_leaderboard_csv(params)
        df = parse_csv_to_df(csv_text)
    except Exception as e:
        print("Savant pitcher fetch failed:", e)
        df = pd.DataFrame()

    mapping = {}
    if not df.empty:
        for _, row in df.iterrows():
            name = row.get("player_name") or row.get("Player")
            if not name: continue
            mapping[name] = {
                "xFIP": row.get("xFIP"),
                "SIERA": row.get("SIERA"),
                "CSW": row.get("CSW%") or row.get("CSW"),
                "SwStr%": row.get("SwStr%") or row.get("SwStr"),
                "K9": row.get("K/9") or row.get("K9"),
                "BB9": row.get("BB/9") or row.get("BB9"),
                "HR/FB": row.get("HR/FB") or row.get("HR/FB%")
            }
    path = os.path.join(CACHE, f"pitcher_stats_{season}.json")
    with open(path, "w") as f:
        json.dump(mapping, f, indent=2)
    print("Wrote pitcher cache:", path)
    return mapping

def main():
    build_hitter_cache()
    build_pitcher_cache()

if __name__ == "__main__":
    main()
