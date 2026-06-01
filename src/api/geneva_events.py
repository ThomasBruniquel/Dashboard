"""
Geneva event catalogue — identifiers + live Wikipedia data.

Only the event name and Wikipedia article title are stored here.
All metrics (participants, countries, days, etc.) are extracted at runtime
from the full Wikipedia article text using regex — no hardcoded numbers.
"""

from __future__ import annotations
import re
import requests
import streamlit as st

WIKI_API  = "https://en.wikipedia.org/w/api.php"
WIKI_REST = "https://en.wikipedia.org/api/rest_v1/page/summary"
HEADERS   = {"User-Agent": "GenevaEventDashboard/1.0 (portfolio; python-requests)"}

# ── Event catalogue — identifiers only ────────────────────────────────────────
EVENTS = [
    {
        "id":         "wha",
        "name":       "World Health Assembly",
        "short":      "WHA",
        "wiki_titles": ["World Health Assembly"],
        "category":   "Institutional / Diplomatic",
        "color":      "#1565C0",
        "accent":     "#E3F2FD",
    },
    {
        "id":         "ww",
        "name":       "Watches & Wonders Geneva",
        "short":      "W&W",
        "wiki_titles": ["Watches and Wonders"],
        "category":   "Luxury Trade Show",
        "color":      "#B8860B",
        "accent":     "#FFF9E6",
    },
    {
        "id":         "mc12",
        "name":       "WTO Ministerial Conference 2022",
        "short":      "WTO MC12",
        "wiki_titles": ["World Trade Organization Ministerial Conference of 2022"],
        "category":   "Ministerial / Trade",
        "color":      "#2E7D32",
        "accent":     "#E8F5E9",
    },
]


# ── Wikipedia fetch ────────────────────────────────────────────────────────────

@st.cache_data(ttl=86400, show_spinner=False)
def _fetch_full_text(title: str) -> str:
    """Fetch the full plain-text Wikipedia article (not just the intro summary)."""
    resp = requests.get(
        WIKI_API,
        params={
            "action":          "query",
            "prop":            "extracts",
            "titles":          title,
            "format":          "json",
            "explaintext":     True,
            "exsectionformat": "plain",
        },
        headers=HEADERS,
        timeout=15,
    )
    if resp.status_code != 200:
        return ""
    pages = resp.json().get("query", {}).get("pages", {})
    page  = next(iter(pages.values()))
    # -1 page id means article not found
    if page.get("pageid", -1) == -1:
        return ""
    return page.get("extract", "")


@st.cache_data(ttl=86400, show_spinner=False)
def _fetch_summary(title: str) -> tuple[str, str]:
    """Fetch intro summary + Wikipedia URL."""
    slug = title.replace(" ", "_")
    resp = requests.get(f"{WIKI_REST}/{slug}", headers=HEADERS, timeout=10)
    if resp.status_code == 200:
        data = resp.json()
        return (
            data.get("extract", ""),
            data.get("content_urls", {}).get("desktop", {}).get("page", ""),
        )
    return "", f"https://en.wikipedia.org/wiki/{slug}"


# ── Fact extraction from article text (regex — no LLM, no hardcoding) ─────────

def _parse_int(s: str) -> int:
    """Remove commas/spaces from number string and return int."""
    return int(re.sub(r"[,\s]", "", s))


def extract_facts(text: str) -> dict:
    """
    Extract key event metrics from Wikipedia article plain text using regex.
    Returns only facts actually found in the text — nothing invented.
    """
    facts: dict = {}
    t = text

    # Participants / visitors / delegates (e.g. "45,000 visitors", "3,000 delegates")
    m = re.search(
        r"([\d][,\d]*)\s+(?:participants?|delegates?|visitors?|attendees?|representatives?)",
        t, re.I,
    )
    if m:
        facts["participants"] = _parse_int(m.group(1))

    # Countries / member states — allow up to 2 words between number and keyword
    # handles "193 member states", "164 WTO member countries", "all 164 members"
    m = re.search(
        r"([\d][,\d]*)\s+(?:\w+\s+){0,2}(?:countries|nations?|member\s+(?:states?|countries?)|members?|delegations?)\b",
        t, re.I,
    )
    if m:
        facts["countries"] = _parse_int(m.group(1))

    # Exhibitors / brands / companies (for trade shows)
    m = re.search(
        r"([\d][,\d]*)\s+(?:exhibitors?|brands?|maisons?|companies|manufacturers?|watch(?:making)?\s+brands?)",
        t, re.I,
    )
    if m:
        facts["exhibitors"] = _parse_int(m.group(1))

    # Duration in days
    m = re.search(r"\b(\d{1,2})\s+days?\b", t, re.I)
    if m:
        facts["days"] = int(m.group(1))

    # Year (first 20xx mention)
    m = re.search(r"\b(20[12]\d)\b", t)
    if m:
        facts["year"] = int(m.group(1))

    # Venue / location keywords
    for venue_kw in ["Palais des Nations", "Palexpo", "WTO Headquarters", "Centre William Rappard"]:
        if venue_kw.lower() in t.lower():
            facts["venue"] = venue_kw
            break

    return facts


# ── Public entry point ─────────────────────────────────────────────────────────

@st.cache_data(ttl=86400, show_spinner=False)
def fetch_event_summaries() -> list[dict]:
    """
    For each event: fetch full Wikipedia article text, extract facts via regex,
    fetch intro summary. Returns enriched event dicts — all data from Wikipedia API.
    """
    enriched = []
    for ev in EVENTS:
        entry = ev.copy()
        full_text = ""
        summary   = ""
        wiki_url  = ""
        used_title = ""

        # Try each title until we find a real article
        for title in ev["wiki_titles"]:
            txt = _fetch_full_text(title)
            if txt:
                full_text   = txt
                used_title  = title
                summary, wiki_url = _fetch_summary(title)
                break

        entry["full_text"]   = full_text
        entry["extract"]     = summary
        entry["wiki_url"]    = wiki_url
        entry["wiki_title_used"] = used_title
        entry["facts"]       = extract_facts(full_text) if full_text else {}

        enriched.append(entry)
    return enriched
