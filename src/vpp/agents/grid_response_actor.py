import os
import time
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

# InfluxDB Cloud Settings (Source from env for cloud readiness)
INFLUX_URL = os.getenv("INFLUX_CLOUD_URL", "https://us-east-1-1.aws.cloud2.influxdata.com")
INFLUX_TOKEN = os.getenv("INFLUX_CLOUD_TOKEN", "your-cloud-token-here")
INFLUX_ORG = os.getenv("INFLUX_CLOUD_ORG", "Energy Simulation")
INFLUX_BUCKET = os.getenv("INFLUX_CLOUD_BUCKET", "energy")

# Simulated asset capacities (MW)
GAS_PEAKER_CAPACITY = 100.0
BATTERY_DISCHARGE_RATE = 40.0

# --- NEW FINANCIAL CONSTANTS ---
# Prices are usually per MWh, so we divide by 60 for 1-minute intervals
SPOT_PRICE_PER_kWH = 0.05      # Normal market rate
PENALTY_RATE_PER_kWH = 0.250   # Penalty for unmitigated ramps
GAS_PEAKER_OP_COST = 0.080      # Fuel + Maintenance cost

def calculate_finances(ramp_rate, p_res, action):
    # 1. Potential Penalty (If we did nothing)
    # We only care about penalties if the ramp is outside safe limits
    potential_penalty = 0.0
    if abs(ramp_rate) > 20: # Our threshold for "Instability"
        # MW * (1/60 hours) * Price
        potential_penalty = abs(ramp_rate) * PENALTY_RATE_PER_kWH 

    # 2. Mitigation Cost (The cost of our prescribed action)
    mitigation_cost = p_res * GAS_PEAKER_OP_COST

    # 3. Net Savings
    # If we mitigated a penalty, we saved money. 
    # If the system is stable, savings are 0.
    net_savings = potential_penalty - mitigation_cost if p_res > 0 else 0.0

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
                    # Also get tags
                    if "recommended_action" in record.values:
                        current_data["action"] = record.values["recommended_action"]

            if not current_data:
                time.sleep(10)
                continue

            action = current_data.get("action", "MONITORING")
            actual_power = current_data.get("Net_Load_kW", 0)
            predicted_change = current_data.get("Predicted_30min_Change", 0)

            # 2. Determine Response Power (P_res)
            p_res = 0.0
            if action == "DISPATCH_GAS_PEAKER_IMMEDIATE":
                p_res = GAS_PEAKER_CAPACITY
            elif action == "PREPARE_BATTERY_DISCHARGE":
                p_res = BATTERY_DISCHARGE_RATE

            # 3. Calculate Compensated Output
            p_compensated = actual_power + p_res
            penalty, cost, savings = calculate_finances(predicted_change, p_res, action)

            # 4. Write back to a new measurement: "simulated_response"
            point = Point("simulated_response") \
                .field("response_mw", p_res) \
                .field("compensated_power", p_compensated) \
                .field("avoided_penalty", penalty) \
                .field("mitigation_cost", cost) \
                .field("net_savings", savings) \
                .tag("asset_active", "NONE" if p_res == 0 else action)
            
            write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=point)
            # log(f"DEBUG: Data written to InfluxDB Cloud") # Optional: uncomment for verbose logging

            if p_res > 0:
                print(f"⚡ [ACTION] {action}: Injecting {p_res} MW. New Grid Level: {p_compensated:.2f}")

            time.sleep(10) # Check every second

    except Exception as e:
        print(f"Error: {e}")
    finally:
        client.close()

if __name__ == "__main__":
    run_simulator()