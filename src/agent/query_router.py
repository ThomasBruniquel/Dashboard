"""
Query router for the Geneva Event Intelligence dashboard.

Two layers of matching:
  1. Field detection  — what specifically is being asked (duration, participants, venue…)
  2. Event detection  — which event (or fall back to session context)

Returns natural-language responses, not data dumps.
Maintains a lightweight context dict so follow-up questions work naturally.
"""

from __future__ import annotations
import re
from src.api.geneva_events import estimate_budget

# ── Field patterns ─────────────────────────────────────────────────────────────
# Ordered: more specific patterns first
FIELD_PATTERNS: list[tuple[list[str], str]] = [
    # Duration
    (["how long", "how many days", "duration", "last how long", "run for", "ran for"], "duration"),
    # Participants / size
    (["how many people", "how many delegates", "how many participants", "how many visitors",
      "how many attendees", "how many guests", "attendance", "size"], "participants"),
    (["how many countries", "how many nations", "how many members", "countries represented"], "countries"),
    (["how many languages", "interpretation", "languages used", "simultaneous"], "languages"),
    # Location / venue
    (["where", "venue", "location", "which building", "which hall", "palais", "palexpo", "wto hq"], "venue"),
    # Dates / timing
    (["when", "what date", "what month", "what year", "took place", "held in", "happen"], "dates"),
    # Cost / budget
    (["how much", "cost", "price", "budget", "expensive", "per head", "per person", "spend"], "cost"),
    # Security
    (["security", "protocol", "protection", "safe", "diplomatic"], "security"),
    # Lead time
    (["lead time", "how far in advance", "plan ahead", "advance", "book how", "when to start"], "lead_time"),
    # Description
    (["tell me about", "what is", "describe", "explain", "overview", "summary", "about"], "describe"),
    # General stats (fallback — only if no more specific field matched)
    (["stats", "figures", "metrics", "numbers", "key facts"], "stats"),
    # Compare
    (["compare", "difference", "vs", "versus", "bigger", "smaller", "between", "all three", "all events"], "compare"),
    # Budget estimate with custom guest count
    (["estimate", "my event", "for my", "guests budget", "calculate", "if i have"], "estimate"),
    # Currency
    (["exchange rate", "chf to", "to eur", "to usd", "to qar", "currency", "rate", "convert"], "currency"),
    # Recommendations / advice
    (["recommend", "advice", "tip", "should i", "best time", "suggestion", "how to"], "recommend"),
]

# ── Event aliases ─────────────────────────────────────────────────────────────
EVENT_ALIASES: dict[str, list[str]] = {
    "wha":  ["wha", "world health assembly", "health assembly", "who assembly", "health organization"],
    "ww":   ["watches", "wonders", "w&w", "watchesandwonders", "horolog", "palexpo", "luxury watch", "watch fair"],
    "mc12": ["wto", "mc12", "ministerial", "trade conference", "wto conference", "world trade"],
}


def _detect_field(q: str) -> str:
    ql = q.lower()
    for patterns, field in FIELD_PATTERNS:
        if any(p in ql for p in patterns):
            return field
    return "general"


def _detect_event_id(q: str) -> str | None:
    ql = q.lower()
    for ev_id, aliases in EVENT_ALIASES.items():
        if any(a in ql for a in aliases):
            return ev_id
    return None


def _get_event(events: list[dict], ev_id: str | None) -> dict | None:
    if not ev_id:
        return None
    return next((e for e in events if e["id"] == ev_id), None)


# ── Natural-language field answers ────────────────────────────────────────────

