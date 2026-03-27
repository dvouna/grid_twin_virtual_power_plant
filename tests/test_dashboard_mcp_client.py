"""
Unit tests for dashboard/mcp_client.py.

All external I/O is mocked:
  - sse_client     → mock async context manager yielding (read, write)
  - ClientSession  → mock with list_tools / call_tool / list_prompts / get_prompt
  - httpx.AsyncClient → mock for check_server_health

No live MCP server or network connection is required.
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

# Ensure project root is on sys.path so `dashboard` package resolves
_root = str(Path(__file__).resolve().parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tool(name: str):
    """Return a minimal MCP Tool-like mock."""
    tool = MagicMock()
    tool.name = name
    return tool


def _make_text_content(text: str):
    part = MagicMock()
    part.text = text
    return part


def _make_sse_patch(session_mock):
    """
    Build a mock for `sse_client` that yields (reader, writer) and allows
    `ClientSession` to be constructed from them.
    """
    read, write = MagicMock(), MagicMock()

    class _FakeSSE:
        async def __aenter__(self):
            return read, write

        async def __aexit__(self, *_):
            pass

    return _FakeSSE(), session_mock


def _make_session_mock(**kwargs):
    """Return a mock ClientSession with async methods pre-configured."""
    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.initialize = AsyncMock()

    for method, return_value in kwargs.items():
        getattr(session, method).return_value = return_value
        setattr(session, method, AsyncMock(return_value=return_value))

    return session


# ---------------------------------------------------------------------------
# fetch_tools
# ---------------------------------------------------------------------------

class TestFetchTools:
    @pytest.mark.asyncio
    async def test_returns_tool_list(self):
        tools = [_make_tool("predict_grid_ramp"), _make_tool("get_feature_store_status")]
        list_tools_result = MagicMock()
        list_tools_result.tools = tools

        session = _make_session_mock(list_tools=list_tools_result)

        with (
            patch("dashboard.mcp_client.sse_client") as mock_sse,
            patch("dashboard.mcp_client.ClientSession") as mock_cls,
        ):
            mock_sse.return_value.__aenter__ = AsyncMock(return_value=(MagicMock(), MagicMock()))
            mock_sse.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = session

            from dashboard.mcp_client import fetch_tools
            result = await fetch_tools()

        assert len(result) == 2
        assert result[0].name == "predict_grid_ramp"

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_tools(self):
        list_tools_result = MagicMock()
        list_tools_result.tools = []
        session = _make_session_mock(list_tools=list_tools_result)

        with (
            patch("dashboard.mcp_client.sse_client") as mock_sse,
            patch("dashboard.mcp_client.ClientSession") as mock_cls,
        ):
            mock_sse.return_value.__aenter__ = AsyncMock(return_value=(MagicMock(), MagicMock()))
            mock_sse.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = session

            from dashboard.mcp_client import fetch_tools
            result = await fetch_tools()

        assert result == []


# ---------------------------------------------------------------------------
# call_tool
# ---------------------------------------------------------------------------

class TestCallTool:
    @pytest.mark.asyncio
    async def test_returns_concatenated_text_content(self):
        content = [_make_text_content("Ramp predicted: 12 MW"), _make_text_content("Action: DISCHARGE")]
        tool_result = MagicMock()
        tool_result.isError = False
        tool_result.content = content
        session = _make_session_mock(call_tool=tool_result)

        with (
            patch("dashboard.mcp_client.sse_client") as mock_sse,
            patch("dashboard.mcp_client.ClientSession") as mock_cls,
        ):
            mock_sse.return_value.__aenter__ = AsyncMock(return_value=(MagicMock(), MagicMock()))
            mock_sse.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = session

            from dashboard.mcp_client import call_tool
            result = await call_tool("predict_grid_ramp", {})

        assert "Ramp predicted: 12 MW" in result
        assert "Action: DISCHARGE" in result

    @pytest.mark.asyncio
    async def test_raises_on_error_result(self):
        tool_result = MagicMock()
        tool_result.isError = True
        tool_result.content = [MagicMock()]
        session = _make_session_mock(call_tool=tool_result)

        with (
            patch("dashboard.mcp_client.sse_client") as mock_sse,
            patch("dashboard.mcp_client.ClientSession") as mock_cls,
        ):
            mock_sse.return_value.__aenter__ = AsyncMock(return_value=(MagicMock(), MagicMock()))
            mock_sse.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = session

            from dashboard.mcp_client import call_tool
            with pytest.raises(ValueError, match="MCP tool"):
                await call_tool("predict_grid_ramp", {})

    @pytest.mark.asyncio
    async def test_returns_placeholder_on_empty_content(self):
        tool_result = MagicMock()
        tool_result.isError = False
        tool_result.content = []
        session = _make_session_mock(call_tool=tool_result)

        with (
            patch("dashboard.mcp_client.sse_client") as mock_sse,
            patch("dashboard.mcp_client.ClientSession") as mock_cls,
        ):
            mock_sse.return_value.__aenter__ = AsyncMock(return_value=(MagicMock(), MagicMock()))
            mock_sse.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = session

            from dashboard.mcp_client import call_tool
            result = await call_tool("my_tool", {})

        assert "my_tool" in result


# ---------------------------------------------------------------------------
# check_server_health
# ---------------------------------------------------------------------------

class TestCheckServerHealth:
    @pytest.mark.asyncio
    async def test_returns_true_on_200(self):
        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("dashboard.mcp_client.httpx.AsyncClient") as mock_client_cls:
            instance = AsyncMock()
            instance.get = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=instance)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            from dashboard.mcp_client import check_server_health
            result = await check_server_health()

        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_on_non_200(self):
        mock_response = MagicMock()
        mock_response.status_code = 503

        with patch("dashboard.mcp_client.httpx.AsyncClient") as mock_client_cls:
            instance = AsyncMock()
            instance.get = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=instance)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            from dashboard.mcp_client import check_server_health
            result = await check_server_health()

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_on_network_error(self):
        with patch("dashboard.mcp_client.httpx.AsyncClient") as mock_client_cls:
            instance = AsyncMock()
            instance.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=instance)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            from dashboard.mcp_client import check_server_health
            result = await check_server_health()

        assert result is False


# ---------------------------------------------------------------------------
# list_prompts
# ---------------------------------------------------------------------------

class TestListPrompts:
    @pytest.mark.asyncio
    async def test_returns_prompt_list(self):
        p1 = MagicMock()
        p1.name = "analyze_resilience"
        p1.description = "Analyze grid resilience"
        list_prompts_result = MagicMock()
        list_prompts_result.prompts = [p1]
        session = _make_session_mock(list_prompts=list_prompts_result)

        with (
            patch("dashboard.mcp_client.sse_client") as mock_sse,
            patch("dashboard.mcp_client.ClientSession") as mock_cls,
        ):
            mock_sse.return_value.__aenter__ = AsyncMock(return_value=(MagicMock(), MagicMock()))
            mock_sse.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = session

            from dashboard.mcp_client import list_prompts
            result = await list_prompts()

        assert len(result) == 1
        assert result[0]["name"] == "analyze_resilience"
        assert result[0]["description"] == "Analyze grid resilience"
