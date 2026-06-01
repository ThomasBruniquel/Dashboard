"""Wikipedia API — past major events in Qatar/Doha. No API key required."""

import requests
import streamlit as st

WIKI_API = "https://en.wikipedia.org/w/api.php"


@st.cache_data(ttl=86400, show_spinner=False)
def search_major_events(query: str, n: int = 6) -> list[dict]:
    """Search Wikipedia for articles matching a query. Returns title + snippet + url."""
    try:
        resp = requests.get(
            WIKI_API,
            params={
                "action":      "query",
                "list":        "search",
                "srsearch":    query,
                "srlimit":     n,
                "format":      "json",
                "srnamespace": 0,
            },
            headers={"User-Agent": "LuxuryEventDashboard/1.0 (portfolio project; python-requests)"},
            timeout=10,
        )
        resp.raise_for_status()

        results = []
        for r in resp.json().get("query", {}).get("search", []):
            snippet = (r.get("snippet", "")
                       .replace('<span class="searchmatch">', "**")
                       .replace("</span>", "**")
                       .replace("&quot;", '"')
                       .replace("&#039;", "'")
                       .replace("&amp;", "&"))
            results.append({
                "title":     r["title"],
                "snippet":   snippet,
                "url":       f"https://en.wikipedia.org/wiki/{r['title'].replace(' ', '_')}",
                "wordcount": r.get("wordcount", 0),
            })
        return results

    except Exception as exc:
        return [{"title": "Error", "snippet": str(exc), "url": "", "wordcount": 0}]
