"""Open-Meteo weather API client — no API key required."""

import requests
import pandas as pd
import streamlit as st
from datetime import date, timedelta

CITIES = {
    "Geneva": {"lat": 46.2044, "lon": 6.1432, "timezone": "Europe/Zurich"},
    "Doha": {"lat": 25.2854, "lon": 51.5310, "timezone": "Asia/Qatar"},
}

# Monthly seasonal averages as fallback when event dates exceed the 16-day forecast window
SEASONAL_AVERAGES = {
    "Geneva": {
        1:  {"temp_max": 4.2,  "temp_min": -0.8, "precip_prob": 57, "wind_speed": 14},
        2:  {"temp_max": 6.0,  "temp_min":  0.5, "precip_prob": 58, "wind_speed": 15},
        3:  {"temp_max": 10.5, "temp_min":  3.2, "precip_prob": 63, "wind_speed": 16},
        4:  {"temp_max": 15.2, "temp_min":  6.8, "precip_prob": 68, "wind_speed": 15},
        5:  {"temp_max": 19.8, "temp_min": 10.5, "precip_prob": 72, "wind_speed": 14},
        6:  {"temp_max": 23.5, "temp_min": 13.8, "precip_prob": 67, "wind_speed": 13},
        7:  {"temp_max": 26.2, "temp_min": 15.8, "precip_prob": 62, "wind_speed": 12},
        8:  {"temp_max": 25.5, "temp_min": 15.5, "precip_prob": 63, "wind_speed": 12},
        9:  {"temp_max": 20.8, "temp_min": 12.0, "precip_prob": 62, "wind_speed": 13},
        10: {"temp_max": 14.5, "temp_min":  7.2, "precip_prob": 68, "wind_speed": 14},
        11: {"temp_max": 8.2,  "temp_min":  2.0, "precip_prob": 64, "wind_speed": 15},
        12: {"temp_max": 4.5,  "temp_min": -0.5, "precip_prob": 59, "wind_speed": 14},
    },
    "Doha": {
        1:  {"temp_max": 23.2, "temp_min": 14.5, "precip_prob": 14, "wind_speed": 19},
        2:  {"temp_max": 25.0, "temp_min": 15.8, "precip_prob": 13, "wind_speed": 21},
        3:  {"temp_max": 29.5, "temp_min": 19.2, "precip_prob":  9, "wind_speed": 22},
        4:  {"temp_max": 35.2, "temp_min": 23.8, "precip_prob":  4, "wind_speed": 23},
        5:  {"temp_max": 40.5, "temp_min": 28.5, "precip_prob":  2, "wind_speed": 25},
        6:  {"temp_max": 42.0, "temp_min": 31.5, "precip_prob":  0, "wind_speed": 24},
        7:  {"temp_max": 41.5, "temp_min": 32.5, "precip_prob":  0, "wind_speed": 23},
        8:  {"temp_max": 41.0, "temp_min": 32.2, "precip_prob":  0, "wind_speed": 22},
        9:  {"temp_max": 38.2, "temp_min": 29.8, "precip_prob":  0, "wind_speed": 21},
        10: {"temp_max": 33.5, "temp_min": 25.2, "precip_prob":  2, "wind_speed": 19},
        11: {"temp_max": 28.0, "temp_min": 19.8, "precip_prob":  7, "wind_speed": 17},
        12: {"temp_max": 24.0, "temp_min": 15.8, "precip_prob": 11, "wind_speed": 18},
    },
}

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
FORECAST_WINDOW_DAYS = 15


def _seasonal_summary(city: str, month: int) -> dict:
    """Return seasonal average data for a city/month, without a DataFrame."""
    data = SEASONAL_AVERAGES[city][month]
    return {
        "source": "seasonal_average",
        "temp_max": data["temp_max"],
        "temp_min": data["temp_min"],
        "precip_prob": data["precip_prob"],
        "wind_speed": data["wind_speed"],
        "df": None,
        "note": None,
    }


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_weather_forecast(city: str, start_date_str: str, end_date_str: str) -> dict:
    """
    Fetch a 16-day daily weather forecast from Open-Meteo for the given city and date range.
    If the event dates fall outside the forecast window, returns seasonal averages instead.
    """
    city_info = CITIES[city]
    today = date.today()
    start_date = date.fromisoformat(start_date_str)
    forecast_end = today + timedelta(days=FORECAST_WINDOW_DAYS)

    if start_date > forecast_end:
        result = _seasonal_summary(city, start_date.month)
        result["note"] = (
            f"Event dates are beyond the {FORECAST_WINDOW_DAYS + 1}-day forecast window. "
            f"Showing seasonal climate averages for {city} in {start_date.strftime('%B')}."
        )
        return result

    fetch_start = max(today, start_date)
    fetch_end = min(forecast_end, date.fromisoformat(end_date_str))

    params = {
        "latitude": city_info["lat"],
        "longitude": city_info["lon"],
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,wind_speed_10m_max",
        "timezone": city_info["timezone"],
        "start_date": fetch_start.isoformat(),
        "end_date": fetch_end.isoformat(),
    }

    try:
        resp = requests.get(OPEN_METEO_URL, params=params, timeout=10)
        resp.raise_for_status()
        raw = resp.json()

        daily = raw["daily"]
        df = pd.DataFrame({
            "date": pd.to_datetime(daily["time"]),
            "temp_max": daily["temperature_2m_max"],
            "temp_min": daily["temperature_2m_min"],
            "precip_prob": daily.get("precipitation_probability_max"),
            "wind_speed": daily["wind_speed_10m_max"],
        })

        return {
            "source": "live_forecast",
            "temp_max": df["temp_max"].mean(),
            "temp_min": df["temp_min"].mean(),
            "precip_prob": df["precip_prob"].mean() if df["precip_prob"].notna().any() else 0.0,
            "wind_speed": df["wind_speed"].mean(),
            "df": df,
            "note": None,
        }

    except Exception as exc:
        result = _seasonal_summary(city, start_date.month)
        result["note"] = f"Live weather API unavailable — showing seasonal averages. ({exc})"
        return result


def compute_weather_risk(weather_geneva: dict, weather_doha: dict) -> dict:
    """
    Compute a 0–100 weather risk score from both city summaries.

    Heat is the dominant risk for a Doha event; precipitation is factored for Geneva departures.
    """
    doha_temp_max = weather_doha.get("temp_max", 30.0)
    doha_precip = weather_doha.get("precip_prob", 5.0) or 0.0
    geneva_precip = weather_geneva.get("precip_prob", 50.0) or 0.0

    # 30 °C → 0 heat risk; 50 °C → 100 heat risk
    heat_risk = min(100.0, max(0.0, (doha_temp_max - 30.0) * 5.0))
    precip_risk = doha_precip * 0.4 + geneva_precip * 0.6
    score = heat_risk * 0.6 + precip_risk * 0.4

    if score < 20:
        level = "Low"
    elif score < 45:
        level = "Moderate"
    elif score < 70:
        level = "High"
    else:
        level = "Critical"

    return {
        "score": round(score, 1),
        "level": level,
        "heat_risk": round(heat_risk, 1),
        "precip_risk": round(precip_risk, 1),
    }
