# VPP Feature Roadmap

> Reference document for future enhancements to the Grid Twin Virtual Power Plant.
> Created: 2026-02-11

---

## 🏗️ Architecture & Reliability

| Feature | Why It Matters | Priority |
|---|---|---|
| **Model retraining pipeline** | Current model trains on static CSV. Add a scheduled Cloud Run job that retrains on fresh InfluxDB data, evaluates against a holdout set, and hot-swaps the model via GCS. | Medium |
| **Alerting & incident response** | Wire Grafana or Cloud Monitoring to Slack/PagerDuty for `CRITICAL` ramp events — don't rely on terminal output. | High |
| **Dead letter queue** | Failed Kafka messages are logged and dropped. Add a DLQ topic for retry and forensic analysis. | Medium |

---

## 🤖 ML & Prediction

| Feature | Why It Matters | Priority |
|---|---|---|
| **Confidence intervals** | XGBoost point predictions don't convey uncertainty. Use quantile regression (`objective: reg:quantileerror`) for P10/P50/P90 bounds — critical for risk-based dispatch. | ⭐ High |
| **Multi-horizon forecasting** | Currently predicts 30-min ahead. Add 1-hour and 4-hour horizons for battery scheduling and market bidding. | Medium |
| **Anomaly detection** | Flag sensor drift or data quality issues (e.g., solar reading at midnight) before they corrupt predictions. Isolation forest on the feature store. | Medium |

---

## ⚡ Agent Intelligence

| Feature | Why It Matters | Priority |
|---|---|---|
| **Battery optimization agent** | `B_SOC` data is underutilized. Optimize charge/discharge cycles based on predicted ramps, time-of-use pricing, and SOC constraints. | ⭐ High |
| **Market bidding agent** | Use predictions + confidence intervals to calculate optimal bid prices for day-ahead and real-time energy markets. This is where VPPs monetize. | High |
| **Multi-agent coordination** | Arbitrage trader and grid response actor operate independently. Add a coordinator to prevent conflicting actions (e.g., buying while another sells). | Medium |

---

## 📊 Observability & UX

| Feature | Why It Matters | Priority |
|---|---|---|
| **Live Grafana dashboard** | Pre-built panels: predicted vs actual load, ramp severity heatmap, battery SOC timeline, agent action log. Ship as provisioned JSON. | ⭐ High |
| **MCP tool: `query_historical`** | Let Claude query InfluxDB for historical patterns — *"How did the grid perform last Tuesday at 3pm?"* | Medium |
| **MCP tool: `simulate_scenario`** | What-if analysis — *"What happens if solar drops 50% in the next hour?"* — without requiring live data. | Medium |

---

## 🔒 Production Hardening

| Feature | Why It Matters | Priority |
|---|---|---|
| **API authentication for MCP** | Cloud Run uses `--no-allow-unauthenticated`, but the MCP SSE endpoint needs a proper auth flow (API keys or OAuth) for Claude Desktop. | High |
| **Feature drift monitoring** | Track input feature distributions over time. If `Solar_kw` suddenly shifts, the model's accuracy degrades silently. | Medium |
| **Canary deployments** | CI/CD deploys directly. Add traffic splitting (10% canary → 100% promotion) to reduce blast radius. | Low |

---

## 🎯 Recommended Starting Order

1. **Confidence intervals** — transforms predictions from point estimates to probability ranges, changing how agents make decisions.
2. **Battery optimization agent** — the biggest untapped value; SOC-aware dispatch is the core VPP business case.
3. **Live Grafana dashboard** — all data flows into InfluxDB already; a pre-built dashboard makes the system tangible and demo-ready.
