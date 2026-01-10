import json
import time
import pandas as pd
from datetime import datetime
from confluent_kafka import Producer

# --- CONFIGURATION ---
TOPIC_NAME = "grid-sensor-stream"
KAFKA_CONF = {'bootstrap.servers': 'localhost:9092'} 
CSV_FILE_PATH = "elec_co.csv"

# --- KAFKA HELPERS ---
def delivery_report(err, msg):
    if err is not None:
        print(f"❌ Delivery failed: {err}")
    else:
        print("Message Delivered Successfully") 
        pass

def run_producer():
    producer = Producer(KAFKA_CONF)
    
    # Load your dataset
    # Expecting columns: 'Electricity Load', 'Solar Output', 'Wind Output'
    try:
        df = pd.read_csv(CSV_FILE_PATH)
    except FileNotFoundError:
        print(f"Error: {CSV_FILE_PATH} not found.")
        return

    print(f"🚀 Starting 30s Stream. Total records: {len(df)}")

    while True: # Loop the dataset for continuous simulation
        for index, row in df.iterrows():
            # 1. Capture Raw Values
            # We use the original names from your CSV here
            load = float(row.get('Electricity Load', 0))
            solar = float(row.get('Solar PV Output (kW)', 0))
            wind = float(row.get('Wind Power Output (kW)', 0))

            # 2. Construct the Payload
            # We send all components so the Consumer can calculate Net Load
            payload = {
                "timestamp": datetime.now().isoformat(), # Overwrite for Live Dashboard
                "electricity_load": load,
                "solar_output": solar,
                "wind_output": wind,
                "sensor_id": "CA_GRID_ZONE_01"
            }
            
            message = json.dumps(payload)
            
            # 3. Produce with Consistent Keying
            # Using a fixed key ('grid_vpp') ensures all data stays in chronological order 
            # on the same Redpanda partition.
            producer.produce(
                TOPIC_NAME,
                key="grid_vpp", 
                value=message,
                callback=delivery_report
            )
            
            # 4. Flush and Pulse
            producer.poll(0) # Trigger delivery reports
            
            # This is your 30-second pulse for the dashboard
            time.sleep(30)

    producer.flush()

if __name__ == "__main__":
    run_producer()