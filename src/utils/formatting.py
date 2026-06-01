"""Formatting helpers for the Luxury Event Intelligence Dashboard."""

CURRENCY_SYMBOLS: dict[str, str] = {
    "CHF": "CHF ",
    "USD": "$",
    "EUR": "€",
    "QAR": "QAR ",
    "GBP": "£",
    "AED": "AED ",
}

RISK_COLORS: dict[str, str] = {
    "Low":      "#68d391",
    "Moderate": "#fbd38d",
    "High":     "#fc8181",
    "Critical": "#e53e3e",
}

RISK_EMOJIS: dict[str, str] = {
    "Low":      "✅",
    "Moderate": "⚠️",
    "High":     "🔴",
    "Critical": "🚨",
}


def format_currency(amount: float, currency: str) -> str:
    """Return a compact, human-readable currency string."""
    symbol = CURRENCY_SYMBOLS.get(currency, f"{currency} ")
    if amount >= 1_000_000:
        return f"{symbol}{amount / 1_000_000:.2f}M"
    if amount >= 1_000:
        return f"{symbol}{amount:,.0f}"
    return f"{symbol}{amount:.2f}"


def risk_color(category: str) -> str:
    """Return a hex colour for the given risk category."""
    return RISK_COLORS.get(category, "#ffffff")


def risk_emoji(category: str) -> str:
    """Return an emoji for the given risk category."""
    return RISK_EMOJIS.get(category, "❓")


def format_hours(hours: float) -> str:
    """Format a duration expressed in fractional hours as 'Xh Ym'."""
    h = int(hours)
    m = int(round((hours - h) * 60))
    return f"{h}h {m}m" if m else f"{h}h"


def source_label(source: str) -> str:
    """Return a short display label for a data source type."""
    return "Live forecast" if source == "live_forecast" else "Seasonal averages"
