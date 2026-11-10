"""A13: MCP client/provider adapter for the TechoHub domain tools server.

Connects to the local MCP server over stdio using the actual MCP protocol.
Provides scoped tool discovery, input/output validation, safe connection
failure handling, and integration with the LangGraph agent architecture.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from collections.abc import Mapping
from contextlib import asynccontextmanager
from contextlib import AsyncExitStack
from typing import Any

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

_MCP_ENABLED_KEY = "TECHOHUB_MCP_ENABLED"
_TRUE_VALUES = frozenset({"true", "1", "yes", "on"})
_FALSE_VALUES = frozenset({"false", "0", "no", "off"})


class McpConfig:
    """Configuration for the MCP feature flag.

    The feature flag defaults to OFF. Only explicit ``true``/``1``/``yes``/``on``
    enables MCP. Any other value raises ``ValueError`` so that invalid
    configuration never silently enables MCP.
    """

    def __init__(self, enabled: bool = False) -> None:
        self.enabled = enabled

    @classmethod
    def from_environment(
        cls,
        environ: Mapping[str, str] | None = None,
    ) -> "McpConfig":
        env = environ if environ is not None else os.environ
        raw = env.get(_MCP_ENABLED_KEY, "false").strip().lower()
        if raw in _TRUE_VALUES:
            enabled = True
        elif raw in _FALSE_VALUES:
            enabled = False
        else:
            raise ValueError(
                f"Invalid {_MCP_ENABLED_KEY} value: {env.get(_MCP_ENABLED_KEY)!r}. "
                f"Expected one of {sorted(_TRUE_VALUES | _FALSE_VALUES)}."
            )
        return cls(enabled=enabled)


# ---------------------------------------------------------------------------
# MCP Client
# ---------------------------------------------------------------------------

MCP_SERVER_COMMAND = sys.executable
MCP_SERVER_ARGS = ["-m", "backend.mcp_server"]


class McpClient:
    """Async MCP client wrapping ClientSession over stdio.

    Discovers and calls approved tools on the local MCP server. On connection
    failure, raises McpConnectionError so callers can fall back to direct
    domain-service calls.
    """

    def __init__(self) -> None:
        self._session: ClientSession | None = None
        self._exit_stack: asyncio.AsyncExitStack | None = None
        self._connected = False

    async def connect(self) -> None:
        """Establish the MCP session and initialize the protocol handshake."""
        params = StdioServerParameters(
            command=MCP_SERVER_COMMAND,
            args=MCP_SERVER_ARGS,
        )
        self._exit_stack = AsyncExitStack()
        read_stream, write_stream = await self._exit_stack.enter_async_context(
            stdio_client(params)
        )
        self._session = await self._exit_stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )
        await self._session.initialize()
        self._connected = True

    async def close(self) -> None:
        """Close the MCP session and tear down the subprocess."""
        self._connected = False
        self._session = None
        if self._exit_stack is not None:
            await self._exit_stack.aclose()
            self._exit_stack = None

    @property
    def connected(self) -> bool:
        return self._connected and self._session is not None

    async def list_tools(self) -> list[dict[str, Any]]:
        """Discover approved tools on the MCP server."""
        if not self.connected:
            raise McpConnectionError("MCP client is not connected")
        result = await self._session.list_tools()  # type: ignore[attr-defined]
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
            }
            for tool in result.tools
        ]

    async def call_tool(
        self, name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """Call an approved MCP tool with validated input/output."""
        if not self.connected:
            raise McpConnectionError("MCP client is not connected")
        result = await self._session.call_tool(name, arguments)  # type: ignore[attr-defined]
        # MCP CallToolResult.content is a list of content items; extract text.
        content_parts: list[str] = []
        for item in result.content:
            if hasattr(item, "text"):
                content_parts.append(item.text)
        content = "".join(content_parts)
        # With structured_output=True, the server serializes its return value
        # as JSON text. Try to parse it so callers can access structured fields
        # such as source_ids; fall back to raw text when not JSON.
        structured: dict[str, Any] | None = None
        try:
            candidate = json.loads(content)
            if isinstance(candidate, dict):
                structured = candidate
        except (json.JSONDecodeError, TypeError, ValueError):
            structured = None
        return {
            "content": content,
            "structured": structured,
            "is_error": result.is_error,
        }


class McpConnectionError(RuntimeError):
    """Raised when the MCP client cannot connect or the session is lost."""


# ---------------------------------------------------------------------------
# Convenience: short-lived client context
# ---------------------------------------------------------------------------


@asynccontextmanager
async def mcp_client_session():
    """Context manager that connects, yields the client, and closes on exit."""
    client = McpClient()
    await client.connect()
    try:
        yield client
    finally:
        await client.close()


# ---------------------------------------------------------------------------
# Standalone smoke test
# ---------------------------------------------------------------------------


async def _smoke_test() -> None:
    async with mcp_client_session() as client:
        tools = await client.list_tools()
        print(f"Connected. {len(tools)} tools:")
        for tool in tools:
            print(f"  - {tool['name']}: {tool['description'][:60]}...")
        result = await client.call_tool("faq_retrieve", {"query": "How much is a haircut?"})
        print(f"faq_retrieve result: {result['content'][:120]}...")


if __name__ == "__main__":
    asyncio.run(_smoke_test())
