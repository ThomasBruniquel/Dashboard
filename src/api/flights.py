"""
Mock flight intelligence module for the Geneva (GVA) → Doha (DOH) route.

In production this would connect to a commercial flight data API
(e.g., Amadeus, OAG, Cirium). Data here is realistic but explicitly mocked
for demonstration purposes.
"""


MOCK_FLIGHT_DATA = {
    "data_type": "mock_api",
    "note": (
        "Mock API data — for demonstration purposes only. "
        "In production, this module connects to a live flight intelligence API."
    ),
    "route": "GVA → DOH",
    "origin": {
        "code": "GVA",
        "city": "Geneva",
        "country": "Switzerland",
        "timezone": "Europe/Zurich",
    },
    "destination": {
        "code": "DOH",
        "city": "Doha",
        "country": "Qatar",
        "timezone": "Asia/Qatar",
    },
    "airlines": [
        {
            "name": "Qatar Airways",
            "code": "QR",
            "direct": True,
            "duration_hours": 6.5,
            "frequency": "Daily",
            "notes": "Business & First Class available. Private terminal at GVA on request.",
        },
        {
            "name": "Lufthansa",
            "code": "LH",
            "direct": False,
            "via": "FRA",
            "duration_hours": 9.5,
            "frequency": "Daily",
            "notes": "Connection at Frankfurt — not recommended for VIP guests.",
        },
    ],
    "direct_flight_available": True,
    "routes_count": 2,
    "avg_travel_duration_hours": 6.5,
    "disruption_risk_label": "Low",
    "disruption_risk_score": 18,
    "recommended_buffer_hours": 3,
    "peak_travel_months": ["December", "January", "March"],
    "typical_booking_lead_days": 45,
    "visa_requirements": {
        "swiss_passport": "Visa on arrival (Hayya card for large-scale events)",
        "eu_passport": "Visa on arrival (Hayya card for large-scale events)",
    },
    "vip_ground_services": {
        "private_terminal_gva": True,
        "meet_and_greet_doh": True,
        "limousine_transfer_available": True,
        "customs_fast_track_doh": True,
    },
}


def get_flight_data() -> dict:
    """Return mock flight intelligence for the Geneva → Doha route."""
    return MOCK_FLIGHT_DATA.copy()
