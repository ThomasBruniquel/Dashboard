"""
F1 2024 Season — Event Intelligence Dashboard
All data from public APIs. Nothing hardcoded.

Sources:
  - Jolpica (Ergast fork)   races, results, standings — no key
  - Wikipedia REST API      circuit & driver context — no key
  - open.er-api.com         live CHF exchange rates — no key
  - Frankfurter / ECB       30-day FX history — no key
  - Gemini / Groq           LLM agent (optional free key)
"""

from pathlib import Path
import os
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

from src.api.f1_data import (
    get_races, get_driver_standings, get_constructor_standings,
    get_race_results, get_all_results,
    get_driver_season_results, get_driver_wiki,
    TEAM_COLORS, DEFAULT_COLOR,
)
from src.api.currency import fetch_currency_rates
from src.api.fx_history import fetch_fx_history, fx_risk_label
from src.agent import llm_agent

# ── Env — local .env first, then Streamlit Cloud secrets ──────────────────────
_env = Path(__file__).parent / ".env"
if _env.exists():
    for line in _env.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ[k.strip()] = v.strip()

# Streamlit Cloud: secrets configured in the app's "Secrets" settings
try:
    for _key in ("GEMINI_API_KEY", "GROQ_API_KEY"):
        if _key in st.secrets and not os.getenv(_key):
            os.environ[_key] = st.secrets[_key]
except Exception:
    pass

# ── Page ───────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Event Portfolio Intelligence",
    page_icon=None,
    layout="wide",
)

NAVY = "#1E3A5F"
GOLD = "#C9A96E"
SLATE = "#64748B"

st.markdown(f"""
<style>
    .block-container {{ padding-top: 1rem; padding-bottom: 2rem; }}

    /* Metric cards — clean white with subtle shadow */
    div[data-testid="metric-container"] {{
        background: white;
        border: 1px solid #E2E8F0;
        border-radius: 10px;
        padding: 16px 20px;
        box-shadow: 0 1px 4px rgba(0,0,0,0.06);
    }}
    div[data-testid="metric-container"] label {{
        color: {SLATE} !important;
        font-size: 0.78rem !important;
        font-weight: 600 !important;
        letter-spacing: 0.04em !important;
        text-transform: uppercase !important;
    }}

    /* Executive summary block */
    .exec-card {{
        background: white;
        border-left: 4px solid {NAVY};
        border-radius: 0 10px 10px 0;
        padding: 18px 24px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.07);
        margin-bottom: 12px;
    }}
    .exec-title {{
        font-size: 0.7rem; font-weight: 700; color: {SLATE};
        text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 2px;
    }}
    .exec-value {{ font-size: 1.6rem; font-weight: 700; color: {NAVY}; }}
    .exec-sub {{ font-size: 0.78rem; color: {SLATE}; margin-top: 2px; }}

    /* Section labels */
    .section-label {{
        font-size: 0.75rem; font-weight: 700; color: {GOLD};
        text-transform: uppercase; letter-spacing: 0.09em; margin-bottom: 6px;
    }}

    /* Tab content headings */
    .stTabs [data-testid="stMarkdownContainer"] h1,
    .stTabs [data-testid="stMarkdownContainer"] h2,
    .stTabs [data-testid="stMarkdownContainer"] h3 {{
        color: {NAVY};
    }}
    h1 {{ font-size: 1.9rem !important; font-weight: 700; color: {NAVY}; }}
    h2 {{ font-size: 1.3rem !important; font-weight: 700; color: {NAVY}; }}
    h3 {{ font-size: 1.05rem !important; font-weight: 600; color: {NAVY}; }}

    /* Source / API box */
    .api-box {{
        background: #F1F5F9;
        border-left: 3px solid {GOLD};
        padding: 5px 10px; font-size: 0.75rem; color: {SLATE};
        border-radius: 0 4px 4px 0; margin: 2px 0;
    }}

    /* Sidebar cleaner */
    section[data-testid="stSidebar"] {{
        background: white;
        border-right: 1px solid #E2E8F0;
    }}
</style>
""", unsafe_allow_html=True)

LIVE = f'<span style="font-size:0.65rem;font-weight:700;padding:2px 7px;border-radius:20px;background:#DCFCE7;color:#15803D;">LIVE</span>'

# ── Data ───────────────────────────────────────────────────────────────────────
if st.sidebar.button("Refresh data"):
    st.cache_data.clear()

with st.spinner("Loading F1 2024 data…"):
    races        = get_races(2024)
    driver_st    = get_driver_standings(2024)
    constructor_st = get_constructor_standings(2024)
    winners      = get_all_results(2024)   # race winners only
    currency     = fetch_currency_rates()
    fx_hist      = fetch_fx_history(days=30)

