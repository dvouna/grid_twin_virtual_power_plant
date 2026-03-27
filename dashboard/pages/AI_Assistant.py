"""
VPP MCP Copilot — AI Assistant page.

Renders a Streamlit chat UI that drives the Gemini + MCP agentic loop.
Consumes typed AgentEvent dicts from run_agent() and renders each type:

  status     → shown inside st.status() (live progress steps)
  tool_start → added as a step in st.status()
  tool_end   → accumulated for the st.expander agent trace
  text       → streamed word-by-word into the chat bubble
  error      → shown inline in the chat bubble in red
"""

import asyncio
import os
import sys
from pathlib import Path

# Add project root to sys.path so 'dashboard.*' imports work from Streamlit pages
_project_root = str(Path(__file__).resolve().parent.parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import nest_asyncio
import streamlit as st
from dashboard.gemini_agent import run_agent
from dashboard.mcp_client import check_server_health, get_prompt, list_prompts

# Allow asyncio inside Streamlit's event loop
nest_asyncio.apply()

st.set_page_config(page_title="MCP AI Assistant", page_icon="🧠", layout="wide")

st.title("🧠 VPP MCP Copilot")
st.subheader("Natural Language Grid Intelligence")
st.markdown(
    "Interact with the **GridIntelligence MCP Server** using natural language. "
    "The AI Copilot can predict grid ramps, check agent status, and orchestrate "
    "VPP tools in real time."
)


# ---------------------------------------------------------------------------
# Helper: run the agentic loop and render events into the chat bubble
# ---------------------------------------------------------------------------
def _run_and_render(prompt: str, history: list[dict]) -> str:
    """
    Execute `run_agent` and render each typed event into the current
    st.chat_message('assistant') context.

    Returns the full assembled text response.
    """
    message_placeholder = st.empty()
    full_response = ""
    tool_traces: list[dict] = []

    # st.status provides the live tool-call progress panel
    with st.status("🤖 Running agent…", expanded=True) as status_box:

        async def consume():
            nonlocal full_response
            async for event in run_agent(prompt, history):
                etype = event.get("type")

                if etype == "status":
                    status_box.write(f"⚙️ {event['msg']}")

                elif etype == "tool_start":
                    args_preview = ", ".join(f"{k}={v!r}" for k, v in list(event["args"].items())[:3])
                    status_box.write(f"🔧 **Calling** `{event['name']}`({args_preview}…)")

                elif etype == "tool_end":
                    tool_traces.append(event)
                    icon = "✅" if event["ok"] else "❌"
                    status_box.write(f"{icon} `{event['name']}` returned ({len(event['result'])} chars)")

                elif etype == "text":
                    full_response += event["chunk"]
                    message_placeholder.markdown(full_response + "▌")

                elif etype == "error":
                    full_response += event["msg"]
                    message_placeholder.markdown(full_response)

        asyncio.run(consume())

        status_box.update(
            label="✅ Agent complete" if full_response else "⚠️ Agent returned no text",
            state="complete",
            expanded=False,
        )

    # Final render without the blinking cursor
    message_placeholder.markdown(full_response)

    # Agent trace expander — only shown when tools were called
    if tool_traces:
        with st.expander(f"🔍 Agent Trace — {len(tool_traces)} tool call(s)", expanded=False):
            for i, trace in enumerate(tool_traces, start=1):
                icon = "✅" if trace["ok"] else "❌"
                st.markdown(f"**{i}. {icon} `{trace['name']}`**")

                col_args, col_result = st.columns([1, 2])
                with col_args:
                    st.caption("Arguments")
                    st.json(trace["args"], expanded=True)
                with col_result:
                    st.caption("Result")
                    st.text(trace["result"])

                if i < len(tool_traces):
                    st.divider()

    return full_response


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ Configuration")

    mcp_url = os.getenv("MCP_SERVER_URL", "http://localhost:8080")
    gemini_key_set = bool(os.getenv("GEMINI_API_KEY"))
    gemini_model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

    st.markdown(f"**MCP Server:** `{mcp_url}`")
    st.markdown(f"**Model:** `{gemini_model}`")

    if gemini_key_set:
        st.success("✅ Gemini API Key loaded")
    else:
        st.error("❌ `GEMINI_API_KEY` not set — responses will fail")

    if st.button("🔄 Check MCP Health", use_container_width=True):
        with st.spinner("Pinging MCP server…"):
            is_healthy = asyncio.run(check_server_health())
        if is_healthy:
            st.success("✅ MCP Server is online")
        else:
            st.error("❌ MCP Server unreachable")

    st.divider()

    # --- Quick-action buttons from MCP prompts ---
    st.subheader("⚡ Quick Actions")
    st.caption("One-click prompts fetched from the live MCP server.")

    if "mcp_prompts" not in st.session_state:
        try:
            st.session_state.mcp_prompts = asyncio.run(list_prompts())
        except Exception:
            st.session_state.mcp_prompts = []

    fallback_prompts = [
        {
            "name": "analyze_resilience",
            "description": "Analyze grid resilience & predict next ramp",
        },
        {
            "name": "feature_store_check",
            "description": "Check feature store readiness",
        },
    ]

    prompt_list = st.session_state.mcp_prompts or fallback_prompts

    for mcp_prompt in prompt_list:
        label = mcp_prompt.get("description") or mcp_prompt["name"]
        if st.button(f"📎 {label}", key=f"qbtn_{mcp_prompt['name']}", use_container_width=True):
            st.session_state["pending_quick_prompt"] = mcp_prompt["name"]

    if not prompt_list:
        st.info("No quick actions — MCP server may be offline.")

    st.divider()
    st.caption("**Available MCP Tools**")
    st.markdown("""
- `predict_grid_ramp` — XGBoost ramp forecast
- `add_grid_observation` — Feed telemetry to buffer
- `get_feature_store_status` — Check model readiness
    """)
    st.divider()

    if st.button("🗑️ Clear Chat History", use_container_width=True):
        st.session_state.messages = [
            {
                "role": "assistant",
                "content": "Chat cleared. How can I help you manage the Virtual Power Plant?",
            }
        ]
        st.session_state.pop("pending_quick_prompt", None)
        st.rerun()


# ---------------------------------------------------------------------------
# Chat history
# ---------------------------------------------------------------------------
if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": (
                "I am the **SmartGrid-AI Copilot** powered by Gemini and the "
                "GridIntelligence MCP Server.\n\n"
                "I can:\n"
                "- 🔮 **Predict** the next grid ramp using the live XGBoost model\n"
                "- 📡 **Check** battery SOC, agent status, and feature store readiness\n"
                "- ⚡ **Recommend** battery charge/discharge actions based on ramp forecasts\n\n"
                "How can I help you manage the Virtual Power Plant today?"
            ),
        }
    ]

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])


