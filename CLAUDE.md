# CLAUDE.md — upmeet_mcp

> Instructions read automatically by Claude. Apply these rules to every change — no exceptions without a documented reason.
>
> This file holds only what is **specific to this project**. Everything cross-repo
> (linting, docstrings, naming, logging, git conventions, anonymization) lives in
> [CODE.md](CODE.md) — read it first, it is not repeated here.

> **SECURITY** — Never write real values (IPs, passwords, API keys, tokens, emails, phone numbers) in this file or any versioned file. Use placeholders such as `YOUR_KEY`, `YOUR_HOST`.
>
> **NEVER COMMIT SENSITIVE DATA** — `.env` files must never be committed, and `.env.example` must never contain real values. Never `git add .` or `git add -A`: stage explicitly by name. If a secret is committed, revoke it immediately, then clean the history with `git filter-repo`.

## Project Overview

MCP server giving AI agents read-only access to [Upmeet](https://upmeet.ai) meetings:
list them, filter by theme, fetch details (attendees, speakers, summary, transcript).
It runs as a local process launched by the MCP client and speaks MCP over stdio.

- **Language / runtime**: Python 3.12+, Poetry
- **Stack**: `mcp` 2.x SDK (`MCPServer`, stdio transport) + `httpx` (sync client). No web server, no database.
- **Deployed at**: not deployed — started locally by the MCP client (`poetry run upmeet-mcp`)
- **Monitored as**: `upmeet_mcp` — must match `project.name` in `monitoring/config/<slug>.yaml`

### Notable features (where to look first)

- **MCP tools** — `app/main.py`. All tools are declared there with `@mcp.tool()`; their docstrings are what the agent sees, so keep them accurate.
- **stdout redirection** — `app/main.py` (`_redirect_stdout_logging_to_stderr`). stdout carries the MCP protocol; the vendored logger writes to stdout, so its handlers are moved to stderr at startup.
- **Tool errors** — `app/main.py` (`_call_upmeet`). Since mcp 2.1 only `ToolError` messages reach the client; Upmeet and missing-key errors are re-raised as `ToolError` so the agent sees the cause. Keep new tools going through this helper.
- **HTTP client** — `app/upmeet/client.py`. API key auth (`X-Api-Token`), explicit timeout, bounded retries with backoff on network errors, 429 and 5xx.

## App Structure

```
app/
├── main.py           # MCP server, tool definitions, stdio entrypoint
├── core/settings.py  # settings from environment variables
├── upmeet/
│   ├── client.py     # HTTP client: auth, timeout, bounded retries
│   └── meetings.py   # meeting listing and details
└── utils/logger.py   # vendored ialab-logging — do not edit (see CODE.md)
```

## Commands

```bash
# Install
poetry install --no-root
poetry run pre-commit install

# Run (stdio MCP server, needs UPMEET_API_KEY in the environment)
poetry run upmeet-mcp

# Quick check without an MCP client
poetry run python -c "from app.main import list_projects; print(list_projects())"

# Lint (also enforced by the Claude Code hooks in .claude/settings.json)
poetry run pre-commit run --all-files

# Test (Upmeet API is mocked)
poetry run pytest
```

## Observability

Logs go through the vendored logger and are shipped to ialab-monitoring by the OTel
Collector (`otel/collector-config.yaml`). From an agent, use the `ialab-platform` MCP
server rather than SSH:

- `search_logs(project="upmeet_mcp", level="ERROR")` to find an error
- `get_log_context(request_id=...)` to replay the whole request behind it

Raw-log storage is opt-in per project: `logs.enabled` and `logs.min_level` in
`monitoring/config/<slug>.yaml`. Widening to `INFO` for a debugging session needs no
server access.

## Domain rules

- Upmeet vocabulary: a **project** is a meeting, a **theme** is a meeting tag. Tools expose
  "project"; the code and the Upmeet API use "meeting".
- Meeting `status` is one of `pending`, `in_progress`, `finished`. Listings are 50 per page.
- Meeting content (summaries, transcripts, attendee names) is client data: it must never be
  logged. Logs carry only request paths and status codes.
- API errors fail loudly: a rejected key (401/403) raises `UpmeetApiError`, never an empty result.

## Known pitfalls

- Never `print()` or write to stdout in server code: it corrupts the MCP stdio stream.
- Settings are read from the environment only — `.env` files are **not** loaded. Export
  `UPMEET_API_KEY` in the shell (or pass it through `.mcp.json`).
- The Upmeet client is built lazily: a missing `UPMEET_API_KEY` does not stop the server
  from starting, it fails on the first tool call.
