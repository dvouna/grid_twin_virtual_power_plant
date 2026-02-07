import os
import time
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

# InfluxDB Cloud Settings (update these with your actual cloud credentials)
INFLUX_URL = os.getenv("INFLUX_CLOUD_URL", "https://us-east-1-1.aws.cloud2.influxdata.com")
INFLUX_TOKEN = os.getenv("INFLUX_CLOUD_TOKEN", "your-cloud-token-here")
INFLUX_ORG = os.getenv("INFLUX_CLOUD_ORG", "Energy Simulation")
INFLUX_BUCKET = os.getenv("INFLUX_CLOUD_BUCKET", "energy")

# --- BATTERY SPECS ---
MAX_CAPACITY_kWH = 100.0  # Total size of your "Virtual Megapack"
current_soc_kWH = 50.0    # Start at 50% charge
charge_efficiency = 0.9   # 10% loss during charging

def run_arbitrage_trader(): 
    global current_soc_kWH
    client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
    query_api = client.query_api()
    write_api = client.write_api(write_options=SYNCHRONOUS)

    print("💰 Arbitrage Trader is active. Optimization engine running...")

    try:
        while True:
            # 1. Pull the latest ML Prediction
            query = f'from(bucket: "{INFLUX_BUCKET}") \
                      |> range(start: -2m) \
                      |> filter(fn: (r) => r["_measurement"] == "ml_predictions") \
                      |> last()'
            
            tables = query_api.query(query)
            predicted_change = 0.0
            
            for table in tables:
                for record in table.records:
                    if record.get_field() == "Predicted_30min_Change":
                        predicted_change = record.get_value()

            # 2. Trading Decision Logic
            trade_action = "HOLD"
            trade_volume_kw = 0.0
            profit_loss = 0.0
            
            # --- BUY (Charging during surplus) ---
            if predicted_change > 20 and current_soc_kWH < (MAX_CAPACITY_kWH * 0.9):
                trade_action = "BUY"
                trade_volume_kw = 0.020 # Charging at 20MW rate
                # We buy at a low "surplus" price ($10/MWh)
                cost = (trade_volume_kw) * 0.010 
                current_soc_kWH += (trade_volume_kw) * charge_efficiency
                profit_loss = -cost # Initial outlay

            # --- SELL (Discharging during shortage) ---
            elif predicted_change < -20 and current_soc_kWH > (MAX_CAPACITY_kWH * 0.1):
                trade_action = "SELL"
                trade_volume_kw = 0.020 # Discharging at 20MW rate
                # We sell at a high "shortage" price ($150/MWh)
                revenue = (trade_volume_kw) * 0.150 
                current_soc_kWH -= (trade_volume_kw)
                profit_loss = revenue

            # 3. Log Trade to InfluxDB
            point = Point("trading_log") \
                .field("soc_kwh", current_soc_kWH) \
                .field("trade_volume", trade_volume_kw) \
                .field("realized_pnl", profit_loss) \
                .tag("trade_action", trade_action)
            
            write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=point)

            if trade_action != "HOLD":
                print(f"📉 [TRADE] {trade_action} {trade_volume_kw }kW | SoC: {current_soc_kWH:.2f}kWh")

            time.sleep(10) # Run trading cycle every 5 seconds

    except Exception as e:
        print(f"Trader Error: {e}")
    finally:
        client.close()

if __name__ == "__main__":
    run_arbitrage_trader()