import os
import xgboost as xgb
import pandas as pd
from fastmcp import FastMCP
from influxdb_client import InfluxDBClient
from vpp.core.GridFeatureStore import GridFeatureStore

# ---- INITIALIZATION ----
mcp = FastMCP("GridIntelligence")

# Environment Variables for Cloud Run 
# These allow us to inject production credentials without changing code
INFLUX_URL = os.getenv("INFLUX_URL", "http://localhost:8086")
INFLUX_TOKEN = os.getenv("INFLUX_TOKEN", "smg!indb25")
ORG = os.getenv("INFLUX_ORG", "myorg")
BUCKET = os.getenv("INFLUX_BUCKET", "energy")

# File Paths (relative to PROJECT ROOT)
# When running as 'python -m vpp.mcp.mcp_server', the cwd is usually the project root.
MODEL_PATH = os.getenv("MODEL_PATH", "xgboost_smart_ml.ubj")
FEATURES_PATH = os.getenv("FEATURES_PATH", "model_features.txt")

# Loading existing model
model = xgb.Booster()
if os.path.exists(MODEL_PATH):
    model.load_model(MODEL_PATH)
    print(f"✓ Model loaded from {MODEL_PATH}")
else:
    print(f"⚠ Warning: Model not found at {MODEL_PATH}")

# Load expected feature columns from model training
expected_features = None
if os.path.exists(FEATURES_PATH):
    try:
        with open(FEATURES_PATH, "r") as f:
            expected_features = [line.strip() for line in f if line.strip()]
        print(f"✓ Loaded {len(expected_features)} expected features from {FEATURES_PATH}")
    except Exception as e:
        print(f"⚠ Error loading features: {e}")
else:
    print(f"⚠ Warning: {FEATURES_PATH} not found. Feature alignment may be inconsistent.")

# Initialize GridFeatureStore for feature engineering
feature_store = GridFeatureStore(window_size=49, expected_columns=expected_features)

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
    This accumulates data needed for lag and rolling window features.
    Call this repeatedly with real-time data before making predictions.
    
    Args:
        timestamp: ISO format timestamp (e.g., '2026-02-04T08:00:00')
        hist_load: Historical load (kW)
        elec_load: Electrical load (kW)
        solar_kw: Solar generation (kW)
        wind_kw: Wind generation (kW)
        rf_error: Random forest error
        c_flag: Control flag
        c_r_s: Control reserve state
        b_soc: Battery state of charge (%)
        temp: Temperature (°C)
        humidity: Humidity (%)
        s_irr: Solar irradiance
        cloud: Cloud cover (%)
        w_speed: Wind speed (m/s)
        hpa: Atmospheric pressure (hPa)
        net_load: Net load (kW)
    
    Returns:
        Status message indicating success and feature store readiness
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
        status += f"Need {49 - buffer_size} more observations to prime the feature store."
    
    return status


@mcp.tool()
def predict_grid_ramp() -> str:
    """
    Predicts the next grid ramp using the full feature engineering pipeline.
    Requires the feature store to be primed with at least 49 observations.
    Uses all 160 features (lags, rolling windows, interactions, cyclical features).
    
    Returns:
        Prediction result with ramp magnitude and direction, or error if not ready
    """
    if not feature_store.is_primed:
        buffer_size = len(feature_store.buffer)
        return f"❌ Feature store not ready. Current buffer: {buffer_size}/49. Add {49 - buffer_size} more observations."
    
    # Get the engineered feature vector
    features = feature_store.get_inference_vector()
    
    if features is None:
        return "❌ Failed to generate feature vector. Check feature store state."
    
    # Make prediction
    dmatrix = xgb.DMatrix(features)
    prediction = model.predict(dmatrix)[0]
    
    # Interpret results
    direction = "UP" if prediction > 0 else "DOWN"
    magnitude = abs(prediction)
    
    # Add context and recommendations
    result = f"🔮 Predicted Ramp: {prediction:.2f} kW {direction}\n\n"
    
    if magnitude > 10000:  # 10 MW threshold
        result += "⚠️ CRITICAL: Large ramp predicted! Recommend immediate battery action.\n"
        if prediction > 0:
            result += "   → Prepare battery discharge to meet rising demand."
        else:
            result += "   → Prepare battery charging with excess generation."
    elif magnitude > 5000:  # 5 MW threshold
        result += "⚡ MODERATE: Significant ramp detected. Monitor closely.\n"
        if prediction > 0:
            result += "   → Consider battery support for load increase."
        else:
            result += "   → Potential arbitrage opportunity on load decrease."
    else:
        result += "✓ STABLE: Minor fluctuation predicted. No immediate action required."
    
    return result


@mcp.tool()
def get_feature_store_status() -> str:
    """
    Returns the current status of the feature store buffer.
    Useful for debugging and monitoring data accumulation.
    
    Returns:
        Detailed status of the feature store including buffer size and readiness
    """
    buffer_size = len(feature_store.buffer)
    is_ready = feature_store.is_primed
    
    status = f"Feature Store Status:\n"
    status += f"  Buffer Size: {buffer_size}/49\n"
    status += f"  Is Primed: {'✓ YES' if is_ready else '✗ NO'}\n"
    
    if not is_ready:
        status += f"  Observations Needed: {49 - buffer_size}\n"
    else:
        status += f"  Expected Features: {len(feature_store.expected_columns) if feature_store.expected_columns else 'Unknown'}\n"
        
        # Show last observation if available
        if feature_store.buffer:
            last_obs = feature_store.buffer[-1]
            status += f"\nLast Observation:\n"
            status += f"  Timestamp: {last_obs.get('Timestamp', 'N/A')}\n"
            status += f"  Net Load: {last_obs.get('Net_Load', 'N/A')} kW\n"
            status += f"  Battery SOC: {last_obs.get('B_SOC', 'N/A')}%\n"
    
    return status


# --- PROMPTS ---
@mcp.prompt()
def analyze_resilience():
    """Generates a prompt for the AI to check if the grid is stable."""
    return "Check the current grid status and predict the next ramp. If the ramp is greater than 10MW, suggest a battery action."


if __name__ == "__main__":
    # Cloud Run requires an HTTP server listening on $PORT
    port = int(os.getenv("PORT", "8080"))
    # Use SSE for cloud deployment, stdio for local debugging
    transport = os.getenv("MCP_TRANSPORT", "sse")
    
    if transport == "sse":
        print(f"🚀 Starting MCP Server on port {port} via SSE...")
        mcp.run("sse", port=port)
    else:
        print("🤖 Starting MCP Server via stdio...")
        mcp.run()
