import os

import pandas as pd
import plotly.express as px
import streamlit as st
from influxdb_client import InfluxDBClient

st.set_page_config(page_title="Financials", page_icon="💰", layout="wide")

st.title("💰 VPP Financial Performance")
st.subheader("Arbitrage Trading & Market Revenues")

# Connection Logic
URL = os.getenv("INFLUX_URL", "https://us-east-1-1.aws.cloud2.influxdata.com")
TOKEN = os.getenv("INFLUX_TOKEN")
ORG = os.getenv("INFLUX_ORG")
BUCKET = os.getenv("INFLUX_BUCKET")

st.info(
    "The Financials dashboard is currently under development. Here we will track the Arbitrage Trader's charging and discharging revenues."
)

# Placeholder Data for Demonstration
data = {
    "Time": pd.date_range("2026-02-20", periods=5, freq="1H"),
    "Revenue (USD)": [120.50, 135.00, -40.20, 180.00, 210.75],
    "Action": ["Sell", "Sell", "Buy", "Sell", "Sell"],
}
df = pd.DataFrame(data)

col1, col2 = st.columns(2)
with col1:
    st.metric("Total Hourly Revenue", "$606.05")
with col2:
    st.metric("Battery Cycles", "2", "-1")

fig = px.bar(
    df,
    x="Time",
    y="Revenue (USD)",
    color="Action",
    color_discrete_map={"Sell": "#00ffcc", "Buy": "#ff4b4b"},
    template="plotly_dark",
    title="Simulated Trading Hourly Revenue",
)
st.plotly_chart(fig, use_container_width=True)
