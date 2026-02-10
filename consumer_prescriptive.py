import json
from datetime import datetime
from confluent_kafka import Consumer
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

# --- 1. CONFIGURATION ---
KAFKA_CONF = {
    'bootstrap.servers': 'localhost:9092',
    'group.id': 'ml-consumer-group',
    'auto.offset.reset': 'earliest',      # Changed to 'earliest' to catch old data
    'broker.address.family': 'v4'         # Force IPv4 to prevent resolution hangs
}
TOPIC_NAME = 'grid-sensor-stream'

# InfluxDB Settings (Match these to your Docker Compose environment)
INFLUX_URL = "http://localhost:8086"
INFLUX_TOKEN = "smg!indb25"
INFLUX_ORG = "myorg"
INFLUX_BUCKET = "energy"

# Ramp Rate Thresholds (MW/min)
# If power drops faster than this, we trigger an alarm.
CRITICAL_DROP_THRESHOLD = -50  
WARNING_DROP_THRESHOLD = -20

# --- 2. PRESCRIPTIVE LOGIC ---
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

# --- 3. MAIN LOOP ---
def start_consumer():
    # Initialize State Variables
    previous_load = None
    previous_time = None

    # Initialize Clients
    consumer = Consumer(KAFKA_CONF)
    consumer.subscribe([TOPIC_NAME])

    influx_client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
    write_api = influx_client.write_api(write_options=SYNCHRONOUS)

    print(f"Listening to {TOPIC_NAME} and writing to InfluxDB...")

    try:
        while True:
            msg = consumer.poll(30.0) # Wait 30 seconds for a message

            if msg is None:
                continue
            if msg.error():
                print(f"Consumer error: {msg.error()}")
                continue

            # Parse JSON
            data = json.loads(msg.value().decode('utf-8'))
            
            # Extract key metrics (Assuming your CSV has 'meter_reading' and timestamp)
            # Adjust 'meter_reading' to match your actual CSV column name!
            solar = float(data.get('solar', 0))
            wind = float(data.get('wind', 0))
            elec = float(data.get('elec', 0)) 

            # --- CALCULATE RENEWABLE ENERGY ---
            ren_load = solar + wind # Total Renewable in kW
            
            # --- CALCULATE NET LOAD ---
            current_load = elec - ren_load  # Net Load in kW            
            
            # Parse the real-time timestamp 
            # ISO format: "2026-01-08T23:00:00.000" 
            current_time = datetime.fromisoformat(data['timestamp'])
            
            # --- CALCULATE RAMP RATE ---
            ramp_rate = 0.0
            if previous_load is not None and previous_time is not None:
                # Time difference in seconds 
                time_diff = (current_time - previous_time).total_seconds() 

                # Simple difference calculation (Current - Previous)
                load_diff = current_load - previous_load

                if time_diff > 0:
                    ramp_rate = (load_diff / time_diff) * 60  # Convert to kW/min
                else: 
                    ramp_rate = 0.0 

            # --- DECISION ENGINE ---
            severity, action = prescribe_action(ramp_rate)

            # --- WRITE TO INFLUXDB ---
            # We create a "Point" that contains the Raw Data AND the Decision
            point = Point("grid_status") \
                .field("solar_kW", solar) \
                .field("wind_kW", wind) \
                .field("elec_kW", elec) \
                .field("ren_load", ren_load) \
                .field("net_load", current_load) \
                .field("ramp_rate", ramp_rate) \
                .tag("severity", severity) \
                .tag("recommended_action", action)
            
            write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=point)

            if severity != "NORMAL":
                print(f"{severity}: Ramp Rate {ramp_rate:.2f} | Action: {action}")
            else:
                print(f"Normal: Power {current_load} | Rate {ramp_rate}")

            # Update State
            previous_load = current_load
            previous_time = current_time

    except KeyboardInterrupt:
        print("Stopping consumer...")
    finally:
        consumer.close()
        influx_client.close()

if __name__ == "__main__":
    start_consumer()
