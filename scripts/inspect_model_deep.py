"""
Deep inspection of xgb_vpp_grid.json to understand feature name handling.
"""
import os
import numpy as np
import pandas as pd
import xgboost as xgb

MODEL_PATH = os.path.join(os.path.dirname(__file__), '..', 'models', 'xgb_vpp_grid.json')

print("=== Deep Model Inspection ===")
print(f"XGBoost version: {xgb.__version__}")

# Load model
model = xgb.XGBRegressor()
model.load_model(MODEL_PATH)

booster = model.get_booster()

# Check feature names from different sources
print("\n--- Feature Names ---")
print(f"booster.feature_names: {booster.feature_names}")
print(f"booster.feature_names type: {type(booster.feature_names)}")

if booster.feature_names:
    print(f"Count: {len(booster.feature_names)}")
    print(f"First 3: {booster.feature_names[:3]}")
    # Check for hidden characters
    for i, name in enumerate(booster.feature_names[:3]):
        print(f"  Feature {i}: repr={repr(name)}, len={len(name)}")
else:
    print("NO feature names in booster!")

# Check feature types
print(f"\nbooster.feature_types: {booster.feature_types}")

# Check number of features
print(f"\nbooster.num_features(): {booster.num_features()}")

# Check model attributes
print(f"\nmodel.n_features_in_: {getattr(model, 'n_features_in_', 'NOT SET')}")
print(f"model.feature_names_in_: {getattr(model, 'feature_names_in_', 'NOT SET')}")

# Try prediction with a proper DataFrame
print("\n--- Prediction Tests ---")
n_features = booster.num_features()
feature_names = booster.feature_names

if feature_names:
    # Test 1: DataFrame with correct names
    print(f"\nTest 1: DataFrame with {len(feature_names)} named columns...")
    df = pd.DataFrame(np.random.rand(1, len(feature_names)), columns=feature_names)
    print(f"  df.shape={df.shape}, df.dtypes.unique()={df.dtypes.unique()}")
    try:
        pred = model.predict(df)
        print(f"  SUCCESS: {pred}")
    except Exception as e:
        print(f"  FAILED: {e}")

    # Test 2: DMatrix with feature names
    print("\nTest 2: DMatrix with feature names...")
    dmat = xgb.DMatrix(df, feature_names=feature_names)
    try:
        pred = booster.predict(dmat)
        print(f"  SUCCESS: {pred}")
    except Exception as e:
        print(f"  FAILED: {e}")

    # Test 3: DMatrix without feature names (numpy)
    print("\nTest 3: DMatrix from numpy (no feature names)...")
    dmat_np = xgb.DMatrix(np.random.rand(1, len(feature_names)))
    try:
        pred = booster.predict(dmat_np)
        print(f"  SUCCESS: {pred}")
    except Exception as e:
        print(f"  FAILED: {e}")
        
    # Test 4: model.predict with numpy array
    print("\nTest 4: model.predict with numpy array...")
    try:
        pred = model.predict(np.random.rand(1, len(feature_names)))
        print(f"  SUCCESS: {pred}")
    except Exception as e:
        print(f"  FAILED: {e}")
else:
    # No feature names - test with num_features
    print(f"\nNo feature names. Testing with {n_features} columns...")
    
    # Test with unnamed DataFrame
    df = pd.DataFrame(np.random.rand(1, n_features))
    try:
        pred = model.predict(df)
        print(f"  SUCCESS (unnamed df): {pred}")
    except Exception as e:
        print(f"  FAILED (unnamed df): {e}")
    
    # Test with numpy
    try:
        pred = model.predict(np.random.rand(1, n_features))
        print(f"  SUCCESS (numpy): {pred}")
    except Exception as e:
        print(f"  FAILED (numpy): {e}")

# Also check the other model file
MODEL_PATH_2 = os.path.join(os.path.dirname(__file__), '..', 'models', 'xgb_vpp_forecast.json')
if os.path.exists(MODEL_PATH_2):
    print("\n\n=== Checking alternate model: xgb_vpp_forecast.json ===")
    model2 = xgb.XGBRegressor()
    model2.load_model(MODEL_PATH_2)
    b2 = model2.get_booster()
    print(f"feature_names: {b2.feature_names}")
    print(f"num_features: {b2.num_features()}")
