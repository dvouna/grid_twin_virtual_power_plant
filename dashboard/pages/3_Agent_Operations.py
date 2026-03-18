import time

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Agent Operations", page_icon="🤖", layout="wide")

st.title("🤖 Autonomous Agent Operations")
st.subheader("Live Dispatch Log & State of Charge")

st.info(
    "This is a placeholder page. It will connect to the active grid_response_actor.py and arbitrage_trader.py output streams."
)

col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Grid Response Actor", "Active", "Normal")
with col2:
    st.metric("Arbitrage Trader", "Active", "Normal")
with col3:
    st.metric("Current Battery SOC", "42%", "+5%")

st.markdown("### Recent Actions")

# Placeholder agent action data
data = {
    "Timestamp": [pd.Timestamp.now() - pd.Timedelta(minutes=i * 15) for i in range(5)],
    "Agent": ["Arbitrage Trader", "Grid Response Actor", "Arbitrage Trader", "Arbitrage Trader", "Grid Response Actor"],
    "Action": ["DISCHARGE", "STANDBY", "CHARGE", "CHARGE", "DISCHARGE"],
    "Details": [
        "Sold 5 MW for Arbitrage",
        "Frequency Stable at 60.01Hz",
        "Bought 8 MW for Arbitrage",
        "Bought 10 MW for Arbitrage",
        "Dispatched 2MW for Freq Response",
    ],
    "Impact (MW)": [-5.0, 0.0, +8.0, +10.0, -2.0],
}

df = pd.DataFrame(data)

# Styling the dataframe to look like a terminal/log feed
st.dataframe(
    df,
    column_config={
        "Timestamp": st.column_config.DatetimeColumn(format="HH:mm:ss"),
        "Impact (MW)": st.column_config.NumberColumn(format="%.2f MW"),
        "Action": st.column_config.TextColumn(),
    },
    use_container_width=True,
    hide_index=True,
)

st.markdown("---")
st.markdown("### Battery Optimization Logic")
st.code(
    """
# Future Integration with arbitrage_trader.py
def optimize_dispatch(predicted_load, current_price, current_soc):
    if predicted_load > THRESHOLD and current_price > BUY_PRICE:
        return "DISCHARGE"
    elif current_price < BUY_PRICE and current_soc < MAX_SOC:
        return "CHARGE"
    return "STANDBY"
""",
    language="python",
)
