import json
import joblib
import numpy as np
import pandas as pd
from datetime import datetime

# ---------------------------------------------------------
# LOAD MODEL + FEATURE CONFIG
# ---------------------------------------------------------

def load_model(model_path="xgb_model.json"):
    import xgboost as xgb
    model = xgb.XGBRegressor()
    model.load_model(model_path)
    return model

def load_feature_config(config_path="feature_config.json"):
    with open(config_path, "r") as f:
        return json.load(f)

# ---------------------------------------------------------
# FEATURE ENGINEERING FOR INFERENCE
# ---------------------------------------------------------

def create_lag_features(df, lag_list, col="net_load"):
    for lag in lag_list:
        df[f"{col}_lag_{lag}"] = df[col].shift(lag)
    return df

def create_rolling_features(df, windows, col="net_load"):
    for w in windows:
        df[f"{col}_roll_mean_{w}"] = df[col].rolling(w).mean()
        df[f"{col}_roll_std_{w}"] = df[col].rolling(w).std()
    return df

def create_interaction_features(df):
    df["solar_x_temp"] = df["solar"] * df["temperature"]
    df["wind_x_pressure"] = df["wind"] * df["pressure"]
    return df

def create_cyclical_features(df):
    df["hour_sin"] = np.sin(2 * np.pi * df["hour"] / 24)
    df["hour_cos"] = np.cos(2 * np.pi * df["hour"] / 24)
    df["dow_sin"] = np.sin(2 * np.pi * df["day_of_week"] / 7)
    df["dow_cos"] = np.cos(2 * np.pi * df["day_of_week"] / 7)
    return df

# ---------------------------------------------------------
# MAIN FEATURE PIPELINE
# ---------------------------------------------------------

def prepare_features(df, config):
    df = df.copy()

    # Lags
    df = create_lag_features(df, config["lags"], col="net_load")

    # Rolling windows
    df = create_rolling_features(df, config["rolling_windows"], col="net_load")

    # Interaction features
    if config.get("use_interactions", True):
        df = create_interaction_features(df)
    # Cyclical features
    if config.get("use_cyclical", True):
        df = create_cyclical_features(df)

    # Drop rows with NaNs created by lags/rolling
    df = df.dropna()

    return df

# ---------------------------------------------------------
# PREDICTION FUNCTION
# ---------------------------------------------------------

def predict_next(df_raw, model, config):
    df_feat = prepare_features(df_raw, config)

    # Select only the columns the model was trained on
    X = df_feat[config["feature_list"]].tail(1)

    prediction = model.predict(X)[0]
    return prediction

# ---------------------------------------------------------
# EXAMPLE USAGE
# ---------------------------------------------------------

if __name__ == "__main__":
    model = load_model("xgb_model.json")
    config = load_feature_config("feature_config.json")

    # df_raw must contain the latest history window
    df_raw = pd.read_csv("latest_data.csv")

    pred = predict_next(df_raw, model, config)
    print("Predicted Net Load for next hour:", pred)
    