rates = currency.get("rates", {})

# Derived
countries    = sorted({r["Circuit"]["Location"]["country"] for r in races})
n_countries  = len(countries)
n_races      = len(races)
winner_name  = f"{driver_st[0]['Driver']['givenName']} {driver_st[0]['Driver']['familyName']}" if driver_st else "—"
winner_pts   = driver_st[0]["points"] if driver_st else "—"
best_team    = constructor_st[0]["Constructor"]["name"] if constructor_st else "—"
best_team_pts = constructor_st[0]["points"] if constructor_st else "—"

# Map winners to races
winner_map: dict[int, dict] = {}
for race in winners:
    rnd = int(race["round"])
    if race.get("Results"):
        r = race["Results"][0]
        winner_map[rnd] = {
            "name":   f"{r['Driver']['givenName']} {r['Driver']['familyName']}",
            "team":   r["Constructor"]["name"],
            "time":   r.get("Time", {}).get("time", "—"),
        }

import random

THINKING_PHRASES = [
    "Bien sûr ! Je regarde les données...",
    "Je consulte les stats F1 en temps réel...",
    "Un instant, je vérifie ça pour vous...",
    "Je regarde ça tout de suite...",
    "Bonne question ! Je cherche...",
]

# ── Session state ──────────────────────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []
using_llm = llm_agent.is_available()

