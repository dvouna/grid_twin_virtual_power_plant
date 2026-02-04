
import pandas as pd
import numpy as np
import sys
import re

# Add current dir to path to import GridFeatureStore
sys.path.append('.')
from GridFeatureStore import GridFeatureStore

def check_alignment():
    print("--- ALIGNMENT CHECK ---")
    
    # 1. Load model features
    try:
        with open('model_features.txt', 'r', encoding='utf-8-sig') as f:
            model_features = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        print("Error: model_features.txt not found")
        return

    # 2. Extract MY_FEATURES from consumer_ml.py
    try:
        with open('consumer_ml.py', 'r') as f:
            content = f.read()
            match = re.search(r'MY_FEATURES = \[(.*?)\]', content, re.DOTALL)
            if match:
                my_features_str = match.group(1)
                my_features = [f.strip().strip("'").strip('"') for f in my_features_str.split(',') if f.strip()]
            else:
                print("Error: MY_FEATURES not found in consumer_ml.py")
                return
    except Exception as e:
        print(f"Error reading consumer_ml.py: {e}")
        return

    # 3. Simulate GridFeatureStore output
    sample_payload = {
        'Timestamp': '2024-01-01 12:00:00',
        'Hist_Load': 100, 'Elec_Load': 110, 'Solar_kw': 50, 'Wind_kw': 30,
        'RF_Error': 5, 'C_Flag': 0, 'C_R_S': 0, 'B_SOC': 80, 'Temp': 25,
        'Humidity': 60, 'S_Irr': 500, 'Cloud': 10, 'W_Speed': 5, 'HPa': 1013,
        'Net_Load': 30
    }
    
    store = GridFeatureStore(window_size=49, expected_columns=model_features)
    for i in range(50):
        store.add_observation(sample_payload)
    
    vector = store.get_inference_vector()
    produced_cols = vector.columns.tolist()

    # Results
    print(f"Model Features Count: {len(model_features)}")
    print(f"MY_FEATURES Count: {len(my_features)}")
    print(f"Produced Columns Count: {len(produced_cols)}")
    
    missing_in_my = set(model_features) - set(my_features)
    extra_in_my = set(my_features) - set(model_features)
    
    missing_in_produced = set(model_features) - set(produced_cols)
    extra_in_produced = set(produced_cols) - set(model_features)

    if missing_in_my: print(f"Missing in consumer_ml.py: {missing_in_my}")
    if extra_in_my: print(f"Extra in consumer_ml.py: {extra_in_my}")
    if missing_in_produced: print(f"Missing in GridFeatureStore output: {missing_in_produced}")
    if extra_in_produced: print(f"Extra in GridFeatureStore output: {extra_in_produced}")

    if produced_cols == model_features:
        print("RESULT: ALIGNMENT PERFECT")
    else:
        print("RESULT: ALIGNMENT FAILED")
        if set(produced_cols) == set(model_features):
            print("REASON: Order mismatch")
        else:
            print("REASON: Content mismatch")

if __name__ == "__main__":
    check_alignment()
