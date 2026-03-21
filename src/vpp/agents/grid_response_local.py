import time
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

from vpp.agents.battery_manager import BatteryManagementAgent

# --- LOCAL CONFIGURATION ---
INFLUX_URL = "http://localhost:8086"
INFLUX_TOKEN = "smg!indb25"
INFLUX_ORG = "myorg"
INFLUX_BUCKET = "energy"

# Simulated asset capacities (kW)
GAS_PEAKER_CAPACITY_kW = 100000.0  # 100 MW
BATTERY_DISCHARGE_RATE_kW = 40000.0 # 40 MW
MAX_CAPACITY_kWH = 100000.0  

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

    print("⚡ Grid Response Actor (LOCAL) is online. Waiting for commands...")

    try:
        while True:
            # 1. Query the latest decision from the Consumer (Using 1m range for local speed)
            query = f'from(bucket: "{INFLUX_BUCKET}") \
                      |> range(start: -1m) \
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
            actual_power_kw = current_data.get("Net_Load_kW", 0)
            # Assuming predicted_change is in kW due to feature store standardisation
            predicted_change_kw = current_data.get("Predicted_30min_Change", 0)

            # 2. Determine Response Power (P_res_kw)
            p_res_kw = 0.0
            duration_hours = 5 / 60.0

            if action == "DISPATCH_GAS_PEAKER_IMMEDIATE":
                p_res_kw = GAS_PEAKER_CAPACITY_kW
            elif action == "PREPARE_BATTERY_DISCHARGE":
                requested_kw = BATTERY_DISCHARGE_RATE_kW
                
                # Grid Response is an emergency! We submit a negative kW request to BAM to discharge.
                # We pass expected_revenue=0 because safety overrides economics.
                approved_kw = bam_agent.evaluate_request("GridResponseActor", -requested_kw, duration_hours, expected_revenue=0.0)
                
                # Flip the sign back to positive for grid injection calculations
                p_res_kw = abs(approved_kw)
                
                if p_res_kw < requested_kw:
                    print(f"BAM Agent VETO/SCALE: Wanted to inject {requested_kw}kW, but battery only allowed {p_res_kw}kW.")

            # 3. Calculate Compensated Output
            p_compensated_kw = actual_power_kw + p_res_kw
            penalty, cost, savings = calculate_finances(predicted_change_kw, p_res_kw, action)

            # 4. Write back to a new measurement: "simulated_response"
            point = Point("simulated_response") \
                .field("response_kw", p_res_kw) \
                .field("compensated_power_kw", p_compensated_kw) \
                .field("avoided_penalty", penalty) \
                .field("mitigation_cost", cost) \
                .field("net_savings", savings) \
                .tag("asset_active", "NONE" if p_res_kw == 0 else action)

            write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=point)

            if p_res_kw > 0:
                print(f"⚡ [ACTION] {action}: Injecting {p_res_kw:.0f} kW. New Grid Level: {p_compensated_kw:.2f}")

            time.sleep(10) # Check every 10 seconds

    except Exception as e:
        print(f"Error: {e}")
    finally:
        client.close()

if __name__ == "__main__":
    run_simulator()