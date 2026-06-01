# Architecture — Luxury Event Intelligence Dashboard

## Conceptual Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                       EXTERNAL APIs                             │
│                                                                 │
│  Open-Meteo (free, no key)    open.er-api.com (free, no key)   │
│  Geneva & Doha forecast       CHF exchange rates                │
└────────────────────┬────────────────────────┬───────────────────┘
                     │                        │
                     ▼                        ▼
┌─────────────────────────────────────────────────────────────────┐
│                    PYTHON API LAYER  (src/api/)                 │
│                                                                 │
│  weather.py          currency.py       flights.py  events.py   │
│  Open-Meteo client   ER-API client     Mock data   Mock data   │
│  + seasonal fallback + rate fallback   (labelled)  (labelled)  │
│  @st.cache_data      @st.cache_data                            │
└────────────────────────────────┬────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│              ANALYTICS LAYER  (src/analytics/)                  │
│                                                                 │
│  risk_score.py                  report_generator.py            │
│  Weighted 0–100 composite       Rule-based markdown brief      │
│  score with per-factor          (deterministic, no LLM)        │
│  breakdown and explanations                                     │
└────────────────────────────────┬────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                STREAMLIT DASHBOARD  (app.py)                    │
│                                                                 │
│  1. Executive Summary   (st.metric KPI cards)                  │
│  2. Weather & Climate   (Plotly line + bar charts, tabs)       │
│  3. Currency & Budget   (exchange table, bar chart)            │
│  4. Travel Readiness    (mock flight intelligence)             │
│  5. Event Logistics     (radar + supplier bar, mock)           │
│  6. Risk Score          (Plotly gauge + factor breakdown)      │
│  7. Executive Brief     (auto-generated markdown, download)    │
└─────────────────────────────────────────────────────────────────┘
```

## Key Design Principles

| Principle | Implementation |
|-----------|---------------|
| No client data stored | All inputs are transient Streamlit widget values |
| Live where free APIs exist | Open-Meteo (weather), open.er-api.com (FX rates) |
| Honest about mock data | Every mock section is labelled with a MOCK badge |
| Graceful degradation | API failures fall back to hardcoded seasonal / rate data |
| Transparent risk logic | All weights and thresholds are constants in `risk_score.py` |
| Auditable reporting | Brief generator is rule-based Python, no LLM |
| Deployment-ready | No secrets required; runs on Streamlit Cloud or Render |

## File Structure

```
dashboard/
├── app.py                          # Streamlit entry point
├── requirements.txt
├── .gitignore
├── assets/
│   └── architecture.md             # This file
└── src/
    ├── api/
    │   ├── weather.py              # Open-Meteo client + seasonal fallback
    │   ├── currency.py             # open.er-api.com client + rate fallback
    │   ├── flights.py              # Mock flight intelligence (GVA→DOH)
    │   └── events.py               # Mock event logistics
    ├── analytics/
    │   ├── risk_score.py           # Weighted composite risk engine
    │   └── report_generator.py     # Rule-based executive brief generator
    └── utils/
        └── formatting.py           # Currency, hour, risk-level formatters
```
