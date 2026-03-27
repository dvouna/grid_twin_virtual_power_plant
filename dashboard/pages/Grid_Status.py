import os

import pandas as pd
import plotly.express as px
import streamlit as st
from influxdb_client import InfluxDBClient

st.set_page_config(page_title="Grid Status", page_icon="⚡", layout="wide")

st.title("⚡ Atlas AVT VPP Grid Status")
st.subheader("Telemetry & Load Forecasting")

# Connection Logic
URL = os.getenv("INFLUX_CLOUD_URL", "https://us-east-1-1.aws.cloud2.influxdata.com")
TOKEN = os.getenv("INFLUX_CLOUD_TOKEN")
ORG = os.getenv("INFLUX_CLOUD_ORG")
BUCKET = os.getenv("INFLUX_CLOUD_BUCKET")


@st.cache_data(ttl=10)  # Refresh data every 10 seconds
def fetch_grid_data():
    client = InfluxDBClient(url=URL, token=TOKEN, org=ORG)
    query_api = client.query_api()

    query = f'from(bucket: "{BUCKET}") |> range(start: -1h) |> filter(fn: (r) => r["_measurement"] == "ml_predictions")'
    tables = query_api.query(query)

    data = []
    for table in tables:
        for record in table.records:
            data.append({"time": record.get_time(), "value": record.get_value(), "field": record.get_field()})

    if not data:
        return pd.DataFrame(columns=["time", "value", "field"])

    return pd.DataFrame(data)


try:
    df = fetch_grid_data()

    if df.empty:
        st.warning("No live data found in the last hour. The grid telemetry stream may be down.", icon="⚠️")
    else:
        # --- KPI Section ---
        col1, col2, col3, col4, col5 = st.columns(5)

        def extract_latest(field_name):
            field_data = df[df["field"].str.lower() == field_name.lower()]
            if len(field_data) >= 2:
                latest = field_data["value"].iloc[-1]
                delta = latest - field_data["value"].iloc[-2]
                return latest, delta
            elif len(field_data) == 1:
                return field_data["value"].iloc[-1], 0.0
            return 0.0, 0.0

        latest_load, load_delta = extract_latest("Net_Load_kW")
        latest_solar, solar_delta = extract_latest("Solar_Output_kW")
        latest_wind, wind_delta = extract_latest("Wind_Output_kW")

        with col1:
            st.metric("Current Net Load", f"{latest_load:.2f} kW", f"{load_delta:.2f} kW")
        with col2:
            st.metric("Solar Output", f"{latest_solar:.2f} kW", f"{solar_delta:.2f} kW")
        with col3:
            st.metric("Wind Output", f"{latest_wind:.2f} kW", f"{wind_delta:.2f} kW")
        with col4:
            status = "STABLE" if abs(load_delta) < 40 else "WARNING"
            st.metric("Grid Stability", status)
        with col5:
            st.metric("Active Nodes", "12 Units")

        # --- Chart Section ---
        st.markdown("### Grid Heartbeat (Last 60 Minutes)")
        net_load_data = df[df["field"] == "Net_Load_kW"]
        fig = px.line(net_load_data, x="time", y="value", template="plotly_dark", color_discrete_sequence=["#00ffcc"])
        fig.update_layout(yaxis_title="Net Load (MW)", xaxis_title="Time")
        st.plotly_chart(fig, use_container_width=True)

except Exception as e:
    # Graceful Offline State Handling
    err_str = str(e).lower()
    if "unauthorized" in err_str:
        st.error("⚠️ DATA STREAM OFFLINE: Unauthorized Database Access", icon="🛑")
        st.info(
            "Please verify that `INFLUX_TOKEN`, `INFLUX_ORG`, and `INFLUX_BUCKET` are set correctly in your environment variables.",
            icon="🔐",
        )
    elif "connection" in err_str or "network" in err_str:
        st.error("⚠️ DATA STREAM OFFLINE: Network Connection Failed", icon="🛑")
        st.info("Could not connect to InfluxDB. Check your network or the `INFLUX_URL`.", icon="🌐")
    else:
        st.error(f"⚠️ DATA STREAM OFFLINE: An unexpected error occurred.", icon="🛑")
        with st.expander("View Error Details"):
            st.code(e)

    # Display an empty chart as a visual fallback instead of the page breaking
    st.markdown("### Grid Heartbeat (Last 60 Minutes)")
    fig = px.line(title="Grid Telemetry Currently Unavailable", template="plotly_dark")
    fig.update_xaxes(showgrid=False, zeroline=False, visible=False)
    fig.update_yaxes(showgrid=False, zeroline=False, visible=False)
    st.plotly_chart(fig, use_container_width=True)
