# SmartGrid-AI: Predictive Resilience & Arbitrage Platform

<pre>
Bash
python src/vpp/intelligence/producer.py
python src/vpp/intelligence/consumer.py
python src/vpp/intelligence/feature_engineering.py
python src/vpp/intelligence/xgboost.py
</pre>

Overview
SmartGrid-AI is an advanced energy management system that bridges the gap between raw grid data and actionable intelligence. It combines real-time monitoring, predictive analytics, and autonomous control to maintain grid stability while maximizing economic efficiency.

Core Architecture
The system operates as a closed-loop ecosystem where data flows from the grid, through an AI decision engine, and back to the grid via control agents.

1. Data Ingestion & Feature Engineering
Raw data from the grid (Net Load, Solar Generation) is collected and transformed into predictive features.

Key Metrics:

Net_Load_kW: The current power imbalance.
Predicted_30min_Change: The forecasted change in load over the next 30 minutes.
Feature Store: A time-series buffer that maintains the last 50 observations to provide context for the predictive model.
2. The "Brain": MCP Decision Engine
We utilize a Micro-Computer Protocol (MCP) server to host our "SmartGrid-AI" agent. This allows the agent to reason over the grid data and call specific tools to execute actions.

Key Capabilities:

Predictive Analysis: Forecasts grid instability (sudden ramps or drops).
Resilience Control: Dispatches Gas Peaker Plants or Battery Storage to counteract predicted changes.
Arbitrage Trading: Monitors price differentials to buy low (during surplus) and sell high (during shortage).
3. Autonomous Agents
Grid Response Actor: Monitors the grid for "Instability Events" (rapid changes in load). If detected, it automatically dispatches generation assets to stabilize the grid and prevent penalties.
Arbitrage Trader: A financial agent that uses the predictive model to execute "Buy Low, Sell High" strategies with the battery storage system.
Technical Stack
Data Layer: InfluxDB (Time-Series Database)
AI/ML: Python (Scikit-learn, Pandas)
Control Logic: Python Agents
Communication: MCP (Micro-Computer Protocol)
Getting Started
Prerequisites
Ensure you have Python 3.8+ installed.

Installation
Clone the repository:

Bash
git clone <repository-url>
cd atl_pr
Install dependencies:

Bash
pip install -r requirements.txt
Running the System
Start the InfluxDB server (if not already running).

Start the MCP Server (The Brain):

Bash
python src/vpp/mcp/mcp_server.py
Start the Grid Response Actor:

Bash
python src/vpp/agents/grid_response_actor.py
Start the Arbitrage Trader:

Bash
python src/vpp/agents/arbitrage_trader.py
Verification
Check the console output for logs from the agents.

Verify data is being written to InfluxDB by querying the database.

Architecture Diagram
[Grid Data] -> [InfluxDB] -> [Feature Store] -> [MCP Agent] -> [Response/Trading Agents] -> [Grid Output]

## System Architecture

[Grid Data] -> [InfluxDB] -> [Feature Store] -> [MCP Agent] -> [Response/Trading Agents] -> [Grid Output]

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

## Running the System

Start the InfluxDB server (if not already running).

Start the MCP Server (The Brain):

Bash
python src/vpp/mcp/mcp_server.py
Start the Grid Response Actor:

Bash
python src/vpp/agents/grid_response_actor.py
Start the Arbitrage Trader:

Bash
python src/vpp/agents/arbitrage_trader.py

## Run the Intelligence Pipeline

python src/vpp/intelligence/producer.py
python src/vpp/intelligence/consumer.py
python src/vpp/intelligence/feature_engineering.py
python src/vpp/intelligence/xgboost.py

## Run the Control & Agents

python src/vpp/agents/grid_response_actor.py
python src/vpp/agents/arbitrage_trader.py
python src/vpp/mcp/mcp_server.py

## Future Roadmap

Cloud Evolution: Migration to AWS MSK for managed streaming and Lambda for serverless inference.

Cybersecurity: Implementation of False Data Injection Attack (FDIA) detection using predictive residuals.

Cognitive Ops (RAG): Integrating Retrieval-Augmented Generation to allow the AI agent to cross-reference grid actions with NERC/FERC regulatory PDF manuals.

Tech Stack

- Streaming: Redpanda (Kafka Compatible)
- Storage: InfluxDB (Time-Series Database)
- AI/ML: XGBoost, Scikit-Learn, Pandas, MCP SDK
- Control: Python Agents
- Communication: MCP (Micro-Computer Protocol)
- Virtualization: Docker, Docker Compose, GitHub Actions

