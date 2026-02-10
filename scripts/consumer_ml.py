import sys
import os
import json
from confluent_kafka import Consumer
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

# Add the 'src' directory to the Python path programmatically
# This allows the script to find the 'vpp' package inside the 'src' folder
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

# Import the new Predictor class
from vpp.core.VPPPredictor import VPPPredictor

# --- 1. CONFIGURATION ---
MODEL_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'models', 'xgb_vpp_grid.json'))
TOPIC_NAME = 'grid-sensor-stream'

KAFKA_CONF = {
    'bootstrap.servers': os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092'),
    'group.id': 'ml-consumer-cloud-group',
    'auto.offset.reset': 'earliest',
    'broker.address.family': 'v4'
}

# InfluxDB Cloud Settings (Source from env for cloud readiness)
INFLUX_URL = os.getenv("INFLUX_CLOUD_URL", "https://us-east-1-1.aws.cloud2.influxdata.com")
INFLUX_TOKEN = os.getenv("INFLUX_CLOUD_TOKEN", "your-cloud-token-here")
INFLUX_ORG = os.getenv("INFLUX_CLOUD_ORG", "Energy Simulation")
INFLUX_BUCKET = os.getenv("INFLUX_CLOUD_BUCKET", "energy")

# Ramp Rate Thresholds (MW/min)
# If power drops faster than this, we trigger an alarm.
CRITICAL_DROP_THRESHOLD = -50  
WARNING_DROP_THRESHOLD = -20

# --- 2. INITIALIZE PREDICTOR ---
# This class now owns the Model, Feature Names, and Feature Store logic
predictor = VPPPredictor(MODEL_PATH)

# --- 3. PRESCRIPTIVE LOGIC ---
def prescribe_action(ramp_rate):
    """
    Decides what to do based on the severity of the ramp event.
    Returns a tuple: (Severity, Action_Message)
    """
    if ramp_rate <= CRITICAL_DROP_THRESHOLD:
        return "CRITICAL", "DISPATCH_GAS_PEAKER_IMMEDIATE"
    elif ramp_rate <= WARNING_DROP_THRESHOLD:
        return "WARNING", "PREPARE_BATTERY_DISCHARGE"
    elif ramp_rate > 50:
        return "NOTICE", "CURTAIL_SOLAR_OUTPUT"
    else:
        return "NORMAL", "MONITORING"

def run_ml_consumer():
    # Initialize Clients
    consumer = Consumer(KAFKA_CONF)
    consumer.subscribe([TOPIC_NAME])

    influx_client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
    write_api = influx_client.write_api(write_options=SYNCHRONOUS)

    print(f"🚀 ML Consumer (CLOUD) started with {MODEL_PATH}")
    print(f"Listening to {TOPIC_NAME}...")
    print(f"📊 Writing to InfluxDB Cloud: {INFLUX_URL}")

    try:
        while True:
            msg = consumer.poll(10.0) # Wait 10 seconds for a message 
            if msg is None:
                continue
            if msg.error():
                print(f"Consumer error: {msg.error()}")
                continue

            # A. Parse Data
            payload = json.loads(msg.value().decode('utf-8'))
            
            # B. Add to State and Predict
            predictor.add_observation(payload)
            prediction_30min_change = predictor.predict()
            
            # C. Check if we have enough data (buffer is primed)
            if prediction_30min_change is None:
                cur, total = predictor.buffer_info
                print(f"⌛ Priming buffer... ({cur}/{total})")
                continue
            
            # D. Metrics for Influx
            solar = float(payload.get('Solar_kw', 0))
            wind = float(payload.get('Wind_kw', 0))
            net_load = float(payload.get('Net_Load', 0)) 
            elec_load = float(payload.get('Elec_Load', 0))
            ren_load = solar + wind
            
            # --- DECISION ENGINE ---
            severity, action = prescribe_action(prediction_30min_change)

            # E. Write to InfluxDB Cloud
            point = Point("ml_predictions") \
                .field("Solar_Output_kW", solar) \
                .field("Wind_Output_kW", wind) \
                .field("Electricity_Load_kW", elec_load) \
                .field("Renewable_Load_kW", ren_load) \
                .field("Net_Load_kW", net_load) \
                .field("Predicted_30min_Change", prediction_30min_change) \
                .tag("severity", severity) \
                .tag("recommended_action", action)
            
            write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=point)
            # log(f"DEBUG: Data written to InfluxDB Cloud") # Optional: uncomment for verbose logging
            
            if severity != "NORMAL":
                print(f"{severity}: Predicted Change {prediction_30min_change:.2f} | Action: {action}")
            else:
                print(f"Normal: Load {net_load} | Predicted {prediction_30min_change:.2f} kW")

    except Exception as e:
        print(f"Error in ML Consumer (Cloud): {e}")
    finally:
        consumer.close()
        influx_client.close()


if __name__ == "__main__":
    run_ml_consumer()
