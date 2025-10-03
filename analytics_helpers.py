# analytics_helpers.py
import math, numpy as np

def logistic(x, k=1.0):
    try:
        return 1.0 / (1.0 + math.exp(-k * x))
    except OverflowError:
        return 0.0 if x < 0 else 1.0

def zscore(series):
    a = np.array(series, dtype=float)
    mu = np.nanmean(a)
    sd = np.nanstd(a)
    if sd == 0:
        return np.zeros_like(a).tolist()
    return ((a - mu) / sd).tolist()

def clamp(x, a=0.0, b=1.0):
    try:
        if x is None:
            return a
        return max(a, min(b, x))
    except Exception:
        return a
