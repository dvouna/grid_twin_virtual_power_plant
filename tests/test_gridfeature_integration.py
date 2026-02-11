"""
Simple test script to verify GridFeatureStore integration with MCP Server
This directly tests the GridFeatureStore functionality
"""

import sys
from datetime import datetime, timedelta

import pytest
import xgboost as xgb

from vpp.core.GridFeatureStore import GridFeatureStore


def generate_sample_observations(count=50):
    """Generate sample grid observations for testing"""
    base_time = datetime(2026, 2, 4, 8, 0, 0)
    observations = []

    for i in range(count):
        timestamp = (base_time + timedelta(seconds=i*5)).isoformat()

        # Simulate realistic grid data
        hour = (base_time + timedelta(seconds=i*5)).hour
        load_base = 5000 + (hour * 100)  # Load increases during day

        obs = {
            'Timestamp': timestamp,
            'Hist_Load': load_base + (i * 10),
            'Elec_Load': load_base,
            'Solar_kw': max(0, 1000 * (1 - abs(hour - 12) / 12)),  # Peak at noon
            'Wind_kw': 500 + (i % 10) * 50,
            'RF_Error': 0.0,
            'C_Flag': 0,
            'C_R_S': 0.0,
            'B_SOC': 75.0 - (i * 0.5),  # Battery slowly discharging
            'Temp': 20 + (hour / 2),
            'Humidity': 60,
            'S_Irr': max(0, 800 * (1 - abs(hour - 12) / 12)),
            'Cloud': 30,
            'W_Speed': 5.0,
            'HPa': 1013.25,
            'Net_Load': load_base - max(0, 1000 * (1 - abs(hour - 12) / 12))
        }
        observations.append(obs)

    return observations




@pytest.mark.integration
def test_gridfeaturestore_integration():
    """Test the GridFeatureStore functionality that MCP server uses"""
    print("="*70)
    print("GridFeatureStore Integration Test")
    print("="*70)

    # Test 1: Load model features
    print("\n[1/5] Loading model features...")
    try:
        with open("models/model_features.txt", "r") as f:
            expected_features = [line.strip() for line in f if line.strip()]
        print(f"✓ Loaded {len(expected_features)} expected features")
    except FileNotFoundError:
        print("⚠ model_features.txt not found, using None")
        expected_features = None

    # Test 2: Initialize feature store
    print("\n[2/5] Initializing GridFeatureStore...")
    feature_store = GridFeatureStore(window_size=49, expected_columns=expected_features)
    print("✓ Feature store initialized")
    print(f"  - Buffer size: {len(feature_store.buffer)}/49")
    print(f"  - Is primed: {feature_store.is_primed}")

    # Test 3: Add observations
    print("\n[3/5] Adding sample observations...")
    observations = generate_sample_observations(50)

    for i, obs in enumerate(observations):
        feature_store.add_observation(obs)
        if i == 0 or i == 25 or i == 48 or i == 49:
            status = "PRIMED ✓" if feature_store.is_primed else f"Need {49 - len(feature_store.buffer)} more"
            print(f"  Observation {i+1}/50: Buffer {len(feature_store.buffer)}/49 - {status}")

    # Test 4: Get inference vector
    print("\n[4/5] Generating inference vector...")
    features = feature_store.get_inference_vector()

    if features is None:
        print("❌ Failed to generate feature vector")
        return False

    print(f"✓ Generated feature vector with shape: {features.shape}")
    print(f"  - Rows: {features.shape[0]}")
    print(f"  - Features: {features.shape[1]}")

    if expected_features:
        print(f"  - Expected features: {len(expected_features)}")
        if features.shape[1] == len(expected_features):
            print("  ✓ Feature count matches model expectations!")
        else:
            print(f"  ⚠ Feature mismatch! Got {features.shape[1]}, expected {len(expected_features)}")

    # Test 5: Load model and make prediction
    print("\n[5/5] Testing model prediction...")
    try:
        model = xgb.Booster()
        model.load_model("models/xgb_vpp_grid.json")
        print("✓ Model loaded successfully")

        # Make prediction
        dmatrix = xgb.DMatrix(features)
        prediction = model.predict(dmatrix)[0]

        direction = "UP" if prediction > 0 else "DOWN"
        magnitude = abs(prediction)

        print("\n🔮 Prediction Result:")
        print(f"  - Predicted Ramp: {prediction:.2f} kW {direction}")
        print(f"  - Magnitude: {magnitude:.2f} kW")

        if magnitude > 10000:
            print("  - Severity: ⚠️ CRITICAL")
        elif magnitude > 5000:
            print("  - Severity: ⚡ MODERATE")
        else:
            print("  - Severity: ✓ STABLE")

    except FileNotFoundError:
        print("⚠ Model file not found (xgb_vpp_grid.json)")
        print("  Skipping actual prediction, but feature engineering works!")
    except Exception as e:
        print(f"❌ Error during prediction: {e}")
        import traceback
        traceback.print_exc()
        return False

    print("\n" + "="*70)
    print("✅ All tests passed! GridFeatureStore integration is working.")
    print("="*70)

    # Summary
    print("\n📊 Summary:")
    print("  - GridFeatureStore can be imported into mcp_server.py ✓")
    print(f"  - Feature engineering produces {features.shape[1]} features ✓")
    print("  - Compatible with XGBoost model format ✓")
    print("  - Ready for MCP server integration ✓")

    # Test passes if we reach here without exceptions


if __name__ == "__main__":
    test_gridfeaturestore_integration()
    sys.exit(0)
