# SmartGrid-AI: Predictive Resilience & Arbitrage Platform

[![CI Build](https://img.shields.io/github/actions/workflow/status/dvouna/grid_twin_virtual_power_plant-/ci.yml?label=CI%20Build)](https://github.com/dvouna/grid_twin_virtual_power_plant-/actions)
[![Unit Tests](https://img.shields.io/github/actions/workflow/status/dvouna/grid_twin_virtual_power_plant-/tests.yml?label=Unit%20Tests)](https://github.com/dvouna/grid_twin_virtual_power_plant-/actions)
[![Codecov](https://img.shields.io/codecov/c/github/dvouna/grid_twin_virtual_power_plant-)](https://codecov.io/gh/dvouna/grid_twin_virtual_power_plant-)
[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue)](https://www.python.org/)
[![Docker Ready](https://img.shields.io/badge/docker-ready-0db7ed)](https://www.docker.com/)
[![Status](https://img.shields.io/badge/status-active-success)](#)
[![Contributions Welcome](https://img.shields.io/badge/contributions-welcome-orange)](#)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](https://opensource.org/licenses/MIT)

SmartGrid‑AI is an intelligent virtual power plant (VPP) platform that transforms raw grid telemetry into real‑time operational decisions. It blends streaming ingestion, stateful feature engineering, predictive modeling, and autonomous control agents to stabilize the grid and optimize economic outcomes.

## 🌐 A. Core Capabilities
#### 1. Real-Time Gride Intelligence 
- Continuous ingestion of Net Load, Solar Generation, and related telemetry
- Stateful feature engineering with temporal lags, rolling statistics, and interaction terms
- Predictive modeling to detect instability, ramps, and arbitrage opportunities

#### 2. MCP-Driven Decision Engine ("The Brain")
Hosted on an MCP server, the SmartGrid‑AI agent can:
- Forecast short‑term load changes
- Trigger resilience actions (e.g., dispatch peakers or batteries)
- Execute arbitrage strategies (buy low, sell high)
- Reason over grid state and call tools autonomously

#### 3. Autonomous Controls Agents 
- ***Grid Response Actor***: Detects instability events and dispatches assets to maintain frequency and avoid penalties.
- ***Arbitrage Trader***: Executes charge/discharge cycles based on predicted price differentials.

## 🧱 B. System Architecture 
**1. High-Level Flow**
```Code
[Grid Data] 
   → [InfluxDB] 
   → [Feature Store] 
   → [MCP Agent] 
   → [Response & Trading Agents] 
   → [Grid Output]
```

**2. Detailed Architecture** 
<pre>
graph TD

classDef infra fill:#FFF2CC,stroke:#D6B656,stroke-width:2px;
classDef ai fill:#EAD1DC,stroke:#741B47,stroke-width:2px;

subgraph "Ingestion"
    CSV[Historical Data] --> Producer(Producer.py)
    Producer --> RP((Redpanda Broker)):::infra
end

subgraph "Intelligence"
    RP --> Consumer(Consumer.py)

    subgraph "In-Stream ML"
        Consumer --> FE[Feature Engineering]
        FE --> XGB[XGBoost Model]
    end
end

subgraph "Storage & Viz"
    XGB --> IDB[(InfluxDB)]
    IDB --> Grafana(Grafana Dashboards):::infra
end

subgraph "Control & Agents"
    IDB --> Actor(Grid Actor)
    IDB --> Trader(Arbitrage Trader)
    IDB --> MCP(MCP Server):::ai
    AI[AI Agent] <--> MCP
end
</pre> 

## 🧠 C. Feature Engineering: The Stateful Intelligence Layer 
Real‑time grid data is noisy and insufficient on its own. The platform uses a stateful feature pipeline to transform raw telemetry into a rich predictive feature space. 

### 1. Cyclical Time Encoding 
To preserve the circular nature of time:
<pre>
### 🔄 Cyclical Time Encoding
To ensure the model understands the periodic nature of time, we transform the hourly data using sine and cosine encodings:

$$\text{Hour}_{sin} = \sin\left(\frac{2\pi \cdot \text{Hour}}{24}\right)$$
$$\text{Hour}_{cos} = \cos\left(\frac{2\pi \cdot \text{Hour}}{24}\right)$$
</pre>

### 2. Temporal Logs
A rolling buffer (Python deque) maintains the last 50 observations:
- 𝐿𝑡−1 … 𝐿𝑡−12 capture short‑term momentum
- Enables autoregressive reasoning about ramps and volatility

### 3. Rolling Window Statistics 
Used to smooth transient spikes:
- Rolling mean (baseline trend)
- Rolling standard deviation (local volatility)

### 4. Grid Interaction Features
Captures non‑linear system behavior:
- Renewable Penetration Ratio
- Net Load Gradient
- Combined indicators for critical ramp detection


## C. 🛠 Technical Stack
| Layer | Technology |
| :--- | :--- |
| **Streaming** | Redpanda (Kafka-compatible) |
| **Storage** | InfluxDB (time-series) |
| **AI/ML** | XGBoost, Scikit-Learn, Pandas |
| **Control** | Python Agents |
| **Communication** | MCP (Model Context Protocol) |
| **Visualization** | Grafana |
| **Virtualization** | Docker, Docker Compose |


## D. Getting Started
### 1. Prerequisites
- Python 3.8+
- InfluxDB running locally or remotely

### 2. Installation 
<pre>git clone https://github.com/dvouna/grid_twin_virtual_power_plant-
cd grid_twin_virtual_power_plant-
pip install -r requirements.txt
</pre>

## Running the System
### 1. Start Core Services
<pre># InfluxDB (if not already running)
# MCP Server (The Brain)
python src/vpp/mcp/mcp_server.py
</pre> 

### 2. Run Intelligence Pipeline
<pre>python src/vpp/intelligence/producer.py
python src/vpp/intelligence/consumer.py
python src/vpp/intelligence/feature_engineering.py
python src/vpp/intelligence/xgboost.py
</pre>

### 3. Verification 
- Check console logs for agent activity
- Query InfluxDB to confirm data ingestion
- View dashboards in Grafana

```
src/vpp/
│
├── intelligence/
│   ├── producer.py
│   ├── consumer.py
│   ├── feature_engineering.py
│   └── xgboost.py
│
├── agents/
│   ├── grid_response_actor.py
│   └── arbitrage_trader.py
│
└── mcp/
    └── mcp_server.py
```
**Module Responsibilties**
```
Module Purpose 
producer.py	Streams historical or synthetic grid data into Redpanda
consumer.py	Consumes messages, applies feature engineering, triggers model inference
feature_engineering.py	Stateful pipeline: lags, rolling stats, cyclical encodings, interaction terms
xgboost.py	Loads model, performs predictions, writes results to InfluxDB
grid_response_actor.py	Detects instability events, dispatches peakers/batteries
arbitrage_trader.py	Executes buy‑low/sell‑high cycles based on predicted deltas
mcp_server.py	Hosts the SmartGrid‑AI agent and exposes MCP tools
```

### 3. Architecture 
```
[Grid Data]
   → [Redpanda Producer]
   → [Redpanda Broker]
   → [Consumer + Feature Engineering]
   → [XGBoost Prediction]
   → [InfluxDB]
   → [MCP Agent + Control Actors]
   → [Grid Output]
```

```
graph TD

classDef infra fill:#FFF2CC,stroke:#D6B656,stroke-width:2px;
classDef ai fill:#EAD1DC,stroke:#741B47,stroke-width:2px;

subgraph "Ingestion"
    CSV[Historical Data] --> Producer(Producer.py)
    Producer --> RP((Redpanda Broker)):::infra
end

subgraph "Intelligence"
    RP --> Consumer(Consumer.py)

    subgraph "In-Stream ML"
        Consumer --> FE[Feature Engineering Class]
        FE --> XGB[XGBoost Model]
    end
end

subgraph "Storage & Viz"
    XGB --> IDB[(InfluxDB)]
    IDB --> Grafana(Grafana Dashboards):::infra
end

subgraph "Control & Agents"
    IDB --> Actor(Grid Actor)
    IDB --> Trader(Arbitrage Trader)
    IDB --> MCP(MCP Server):::ai
    AI[AI Agent] <--> MCP
end
```


Autonomous resilience and arbitrage agents
python src/vpp/intelligence/producer.py
python src/vpp/intelligence/consumer.py
python src/vpp/intelligence/feature_engineering.py
python src/vpp/intelligence/xgboost.py   
</pre>

The system functions as a closed‑loop intelligence layer:
Grid → Ingestion → Feature Store → AI Decision Engine → Control Agents → Grid

## System Architecture 
### High Level Flow 
[Grid Data] 
   → [InfluxDB] 
   → [Feature Store] 
   → [MCP Agent] 
   → [Response & Trading Agents] 
   → [Grid Output]




9. Roadmap
  - GCP
  - FDIA detection via predictive residuals
  - RAG‑based compliance reasoning
