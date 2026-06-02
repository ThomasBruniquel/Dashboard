"""
Agentic LLM layer with real function calling.

Primary:  OpenRouter + Qwen3 (free, works on Streamlit Cloud)
Fallback: Groq + Llama-3.3-70b (free, function calling supported)
Both use the OpenAI SDK — same code, different base_url.

The LLM sees the tool list, decides which to call, we execute,
it synthesises. Nothing hardcoded — all data fetched at runtime.

Setup:
  Get a free OpenRouter key at https://openrouter.ai (no CC)
  Add to .env:  OPENROUTER_API_KEY=sk-or-...
"""

from __future__ import annotations
import os
import json
import requests as _req
import streamlit as st
from openai import OpenAI

# ── Models — fastest first, auto-fallback on 429 ──────────────────────────────
OPENROUTER_MODELS = [
    "meta-llama/llama-3.3-70b-instruct:free",       # fast, reliable function calling
    "google/gemma-4-31b-it:free",                    # good fallback
    "qwen/qwen3-next-80b-a3b-instruct:free",         # large, can be slow on free tier
]
OPENROUTER_MODEL = OPENROUTER_MODELS[0]   # shown in UI
GROQ_MODEL       = "llama-3.3-70b-versatile"
GEMINI_MODEL     = "gemini-2.5-flash-lite"

CALL_TIMEOUT = 25   # seconds per LLM call — avoids infinite hangs on slow models

SYSTEM = (
    "You are an F1 racing intelligence assistant with access to real-time data tools.\n"
    "ALWAYS use your tools to answer — never rely on training data for statistics or results.\n"
    "Answer in the user's language (French if they write French).\n"
    "Be concise: 2–4 sentences for simple questions. Use **bold** for key numbers.\n"
    "When a user mentions a race name (e.g. 'Monaco', 'Japan'), find its round number "
    "from the calendar tool first if you don't already know it."
)


