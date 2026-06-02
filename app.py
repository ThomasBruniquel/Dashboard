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
    get_race_results, get_all_results, TEAM_COLORS, DEFAULT_COLOR,
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
st.set_page_config(page_title="F1 2024 Event Intelligence", layout="wide")

st.markdown("""
<style>
    .block-container { padding-top: 1.2rem; padding-bottom: 2rem; }
    div[data-testid="metric-container"] {
        border: 1px solid #e0e0e0; border-radius: 8px;
        padding: 12px 16px; background: #fafafa;
    }
    .api-box {
        background: #f8f9fa; border-left: 3px solid #E8002D;
        padding: 5px 10px; font-size: 0.78rem; color: #555;
        border-radius: 0 4px 4px 0; margin: 2px 0;
    }
    .source-chip {
        display: inline-block; font-size: 0.68rem; font-weight: 700;
        padding: 2px 8px; border-radius: 20px; margin-right: 4px;
    }
    .live-chip { background:#d4edda; color:#155724; }
</style>
""", unsafe_allow_html=True)

LIVE = '<span class="source-chip live-chip">LIVE</span>'

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

# ── Session state ──────────────────────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = [{
        "role": "assistant",
        "content": (
            "Bonjour ! Je suis connecté aux données F1 2024 en temps réel (Jolpica API).\n\n"
            "Demandez-moi : *\"Qui a gagné Monaco ?\"* · *\"Standings constructeurs ?\"* · "
            "*\"Quel circuit en Japon ?\"* · *\"Taux CHF/USD ?\"*"
        ),
        "calls": [],
    }]
using_llm = llm_agent.is_available()

# ── Sidebar — chat ─────────────────────────────────────────────────────────────
with st.sidebar:
    model_str = llm_agent.model_label() if using_llm else "No LLM key"
    st.markdown(f"**Assistant** &nbsp; {'🟢 ' + model_str if using_llm else '⚪ ' + model_str}")
    st.divider()

    with st.container(height=480, border=False):
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
                if msg.get("calls"):
                    with st.expander("Sources", expanded=False):
                        for c in msg["calls"]:
                            st.markdown(f'<div class="api-box">{c}</div>', unsafe_allow_html=True)

    with st.form("chat_form", clear_on_submit=True):
        user_input = st.text_input("msg", placeholder="Votre question F1…", label_visibility="collapsed")
        submitted  = st.form_submit_button("Envoyer →", use_container_width=True)

    if submitted and user_input.strip():
        st.session_state.messages.append({"role": "user", "content": user_input, "calls": []})
        if using_llm:
            try:
                # Inject live F1 standings into context for the agent
                f1_ctx = (
                    f"[Live F1 2024 data] "
                    f"Driver leader: {winner_name} ({winner_pts} pts). "
                    f"Constructor leader: {best_team} ({best_team_pts} pts). "
                    f"Season: {n_races} races in {n_countries} countries."
                )
                augmented = user_input + f"\n\nContext: {f1_ctx}"
                with st.spinner(f"Agent thinking… ({llm_agent.model_label()}, max 25s)"):
                    response, calls = llm_agent.ask(augmented, st.session_state.messages[:-1])
                calls.insert(0, "Jolpica F1 API — season context injected")
            except Exception as e:
                response, calls = f"Erreur : {str(e)[:200]}", []
        else:
            response = "Ajoutez `GEMINI_API_KEY` dans `.env` pour activer l'agent."
            calls    = []
        st.session_state.messages.append({"role": "assistant", "content": response, "calls": calls})
        st.rerun()

    if len(st.session_state.messages) > 1:
        if st.button("Effacer", use_container_width=True):
            st.session_state.messages = st.session_state.messages[:1]
            st.rerun()

    st.divider()
    st.caption("🟢 Jolpica · 🟢 Wikipedia · 🟢 open.er-api.com · 🟢 Frankfurter/ECB")

# ── Header ─────────────────────────────────────────────────────────────────────
st.title("F1 2024 Season — Event Intelligence Dashboard")
st.caption(
    "All data from public APIs — no hardcoded values.  |  "
    "Jolpica (race data) · Wikipedia · open.er-api.com · Frankfurter/ECB"
)

