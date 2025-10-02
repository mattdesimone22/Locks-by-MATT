# analytics_utils.py
import math
import numpy as np
import logging
from datetime import datetime
from retrying import retry
from ratelimit import limits, sleep_and_retry

logger = logging.getLogger("analytics_utils")
logger.setLevel(logging.INFO)

SECONDS_PER_MINUTE = 60

def zscore(series):
    s = np.array(series, dtype=float)
    mu = np.nanmean(s)
    sigma = np.nanstd(s, ddof=0)
    if sigma == 0:
        return np.zeros_like(s)
    return (s - mu) / sigma

def clamp(x, a=-1.0, b=1.0):
    return max(a, min(b, x))

def logistic(x, k=1.0):
    return 1.0 / (1.0 + math.exp(-k * x))

def safeget(d, *keys, default=None):
    cur = d
    try:
        for k in keys:
            cur = cur[k]
        return cur
    except Exception:
        return default
