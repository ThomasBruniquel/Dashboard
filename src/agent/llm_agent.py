"""
Streaming agent — RAG + streaming LLM synthesis.

Flow per question:
  1. Fetch relevant F1 data from Jolpica/Wikipedia (< 1s, keyword-based)
  2. Stream LLM synthesis from that context (visible progress, feels instant)

No function calling roundtrips — data is fetched before the LLM call.
Supports: OpenRouter (Llama/Gemma/Qwen3 free), Groq, Gemini.
"""

from __future__ import annotations
import os, json
from typing import Generator

import requests as _req
import streamlit as st

# ── Models ─────────────────────────────────────────────────────────────────────
OPENROUTER_MODELS = [
    "meta-llama/llama-3.3-70b-instruct:free",
    "google/gemma-4-31b-it:free",
    "qwen/qwen3-next-80b-a3b-instruct:free",
]
GROQ_MODEL   = "llama-3.3-70b-versatile"
GEMINI_MODEL = "gemini-2.5-flash-lite"

SYSTEM = (
    "You are an F1 racing intelligence assistant. "
    "Answer using ONLY the live F1 data provided below — never use training memory for stats. "
    "Answer in the user's language (French if they write French). "
    "Be concise: 2-4 sentences for simple questions. Bold key numbers."
)

CALL_TIMEOUT = 30


# ── Provider ───────────────────────────────────────────────────────────────────

def _provider() -> str | None:
    # Gemini first — most reliable for streaming on free tier
    # OpenRouter free models hit shared rate-limits too aggressively
    if os.getenv("GEMINI_API_KEY"):     return "gemini"
    if os.getenv("GROQ_API_KEY"):       return "groq"
    if os.getenv("OPENROUTER_API_KEY"): return "openrouter"
    return None

def is_available() -> bool:
    return _provider() is not None

def model_label() -> str:
    p = _provider()
    if p == "openrouter": return "Llama-3.3-70B (OpenRouter)"
    if p == "groq":       return "Llama-3.3-70B (Groq)"
    if p == "gemini":     return f"{GEMINI_MODEL} (Gemini)"
    return "none"


# ── Fast data fetchers (cached) ────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def _jolpica(path: str) -> dict:
    r = _req.get(f"https://api.jolpi.ca/ergast/f1/{path}",
                 params={"format": "json", "limit": 30}, timeout=10)
    r.raise_for_status()
    return r.json()["MRData"]


@st.cache_data(ttl=3600, show_spinner=False)
def _er_rates() -> dict:
    r = _req.get("https://open.er-api.com/v6/latest/CHF", timeout=10)
    return r.json().get("rates", {})


@st.cache_data(ttl=3600, show_spinner=False)
def _wiki_summary(query: str) -> str:
    headers = {"User-Agent": "F1Dashboard/1.0"}
    s = _req.get("https://en.wikipedia.org/w/api.php",
                 params={"action": "query", "list": "search", "srsearch": query,
                         "srlimit": 1, "format": "json"},
                 headers=headers, timeout=8).json()
    hits = s.get("query", {}).get("search", [])
    if not hits:
        return ""
    title = hits[0]["title"]
    r = _req.get(f"https://en.wikipedia.org/api/rest_v1/page/summary/{title.replace(' ','_')}",
                 headers=headers, timeout=8)
    if r.status_code == 200:
        return r.json().get("extract", "")[:500]
    return ""


# ── RAG: keyword-based context fetching ───────────────────────────────────────

_RACE_NAMES = {
    "bahrain": 1, "saudi": 2, "australian": 3, "japan": 4, "japanese": 4,
    "chinese": 5, "china": 5, "miami": 6, "emilia": 7, "romagna": 7,
    "monaco": 8, "canadian": 9, "canada": 9, "spanish": 10, "spain": 10,
    "austrian": 11, "austria": 11, "british": 12, "uk": 12, "hungarian": 13,
    "hungarian": 13, "belgium": 14, "belgian": 14, "dutch": 15,
    "netherlands": 15, "italian": 16, "italy": 16, "monza": 16,
    "azerbaijan": 17, "baku": 17, "singapore": 18, "united states": 19,
    "austin": 19, "mexico": 20, "brazil": 21, "sao paulo": 21,
    "las vegas": 22, "vegas": 22, "qatar": 23, "abu dhabi": 24,
}

_STANDINGS_KW = ("standing", "classement", "champion", "points", "leader",
                  "who leads", "qui mène", "qui est en tête")
_RESULT_KW    = ("winner", "vainqueur", "gagné", "won", "résultat", "result",
                  "podium", "finish", "first", "premier")
_CALENDAR_KW  = ("calendar", "calendrier", "schedule", "when", "quand",
                  "races", "courses", "date")