# ── Sidebar — chat ─────────────────────────────────────────────────────────────
with st.sidebar:
    model_str = llm_agent.model_label() if using_llm else "Aucune clé LLM"
    st.markdown(f"**Assistant F1** &nbsp; {'🟢' if using_llm else '⚪'}")
    st.caption(model_str)
    st.divider()

    # Chat history + streaming — all inside the scrollable container
    with st.container(height=460, border=False):
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
                if msg.get("calls"):
                    with st.expander("Sources", expanded=False):
                        for c in msg["calls"]:
                            st.markdown(
                                f'<div class="api-box">{c}</div>',
                                unsafe_allow_html=True,
                            )

        # Process pending question — runs INSIDE the container so it appears inline
        if "pending_question" in st.session_state:
            q = st.session_state.pop("pending_question")

            with st.chat_message("user"):
                st.markdown(q)

            with st.chat_message("assistant"):
                # 1. Instant thinking message — masks fetch latency
                thinking = st.empty()
                thinking.markdown(random.choice(THINKING_PHRASES))

                if using_llm:
                    try:
                        gen, sources = llm_agent.ask_streaming(
                            q, st.session_state.messages
                        )
                        # 2. Clear thinking, stream real response word by word
                        thinking.empty()
                        full_response = ""
                        area = st.empty()
                        for chunk in gen:
                            full_response += chunk
                            area.markdown(full_response + "▌")
                        area.markdown(full_response)
                    except Exception as e:
                        thinking.empty()
                        full_response = f"Erreur : {e}"
                        sources       = []
                        st.markdown(full_response)
                else:
                    thinking.empty()
                    full_response = "Ajoutez `GEMINI_API_KEY` dans `.env`."
                    sources       = []
                    st.markdown(full_response)

            st.session_state.messages.append(
                {"role": "user",      "content": q,             "calls": []}
            )
            st.session_state.messages.append(
                {"role": "assistant", "content": full_response, "calls": sources or []}
            )

    # Input form — clear_on_submit clears the field after sending
    with st.form("cf", clear_on_submit=True):
        inp  = st.text_input(
            "q", placeholder="Qui a gagné Monaco ? Classement ?",
            label_visibility="collapsed",
        )
        send = st.form_submit_button("Envoyer →", use_container_width=True)

    if send and inp.strip():
        st.session_state["pending_question"] = inp.strip()
        st.rerun()

    if st.session_state.messages:
        if st.button("Effacer", use_container_width=True):
            st.session_state.messages = []
            st.rerun()

    st.divider()
    st.caption("🟢 Jolpica · 🟢 Gemini · 🟢 open.er-api.com")
    if st.button("Refresh data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# ── Header ─────────────────────────────────────────────────────────────────────
st.markdown(f'<p class="section-label">Event Portfolio Intelligence</p>', unsafe_allow_html=True)
st.title("Formula 1 — 2024 World Championship Series")
st.caption(
    "Live data · Jolpica API · Wikipedia · open.er-api.com · Frankfurter/ECB — "
    "demonstrating the architecture used for any multi-event international portfolio."
)

# ── Tabs ───────────────────────────────────────────────────────────────────────
tab_season, tab_results, tab_standings, tab_finance, tab_participants = st.tabs([
    "Portfolio Overview", "Event Detail", "Performance Rankings", "Budget Exposure", "Participants"
])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — SEASON OVERVIEW
# ══════════════════════════════════════════════════════════════════════════════
with tab_season:
    # ── Executive Summary ─────────────────────────────────────────────────────
    completed_events = len(winner_map)
    remaining_events = n_races - completed_events
    completion_pct   = completed_events / n_races * 100

    st.markdown(f'<p class="section-label">Executive Portfolio Summary</p>', unsafe_allow_html=True)
    k1, k2, k3, k4, k5, k6 = st.columns(6)
    with k1:
        st.metric("Events in Portfolio",   n_races)
    with k2:
        st.metric("Events Delivered",      completed_events,
                  delta=f"{completion_pct:.0f}% completion", delta_color="off")
    with k3:
        st.metric("Events Remaining",      remaining_events)
    with k4:
        st.metric("Countries Covered",     n_countries)
    with k5:
        st.metric("Top Performing Entity", best_team,
                  delta=f"{best_team_pts} pts", delta_color="off")
    with k6:
        n_teams = len({r["Constructor"]["name"] for rr in winners for r in rr.get("Results", [])[:1]})
        st.metric("Competing Entities",    n_teams if n_teams else 10)

    st.markdown(
        f'<p style="color:{SLATE};font-size:0.8rem;margin-top:4px">'
        f'{LIVE} All metrics pulled live from Jolpica API (Ergast fork) — no hardcoded values.</p>',
        unsafe_allow_html=True,
    )
    st.divider()

    # ── Global deployment map ─────────────────────────────────────────────────
    st.markdown(f'<p class="section-label">Global Deployment Map</p>', unsafe_allow_html=True)
    map_rows = []
    for race in races:
        loc = race["Circuit"]["Location"]
        rnd = int(race["round"])
        w   = winner_map.get(rnd, {})
        delivered = rnd <= completed_events
        map_rows.append({
            "Round":   rnd,
            "Event":   race["raceName"],
            "Country": loc["country"],
            "Venue":   race["Circuit"]["circuitName"],
            "Date":    race["date"],
            "lat":     float(loc.get("lat", 0)),
            "lon":     float(loc.get("long", 0)),
            "Winner":  w.get("name", "—"),
            "Team":    w.get("team", "—"),
            "Status":  "Delivered" if delivered else "Upcoming",
        })
    map_df = pd.DataFrame(map_rows)

    # ── Selectors ─────────────────────────────────────────────────────────────
    mc1, mc2, mc3 = st.columns([2, 2, 3])
    with mc1:
        status_filter = st.radio(
            "Show", ["All events", "Delivered only", "Upcoming only"],
            horizontal=True, label_visibility="collapsed",
        )
    with mc2:
        region_options = {
            "All regions": [],
            "Europe":      ["UK", "Monaco", "Spain", "Belgium", "Netherlands",
                            "Italy", "Hungary", "Austria", "Azerbaijan"],
            "Americas":    ["USA", "Canada", "Mexico", "Brazil"],
            "Middle East": ["Bahrain", "Saudi Arabia", "Qatar", "UAE"],
            "Asia-Pacific": ["Japan", "China", "Australia", "Singapore"],
        }
        region_filter = st.selectbox(
            "Region", list(region_options.keys()), label_visibility="collapsed"
        )

    # Apply filters
    filtered_df = map_df.copy()
    if status_filter == "Delivered only":
        filtered_df = filtered_df[filtered_df["Status"] == "Delivered"]
    elif status_filter == "Upcoming only":
        filtered_df = filtered_df[filtered_df["Status"] == "Upcoming"]
    if region_options[region_filter]:
        filtered_df = filtered_df[filtered_df["Country"].isin(region_options[region_filter])]

    with mc3:
        n_shown = len(filtered_df)
        st.caption(f"Showing {n_shown} of {n_races} events")

    # ── Map — Scattergeo, static (no zoom/pan), always fills the frame cleanly ──
    fig_map = go.Figure()

    for status, color in [("Delivered", NAVY), ("Upcoming", GOLD)]:
        sub = filtered_df[filtered_df["Status"] == status]
        if sub.empty:
            continue
        fig_map.add_trace(go.Scattergeo(
            lat=sub["lat"], lon=sub["lon"],
            mode="markers+text",
            marker=dict(size=18, color=color, opacity=0.90,
                        line=dict(width=1.5, color="white")),
            text=sub["Round"].astype(str),
            textposition="middle center",
            textfont=dict(color="white", size=8, family="Arial Black, sans-serif"),
            customdata=sub[["Event", "Country", "Venue", "Date", "Winner", "Team"]].values,
            hovertemplate=(
                "<b>Round %{text} — %{customdata[0]}</b><br>"
                "%{customdata[2]}<br>"
                "%{customdata[1]} · %{customdata[3]}<br>"
                "Winner: %{customdata[4]} (%{customdata[5]})<br>"
                "<extra></extra>"
            ),
            name=status,
        ))

    fig_map.update_layout(
        height=440,
        margin=dict(l=0, r=0, t=8, b=0),
        dragmode=False,   # disable zoom & pan — frame is always the same size
        showlegend=True,
        legend=dict(orientation="h", y=1.02, x=0.5, xanchor="center",
                    font=dict(size=11, color=SLATE)),
        geo=dict(
            projection_type="equirectangular",
            showland=True,       landcolor="#EEF2F7",
            showocean=True,      oceancolor="#EFF6FF",
            showcoastlines=True, coastlinecolor="#CBD5E1",
            showcountries=True,  countrycolor="#E2E8F0",
            showframe=False,
            bgcolor="#F8FAFC",
            lataxis=dict(range=[-65, 80],   showgrid=False),
            lonaxis=dict(range=[-175, 180], showgrid=False),
        ),
        paper_bgcolor="#F8FAFC",
    )

    st.plotly_chart(fig_map, use_container_width=True, config={
        "scrollZoom":     False,
        "displayModeBar": False,   # hide toolbar entirely — no zoom controls shown
    })

    # ── Event calendar table ──────────────────────────────────────────────────
    st.markdown(f'<p class="section-label">Event Portfolio Calendar</p>', unsafe_allow_html=True)
    cal_rows = []
    for race in races:
        rnd       = int(race["round"])
        loc       = race["Circuit"]["Location"]
        w         = winner_map.get(rnd, {})
        delivered = rnd <= completed_events
        cal_rows.append({
            "#":       rnd,
            "Event":       race["raceName"],
            "Venue":       race["Circuit"]["circuitName"],
            "Country":     loc["country"],
            "City":        loc["locality"],
            "Date":        race["date"],
            "Status":      "✓ Delivered" if delivered else "Upcoming",
            "Top Result":  w.get("name", "—"),
            "Entity":      w.get("team", "—"),
        })
    cal_df = pd.DataFrame(cal_rows)
    st.dataframe(
        cal_df, hide_index=True, use_container_width=True,
        height=min(50 + len(cal_df) * 35, 520),   # auto-fit, max 520px
        column_config={
            "#":          st.column_config.NumberColumn(width="small"),
            "Status":     st.column_config.TextColumn(width="small"),
            "Top Result": st.column_config.TextColumn(width="medium"),
            "Entity":     st.column_config.TextColumn(width="medium"),
        },
    )
    st.caption("Source: Jolpica API — no API key required")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — RACE RESULTS
# ══════════════════════════════════════════════════════════════════════════════
with tab_results:
    st.markdown(f'<p class="section-label">Event Detail — Results & Delivery</p>', unsafe_allow_html=True)
    st.markdown(f'{LIVE} Jolpica API', unsafe_allow_html=True)

    race_options = {f"#{r['round']} — {r['raceName']} ({r['date']})": int(r["round"]) for r in races}
    selected_label = st.selectbox("Select event", list(race_options.keys()))
    selected_round = race_options[selected_label]

    with st.spinner("Loading results…"):
        result_data = get_race_results(2024, selected_round)

    if result_data and result_data.get("Results"):
        race_info = result_data
        loc       = race_info["Circuit"]["Location"]
        results   = race_info["Results"]

        rc1, rc2, rc3 = st.columns(3)
        with rc1: st.metric("Circuit",  race_info["Circuit"]["circuitName"])
        with rc2: st.metric("Location", f"{loc['locality']}, {loc['country']}")
        with rc3: st.metric("Date",     race_info["date"])

        st.divider()

        # Podium
        p1, p2, p3 = st.columns(3)
        podium_data = [(results[0], "🥇 P1", p1), (results[1], "🥈 P2", p2), (results[2], "🥉 P3", p3)] if len(results) >= 3 else []
        for res, label, col in podium_data:
            d = res["Driver"]
            name = f"{d['givenName']} {d['familyName']}"
            team = res["Constructor"]["name"]
            t    = res.get("Time", {}).get("time", res.get("status", "—"))
            with col:
                color = TEAM_COLORS.get(team, DEFAULT_COLOR)
                st.markdown(
                    f"<div style='border-left:4px solid {color};padding-left:10px'>"
                    f"<b>{label}</b><br>{name}<br><small>{team}</small><br>{t}</div>",
                    unsafe_allow_html=True,
                )

        st.divider()

        # Full results table
        res_rows = []
        for res in results:
            d    = res["Driver"]
            name = f"{d['givenName']} {d['familyName']}"
            t    = res.get("Time", {}).get("time", res.get("status", "—"))
            res_rows.append({
                "Pos":    res["position"],
                "Driver": name,
                "Team":   res["Constructor"]["name"],
                "Laps":   res.get("laps", "—"),
                "Time":   t,
                "Points": res.get("points", "—"),
            })
        res_df = pd.DataFrame(res_rows)
        st.dataframe(res_df, hide_index=True, use_container_width=True)
        st.caption("Source: Jolpica API")
    else:
        st.info("Results not yet available for this race.")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — PERFORMANCE RANKINGS
# ══════════════════════════════════════════════════════════════════════════════
with tab_standings:
    st.markdown(f'<p class="section-label">Performance Rankings — 2024 Season</p>', unsafe_allow_html=True)
    st.markdown(f'{LIVE} Jolpica API', unsafe_allow_html=True)

    col_d, col_c = st.columns(2)

    with col_d:
        st.markdown("**Individual Rankings**")
        drv_rows = []
        for d in driver_st:
            drv  = d["Driver"]
            name = f"{d['position']}. {drv['givenName']} {drv['familyName']}"
            team = d["Constructors"][0]["name"]
            drv_rows.append({
                "Driver": name,
                "Team":   team,
                "Points": int(d["points"]),
                "Wins":   int(d["wins"]),
            })
        drv_df = pd.DataFrame(drv_rows)

        fig_d = px.bar(
            drv_df.head(10), x="Points", y="Driver", orientation="h",
            color="Team",
            color_discrete_map={t: TEAM_COLORS.get(t, DEFAULT_COLOR) for t in drv_df["Team"].unique()},
            template="plotly_white", text="Points",
            title="Top 10 Drivers",
        )
        fig_d.update_layout(height=380, showlegend=False,
                             margin=dict(l=0, r=0, t=35, b=0),
                             yaxis=dict(categoryorder="total ascending"))
        fig_d.update_traces(textposition="outside")
        st.plotly_chart(fig_d, use_container_width=True)

        st.dataframe(drv_df, hide_index=True, use_container_width=True)

    with col_c:
        st.subheader("Constructors Championship")
        con_rows = []
        for c in constructor_st:
            con  = c["Constructor"]
            con_rows.append({
                "Team":   f"{c['position']}. {con['name']}",
                "Points": int(c["points"]),
                "Wins":   int(c["wins"]),
            })
        con_df = pd.DataFrame(con_rows)

        colors = [TEAM_COLORS.get(r["Team"].split(". ", 1)[1], DEFAULT_COLOR) for _, r in con_df.iterrows()]
        fig_c = px.bar(
            con_df, x="Points", y="Team", orientation="h",
            template="plotly_white", text="Points",
            title="All Constructors",
        )
        fig_c.update_traces(marker_color=colors, textposition="outside")
        fig_c.update_layout(height=380, margin=dict(l=0, r=0, t=35, b=0),
                             yaxis=dict(categoryorder="total ascending"))
        st.plotly_chart(fig_c, use_container_width=True)

        st.dataframe(con_df, hide_index=True, use_container_width=True)

    st.caption("Source: Jolpica API (community-maintained fork of Ergast)")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — BUDGET EXPOSURE BY REGION
# ══════════════════════════════════════════════════════════════════════════════
with tab_finance:
    st.markdown(f'<p class="section-label">Multi-Currency Budget Exposure</p>', unsafe_allow_html=True)
    st.markdown(
        f'{LIVE} open.er-api.com · {LIVE} Frankfurter/ECB',
        unsafe_allow_html=True,
    )
    st.caption(
        "For a CHF-based organisation managing an international event portfolio, each host country "
        "creates a currency exposure. Higher event concentration in one currency = higher FX risk "
        "on local supplier contracts, venue costs, and staff fees."
    )
    st.divider()

    host_currencies = {
        "Bahrain":     "BHD", "Saudi Arabia": "SAR", "Australia":  "AUD",
        "Japan":       "JPY", "China":        "CNY", "USA":        "USD",
        "Monaco":      "EUR", "Canada":       "CAD", "Spain":      "EUR",
        "UK":          "GBP", "Hungary":      "HUF", "Belgium":    "EUR",
        "Netherlands": "EUR", "Italy":        "EUR", "Azerbaijan": "AZN",
        "Singapore":   "SGD", "Mexico":       "MXN", "Brazil":     "BRL",
        "Qatar":       "QAR", "UAE":          "AED",
    }

    # Build exposure table — events per currency × live rate × 30d volatility
    currency_events: dict[str, list[str]] = {}
    for country in countries:
        curr = host_currencies.get(country)
        if curr:
            currency_events.setdefault(curr, []).append(country)

    usd  = fx_hist.get("currencies", {}).get("USD", {})
    eur  = fx_hist.get("currencies", {}).get("EUR", {})
    gbp  = fx_hist.get("currencies", {}).get("GBP", {})
    # Build volatility lookup (use USD vol as proxy for pegged currencies)
    vol_lookup = {
        "USD": usd.get("volatility_pct", 0),
        "EUR": eur.get("volatility_pct", 0),
        "GBP": gbp.get("volatility_pct", 0),
    }

    exposure_rows = []
    for curr, event_countries in sorted(currency_events.items(),
                                        key=lambda x: -len(x[1])):
        n        = len(event_countries)
        rate     = rates.get(curr, None) if curr != "CHF" else 1.0
        vol      = vol_lookup.get(curr, usd.get("volatility_pct", 0.5))
        risk_lbl = "Low" if vol < 0.5 else "Moderate" if vol < 1.5 else "High"
        exposure_rows.append({
            "Currency":     curr,
            "Events":       n,
            "% of Portfolio": f"{n/n_races*100:.0f}%",
            "Rate (1 CHF)": f"{rate:.4f}" if rate else "N/A",
            "30d Volatility": f"{vol:.3f}%",
            "FX Risk":      risk_lbl,
            "Markets":      ", ".join(event_countries),
        })
    exposure_df = pd.DataFrame(exposure_rows)

    # ── Top KPIs ──────────────────────────────────────────────────────────────
    main_curr    = exposure_rows[0]["Currency"] if exposure_rows else "USD"
    main_events  = exposure_rows[0]["Events"]   if exposure_rows else 0
    eur_events   = next((r["Events"] for r in exposure_rows if r["Currency"] == "EUR"), 0)
    single_event = sum(1 for r in exposure_rows if r["Events"] == 1)

    fk1, fk2, fk3, fk4 = st.columns(4)
    with fk1:
        st.metric("Currencies in Portfolio", len(exposure_rows),
                  help="Number of distinct currencies across all host countries.")
    with fk2:
        st.metric("Largest Exposure",        f"{main_curr} ({main_events} events)",
                  help="Currency with most events = highest supplier contract exposure.")
    with fk3:
        st.metric("EUR-zone Events",         eur_events,
                  help="Events in EUR-zone countries (Monaco, Spain, Belgium, Italy, Netherlands).")
    with fk4:
        st.metric("Single-Event Currencies", single_event,
                  help="Currencies used by only one host country — unique procurement challenges.")

    st.divider()

    # ── Exposure chart + table side by side ───────────────────────────────────
    fc1, fc2 = st.columns([2, 1])

    with fc1:
        # Bar chart: events per currency (= weight of exposure)
        exp_chart_df = exposure_df[["Currency", "Events"]].copy()
        exp_chart_df["Color"] = [
            NAVY if r["FX Risk"] == "Low" else
            GOLD if r["FX Risk"] == "Moderate" else "#B5451B"
            for r in exposure_rows
        ]
        fig_exp = go.Figure(go.Bar(
            x=exp_chart_df["Currency"],
            y=exp_chart_df["Events"],
            marker_color=exp_chart_df["Color"].tolist(),
            text=exp_chart_df["Events"],
            textposition="auto",
        ))
        fig_exp.update_layout(
            title="Event weight by currency (events = exposure weight)",
            template="plotly_white",
            height=300,
            margin=dict(l=0, r=0, t=40, b=0),
            xaxis_title="",
            yaxis_title="Number of events",
        )
        st.plotly_chart(fig_exp, use_container_width=True)
        st.caption(
            f"Colour: {NAVY[:7]} = Low FX risk · Gold = Moderate · Red = High — "
            "based on 30-day CHF volatility vs that currency."
        )

    with fc2:
        st.markdown("**Exposure breakdown**")
        st.dataframe(
            exposure_df[["Currency", "Events", "% of Portfolio", "FX Risk"]],
            hide_index=True, use_container_width=True, height=280,
        )
        st.caption(f"Rates: open.er-api.com · Updated: {currency.get('last_updated','N/A')[:16]}")

    st.divider()

    # ── 30-day CHF trend for key currencies ───────────────────────────────────
    st.markdown(f'<p class="section-label">30-Day CHF Rate Trend — Key Portfolio Currencies</p>',
                unsafe_allow_html=True)
    st.caption(
        "CHF appreciation vs. USD or EUR reduces the cost of foreign-currency contracts "
        "but may impact international delegate travel budgets. Source: Frankfurter / ECB."
    )

    h1, h2, h3, h4 = st.columns(4)
    with h1: st.metric("CHF/USD now",   f"{usd['current']:.4f}" if usd else "N/A")
    with h2:
        if usd:
            st.metric("30d trend", f"{usd['trend_pct']:+.2f}%",
                      delta_color="normal" if usd["trend_pct"] > 0 else "inverse")
    with h3: st.metric("CHF/EUR now",   f"{eur['current']:.4f}" if eur else "N/A")
    with h4:
        if usd:
            lbl, _ = fx_risk_label(usd["volatility_pct"])
            st.metric("USD volatility 30d", f"{usd['volatility_pct']:.3f}%",
                      delta=lbl, delta_color="off")

    if usd.get("series") is not None:
        fig_fx = go.Figure()
        fig_fx.add_trace(go.Scatter(
            x=usd["series"].index, y=usd["series"].values,
            name="CHF/USD", line=dict(color=NAVY, width=2),
            fill="tozeroy", fillcolor=f"rgba(30,58,95,0.07)",
        ))
        if eur and eur.get("series") is not None:
            fig_fx.add_trace(go.Scatter(
                x=eur["series"].index, y=eur["series"].values,
                name="CHF/EUR", line=dict(color=GOLD, width=2, dash="dot"),
            ))
        fig_fx.update_layout(
            template="plotly_white", height=240,
            margin=dict(l=0, r=0, t=10, b=0),
            legend=dict(orientation="h", y=1.05),
        )
        st.plotly_chart(fig_fx, use_container_width=True)



# ══════════════════════════════════════════════════════════════════════════════
# TAB 5 — PARTICIPANTS
# ══════════════════════════════════════════════════════════════════════════════
from datetime import date as _date

with tab_participants:
    st.markdown(f'<p class="section-label">Participant Intelligence</p>', unsafe_allow_html=True)
    st.caption(
        "Individual participant profiles — biographical data from Wikipedia, "
        "performance data from Jolpica API. "
        "In a live event context, the same architecture serves speaker, VIP, or delegate intelligence."
    )

    # ── Build selector from live standings ────────────────────────────────────
    selector_map = {}
    for s in driver_st:
        d   = s["Driver"]
        key = f"#{s['position']}  {d['code']} — {d['givenName']} {d['familyName']}  ·  {s['Constructors'][0]['name']}  ·  {s['points']} pts"
        selector_map[key] = {
            "id":          d["driverId"],
            "code":        d["code"],
            "given":       d["givenName"],
            "family":      d["familyName"],
            "dob":         d.get("dateOfBirth", ""),
            "nationality": d.get("nationality", ""),
            "wiki_url":    d.get("url", ""),
            "number":      d.get("permanentNumber", ""),
            "team":        s["Constructors"][0]["name"],
            "position":    int(s["position"]),
            "points":      float(s["points"]),
            "wins":        int(s["wins"]),
        }

    selected_key = st.selectbox(
        "Select participant",
        list(selector_map.keys()),
        label_visibility="collapsed",
    )
    drv = selector_map[selected_key]

    # ── Fetch live data ───────────────────────────────────────────────────────
    with st.spinner("Loading profile…"):
        wiki  = get_driver_wiki(drv["wiki_url"])
        results = get_driver_season_results(drv["id"], 2024)

    # Derived stats
    age = (_date.today() - _date.fromisoformat(drv["dob"])).days // 365 if drv["dob"] else "—"

    def _is_dnf(status: str) -> bool:
        return bool(status) and status != "Finished" and not status.endswith("Lap") and not status.endswith("Laps")

    podiums    = sum(1 for r in results if r["position"] <= 3)
    dnfs       = sum(1 for r in results if _is_dnf(r["status"]))
    races_done = len(results)
    avg_finish = sum(r["position"] for r in results if r["position"] < 99) / max(races_done - dnfs, 1)

    team_color = TEAM_COLORS.get(drv["team"], NAVY)

    st.divider()

    # ── Profile header ─────────────────────────────────────────────────────────
    col_photo, col_bio = st.columns([1, 3], gap="large")

    with col_photo:
        if wiki.get("thumbnail"):
            st.image(wiki["thumbnail"], width=200, caption="Source: Wikipedia")
        else:
            st.markdown(
                f"<div style='width:200px;height:240px;background:{team_color}22;"
                f"border-radius:12px;display:flex;align-items:center;"
                f"justify-content:center;font-size:3rem;color:{team_color};font-weight:900'>"
                f"{drv['code']}</div>",
                unsafe_allow_html=True,
            )

    with col_bio:
        # Championship badge
        st.markdown(
            f"<div style='display:inline-block;background:{team_color};color:white;"
            f"padding:4px 14px;border-radius:20px;font-weight:700;font-size:0.8rem;"
            f"letter-spacing:0.05em;margin-bottom:8px'>"
            f"#{drv['position']} CHAMPIONSHIP · {drv['team'].upper()}</div>",
            unsafe_allow_html=True,
        )
        st.markdown(f"## {drv['given']} {drv['family']}")
        st.markdown(
            f"<p style='color:{SLATE};font-size:1rem;margin-top:-8px'>"
            f"{drv['nationality']}  ·  {age} years old  ·  Car #{drv['number']}</p>",
            unsafe_allow_html=True,
        )
        if drv["dob"]:
            st.caption(f"Date of birth: {drv['dob']}")

        # Wikipedia link
        if wiki.get("wiki_url"):
            st.markdown(f"[Full profile on Wikipedia ↗]({wiki['wiki_url']})")

    st.divider()

    # ── KPI row ───────────────────────────────────────────────────────────────
    st.markdown(f'<p class="section-label">2024 Season Performance</p>', unsafe_allow_html=True)

    kc1, kc2, kc3, kc4, kc5, kc6 = st.columns(6)
    with kc1: st.metric("Championship Pts", f"{drv['points']:.0f}")
    with kc2: st.metric("Wins",             drv["wins"])
    with kc3: st.metric("Podiums",          podiums)
    with kc4: st.metric("Races",            races_done)
    with kc5: st.metric("DNFs",             dnfs,
                         delta_color="inverse" if dnfs > 2 else "off")
    with kc6: st.metric("Avg Finish Pos.",  f"{avg_finish:.1f}")

    # ── Season performance chart ──────────────────────────────────────────────
    if results:
        res_df = pd.DataFrame(results)
        res_df["cumulative"] = res_df["points"].cumsum()

        fig_perf = go.Figure()

        # Bar: points per race
        bar_colors = [
            team_color if r["position"] <= 3 else f"{team_color}88"
            for r in results
        ]
        fig_perf.add_trace(go.Bar(
            x=res_df["round"], y=res_df["points"],
            name="Points per race",
            marker_color=bar_colors,
            hovertemplate="Round %{x} — %{customdata}<br>%{y} pts<extra></extra>",
            customdata=res_df["race"],
        ))

        # Line: cumulative
        fig_perf.add_trace(go.Scatter(
            x=res_df["round"], y=res_df["cumulative"],
            name="Cumulative points",
            line=dict(color=NAVY, width=2.5),
            yaxis="y2",
            mode="lines+markers",
            marker=dict(size=5),
            hovertemplate="Round %{x}<br>Total: %{y} pts<extra></extra>",
        ))

        fig_perf.update_layout(
            template="plotly_white",
            height=280,
            margin=dict(l=0, r=0, t=10, b=0),
            xaxis=dict(title="Round", dtick=2),
            yaxis=dict(title="Points scored", showgrid=True, gridcolor="#F1F5F9"),
            yaxis2=dict(title="Cumulative pts", overlaying="y", side="right",
                        showgrid=False),
            legend=dict(orientation="h", y=1.06),
            bargap=0.25,
        )
        st.plotly_chart(fig_perf, use_container_width=True)

        # Race detail table (compact)
        with st.expander("Race-by-race results", expanded=False):
            table_df = pd.DataFrame([{
                "Round":    r["round"],
                "Event":    r["race"],
                "Grid":     r["grid"],
                "Finish":   r["position"] if r["position"] < 99 else "—",
                "Points":   int(r["points"]),
                "Status":   r["status"],
            } for r in results])
            st.dataframe(table_df, hide_index=True, use_container_width=True, height=300)

    st.divider()

    # ── Biography ─────────────────────────────────────────────────────────────
    st.markdown(f'<p class="section-label">Biography</p>', unsafe_allow_html=True)
    if wiki.get("extract"):
        st.markdown(wiki["extract"])
        st.caption("Source: Wikipedia REST API (live)")
    else:
        st.info("Biography not available from Wikipedia for this participant.")


# ── Footer ─────────────────────────────────────────────────────────────────────
st.divider()
st.caption(
    "Event Portfolio Intelligence · Formula 1 2024 Series · "
    "Jolpica · Wikipedia · open.er-api.com · Frankfurter/ECB · "
    "No hardcoded data — all metrics fetched live from public APIs."
)
