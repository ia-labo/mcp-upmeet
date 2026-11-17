"""Tests for the MCP tool layer, as seen by an in-memory MCP client."""

import asyncio

import httpx
from mcp import Client

from app import main
from app.core.settings import Settings
from app.upmeet import UpmeetClient


def _call_tool_in_memory(name: str, arguments: dict) -> object:
    """Call a tool on the server through a real MCP client session.

    Args:
        name: Tool name.
        arguments: Tool arguments.

    Returns:
        The ``CallToolResult`` received by the client.
    """

    async def _call() -> object:
        async with Client(main.mcp) as client:
            return await client.call_tool(name, arguments)

    return asyncio.run(_call())


def test_rejected_api_key_is_readable_by_the_client(monkeypatch):
    """A 401 reaches the model with its cause, not the generic 2.x tool error."""
    settings = Settings(
        api_key="BAD_KEY", base_url="https://api.test", timeout_seconds=1, max_retries=1
    )
    rejecting_client = UpmeetClient(
        settings, transport=httpx.MockTransport(lambda _: httpx.Response(401))
    )
    monkeypatch.setattr(main, "get_upmeet_client", lambda: rejecting_client)

    result = _call_tool_in_memory("list_projects", {})

    assert result.is_error
    assert "Upmeet rejected the API key (check UPMEET_API_KEY)" in result.content[0].text


def test_missing_api_key_is_readable_by_the_client(monkeypatch):
    """A missing key is reported to the model instead of being hidden."""
    monkeypatch.delenv("UPMEET_API_KEY", raising=False)
    main.get_upmeet_client.cache_clear()

    result = _call_tool_in_memory("get_project_details", {"project_id": 27})

    assert result.is_error
    assert "UPMEET_API_KEY is not set" in result.content[0].text
