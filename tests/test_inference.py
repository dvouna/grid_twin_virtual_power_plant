import pytest
import pandas as pd
import numpy as np
from vpp.ml.inference import prepare_features

def test_prepare_features_basic():
    # Setup dummy data
    data = {
        'Timestamp': pd.date_range(start='2026-01-01', periods=50, freq='5min'),
        'net_load': np.random.rand(50) * 100,
        'solar': np.random.rand(50) * 10,
        'temperature': np.random.rand(50) * 30,
        'wind': np.random.rand(50) * 5,
        'pressure': np.random.rand(50) + 1000,
        'hour': np.random.randint(0, 24, 50),
        'day_of_week': np.random.randint(0, 7, 50)
    }
    df = pd.DataFrame(data)
    
    config = {
        "lags": [1, 2],
        "rolling_windows": [3],
        "use_interactions": True,
        "use_cyclical": True,
        "feature_list": ["hour_sin", "hour_cos", "net_load_lag_1"]
    }
    
    # Run function
    df_feat = prepare_features(df, config)
    
    # Verify
    assert not df_feat.empty
    assert "net_load_lag_1" in df_feat.columns
    assert "net_load_roll_mean_3" in df_feat.columns
    assert "hour_sin" in df_feat.columns
    # With lags of 1,2 and rolling of 3, we should lose at least 2 rows
    assert len(df_feat) < len(df)
