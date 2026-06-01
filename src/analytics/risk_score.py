"""
Event risk scoring engine.

Produces a transparent, weighted 0–100 risk score from weather, travel,
and logistics signals. All weights and thresholds are explicit so the
output is fully auditable.
"""


WEIGHTS = {
    "weather":   0.25,
    "travel":    0.25,
    "supplier":  0.20,
    "vip":       0.20,
    "guest":     0.10,
}


def compute_risk_score(weather_risk: dict, flight_data: dict, event_data: dict) -> dict:
    """
    Compute the overall event risk score from component signals.

    Returns a dict with:
        score       — weighted average, 0 (best) to 100 (worst)
        category    — Low / Moderate / High / Critical
        breakdown   — per-factor scores (0–100 each)
        weights     — factor weights used
        explanations — list of human-readable risk observations
    """
    breakdown = {
        "weather":  weather_risk.get("score", 30.0),
        "travel":   float(flight_data.get("disruption_risk_score", 20)),
        "supplier": 100.0 - float(event_data.get("supplier_readiness", 85)),
        "vip":      100.0 - float(event_data.get("vip_arrivals_completed", 70)),
        "guest":    100.0 - float(event_data.get("guest_confirmation", 80)),
    }

    total = sum(breakdown[k] * WEIGHTS[k] for k in WEIGHTS)

    if total < 25:
        category = "Low"
    elif total < 50:
        category = "Moderate"
    elif total < 75:
        category = "High"
    else:
        category = "Critical"

    return {
        "score":        round(total, 1),
        "category":     category,
        "breakdown":    {k: round(v, 1) for k, v in breakdown.items()},
        "weights":      WEIGHTS,
        "explanations": _build_explanations(weather_risk, flight_data, event_data),
    }


def _build_explanations(weather_risk: dict, flight_data: dict, event_data: dict) -> list[str]:
    """Generate one human-readable observation per risk factor."""
    out = []

    level = weather_risk.get("level", "Low")
    heat = weather_risk.get("heat_risk", 0)
    if level in ("High", "Critical"):
        out.append(f"Weather risk is {level.lower()} — extreme heat or precipitation conditions forecast.")
    elif level == "Moderate":
        out.append("Weather presents moderate risk — standard indoor-climate and precipitation contingencies apply.")
    else:
        out.append("Weather conditions are favourable for the event period.")

    if heat > 60:
        out.append("Doha heat index is extreme — indoor climate control confirmation is mandatory.")

    disruption = flight_data.get("disruption_risk_label", "Low")
    if disruption in ("High", "Critical"):
        out.append(f"Travel disruption risk is {disruption.lower()} — increase VIP arrival buffer significantly.")
    elif disruption == "Moderate":
        out.append("Moderate travel disruption risk — recommend +3 h buffer for all VIP arrivals.")
    else:
        out.append("Travel disruption risk is low — standard scheduling applies.")

    supplier = float(event_data.get("supplier_readiness", 85))
    if supplier < 70:
        out.append(f"Supplier readiness is critically low ({supplier:.0f}%) — immediate escalation required.")
    elif supplier < 85:
        out.append(f"Supplier readiness at {supplier:.0f}% — follow up outstanding confirmations.")
    else:
        out.append(f"Supplier readiness is strong ({supplier:.0f}%).")

    vip = float(event_data.get("vip_arrivals_completed", 70))
    if vip < 60:
        out.append(f"VIP arrival confirmation rate is low ({vip:.0f}%) — activate personal liaison protocol.")
    elif vip < 80:
        out.append(f"VIP arrivals at {vip:.0f}% — personal follow-up required for pending confirmations.")
    else:
        out.append(f"VIP arrival confirmations are strong ({vip:.0f}%).")

    guest = float(event_data.get("guest_confirmation", 80))
    if guest < 70:
        out.append(f"Guest confirmation rate is low ({guest:.0f}%) — consider targeted re-engagement.")
    else:
        out.append(f"Guest confirmation rate is adequate ({guest:.0f}%).")

    return out
