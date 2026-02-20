import os
import time
import json

from dotenv import load_dotenv
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

from vpp.agents.battery_manager import BatteryManagementAgent

# Load environment variables from .env file
load_dotenv()

# InfluxDB Cloud Settings (Source from env for cloud readiness)
INFLUX_URL = os.getenv("INFLUX_CLOUD_URL", "https://us-east-1-1.aws.cloud2.influxdata.com")
INFLUX_TOKEN = os.getenv("INFLUX_CLOUD_TOKEN", "your-cloud-token-here")
INFLUX_ORG = os.getenv("INFLUX_CLOUD_ORG", "Energy Simulation")
INFLUX_BUCKET = os.getenv("INFLUX_CLOUD_BUCKET", "energy")

# --- BATTERY SPECS (kW/kWh) ---
MAX_CAPACITY_kWH = 100000.0  # Total size of "Virtual Megapack" (100 MWh = 100,000 kWh)
charge_efficiency = 0.9      # 10% loss during charging

def run_arbitrage_trader():
    # Initialize the BAM Gatekeeper
    bam_agent = BatteryManagementAgent(
        capacity_kwh=MAX_CAPACITY_kWH,
        max_c_rate=1.0, 
        base_wear_cost_per_kwh=0.015
    )
    # Set starting SoC to 50%
    bam_agent.current_soc_kwh = MAX_CAPACITY_kWH * 0.50

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

            # 2. Trading Decision Logic
            trade_action = "HOLD"
            requested_kw = 0.0
            approved_kw = 0.0
            profit_loss = 0.0
            duration_hours = 5 / 60.0  # 5-minute dispatch cycle

            # --- AI PRE-CONDITIONING (Safety overrides economics) ---
            pre_condition_kw = bam_agent.pre_condition(predicted_curve)
            
            if pre_condition_kw > 0.0:
                trade_action = "PRE-CHARGE"
                approved_kw = pre_condition_kw
                profit_loss = 0.0 # Absorbed as a safety cost
                print("BAM Agent Triggered AI Pre-Conditioning ahead of severe ramp!")
            else:
                # --- NORMAL TRADING ---
                # --- BUY (Charging during surplus) ---
                if predicted_change > 20 and bam_agent.soc_percentage < 0.90:
                    requested_kw = 20000.0 # Charging at 20MW rate (20,000 kW)
                    # We buy at a low "surplus" price ($10/MWh = $0.010/kWh)
                    cost = (requested_kw * duration_hours) * 0.010
                    expected_profit = 0.0 # Just charging, no immediate profit, wait, we might need a way to pass this
                    
                    # Ask BAM for permission
                    approved_kw = bam_agent.evaluate_request("ArbitrageTrader", requested_kw, duration_hours, expected_revenue=0.0)
                    
                    if approved_kw > 0:
                        trade_action = "BUY"
                        profit_loss = -((approved_kw * duration_hours) * 0.010)

                # --- SELL (Discharging during shortage) ---
                elif predicted_change < -20 and bam_agent.soc_percentage > 0.10:
                    requested_kw = -20000.0 # Discharging at 20MW rate (-20,000 kW)
                    # We sell at a high "shortage" price ($150/MWh = $0.150/kWh)
                    expected_revenue = abs(requested_kw * duration_hours) * 0.150
                    
                    # Ask BAM for permission, factoring in expected revenue against degradation
                    approved_kw = bam_agent.evaluate_request("ArbitrageTrader", requested_kw, duration_hours, expected_revenue=expected_revenue)
                    
                    if approved_kw < 0:
                        trade_action = "SELL"
                        profit_loss = abs(approved_kw * duration_hours) * 0.150

            # 3. Log Trade to InfluxDB
            point = Point("trading_log") \
                .field("soc_kwh", bam_agent.current_soc_kwh) \
                .field("trade_volume", approved_kw) \
                .field("realized_pnl", profit_loss) \
                .tag("trade_action", trade_action)

            write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=point)

            if trade_action != "HOLD":
                print(f"[TRADE] {trade_action} {abs(approved_kw):.0f}kW | SoC: {bam_agent.current_soc_kwh:.2f}kWh | PnL: ${profit_loss:.2f}")

            time.sleep(10) # Run trading cycle every 5 seconds

    except Exception as e:
        print(f"Trader Error: {e}")
    finally:
        client.close()

if __name__ == "__main__":
    run_arbitrage_trader()
