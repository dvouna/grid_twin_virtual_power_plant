# Copilot Instructions for AI Coding Agents

## Project Overview
This project is a data streaming and analytics stack for energy demand data, using Redpanda (Kafka-compatible), InfluxDB, and Grafana, orchestrated via Docker Compose. A Python producer script streams data from a CSV file into Redpanda.

## Architecture & Data Flow
- **Redpanda**: Kafka-compatible broker for ingesting streaming data.
- **Console**: Redpanda Console for cluster management and topic inspection.
- **InfluxDB**: Time-series database for storing processed data.
- **Grafana**: Visualization dashboard, connects to InfluxDB.
- **Producer (Python)**: Reads `energy_demand.csv` and streams rows as JSON to the `energy-demand-raw` topic in Redpanda.

## Key Files
- `docker-compose.yml`: Defines all services, ports, and volumes.
- `producer.py`: Streams CSV data to Redpanda. Expects `energy_demand.csv` in the same directory.

## Developer Workflows
- **Start stack**: `docker-compose up -d` (from project root)
- **Stop stack**: `docker-compose down`
- **Run producer**: Ensure Redpanda is running, then execute `python producer.py` (requires `confluent_kafka` and `pandas`)
- **CSV file**: Place `energy_demand.csv` in the project root with columns: `timestamp`, `demand_mw`.

## Conventions & Patterns
- All inter-service communication uses Docker Compose service names (e.g., `redpanda:29092`).
- Python producer logs to console and flushes every 100 messages.
- Environment variables for InfluxDB and Grafana are set in `docker-compose.yml`.
- Change default passwords/tokens before production use.

## Integration Points
- Redpanda Console is available at [http://localhost:8080](http://localhost:8080) for topic inspection.
- Grafana is available at [http://localhost:3000](http://localhost:3000) (default admin password: `adminpassword`).
- InfluxDB is available at [http://localhost:8086](http://localhost:8086).

## Example: Adding a New Producer
- Use the same Redpanda broker address as in `producer.py`.
- Produce to a new topic as needed; update `docker-compose.yml` if new services are required.

## Troubleshooting
- If `producer.py` fails, check that Redpanda is running and ports are mapped.
- Use Redpanda Console to verify topic existence and message flow.

---
For further conventions or questions, review `docker-compose.yml` and `producer.py` for up-to-date patterns.
