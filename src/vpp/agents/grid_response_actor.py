import os
import time
import logging

from dotenv import load_dotenv
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
import requests
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

# Load environment variables from .env file
load_dotenv()

logger = logging.getLogger(__name__)

# InfluxDB Cloud Settings (Source from env for cloud readiness)
INFLUX_URL = os.getenv("INFLUX_CLOUD_URL", "https://us-east-1-1.aws.cloud2.influxdata.com")
INFLUX_TOKEN = os.getenv("INFLUX_CLOUD_TOKEN", "your-cloud-token-here")
INFLUX_ORG = os.getenv("INFLUX_CLOUD_ORG", "Energy Simulation")
INFLUX_BUCKET = os.getenv("INFLUX_CLOUD_BUCKET", "energy")

# Simulated asset capacities (kW)
GAS_PEAKER_CAPACITY_kW = 100000.0  # 100 MW
BATTERY_DISCHARGE_RATE_kW = 40000.0 # 40 MW
BAM_API_URL = os.getenv("BAM_API_URL", "http://localhost:8000")
BAM_API_KEY = os.getenv("BAM_API_KEY", "")
_BAM_HEADERS = {"X-BAM-API-Key": BAM_API_KEY} if BAM_API_KEY else {}

# --- Resilient BAM API helpers (Phase B) ---
_RETRY_POLICY = dict(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=4),
    retry=retry_if_exception_type((requests.exceptions.ConnectionError,
                                   requests.exceptions.Timeout)),
    reraise=False,
)

@retry(**_RETRY_POLICY)
def _bam_dispatch(payload: dict) -> dict:
    resp = requests.post(f"{BAM_API_URL}/dispatch", json=payload, headers=_BAM_HEADERS, timeout=5)
    resp.raise_for_status()
    return resp.json()

@retry(**_RETRY_POLICY)
def _bam_get_state() -> dict:
    resp = requests.get(f"{BAM_API_URL}/state", headers=_BAM_HEADERS, timeout=5)
    resp.raise_for_status()
    return resp.json()

@retry(**_RETRY_POLICY)
def _bam_pre_condition(payload: dict) -> dict:
    """C1: Triggers proactive battery charging via the BAM service."""
    resp = requests.post(f"{BAM_API_URL}/pre_condition", json=payload, headers=_BAM_HEADERS, timeout=5)
    resp.raise_for_status()
    return resp.json()

# --- NEW FINANCIAL CONSTANTS ---
# Prices are usually per MWh, so we convert to kWh pricing
SPOT_PRICE_PER_kWH = 0.05      # Normal market rate
PENALTY_RATE_PER_kWH = 0.250   # Penalty for unmitigated ramps
GAS_PEAKER_OP_COST = 0.080     # Fuel + Maintenance cost

def calculate_finances(ramp_rate_kw, p_res_kw, action):
    # 1. Potential Penalty (If we did nothing)
    # We only care about penalties if the ramp is outside safe limits (e.g., > 20MW or 20,000kW)
    potential_penalty = 0.0
    if abs(ramp_rate_kw) > 20000: # Our threshold for "Instability"
        # kW * (1/60 hours) * Price
        potential_penalty = abs(ramp_rate_kw) * PENALTY_RATE_PER_kWH

    # 2. Mitigation Cost (The cost of our prescribed action)
    mitigation_cost = p_res_kw * GAS_PEAKER_OP_COST if action == "DISPATCH_GAS_PEAKER_IMMEDIATE" else 0.0
    # Note: Battery degradation cost is now calculated directly inside the BAM agent, so we don't duplicate it here.

    # 3. Net Savings
    # If we mitigated a penalty, we saved money.
    # If the system is stable, savings are 0.
    net_savings = potential_penalty - mitigation_cost if p_res_kw > 0 else 0.0

    return potential_penalty, mitigation_cost, net_savings

