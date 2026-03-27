"""
Unit tests for dashboard/gemini_agent.py.

Strategy
--------
`run_agent()` is an async generator that drives a Gemini ↔ MCP agentic loop.
We cannot call the real Gemini API in CI, so we mock:
  - `google.generativeai.GenerativeModel` / `chat.send_message`
  - `dashboard.mcp_client.fetch_tools`, `call_tool`

Each test scenario injects a specific Gemini response shape and asserts on
the sequence of AgentEvents yielded.
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure project root is on sys.path
_root = str(Path(__file__).resolve().parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

# ---------------------------------------------------------------------------
# Helpers to fabricate Gemini response objects
# ---------------------------------------------------------------------------

def _make_text_part(text: str):
    """Fake a Gemini response Part that contains only text."""
    part = MagicMock()
    part.text = text
    # No function_call
    fc = MagicMock()
    fc.name = ""
    part.function_call = fc
    return part


def _make_tool_call_part(name: str, args: dict):
    """Fake a Gemini response Part that contains a function_call."""
    part = MagicMock()
    part.text = ""
    fc = MagicMock()
    fc.name = name
    fc.args = args
    part.function_call = fc
    return part


def _make_gemini_response(parts: list):
    """Wrap parts in a fake GenerateContentResponse."""
    candidate = MagicMock()
    candidate.content.parts = parts
    response = MagicMock()
    response.candidates = [candidate]
    return response


def _make_mcp_tool(name="predict_grid_ramp"):
    tool = MagicMock()
    tool.name = name
    tool.description = "Test tool"
    tool.inputSchema = {"properties": {}, "required": []}
    return tool


# ---------------------------------------------------------------------------
# Shared patches context
# ---------------------------------------------------------------------------

def _base_patches(gemini_response, mcp_result="Tool result text"):
    """Return a dict of patch targets and their mocks for a standard run."""
    chat_mock = MagicMock()
    chat_mock.send_message = MagicMock(return_value=gemini_response)

    model_mock = MagicMock()
    model_mock.start_chat.return_value = chat_mock

    return {
        "dashboard.gemini_agent.genai.configure": MagicMock(),
        "dashboard.gemini_agent.genai.GenerativeModel": MagicMock(return_value=model_mock),
        "dashboard.gemini_agent.fetch_tools": AsyncMock(return_value=[_make_mcp_tool()]),
        "dashboard.gemini_agent.call_tool": AsyncMock(return_value=mcp_result),
        # Silence asyncio.to_thread so send_message is called synchronously in tests
        "dashboard.gemini_agent.asyncio.to_thread": AsyncMock(return_value=gemini_response),
    }


async def _collect(gen):
    """Drain an async generator into a list."""
    events = []
    async for event in gen:
        events.append(event)
    return events


# ---------------------------------------------------------------------------
# Test: missing API key
# ---------------------------------------------------------------------------

class TestMissingApiKey:
    @pytest.mark.asyncio
    async def test_yields_error_when_no_api_key(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "")
        # Force module-level constant to re-read (it's cached at import)
        with patch("dashboard.gemini_agent.GEMINI_API_KEY", ""):
            from dashboard.gemini_agent import run_agent
            events = await _collect(run_agent("Hello", []))

        assert len(events) == 1
        assert events[0]["type"] == "error"
        assert "GEMINI_API_KEY" in events[0]["msg"]


# ---------------------------------------------------------------------------
# Test: MCP server unreachable
# ---------------------------------------------------------------------------

class TestMCPServerUnreachable:
    @pytest.mark.asyncio
    async def test_yields_error_on_fetch_tools_failure(self):
        with (
            patch("dashboard.gemini_agent.GEMINI_API_KEY", "fake-key"),
            patch("dashboard.gemini_agent.genai.configure"),
            patch("dashboard.gemini_agent.fetch_tools", AsyncMock(side_effect=ConnectionError("refused"))),
        ):
            from dashboard.gemini_agent import run_agent
            events = await _collect(run_agent("Hello", []))

        error_events = [e for e in events if e["type"] == "error"]
        assert error_events, "Expected at least one error event"
        assert "MCP server" in error_events[0]["msg"] or "refused" in error_events[0]["msg"]


# ---------------------------------------------------------------------------
# Test: simple text-only response (no tool calls)
# ---------------------------------------------------------------------------

class TestTextOnlyResponse:
    @pytest.mark.asyncio
    async def test_yields_status_then_text_chunks(self):
        gemini_response = _make_gemini_response([_make_text_part("Grid is stable.")])

        patches = _base_patches(gemini_response)
        with (
            patch("dashboard.gemini_agent.GEMINI_API_KEY", "fake-key"),
            patch("dashboard.gemini_agent.genai.configure", patches["dashboard.gemini_agent.genai.configure"]),
            patch("dashboard.gemini_agent.genai.GenerativeModel", patches["dashboard.gemini_agent.genai.GenerativeModel"]),
            patch("dashboard.gemini_agent.fetch_tools", patches["dashboard.gemini_agent.fetch_tools"]),
            patch("dashboard.gemini_agent.asyncio.to_thread", patches["dashboard.gemini_agent.asyncio.to_thread"]),
        ):
            from dashboard.gemini_agent import run_agent
            events = await _collect(run_agent("What is the grid status?", []))

        types = [e["type"] for e in events]
        assert "status" in types
        assert "text" in types

        full_text = "".join(e.get("chunk", "") for e in events if e["type"] == "text")
        assert "Grid is stable" in full_text

    @pytest.mark.asyncio
    async def test_no_tool_end_events_for_text_response(self):
        gemini_response = _make_gemini_response([_make_text_part("SoC at 72%.")])
        patches = _base_patches(gemini_response)

        with (
            patch("dashboard.gemini_agent.GEMINI_API_KEY", "fake-key"),
            patch("dashboard.gemini_agent.genai.configure", patches["dashboard.gemini_agent.genai.configure"]),
            patch("dashboard.gemini_agent.genai.GenerativeModel", patches["dashboard.gemini_agent.genai.GenerativeModel"]),
            patch("dashboard.gemini_agent.fetch_tools", patches["dashboard.gemini_agent.fetch_tools"]),
            patch("dashboard.gemini_agent.asyncio.to_thread", patches["dashboard.gemini_agent.asyncio.to_thread"]),
        ):
            from dashboard.gemini_agent import run_agent
            events = await _collect(run_agent("Battery SoC?", []))

        assert not any(e["type"] == "tool_end" for e in events)


# ---------------------------------------------------------------------------
# Test: tool call followed by text response
# ---------------------------------------------------------------------------

class TestToolCallThenText:
    @pytest.mark.asyncio
    async def test_yields_tool_start_and_tool_end(self):
        tool_response = _make_gemini_response([_make_text_part("Ramp: 15 MW. Recommend discharge.")])

        # First call: Gemini returns a tool call
        tool_call_response = _make_gemini_response(
            [_make_tool_call_part("predict_grid_ramp", {})]
        )

        call_count = 0

        async def mock_to_thread(fn, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return tool_call_response
            return tool_response

        with (
            patch("dashboard.gemini_agent.GEMINI_API_KEY", "fake-key"),
            patch("dashboard.gemini_agent.genai.configure"),
            patch("dashboard.gemini_agent.genai.GenerativeModel") as mock_model_cls,
            patch("dashboard.gemini_agent.fetch_tools", AsyncMock(return_value=[_make_mcp_tool("predict_grid_ramp")])),
            patch("dashboard.gemini_agent.call_tool", AsyncMock(return_value="Ramp: 15 MW")),
            patch("dashboard.gemini_agent.asyncio.to_thread", mock_to_thread),
            patch("dashboard.gemini_agent.genai.protos.Part"),
            patch("dashboard.gemini_agent.genai.protos.FunctionResponse"),
        ):
            model_mock = MagicMock()
            chat_mock = MagicMock()
            model_mock.start_chat.return_value = chat_mock
            mock_model_cls.return_value = model_mock

            from dashboard.gemini_agent import run_agent
            events = await _collect(run_agent("Predict next ramp", []))

        types = [e["type"] for e in events]
        assert "tool_start" in types
        assert "tool_end" in types
        assert "text" in types

    @pytest.mark.asyncio
    async def test_tool_end_event_has_correct_name(self):
        tool_response = _make_gemini_response([_make_text_part("Done.")])
        tool_call_response = _make_gemini_response(
            [_make_tool_call_part("get_feature_store_status", {})]
        )
        call_count = 0

        async def mock_to_thread(fn, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            return tool_call_response if call_count == 1 else tool_response

        with (
            patch("dashboard.gemini_agent.GEMINI_API_KEY", "fake-key"),
            patch("dashboard.gemini_agent.genai.configure"),
            patch("dashboard.gemini_agent.genai.GenerativeModel") as mock_model_cls,
            patch("dashboard.gemini_agent.fetch_tools", AsyncMock(return_value=[_make_mcp_tool("get_feature_store_status")])),
            patch("dashboard.gemini_agent.call_tool", AsyncMock(return_value="Buffer: 49/50")),
            patch("dashboard.gemini_agent.asyncio.to_thread", mock_to_thread),
            patch("dashboard.gemini_agent.genai.protos.Part"),
            patch("dashboard.gemini_agent.genai.protos.FunctionResponse"),
        ):
            model_mock = MagicMock()
            model_mock.start_chat.return_value = MagicMock()
            mock_model_cls.return_value = model_mock

            from dashboard.gemini_agent import run_agent
            events = await _collect(run_agent("Check feature store", []))

        tool_ends = [e for e in events if e["type"] == "tool_end"]
        assert any(e["name"] == "get_feature_store_status" for e in tool_ends)


# ---------------------------------------------------------------------------
# Test: rate limiting
# ---------------------------------------------------------------------------

class TestRateLimit:
    @pytest.mark.asyncio
    async def test_error_emitted_when_tool_call_limit_exceeded(self):
        """When more tool calls arrive than TOOL_CALL_LIMIT, an error is yielded."""
        # Return a tool call on every Gemini response to exhaust the limit
        tool_call_response = _make_gemini_response(
            [_make_tool_call_part("predict_grid_ramp", {})]
        )

        with (
            patch("dashboard.gemini_agent.GEMINI_API_KEY", "fake-key"),
            patch("dashboard.gemini_agent.genai.configure"),
            patch("dashboard.gemini_agent.genai.GenerativeModel") as mock_model_cls,
            patch("dashboard.gemini_agent.fetch_tools", AsyncMock(return_value=[_make_mcp_tool()])),
            patch("dashboard.gemini_agent.call_tool", AsyncMock(return_value="ok")),
            patch("dashboard.gemini_agent.asyncio.to_thread", AsyncMock(return_value=tool_call_response)),
            patch("dashboard.gemini_agent.TOOL_CALL_LIMIT", 1),   # tiny limit
            patch("dashboard.gemini_agent.genai.protos.Part"),
            patch("dashboard.gemini_agent.genai.protos.FunctionResponse"),
        ):
            model_mock = MagicMock()
            model_mock.start_chat.return_value = MagicMock()
            mock_model_cls.return_value = model_mock

            from dashboard.gemini_agent import run_agent
            events = await _collect(run_agent("loop forever?", []))

        error_events = [e for e in events if e["type"] == "error"]
        assert error_events
        assert "limit" in error_events[0]["msg"].lower() or "rate" in error_events[0]["msg"].lower()
