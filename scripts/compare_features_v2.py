
import os
import sys
import xgboost as xgb
from datetime import datetime

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))
from vpp.core.GridFeatureStore import GridFeatureStore

MODEL_PATH = os.path.join(os.path.dirname(__file__), '..', 'models', 'xgb_vpp_grid.json')

def run_comparison():
    # 1. Load Model Features
    bst = xgb.Booster()
    bst.load_model(MODEL_PATH)
    model_features = bst.feature_names
    print(f"Model has {len(model_features)} features.")

    # 2. Get GFS Features
    gfs = GridFeatureStore(window_size=49)
    # Give it dummy data to prime it
    for i in range(50):
        ts = datetime(2024, 1, 1) if i == 0 else datetime(2024, 1, 1).replace(hour=i % 24)
        gfs.add_observation({
            'Timestamp': ts.isoformat(),
            'Hist_Load': 100, 'Elec_Load': 100, 'Solar_kw': 50, 'Wind_kw': 30,
            'RF_Error': 0, 'C_Flag': 0, 'C_R_S': 0, 'B_SOC': 50, 'Temp': 20,
            'Humidity': 50, 'S_Irr': 500, 'Cloud': 0, 'W_Speed': 5, 'HPa': 1013,
            'Net_Load': 20
        })
    
    vec = gfs.get_inference_vector()
    gfs_features = list(vec.columns)
    print(f"GridFeatureStore produces {len(gfs_features)} features.")

    # 3. Compare
    model_set = set(model_features)
    gfs_set = set(gfs_features)

    only_in_model = model_set - gfs_set
    only_in_gfs = gfs_set - model_set

    print("\n--- Model Feature List (Ordered) ---")
    print("expected_columns = [")
    for f in model_features:
        print(f"    '{f}',")
    print("]")

    print("\n--- Differences ---")

    print(f"Features ONLY in Model ({len(only_in_model)}):")
    for f in sorted(list(only_in_model)):
        print(f"  - {f}")

    print(f"\nFeatures ONLY in GridFeatureStore ({len(only_in_gfs)}):")
    for f in sorted(list(only_in_gfs)):
        print(f"  - {f}")
        
    # Check order if they match sets
    if not only_in_model and not only_in_gfs:
        if model_features == gfs_features:
            print("\nSUCCESS: Features match exactly in content and order.")
        else:
            print("\nWARNING: Feature sets match, but ORDER is different.")
            # Find the first mismatching index
            for i, (m, g) in enumerate(zip(model_features, gfs_features)):
                if m != g:
                    print(f"First mismatch at index {i}: Model='{m}', GFS='{g}'")
                    break

if __name__ == "__main__":
    run_comparison()
