<div align="center">

# ⚡ SmartGrid-AI

### *Intelligent Virtual Power Plant Platform*

**Real-time grid intelligence powered by ML, streaming data, and autonomous agents**

[![CI/CD Pipeline](https://img.shields.io/github/actions/workflow/status/dvouna/grid_twin_virtual_power_plant-/deploy-cloud-run.yml?label=CI%2FCD&logo=github-actions&logoColor=white)](https://github.com/dvouna/grid_twin_virtual_power_plant-/actions)
[![Python](https://img.shields.io/badge/python-3.11-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Cloud Run](https://img.shields.io/badge/Google_Cloud-Run-4285F4?logo=google-cloud&logoColor=white)](https://cloud.google.com/run)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Status](https://img.shields.io/badge/status-production-success?logo=statuspage&logoColor=white)](#-system-architecture)

[Features](#-key-features) • [Architecture](#-system-architecture) • [Quick Start](#-quick-start) • [Documentation](#-technical-deep-dive) • [Roadmap](#-roadmap)

</div>

---

## 🎯 Overview

SmartGrid-AI is a production-ready **Virtual Power Plant (VPP)** platform that transforms raw grid telemetry into intelligent, real-time operational decisions. By combining streaming data ingestion, stateful feature engineering, predictive ML models, and autonomous control agents, it enables:

- **Grid Stabilization** – Detect and respond to frequency instabilities in real-time
- **Economic Optimization** – Execute energy arbitrage strategies (buy low, sell high)
- **Predictive Intelligence** – Forecast load ramps and renewable generation patterns
- **Autonomous Operations** – AI agents that reason over grid state and take action

---

## ✨ Key Features

<table>
<tr>
<td width="50%">

### 🧠 **AI-Powered Decision Engine**

- MCP-based "brain" hosted on Cloud Run
- Natural language interface via Claude Desktop
- Autonomous reasoning and tool execution
- Real-time load forecasting and anomaly detection

</td>
<td width="50%">

### 📊 **Real-Time Intelligence**

- Streaming ingestion from Redpanda/Kafka
- Stateful feature engineering (160+ features)
- XGBoost predictive models
- InfluxDB time-series storage

</td>
</tr>
<tr>
<td width="50%">

### 🤖 **Autonomous Agents**

- **Grid Response Actor** – Dispatch batteries to stabilize frequency
- **Arbitrage Trader** – Execute charge/discharge cycles for profit
- **Predictive Consumer** – ML-driven load forecasting

</td>
<td width="50%">

### 🚀 **Production-Grade Infrastructure**

- Multi-environment CI/CD (staging → production)
- Workload Identity Federation (WIF) security
- Secret management via GCP Secret Manager
- Automated health checks and rollbacks

</td>
</tr>
</table>

---

## 🏗️ System Architecture

### High-Level Data Flow

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'primaryColor': '#4285F4', 'primaryTextColor': '#fff', 'primaryBorderColor': '#1a73e8', 'lineColor': '#5f6368', 'secondaryColor': '#34A853', 'tertiaryColor': '#FBBC04'}}}%%
graph LR
    A[🔌 Grid Sensors] -->|Telemetry| B[📨 Redpanda Broker]
    B -->|Stream| C[🌉 Redpanda Connect]
    C -->|Bridge| D[(☁️ InfluxDB Cloud)]
    D -->|Query| E[🧠 MCP Server]
    E -->|Tools| F[🤖 AI Agents]
    E -->|Interface| G[💬 Claude Desktop]
    
    style A fill:#EA4335,stroke:#c5221f,color:#fff
    style B fill:#FBBC04,stroke:#f9ab00,color:#000
    style C fill:#34A853,stroke:#0f9d58,color:#fff
    style D fill:#4285F4,stroke:#1a73e8,color:#fff
    style E fill:#9334E9,stroke:#7c3aed,color:#fff
    style F fill:#EC4899,stroke:#db2777,color:#fff
    style G fill:#8B5CF6,stroke:#7c3aed,color:#fff
```

### Microservices Architecture

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'primaryColor': '#007ACC', 'edgeLabelBackground':'#ffffff', 'tertiaryColor': '#E6F3FF'}}}%%
graph TD
    classDef storage fill:#D9EAD3,stroke:#274E13,stroke-width:2px;
    classDef infra fill:#FFF2CC,stroke:#D6B656,stroke-width:2px;
    classDef python fill:#E6F3FF,stroke:#007ACC,stroke-width:2px;
    classDef ai fill:#EAD1DC,stroke:#741B47,stroke-width:2px;

    subgraph "📥 Data Ingestion"
        CSV[Historical Data] --> Producer(Producer.py):::python
        Producer -->|5s pulse| RP((Redpanda)):::infra
    end

    subgraph "🧠 Intelligence Layer"
        RP -->|grid-stream| Consumer(Consumer ML):::python
        RP -->|grid-stream| Actor(Response Actor):::python
        RP -->|grid-stream| Trader(Arbitrage Trader):::python

        subgraph "⚙️ Feature Engineering"
            Consumer --> FE[160+ Features]
            FE --> XGB[XGBoost Model]
            XGB -->|Predictions| Consumer
        end
    end

    subgraph "💾 Storage & Viz"
        Consumer --> IDB[(InfluxDB)]:::storage
        Actor --> IDB
        Trader --> IDB
        IDB --> Grafana(Grafana):::infra
    end

    subgraph "🤖 MCP Interface"
        IDB -.->|Resources| MCP(MCP Server):::ai
        XGB -.->|Tools| MCP
        Human[👤 User/Agent] <-->|NL Queries| MCP
    end
```

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.11+**
- **InfluxDB** (local or cloud)
- **Redpanda/Kafka** (optional, for streaming)
- **GCP Account** (for Cloud Run deployment)

### Installation

```bash
# Clone the repository
git clone https://github.com/dvouna/grid_twin_virtual_power_plant-.git
cd grid_twin_virtual_power_plant-

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Running Locally

```powershell
# 1. Start the MCP Server (The Brain)
$env:PYTHONPATH="src"
python src/vpp/mcp/mcp_server.py

# 2. Start Autonomous Agents (in separate terminals)
python -m vpp.agents.grid_response_actor
python -m vpp.agents.arbitrage_trader

# 3. Start Data Pipeline
python -m vpp.intelligence.producer
python -m vpp.intelligence.consumer
```

### Deploying to Cloud Run

The project includes a production-ready CI/CD pipeline:

1. **Push to `develop`** → Auto-deploys to **staging**
2. **Merge to `main`** → Deploys to **staging** → **production** (with approval)

```bash
# Trigger deployment
git push origin develop  # Staging
git push origin main     # Production (after staging validation)
```

---

## 📁 Project Structure

```
grid_twin_virtual_power_plant-/
├── .github/workflows/       # CI/CD pipelines
│   └── deploy-cloud-run.yml
├── src/vpp/
│   ├── intelligence/        # ML & streaming pipeline
│   │   ├── producer.py      # Data ingestion
│   │   ├── consumer_ml.py   # ML inference consumer
│   │   └── GridFeatureStore.py  # Feature engineering
│   ├── agents/              # Autonomous control agents
│   │   ├── grid_response_actor.py
│   │   └── arbitrage_trader.py
│   └── mcp/                 # MCP server (the "brain")
│       └── mcp_server.py
├── tests/                   # Unit & integration tests
├── models/                  # Trained ML models
├── data/                    # Historical grid data
├── Dockerfile               # Container definition
└── requirements.txt         # Python dependencies
```

---

## 🔬 Technical Deep Dive

### Feature Engineering Pipeline

SmartGrid-AI transforms raw telemetry into **160+ engineered features** using:

#### 1. **Cyclical Time Encoding**

Preserves temporal periodicity:
$$\text{Hour}_{sin} = \sin\left(\frac{2\pi \cdot \text{Hour}}{24}\right), \quad \text{Hour}_{cos} = \cos\left(\frac{2\pi \cdot \text{Hour}}{24}\right)$$

#### 2. **Temporal Lags**

Rolling buffer (50 observations) captures momentum:

- $L_{t-1}$ to $L_{t-12}$ for short-term patterns
- Enables autoregressive forecasting

#### 3. **Rolling Statistics**

- **Mean** – Baseline trend
- **Std Dev** – Local volatility

#### 4. **Grid Interaction Features**

- **Renewable Penetration**: $\frac{\text{Solar} + \text{Wind}}{\text{Gross Load}}$
- **Net Load Gradient**: Instantaneous rate of change

### Technology Stack

| **Category** | **Technology** |
|:-------------|:---------------|
| **Streaming** | Redpanda (Kafka-compatible) |
| **Data Bridge** | Redpanda Connect (Benthos) |
| **Cloud Platform** | Google Cloud Run (Serverless) |
| **Compute** | Google Compute Engine (VMs) |
| **Security** | Workload Identity Federation, Secret Manager |
| **Storage** | InfluxDB Cloud (Time-Series DB) |
| **ML/AI** | XGBoost, Scikit-Learn, FastMCP |
| **CI/CD** | GitHub Actions |
| **Monitoring** | Grafana, Cloud Logging |

---

## 🧪 Testing

```bash
# Run unit tests (excludes integration tests)
pytest -m "not integration" -v

# Run linter
ruff check src/ tests/ --output-format=github

# Run all tests (requires Redpanda + InfluxDB)
pytest -v
```

---

## 📊 CI/CD Pipeline

The project implements a **staging-before-production** deployment strategy:

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'primaryColor': '#4285F4'}}}%%
graph LR
    A[📝 Push Code] --> B[🧪 Run Tests]
    B --> C[🚀 Deploy Staging]
    C --> D{✅ Staging OK?}
    D -->|Yes| E[🔒 Manual Approval]
    D -->|No| F[❌ Block Production]
    E --> G[🌍 Deploy Production]
    
    style A fill:#FBBC04,stroke:#f9ab00,color:#000
    style B fill:#34A853,stroke:#0f9d58,color:#fff
    style C fill:#4285F4,stroke:#1a73e8,color:#fff
    style E fill:#EA4335,stroke:#c5221f,color:#fff
    style G fill:#9334E9,stroke:#7c3aed,color:#fff
```

**Key Features:**

- ✅ Automated testing (linting + unit tests)
- ✅ Staging validation before production
- ✅ Manual approval gates
- ✅ Health checks and rollback capability
- ✅ Workload Identity Federation (no service account keys)

---

## 🗺️ Roadmap

### 🔜 Near-Term

- [ ] **Enhanced Monitoring** – Prometheus metrics + alerting
- [ ] **Load Testing** – Stress test MCP server under high query load
- [ ] **Multi-Region Deployment** – HA across GCP regions

### 🔮 Future Vision

- [ ] **Digital Twin Integration** – Physics-based grid simulation
- [ ] **Cybersecurity Module** – False Data Injection Attack (FDIA) detection
- [ ] **Cognitive Ops (RAG)** – AI agent cross-references NERC/FERC regulations
- [ ] **Federated Learning** – Privacy-preserving multi-utility collaboration

---

## 🤝 Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- **Google Cloud Platform** – Cloud Run, Secret Manager, Workload Identity
- **Redpanda** – High-performance streaming platform
- **InfluxDB** – Time-series database
- **Anthropic** – Claude AI and MCP protocol
- **XGBoost** – Gradient boosting framework

---

<div align="center">

**For a smarter, more resilient grid that works for all**

[⬆ Back to Top](#-smartgrid-ai)

</div>
