<!-- ialab-standards: CODE.md v1.0 - generated, do not edit -->
<!-- ialab-standards-sha256: 1285fecccde106895fb6129cdeecd36b05af4b47ceb4d4ab4117e64aa09212e2 -->
# CODE.md — Coding standards, IALab (cross-repo)

> Reference for anyone (human or AI) working on any IALab repository. This file is
> **vendored**: it is generated from a single source of truth and stamped with a
> checksum. Do not edit it in place — edit the source and run
> `python scripts/ialab_standards.py sync`. The `ialab-standards` pre-commit hook
> fails on a hand-edited copy.
>
> Per-repo `CLAUDE.md` remains authoritative for domain-specific rules.

> Follow these rules on every change — no exceptions without a good reason documented in a comment.

---

## Pre-commit & Linting — Non-Negotiable

1. **All code must pass `pre-commit` without errors** before any commit.
2. **All code must satisfy `.pylintrc`** :
   - **dashboard-api : 10.00/10** (strict)
   - **monitoring, cesaretbrutus, dropshot, tools/server : ≥ 9.5/10**
3. **No wild `# pylint: disable=...`** scattered in the code.

### Acceptable `pylint: disable` use cases

| Disable tag | When acceptable |
|---|---|
| `broad-except` | Catch-all at a service/scheduler boundary where re-raising would crash the app |
| `global-statement` | Module-level mutable singleton explicitly documented |
| `import-outside-toplevel` | Deferred import to avoid circular dependency or optional heavy dep |
| `unused-argument` | API method where arg is required by contract but not used yet |

**Every disable must have a comment on the same line explaining why, and the line must stay ≤ 100 chars.**

### Run hooks manually

```bash
poetry run pre-commit run --all-files
# Or, to lint a single file at full pylint :
poetry run pylint app/path/to/file.py
```

---

## File Structure — One Responsibility Per File

> Don't dump everything in one file. If a file does two unrelated things, split it.

### Rules

- **One class or one cohesive group of functions per file.**
- If a file grows beyond ~300 lines, ask "can this be split?"
- If you add a new integration (e.g. PagerDuty, Teams) → create a new file `alerts_pagerduty.py`, don't bloat `alerts.py`.
- If you add new data models, add them to `models.py` unless they're specific to one module.

### Subpackages with `__init__.py` re-exports

When 3+ files share a domain :

```
app/
├── integrations/
│   ├── __init__.py        # re-exports the public API
│   ├── github/
│   │   ├── __init__.py
│   │   ├── issues.py
│   │   └── labels.py
│   └── notifications/
│       ├── __init__.py
│       ├── slack.py
│       └── whatsapp.py
```

```python
# app/integrations/github/__init__.py
from .issues import GitHubIssueManager
from .labels import ensure_labels

# Callers stay clean :
from app.integrations.github import GitHubIssueManager
```

---

## Docstrings — Google Style, English, Always

Every module, class, method, and private `_method` must have a docstring.

### Format

```python
def process_something(param_a: str, param_b: int) -> bool:
    """One-line summary ending with a period.

    Optional longer description when behavior isn't obvious from the signature.

    Args:
        param_a (str): What param_a represents.
        param_b (int): What param_b represents.

    Returns:
        bool: What True/False means in this context.

    Raises:
        ValueError: When and why this is raised.
    """
```

- **`__init__`** → document args on the class docstring, not on `__init__` itself.
- **Properties** → one-line summary + `Returns:` block.
- **Module** → one-line summary at the top of every `.py` file.

---

## Clean Code

### Naming

- **Variables and functions** : `snake_case`, descriptive nouns/verbs. No `x`, `tmp`, `data2`.
- **Constants** : `UPPER_SNAKE_CASE` at module level.
- **Private helpers** : `_underscore_prefix`.
- **Booleans** : `is_`, `has_`, `should_` prefixes.
- **Functions** : `verb_object_complement` pattern (`fetch_project_incidents`, `build_auth_token`).

