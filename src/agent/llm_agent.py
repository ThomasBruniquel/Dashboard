"""
RAG (Retrieval-Augmented Generation) agent.

For every user question:
  1. Search Wikipedia live (always)
  2. Fetch live exchange rates if the question involves money/currency
  3. Inject the fetched data into the LLM context
  4. LLM answers ONLY from what was retrieved — nothing hardcoded

Nothing is pre-stored. Every response is grounded in live API calls.
"""

from __future__ import annotations
import os
import json
import requests as _req
import streamlit as st

GEMINI_MODEL = "gemini-2.5-flash-lite"
GROQ_MODEL   = "llama-3.3-70b-versatile"

MONEY_KEYWORDS = {
    "budget", "cost", "price", "coût", "prix", "budget", "franc", "euro",
    "chf", "eur", "usd", "qar", "dollar", "currency", "monnaie", "dépense",
    "expense", "spend", "argent", "combien", "how much", "financement",
}


# ── Live data fetchers ─────────────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def _wiki_fetch(query: str) -> str:
    """Search Wikipedia and return the top article summary."""
    headers = {"User-Agent": "GenevaEventDashboard/1.0 (portfolio; python-requests)"}

    search = _req.get(
        "https://en.wikipedia.org/w/api.php",
        params={"action": "query", "list": "search", "srsearch": query,
                "srlimit": 2, "format": "json", "srnamespace": 0},
        headers=headers, timeout=10,
    ).json().get("query", {}).get("search", [])

    if not search:
        return f"No Wikipedia results for: {query}"

    title = search[0]["title"]
    resp  = _req.get(
        f"https://en.wikipedia.org/api/rest_v1/page/summary/{title.replace(' ', '_')}",
        headers=headers, timeout=10,
    )
    if resp.status_code == 200:
        data    = resp.json()
        extract = data.get("extract", "")[:1000]
        url     = data.get("content_urls", {}).get("desktop", {}).get("page", "")
        return f"Source: {title} ({url})\n\n{extract}"
    return f"Article '{title}' found but unavailable."


@st.cache_data(ttl=3600, show_spinner=False)
def _rates_fetch() -> str:
    """Fetch live CHF exchange rates."""
    try:
        r = _req.get("https://open.er-api.com/v6/latest/CHF", timeout=10).json()
        rates = r.get("rates", {})
        lines = [f"1 CHF = {rates[c]:.4f} {c}" for c in ["EUR", "USD", "GBP", "QAR"] if c in rates]
        return "\n".join(lines)
    except Exception as e:
        return f"Exchange rate API unavailable: {e}"


def _needs_rates(question: str) -> bool:
    q = question.lower()
    return any(kw in q for kw in MONEY_KEYWORDS)


# ── Query enhancement ─────────────────────────────────────────────────────────

_WHA  = ("wha", "world health assembly", "assemblée mondiale", "assemblée santé", "who assembly")
_WW   = ("watches and wonders", "watches & wonders", "w&w", "montres genève", "horlog", "palexpo watch")
_WTO  = ("wto", "omc", "mc12", "ministérielle", "ministerial conference", "world trade")

_BUDGET_KW = ("budget", "coût", "cost", "financement", "composé", "composition",
               "dépense", "funding", "argent", "prix", "how much", "combien coûte")
_PART_KW   = ("participants", "délégués", "delegates", "combien de personnes",
               "how many people", "attendance", "combien de gens")
_COUNTRY_KW = ("pays", "countries", "nations", "membres", "members", "représentés")
_VENUE_KW   = ("venue", "lieu", "endroit", "where", "palais", "bâtiment", "salle")
_DURATION_KW = ("durée", "jours", "how long", "duration", "combien de jours", "long")


def _event_query(q: str) -> str:
    """Return the clean English Wikipedia article name for the detected event."""
    if any(x in q for x in _WHA):  return "World Health Assembly"
    if any(x in q for x in _WW):   return "Watches and Wonders Geneva"
    if any(x in q for x in _WTO):  return "Twelfth WTO Ministerial Conference 2022 Geneva"
    return ""