def run_simulator():
    client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
    query_api = client.query_api()
    write_api = client.write_api(write_options=SYNCHRONOUS)

    print("Grid Response Actor is online. Waiting for commands...")

    try:
        while True:
            # 1. Query the latest decision from the Consumer (Using 5m range for cloud robustness)
            query = f'from(bucket: "{INFLUX_BUCKET}") \
                      |> range(start: -5m) \
                      |> filter(fn: (r) => r["_measurement"] == "ml_predictions") \
                      |> last()'

            tables = query_api.query(query)

            # Extract data from the result
            current_data = {}
            for table in tables:
                for record in table.records:
                    current_data[record.get_field()] = record.get_value()
                    if "recommended_action" in record.values:
                        current_data["action"] = record.values["recommended_action"]

            if not current_data:
                time.sleep(10)
                continue

            action = current_data.get("action", "MONITORING")
            actual_power_kw = current_data.get("Net_Load_kW", 0)
            predicted_change_kw = current_data.get("Predicted_30min_Change", 0)

            # Extract predicted curve (same field used by the Arbitrage Trader)
            import json as _json
            predicted_curve_json = current_data.get("Predicted_Curve_JSON")
            predicted_curve = _json.loads(predicted_curve_json) if predicted_curve_json else []

            # C1: Run AI Pre-Conditioning before any reactive dispatch decision.
            # This mirrors the same logic in arbitrage_trader.py so both actors
            # independently trigger proactive charging ahead of severe ramps.
            pre_resp = _bam_pre_condition({
                "predicted_load_curve": predicted_curve,
                "current_price": 0.0
            })
            if pre_resp and pre_resp.get("dispatch_kw", 0.0) > 0.0:
                logger.info(
                    f"[GridActor] BAM Pre-Conditioning triggered: "
                    f"{pre_resp['dispatch_kw']:.0f} kW pre-charge ahead of severe ramp."
                )

            # 2. Determine Response Power (P_res_kw)
            p_res_kw = 0.0
            duration_hours = 5 / 60.0

            if action == "DISPATCH_GAS_PEAKER_IMMEDIATE":
                p_res_kw = GAS_PEAKER_CAPACITY_kW
            elif action == "PREPARE_BATTERY_DISCHARGE":
                requested_kw = BATTERY_DISCHARGE_RATE_kW
                dispatch_payload = {
                    "agent_name": "GridResponseActor",
                    "requested_kw": -requested_kw,
                    "duration_hours": duration_hours,
                    "expected_revenue_per_kwh": 0.0
                }
                resp = _bam_dispatch(dispatch_payload)
                if resp is not None:
                    approved_kw = resp["approved_kw"]
                else:
                    logger.warning("[GridActor] BAM /dispatch unreachable after retries — defaulting to 0 kW injection.")
                    approved_kw = 0.0

                # Flip the sign back to positive for grid injection calculations
                p_res_kw = abs(approved_kw)

                if p_res_kw < requested_kw:
                    logger.warning(f"BAM VETO/SCALE: Wanted {requested_kw}kW, allowed {p_res_kw}kW.")

            # 3. Calculate Compensated Output
            p_compensated_kw = actual_power_kw + p_res_kw
            penalty, cost, savings = calculate_finances(predicted_change_kw, p_res_kw, action)

            # 4. Write back to a new measurement: "simulated_response"
            state = _bam_get_state()
            current_soc_kwh = state["current_soc_kwh"] if state else 0.0
            point = Point("simulated_response") \
                .field("response_kw", p_res_kw) \
                .field("compensated_power_kw", p_compensated_kw) \
                .field("avoided_penalty", penalty) \
                .field("mitigation_cost", cost) \
                .field("net_savings", savings) \
                .field("soc_kwh", current_soc_kwh) \
                .tag("asset_active", "NONE" if p_res_kw == 0 else action)

            write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=point)

            if p_res_kw > 0:
                print(f"[ACTION] {action}: Injecting {p_res_kw:.0f} kW. New Grid Level: {p_compensated_kw:.2f}")

            time.sleep(10) # Check every 10 seconds

    except Exception as e:
        print(f"Error: {e}")
    finally:
        client.close()

if __name__ == "__main__":
    run_simulator()
