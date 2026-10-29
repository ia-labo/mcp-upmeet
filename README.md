# mcp-upmeet

MCP server that gives an AI agent read access to [Upmeet](https://upmeet.ai) meetings.

In Upmeet terms, a **project** is a meeting and a **theme** is a meeting tag.

## Tools

| Tool | Description | Upmeet endpoints |
|---|---|---|
| `list_projects(status?, page=1)` | List meetings, 50 per page. `status`: `pending`, `in_progress` or `finished`. | `GET /meetings` |
| `list_projects_by_theme(theme, page=1)` | List meetings tagged with `theme` (comma-separated for several). | `GET /meetings?tagsNames=` |
| `get_project_details(project_id, include_transcription=true)` | Dates, duration, themes, platform, summary, attendees, speakers and full transcript. | `/meetings/{id}`, `/attendees`, `/speakers`, `/full-transcription` |

## Setup

Requires Python 3.12+ and [Poetry](https://python-poetry.org).

```bash
poetry install --no-root
poetry run pre-commit install
```

## Configuration

The server reads its settings from environment variables (it does not load `.env` files):

| Variable | Required | Default |
|---|---|---|
| `UPMEET_API_KEY` | yes | — |
| `UPMEET_BASE_URL` | no | `https://api.upmeet.ai` |
| `UPMEET_TIMEOUT_SECONDS` | no | `30` |
| `UPMEET_MAX_RETRIES` | no | `3` |

The key is sent in the `X-Api-Token` header. Never commit it: export it in your shell.

```bash
export UPMEET_API_KEY=YOUR_UPMEET_API_KEY
```

## Usage

Quick check without an MCP client:

```bash
poetry run python -c "from app.main import list_projects; print(list_projects())"
```

### Claude Code

Add the server to `.mcp.json`; `${UPMEET_API_KEY}` is resolved from your shell:

```json
{
  "mcpServers": {
    "upmeet": {
      "command": "poetry",
      "args": ["run", "--directory", "/path/to/mcp-upmeet", "upmeet-mcp"],
      "env": { "UPMEET_API_KEY": "${UPMEET_API_KEY}" }
    }
  }
}
```

The server speaks MCP over stdio.

## Development

```bash
poetry run pytest                      # tests (Upmeet API is mocked)
poetry run pre-commit run --all-files  # black, isort, pylint
```

Layout:

```
app/
├── main.py           # MCP server and tool definitions
├── core/settings.py  # environment configuration
├── upmeet/
│   ├── client.py     # HTTP client: auth, timeout, bounded retries
│   └── meetings.py   # meeting listing and details
└── utils/logger.py   # vendored ialab-logging, do not edit
```

API errors fail loudly: a rejected key (401/403) raises `UpmeetApiError` instead of returning empty
results. Logs contain only request paths and status codes, never meeting content.