def _extra_query(q: str) -> str | None:
    """Return a second, more specific search for budget/org-level questions."""
    if any(x in q for x in _BUDGET_KW):
        if any(x in q for x in _WHA):  return "World Health Organization budget contributions"
        if any(x in q for x in _WTO):  return "World Trade Organization secretariat funding"
        if any(x in q for x in _WW):   return "Fondation de la Haute Horlogerie Geneva"
    return None


def _build_context(question: str) -> tuple[str, list[str]]:
    """Fetch 1-2 Wikipedia articles + optional FX rates for the question."""
    q       = question.lower()
    sources: list[str] = []
    blocks:  list[str] = []

    # Primary Wikipedia search
    primary = _event_query(q) or question[:100]
    wiki1   = _wiki_fetch(primary)
    sources.append(f"search_wikipedia('{primary}')")
    blocks.append(f"## Wikipedia — {primary}\n{wiki1}")

    # Secondary search for deep-topic questions
    extra = _extra_query(q)
    if extra:
        wiki2 = _wiki_fetch(extra)
        sources.append(f"search_wikipedia('{extra}')")
        blocks.append(f"## Wikipedia — {extra}\n{wiki2}")

    # Exchange rates
    if _needs_rates(question):
        rates = _rates_fetch()
        sources.append("get_exchange_rates(CHF base) → open.er-api.com")
        blocks.append(f"## Live exchange rates (CHF base)\n{rates}")

    return "\n\n".join(blocks), sources


# ── Provider ───────────────────────────────────────────────────────────────────

def _provider() -> str | None:
    if os.getenv("GEMINI_API_KEY"): return "gemini"
    if os.getenv("GROQ_API_KEY"):   return "groq"
    return None

def is_available() -> bool:
    return _provider() is not None

def model_label() -> str:
    p = _provider()
    if p == "gemini": return GEMINI_MODEL
    if p == "groq":   return GROQ_MODEL
    return "none"


# ── LLM call ──────────────────────────────────────────────────────────────────

def _system(context: str) -> str:
    return (
        "You are a professional event intelligence assistant specialising in "
        "Geneva international events.\n\n"
        "Answer ONLY using the live data below. "
        "If the data doesn't fully answer the question, say so honestly. "
        "Answer in the user's language (French if they write French). "
        "Be concise — one paragraph max. Use **bold** for key numbers.\n\n"
        f"## Live data fetched for this question\n\n{context}"
    )


def _gemini(question: str, history: list[dict], system: str) -> str:
    key = os.getenv("GEMINI_API_KEY")
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{GEMINI_MODEL}:generateContent?key={key}")

    contents = []
    for m in history[-6:]:
        if m["role"] in ("user", "assistant") and m.get("content"):
            role = "model" if m["role"] == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": m["content"]}]})
    contents.append({"role": "user", "parts": [{"text": question}]})

    resp = _req.post(url, json={
        "system_instruction": {"parts": [{"text": system}]},
        "contents": contents,
        "generationConfig": {"maxOutputTokens": 400, "temperature": 0.2},
    }, timeout=25)
    resp.raise_for_status()

    parts = resp.json()["candidates"][0]["content"].get("parts", [])
    return "".join(p.get("text", "") for p in parts).strip()


def _groq(question: str, history: list[dict], system: str) -> str:
    from groq import Groq
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    messages = [{"role": "system", "content": system}]
    for m in history[-6:]:
        if m["role"] in ("user", "assistant") and m.get("content"):
            messages.append({"role": m["role"], "content": m["content"]})
    messages.append({"role": "user", "content": question})
    resp = client.chat.completions.create(
        model=GROQ_MODEL, messages=messages, max_tokens=400, temperature=0.2,
    )
    return resp.choices[0].message.content.strip()


# ── Public entry point ─────────────────────────────────────────────────────────

def ask(question: str, history: list[dict]) -> tuple[str, list[str]]:
    """
    Fetch live context from APIs, inject into LLM, return (response, sources).
    Nothing is hardcoded — data is always retrieved at call time.
    """
    context, sources = _build_context(question)
    system = _system(context)

    p = _provider()
    if p == "gemini":
        text = _gemini(question, history, system)
    elif p == "groq":
        text = _groq(question, history, system)
    else:
        raise RuntimeError("No LLM key configured.")

    return text, sources