_CURRENCY_KW  = ("chf", "eur", "usd", "franc", "currency", "monnaie",
                  "taux", "rate", "convert")


def fetch_context(question: str) -> tuple[str, list[str]]:
    """
    Fetch relevant F1 data in < 1s.
    Base context (always): full race calendar + driver standings top 5.
    Additional: race results, constructor standings, FX, Wikipedia — if relevant.
    """
    q       = question.lower()
    parts:   list[str] = []
    sources: list[str] = []

    # ── Always: full race calendar (country, circuit, date, winner per race) ──
    # This answers location/date/venue questions in any language without keyword matching.
    try:
        races = _jolpica("2024/races/")["RaceTable"]["Races"]
        winners_raw = _jolpica("2024/results/1/")["RaceTable"]["Races"]
        winner_by_round = {
            int(r["round"]): f"{r['Results'][0]['Driver']['givenName']} {r['Results'][0]['Driver']['familyName']} ({r['Results'][0]['Constructor']['name']})"
            for r in winners_raw if r.get("Results")
        }
        calendar = [{
            "round":   r["round"],
            "name":    r["raceName"],
            "circuit": r["Circuit"]["circuitName"],
            "country": r["Circuit"]["Location"]["country"],
            "city":    r["Circuit"]["Location"]["locality"],
            "date":    r["date"],
            "winner":  winner_by_round.get(int(r["round"]), "TBD"),
        } for r in races]
        parts.append("2024 F1 Calendar (all 24 races with circuit, country, city, date, winner): "
                     + json.dumps(calendar))
        sources.append("Jolpica — race_calendar(2024) with winners")
    except Exception:
        pass

    # ── Always: driver standings top 5 ───────────────────────────────────────
    try:
        sl = _jolpica("2024/driverstandings/")["StandingsTable"]["StandingsLists"]
        if sl:
            top = sl[0]["DriverStandings"][:5]
            parts.append("2024 Driver Standings (top 5): " + json.dumps([{
                "pos":    s["position"],
                "driver": f"{s['Driver']['givenName']} {s['Driver']['familyName']}",
                "team":   s["Constructors"][0]["name"],
                "points": s["points"],
                "wins":   s["wins"],
            } for s in top]))
            sources.append("Jolpica — driver_standings(2024)")
    except Exception:
        pass

    # Constructor standings if relevant
    if any(w in q for w in ("constructor", "team", "constructeur", "équipe", "mclaren",
                             "ferrari", "red bull", "mercedes", "aston")):
        try:
            cl = _jolpica("2024/constructorstandings/")["StandingsTable"]["StandingsLists"]
            if cl:
                parts.append("2024 Constructor Standings: " + json.dumps([{
                    "pos":    s["position"],
                    "team":   s["Constructor"]["name"],
                    "points": s["points"],
                } for s in cl[0]["ConstructorStandings"]]))
                sources.append("Jolpica — constructor_standings(2024)")
        except Exception:
            pass

    # Race-specific results
    for kw, rnd in _RACE_NAMES.items():
        if kw in q:
            try:
                races = _jolpica(f"2024/{rnd}/results/")["RaceTable"]["Races"]
                if races:
                    res = races[0]["Results"][:10]
                    parts.append(f"Round {rnd} — {races[0]['raceName']} results: " + json.dumps([{
                        "pos":    r["position"],
                        "driver": f"{r['Driver']['givenName']} {r['Driver']['familyName']}",
                        "team":   r["Constructor"]["name"],
                        "time":   r.get("Time", {}).get("time", r.get("status", "")),
                        "points": r.get("points", "0"),
                    } for r in res]))
                    sources.append(f"Jolpica — race_results(2024, round={rnd})")
            except Exception:
                pass
            break

    # (calendar already in base context above)

    # Exchange rates
    if any(w in q for w in _CURRENCY_KW):
        try:
            rates = _er_rates()
            subset = {c: rates[c] for c in ("EUR", "USD", "GBP", "JPY", "AED", "QAR") if c in rates}
            parts.append("Live CHF rates: " + json.dumps(subset))
            sources.append("open.er-api.com — exchange_rates(CHF)")
        except Exception:
            pass

    # Wikipedia for biographical/circuit questions
    if any(w in q for w in ("who is", "qui est", "circuit", "pilote", "driver",
                              "histoire", "history", "career", "carrière", "biograph")):
        try:
            wiki = _wiki_summary(question[:80])
            if wiki:
                parts.append("Wikipedia: " + wiki)
                sources.append(f"Wikipedia — search('{question[:40]}')")
        except Exception:
            pass

    ctx = "\n\n".join(parts) if parts else "No specific F1 data retrieved for this question."
    return ctx, sources


# ── Streaming LLM calls ────────────────────────────────────────────────────────

