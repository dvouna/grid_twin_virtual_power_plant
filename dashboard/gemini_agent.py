"""
Gemini Agentic Loop for the VPP Dashboard.

Converts MCP tool schemas to Gemini FunctionDeclarations, then runs the
multi-turn agentic loop:
  1. Send user prompt + tool schemas → Gemini
  2. If Gemini requests tool calls → execute via MCP client
  3. Feed tool results back → Gemini
  4. Repeat until Gemini returns a final text response

Event protocol
--------------
run_agent() yields typed dicts so the UI can render each event appropriately:

  {"type": "status",     "msg": str}
      ↳ Connection or loop progress message (shown in st.status)
  {"type": "tool_start", "name": str, "args": dict}
      ↳ A tool call is about to execute (shown in st.status as a step)
  {"type": "tool_end",   "name": str, "args": dict, "result": str, "ok": bool}
      ↳ Tool result returned (accumulated into the expander trace)
  {"type": "text",       "chunk": str}
      ↳ A text chunk from Gemini's final response (streamed to chat bubble)
  {"type": "error",      "msg": str}
      ↳ Fatal error that stops the loop (shown inline in the chat bubble)
"""

import asyncio
import datetime
import json
import logging
import os
from typing import Any, AsyncGenerator

import google.generativeai as genai
from google.generativeai.types import GenerateContentResponse
from mcp.types import Tool

from dashboard.mcp_client import call_tool, fetch_tools, get_prompt, list_prompts

logger = logging.getLogger(__name__)

# ── Cloud Logging audit client (optional — only available on GCP) ─────────────
def _make_audit_logger():
    """Return a google.cloud.logging logger, or None if unavailable."""
    try:
        import google.cloud.logging as gcp_logging
        client = gcp_logging.Client()
        return client.logger("vpp-copilot-audit")
    except Exception:
        return None

_AUDIT_LOGGER = _make_audit_logger()


def _audit_log(payload: dict) -> None:
    """
    Write a structured audit record to Cloud Logging (prod) or stderr (local).

    Fields always present:
      ts        – UTC ISO timestamp
      prompt    – original user prompt
      tools     – list of tool names called
      response  – final assistant text (first 500 chars)
    """
    payload.setdefault("ts", datetime.datetime.utcnow().isoformat())
    if _AUDIT_LOGGER:
        try:
            _AUDIT_LOGGER.log_struct(payload, severity="INFO")
        except Exception as exc:  # pragma: no cover
            logger.warning(f"Cloud Logging write failed: {exc}")
    else:
        logger.info(f"[AUDIT] {json.dumps(payload)}") 

# --- Configuration ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

# Per-turn tool-call cap — prevents runaway agent loops (default: 10 calls/turn)
TOOL_CALL_LIMIT = int(os.getenv("MCP_TOOL_CALL_LIMIT", "10"))

# System prompt giving Gemini full VPP domain awareness
VPP_SYSTEM_PROMPT = """You are the SmartGrid-AI Copilot, an expert operations assistant
for a Virtual Power Plant (VPP) managing battery storage, solar, wind, and grid demand response.
Your role is to give grid operators fast, accurate, and actionable intelligence.

## Live MCP Tools
You have real-time access to the GridIntelligence MCP server with these tools:
- **add_grid_observation(timestamp, hist_load, elec_load, solar_kw, wind_kw, ...)**
  Feed a single timestep of raw telemetry into the rolling prediction buffer.
  The buffer must accumulate 49 observations before predictions are possible.
- **predict_grid_ramp()**
  Run the XGBoost model (160 engineered features — lags, rolling windows, cyclical time)
  to forecast the next grid ramp in kW. Interpret direction (UP/DOWN) and magnitude.
- **get_feature_store_status()**
  Report how full the prediction buffer is and whether the model is ready.

## Autonomous Agents in the System
These agents run continuously in the background. Refer to them by name when making recommendations:
- **ArbitrageTrader** — Monitors energy market prices and dispatches battery charge/discharge
  orders to exploit price spreads. Activates when price delta exceeds the configured threshold.
- **BatteryManager (GridResponseActor)** — Executes battery dispatch commands. Monitors State of
  Charge (SOC) and enforces min/max SOC limits (typically 20%–90%).
- **ConsumerML** — Runs the XGBoost inference pipeline on incoming Kafka telemetry and publishes
  load forecasts back to the grid topic.

## Decision Thresholds
- Ramp > **10 MW (10,000 kW)** → CRITICAL: Immediate battery action required
- Ramp **5–10 MW (5,000–10,000 kW)** → MODERATE: Monitor and prepare battery
- Ramp < **5 MW** → STABLE: No immediate action
- Battery SOC < **20%** → Do NOT discharge; risk of deep discharge
- Battery SOC > **90%** → Do NOT charge further; risk of overcharge

## Response Style
- Be concise and operational. Operators need answers in seconds, not paragraphs.
- Lead with the key metric or prediction (bolded), then give context.
- Use bullet lists for multi-step actions or recommendations.
- Always state units (kW, %, °C, hPa) explicitly.
- If a tool fails or the buffer isn't ready, explain why and what the operator should do next.
- Use Markdown formatting: **bold** for key values, `code` for tool names.
"""

