# player_prop_predictor.py
import math, random
from analytics_utils import logistic

def predict_player_total_bases(player_stats, pitcher_stats, park_factor=1.0):
    """
    Very simple model: base rate (player wOBA -> TB expectation) * pitcher effect * park
    Replace with a trained model for better accuracy.
    """
    # placeholders
    base_rate = player_stats.get("xwOBA", 0.300)  # normalized
    power = player_stats.get("barrel%", 0.03)
    pitcher_damp = 1.0 - ((pitcher_stats.get("CSW%", 0.25) - 0.25) * 0.5)  # heuristic
    expected_tb = base_rate * (1 + power * 5) * pitcher_damp * park_factor * 4.0  # scale -> total bases
    # variance
    sigma = max(0.5, expected_tb * 0.2)
    return {"expected_tb": expected_tb, "std": sigma, "prob_over_1.5": logistic((expected_tb - 1.5)/sigma)}

def predict_player_k_props(player_stats, pitcher_stats):
    # placeholder predictive logic for strikeouts
    k_rate = player_stats.get("K%", 0.2)
    pitcher_k = pitcher_stats.get("K9", 8.5)
    # expected strikeouts in game:
    expected_k = pitcher_k / 9.0 * 6.0  # per outing assumption
    # map to probability of over/under 0.5/1.5 etc
    return {"exp_k": expected_k, "prob_over_0.5": logistic((expected_k-0.5)/1.0)}
