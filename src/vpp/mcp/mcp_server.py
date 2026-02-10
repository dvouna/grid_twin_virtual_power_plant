import os
import sys
import signal
import xgboost as xgb
from fastmcp import FastMCP
from influxdb_client import InfluxDBClient
from vpp.core.GridFeatureStore import GridFeatureStore
from starlette.requests import Request
from starlette.responses import PlainTextResponse

# ---- INITIALIZATION ----
mcp = FastMCP("GridIntelligence")

@mcp.custom_route("/health", methods=["GET"])
async def mcp_health_check(request: Request) -> PlainTextResponse:
    """Health check endpoint for Cloud Run startup probes."""
    # Ensure model is ready before serving traffic
    if not model:
        log("Health check FAILED: Model not loaded")
        return PlainTextResponse("Model Not Loaded", status_code=503)
    return PlainTextResponse("OK", status_code=200)

def log(message: str):
    """Utility to log to stderr to avoid corrupting stdio transport."""
    print(message, file=sys.stderr)

# Graceful shutdown handler
def sigterm_handler(_signo, _stack_frame):
    log("Received SIGTERM. Shutting down gracefully...")
    sys.exit(0)

signal.signal(signal.SIGTERM, sigterm_handler)

# Environment Variables for Cloud Run 
INFLUX_URL = os.getenv("INFLUX_CLOUD_URL", "https://us-east-1-1.aws.cloud2.influxdata.com")
INFLUX_TOKEN = os.getenv("INFLUX_CLOUD_TOKEN", "your-cloud-token-here")
ORG = os.getenv("INFLUX_CLOUD_ORG", "Energy Simulation")
BUCKET = os.getenv("INFLUX_CLOUD_BUCKET", "energy")

# File Paths (Absolute hooks)
# __file__ is /app/src/vpp/mcp/mcp_server.py
# dirname 1: /app/src/vpp/mcp
# dirname 2: /app/src/vpp
# dirname 3: /app/src
# dirname 4: /app
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
MODEL_PATH = os.path.join(BASE_DIR, "models", "xgboost_smart_ml.ubj")
FEATURES_PATH = os.path.join(BASE_DIR, "models", "model_features.txt")

log(f"Calculated BASE_DIR: {BASE_DIR}")
log(f"Calculated MODEL_PATH: {MODEL_PATH}")

# Debugging Info
log(f"Current Working Directory: {os.getcwd()}")

# Loading existing model
model = None
abs_model_path = os.path.abspath(MODEL_PATH)
log(f"Attempting to load model from: {abs_model_path}")

if os.path.exists(abs_model_path):
    try:
        model = xgb.Booster()
        model.load_model(abs_model_path)
        log(f"✓ Model successfully loaded from {abs_model_path}")
    except Exception as e:
        log(f"❌ Error loading model: {e}")
        model = None
else:
    log(f"⚠ Warning: Model file NOT FOUND at {abs_model_path}")

# Load expected feature columns from model training
expected_features = None
abs_features_path = os.path.abspath(FEATURES_PATH)
log(f"Attempting to load features from: {abs_features_path}")

if os.path.exists(abs_features_path):
    try:
        # Using utf-8-sig to automatically handle potential Byte Order Mark (BOM)
        with open(abs_features_path, "r", encoding='utf-8-sig') as f:
            expected_features = [line.strip() for line in f if line.strip()]
        log(f"✓ Loaded {len(expected_features)} expected features from {abs_features_path}")
    except Exception as e:
        log(f"❌ Error loading features: {e}")
else:
    log(f"⚠ Warning: Features file NOT FOUND at {abs_features_path}")

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
    
    # log(f"DEBUG: Added obs. Buffer size: {buffer_size}")
    
    status = f"Observation added. Buffer: {buffer_size}/49. "
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
    """
    if not feature_store.is_primed:
        buffer_size = len(feature_store.buffer)
        return f"Feature store not ready. Current buffer: {buffer_size}/49. Add {49 - buffer_size} more observations."
    
    # Get the engineered feature vector
    try:
        features = feature_store.get_inference_vector()
    except Exception as e:
        log(f" Error in get_inference_vector: {e}")
        import traceback
        log(traceback.format_exc())
        return f"Error: {e}"
    
    if features is None:
        return "Failed to generate feature vector. Check feature store state."
    
    # Make prediction
    try:
        # Explicitly pass feature names to match model training expectations
        dmatrix = xgb.DMatrix(features, feature_names=expected_features)
        prediction = model.predict(dmatrix)[0]
    except Exception as e:
        log(f" Error during XGBoost prediction: {e}")
        return f"Prediction Error: {e}"
    
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
    
    status = "Feature Store Status:\n"
    status += f"  Buffer Size: {buffer_size}/49\n"
    status += f"  Is Primed: {'✓ YES' if is_ready else '✗ NO'}\n"
    
    if not is_ready:
        status += f"  Observations Needed: {49 - buffer_size}\n"
    else:
        status += f"  Expected Features: {len(feature_store.expected_columns) if feature_store.expected_columns else 'Unknown'}\n"
        
        # Show last observation if available
        if feature_store.buffer:
            last_obs = feature_store.buffer[-1]
            status += "\nLast Observation:\n"
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
    # Cloud Run injects the PORT environment variable
    port = int(os.getenv("PORT", "8080"))
    transport = os.getenv("MCP_TRANSPORT", "sse")
    
    if transport == "sse":
        host = os.getenv("HOST", "0.0.0.0")
        log(f"🚀 Starting MCP Server on port {port} on {host} via SSE...")  # nosec B104
        mcp.run(transport="sse", host=host, port=port)
    else:
        # Standard input/output for local Claude Desktop use
        mcp.run(transport="stdio")
