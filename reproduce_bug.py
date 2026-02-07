import sys
import os
import pandas as pd
from datetime import datetime, timedelta

# Mock environment
sys.path.append(os.path.abspath("src"))
from vpp.core.GridFeatureStore import GridFeatureStore

def test_repro():
    print("Testing GridFeatureStore reproduction...")
    fs = GridFeatureStore(window_size=49)
    
    base_time = datetime(2026, 2, 5, 12, 0, 0)
    for i in range(50):
        timestamp = (base_time + timedelta(seconds=i*5)).isoformat()
        payload = {
            'Timestamp': timestamp,
            'Hist_Load': float(5000 + i),
            'Elec_Load': float(5000 + i),
            'Solar_kw': 0.0,
            'Wind_kw': 0.0,
            'Net_Load': float(5000 + i)
        }
        # In mcp_server.py we call fs.add_observation(payload)
        fs.add_observation(payload)
        
    print(f"Buffer size: {len(fs.buffer)}")
    print(f"Is primed: {fs.is_primed}")
    
    print("Generating inference vector...")
    try:
        vec = fs.get_inference_vector()
        print(f"Success! Vector shape: {vec.shape}")
    except Exception as e:
        print(f"Caught error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_repro()
