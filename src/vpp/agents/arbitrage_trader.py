import json
import logging
import os
import time

import requests
from dotenv import load_dotenv
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
from tenacity import (
    RetryError,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

# Load environment variables from .env file
load_dotenv()

logger = logging.getLogger(__name__)

# InfluxDB Cloud Settings (Source from env for cloud readiness)
INFLUX_URL = os.getenv("INFLUX_CLOUD_URL", "https://us-east-1-1.aws.cloud2.influxdata.com")
INFLUX_TOKEN = os.getenv("INFLUX_CLOUD_TOKEN", "your-cloud-token-here")
INFLUX_ORG = os.getenv("INFLUX_CLOUD_ORG", "Energy Simulation")
INFLUX_BUCKET = os.getenv("INFLUX_CLOUD_BUCKET", "energy")

# BAM Service endpoint
BAM_API_URL = os.getenv("BAM_API_URL", "http://localhost:8000")
BAM_API_KEY = os.getenv("BAM_API_KEY", "")
_BAM_HEADERS = {"X-BAM-API-Key": BAM_API_KEY} if BAM_API_KEY else {}

# --- Resilient BAM API helpers (Phase B) ---
# Each function retries up to 3 times with exponential backoff (1s, 2s, 4s).
# On total failure, returns a safe fallback value instead of propagating an exception.


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=4),
    retry=retry_if_exception_type((requests.exceptions.ConnectionError, requests.exceptions.Timeout)),
    reraise=False,
)
def _bam_get_state() -> dict:
    resp = requests.get(f"{BAM_API_URL}/state", headers=_BAM_HEADERS, timeout=5)
    resp.raise_for_status()
    return resp.json()


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=4),
    retry=retry_if_exception_type((requests.exceptions.ConnectionError, requests.exceptions.Timeout)),
    reraise=False,
)
def _bam_dispatch(payload: dict) -> dict:
    resp = requests.post(f"{BAM_API_URL}/dispatch", json=payload, headers=_BAM_HEADERS, timeout=5)
    resp.raise_for_status()
    return resp.json()


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=4),
    retry=retry_if_exception_type((requests.exceptions.ConnectionError, requests.exceptions.Timeout)),
    reraise=False,
)
def _bam_pre_condition(payload: dict) -> dict:
    resp = requests.post(f"{BAM_API_URL}/pre_condition", json=payload, headers=_BAM_HEADERS, timeout=5)
    resp.raise_for_status()
    return resp.json()


def run_arbitrage_trader():

    client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
    query_api = client.query_api()
    write_api = client.write_api(write_options=SYNCHRONOUS)

    print("Arbitrage Trader is active. Optimization engine running...")

    try:
        while True:
            # 1. Pull the latest ML Prediction (Using 5m range for cloud robustness)
            query = f'from(bucket: "{INFLUX_BUCKET}") \
                      |> range(start: -5m) \
                      |> filter(fn: (r) => r["_measurement"] == "ml_predictions") \
                      |> last()'

            tables = query_api.query(query)
            predicted_change = 0.0
            predicted_curve_json = None

            for table in tables:
                for record in table.records:
                    if record.get_field() == "Predicted_30min_Change":
                        predicted_change = float(record.get_value())
                    elif record.get_field() == "Predicted_Curve_JSON":
                        predicted_curve_json = record.get_value()

            predicted_curve = []
            if predicted_curve_json:
                predicted_curve = json.loads(predicted_curve_json)

            # 2. Trading Decision Logic Default State
            trade_action = "HOLD"
            requested_kw = 0.0
            approved_kw = 0.0
            profit_loss = 0.0
            duration_hours = 5 / 60.0  # 5-minute dispatch cycle

            # Fetch current state from BAM — fallback to HOLD if unreachable
            state_resp = _bam_get_state()
            if state_resp is None:
                logger.warning("[Trader] BAM /state unreachable after retries — skipping cycle.")
                time.sleep(10)
                continue
            current_soc_pct = state_resp["soc_percentage"]
            current_soc_kwh = state_resp["current_soc_kwh"]

            # --- AI PRE-CONDITIONING (Safety overrides economics) ---
            pre_resp = _bam_pre_condition({"predicted_load_curve": predicted_curve, "current_price": 0.0})
            pre_condition_kw = (pre_resp or {}).get("dispatch_kw", 0.0)

            if pre_condition_kw > 0.0:
                trade_action = "PRE-CHARGE"
                approved_kw = pre_condition_kw
                # Refresh SoC after pre-condition dispatch updates state
                refreshed = _bam_get_state()
                if refreshed:
                    current_soc_kwh = refreshed["current_soc_kwh"]
                profit_loss = 0.0
                print("BAM Agent Triggered AI Pre-Conditioning ahead of severe ramp!")

            # --- NORMAL TRADING ---
            if trade_action == "HOLD":
                # --- BUY (Charging during surplus) ---
                if predicted_change > 20 and current_soc_pct < 0.90:
                    requested_kw = 20000.0
                    dispatch_payload = {
                        "agent_name": "ArbitrageTrader",
                        "requested_kw": requested_kw,
                        "duration_hours": duration_hours,
                        "expected_revenue_per_kwh": 0.0,
                    }
                    resp = _bam_dispatch(dispatch_payload)
                    if resp:
                        approved_kw = resp["approved_kw"]
                        current_soc_kwh = resp["current_soc_kwh"]
                        if approved_kw > 0:
                            trade_action = "BUY"
                            profit_loss = -((approved_kw * duration_hours) * 0.010)
                    else:
                        logger.warning("[Trader] BAM /dispatch (BUY) unreachable — holding position.")

                # --- SELL (Discharging during shortage) ---
                elif predicted_change < -20 and current_soc_pct > 0.10:
                    requested_kw = -20000.0
                    expected_revenue = abs(requested_kw * duration_hours) * 0.150
                    dispatch_payload = {
                        "agent_name": "ArbitrageTrader",
                        "requested_kw": requested_kw,
                        "duration_hours": duration_hours,
                        "expected_revenue_per_kwh": expected_revenue,
                    }
                    resp = _bam_dispatch(dispatch_payload)
                    if resp:
                        approved_kw = resp["approved_kw"]
                        current_soc_kwh = resp["current_soc_kwh"]
                        if approved_kw < 0:
                            trade_action = "SELL"
                            profit_loss = abs(approved_kw * duration_hours) * 0.150
                    else:
                        logger.warning("[Trader] BAM /dispatch (SELL) unreachable — holding position.")

            # 3. Log Trade to InfluxDB
            point = (
                Point("trading_log")
                .field("soc_kwh", current_soc_kwh)
                .field("trade_volume", approved_kw)
                .field("realized_pnl", profit_loss)
                .tag("trade_action", trade_action)
            )

            write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=point)

            if trade_action != "HOLD":
                print(
                    f"[TRADE] {trade_action} {abs(approved_kw):.0f}kW | SoC: {current_soc_kwh:.2f}kWh | PnL: ${profit_loss:.2f}"
                )

            time.sleep(10)  # Run trading cycle every 5 seconds

    except Exception as e:
        print(f"Trader Error: {e}")
    finally:
        client.close()


if __name__ == "__main__":
    run_arbitrage_trader()
