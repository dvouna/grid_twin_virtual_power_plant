import os

import pandas as pd
import plotly.express as px
import streamlit as st
from influxdb_client import InfluxDBClient

st.set_page_config(page_title="Grid Status", page_icon="⚡", layout="wide")

st.title("🔋 Real-time Grid Status")
st.subheader("Telemetry & Load Forecasting")

# Connection Logic
URL = os.getenv("INFLUX_URL", "https://us-east-1-1.aws.cloud2.influxdata.com")
TOKEN = os.getenv("INFLUX_TOKEN")
ORG = os.getenv("INFLUX_ORG")
BUCKET = os.getenv("INFLUX_BUCKET")


@st.cache_data(ttl=10)  # Refresh data every 10 seconds
def fetch_grid_data():
    client = InfluxDBClient(url=URL, token=TOKEN, org=ORG)
    query_api = client.query_api()

    query = f'from(bucket: "{BUCKET}") |> range(start: -1h) |> filter(fn: (r) => r["_measurement"] == "grid_telemetry")'
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
        col1, col2, col3 = st.columns(3)
        net_load_data = df[df["field"] == "net_load"]

        if len(net_load_data) >= 2:
            latest_load = net_load_data["value"].iloc[-1]
            prev_load = net_load_data["value"].iloc[-2]
            delta = latest_load - prev_load
        elif len(net_load_data) == 1:
            latest_load = net_load_data["value"].iloc[-1]
            delta = 0.0
        else:
            latest_load = 0.0
            delta = 0.0

        with col1:
            st.metric("Current Net Load", f"{latest_load:.2f} MW", f"{delta:.2f} MW")
        with col2:
            status = "STABLE" if abs(delta) < 40 else "WARNING"
            st.metric("Grid Stability", status)
        with col3:
            st.metric("Active Nodes", "12 Units")

        # --- Chart Section ---
        st.markdown("### Grid Heartbeat (Last 60 Minutes)")
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