# ---------------------------------------------------------------------------
# Quick-action prompt injection
quick_prompt_name = st.session_state.pop("pending_quick_prompt", None)
if quick_prompt_name:
    with st.spinner(f"Fetching MCP prompt `{quick_prompt_name}`…"):
        try:
            injected_text = asyncio.run(get_prompt(quick_prompt_name))
        except Exception:
            fallback_texts = {
                "analyze_resilience": (
                    "Check the current grid status and predict the next ramp. "
                    "If the ramp is greater than 10 MW, suggest a battery action."
                ),
                "feature_store_check": "What is the current status of the feature store buffer?",
            }
            injected_text = fallback_texts.get(quick_prompt_name, f"Run the '{quick_prompt_name}' analysis.")

    st.chat_message("user").markdown(f"*[Quick Action]* {injected_text}")
    st.session_state.messages.append({"role": "user", "content": injected_text})

    with st.chat_message("assistant"):
        history_for_agent = st.session_state.messages[:-1]
        response_text = _run_and_render(injected_text, history_for_agent)

    st.session_state.messages.append({"role": "assistant", "content": response_text})


# Manual chat input
if prompt := st.chat_input("Ask about grid stability, predict load, or check agent logs…"):
    st.chat_message("user").markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("assistant"):
        history_for_agent = st.session_state.messages[:-1]
        response_text = _run_and_render(prompt, history_for_agent)

    st.session_state.messages.append({"role": "assistant", "content": response_text})