def _stream_openrouter(messages: list) -> Generator[str, None, None]:
    """Stream from OpenRouter — tries models in order on 429."""
    for model in OPENROUTER_MODELS:
        try:
            with _req.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}",
                    "Content-Type":  "application/json",
                    "HTTP-Referer":  "https://f1-event-intelligence.streamlit.app",
                    "X-Title":       "F1 Event Intelligence",
                },
                json={
                    "model":       model,
                    "messages":    messages,
                    "stream":      True,
                    "temperature": 0.1,
                    "max_tokens":  400,
                },
                stream=True,
                timeout=CALL_TIMEOUT,
            ) as resp:
                if resp.status_code == 429:
                    continue
                resp.raise_for_status()
                for raw in resp.iter_lines():
                    if not raw:
                        continue
                    line = raw.decode("utf-8") if isinstance(raw, bytes) else raw
                    if line == "data: [DONE]":
                        return
                    if line.startswith("data: "):
                        try:
                            chunk = json.loads(line[6:])
                            content = chunk["choices"][0]["delta"].get("content") or ""
                            if content:
                                yield content
                        except Exception:
                            continue
                return   # streamed successfully

        except (_req.exceptions.Timeout, _req.exceptions.ConnectionError):
            continue
        except _req.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 429:
                continue
            yield f"Erreur réseau : {e}"
            return

    yield "Tous les modèles OpenRouter sont indisponibles — réessayez dans 30 s."


def _stream_groq(messages: list) -> Generator[str, None, None]:
    from openai import OpenAI
    client = OpenAI(api_key=os.getenv("GROQ_API_KEY"),
                    base_url="https://api.groq.com/openai/v1", timeout=CALL_TIMEOUT)
    with client.chat.completions.stream(
        model=GROQ_MODEL, messages=messages, temperature=0.1, max_tokens=400
    ) as stream:
        for chunk in stream.text_stream:
            yield chunk


def _stream_gemini(messages: list) -> Generator[str, None, None]:
    """Real streaming from Gemini via SSE (streamGenerateContent)."""
    key         = os.getenv("GEMINI_API_KEY")
    system_text = next((m["content"] for m in messages if m["role"] == "system"), "")
    contents    = [
        {"role": "model" if m["role"] == "assistant" else "user",
         "parts": [{"text": m["content"]}]}
        for m in messages if m["role"] in ("user", "assistant") and m.get("content")
    ]
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{GEMINI_MODEL}:streamGenerateContent?alt=sse&key={key}")
    with _req.post(
        url,
        json={
            "system_instruction": {"parts": [{"text": system_text}]},
            "contents":           contents,
            "generationConfig":   {"maxOutputTokens": 400, "temperature": 0.1},
        },
        stream=True,
        timeout=CALL_TIMEOUT,
    ) as resp:
        resp.raise_for_status()
        for raw in resp.iter_lines():
            if not raw:
                continue
            line = raw.decode("utf-8") if isinstance(raw, bytes) else raw
            if not line.startswith("data: "):
                continue
            try:
                chunk = json.loads(line[6:])
                parts = chunk["candidates"][0]["content"].get("parts", [])
                text  = "".join(p.get("text", "") for p in parts)
                if text:
                    yield text
            except Exception:
                continue


# ── Public streaming entry point ───────────────────────────────────────────────

def ask_streaming(question: str, history: list[dict]) -> tuple[Generator[str, None, None], list[str]]:
    """
    Fetch live F1 context (< 1s), then stream the LLM synthesis.
    Returns (text_chunk_generator, list_of_sources).
    Call this with st.write_stream(generator).
    """
    ctx, sources = fetch_context(question)

    messages = [{
        "role":    "system",
        "content": f"{SYSTEM}\n\n## Live F1 data (fetched now, not from training)\n\n{ctx}",
    }]
    for m in history[-6:]:
        if m["role"] in ("user", "assistant") and m.get("content"):
            messages.append({"role": m["role"], "content": m["content"]})
    messages.append({"role": "user", "content": question})

    p = _provider()
    if p == "openrouter":
        gen = _stream_openrouter(messages)
    elif p == "groq":
        gen = _stream_groq(messages)
    elif p == "gemini":
        gen = _stream_gemini(messages)
    else:
        def _no_key():
            yield "Aucune clé LLM configurée. Ajoutez `OPENROUTER_API_KEY` dans `.env`."
        gen = _no_key()

    return gen, sources


# ── Non-streaming fallback (kept for compatibility) ────────────────────────────

def ask(question: str, history: list[dict]) -> tuple[str, list[str]]:
    """Non-streaming version — collects full response then returns."""
    gen, sources = ask_streaming(question, history)
    return "".join(gen), sources
