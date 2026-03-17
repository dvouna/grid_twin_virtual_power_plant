import streamlit as st

st.set_page_config(
    page_title="Smart Grid VPP",
    page_icon="⚡",
    layout="wide",
)

# Custom CSS for the "Cyberpunk" Energy UI
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    div[data-testid="stMetricValue"] { color: #00ffcc; }
    </style>
    """, unsafe_allow_html=True)

st.title("⚡ Smart Grid Command Center")
st.sidebar.success("Select a dashboard above.")

st.markdown(
    """
    Welcome to the SmartGrid-AI Virtual Power Plant (VPP) control interface.
    
    ### Available Dashboards:
    - **Grid Status:** Real-time telemetry, net load forecasting, and system stability metrics.
    - **Financials:** Market bidding performance, energy arbitrage revenue, and battery optimization costs (Coming Soon).
    - **Agent Operations:** Live dispatch log of autonomous AI agents and battery State of Charge (SOC).
    - **AI Assistant:** Natural language chat interface interacting with the MCP Server.
    - **Settings:** Live operational configuration panel for trading and battery constraints.
    
    ---
    **System Architecture**
    - **Ingestion:** Redpanda (Kafka-compatible)
    - **Storage:** InfluxDB Cloud v3 (Time-Series)
    - **Inference:** XGBoost via Google Cloud Run
    - **Interface:** Model Context Protocol (MCP)
    """
)
