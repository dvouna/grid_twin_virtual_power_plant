import os
import xgboost as xgb
import pandas as pd
from fastmcp import FastMCP
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

# Robust path handling
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
MODEL_DIR = os.path.join(BASE_DIR, "models")

# Import GridFeatureStore from its new home
try:
    from vpp.core.GridFeatureStore import GridFeatureStore
except ImportError:
    # If not running as package, try relative or sys.path
    import sys
    sys.path.append(os.path.join(BASE_DIR, "src"))
    from vpp.core.GridFeatureStore import GridFeatureStore

# ---- INITIALIZATION ----
mcp = FastMCP("GridIntelligence")

# Loading existing model
MODEL_PATH = os.path.join(MODEL_DIR, "xgboost_smart_ml.ubj")
model = xgb.Booster()
model.load_model(MODEL_PATH)

# Load expected feature columns from model training
FEATURE_FILE = os.path.join(MODEL_DIR, "model_features.txt")
try:
    with open(FEATURE_FILE, "r") as f:
        expected_features = [line.strip() for line in f if line.strip()]
except FileNotFoundError:
    expected_features = None
    print(f"Warning: {FEATURE_FILE} not found. Feature alignment may be inconsistent.")

# Initialize GridFeatureStore for feature engineering
feature_store = GridFeatureStore(window_size=49, expected_columns=expected_features)

# InfluxDB Config
INFLUX_URL = "http://localhost:8086"
INFLUX_TOKEN = "smg!indb25"
ORG = "myorg"
BUCKET = "energy"

# --- RESOURCES ----
@mcp.resource("grid://current-status")
def get_grid_status() -> str:
    """Fetches the most recent net load and renewable output from InfluxDB."""
    client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=ORG)
    query = f'from(bucket:"{BUCKET}") |> range(start: -1m) |> last()'
    tables = client.query_api().query(query)
    
    results = {}
    for table in tables:
        for record in table.records:
            results[record.get_field()] = record.get_value()
    
    return f"Current Net Load: {results.get('Net_Load_kW', 'N/A')} kW | Solar: {results.get('Renewable_Load_kW', 0)} kW"


# --- TOOLS ---
@mcp.tool()
def add_grid_observation(
    timestamp: str,
    hist_load: float,
    elec_load: float,
    solar_kw: float = 0.0,
    wind_kw: float = 0.0,
    rf_error: float = 0.0,
    c_flag: int = 0,
    c_r_s: float = 0.0,
    b_soc: float = 0.0,
    temp: float = 0.0,
    humidity: float = 0.0,
    s_irr: float = 0.0,
    cloud: float = 0.0,
    w_speed: float = 0.0,
    hpa: float = 0.0,
    net_load: float = 0.0
) -> str:
    """
    Adds a new grid observation to the feature store.
    """
    payload = {
        'Timestamp': timestamp,
        'Hist_Load': hist_load,
        'Elec_Load': elec_load,
        'Solar_kw': solar_kw,
        'Wind_kw': wind_kw,
        'RF_Error': rf_error,
        'C_Flag': c_flag,
        'C_R_S': c_r_s,
        'B_SOC': b_soc,
        'Temp': temp,
        'Humidity': humidity,
        'S_Irr': s_irr,
        'Cloud': cloud,
        'W_Speed': w_speed,
        'HPa': hpa,
        'Net_Load': net_load
    }
    
    feature_store.add_observation(payload)
    
    buffer_size = len(feature_store.buffer)
    is_ready = feature_store.is_primed
    
    status = f"✓ Observation added. Buffer: {buffer_size}/49. "
    if is_ready:
        status += "Feature store is PRIMED and ready for predictions."
    else:
        status += f"Need {49 - buffer_size} more observations."
    
    return status


@mcp.tool()
def predict_30min_Change() -> str:
    """
    Predicts the next grid ramp using the full feature engineering pipeline.
    """
    if not feature_store.is_primed:
        buffer_size = len(feature_store.buffer)
        return f"Feature store not ready. Current buffer: {buffer_size}/49. Add {49 - buffer_size} more observations."
    
    features = feature_store.get_inference_vector()
    if features is None:
        return "Failed to generate feature vector. Check feature store state."
    
    # Make prediction
    dmatrix = xgb.DMatrix(features)
    prediction = model.predict(dmatrix)[0]
    
    direction = "UP" if prediction > 0 else "DOWN"
    magnitude = abs(prediction)
    
    result = f"Predicted Ramp: {prediction:.2f} kW {direction}\n\n"
    
    if magnitude > 10000:
        result += "⚠️ CRITICAL: Large ramp predicted! Recommend immediate battery action.\n"
    elif magnitude > 5000:
        result += "⚡ MODERATE: Significant ramp detected. Monitor closely.\n"
    else:
        result += "✓ STABLE: Minor fluctuation predicted."
    
    return result

@mcp.tool()
def get_feature_store_status() -> str:
    """Returns the current status of the feature store buffer."""
    buffer_size = len(feature_store.buffer)
    is_ready = feature_store.is_primed
    
    status = f"Feature Store Status:\n"
    status += f"  Buffer Size: {buffer_size}/49\n"
    status += f"  Is Primed: {'✓ YES' if is_ready else '✗ NO'}\n"
    
    if is_ready and feature_store.buffer:
        last_obs = feature_store.buffer[-1]
        status += f"\nLast Observation:\n"
        status += f"  Timestamp: {last_obs.get('Timestamp', 'N/A')}\n"
        status += f"  Net Load: {last_obs.get('Net_Load', 'N/A')} kW\n"
    
    return status

@mcp.tool()
def dispatch_asset(asset_type: str, power_kw: float) -> str:
    """
    Simulates dispatching a grid asset (e.g., Gas Peaker, Battery).
    """
    client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=ORG)
    write_api = client.write_api(write_options=SYNCHRONOUS)
    
    point = Point("simulated_response") \
        .field("response_kw", float(power_kw)) \
        .tag("asset_type", asset_type) \
        .tag("action_source", "mcp_agent")
    
    write_api.write(bucket=BUCKET, org=ORG, record=point)
    return f"🚀 Dispatched {asset_type} with {power_kw} kW. Recorded in InfluxDB."

@mcp.tool()
def execute_trade(action: str, volume_kw: float) -> str:
    """
    Executes a virtual arbitrage trade (BUY/SELL) for the virtual power plant.
    """
    client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=ORG)
    write_api = client.write_api(write_options=SYNCHRONOUS)
    
    point = Point("trading_log") \
        .field("trade_volume", float(volume_kw)) \
        .tag("trade_action", action) \
        .tag("trade_source", "mcp_agent")
    
    write_api.write(bucket=BUCKET, org=ORG, record=point)
    return f"📉 Executed {action} trade for {volume_kw} kW. Recorded in trading log."


# --- PROMPTS ---
@mcp.prompt()
def analyze_resilience():
    """Generates a prompt for the AI to check if the grid is stable."""
    return "Check the current grid status and predict the next ramp. If the ramp is greater than 10MW, suggest a battery action."


if __name__ == "__main__":
    mcp.run()
