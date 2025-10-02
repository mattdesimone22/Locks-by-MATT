# weather_and_park_adjustments.py
import requests, logging, math
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("weather_and_park_adjustments")
logger.setLevel(logging.INFO)

OPENWEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"
# Park factors should be a curated dataset you maintain locally.
PARK_FACTORS = {
    # example: "Yankee Stadium": {"runs_multiplier": 1.05, "HR_multiplier": 1.10}
}

def get_weather(city, api_key):
    params = {"q": city, "appid": api_key, "units": "metric"}
    r = requests.get(OPENWEATHER_URL, params=params, timeout=10)
    r.raise_for_status()
    return r.json()

def park_adjustment(park_name):
    return PARK_FACTORS.get(park_name, {"runs_multiplier": 1.0, "HR_multiplier": 1.0})

def compute_weather_park_factor(weather_json, park_name):
    """
    Example: combine wind, temp, and park factors to adjust run expectation.
    Returns a multiplier >0
    """
    wf = weather_json
    temp = wf.get("main", {}).get("temp", 15)
    wind_m_s = abs(wf.get("wind", {}).get("speed", 0))
    # heuristic: higher temp and stronger outfield wind favor runs/hr
    temp_factor = 1.0 + (max(0, temp - 15) * 0.005)
    wind_factor = 1.0 + (wind_m_s * 0.01)  # tweak or invert depending on direction
    park = park_adjustment(park_name)
    combined = temp_factor * wind_factor * park['runs_multiplier']
    logger.debug("Weather/park combined factor=%s", combined)
    return combined
