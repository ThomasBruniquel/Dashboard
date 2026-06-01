"""
Flight intelligence module for the Geneva (GVA) -> Doha (DOH) route.

Fetches real departure records from the OpenSky Network free API (no API key required).
Falls back to realistic estimates if the API is unavailable or returns no matching flights.
"""

import requests
import streamlit as st
from datetime import datetime, timedelta

OPENSKY_BASE = "https://opensky-network.org/api"
GVA_ICAO = "LSGG"
DOH_ICAO = "OTHH"
LOOKBACK_DAYS = 7
DAILY_DIRECT_FLIGHTS = 1  # Qatar Airways operates one daily direct GVA-DOH service

FALLBACK_DATA = {
    "data_type": "estimated",
    "source": "Estimated (OpenSky API unavailable)",
    "route": "GVA -> DOH",
    "origin": {"code": "GVA", "city": "Geneva", "country": "Switzerland"},
    "destination": {"code": "DOH", "city": "Doha", "country": "Qatar"},
    "flights_last_7_days": None,
    "callsigns_observed": [],
    "direct_flight_available": True,
    "routes_count": 2,
    "avg_travel_duration_hours": 6.5,
    "disruption_risk_label": "Low",
    "disruption_risk_score": 18,
    "recommended_buffer_hours": 3,
    "vip_ground_services": {
        "private_terminal_gva": True,
        "meet_and_greet_doh": True,
        "limousine_transfer_available": True,
        "customs_fast_track_doh": True,
    },
    "note": None,
}


@st.cache_data(ttl=3600, show_spinner=False)
def get_flight_data() -> dict:
    """
    Fetch recent GVA -> DOH departure data from OpenSky Network.

    Computes average flight duration and disruption risk from actual ADS-B records.
    Falls back to FALLBACK_DATA with a clear note if the API is unavailable or
    no matching flights are found (ADS-B coverage gaps are common over remote ocean areas).
    """
    end = int(datetime.utcnow().timestamp())
    begin = int((datetime.utcnow() - timedelta(days=LOOKBACK_DAYS)).timestamp())

    try:
        resp = requests.get(
            f"{OPENSKY_BASE}/flights/departure",
            params={"airport": GVA_ICAO, "begin": begin, "end": end},
            timeout=15,
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        all_departures = resp.json()

        doh_flights = [
            f for f in all_departures
            if f.get("estArrivalAirport") == DOH_ICAO
        ]

        if not doh_flights:
            result = FALLBACK_DATA.copy()
            result["note"] = (
                f"OpenSky Network returned 0 GVA -> DOH flights in the last {LOOKBACK_DAYS} days. "
                "ADS-B coverage gaps over remote areas may explain the absence. Showing estimates."
            )
            return result

        # Duration from ADS-B firstSeen / lastSeen (not perfectly accurate but genuine)
        durations = []
        for f in doh_flights:
            dep_ts = f.get("firstSeen")
            arr_ts = f.get("lastSeen")
            if dep_ts and arr_ts:
                hours = (arr_ts - dep_ts) / 3600
                if 5.0 < hours < 12.0:  # sanity bounds for GVA->DOH
                    durations.append(hours)

        avg_duration = round(sum(durations) / len(durations), 1) if durations else 6.5

        callsigns = sorted({
            (f.get("callsign") or "").strip()
            for f in doh_flights
            if (f.get("callsign") or "").strip()
        })

        # Disruption score: ratio of detected vs. expected daily flights
        expected = DAILY_DIRECT_FLIGHTS * LOOKBACK_DAYS
        ratio = len(doh_flights) / max(expected, 1)
        if ratio >= 0.85:
            disruption_label, disruption_score = "Low", 15
        elif ratio >= 0.60:
            disruption_label, disruption_score = "Moderate", 40
        else:
            disruption_label, disruption_score = "High", 70

        return {
            "data_type": "live_api",
            "source": "OpenSky Network (opensky-network.org)",
            "route": "GVA -> DOH",
            "origin": {"code": "GVA", "city": "Geneva", "country": "Switzerland"},
            "destination": {"code": "DOH", "city": "Doha", "country": "Qatar"},
            "flights_last_7_days": len(doh_flights),
            "callsigns_observed": callsigns[:6],
            "direct_flight_available": True,
            "routes_count": 2,
            "avg_travel_duration_hours": avg_duration,
            "disruption_risk_label": disruption_label,
            "disruption_risk_score": disruption_score,
            "recommended_buffer_hours": 3,
            "vip_ground_services": {
                "private_terminal_gva": True,
                "meet_and_greet_doh": True,
                "limousine_transfer_available": True,
                "customs_fast_track_doh": True,
            },
            "note": None,
        }

    except Exception as exc:
        result = FALLBACK_DATA.copy()
        result["note"] = f"OpenSky API unavailable ({exc}). Showing estimates."
        return result
