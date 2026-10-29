---
name: ialab-bootstrap
description: Use when the user asks to apply the IALab harness to a repository — "bootstrap this repo", "aligne ce repo sur le template", "ajoute les hooks/CLAUDE.md/CODE.md", "mets le logger standard", "branche ce projet sur le monitoring". Applies `IALAB/ialab-template` to an existing repo in merge mode: adds what is missing, never overwrites hand-written content without showing the diff first. Skip for a brand-new project — there, copying the template directly is simpler.
---

# ialab-bootstrap

Aligns an existing repository on the IALab harness so an agent finds the same
conventions, the same logging, and the same guardrails everywhere.

Source of truth: a local checkout of the `ialab-template` repository (ask the user for its path if not found next to the current repo).
Canonical vendored files: `~/.claude/contexts/ialab/templates/` when present (Souheil's machine); otherwise use the template checkout directly.

## Never do

- Overwrite an existing `CLAUDE.md`, `.pre-commit-config.yaml`, `.pylintrc`, `docker-compose.yml`
  or `.claude/settings.json` without showing the user what changes and getting a yes.
- Touch `.env`. Environment variables go in `.env.example` with placeholder values.
- `git add .` — stage explicitly, one file at a time.
- Run `ialab_standards.py sync` on a repo whose logger has project-specific extras
  (dropshot's `setup_video_logger`, for instance) without first extracting them into a
  separate module. Sync overwrites the file wholesale.

## Step 1 — Detect

```bash
ls -a                              # what is already there
cat pyproject.toml package.json 2>/dev/null | head -40
find . -maxdepth 4 -name "logger*.py" -not -path "*/node_modules/*" -not -path "*/.venv/*"
grep -rn "logger import" --include='*.py' app 2>/dev/null | sed 's/:.*//' | sort -u | head
```

Establish:

- stack: Python/Poetry, Node/npm, or both
- where the logger lives and **how modules import it** (`from app.utils.logger import logger`,
  `from app.logger import get_logger`, `from core.logger import logger`) — the vendored module
  exposes both `logger` and `get_logger`, so either style keeps working
- which logger namespaces are in use (the package name of the modules that log)
- whether the repo already has a `CLAUDE.md`, and how much of it is cross-repo boilerplate

Report the findings before changing anything.

## Step 2 — Vendored files

Write `.ialab-standards.json` mapping the canonical names to this repo's paths:

```json
{"files": {"CODE.md": "CODE.md", "logger.py": "<the path found in step 1>"}}
```

Copy `~/.claude/contexts/ialab/templates/ialab_standards.py` to `scripts/`, then:

```bash
python scripts/ialab_standards.py sync
python scripts/ialab_standards.py check
```

If the repo already has a `CODING_STANDARDS.md`, `git mv` it to `CODE.md` first, then diff the
old content against the freshly synced one and surface anything repo-specific that would be
lost — that content belongs in `CLAUDE.md`, not in the vendored file.

## Step 3 — Wire the logging

1. FastAPI apps: add the middleware in `main.py`, right after the app is created.

   ```python
   from app.utils.logger import RequestIdMiddleware, logger

   app.add_middleware(RequestIdMiddleware)
   ```

   Without it there is no `request_id`, and `get_log_context` cannot rebuild a request.

2. Add the environment variables to `.env.example` **and** to the `environment:` block of the
   service in `docker-compose.yml` (not to `.env`, which is not versioned):

   ```yaml
   environment:
     ENV: production
     IALAB_PROJECT: <must match project.name in monitoring/config/<slug>.yaml>
     LOG_FILE: app.log
     # LOG_NAMESPACE: app,core   # only when modules log outside the "app" namespace
   ```

3. Check the log file path the container writes to matches what the OTel Collector tails.

## Step 4 — Hooks and linting

- Copy `.claude/hooks/*.py` and `.claude/settings.json` from the template. If a
  `.claude/settings.json` already exists, **merge** the `hooks` key into it rather than
  replacing the file — it may hold permissions the user relies on.
- If `.pre-commit-config.yaml` exists, append only the `ialab-standards` hook. If not, copy the
  template's.
- If `.pylintrc` is missing, copy the template's.

## Step 5 — MCP and OTel

- Copy `.mcp.json`, fixing the relative path to `platform/mcp-server` for this repo's depth.
- Copy `otel/collector-config.yaml` only if the repo has no `otel/` yet, and replace every
  `<PLACEHOLDER>`. If a collector config already exists, add the `logs` pipeline and the
  `filelog` receiver to it instead of overwriting.

## Step 6 — CLAUDE.md

- No `CLAUDE.md`: copy the template's and fill it in from what you learned in step 1.
- Existing `CLAUDE.md`: do not replace it. Strip the sections now covered by `CODE.md`
  (linting rules, docstring format, naming, git conventions, sensitive files), keep everything
  project-specific, and add a line at the top pointing to `CODE.md`. Show the diff before applying.

## Step 7 — Verify

```bash
python scripts/ialab_standards.py check
poetry run pre-commit run --all-files
poetry run pytest                       # if the repo has tests
python -c "from app.utils.logger import logger; logger.info('bootstrap ok')"
```

Then report: what was added, what was merged, what was left alone and why.

## Enabling raw-log storage

Bootstrapping a repo does not by itself make its logs searchable. That needs, on the
ialab-monitoring side, a `logs` block in `monitoring/config/<slug>.yaml`:

```yaml
logs:
  enabled: true
  min_level: WARNING     # INFO for a debugging session
  retention_days: 14
  max_records_per_batch: 500
```

Mention it in the final report if the project is monitored.
