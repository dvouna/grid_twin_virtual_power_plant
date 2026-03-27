"""
MCP Client helper for the VPP Dashboard.

Connects to the GridIntelligence MCP server over SSE and provides:
  - `fetch_tools()`:  returns the list of available MCP tools
  - `call_tool()`:   executes a named tool and returns its result
  - `list_prompts()`: fetches registered MCP prompts
  - `get_prompt()`:  resolves a prompt by name
  - `check_server_health()`: pings /health

Reliability
-----------
All MCP SSE connections are wrapped with exponential-backoff retry via
`tenacity` to handle transient network blips, cold-start latency on Cloud
Run, and SSE drop-reconnects.

Retry policy (configurable via env):
  MCP_MAX_RETRIES   – total attempts (default 3)
  MCP_RETRY_WAIT_S  – initial wait in seconds (default 1.0); doubles each try
  MCP_RETRY_MAX_W_S – maximum wait cap in seconds (default 10.0)
"""

import asyncio
import logging
import os
from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.types import Tool
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

# ── Server configuration ─────────────────────────────────────────────────────
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8080")

# ── Retry policy (tune via env vars) ─────────────────────────────────────────
_MAX_RETRIES = int(os.getenv("MCP_MAX_RETRIES", "3"))
_WAIT_MIN = float(os.getenv("MCP_RETRY_WAIT_S", "1.0"))
_WAIT_MAX = float(os.getenv("MCP_RETRY_MAX_W_S", "10.0"))

# Exceptions that are safe to retry (transient network / SSE errors)
_RETRYABLE = (
    httpx.ConnectError,
    httpx.ReadTimeout,
    httpx.RemoteProtocolError,
    ConnectionError,
    OSError,
)

_retry = retry(
    retry=retry_if_exception_type(_RETRYABLE),
    stop=stop_after_attempt(_MAX_RETRIES),
    wait=wait_exponential(multiplier=1, min=_WAIT_MIN, max=_WAIT_MAX),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)


# ── Internal session helper ───────────────────────────────────────────────────
async def _open_session(url: str):
    """
    Context-manager-aware helper used by all public functions.
    Yields (read, write, session) after MCP handshake.
    """
    # Note: This is a thin wrapper so @_retry can be applied at the
    # *function* level cleanly, since async context managers cannot be
    # retried directly.
    async with sse_client(url) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


# ── Public API ────────────────────────────────────────────────────────────────

@_retry
async def fetch_tools() -> list[Tool]:
    """
    Connect to the MCP server and return the full tool list.
    Retried automatically on transient network errors.
    """
    url = f"{MCP_SERVER_URL}/sse"
    logger.info(f"fetch_tools → {url}")
    async with sse_client(url) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()
            tools = result.tools
            logger.info(f"Fetched {len(tools)} tools: {[t.name for t in tools]}")
            return tools


@_retry
async def call_tool(name: str, args: dict[str, Any]) -> str:
    """
    Call a named MCP tool with the given arguments.
    Retried automatically on transient network errors.

    Returns:
        Concatenated text content from the tool result.

    Raises:
        ValueError: If the tool itself reports an error.
    """
    url = f"{MCP_SERVER_URL}/sse"
    logger.info(f"call_tool '{name}' args={args}")
    async with sse_client(url) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(name, args)

    if result.isError:
        raise ValueError(f"MCP tool '{name}' error: {result.content}")

    if not result.content:
        return f"Tool '{name}' completed with no output."

    text_parts = [b.text for b in result.content if hasattr(b, "text")]
    return "\n".join(text_parts) if text_parts else str(result.content[0])


async def check_server_health() -> bool:
    """
    Ping the MCP server /health endpoint.
    Returns True if HTTP 200, False otherwise. Not retried (used for UI badge).
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{MCP_SERVER_URL}/health")
            return resp.status_code == 200
    except Exception as exc:
        logger.warning(f"MCP health check failed: {exc}")
        return False


@_retry
async def list_prompts() -> list[dict]:
    """
    Fetch all registered MCP prompts.
    Retried automatically on transient network errors.
    """
    url = f"{MCP_SERVER_URL}/sse"
    logger.info(f"list_prompts → {url}")
    async with sse_client(url) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_prompts()
            prompts = [
                {"name": p.name, "description": p.description or p.name}
                for p in result.prompts
            ]
            logger.info(f"Fetched {len(prompts)} prompts")
            return prompts


@_retry
async def get_prompt(name: str, arguments: dict[str, str] | None = None) -> str:
    """
    Retrieve the resolved text of a named MCP prompt.
    Retried automatically on transient network errors.
    """
    url = f"{MCP_SERVER_URL}/sse"
    logger.info(f"get_prompt '{name}' args={arguments}")
    async with sse_client(url) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.get_prompt(name, arguments=arguments or {})

    text_parts = []
    for msg in result.messages:
        parts = msg.content if isinstance(msg.content, list) else [msg.content]
        for part in parts:
            if hasattr(part, "text"):
                text_parts.append(part.text)
    return " ".join(text_parts) if text_parts else name
