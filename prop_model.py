# prop_model.py
import math
from analytics_helpers import clamp, logistic

# Calibrated baseline rates (these are heuristics — tune with a backtest)
BASE_HR_RATE = 0.035   # typical per-player single-game HR expectation baseline
BASE_HITS_PER_PA = 0.22  # approximate hits per plate appearance baseline

def hr_probability(batter, pitcher, park_factor=1.0):
    # Batter features
    barrel = batter.get("Barrel%", 0.03) or 0.03
    xwoba = batter.get("xwOBA", 0.320) or 0.320
    pa = batter.get("PA", 4.0) or 4.0
    # Pitcher features
    xfip = pitcher.get("xFIP", 4.0) or 4.0
    hrfb = pitcher.get("HR/FB", 0.10) or 0.10
    csw = pitcher.get("CSW", 0.26) or pitcher.get("CSW%", 0.26) or 0.26
    # Combine: power_factor and pitcher suppression
    power_score = (barrel * 20.0) + ((xwoba - 0.32) * 2.5)
    pitcher_suppress = 1.0 + ((xfip - 4.0) * 0.08) + (hrfb - 0.10)
    base = BASE_HR_RATE * (1 + power_score) / pitcher_suppress * park_factor
    base = clamp(base, 0.002, 0.8)
    prob = 1 - math.exp(-base)  # Poisson style mapping
    # confidence grows with sample size (PA) and barrel frequency
    conf = clamp(0.25 + min(pa/600, 0.5) + (barrel * 3.0), 0.05, 0.98)
    return {"prob": prob, "confidence": conf, "expected_rate": base}

def total_bases_projection(batter, pitcher, park_factor=1.0):
    pa = batter.get("PA", 4.0)
    # map xwOBA to TB per PA via approximate linear calibration
    xwoba = batter.get("xwOBA", 0.32)
    tb_per_pa = (xwoba - 0.18) * 1.8  # calibration
    pitcher_k = pitcher.get("CSW", 0.26)
    pitcher_factor = 1.0 - (pitcher_k - 0.26) * 0.7
    expected_tb = pa * tb_per_pa * pitcher_factor * park_factor
    std = max(0.5, expected_tb * 0.35)
    # probability over 1.5 TB (normal approx)
    z = (expected_tb - 1.5) / std
    import math
    prob_over_1_5 = 0.5 * (1 + math.erf(z / math.sqrt(2)))
    return {"expected_tb": expected_tb, "std": std, "prob_over_1_5": prob_over_1_5}

def hits_projection(batter, pitcher, park_factor=1.0):
    pa = batter.get("PA", 4.0)
    xba = batter.get("xBA", batter.get("xwOBA", 0.24))
    expected_hits = pa * xba * park_factor
    import math
    prob_1plus = 1 - math.exp(-expected_hits)
    conf = clamp(0.25 + (pa/600)*0.4, 0.05, 0.95)
    return {"expected_hits": expected_hits, "prob_1plus": prob_1plus, "confidence": conf}

def walk_probability(batter, pitcher):
    bb = batter.get("BB%", 0.08)
    pb = pitcher.get("BB9", 3.0)
    prob = clamp(bb * (1 + (pb-3.0)*0.05), 0.01, 0.45)
    conf = clamp(0.2 + (batter.get("PA",4)/600)*0.4, 0.05, 0.95)
    return {"prob": prob, "confidence": conf}

def batter_strikeouts_projection(batter, pitcher):
    # Model batter K probability per PA using K% or league average mapping
    k_pct = batter.get("K%", 0.22)
    pa = batter.get("PA", 4.0)
    pitcher_k = pitcher.get("K9", pitcher.get("K/9", 8.5))
    pitcher_factor = 1.0 + ((pitcher_k - 8.5) * 0.05)
    exp_ks = pa * k_pct * pitcher_factor
    # probability over 1.5 strikeouts approx using Poisson
    import math
    prob_over_1_5 = 1 - (math.exp(-exp_ks) * (1 + exp_ks))
    conf = clamp(0.2 + (batter.get("PA",4)/600)*0.35, 0.05, 0.95)
    return {"exp_k": exp_ks, "prob_over_1_5": prob_over_1_5, "confidence": conf}

def pitcher_k_projection(pitcher, est_innings=5.5):
    k9 = pitcher.get("K9", pitcher.get("K/9", 8.5))
    exp_k = (k9 / 9.0) * est_innings
    import math
    std = max(1.0, exp_k * 0.4)
    z = (exp_k - 7.5) / std
    prob_over_7_5 = 0.5 * (1 + math.erf(z/math.sqrt(2)))
    conf = clamp(0.25 + (pitcher.get("sample_stability", 0.6) * 0.3), 0.05, 0.98)
    return {"exp_k": exp_k, "prob_over_7_5": prob_over_7_5, "confidence": conf}
