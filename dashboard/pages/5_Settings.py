import streamlit as st

st.set_page_config(page_title="Settings & Config", page_icon="⚙️", layout="wide")

st.title("⚙️ VPP Configuration Panel")
st.subheader("Live Operational Settings")

st.markdown("""
Use this panel to adjust the behavior of the autonomous agents. **Warning:** Changes made here will directly impact physical dispatch and financial trading once connected to the live control loop.
""")

st.divider()

col1, col2 = st.columns(2)

with col1:
    st.markdown("### 📈 Arbitrage Trader Settings")

    st.slider(
        "Buy Threshold ($/MWh)",
        min_value=0,
        max_value=200,
        value=25,
        step=5,
        help="The trader will buy energy to charge batteries when market price drops below this value.",
    )

    st.slider(
        "Sell Threshold ($/MWh)",
        min_value=50,
        max_value=500,
        value=120,
        step=10,
        help="The trader will sell stored energy when market price exceeds this value.",
    )

    st.checkbox("Enable Automated Trading", value=False, help="Toggle the arbitrage trader on/off.")

with col2:
    st.markdown("### 🔋 Battery Constraints & Safety")

    st.slider(
        "Maximum Discharge Rate (MW)",
        min_value=1.0,
        max_value=20.0,
        value=10.0,
        step=0.5,
        help="The maximum power the grid response actor is allowed to dispatch.",
    )

    st.slider(
        "Reserve Capacity (Minimum SOC)",
        min_value=0,
        max_value=50,
        value=20,
        step=5,
        format="%d%%",
        help="Never discharge below this battery percentage. Kept for critical emergency reserves.",
    )

st.divider()

st.markdown("### 🔔 Alerting Channels")
st.text_input("Slack Webhook URL", placeholder="https://hooks.slack.com/services/T0000/B0000/XXXX", type="password")

if st.button("Apply Settings", type="primary"):
    st.success(
        "Settings saved locally! (In the future, this will push configuration to the REDPANDA stream or environment)."
    )
