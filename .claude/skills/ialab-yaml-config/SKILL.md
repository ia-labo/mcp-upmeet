---
name: ialab-yaml-config
description: Use when modifying a `config/*.yaml` file in an IALab monitored project, OR adding a top-level YAML key (alerts, thresholds, server metadata). Triggers on `config/*.yaml` in a repo carrying `.ialab-standards.json`, or in the central `monitoring` service (`platform/monitoring/config/*.yaml`). Forces coordination with the wizard's Zod schema and the loaders in `dashboard-api/app/config.py`. Skip on non-IALab YAML (Docker compose, GitHub Actions, etc.).
---

# IALab project YAML config

## Activation criteria

- File edited matches `platform/monitoring/config/*.yaml` OR `config/*.yaml` in a repo carrying `.ialab-standards.json`
- Task involves adding a new key, restructuring a section, or modifying a threshold

## What the YAML drives

Each IALab project monitored by the central `monitoring` service has a YAML file at `IALAB/platform/monitoring/config/<slug>.yaml`. This YAML drives :

1. **Alert routing** (Slack channel, WhatsApp number, GitHub repo for issues, email recipients)
2. **Email classification** rules (excluded_subjects, allowed_senders, bug_keywords, feedback_keywords, critical_keywords)
3. **Metric thresholds** (CPU%, RAM%, deadlocks, error_rate, avg_latency_ms — per-project)
4. **Server metadata** (GPU presence, Docker network name)
5. **FastAPI services** list (URLs to ping, expected status codes)
6. **PostgreSQL config** (which DB to monitor for connection / deadlock metrics)
7. **Reporting context** (business description injected into Anthropic narrative prompts)

## Three sources of truth — must stay in sync

When adding a new top-level key (or restructuring an existing one) :

1. **The YAML schema (implicit)** : `IALAB/platform/monitoring/config/cetb.yaml` is the canonical example. Read it before changing anything.
2. **The wizard schema (Zod)** : `IALAB/platform/dashboard/lib/wizard/schema.ts` — the dashboard "Nouveau projet" wizard validates user input against this Zod schema and emits the YAML. If your new key isn't here, the wizard can't emit it.
3. **The loaders in `dashboard-api`** : `IALAB/platform/dashboard-api/app/config.py` has `_load_display_names_from_yaml`, `_load_report_context_from_yaml`, `_load_server_gpus_from_yaml`. New keys exposed to the dashboard need a loader.

These run once at startup. Restart `dashboard-api` after YAML changes — there's no hot reload.

## Canonical structure (from cetb.yaml)

```yaml
project:
  slug: cetb
  display_name: Cesar et Brutus

server:
  hostname: cetb-prod
  gpu:                # null if CPU-only
    vendor: nvidia
    model: A4000
  docker_network: cetb_default

email:
  excluded_subjects: ["Automated notification", "Out of office"]
  allowed_senders: ["@cesaretbrutus.com", "@partner-domain.com"]
  bug_keywords: ["error", "bug", "broken", "doesn't work"]
  feedback_keywords: ["suggestion", "improvement"]
  critical_keywords: ["data loss", "all users", "production down"]

fastapi:
  services:
    - name: backend
      url: https://api.cesaretbrutus.com/health
      expected_status: 200

postgres:
  host: cetb-db-prod
  database: cetb

metrics:
  thresholds:
    cpu_percent: 85
    ram_percent: 90
    deadlocks_per_5min: 3
    error_rate_5xx: 0.05
    avg_latency_ms: 800

report:
  business_context: |
    CesaretBrutus is a real estate platform managing agents, sales, and
    tiered commissions. Critical periods : year-end commission calculations
    (December), anniversary CAP resets (per agent).

alerts:
  channels:
    slack:
      webhook: ${SLACK_WEBHOOK_URL}
      severities: [warning, critical]
    whatsapp:
      number: ${WHATSAPP_NUMBER}
      severities: [critical]
    github:
      repo: ialab/cesaretbrutus
      severities: [critical]
```

## Adding a new top-level key — checklist

1. **Edit the YAML** (e.g., add `server.cpu_cores: 8`).
2. **Update the Zod schema** : `IALAB/platform/dashboard/lib/wizard/schema.ts` — add the field, with validation.
3. **Update the wizard UI** : add the form input in the relevant wizard step.
4. **Add a loader** in `dashboard-api/app/config.py` if the value needs to surface in the dashboard.
5. **Use the value** in `monitoring` — e.g., in `app/services/metrics_alerter.py` if it's a threshold.
6. **Restart** `dashboard-api` and `monitoring` containers.

If you only need the value in `monitoring` (e.g., a new email keyword list), steps 2-4 are optional, but the wizard can't create projects with that key — only manual YAML editing.

## Secrets in YAML

Use `${ENV_VAR}` syntax for secrets — pydantic-settings interpolates these from `.env`. Never put real webhook URLs, API keys, or passwords in the YAML.

## Gotchas

- The wizard writes YAML via `POST /admin/projects` on `dashboard-api` (see `IALAB/platform/dashboard-api/app/routers/admin_projects.py`). The target path is `/monitoring/config/<slug>.yaml` via a bind mount from `platform/docker-compose.yml`. Don't relocate the YAML directory without coordinating both writers.
- `monitoring` does NOT hot-reload YAML — a container restart is required.
- For `server.gpu : null` (CPU-only projects), `dashboard-api` uses this flag to decide whether to render GPU widgets. Don't add `gpu: {}` (empty dict) — use explicit `null`.
- New top-level keys appear in `ProjectSummary` (`dashboard-api/app/routers/projects.py`) — verify the type matches the loader.

## Reference files

- `IALAB/platform/monitoring/config/cetb.yaml` — canonical example
- `IALAB/platform/monitoring/CLAUDE.md:18-21` — YAML schema note
- `IALAB/platform/dashboard/lib/wizard/schema.ts` — Zod schema (wizard source of truth)
- `IALAB/platform/dashboard-api/app/config.py` — YAML loaders
- `IALAB/platform/dashboard-api/app/routers/admin_projects.py` — write endpoint