# Type alias for agent events
AgentEvent = dict[str, Any]


def _mcp_tool_to_gemini(tool: Tool) -> genai.protos.Tool:
    """
    Convert an MCP Tool definition to a Gemini FunctionDeclaration Tool.
    """
    input_schema = tool.inputSchema or {}
    properties_raw = input_schema.get("properties", {})
    required = input_schema.get("required", [])

    type_map = {
        "STRING": genai.protos.Type.STRING,
        "NUMBER": genai.protos.Type.NUMBER,
        "INTEGER": genai.protos.Type.INTEGER,
        "BOOLEAN": genai.protos.Type.BOOLEAN,
        "ARRAY": genai.protos.Type.ARRAY,
        "OBJECT": genai.protos.Type.OBJECT,
    }

    properties: dict[str, genai.protos.Schema] = {
        param_name: genai.protos.Schema(
            type=type_map.get(param_info.get("type", "string").upper(), genai.protos.Type.STRING),
            description=param_info.get("description", ""),
        )
        for param_name, param_info in properties_raw.items()
    }

    return genai.protos.Tool(
        function_declarations=[
            genai.protos.FunctionDeclaration(
                name=tool.name,
                description=tool.description or "",
                parameters=genai.protos.Schema(
                    type=genai.protos.Type.OBJECT,
                    properties=properties,
                    required=required,
                ),
            )
        ]
    )


