import json
import time
import pandas as pd
from confluent_kafka import Producer

# --- CONFIGURATION ---
TOPIC_NAME = "grid-sensor-stream"
KAFKA_CONF = {'bootstrap.servers': 'localhost:9092'} 
CSV_FILE_PATH = "./data/smart_grid_data.csv"

# --- KAFKA HELPERS ---
def delivery_report(err, msg):
    if err is not None:
        print(f" Delivery failed: {err}")
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
            Timestamp = row.get('Timestamp')
            Hour = row.get('Hour of Day')
            Day = row.get('Day of Week')
            Weekend = row.get('Is Weekend')
            Month = row.get('Month')
            Hist_Load = float(row.get('Historical Electricity Load (kW)', 0))
            Elec = float(row.get('Electricity Load', 0))
            Solar = float(row.get('Solar PV Output (kW)', 0))
            Wind = float(row.get('Wind Power Output (kW)', 0))
            RF_Error = float(row.get('Renewable Forecast Error', 0)) 
            C_Flag = float(row.get('Curtailment Event Flag', 0))
            C_R_S = float(row.get('Curtailment Risk / Surplus Flag', 0)) 
            B_SOC = float(row.get('Battery State of Charge (SOC) (%)', 0))
            Temp = float(row.get('Temperature (°C)', 0))
            Humidity = float(row.get('Humidity (%)', 0))
            S_Irr = float(row.get('Solar Irradiance (W/m²)', 0))
            Cloud = float(row.get('Cloud Cover (%)', 0))
            W_Speed = float(row.get('Wind Speed (m/s)', 0))
            HPa = float(row.get('Atmospheric Pressure (hPa)', 0))
            Net_Load = float(row.get('Net Load', 0)) 

            # 2. Construct the Payload
            # We send all components so the Consumer for further analysis
            payload = {
                "Timestamp": Timestamp,
                "Hour": Hour,
                "Day": Day,
                "Month": Month,
                "Hist_Load": Hist_Load,
                "Elec_Load": Elec,
                "Solar_kw": Solar,
                "Wind_kw": Wind,
                "RF_Error": RF_Error,
                "C_Flag": C_Flag,
                "C_R_S": C_R_S,
                "B_SOC": B_SOC,
                "Temp": Temp,
                "Humidity": Humidity,
                "S_Irr": S_Irr,
                "Cloud": Cloud,
                "W_Speed": W_Speed,
                "HPa": HPa, 
                "Net_Load": Net_Load,
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
            time.sleep(10)

    producer.flush()

if __name__ == "__main__":
    run_producer()