def _answer_field(field: str, ev: dict, rates: dict, guests_hint: int | None = None) -> tuple[str, list[str]]:
    """Return a concise, natural-language answer for a specific field about one event."""
    calls: list[str] = ["Curated event metadata (Wikipedia + ICCA sources)"]
    name = ev["name"]

    if field == "duration":
        return (
            f"The **{name}** ran for **{ev['days']} days**, from {ev['dates']}."
        ), calls

    if field == "participants":
        return (
            f"The **{name}** brought together **{ev['participants']:,} participants** "
            f"from {ev['countries']} countries."
        ), calls

    if field == "countries":
        return (
            f"**{ev['countries']} countries** (or member states) were represented at the {name}."
        ), calls

    if field == "languages":
        booths = ev["languages"] * 2
        return (
            f"The {name} operated in **{ev['languages']} official languages**, "
            f"requiring approximately **{booths} simultaneous interpretation booths**."
        ), calls

    if field == "venue":
        return (
            f"The **{name}** was held at **{ev['venue']}**, {ev['city']} "
            f"— a {ev['venue_sqm']:,} m² venue. Security level: {ev['security']}."
        ), calls

    if field == "dates":
        return (
            f"It took place **{ev['dates']}** — {ev['days']} days in "
            f"{ev['month']} {ev['year']}."
        ), calls

    if field == "cost":
        total_est = ev["cost_per_head_chf"] * ev["participants"]
        return (
            f"The benchmark cost per participant for a **{ev['category']}** event like "
            f"the **{name}** is **CHF {ev['cost_per_head_chf']:,}**.\n\n"
            f"Applied to the actual {ev['participants']:,} participants over {ev['days']} days, "
            f"that's an estimated **CHF {total_est:,}** total."
        ), calls

    if field == "security":
        return (
            f"The **{name}** required **{ev['security']}** — "
            f"typical for a {ev['category'].lower()} event. "
            f"Security coordination requires a minimum of "
            f"**{ev['lead_time_months']} months** of lead time."
        ), calls

    if field == "lead_time":
        return (
            f"For an event like the **{name}** ({ev['category'].lower()}), "
            f"plan at least **{ev['lead_time_months']} months** in advance. "
            f"This covers venue booking, security clearance, and catering contracts."
        ), calls

    if field == "describe":
        extract = ev.get("extract", "")
        calls.append("Wikipedia REST API")
        parts = [f"**{name}** ({ev['dates']})\n"]
        if extract:
            parts.append(extract)
        parts.append(f"\n[Read on Wikipedia ↗]({ev.get('wiki_url','')})")
        return "\n".join(parts), calls

    # stats — full summary
    return _full_stats(ev), calls


def _full_stats(ev: dict) -> str:
    return (
        f"**{ev['name']}** — full figures\n\n"
        f"- Participants: **{ev['participants']:,}**\n"
        f"- Countries: **{ev['countries']}**\n"
        f"- Duration: **{ev['days']} days** ({ev['dates']})\n"
        f"- Languages: **{ev['languages']}**\n"
        f"- Venue: **{ev['venue']}** ({ev['venue_sqm']:,} m²)\n"
        f"- Security: **{ev['security']}**\n"
        f"- Benchmark cost/head: **CHF {ev['cost_per_head_chf']:,}**\n"
        f"- Lead time: **{ev['lead_time_months']} months**"
    )


def _compare_all(events: list[dict]) -> tuple[str, list[str]]:
    calls = ["Curated event metadata (Wikipedia + ICCA sources)"]
    rows  = [
        ("Participants",    lambda e: f"{e['participants']:,}"),
        ("Countries",       lambda e: str(e["countries"])),
        ("Days",            lambda e: str(e["days"])),
        ("Languages",       lambda e: str(e["languages"])),
        ("Venue sqm",       lambda e: f"{e['venue_sqm']:,}"),
        ("Cost/head (CHF)", lambda e: f"{e['cost_per_head_chf']:,}"),
        ("Lead time (mo.)", lambda e: str(e["lead_time_months"])),
    ]
    header = f"{'Metric':<22} | " + " | ".join(f"{e['short']:>14}" for e in events)
    lines  = ["**Comparison — 3 Geneva reference events**\n", header, "-" * 68]
    for label, fn in rows:
        lines.append(f"{label:<22} | " + " | ".join(f"{fn(e):>14}" for e in events))
    return "\n".join(lines), calls


