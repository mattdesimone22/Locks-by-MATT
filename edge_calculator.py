# edge_calculator.py
import math
from analytics_utils import logistic, clamp

def compute_edge_for_game(home_team_metrics, away_team_metrics, home_pitcher, away_pitcher, market_odds_delta=0.0):
    """
    Combine metrics into a single signed edge favoring home team (>0).
    All inputs are dictionaries with keys like xFIP, wRC+, CSW, bullpen_xFIP, park_factor etc.
    """
    # Example weightings - tune with backtest
    weights = {
        "pitching_delta": 0.35,
        "hitting_delta": 0.25,
        "bullpen_delta": 0.15,
        "park_factor_delta": 0.05,
        "rest_delta": 0.05,
        "market_delta": 0.15
    }

    # Compute normalized deltas (higher is better for home team)
    pitching_delta = (away_pitcher.get("xFIP", 4.0) - home_pitcher.get("xFIP", 4.0))  # lower xFIP better -> invert
    hitting_delta = (home_team_metrics.get("wRC+", 100) - away_team_metrics.get("wRC+", 100)) / 100.0
    bullpen_delta = (away_team_metrics.get("bullpen_xFIP", 4.0) - home_team_metrics.get("bullpen_xFIP", 4.0))
    park_delta = home_team_metrics.get("park_factor", 1.0) - away_team_metrics.get("park_factor", 1.0)
    rest_delta = home_team_metrics.get("rest_days", 0) - away_team_metrics.get("rest_days", 0)
    market_delta = market_odds_delta

    score = 0.0
    score += weights["pitching_delta"] * pitching_delta
    score += weights["hitting_delta"] * hitting_delta
    score += weights["bullpen_delta"] * bullpen_delta
    score += weights["park_factor_delta"] * park_delta
    score += weights["rest_delta"] * rest_delta
    score += weights["market_delta"] * market_delta

    # map score to probability via logistic; scale factor chosen for calibration
    prob_home = logistic(score, k=2.5)
    # convert to edge (prob_home - implied_market)
    return clamp(prob_home, 0.01, 0.99)