🧠 Feature Engineering: The Stateful Intelligence Layer
In a real-time smart grid, raw sensor data is often too "noisy" and "flat" for accurate forecasting. This project utilizes a Stateful Feature Pipeline within the consumer.py script to transform simple telemetry into a high-dimensional feature space.

1. Cyclical Time EncodingsTime is not a linear progression from 0 to 23; it is circular. To prevent the model from seeing "Hour 23" as mathematically distant from "Hour 0," we project time onto a 2D coordinate system using trigonometric transformations:$$Hour_{sin} = \sin\left(\frac{2\pi \cdot Hour}{24}\right)$$$$Hour_{cos} = \cos\left(\frac{2\pi \cdot Hour}{24}\right)$$This ensures the model recognizes that 11:59 PM and 12:01 AM are adjacent, capturing the natural daily rhythm of the grid.

2. Temporal Lags ($t-n$)To capture the "momentum" of the grid, the pipeline maintains an in-memory buffer (using Python's collections.deque) to generate historical lags. These features allow the model to perform Auto-Regressive analysis:$L_{t-1}$ to $L_{t-12}$: Captures immediate short-term trends over the last minute (at a 5s pulse).Significance: These features inform the XGBoost model if the current ramp is accelerating or stabilizing.

3. Rolling Window StatisticsRaw electricity load is prone to transient spikes. We smooth these out using Rolling Statistics calculated over various horizons (e.g., 5-minute and 30-minute windows):Rolling Mean: Captures the moving baseline.Rolling Std Dev: Measures local volatility, signaling the model to "watch out" for unpredictable weather-driven solar shifts.

4. Grid Interaction FeaturesThe grid is a complex system of dependencies. We calculate Interaction Terms to highlight non-linear relationships:Renewable Penetration Ratio: $$\frac{Solar + Wind}{Gross Load}$$Net Load Gradient: The instantaneous rate of change between $t$ and $t-1$.Significance: A high penetration ratio combined with a high gradient is a leading indicator of a Critical Ramp Event.Feature Importance SummaryBy providing these engineered features, the XGBoost model can distinguish between a routine evening ramp and a catastrophic frequency excursion.

%%{init: {'theme': 'base', 'themeVariables': { 'primaryColor': '#007ACC', 'edgeLabelBackground':'#ffffff', 'tertiaryColor': '#E6F3FF'}}}%%
graph TD
    %% Define styles
    classDef storage fill:#D9EAD3,stroke:#274E13,stroke-width:2px;
    classDef infra fill:#FFF2CC,stroke:#D6B656,stroke-width:2px;
    classDef python fill:#E6F3FF,stroke:#007ACC,stroke-width:2px;
    classDef ai fill:#EAD1DC,stroke:#741B47,stroke-width:2px;

    subgraph "Data Ingestion Layer"
        CSV[Historical_Data.csv] -- "Read Row" --> Producer(Producer.py):::python
        Producer -- "Inject Current Timestamp (5s pulse)" --> RP((Redpanda Broker)):::infra
    end

    subgraph "Intelligence & Control Layer (Microservices)"
        RP -- "Sub: grid-stream" --> Consumer(Consumer.py):::python
        RP -- "Sub: grid-stream" --> Actor(Response_Actor.py):::python
        RP -- "Sub: grid-stream" --> Trader(Arbitrage_Trader.py):::python

        subgraph "In-Stream AI"
            Consumer -- "1. Buffer & Feature Engineer" --> FE[Stateful Features]
            FE -- "2. Inference Vector" --> XGB[XGBoost Model.ubj]
            XGB -- "3. Predicted Ramp (MW/min)" --> Consumer
        end
    end

    subgraph "Storage & Visualization Layer"
        Consumer -- "Write: Net Load + Predictions" --> IDB[(InfluxDB)]:::storage
        Actor -- "Write: Battery Actions" --> IDB
        Trader -- "Write: PnL & Trades" --> IDB
        IDB -- "Query: Flux" --> Grafana(Grafana Dashboards):::infra
    end

    subgraph "Agentic Interface Layer (MCP)"
        IDB -.->|"Read Resource (grid://status)"| MCP(MCP_Server.py):::ai
        XGB -.->|"Run Tool (predict_ramp)"| MCP
        Human[Human / AI Agent] <==>|"Natural Language Queries"| MCP
    end

    %% Define arrow styles for clarity
    linkStyle 4,5,6,7 stroke:#007ACC,stroke-width:2px,fill:none;
    linkStyle 11,12,13 stroke:#274E13,stroke-width:2px;
