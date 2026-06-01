"""
Mock event logistics module.

In production this would pull live data from an event management platform
(e.g., Cvent, Eventforce, or a bespoke CRM API). Data here is realistic
but explicitly mocked for demonstration purposes.
"""


MOCK_EVENT_DATA = {
    "data_type": "mock_api",
    "note": (
        "Mock API data — for demonstration purposes only. "
        "In production, this module connects to an event management platform API."
    ),
    "event_name": "Geneva–Doha Executive Summit",
    "venue": {
        "name": "Four Seasons Hotel Doha",
        "location": "West Bay, Doha, Qatar",
        "capacity": 350,
        "confirmed": True,
        "indoor_climate_control": True,
    },
    "venue_readiness": 88,
    "guest_confirmation": 79,
    "vip_arrivals_completed": 72,
    "supplier_readiness": 85,
    "security_clearance": 91,
    "suppliers": [
        {"category": "AV & Technology",             "status": "Confirmed",   "readiness": 92},
        {"category": "Catering & F&B",              "status": "Confirmed",   "readiness": 87},
        {"category": "Ground Transportation",        "status": "Confirmed",   "readiness": 81},
        {"category": "Floral & Decor",              "status": "In Progress", "readiness": 75},
        {"category": "Security & Protocol",         "status": "Confirmed",   "readiness": 95},
        {"category": "Simultaneous Interpretation", "status": "Confirmed",   "readiness": 90},
    ],
    "vip_guests": {
        "total_invited": 42,
        "confirmed": 30,
        "pending": 8,
        "declined": 4,
    },
    "agenda_status": "Draft confirmed — pending final speaker biographies",
    "contingency_plan": "Available — full indoor backup for all outdoor programme elements",
}


def get_event_logistics() -> dict:
    """Return mock event logistics data for a Geneva–Doha executive summit."""
    return MOCK_EVENT_DATA.copy()
