"""Exchange rate client using open.er-api.com — no API key required."""

import requests
import streamlit as st

BASE_URL = "https://open.er-api.com/v6/latest"

# Approximate fallback rates (CHF base) used when the API is unavailable
FALLBACK_RATES = {
    "USD": 1.13,
    "EUR": 1.03,
    "QAR": 4.12,
    "GBP": 0.89,
    "AED": 4.15,
    "JPY": 167.0,
    "SGD": 1.52,
    "AUD": 1.74,
    "CHF": 1.00,
}


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_currency_rates(base: str = "CHF") -> dict:
    """
    Fetch live exchange rates from open.er-api.com with CHF as the base currency.
    Falls back to hardcoded approximate rates on any API failure.
    """
    try:
        resp = requests.get(f"{BASE_URL}/{base}", timeout=10)
        resp.raise_for_status()
        data = resp.json()

        if data.get("result") != "success":
            raise ValueError(f"API returned: {data.get('result')}")

        return {
            "base": base,
            "rates": data["rates"],
            "last_updated": data.get("time_last_update_utc", "Unknown"),
            "error": None,
        }

    except Exception as exc:
        return {
            "base": base,
            "rates": FALLBACK_RATES,
            "last_updated": "Unavailable — using fallback rates",
            "error": str(exc),
        }
