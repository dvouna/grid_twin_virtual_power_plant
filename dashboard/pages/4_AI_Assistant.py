import time

import streamlit as st

st.set_page_config(page_title="MCP AI Assistant", page_icon="🧠", layout="wide")

st.title("🧠 VPP MCP Copilot")
st.subheader("Natural Language Grid Intelligence")

st.markdown("""
Interact directly with the underlying **Model Context Protocol (MCP)** server. The AI Copilot can read historical telemetry, check active agent status, and query the XGBoost predictor.
""")

st.info("Note: True MCP integration via stdio or SSE will replace this simulated interface.")

# Initialize chat history
if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": "I am the SmartGrid-AI Copilot. How can I help you manage the Virtual Power Plant today?",
        }
    ]

# Display chat messages from history on app rerun
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# React to user input
if prompt := st.chat_input("Ask about grid stability, predict load, or check agent logs..."):
    # Display user message in chat message container
    st.chat_message("user").markdown(prompt)
    # Add user message to chat history
    st.session_state.messages.append({"role": "user", "content": prompt})

    # Simulated Response Logic
    response = ""
    if "predict" in prompt.lower() or "forecast" in prompt.lower():
        response = "Based on the XGBoost model and recent telemetry, I predict the net load will reach **452.5 MW** in the next hour due to a drop in solar generation."
    elif "agent" in prompt.lower() or "trader" in prompt.lower():
        response = "The Arbitrage Trader is currently active and recently purchased 10 MW to charge the battery system."
    else:
        response = f"I am connected to the MCP Server, but I don't have a specific tool to answer that yet. I heard you ask: '{prompt}'"

    # Display assistant response in chat message container
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        full_response = ""
        # Simulate stream of response with milliseconds delay
        for chunk in response.split():
            full_response += chunk + " "
            time.sleep(0.05)
            # Add a blinking cursor to simulate typing
            message_placeholder.markdown(full_response + "▌")
        message_placeholder.markdown(full_response)

    # Add assistant response to chat history
    st.session_state.messages.append({"role": "assistant", "content": full_response})