async def run_agent(
    user_prompt: str,
    conversation_history: list[dict],
) -> AsyncGenerator[AgentEvent, None]:
    """
    Run the Gemini agentic loop against the MCP server.

    Yields typed AgentEvent dicts (see module docstring for the event protocol).

    Args:
        user_prompt: The latest user message.
        conversation_history: Prior messages as [{role, content}], excluding
                              the current prompt.
    """
    if not GEMINI_API_KEY:
        yield {
            "type": "error",
            "msg": "⚠️ `GEMINI_API_KEY` is not set. Cannot connect to Gemini.",
        }
        return

    genai.configure(api_key=GEMINI_API_KEY)

    # ── Step 1: Fetch MCP tools ──────────────────────────────────────────────
    yield {"type": "status", "msg": "Connecting to MCP server…"}
    try:
        mcp_tools = await fetch_tools()
    except Exception as exc:
        yield {
            "type": "error",
            "msg": (
                f"❌ Could not reach MCP server: `{exc}`\n\n"
                "Ensure `MCP_SERVER_URL` is correct and the server is running."
            ),
        }
        return

    yield {
        "type": "status",
        "msg": f"Connected — {len(mcp_tools)} tool(s) available: "
               + ", ".join(f"`{t.name}`" for t in mcp_tools),
    }

    gemini_tools = [_mcp_tool_to_gemini(t) for t in mcp_tools]

    # ── Step 2: Build Gemini conversation history ────────────────────────────
    gemini_history = [
        {
            "role": "model" if msg["role"] == "assistant" else "user",
            "parts": [msg["content"]],
        }
        for msg in conversation_history
    ]

    # ── Step 3: Initialise model and chat ────────────────────────────────────
    model = genai.GenerativeModel(
        model_name=GEMINI_MODEL,
        system_instruction=VPP_SYSTEM_PROMPT,
        tools=gemini_tools,
    )
    chat = model.start_chat(history=gemini_history)

    # ── Step 4: Agentic loop ─────────────────────────────────────────────────
    current_message: Any = user_prompt
    max_iterations = 5

    # Phase 4: rate limiting and audit trail accumulators
    total_tool_calls = 0
    audit_tools_called: list[dict] = []
    final_response_text = ""

    for iteration in range(max_iterations):
        logger.info(f"Agentic loop — iteration {iteration + 1}/{max_iterations}")

        yield {"type": "status", "msg": f"Thinking… (iteration {iteration + 1})"}

        response: GenerateContentResponse = await asyncio.to_thread(
            chat.send_message, current_message
        )

        candidate = response.candidates[0]
        parts = candidate.content.parts

        # Detect tool calls vs final text
        tool_calls = [p for p in parts if p.function_call.name]

        if not tool_calls:
            # Final text response — yield each text part as a chunk
            yield {"type": "status", "msg": "Generating response…"}
            for part in parts:
                if part.text:
                    final_response_text += part.text
                    # Simulate word-level streaming for smooth UI
                    words = part.text.split(" ")
                    for i, word in enumerate(words):
                        separator = " " if i < len(words) - 1 else ""
                        yield {"type": "text", "chunk": word + separator}

            # ── Audit log ────────────────────────────────────────────────────
            _audit_log({
                "prompt": user_prompt[:500],
                "model": GEMINI_MODEL,
                "iterations": iteration + 1,
                "tools_called": audit_tools_called,
                "response_preview": final_response_text[:500],
            })
            return

        # ── Rate limiting guard ──────────────────────────────────────────────
        incoming_calls = len(tool_calls)
        if total_tool_calls + incoming_calls > TOOL_CALL_LIMIT:
            msg = (
                f"⚠️ Rate limit reached: this turn has already executed "
                f"{total_tool_calls} tool call(s). "
                f"The limit is {TOOL_CALL_LIMIT} per conversation turn to prevent runaway loops. "
                "Please start a new question."
            )
            yield {"type": "error", "msg": msg}
            _audit_log({
                "prompt": user_prompt[:500],
                "model": GEMINI_MODEL,
                "iterations": iteration + 1,
                "tools_called": audit_tools_called,
                "rate_limited": True,
            })
            return

        # ── Step 5: Execute tool calls via MCP ──────────────────────────────
        tool_responses = []

        for part in tool_calls:
            fc = part.function_call
            tool_name = fc.name
            tool_args = dict(fc.args)

            total_tool_calls += 1
            yield {"type": "tool_start", "name": tool_name, "args": tool_args}
            logger.info(f"Calling MCP tool '{tool_name}' args={tool_args}")

            try:
                result = await call_tool(tool_name, tool_args)
                logger.info(f"'{tool_name}' result (truncated): {result[:300]}")
                audit_tools_called.append({"name": tool_name, "args": tool_args, "ok": True})
                yield {
                    "type": "tool_end",
                    "name": tool_name,
                    "args": tool_args,
                    "result": result,
                    "ok": True,
                }
            except Exception as exc:
                result = f"Tool error: {exc}"
                logger.error(f"MCP tool '{tool_name}' failed: {exc}")
                audit_tools_called.append({"name": tool_name, "args": tool_args, "ok": False, "error": str(exc)})
                yield {
                    "type": "tool_end",
                    "name": tool_name,
                    "args": tool_args,
                    "result": result,
                    "ok": False,
                }

            tool_responses.append(
                genai.protos.Part(
                    function_response=genai.protos.FunctionResponse(
                        name=tool_name,
                        response={"result": result},
                    )
                )
            )

        current_message = tool_responses

    # Exhausted max iterations
    _audit_log({
        "prompt": user_prompt[:500],
        "model": GEMINI_MODEL,
        "iterations": max_iterations,
        "tools_called": audit_tools_called,
        "max_iterations_reached": True,
    })
    yield {
        "type": "error",
        "msg": "⚠️ Agent loop reached maximum iterations without a final answer.",
    }
