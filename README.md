# 💎 Luxury Event Intelligence Dashboard

A polished full-stack dashboard prototype for international luxury event planning — built to demonstrate real-world API integration, risk scoring, and executive reporting **without storing any client data**.

> **Portfolio project** built with Streamlit, Python, and free public APIs. Designed for a fictional executive event between Geneva and Doha, modelled on the kind of intelligence platform that high-end event agencies (think MCI, Eventive, GPJ) could build for VIP institutional clients.

---

## Business Context

International luxury events — executive summits, investor forums, diplomatic dinners — require intelligence across multiple domains simultaneously: climate conditions at both ends of the route, live currency exposure, travel logistics for VIPs, and vendor readiness. Traditionally this intelligence lives in spreadsheets or static briefing documents.

This dashboard prototype answers the question: **what if you could pull all of that into a single, API-driven, always-current view — without hosting a single byte of client data?**

The architecture is fully "API-out": the dashboard is a stateless application that assembles intelligence from external APIs on demand. Nothing is persisted.

---

## Architecture

```
External APIs (Open-Meteo, open.er-api.com)
            ↓
  Python API Layer  (src/api/)
            ↓
  Analytics & Risk Engine  (src/analytics/)
            ↓
  Streamlit Dashboard  (app.py)
            ↓
  Auto-Generated Executive Brief
```

See [`assets/architecture.md`](assets/architecture.md) for the full annotated diagram.

---

## APIs Used

| Module | Source | Key Required | Status |
|--------|--------|:---:|--------|
| `weather.py` | [Open-Meteo](https://open-meteo.com/) | ❌ | **Live** |
| `currency.py` | [open.er-api.com](https://www.exchangerate-api.com/) | ❌ | **Live** |
| `flights.py` | Geneva → Doha route | — | **Mock** (labelled) |
| `events.py` | Event logistics platform | — | **Mock** (labelled) |

### Live vs. Mock — what that means

- **Live**: the dashboard fetches real data at runtime and caches it for 1 hour (`@st.cache_data(ttl=3600)`). If the API is unavailable, a hardcoded fallback is used and a warning is shown.
- **Mock**: data is realistic but static, clearly flagged with an amber **MOCK** badge throughout the UI. In a production system these modules would be replaced with real API clients (Amadeus for flights, Cvent/Eventforce for logistics).

**Weather edge case**: Open-Meteo only provides a 16-day forecast. If the selected event dates are beyond that window, the app automatically switches to monthly seasonal averages for each city and tells the user.

---

## Dashboard Sections

1. **Executive Summary** — five KPI cards: overall risk, Doha peak temperature, supplier readiness, VIP arrival rate, budget in selected currency.
2. **Weather & Climate Risk** — live or seasonal temperature forecast for Geneva and Doha, precipitation probability, and a side-by-side comparison chart.
3. **Currency & Budget Context** — live CHF exchange rates and a budget conversion bar chart for CHF / USD / EUR / QAR.
4. **Travel & Flight Readiness** — direct flight availability, average travel time, disruption risk, and VIP ground service status (mock).
5. **Event Logistics Status** — readiness radar across five pillars (venue, guests, VIPs, suppliers, security) and a supplier breakdown bar chart (mock).
6. **Overall Risk Score** — Plotly gauge built from a weighted composite of all signals, with a per-factor breakdown and plain-language observations.
7. **Auto-Generated Executive Brief** — rule-based markdown report, downloadable as `.txt`. No LLM involved.

---

## Risk Scoring Methodology

The risk score is a transparent weighted average of five factors (all values 0–100):

| Factor | Weight | Derivation |
|--------|-------:|------------|
| Weather risk | 25% | Doha heat index (°C above 30) + precipitation probability |
| Travel disruption | 25% | Mock disruption score for GVA→DOH route |
| Supplier risk | 20% | `100 − supplier_readiness` |
| VIP arrival risk | 20% | `100 − vip_arrivals_completed` |
| Guest confirmation risk | 10% | `100 − guest_confirmation` |

Thresholds: **0–24** Low · **25–49** Moderate · **50–74** High · **75–100** Critical.

All weights and thresholds are constants in [`src/analytics/risk_score.py`](src/analytics/risk_score.py) — easy to tune per client.

---

## How to Run Locally

```bash
# 1. Clone the repository
git clone https://github.com/ThomasBruniquel/Dashboard.git
cd Dashboard

# 2. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate        # macOS / Linux
.venv\Scripts\activate           # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Launch the dashboard
streamlit run app.py
```

The app opens at `http://localhost:8501`. No API keys or `.env` file are required.

---

## Deployment

### Streamlit Cloud (recommended for demos)

1. Push this repository to GitHub.
2. Go to [share.streamlit.io](https://share.streamlit.io) → **New app** → select your repo.
3. Set **Main file path**: `app.py`.
4. Click **Deploy**. No secrets needed.

### Render

1. Create a new **Web Service** pointing to this repository.
2. Set **Build command**: `pip install -r requirements.txt`
3. Set **Start command**:
   ```
   streamlit run app.py --server.port $PORT --server.address 0.0.0.0
   ```
4. Deploy.

---

## How to Extend for a Real Client

| Capability | How to add |
|------------|-----------|
| Live flight data | Replace `src/api/flights.py` with an [Amadeus](https://developers.amadeus.com/) or [OAG](https://www.oag.com/flight-data-sets) API client |
| Live event logistics | Replace `src/api/events.py` with a Cvent / Eventforce REST API client |
| Multi-event support | Add an event selector in the sidebar; parameterise all API calls |
| Client authentication | Add `streamlit-authenticator` or deploy behind an OAuth proxy |
| Historical risk trends | Persist risk snapshots to a lightweight SQLite or Supabase DB |
| Notifications | Add a webhook call in `report_generator.py` to post the brief to Slack or email |
| LLM-enhanced brief | Swap the rule-based generator for a Claude / GPT call with structured prompting |
| White-labelling | Override colours and logos via Streamlit theming (`~/.streamlit/config.toml`) |

---

## Why This Is Relevant for Event Management Companies

1. **No data lock-in**: the stateless API architecture means a client can onboard without sharing proprietary guest lists or financial data.
2. **Composable**: each `src/api/` module is an independent adapter — swapping a data source requires changing one file.
3. **Auditable AI**: the risk score and report are deterministic, not a black box — important for enterprise and government clients.
4. **Demo-ready in 2 minutes**: the sidebar defaults produce a complete, realistic dashboard the moment the app loads.
5. **Production path is clear**: the mock modules serve as documented contracts for future real integrations.

---

## Tech Stack

- **Python 3.10+**
- **Streamlit ≥ 1.28** — dashboard framework
- **Plotly** — interactive charts (gauge, radar, line, bar)
- **pandas** — data shaping
- **requests** — HTTP API calls
- **python-dotenv** — environment variable support (ready for future secrets)
