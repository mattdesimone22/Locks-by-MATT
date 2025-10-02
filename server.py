# server.py
from flask import Flask, jsonify, request
from flask_cors import CORS
import os, requests, json, time
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)
CORS(app)  # allow local dev; in production lock to your domain

ESPN_SB = "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard"
ODDS_BASE = "https://api.the-odds-api.com/v4"  # example, requires key

ODDS_KEY = os.getenv("ODDS_API_KEY")
WEATHER_KEY = os.getenv("WEATHER_API_KEY")
# Add other keys as needed

@app.route("/api/scoreboard")
def scoreboard():
    r = requests.get(ESPN_SB, timeout=15)
    return jsonify(r.json())

@app.route("/api/odds")
def odds():
    if not ODDS_KEY:
        return jsonify([])
    # example endpoint: odds for sport key 'baseball_mlb'
    url = f"{ODDS_BASE}/sports/baseball_mlb/odds"
    params = {"apiKey": ODDS_KEY, "regions":"us", "markets":"moneyline,totals", "oddsFormat":"american"}
    r = requests.get(url, params=params, timeout=15)
    return jsonify(r.json())

# lightweight pitcher stats fetch (from ESPN/MLB endpoints or cached)
@app.route("/api/pitcher_stats")
def pitcher_stats():
    name = request.args.get("name")
    # Ideally map name -> playerId -> call Baseball Savant or Fangraphs
    return jsonify({"name":name,"xFIP":3.5,"CSW%":0.28,"K9":8.5,"BB9":2.8,"HRFB":0.10})

@app.route("/api/player_stats")
def player_stats():
    name = request.args.get("name")
    return jsonify({"name":name,"xwOBA":0.340,"Barrel%":0.06,"HardHit%":0.40,"BABIP":0.29,"K%":0.20})

@app.route("/api/team_stats")
def team_stats():
    # build a minimal structure of team matchups with pitchers and stats
    # For production: join ESPN scoreboard with Savant/FanGraphs stats
    r = requests.get(ESPN_SB, timeout=15).json()
    games = []
    for ev in r.get("events",[]):
        comp = ev["competitions"][0]
        home = comp["competitors"][0]["team"]
        away = comp["competitors"][1]["team"]
        homePitch = comp["competitors"][0].get("probablePitcher",{}).get("fullName")
        awayPitch = comp["competitors"][1].get("probablePitcher",{}).get("fullName")
        games.append({
          "shortMatch": f"{away['shortDisplayName']} @ {home['shortDisplayName']}",
          "home": {"id":home["id"], "shortName":home["shortDisplayName"], "wRC_plus":105},
          "away": {"id":away["id"], "shortName":away["shortDisplayName"], "wRC_plus":100},
          "homePitcher": {"name":homePitch, "xFIP":3.5},
          "awayPitcher": {"name":awayPitch, "xFIP":3.8},
          "odds": None,
          "reason": ""
        })
    return jsonify({"games":games})

@app.route("/api/picks_props", methods=["GET"])
def picks_props():
    # Compose picks + props by calling team_stats, player_stats, pitcher_stats
    ts = app.test_client().get("/api/team_stats").json
    picks = []
    for g in ts['games']:
        # compute simple probabilities
        home = g['home']; away = g['away']; hp = g['homePitcher']; ap = g['awayPitcher']
        prob_home = 0.55 if (hp.get("xFIP",3.5) <= ap.get("xFIP",4.0)) else 0.48
        pick = home['shortName'] + " ML" if prob_home>0.5 else away['shortName'] + " ML"
        # find top batters (placeholder)
        props = [
            {"player":"Top Batter 1", "team":home["shortName"], "prop_name":"Total Bases O/U 1.5", "line":1.5, "model_ev":0.62, "confidence":0.7,
             "justification":"High xwOBA vs today's opposing pitcher's breaking stuff and park favorability."}
        ]
        picks.append({
          "matchup":g["shortMatch"],
          "pick":pick,
          "edge": round(abs(prob_home-0.5),3),
          "probability": round(prob_home,3),
          "reason":"Model combining xFIP/CSW/wRC+",
          "player_props": props,
          "pitcher_matchup": f"{ap['name']} vs {hp['name']}"
        })
    # flatten props for frontend
    props_flat = []
    for p in picks:
      for pr in p['player_props']:
        props_flat.append(pr)
    return jsonify({"picks":picks,"props":props_flat,"date":time.strftime("%Y-%m-%d")})

@app.route("/api/generate_picks", methods=["POST"])
def generate_picks():
  # In production run the whole pipeline, compute edges & write to disk
  # Here we simply return the picks_props endpoint result
  res = picks_props()
  return res

if __name__ == "__main__":
  app.run(host="0.0.0.0",port=5000,debug=True)
