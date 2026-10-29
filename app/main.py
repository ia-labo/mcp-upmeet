"""MCP server entrypoint exposing Upmeet projects (meetings) to agents over stdio."""

import logging
import sys
from functools import lru_cache
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP

from app.core.settings import load_settings
from app.upmeet import UpmeetClient, fetch_meeting_details, list_meetings

mcp = FastMCP("upmeet")


@lru_cache(maxsize=1)
def get_upmeet_client() -> UpmeetClient:
    """Build the shared client lazily so a missing API key surfaces on the first call.

    Returns:
        The authenticated Upmeet client.
    """
    return UpmeetClient(load_settings())


@mcp.tool()
def list_projects(status: Optional[str] = None, page: int = 1) -> dict[str, Any]:
    """List Upmeet projects (meetings), most recent first.

    Args:
        status: Optional filter: pending, in_progress or finished.
        page: Page number, 50 projects per page.
    """
    return list_meetings(get_upmeet_client(), status=status, page=page)


@mcp.tool()
def list_projects_by_theme(theme: str, page: int = 1) -> dict[str, Any]:
    """List Upmeet projects tagged with a theme (Upmeet tag name, comma-separated for several).

    Args:
        theme: Theme (tag) name, e.g. "daily".
        page: Page number, 50 projects per page.
    """
    return list_meetings(get_upmeet_client(), theme=theme, page=page)


@mcp.tool()
def get_project_details(project_id: int, include_transcription: bool = True) -> dict[str, Any]:
    """Get a project's details: date, duration, themes, attendees, speakers, summary, transcript.

    Args:
        project_id: Project (meeting) id as returned by list_projects.
        include_transcription: Set to false to skip the full transcript on long meetings.
    """
    return fetch_meeting_details(get_upmeet_client(), project_id, include_transcription)


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
    mcp.run()


if __name__ == "__main__":
    run_server()