# ── Tabs ───────────────────────────────────────────────────────────────────────
tab_season, tab_results, tab_standings, tab_finance = st.tabs([
    "Season Overview", "Race Results", "Championship", "Finance & FX"
])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — SEASON OVERVIEW
# ══════════════════════════════════════════════════════════════════════════════
with tab_season:
    st.markdown(f'{LIVE} Jolpica — 2024 F1 Season', unsafe_allow_html=True)

    # ── 5 KPIs ────────────────────────────────────────────────────────────────
    k1, k2, k3, k4, k5 = st.columns(5)
    with k1: st.metric("Races",             n_races)
    with k2: st.metric("Countries",         n_countries)
    with k3: st.metric("WDC Leader",        winner_name, delta=f"{winner_pts} pts", delta_color="off")
    with k4: st.metric("WCC Leader",        best_team,   delta=f"{best_team_pts} pts", delta_color="off")
    with k5:
        n_teams = len({r["Constructor"]["name"] for rr in winners for r in rr.get("Results", [])[:1]})
        st.metric("Teams", n_teams if n_teams else "10")

    st.divider()

    # ── World map of circuits ─────────────────────────────────────────────────
    map_rows = []
    for race in races:
        loc = race["Circuit"]["Location"]
        rnd = int(race["round"])
        w   = winner_map.get(rnd, {})
        map_rows.append({
            "Race":    race["raceName"],
            "Country": loc["country"],
            "Circuit": race["Circuit"]["circuitName"],
            "Date":    race["date"],
            "lat":     float(loc.get("lat", 0)),
            "lon":     float(loc.get("long", 0)),
            "Winner":  w.get("name", "TBD"),
            "Team":    w.get("team", ""),
        })
    map_df = pd.DataFrame(map_rows)

    fig_map = px.scatter_geo(
        map_df,
        lat="lat", lon="lon",
        hover_name="Race",
        hover_data={"Country": True, "Circuit": True, "Date": True,
                    "Winner": True, "lat": False, "lon": False},
        color_discrete_sequence=["#E8002D"],
        template="plotly_white",
        title="2024 F1 Calendar — 24 races across 19 countries",
    )
    fig_map.update_traces(marker=dict(size=10, opacity=0.85))
    fig_map.update_layout(height=400, margin=dict(l=0, r=0, t=40, b=0),
                           geo=dict(showland=True, landcolor="#f8f8f8",
                                    showocean=True, oceancolor="#e8f4f8"))
    st.plotly_chart(fig_map, use_container_width=True)

    # ── Race calendar table ───────────────────────────────────────────────────
    st.subheader("Race Calendar")
    cal_rows = []
    for race in races:
        rnd = int(race["round"])
        loc = race["Circuit"]["Location"]
        w   = winner_map.get(rnd, {})
        cal_rows.append({
            "Round":   rnd,
            "Grand Prix":  race["raceName"],
            "Circuit":     race["Circuit"]["circuitName"],
            "Country":     loc["country"],
            "City":        loc["locality"],
            "Date":        race["date"],
            "Winner":      w.get("name", "—"),
            "Team":        w.get("team", "—"),
        })
    cal_df = pd.DataFrame(cal_rows)
    st.dataframe(cal_df, hide_index=True, use_container_width=True, height=500)
    st.caption("Source: Jolpica API (no API key required)")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — RACE RESULTS