def _estimate_budget(events: list[dict], question: str, ev: dict | None, rates: dict) -> tuple[str, list[str]]:
    calls = ["Budget estimator (ICCA Geneva market benchmarks)", "open.er-api.com — live CHF rates"]
    m = re.search(r"\b(\d{2,5})\b", question)
    guests = int(m.group(1)) if m else (ev["participants"] if ev else 200)
    ref    = ev or events[0]
    b      = estimate_budget(guests, ref["cost_per_head_chf"], ref["days"])

    lines = [
        f"**Budget estimate for {guests:,} guests** "
        f"(benchmark: {ref['short']}, {ref['days']} days)\n",
        f"- Catering:  **CHF {b['catering_chf']:>10,.0f}**",
        f"- AV / Tech: **CHF {b['av_tech_chf']:>10,.0f}**",
        f"- Venue:     **CHF {b['venue_chf']:>10,.0f}**",
        f"- Security:  **CHF {b['security_chf']:>10,.0f}**",
        f"- **Total:   CHF {b['total_chf']:>10,.0f}**",
        f"- Per head:  CHF {b['per_head_chf']:>10,.0f}",
    ]
    for curr in ["EUR", "USD", "QAR"]:
        r = rates.get(curr)
        if r:
            lines.append(f"- In {curr}: **{curr} {b['total_chf'] * r:,.0f}**")
    return "\n".join(lines), calls


# ── Public entry point ─────────────────────────────────────────────────────────

def handle_query(
    question: str,
    live: dict,
    context: dict | None = None,
) -> tuple[str, list[str], dict]:
    """
    Route `question` and return (response, api_calls, updated_context).

    `context` carries the last discussed event across turns so follow-up
    questions like "and how many people?" work without repeating the event name.
    """
    if context is None:
        context = {}

    events = live.get("events", [])
    rates  = live.get("currency_data", {}).get("rates", {})
    calls: list[str] = []

    # Detect event and field
    ev_id = _detect_event_id(question)
    if ev_id:
        context = {**context, "last_event_id": ev_id}   # remember for next turn
    else:
        ev_id = context.get("last_event_id")             # use context

    ev    = _get_event(events, ev_id)
    field = _detect_field(question)

    # ── Routing ────────────────────────────────────────────────
    if field == "compare":
        response, calls = _compare_all(events)
        return response, calls, context

    if field == "estimate":
        response, calls = _estimate_budget(events, question, ev, rates)
        return response, calls, context

    if field == "currency":
        calls.append("open.er-api.com — live CHF rates")
        lines = ["**Live CHF exchange rates**\n"]
        for curr in ["EUR", "USD", "GBP", "QAR"]:
            r = rates.get(curr)
            if r:
                lines.append(f"- 1 CHF = **{r:.4f} {curr}**")
        return "\n".join(lines), calls, context

    if field == "recommend":
        return (
            "**Geneva event planning — key tips**\n\n"
            "- **Lead time**: 12–24 months for Palais des Nations or Palexpo.\n"
            "- **Peak season**: May–June and October–November are densest — book early.\n"
            "- **Catering**: CHF 150–200 per person per day for professional Geneva rates.\n"
            "- **Interpretation**: add CHF 5,000–15,000 per language pair per day.\n"
            "- **Security**: diplomatic events need cantonal police coordination — start 6 months early.\n"
            "- **Accommodation**: major sessions fill hotels 6–9 months ahead."
        ), ["Rule-based recommendations (ICCA + industry benchmarks)"], context

    if field == "cost":
        calls.append("Budget estimator (ICCA benchmarks) + open.er-api.com")
        if ev:
            response, c = _answer_field("cost", ev, rates)
            calls += c
            return response, calls, context
        # No event specified — ask which one or show all
        lines = ["**Benchmark cost per head by event type**\n"]
        for e in events:
            lines.append(f"- **{e['short']}** ({e['category']}): CHF {e['cost_per_head_chf']:,}/head")
        lines.append("\nAsk *\"budget for 300 guests\"* for a full estimate.")
        return "\n".join(lines), calls, context

    # Field about a specific event
    if field not in ("general",) and ev:
        response, c = _answer_field(field, ev, rates)
        return response, c, context

    # Field with no event identified
    if field not in ("general",) and not ev:
        lines = [f"Which event are you asking about?\n"]
        for e in events:
            lines.append(f"- **{e['short']}** ({e['dates']})")
        return "\n".join(lines), [], context

    # Fallback
    return (
        "I can answer questions about:\n\n"
        + "\n".join(f"- **{e['name']}** ({e['dates']})" for e in events)
        + "\n\nTry: *\"How long was the WHA?\"* · *\"Where was WTO MC12 held?\"* · "
          "*\"Compare the 3 events\"* · *\"Budget for 500 guests\"*"
    ), [], context
