---
name: ialab-otel-prometheus
description: Use when adding OpenTelemetry instrumentation or a Prometheus `/metrics` endpoint to an IALab FastAPI service — detect via `.ialab-standards.json` at repo root (IALab harness marker) AND `opentelemetry-instrumentation-fastapi` or `prometheus-fastapi-instrumentator` in `pyproject.toml`. Ensures the service is discoverable by the central OTel Collector that ships to monitoring.ia-lab.fr. Skip on non-IALab repos or services without instrumentation infrastructure.
---

# IALab OTel + Prometheus instrumentation

## Activation criteria

- `.ialab-standards.json` exists at repo root (IALab harness marker, posed by `ialab-template`)
- `pyproject.toml` includes `opentelemetry-instrumentation-fastapi` OR `prometheus-fastapi-instrumentator`
- Task involves adding/modifying a service's observability (new instrument, new metric, OTel pipeline change)

## Why this matters (non-obvious)

IALab services are collected by a central OTel Collector running on the monitoring host. The Collector :

1. Scrapes each service's `/metrics` endpoint every 30s
2. Forwards via OTLP HTTP to `monitoring.ia-lab.fr` (which is the `monitoring` service in `IALAB/platform/monitoring`)
3. `monitoring` persists metrics to PostgreSQL → consumed by `dashboard-api` → displayed in `dashboard`

If you remove instrumentation or break the `/metrics` endpoint, alerts go dark. The `cesaretbrutus/CLAUDE.md:337-346` explicitly says : **"Ne pas supprimer l'instrumentation dans `app/main.py` sans en informer l'équipe IALab."**

## Canonical setup (from cesaretbrutus/app/main.py)

```python
"""FastAPI app entry point with OTel + Prometheus instrumentation."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_fastapi_instrumentator import Instrumentator

from app.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize OTel and scheduler at startup."""
    resource = Resource.create({"service.name": settings.service_name})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otel_collector_url))
    )
    trace.set_tracer_provider(provider)
    yield


app = FastAPI(lifespan=lifespan)

# Prometheus /metrics endpoint
Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)

# OTel auto-instrumentation for FastAPI routes
FastAPIInstrumentor.instrument_app(app)
```

Key points :

- **`service.name` tag** matches the project key in the central collector's config — must be unique per service.
- **`/metrics`** is `include_in_schema=False` — don't expose it in Swagger UI (security through obscurity, not a real defense, but the convention).
- **`OTEL_COLLECTOR_URL`** is environment-driven (`.env`) — never hardcoded.
- **OTLP HTTP exporter**, not gRPC — the central collector accepts HTTP only for IALab.

## What `/metrics` exposes by default

`prometheus-fastapi-instrumentator` adds :

- `http_requests_total{method, status, handler}` — request count
- `http_request_duration_seconds_bucket{...}` — latency histogram
- `http_requests_in_progress{method, handler}` — concurrency gauge

These are sufficient for SLO dashboards. **Don't add custom HTTP counters** — they duplicate the above.

## Adding custom metrics (business KPIs)

For non-HTTP counters (e.g., commission processed, email classified) :

```python
from prometheus_client import Counter, Histogram

EMAILS_CLASSIFIED = Counter(
    "emails_classified_total",
    "Number of emails classified by Haiku",
    ["project", "category"],
)

EMAILS_CLASSIFIED.labels(project="cetb", category="bug").inc()
```

The default Prometheus client registry is global — these counters appear automatically at `/metrics`.

## Coordination with `monitoring`

If you add a new `service.name` or a new business counter, **inform the team / update the YAML schema** :

- Service-level config : `IALAB/platform/monitoring/config/<slug>.yaml` (created via the dashboard wizard)
- New top-level YAML keys require updating the wizard schema : `IALAB/platform/dashboard/lib/wizard/schema.ts`

## Gotchas

- `cesaretbrutus` runs Prometheus and OTel **simultaneously** — Prometheus for HTTP metrics (collected by central OTel Collector), OTel spans for traces. Both are needed.
- `monitoring` itself is the central collector consumer, not a producer — it does NOT expose `/metrics` for itself, it INGESTS via `/v1/metrics` (OTLP).
- Adding tracing (spans) to a long-running scheduler task : use `trace.get_tracer(__name__).start_as_current_span(...)` — but watch the span volume, the central collector is not infinite.
- Don't add APM SDKs (Datadog, New Relic) in parallel — IALab is self-hosted via OTel only.

## Reference files

- `IALAB/CetB/cesaretbrutus/app/main.py` — canonical OTel + Prometheus setup
- `IALAB/platform/monitoring/app/otlp_receiver.py` — what the central collector ingests (you don't usually touch this, but it's the contract you're shipping to)
- `IALAB/CetB/cesaretbrutus/CLAUDE.md:337-346` — explicit non-removal warning
