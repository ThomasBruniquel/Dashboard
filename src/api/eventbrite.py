"""
Eventbrite API client — free OAuth token, no credit card required.
Get yours at: https://www.eventbrite.com/platform/api
"""

import requests
import pandas as pd
import streamlit as st
from datetime import datetime, timedelta, timezone

EVENTBRITE_BASE = "https://www.eventbriteapi.com/v3"

BUSINESS_CATEGORY_ID = "101"   # Business & Professional
SCIENCE_CATEGORY_ID  = "102"   # Science & Technology

SETUP_INSTRUCTIONS = """
**No Eventbrite token found.**

1. Go to [eventbrite.com/platform/api](https://www.eventbrite.com/platform/api)
2. Sign in / create a free account
3. Create an app → copy the **Private Token**
4. Add it to a `.env` file in the project root:

```
EVENTBRITE_TOKEN=your_private_token_here
```

5. Restart the app.
"""


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_past_events(token: str, location: str = "Geneva, Switzerland", radius: str = "30km", days_back: int = 365) -> dict:
    """
    Fetch past business/professional events in a given location from Eventbrite.
    Returns a structured dict with event list, summary stats, and a tidy DataFrame.
    """
    if not token:
        return {"error": "no_token", "events": [], "df": None, "total": 0}

    since = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        resp = requests.get(
            f"{EVENTBRITE_BASE}/events/search/",
            headers=_headers(token),
            params={
                "location.address":          location,
                "location.within":           radius,
                "categories":                f"{BUSINESS_CATEGORY_ID},{SCIENCE_CATEGORY_ID}",
                "time_filter":               "past",
                "start_date.range_start":    since,
                "sort_by":                   "date",
                "page_size":                 50,
                "expand":                    "venue,ticket_classes",
            },
            timeout=15,
        )

        if resp.status_code == 401:
            return {"error": "invalid_token", "events": [], "df": None, "total": 0}

        resp.raise_for_status()
        raw = resp.json()
        events_raw = raw.get("events", [])

        events = []
        for ev in events_raw:
            tcs      = ev.get("ticket_classes") or []
            capacity = sum((tc.get("quantity_total") or 0) for tc in tcs) or None
            venue    = (ev.get("venue") or {})

            events.append({
                "name":       ev.get("name", {}).get("text", "N/A"),
                "start":      ev.get("start", {}).get("local", "")[:10],
                "month":      ev.get("start", {}).get("local", "")[:7],
                "venue_name": venue.get("name", "N/A"),
                "venue_city": (venue.get("address") or {}).get("city", "Doha"),
                "url":        ev.get("url", ""),
                "is_free":    ev.get("is_free", False),
                "capacity":   capacity,
                "status":     ev.get("status", ""),
            })

        df = pd.DataFrame(events) if events else pd.DataFrame()

        return {
            "events":  events,
            "df":      df,
            "total":   raw.get("pagination", {}).get("object_count", len(events)),
            "fetched": len(events),
            "error":   None,
        }

    except requests.exceptions.Timeout:
        return {"error": "timeout", "events": [], "df": None, "total": 0}
    except Exception as exc:
        return {"error": str(exc), "events": [], "df": None, "total": 0}


def event_summary_stats(df: pd.DataFrame) -> dict:
    """Compute summary KPIs from a tidy event DataFrame."""
    if df.empty:
        return {}

    df = df.copy()
    df["start_dt"] = pd.to_datetime(df["start"], errors="coerce")

    monthly = df.groupby("month").size().reset_index(name="count")
    monthly = monthly.sort_values("month")

    busiest_month = monthly.loc[monthly["count"].idxmax(), "month"] if not monthly.empty else None
    venues = df[df["venue_name"] != "N/A"]["venue_name"].value_counts()

    with_capacity  = df["capacity"].dropna()
    avg_capacity   = int(with_capacity.mean()) if not with_capacity.empty else None

    return {
        "total_events":    len(df),
        "busiest_month":   busiest_month,
        "busiest_count":   int(monthly["count"].max()) if not monthly.empty else 0,
        "top_venue":       venues.index[0] if not venues.empty else "N/A",
        "top_venue_count": int(venues.iloc[0]) if not venues.empty else 0,
        "pct_free":        round(df["is_free"].mean() * 100, 1),
        "avg_capacity":    avg_capacity,
        "monthly_df":      monthly,
    }
