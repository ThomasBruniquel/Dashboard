"""
Jolpica F1 API client — no API key required.
Community-maintained fork of the Ergast Motor Racing API.
https://api.jolpi.ca/
"""

import requests
import streamlit as st

BASE = "https://api.jolpi.ca/ergast/f1"


@st.cache_data(ttl=3600, show_spinner=False)
def get_races(year: int = 2024) -> list[dict]:
    """Full race calendar for a season with circuit lat/lon."""
    resp = requests.get(f"{BASE}/{year}/races/",
                        params={"format": "json", "limit": 30}, timeout=15)
    resp.raise_for_status()
    return resp.json()["MRData"]["RaceTable"]["Races"]


@st.cache_data(ttl=3600, show_spinner=False)
def get_driver_standings(year: int = 2024) -> list[dict]:
    resp = requests.get(f"{BASE}/{year}/driverstandings/",
                        params={"format": "json"}, timeout=10)
    resp.raise_for_status()
    lists = resp.json()["MRData"]["StandingsTable"]["StandingsLists"]
    return lists[0]["DriverStandings"] if lists else []


@st.cache_data(ttl=3600, show_spinner=False)
def get_constructor_standings(year: int = 2024) -> list[dict]:
    resp = requests.get(f"{BASE}/{year}/constructorstandings/",
                        params={"format": "json"}, timeout=10)
    resp.raise_for_status()
    lists = resp.json()["MRData"]["StandingsTable"]["StandingsLists"]
    return lists[0]["ConstructorStandings"] if lists else []


@st.cache_data(ttl=3600, show_spinner=False)
def get_race_results(year: int, round_num: int) -> dict | None:
    resp = requests.get(f"{BASE}/{year}/{round_num}/results/",
                        params={"format": "json"}, timeout=10)
    if resp.status_code != 200:
        return None
    races = resp.json()["MRData"]["RaceTable"]["Races"]
    return races[0] if races else None


@st.cache_data(ttl=86400, show_spinner=False)
def get_all_results(year: int = 2024) -> list[dict]:
    """All race results in one call (winners only for performance)."""
    resp = requests.get(f"{BASE}/{year}/results/1/",
                        params={"format": "json", "limit": 30}, timeout=15)
    if resp.status_code != 200:
        return []
    return resp.json()["MRData"]["RaceTable"]["Races"]


@st.cache_data(ttl=86400, show_spinner=False)
def get_driver_season_results(driver_id: str, year: int = 2024) -> list[dict]:
    """All race results for one driver in a season — points, position, status."""
    resp = requests.get(
        f"{BASE}/{year}/drivers/{driver_id}/results/",
        params={"format": "json", "limit": 50}, timeout=15,
    )
    if resp.status_code != 200:
        return []
    out = []
    for race in resp.json()["MRData"]["RaceTable"]["Races"]:
        for r in race.get("Results", []):
            out.append({
                "round":    int(race["round"]),
                "race":     race["raceName"],
                "position": int(r.get("position", 99)),
                "points":   float(r.get("points", 0)),
                "status":   r.get("status", ""),
                "grid":     int(r.get("grid", 0)),
                "laps":     int(r.get("laps", 0)),
                "time":     r.get("Time", {}).get("time", ""),
            })
    return out


@st.cache_data(ttl=86400, show_spinner=False)
def get_driver_wiki(wiki_url: str) -> dict:
    """Fetch driver photo (thumbnail) and bio extract from Wikipedia REST API."""
    if "/wiki/" not in wiki_url:
        return {}
    title = wiki_url.split("/wiki/")[-1]
    headers = {"User-Agent": "F1EventDashboard/1.0 (portfolio; python-requests)"}
    resp = requests.get(
        f"https://en.wikipedia.org/api/rest_v1/page/summary/{title}",
        headers=headers, timeout=10,
    )
    if resp.status_code != 200:
        return {}
    data = resp.json()
    return {
        "thumbnail": data.get("thumbnail", {}).get("source", ""),
        "extract":   data.get("extract", "")[:700],
        "wiki_url":  data.get("content_urls", {}).get("desktop", {}).get("page", wiki_url),
    }


# ── Helper: team colours (UI styling only — not event data) ───────────────────
TEAM_COLORS: dict[str, str] = {
    "McLaren":      "#FF8000",
    "Ferrari":      "#E8002D",
    "Red Bull":     "#3671C6",
    "Mercedes":     "#27F4D2",
    "Aston Martin": "#229971",
    "Williams":     "#64C4FF",
    "Racing Bulls": "#6692FF",
    "Haas F1 Team": "#B6BABD",
    "Kick Sauber":  "#52E252",
    "Alpine F1 Team": "#0093CC",
}

DEFAULT_COLOR = "#888888"
