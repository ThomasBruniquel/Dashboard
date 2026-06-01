"""
Luxury Event Intelligence Dashboard
Full-API prototype for international luxury event planning.
"""

import streamlit as st
from datetime import date, timedelta
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

from src.api.weather import fetch_weather_forecast, compute_weather_risk
from src.api.currency import fetch_currency_rates
from src.api.flights import get_flight_data
from src.api.events import get_event_logistics
from src.analytics.risk_score import compute_risk_score
from src.analytics.report_generator import generate_executive_brief
from src.utils.formatting import format_currency, risk_color, risk_emoji, format_hours, source_label

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Luxury Event Intelligence Dashboard",
    page_icon="💎",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .block-container { padding-top: 1.5rem; padding-bottom: 2rem; }
    div[data-testid="metric-container"] {
        border: 1px solid rgba(201,169,110,0.3);
        border-radius: 8px;
        padding: 14px 18px;
        background: rgba(201,169,110,0.04);
    }
    .source-tag {
        display: inline-block;
        font-size: 0.72rem;
        font-weight: 700;
        letter-spacing: 0.04em;
        padding: 2px 9px;
        border-radius: 20px;
        margin-right: 4px;
    }
    .live-tag  { background:#1a472a; color:#68d391; }
    .mock-tag  { background:#3d2b00; color:#fbd38d; }
</style>
""", unsafe_allow_html=True)

LIVE = '<span class="source-tag live-tag">LIVE</span>'
MOCK = '<span class="source-tag mock-tag">MOCK</span>'


# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 💎 Event Parameters")
    st.divider()

    st.markdown("**Location**")
    st.text_input("Origin City", value="Geneva", disabled=True)
    st.text_input("Destination City", value="Doha", disabled=True)

    st.markdown("**Event Timeline**")
    today = date.today()
    event_start = st.date_input(
        "Start Date",
        value=today + timedelta(days=30),
        min_value=today,
    )
    event_end = st.date_input(
        "End Date",
        value=today + timedelta(days=33),
        min_value=event_start,
    )

    st.markdown("**Guests & Budget**")
    expected_guests = st.slider("Expected Guests", 20, 500, 200, 10)
    budget_chf = st.number_input(
        "Total Budget (CHF)",
        min_value=10_000,
        max_value=10_000_000,
        value=500_000,
        step=10_000,
        format="%d",
    )
    budget_currency = st.selectbox("Display Currency", ["CHF", "USD", "EUR", "QAR"])

    st.divider()
    refresh = st.button("🔄 Refresh Live Data", use_container_width=True)

    st.divider()
    st.markdown("**Data Sources**")
    st.markdown(f'{LIVE} Open-Meteo Weather', unsafe_allow_html=True)
    st.markdown(f'{LIVE} open.er-api.com Rates', unsafe_allow_html=True)
    st.markdown(f'{MOCK} Flight Intelligence', unsafe_allow_html=True)
    st.markdown(f'{MOCK} Event Logistics', unsafe_allow_html=True)
    st.caption("Mock data simulates realistic API responses and is clearly labelled throughout.")


# ── Data loading ───────────────────────────────────────────────────────────────
if refresh:
    st.cache_data.clear()

start_str = event_start.isoformat()
end_str = event_end.isoformat()

with st.spinner("Fetching live intelligence data…"):
    weather_geneva = fetch_weather_forecast("Geneva", start_str, end_str)
    weather_doha   = fetch_weather_forecast("Doha",   start_str, end_str)
    currency_data  = fetch_currency_rates()
    flight_data    = get_flight_data()
    event_data     = get_event_logistics()


# ── Analytics ──────────────────────────────────────────────────────────────────
weather_risk = compute_weather_risk(weather_geneva, weather_doha)
risk_result  = compute_risk_score(weather_risk, flight_data, event_data)

event_params = {
    "origin":          "Geneva",
    "destination":     "Doha",
    "start_date":      event_start,
    "end_date":        event_end,
    "guests":          expected_guests,
    "budget_chf":      budget_chf,
    "budget_currency": budget_currency,
}

brief = generate_executive_brief(
    risk_result, weather_geneva, weather_doha,
    flight_data, event_data, event_params,
)


# ── Page header ────────────────────────────────────────────────────────────────
st.title("💎 Luxury Event Intelligence Dashboard")
st.caption(
    f"Full-API prototype for international event planning — no hosted client data. &nbsp;|&nbsp; "
    f"**Route:** Geneva → Doha &nbsp;|&nbsp; "
    f"**Dates:** {event_start.strftime('%d %b %Y')} – {event_end.strftime('%d %b %Y')} &nbsp;|&nbsp; "
    f"**Guests:** {expected_guests}"
)

# Warn if any API fallback is active
if weather_geneva.get("note"):
    st.info(f"**Geneva weather:** {weather_geneva['note']}")
if weather_doha.get("note"):
    st.info(f"**Doha weather:** {weather_doha['note']}")
if currency_data.get("error"):
    st.warning(f"**Exchange rates:** API unavailable — showing fallback rates. ({currency_data['error']})")


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — Executive Summary
# ══════════════════════════════════════════════════════════════════════════════
st.header("Executive Summary")

rates = currency_data.get("rates", {})
display_rate = rates.get(budget_currency, 1.0) if budget_currency != "CHF" else 1.0
display_budget = budget_chf * display_rate

col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    cat   = risk_result["category"]
    score = risk_result["score"]
    st.metric(
        "Overall Risk",
        f"{risk_emoji(cat)} {cat}",
        delta=f"Score: {score}/100",
        delta_color="inverse" if score > 50 else "off",
        help="Weighted composite of weather, travel, supplier, VIP, and guest signals.",
    )
with col2:
    doha_temp = weather_doha.get("temp_max", 0.0)
    st.metric(
        "Doha Peak Temp",
        f"{doha_temp:.1f} °C",
        delta="Extreme heat" if doha_temp > 40 else ("Heat advisory" if doha_temp > 35 else "Favourable"),
        delta_color="inverse" if doha_temp > 35 else "normal",
    )
with col3:
    supplier = event_data.get("supplier_readiness", 0)
    st.metric(
        "Supplier Readiness",
        f"{supplier:.0f}%",
        delta="On track" if supplier >= 85 else "Needs attention",
        delta_color="normal" if supplier >= 85 else "inverse",
    )
with col4:
    vip = event_data.get("vip_arrivals_completed", 0)
    st.metric(
        "VIP Arrivals",
        f"{vip:.0f}%",
        delta="Confirmed" if vip >= 80 else "Pending",
        delta_color="normal" if vip >= 80 else "inverse",
    )
with col5:
    st.metric(
        f"Budget ({budget_currency})",
        format_currency(display_budget, budget_currency),
        help=f"CHF {budget_chf:,.0f} converted at live rate.",
    )

st.divider()


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — Weather & Climate Risk
# ══════════════════════════════════════════════════════════════════════════════
st.header("Weather & Climate Risk")

weather_risk_score = weather_risk["score"]
weather_level = weather_risk["level"]
st.markdown(
    f"Weather Risk: **{weather_level}** ({weather_risk_score:.0f}/100) — "
    f"Heat risk score: {weather_risk['heat_risk']:.0f}/100 · "
    f"Precipitation risk score: {weather_risk['precip_risk']:.0f}/100"
)

tab_gva, tab_doh, tab_compare = st.tabs(["🇨🇭 Geneva", "🇶🇦 Doha", "Comparison"])


def weather_chart(city: str, wdata: dict, color_max: str, color_min: str) -> go.Figure | None:
    """Build a dual-axis temperature + precipitation Plotly figure."""
    df: pd.DataFrame | None = wdata.get("df")
    if df is None or df.empty:
        return None

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["date"], y=df["temp_max"],
        name="Max °C", line=dict(color=color_max, width=2.5),
        mode="lines+markers", marker=dict(size=5),
    ))
    fig.add_trace(go.Scatter(
        x=df["date"], y=df["temp_min"],
        name="Min °C", line=dict(color=color_min, width=2, dash="dot"),
        mode="lines+markers", marker=dict(size=4),
    ))
    if df["precip_prob"].notna().any():
        fig.add_trace(go.Bar(
            x=df["date"], y=df["precip_prob"],
            name="Precip %", yaxis="y2",
            marker_color="rgba(100,150,255,0.25)",
        ))
    fig.update_layout(
        xaxis_title="Date",
        yaxis_title="Temperature (°C)",
        yaxis2=dict(title="Precipitation prob. (%)", overlaying="y", side="right", range=[0, 100]),
        template="plotly_dark",
        height=340,
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        margin=dict(l=10, r=10, t=10, b=10),
    )
    return fig


def climate_summary_col(city: str, wdata: dict) -> None:
    """Render a summary metrics column for a single city."""
    temp_max = wdata.get("temp_max", 0.0)
    is_hot = city == "Doha" and temp_max > 38

    st.metric("Avg Max Temp", f"{temp_max:.1f} °C",
              delta="⚠ High" if is_hot else None,
              delta_color="inverse" if is_hot else "off")
    st.metric("Avg Min Temp", f"{wdata.get('temp_min', 0.0):.1f} °C")
    st.metric("Precipitation Prob.", f"{wdata.get('precip_prob', 0.0):.0f}%")
    st.metric("Avg Wind Speed", f"{wdata.get('wind_speed', 0.0):.0f} km/h")
    st.caption(f"Source: {source_label(wdata.get('source', 'seasonal_average'))}")


with tab_gva:
    c1, c2 = st.columns([3, 1])
    with c1:
        fig = weather_chart("Geneva", weather_geneva, "#4fc3f7", "#b3e5fc")
        if fig:
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Live forecast unavailable for these dates — seasonal summary shown.")
    with c2:
        climate_summary_col("Geneva", weather_geneva)

with tab_doh:
    c1, c2 = st.columns([3, 1])
    with c1:
        fig = weather_chart("Doha", weather_doha, "#ff7043", "#ffccbc")
        if fig:
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Live forecast unavailable for these dates — seasonal summary shown.")
    with c2:
        climate_summary_col("Doha", weather_doha)

with tab_compare:
    categories = ["Max Temp (°C)", "Min Temp (°C)", "Precip Prob (%)", "Wind (km/h)"]
    gva_vals = [
        weather_geneva.get("temp_max", 0),
        weather_geneva.get("temp_min", 0),
        weather_geneva.get("precip_prob", 0) or 0,
        weather_geneva.get("wind_speed", 0),
    ]
    doh_vals = [
        weather_doha.get("temp_max", 0),
        weather_doha.get("temp_min", 0),
        weather_doha.get("precip_prob", 0) or 0,
        weather_doha.get("wind_speed", 0),
    ]
    fig_cmp = go.Figure()
    fig_cmp.add_trace(go.Bar(name="Geneva", x=categories, y=gva_vals, marker_color="#4fc3f7"))
    fig_cmp.add_trace(go.Bar(name="Doha",   x=categories, y=doh_vals, marker_color="#ff7043"))
    fig_cmp.update_layout(
        barmode="group", template="plotly_dark", height=340,
        margin=dict(l=10, r=10, t=10, b=10),
    )
    st.plotly_chart(fig_cmp, use_container_width=True)

st.divider()


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — Currency & Budget
# ══════════════════════════════════════════════════════════════════════════════
st.header("Currency & Budget Context")
st.caption(f"Base: CHF · Last updated: {currency_data.get('last_updated', 'N/A')}")

c_rates, c_chart = st.columns([1, 2])

with c_rates:
    st.subheader("CHF Exchange Rates")
    display_currencies = ["USD", "EUR", "QAR", "GBP", "AED"]
    rate_rows = []
    for curr in display_currencies:
        r = rates.get(curr)
        rate_rows.append({"Currency": curr, "1 CHF =":{curr: f"{r:.4f} {curr}" if r else "N/A"}.get(curr)})
    rate_df = pd.DataFrame([
        {"Currency": c, "Rate (1 CHF)": f"{rates[c]:.4f}" if rates.get(c) else "N/A"}
        for c in display_currencies
    ])
    st.dataframe(rate_df, hide_index=True, use_container_width=True)

with c_chart:
    st.subheader(f"Budget of CHF {budget_chf:,.0f} in Key Currencies")
    target_curs = ["CHF", "USD", "EUR", "QAR"]
    budget_rows = []
    for curr in target_curs:
        r = 1.0 if curr == "CHF" else rates.get(curr)
        if r:
            budget_rows.append({"Currency": curr, "Amount": budget_chf * r})
    if budget_rows:
        bdf = pd.DataFrame(budget_rows)
        fig_bud = px.bar(
            bdf, x="Currency", y="Amount",
            color="Currency",
            color_discrete_sequence=["#c9a96e", "#4fc3f7", "#81c784", "#ff7043"],
            template="plotly_dark",
            labels={"Amount": "Amount"},
            text_auto=",.0f",
        )
        fig_bud.update_layout(height=300, showlegend=False, margin=dict(l=10, r=10, t=10, b=10))
        fig_bud.update_traces(textposition="auto")
        st.plotly_chart(fig_bud, use_container_width=True)

st.divider()


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 4 — Travel & Flight Readiness
# ══════════════════════════════════════════════════════════════════════════════
st.header("Travel & Flight Readiness")
st.markdown(
    f'{MOCK} Flight data is simulated for demo purposes. '
    'In production this connects to a live flight intelligence API.',
    unsafe_allow_html=True,
)

f1, f2, f3, f4 = st.columns(4)
with f1:
    st.metric("Direct Flight (GVA→DOH)", "Available" if flight_data["direct_flight_available"] else "Not available")
with f2:
    st.metric("Avg. Travel Time", format_hours(flight_data["avg_travel_duration_hours"]))
with f3:
    dlabel = flight_data["disruption_risk_label"]
    st.metric("Disruption Risk", dlabel,
              delta_color="inverse" if dlabel in ("High", "Critical") else "normal")
with f4:
    st.metric("Recommended Buffer", f"+{flight_data['recommended_buffer_hours']} h")

with st.expander("Flight routes & VIP ground services"):
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("**Available Routes**")
        for airline in flight_data["airlines"]:
            direct_str = "✈️ Direct" if airline["direct"] else f"🔁 Via {airline.get('via','')}"
            st.markdown(
                f"**{airline['name']} ({airline['code']})** — {direct_str} · "
                f"{airline['duration_hours']:.1f} h · {airline['frequency']}"
            )
            st.caption(airline.get("notes", ""))
    with col_b:
        st.markdown("**VIP Ground Services**")
        vip_svc = flight_data.get("vip_ground_services", {})
        for svc, available in vip_svc.items():
            icon = "✅" if available else "❌"
            label = svc.replace("_", " ").title()
            st.markdown(f"{icon} {label}")

st.divider()


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 5 — Event Logistics
# ══════════════════════════════════════════════════════════════════════════════
st.header("Event Logistics Status")
st.markdown(
    f'{MOCK} Logistics data is simulated for demo purposes. '
    'In production this connects to an event management platform API.',
    unsafe_allow_html=True,
)

logistics_metrics = [
    ("Venue Readiness",     "venue_readiness"),
    ("Guest Confirmation",  "guest_confirmation"),
    ("VIP Arrivals",        "vip_arrivals_completed"),
    ("Supplier Readiness",  "supplier_readiness"),
    ("Security Clearance",  "security_clearance"),
]

cols = st.columns(len(logistics_metrics))
for col, (label, key) in zip(cols, logistics_metrics):
    val = float(event_data.get(key, 0))
    delta_txt = "On track" if val >= 85 else ("Monitor" if val >= 70 else "Action needed")
    with col:
        st.metric(label, f"{val:.0f}%", delta=delta_txt,
                  delta_color="normal" if val >= 85 else "inverse")

# Radar chart for readiness overview
theta = [m[0] for m in logistics_metrics]
r_vals = [float(event_data.get(m[1], 0)) for m in logistics_metrics]

fig_radar = go.Figure(go.Scatterpolar(
    r=r_vals + [r_vals[0]],
    theta=theta + [theta[0]],
    fill="toself",
    fillcolor="rgba(201,169,110,0.18)",
    line=dict(color="#c9a96e", width=2),
))
fig_radar.update_layout(
    polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
    template="plotly_dark",
    height=340,
    showlegend=False,
    margin=dict(l=40, r=40, t=20, b=20),
)

with st.expander("Readiness Radar & Supplier Detail", expanded=True):
    c_radar, c_supply = st.columns([1, 1])
    with c_radar:
        st.plotly_chart(fig_radar, use_container_width=True)
    with c_supply:
        st.markdown("**Supplier Breakdown**")
        supply_df = pd.DataFrame(event_data.get("suppliers", []))
        if not supply_df.empty:
            fig_sup = px.bar(
                supply_df, x="readiness", y="category", orientation="h",
                color="readiness",
                color_continuous_scale=["#fc8181", "#fbd38d", "#68d391"],
                range_color=[0, 100],
                template="plotly_dark",
                labels={"readiness": "Readiness %", "category": ""},
            )
            fig_sup.update_layout(
                height=300, coloraxis_showscale=False,
                margin=dict(l=10, r=10, t=10, b=10),
            )
            st.plotly_chart(fig_sup, use_container_width=True)

st.divider()


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 6 — Overall Risk Score
# ══════════════════════════════════════════════════════════════════════════════
st.header("Overall Event Risk Score")

GAUGE_COLOR = risk_color(risk_result["category"])

fig_gauge = go.Figure(go.Indicator(
    mode="gauge+number",
    value=risk_result["score"],
    number={"suffix": "/100", "font": {"size": 36}},
    gauge={
        "axis": {"range": [0, 100], "tickwidth": 1, "tickcolor": "white"},
        "bar": {"color": GAUGE_COLOR, "thickness": 0.25},
        "bgcolor": "rgba(0,0,0,0)",
        "borderwidth": 1,
        "bordercolor": "rgba(255,255,255,0.2)",
        "steps": [
            {"range": [0,  25], "color": "rgba(104,211,145,0.15)"},
            {"range": [25, 50], "color": "rgba(251,211,141,0.15)"},
            {"range": [50, 75], "color": "rgba(252,129,129,0.15)"},
            {"range": [75,100], "color": "rgba(229,62,62,0.15)"},
        ],
        "threshold": {
            "line": {"color": GAUGE_COLOR, "width": 4},
            "thickness": 0.8,
            "value": risk_result["score"],
        },
    },
    title={
        "text": (
            f"<b>{risk_result['category']} Risk</b><br>"
            f"<span style='font-size:0.75em;color:{GAUGE_COLOR}'>Weighted composite score</span>"
        )
    },
))
fig_gauge.update_layout(
    template="plotly_dark", height=320,
    font={"color": "white"},
    margin=dict(l=30, r=30, t=30, b=10),
)

c_gauge, c_breakdown = st.columns([1, 1])

with c_gauge:
    st.plotly_chart(fig_gauge, use_container_width=True)

with c_breakdown:
    breakdown_labels = {
        "weather":  "Weather",
        "travel":   "Travel Disruption",
        "supplier": "Supplier Risk",
        "vip":      "VIP Arrival Risk",
        "guest":    "Guest Confirmation",
    }
    weights = risk_result["weights"]
    bdf = pd.DataFrame([
        {
            "Factor":       breakdown_labels.get(k, k),
            "Score":        v,
            "Weight (%)":   round(weights.get(k, 0) * 100),
        }
        for k, v in risk_result["breakdown"].items()
    ])
    fig_break = px.bar(
        bdf, x="Score", y="Factor", orientation="h",
        color="Score",
        color_continuous_scale=["#68d391", "#fbd38d", "#fc8181", "#e53e3e"],
        range_color=[0, 100],
        template="plotly_dark",
        text="Score",
        labels={"Score": "Risk Score (0–100)"},
    )
    fig_break.update_layout(
        height=300, coloraxis_showscale=False,
        margin=dict(l=10, r=10, t=10, b=10),
    )
    fig_break.update_traces(texttemplate="%{text:.0f}", textposition="outside")
    st.plotly_chart(fig_break, use_container_width=True)

st.markdown("**Risk Factor Observations**")
for obs in risk_result["explanations"]:
    st.markdown(f"- {obs}")

st.divider()


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 7 — Executive Brief
# ══════════════════════════════════════════════════════════════════════════════
st.header("Auto-Generated Executive Brief")
st.caption(
    "Generated by a deterministic rule-based engine from live and mock API data. "
    "No AI / LLM involved — every sentence is traceable to an input value."
)

with st.container(border=True):
    st.markdown(brief)

col_dl, _ = st.columns([1, 4])
with col_dl:
    st.download_button(
        label="⬇️ Download Brief (.txt)",
        data=brief,
        file_name=f"event_brief_{start_str}_{end_str}.txt",
        mime="text/plain",
        use_container_width=True,
    )

st.divider()
st.caption(
    "Luxury Event Intelligence Dashboard · "
    "Streamlit + Open-Meteo + open.er-api.com · "
    "Portfolio project — no client data stored."
)