### Functions

- One function = one job.
- Max ~25 statements, ~15 local variables (pylint enforces).
- Guard clauses / early returns over deep nesting.
- Extract inner loop bodies into helpers when nesting exceeds 3 levels.

### No magic values

```python
# BAD
if time_diff < 1800: ...

# GOOD
_CORRELATION_WINDOW_SECONDS = 1800
if time_diff < _CORRELATION_WINDOW_SECONDS: ...
```

### Logging, not print()

Every service uses the vendored **ialab-logging** module (`logger.py`, also managed by
`ialab_standards.py`). It writes a human-readable line to the console and one JSON object
per line to the log file — which is what the OTel Collector ships to ialab-monitoring, and
what makes the logs searchable from an agent.

```python
from app.utils.logger import get_logger  # or: from .logger import logger

logger = get_logger(__name__)

logger.info("Project loaded: %s", project_name)
logger.warning("IMAP reconnect failed for: %s", project)
logger.error("Failed to connect: %s", exc)
```

- **`print()` is forbidden in `app/`**.
- Use **`%s` lazy format** — never f-strings inside logger calls.
- FastAPI services must install `RequestIdMiddleware` so every line of one request shares
  a `request_id`. Without it, `get_log_context` cannot rebuild a request.
- Never reconfigure `logging` by hand in a module: the vendored logger owns the config,
  and the per-project values come from the environment (`ENV`, `IALAB_PROJECT`,
  `LOG_FILE`, `LOG_NAMESPACE`, `LOG_LEVEL`, `LOG_DIR`).

---

## Config Over Hardcode

- `.env` → credentials, URLs, API keys, intervals
- `config/*.yaml` (monitored projects only) → per-project rules
- `models.py` constants / enums → severity levels, report types

```python
# BAD
slack_webhook = "https://hooks.slack.com/services/XXX"

# GOOD
from app.config import settings
slack_webhook = settings.slack_webhook_url
```

The system must work with any `config/*.yaml` without touching Python code.

---

## Style Rules Summary

| Rule | Value |
|---|---|
| Line length | 100 chars |
| Formatter | `black --line-length 100` |
| Import sorting | `isort --profile black --line-length 100` |
| Linter | `pylint --rcfile=.pylintrc` (≥ 9.5/10, 10.00/10 for dashboard-api) |
| String quotes | Double (black enforced) |
| Logging | `logger` (centralized), `%s` lazy format, never f-string |
| `print()` | Forbidden in `app/` |

---

## Setup After Cloning a Repo

```bash
# Python version (cesaretbrutus = 3.12, monitoring = 3.10+, dashboard-api = 3.11+, dropshot api = 3.12)
poetry env use python3.12
poetry install --no-root
poetry self add poetry-plugin-shell  # if not present
poetry shell

# Pre-commit hooks
poetry run pre-commit install
```

---

## Git Conventions

- Commits in **English** only
- Format : `type(scope): description` + body 1-3 lines on *why*
- Types : `feat`, `fix`, `chore`, `docs`, `refactor`, `test`, `style`
- One concern per commit (no catch-all)
- **Never `git add .` or `git add -A`** — always stage by name
- **Never commit** : `.env*`, `.claude/`, secrets, tokens, real credentials

See the global skill `conventional-commit-en` for the full procedure.

---

## Sensitive Data & Anonymization

PRs, issues, commit messages, and Claude conversations are NOT strictly private :

- No real emails (use domain placeholders : `user@cesaretbrutus.com`, `dev@ia-lab.fr`)
- No real person names (use `Agent A`, `Mandate XXX-1234`)
- No real business amounts with identifying context
- No real internal UUIDs in production data

Full guidance : `~/.claude/skills/pii-anonymizer/SKILL.md`.

---

## Per-repo specifics

This file describes what's **common** across IALab repos. Each repo's `CLAUDE.md` remains authoritative for its own architecture, domain model, and exceptions. When in doubt, the repo CLAUDE.md wins.