# ══════════════════════════════════════════════════════════════════════════════
with tab_results:
    st.markdown(f'{LIVE} Jolpica — race-by-race results', unsafe_allow_html=True)

    race_options = {f"Round {r['round']}: {r['raceName']}": int(r["round"]) for r in races}
    selected_label = st.selectbox("Select race", list(race_options.keys()))
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
# TAB 3 — CHAMPIONSHIP STANDINGS
# ══════════════════════════════════════════════════════════════════════════════
with tab_standings:
    st.markdown(f'{LIVE} Jolpica — 2024 championship standings', unsafe_allow_html=True)

    col_d, col_c = st.columns(2)

    with col_d:
        st.subheader("Drivers Championship")
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
# TAB 4 — FINANCE & FX
# ══════════════════════════════════════════════════════════════════════════════
with tab_finance:
    st.markdown(f'{LIVE} open.er-api.com + Frankfurter/ECB', unsafe_allow_html=True)
    st.caption("Currency context for F1 host countries — relevant for international event budget planning.")

    # Key host country currencies
    host_currencies = {
        "Bahrain":      "BHD", "Saudi Arabia": "SAR", "Australia": "AUD",
        "Japan":        "JPY", "China":        "CNY", "USA":       "USD",
        "Monaco":       "EUR", "Canada":       "CAD", "Spain":     "EUR",
        "UK":           "GBP", "Hungary":      "HUF", "Belgium":   "EUR",
        "Netherlands":  "EUR", "Italy":        "EUR", "Azerbaijan": "AZN",
        "Singapore":    "SGD", "Mexico":       "MXN", "Brazil":    "BRL",
        "Qatar":        "QAR", "UAE":          "AED",
    }

    # Unique currencies with rates
    unique_curs = sorted({c for c in host_currencies.values() if rates.get(c)})
    fx_rows = [
        {"Currency": c, "1 CHF =": f"{rates[c]:.4f}", "Host countries": ", ".join(
            [co for co, cu in host_currencies.items() if cu == c][:3]
        )}
        for c in unique_curs
    ]

    c_table, c_chart = st.columns([1, 2])
    with c_table:
        st.subheader("Host Country Currencies")
        st.dataframe(pd.DataFrame(fx_rows), hide_index=True, use_container_width=True)
        st.caption(f"Updated: {currency.get('last_updated','N/A')}")

    with c_chart:
        # How many races per currency
        currency_count = {}
        for country in countries:
            c = host_currencies.get(country)
            if c:
                currency_count[c] = currency_count.get(c, 0) + 1
        cc_df = pd.DataFrame([
            {"Currency": c, "Races": n}
            for c, n in sorted(currency_count.items(), key=lambda x: -x[1])
        ])
        fig_cc = px.bar(cc_df, x="Currency", y="Races",
                        color_discrete_sequence=["#E8002D"],
                        template="plotly_white", text="Races",
                        title="Races per host currency")
        fig_cc.update_layout(height=280, margin=dict(l=0, r=0, t=35, b=0))
        fig_cc.update_traces(textposition="auto")
        st.plotly_chart(fig_cc, use_container_width=True)

    st.divider()

    # 30-day FX history
    usd = fx_hist.get("currencies", {}).get("USD", {})
    eur = fx_hist.get("currencies", {}).get("EUR", {})
    if usd.get("series") is not None:
        h1, h2, h3, h4 = st.columns(4)
        with h1: st.metric("CHF/USD",    f"{usd['current']:.4f}")
        with h2: st.metric("30d trend",  f"{usd['trend_pct']:+.2f}%",
                           delta_color="normal" if usd["trend_pct"] > 0 else "inverse")
        with h3: st.metric("CHF/EUR",    f"{eur['current']:.4f}" if eur else "N/A")
        with h4:
            lbl, _ = fx_risk_label(usd["volatility_pct"])
            st.metric("FX volatility", f"{usd['volatility_pct']:.3f}%", delta=lbl, delta_color="off")

        fig_fx = go.Figure()
        fig_fx.add_trace(go.Scatter(
            x=usd["series"].index, y=usd["series"].values,
            name="CHF/USD", line=dict(color="#E8002D", width=2),
            fill="tozeroy", fillcolor="rgba(232,0,45,0.07)",
        ))
        if eur and eur.get("series") is not None:
            fig_fx.add_trace(go.Scatter(
                x=eur["series"].index, y=eur["series"].values,
                name="CHF/EUR", line=dict(color="#3671C6", width=1.5, dash="dot"),
            ))
        fig_fx.update_layout(template="plotly_white", height=240,
                              margin=dict(l=0, r=0, t=20, b=0),
                              legend=dict(orientation="h", y=1.05))
        st.plotly_chart(fig_fx, use_container_width=True)
        st.caption("Source: Frankfurter / ECB (30 days)")

# ── Footer ─────────────────────────────────────────────────────────────────────
st.divider()
st.caption(
    "F1 2024 Event Intelligence · Jolpica API · Wikipedia REST API · "
    "open.er-api.com · Frankfurter/ECB · No hardcoded data."
)
