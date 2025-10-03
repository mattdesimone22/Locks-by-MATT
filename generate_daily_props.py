# generate_daily_props.py
import os, json, time
from datetime import datetime, timezone
from fetch_scoreboard import fetch_scoreboard, extract_games, write_games_file
from fetch_lineups import main as fetch_lineups_main
from fetch_player_stats import build_hitter_cache, build_pitcher_cache
from odds_aggregator import collect_player_props
from prop_model import hr_probability, total_bases_projection, hits_projection, walk_probability, batter_strikeouts_projection, pitcher_k_projection
from analytics_helpers import clamp
from retrying import retry

OUTDIR = "data"
CACHE = "data/cache"
os.makedirs(OUTDIR, exist_ok=True)
os.makedirs(CACHE, exist_ok=True)

def load_caches():
    hitters = {}
    pitchers = {}
    try:
        with open(os.path.join(CACHE, "hitter_stats_2025.json")) as f:
            hitters = json.load(f)
    except Exception:
        pass
    try:
        with open(os.path.join(CACHE, "pitcher_stats_2025.json")) as f:
            pitchers = json.load(f)
    except Exception:
        pass
    return hitters, pitchers

def find_market_for_player(player_name, market_snapshot):
    # naive substring match; return best match or None
    if not market_snapshot:
        return None
    pname = player_name.lower()
    best = None
    for m in market_snapshot:
        label = str(m.get("label","")).lower()
        raw = str(m.get("raw","")).lower()
        if pname in label or pname in raw:
            best = m
            break
    return best

def american_to_prob(odds):
    # odds like -150 or +130 or 'EVEN'
    try:
        o = float(odds)
    except Exception:
        s = str(odds).upper()
        if s in ["EVEN", "PUSH"]:
            return 0.5
        return None
    if o > 0:
        return 100.0 / (o + 100.0)
    else:
        return -o / (-o + 100.0)

@retry(stop_max_attempt_number=2, wait_fixed=1000)
def generate():
    # 1) scoreboard
    sb_json = fetch_scoreboard()
    games = extract_games(sb_json)
    write_games_file(games)

    # 2) lineups + caches
    fetch_lineups_main()  # best-effort
    hitters, pitchers = load_caches()
    # If caches empty, build them (attempt)
    if not hitters:
        hitters = build_hitter_cache()
    if not pitchers:
        pitchers = build_pitcher_cache()

    # 3) odds snapshot
    market_props = collect_player_props()

    # 4) build props for players in today's games
    player_props = []
    for g in games:
        home = g.get("home", {})
        away = g.get("away", {})
        home_pitcher_name = home.get("probable_pitcher")
        away_pitcher_name = away.get("probable_pitcher")
        home_pitcher = pitchers.get(home_pitcher_name, {"name": home_pitcher_name})
        away_pitcher = pitchers.get(away_pitcher_name, {"name": away_pitcher_name})

        # use lineups if present
        lineup_file = os.path.join(OUTDIR, "lineups_today.json")
        if os.path.exists(lineup_file):
            with open(lineup_file) as f:
                lineup_json = json.load(f)
            match = next((x for x in lineup_json.get("lineups", []) if x.get("game_id") == g.get("game_id")), None)
            away_list = match['lineup'].get('away', []) if match and 'lineup' in match else []
            home_list = match['lineup'].get('home', []) if match and 'lineup' in match else []
        else:
            away_list = []
            home_list = []
        # fallback heuristics: use top batters from hitters cache if lineup unknown
        if not away_list:
            away_list = list(hitters.keys())[:6]
        if not home_list:
            home_list = list(hitters.keys())[:6]

        # compute props for away batters vs home pitcher
        for pname in away_list:
            batter_stats = hitters.get(pname, {})
            batter = {"name": pname, "team": away.get("abbr"), **batter_stats}
            p = {}
            p["hr"] = hr_probability(batter, home_pitcher, park_factor=1.0)
            p["tb"] = total_bases_projection(batter, home_pitcher, park_factor=1.0)
            p["hits"] = hits_projection(batter, home_pitcher, park_factor=1.0)
            p["walk"] = walk_probability(batter, home_pitcher)
            p["ks"] = batter_strikeouts_projection(batter, home_pitcher)
            market = find_market_for_player(pname, market_props)
            player_props.append({"player": pname, "team": away.get("abbr"), "opponent_pitcher": home_pitcher_name, "model": p, "market": market})

        # compute props for home batters vs away pitcher
        for pname in home_list:
            batter_stats = hitters.get(pname, {})
            batter = {"name": pname, "team": home.get("abbr"), **batter_stats}
            p = {}
            p["hr"] = hr_probability(batter, away_pitcher, park_factor=1.0)
            p["tb"] = total_bases_projection(batter, away_pitcher, park_factor=1.0)
            p["hits"] = hits_projection(batter, away_pitcher, park_factor=1.0)
            p["walk"] = walk_probability(batter, away_pitcher)
            p["ks"] = batter_strikeouts_projection(batter, away_pitcher)
            market = find_market_for_player(pname, market_props)
            player_props.append({"player": pname, "team": home.get("abbr"), "opponent_pitcher": away_pitcher_name, "model": p, "market": market})

    # 5) compare model to market (if market exists, attempt to parse implied)
    for p in player_props:
        market = p.get('market')
        if market and isinstance(market, dict):
            # if market raw has price fields for O/U labels, we can attempt to parse
            # this part is provider-specific — keep it generic: store market snapshot
            p['market_snapshot'] = market
            # if a simple odds field exists, we could convert to implied probability here
        else:
            p['market_snapshot'] = None

    # 6) save to file
    player_props_path = os.path.join(OUTDIR, "player_props.json")
    with open(player_props_path, "w") as f:
        json.dump({"generated_at": datetime.now(timezone.utc).isoformat(), "props": player_props}, f, indent=2)
    print("Wrote", player_props_path)

    # 7) quick picks (simple team picks from team_stats if available) — keep empty for now; frontend will use model props to derive picks
    picks_path = os.path.join(OUTDIR, "picks_today.json")
    picks = {"date": datetime.now(timezone.utc).isoformat(), "games": []}
    with open(picks_path, "w") as f:
        json.dump(picks, f, indent=2)
    print("Wrote", picks_path)
    return player_props_path

if __name__ == "__main__":
    generate()
