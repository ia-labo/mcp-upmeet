"""MCP server entrypoint exposing Upmeet projects (meetings) to agents over stdio."""

import logging
import sys
from functools import lru_cache
from typing import Any, Callable, Optional

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from app.core.settings import load_settings
from app.upmeet import UpmeetApiError, UpmeetClient, fetch_meeting_details, list_meetings

mcp = MCPServer("upmeet")


@lru_cache(maxsize=1)
def get_upmeet_client() -> UpmeetClient:
    """Build the shared client lazily so a missing API key surfaces on the first call.

    Returns:
        The authenticated Upmeet client.
    """
    return UpmeetClient(load_settings())


def _call_upmeet(operation: Callable[[UpmeetClient], dict[str, Any]]) -> dict[str, Any]:
    """Run an Upmeet operation, surfacing anticipated failures to the model.

    Since mcp 2.1 any exception other than ``ToolError`` reaches the client as a bare
    "Error executing tool <name>", which would hide actionable causes such as a bad key.

    Args:
        operation: Callable receiving the shared client and returning the tool result.

    Returns:
        The operation's result.

    Raises:
        ToolError: If the API key is missing or the Upmeet API call fails.
    """
    try:
        client = get_upmeet_client()
    except RuntimeError as exc:  # load_settings signals a missing UPMEET_API_KEY this way
        raise ToolError(str(exc)) from exc
    try:
        return operation(client)
    except UpmeetApiError as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool()
def list_projects(status: Optional[str] = None, page: int = 1) -> dict[str, Any]:
    """List Upmeet projects (meetings), most recent first.

    Args:
        status: Optional filter: pending, in_progress or finished.
        page: Page number, 50 projects per page.
    """
    return _call_upmeet(lambda client: list_meetings(client, status=status, page=page))


@mcp.tool()
def list_projects_by_theme(theme: str, page: int = 1) -> dict[str, Any]:
    """List Upmeet projects tagged with a theme (Upmeet tag name, comma-separated for several).

    Args:
        theme: Theme (tag) name, e.g. "daily".
        page: Page number, 50 projects per page.
    """
    return _call_upmeet(lambda client: list_meetings(client, theme=theme, page=page))


@mcp.tool()
def get_project_details(project_id: int, include_transcription: bool = True) -> dict[str, Any]:
    """Get a project's details: date, duration, themes, attendees, speakers, summary, transcript.

    Args:
        project_id: Project (meeting) id as returned by list_projects.
        include_transcription: Set to false to skip the full transcript on long meetings.
    """
    return _call_upmeet(
        lambda client: fetch_meeting_details(client, project_id, include_transcription)
    )


def _redirect_stdout_logging_to_stderr() -> None:
    """Move console log handlers off stdout, which carries the MCP stdio protocol.

    The vendored logger writes its console output to stdout and must not be edited.
    """
    for handler in logging.getLogger().handlers + logging.getLogger("app").handlers:
        if isinstance(handler, logging.StreamHandler) and handler.stream is sys.stdout:
            handler.setStream(sys.stderr)


def run_server() -> None:
    """Start the MCP server on stdio."""
    _redirect_stdout_logging_to_stderr()
    mcp.run(transport="stdio")


if __name__ == "__main__":
    run_server()