# ── Tool definitions ───────────────────────────────────────────────────────────
TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "get_race_calendar",
            "description": "Get the complete F1 race calendar for a year: round numbers, race names, circuits, countries, dates.",
            "parameters": {
                "type": "object",
                "properties": {
                    "year": {"type": "integer", "description": "Season year, e.g. 2024"}
                },
                "required": ["year"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_race_results",
            "description": "Get the top-10 finishing order, times and points for a specific Grand Prix.",
            "parameters": {
                "type": "object",
                "properties": {
                    "year":  {"type": "integer"},
                    "round": {"type": "integer", "description": "Round number (1–24). Use get_race_calendar first if unsure."},
                },
                "required": ["year", "round"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_driver_standings",
            "description": "Get the Drivers' World Championship standings (points, wins) for a season.",
            "parameters": {
                "type": "object",
                "properties": {
                    "year": {"type": "integer"}
                },
                "required": ["year"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_constructor_standings",
            "description": "Get the Constructors' World Championship standings for a season.",
            "parameters": {
                "type": "object",
                "properties": {
                    "year": {"type": "integer"}
                },
                "required": ["year"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_exchange_rates",
            "description": "Get current live CHF exchange rates from open.er-api.com.",
            "parameters": {
                "type": "object",
                "properties": {
                    "currencies": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "ISO currency codes, e.g. ['USD', 'EUR', 'GBP', 'JPY']",
                    }
                },
                "required": ["currencies"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_wikipedia",
            "description": "Search Wikipedia for information about an F1 driver, team, circuit, or race.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query, e.g. 'Max Verstappen career'"}
                },
                "required": ["query"],
            },
        },
    },
]


# ── Tool execution ─────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def _jolpica(path: str) -> dict:
    resp = _req.get(f"https://api.jolpi.ca/ergast/f1/{path}",
                    params={"format": "json", "limit": 30}, timeout=15)
    resp.raise_for_status()
    return resp.json()["MRData"]


@st.cache_data(ttl=3600, show_spinner=False)
def _er_api() -> dict:
    return _req.get("https://open.er-api.com/v6/latest/CHF", timeout=10).json().get("rates", {})


@st.cache_data(ttl=3600, show_spinner=False)
def _wiki(query: str) -> str:
    headers = {"User-Agent": "F1Dashboard/1.0 (portfolio; python-requests)"}
    search  = _req.get("https://en.wikipedia.org/w/api.php",
                       params={"action": "query", "list": "search", "srsearch": query,
                               "srlimit": 1, "format": "json"},
                       headers=headers, timeout=10).json()
    results = search.get("query", {}).get("search", [])
    if not results:
        return "No Wikipedia result found."
    title = results[0]["title"]
    slug  = title.replace(" ", "_")
    resp  = _req.get(f"https://en.wikipedia.org/api/rest_v1/page/summary/{slug}",
                     headers=headers, timeout=10)
    if resp.status_code == 200:
        d = resp.json()
        return f"{title}\n{d.get('extract','')[:600]}\n{d.get('content_urls',{}).get('desktop',{}).get('page','')}"
    return f"Article '{title}' unavailable."


def _execute(name: str, args: dict) -> str:
    try:
        if name == "get_race_calendar":
            races = _jolpica(f"{args['year']}/races/")["RaceTable"]["Races"]
            return json.dumps([{
                "round":   r["round"],
                "name":    r["raceName"],
                "circuit": r["Circuit"]["circuitName"],
                "country": r["Circuit"]["Location"]["country"],
                "date":    r["date"],
            } for r in races])

        if name == "get_race_results":
            data = _jolpica(f"{args['year']}/{args['round']}/results/")["RaceTable"]["Races"]
            if not data:
                return "Results not available."
            race    = data[0]
            results = race.get("Results", [])
            return json.dumps({
                "race":    race["raceName"],
                "date":    race["date"],
                "circuit": race["Circuit"]["circuitName"],
                "results": [{
                    "pos":    r["position"],
                    "driver": f"{r['Driver']['givenName']} {r['Driver']['familyName']}",
                    "team":   r["Constructor"]["name"],
                    "time":   r.get("Time", {}).get("time", r.get("status", "—")),
                    "points": r.get("points", "0"),
                } for r in results[:10]],
            })

        if name == "get_driver_standings":
            lists = _jolpica(f"{args['year']}/driverstandings/")["StandingsTable"]["StandingsLists"]
            if not lists:
                return "Standings not available."
            return json.dumps([{
                "pos":    s["position"],
                "driver": f"{s['Driver']['givenName']} {s['Driver']['familyName']}",
                "team":   s["Constructors"][0]["name"],
                "points": s["points"],
                "wins":   s["wins"],
            } for s in lists[0]["DriverStandings"]])

        if name == "get_constructor_standings":
            lists = _jolpica(f"{args['year']}/constructorstandings/")["StandingsTable"]["StandingsLists"]
            if not lists:
                return "Standings not available."
            return json.dumps([{
                "pos":    s["position"],
                "team":   s["Constructor"]["name"],
                "points": s["points"],
                "wins":   s["wins"],
            } for s in lists[0]["ConstructorStandings"]])

        if name == "get_exchange_rates":
            all_rates = _er_api()
            rates     = {c: all_rates[c] for c in args.get("currencies", []) if c in all_rates}
            return json.dumps({"base": "CHF", "rates": rates})

        if name == "search_wikipedia":
            return _wiki(args.get("query", ""))

        return f"Unknown tool: {name}"

    except Exception as e:
        return f"Tool error: {e}"


# ── Provider ───────────────────────────────────────────────────────────────────

def _provider() -> str | None:
    if os.getenv("OPENROUTER_API_KEY"): return "openrouter"
    if os.getenv("GROQ_API_KEY"):       return "groq"
    if os.getenv("GEMINI_API_KEY"):     return "gemini"
    return None

def is_available() -> bool:
    return _provider() is not None

def model_label() -> str:
    p = _provider()
    if p == "openrouter": return f"Qwen3-30B (OpenRouter)"
    if p == "groq":       return f"Llama-3.3-70B (Groq)"
    if p == "gemini":     return f"{GEMINI_MODEL} (Gemini)"
    return "none"


def _openai_client(provider: str) -> OpenAI:
    """Create a fresh client each time — avoids caching a client with a missing key."""
    if provider == "openrouter":
        return OpenAI(
            api_key=os.getenv("OPENROUTER_API_KEY"),
            base_url="https://openrouter.ai/api/v1",
            timeout=CALL_TIMEOUT,
            default_headers={
                "HTTP-Referer": "https://f1-event-intelligence.streamlit.app",
                "X-Title":      "F1 Event Intelligence",
            },
        )
    if provider == "groq":
        return OpenAI(
            api_key=os.getenv("GROQ_API_KEY"),
            base_url="https://api.groq.com/openai/v1",
            timeout=CALL_TIMEOUT,
        )
    raise ValueError(f"Unknown provider: {provider}")


# ── Raw HTTP call (guaranteed timeout, no SDK issues) ─────────────────────────

def _openrouter_call(model: str, messages: list, tools: list | None = None) -> dict:
    """
    Direct requests call to OpenRouter — hard 15s timeout, no SDK wrapping.
    Returns the raw API response dict.
    """
    payload: dict = {
        "model":       model,
        "messages":    messages,
        "temperature": 0.1,
        "max_tokens":  400,
    }
    if tools:
        payload["tools"]       = tools
        payload["tool_choice"] = "auto"

    resp = _req.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}",
            "Content-Type":  "application/json",
            "HTTP-Referer":  "https://f1-event-intelligence.streamlit.app",
            "X-Title":       "F1 Event Intelligence",
        },
        json=payload,
        timeout=15,   # hard timeout — always respected by requests
    )
    resp.raise_for_status()
    return resp.json()


# ── Agentic loop ───────────────────────────────────────────────────────────────

