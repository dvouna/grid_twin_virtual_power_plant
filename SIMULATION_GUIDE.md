# ⚡ Grid Twin Simulation Guide

This guide provides a step-by-step roadmap to running the Virtual Power Plant (VPP) simulation locally.

## 1. Prerequisites

Ensure you have the following installed:

- **Docker & Docker Compose**: For running the infrastructure (Redpanda, InfluxDB, Grafana).
- **Python 3.11+**: For running the producer and consumer scripts.
- **Git**: To clone/manage the repository.

## 2. Infrastructure Setup

The project uses Docker Compose to spin up the necessary services.

1. **Start the Services**:

    ```bash
    docker-compose up -d
    ```

    This starts:
    - **Redpanda** (Kafka) on port `9092`.
    - **Redpanda Console** on port `8080` (<http://localhost:8080>).
    - **InfluxDB** on port `8086`.
    - **Grafana** on port `3000`.

2. **Verify Services**:
    - Check if containers are running: `docker-compose ps`
    - Access Redpanda Console: [http://localhost:8080](http://localhost:8080)

## 3. Environment Configuration

You **must** configure your environment variables for the Python scripts to work securely.

1. **Create `.env` file**:
    Copy the example file to create your local configuration.

    ```bash
    cp .env.example .env
    ```

2. **Update `.env` values**:
    Open `.env` and assign local InfluxDB credentials. The producer and consumer depend on these values.

    *Default Docker Values (found in `docker-compose.yml`):*

    ```properties
    INFLUX_URL=http://localhost:8086
    INFLUX_TOKEN=smg!indb25
    INFLUX_ORG=myorg
    INFLUX_BUCKET=energy
    ```

    > **Note**: If you changed the password/token in `docker-compose.yml`, must update `.env` accordingly.

## 4. Running the Simulation

The simulation consists of a Producer (generating data) and a Consumer (processing data/ML predictions).

### Terminal 1: The Consumer (ML Processor)

Start the consumer first so it's ready to receive data.

```bash
# Activate your virtual environment if you have one
# source .venv/bin/activate

python scripts/consumer_ml_local.py
```

*You should see: `🚀 ML Consumer started... Listening to grid-sensor-stream...`*

### Terminal 2: The Producer (Data Generator)

Start the data stream.

```bash
python scripts/producer.py
```

*You should see: `🚀 Starting 30s Stream...`*

## 5. Monitoring & Verification

- **Terminal Output**: Watch the Consumer terminal for "Predicted Change" logs.
- **Redpanda Console**: Go to [http://localhost:8080](http://localhost:8080) -> Topics -> `grid-sensor-stream` to see live messages.
- **InfluxDB**: Check the `energy` bucket for `ml_predictions` measurement.

## 6. Troubleshooting

- **`ValueError: INFLUX_TOKEN not found`**: Ensure you created the `.env` file and it contains `INFLUX_TOKEN`.
- **Connection Refused**: Ensure Docker containers are running (`docker-compose ps`).
