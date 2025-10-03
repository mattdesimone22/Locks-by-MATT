# server.py
from flask import Flask, jsonify, request
from flask_cors import CORS
import os, json, subprocess, time

app = Flask(__name__)
CORS(app)
DATA_DIR = "data"

def load_json_or_empty(path):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}

@app.route("/api/scoreboard")
def scoreboard():
    return load_json_or_empty(os.path.join(DATA_DIR, "games_today.json"))

@app.route("/api/lineups")
def lineups():
    return load_json_or_empty(os.path.join(DATA_DIR, "lineups_today.json"))

@app.route("/api/picks_props")
def picks_props():
    return load_json_or_empty(os.path.join(DATA_DIR, "player_props.json"))

@app.route("/api/odds")
def odds():
    return load_json_or_empty(os.path.join(DATA_DIR, "odds_snapshot.json"))

@app.route("/api/generate_picks", methods=["POST","GET"])
def generate_picks():
    # run generation synchronously for now
    try:
        subprocess.check_call(["python", "generate_daily_props.py"])
        return jsonify({"status":"ok", "date": time.strftime("%Y-%m-%d")})
    except subprocess.CalledProcessError as e:
        return jsonify({"status":"error", "error": str(e)}), 500

if __name__ == "__main__":
    # create data dir
    os.makedirs(DATA_DIR, exist_ok=True)
    app.run(host="0.0.0.0", port=5000)
