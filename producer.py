import pandas as pd
import json
import time
from confluent_kafka import Producer

# 1. Configuration
KAFKA_CONFIG = {
    'bootstrap.servers': 'localhost:9092', # Standard Redpanda port
}
TOPIC_NAME = 'grid-sensor-stream'
CSV_FILE_PATH = 'elec_co.csv' # Update this to your filename

# Initialize Producer
producer = Producer(KAFKA_CONFIG)

def delivery_report(err, msg):
    """ Called once for each message produced to indicate delivery result. """
    if err is not None:
        print(f"Message delivery failed: {err}")
    else:
        print(f"Message delivered to {msg.topic()} [{msg.partition()}]")

def stream_data():
    # 2. Load the Dataset
    print(f"Loading {CSV_FILE_PATH}...")
    df = pd.read_csv(CSV_FILE_PATH)
    
    print(f"Starting stream to topic: {TOPIC_NAME}...")
    
    # 3. Iterate and Produce
    for index, row in df.iterrows():
        # Convert row to dictionary and then to JSON string
        payload = row.to_dict()
        message = json.dumps(payload)
        
        # Trigger the send
        producer.produce(
            TOPIC_NAME, 
            key=str(index), 
            value=message, 
            callback=delivery_report
        )
        
        # 'Poll' handles the delivery callbacks
        producer.poll(0)
        
        # 4. Simulation Delay 
        # Set to 1 second to represent 30 mins of real-time, or 0.1 for faster testing
        time.sleep(0.5) 

    # Wait for any remaining messages to be delivered
    producer.flush()

if __name__ == "__main__":
    stream_data()