def _function_calling_loop(question: str, history: list[dict], provider: str) -> tuple[str, list[str]]:
    model_candidates = OPENROUTER_MODELS if provider == "openrouter" else [GROQ_MODEL]

    messages: list[dict] = [{"role": "system", "content": SYSTEM}]
    for m in history[-6:]:
        if m["role"] in ("user", "assistant") and m.get("content"):
            messages.append({"role": m["role"], "content": m["content"]})
    messages.append({"role": "user", "content": question})

    tools_called: list[str] = []

    for candidate in model_candidates:
        msgs = list(messages)

        try:
            for _ in range(5):   # max 5 tool-call rounds
                if provider == "openrouter":
                    data   = _openrouter_call(candidate, msgs, TOOLS)
                    choice = data["choices"][0]
                    raw    = choice["message"]
                    # Normalise to simple dict
                    content    = raw.get("content") or ""
                    tool_calls = raw.get("tool_calls") or []
                    msgs.append(raw)   # append raw dict to history
                else:
                    # Groq via OpenAI SDK (fast, reliable)
                    client = _openai_client(provider)
                    resp   = client.chat.completions.create(
                        model=GROQ_MODEL, messages=msgs, tools=TOOLS,
                        tool_choice="auto", temperature=0.1, max_tokens=400,
                    )
                    sdk_msg    = resp.choices[0].message
                    content    = sdk_msg.content or ""
                    tool_calls = sdk_msg.tool_calls or []
                    msgs.append(sdk_msg)

                if not tool_calls:
                    return content.strip(), tools_called

                # Execute each tool call
                for tc in tool_calls:
                    if provider == "openrouter":
                        tc_id  = tc["id"]
                        name   = tc["function"]["name"]
                        args   = json.loads(tc["function"]["arguments"])
                    else:
                        tc_id  = tc.id
                        name   = tc.function.name
                        args   = json.loads(tc.function.arguments)

                    short_model = candidate.split("/")[-1][:18]
                    label  = f"{name}({json.dumps(args, ensure_ascii=False)[:50]}) [{short_model}]"
                    result = _execute(name, args)
                    tools_called.append(label)
                    msgs.append({"role": "tool", "tool_call_id": tc_id, "content": result})

            return "Trop d'appels d'outils — réessayez.", tools_called

        except _req.exceptions.Timeout:
            continue   # timeout → try next model
        except _req.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 429:
                continue   # rate-limited → try next model
            return f"Erreur réseau : {e}", tools_called
        except Exception as e:
            err = str(e)
            if "rate" in err.lower() or "429" in err or "timeout" in err.lower():
                continue
            return f"Erreur : {err[:120]}", tools_called

    return "Tous les modèles sont indisponibles — réessayez dans 30 s.", tools_called


def _gemini_rag(question: str, history: list[dict]) -> tuple[str, list[str]]:
    """Gemini fallback — pre-fetch context and inject (no native function calling)."""
    key  = os.getenv("GEMINI_API_KEY")
    url  = (f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{GEMINI_MODEL}:generateContent?key={key}")

    # Pre-fetch relevant data
    tools_called: list[str] = []
    context_parts: list[str] = []

    q = question.lower()
    if any(w in q for w in ["standing", "classement", "champion", "points", "winner", "vainqueur", "résultat", "result", "win", "gagn"]):
        dr = _jolpica("2024/driverstandings/")["StandingsTable"]["StandingsLists"]
        if dr:
            tools_called.append("get_driver_standings(2024)")
            context_parts.append("Driver standings 2024: " + json.dumps(
                [{"pos": s["position"], "driver": f"{s['Driver']['givenName']} {s['Driver']['familyName']}", "pts": s["points"]} for s in dr[0]["DriverStandings"][:5]]
            ))

    if any(w in q for w in ["race", "course", "grand prix", "monaco", "bahrain", "japan", "uk", "circuit"]):
        wiki_q = question[:80]
        context_parts.append("Wikipedia: " + _wiki(wiki_q))
        tools_called.append(f"search_wikipedia('{wiki_q[:50]}')")

    system = (SYSTEM + "\n\n## Live data\n" + "\n\n".join(context_parts)) if context_parts else SYSTEM

    contents = []
    for m in history[-6:]:
        if m["role"] in ("user", "assistant") and m.get("content"):
            contents.append({"role": "model" if m["role"] == "assistant" else "user",
                             "parts": [{"text": m["content"]}]})
    contents.append({"role": "user", "parts": [{"text": question}]})

    resp  = _req.post(url, json={
        "system_instruction": {"parts": [{"text": system}]},
        "contents": contents,
        "generationConfig": {"maxOutputTokens": 400, "temperature": 0.2},
    }, timeout=25)
    resp.raise_for_status()
    parts = resp.json()["candidates"][0]["content"].get("parts", [])
    return "".join(p.get("text", "") for p in parts).strip(), tools_called


# ── Public entry point ─────────────────────────────────────────────────────────

def ask(question: str, history: list[dict]) -> tuple[str, list[str]]:
    """Route to the best available provider and run the agentic loop."""
    p = _provider()
    if p in ("openrouter", "groq"):
        return _function_calling_loop(question, history, p)
    if p == "gemini":
        return _gemini_rag(question, history)
    raise RuntimeError("No LLM key configured.")
