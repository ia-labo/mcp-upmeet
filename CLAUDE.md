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

<One paragraph: what this service does and for whom.>

- **Language / runtime**: <Python 3.12 | Node 20 | ...>
- **Stack**: <FastAPI + SQLModel + PostgreSQL | Next.js 14 + Tailwind | ...>
- **Deployed at**: <URL or "not deployed">
- **Monitored as**: `upmeet_mcp` — must match `project.name` in `monitoring/config/<slug>.yaml`

### Notable features (where to look first)

<Two to five bullets pointing at the non-obvious parts of the codebase: the file
that owns a tricky mechanism, the place where a convention is enforced, the
module a newcomer always looks for in the wrong place.>

- **<Feature>** — `<path/to/file.py>`. <Why it is worth knowing about.>

## App Structure

```
app/
├── main.py          # entrypoint, router registration, lifespan
├── core/            # settings, database, errors
├── utils/logger.py  # vendored ialab-logging — do not edit (see CODE.md)
├── <domain>/        # one folder per business domain
└── ...
```

## Commands

```bash
# Install
poetry install --no-root
poetry run pre-commit install

# Run
poetry run uvicorn app.main:app --reload

# Lint (also enforced by the Claude Code hooks in .claude/settings.json)
poetry run pre-commit run --all-files

# Test
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

<The business rules an agent cannot infer from the code: invariants, calculations
that look wrong but are intentional, endpoints deliberately left unauthenticated,
tenant isolation requirements.>

## Known pitfalls

<Traps that already cost someone an afternoon: a migration that must run before a
deploy, a cache to invalidate, an API that rate-limits, a test that needs a fixture
database.>
