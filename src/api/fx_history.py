"""
Historical FX data from Frankfurter (ECB rates) — no API key required.

QAR note: the Qatari Riyal has been pegged to USD at 3.64 since 2001.
CHF/USD 30-day volatility is therefore the correct proxy for CHF/QAR budget exposure.
"""

import requests
import pandas as pd
import streamlit as st
from datetime import date, timedelta

FRANKFURTER_BASE = "https://api.frankfurter.app"


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_fx_history(days: int = 30) -> dict:
    """
    Fetch the last `days` days of ECB daily rates for CHF -> USD, EUR, GBP.
    Computes trend (% change) and volatility (coefficient of variation) per pair.
    Returns a structured dict with a tidy DataFrame and per-currency stats.
    """
    end_date = date.today()
    start_date = end_date - timedelta(days=days)

    try:
        resp = requests.get(
            f"{FRANKFURTER_BASE}/{start_date.isoformat()}..{end_date.isoformat()}",
            params={"from": "CHF", "to": "USD,EUR,GBP"},
            timeout=10,
        )
        resp.raise_for_status()
        raw = resp.json()

        df = pd.DataFrame(raw["rates"]).T
        df.index = pd.to_datetime(df.index)
        df = df.sort_index()

        stats: dict[str, dict] = {}
        for currency in ["USD", "EUR", "GBP"]:
            if currency not in df.columns:
                continue
            series = df[currency].dropna()
            if len(series) < 2:
                continue
            stats[currency] = {
                "current":        round(float(series.iloc[-1]), 4),
                "trend_pct":      round((float(series.iloc[-1]) - float(series.iloc[0])) / float(series.iloc[0]) * 100, 2),
                "volatility_pct": round(float(series.std()) / float(series.mean()) * 100, 3),
                "min":            round(float(series.min()), 4),
                "max":            round(float(series.max()), 4),
                "series":         series,
            }

        return {
            "source":       "Frankfurter / ECB",
            "period_days":  days,
            "start_date":   start_date.isoformat(),
            "end_date":     end_date.isoformat(),
            "currencies":   stats,
            "df":           df,
            "error":        None,
        }

    except Exception as exc:
        return {
            "source":     "Frankfurter / ECB",
            "period_days": days,
            "currencies": {},
            "df":         None,
            "error":      str(exc),
        }


def fx_risk_label(volatility_pct: float) -> tuple[str, str]:
    """Map CHF/USD coefficient-of-variation to a risk label and colour."""
    if volatility_pct < 0.5:
        return "Low", "#68d391"
    if volatility_pct < 1.5:
        return "Moderate", "#fbd38d"
    return "High", "#fc8181"
