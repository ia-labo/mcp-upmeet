---
name: ialab-fastapi-endpoint
description: Use when creating or modifying a FastAPI endpoint in an IALab repository — detect via `.ialab-standards.json` at repo root (IALab harness marker) AND presence of `pyproject.toml` with `fastapi` + `sqlmodel` dependencies AND `app/routers/` directory. Enforces thin routers + fat services, JWT via Depends(get_current_user), Pydantic v2 model_validate, status import aliasing, pylint accepted disables only. Skip on Next.js, non-IALab repos, or scripts.
---

# IALab FastAPI endpoint

## Activation criteria (all must be true)

- `.ialab-standards.json` exists at repo root (IALab harness marker, posed by `ialab-template`)
- `pyproject.toml` exists at repo root with `fastapi` AND `sqlmodel` in dependencies
- `app/routers/` directory exists
- The task is about adding/modifying an HTTP endpoint (route, query, response model)

If the repo is `confideo` (Next.js + Prisma) or any non-IALab repo, skip this skill.

## Canonical pattern (observed in dashboard-api, monitoring, cesaretbrutus)

### Layout

```
app/
├── main.py                     # registers routers
├── routers/
│   └── <domain>.py             # thin : validate input → call service → return
├── services/
│   └── <domain>.py             # business logic, db sessions, side effects
├── models.py                   # SQLModel + Pydantic models
└── auth.py                     # get_current_user, JWT verification
```

### Router file template

```python
"""Routes for the <domain> domain."""

from fastapi import APIRouter, Depends, status as http_status
from sqlmodel import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import User, IncidentRead, IncidentCreate
from app.services.incidents import fetch_project_incidents, create_incident

router = APIRouter(prefix="/incidents", tags=["incidents"])


@router.get("", response_model=list[IncidentRead])
def list_incidents(
    project: str,
    limit: int = 50,
    _current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[IncidentRead]:
    """Return recent incidents for a project.

    Args:
        project (str): Project identifier (matches a config YAML key).
        limit (int): Maximum incidents to return.

    Returns:
        list[IncidentRead]: Incidents ordered by timestamp descending.

    Raises:
        HTTPException: 404 if project is unknown.
    """
    return fetch_project_incidents(db, project=project, limit=limit)


@router.post("", response_model=IncidentRead, status_code=http_status.HTTP_201_CREATED)
def post_incident(
    payload: IncidentCreate,
    _current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> IncidentRead:
    """Create an incident. Description per Google style..."""
    return create_incident(db, payload)
```

### Non-negotiable patterns

1. **Routers are thin** : validate → call service → return. No business logic, no DB queries directly in the route.
2. **JWT auth** via `_current_user: User = Depends(get_current_user)`. The underscore prefix marks it unused-by-name (Depends enforces the auth side effect).
3. **DB session** via `db: Session = Depends(get_db)`.
4. **Status alias** : `from fastapi import status as http_status` to avoid shadowing the `status` kwarg in Pydantic models or query params.
5. **Response model** declared on the decorator (`response_model=...`) — Pydantic v2 validates output.
6. **Query params > 4** → group into a `@dataclass` (the Pydantic / dataclass pattern is in `dashboard-api/CLAUDE.md:110`).
7. **Pydantic v2** : use `model_validate(data)` to parse dicts, not `**data` spread.
8. **Docstring Google style** mandatory on every route function.

### Service file template

```python
"""Business logic for the <domain> domain."""

from sqlmodel import Session, select

from app.models import Incident, IncidentCreate, IncidentRead


_DEFAULT_INCIDENT_LIMIT = 50  # named constant, no magic numbers


def fetch_project_incidents(
    db: Session,
    *,
    project: str,
    limit: int = _DEFAULT_INCIDENT_LIMIT,
) -> list[IncidentRead]:
    """Return recent incidents for a project."""
    stmt = (
        select(Incident)
        .where(Incident.project == project)
        .order_by(Incident.created_at.desc())
        .limit(limit)
    )
    rows = db.exec(stmt).all()
    return [IncidentRead.model_validate(r) for r in rows]
```

## Register the router

In `app/main.py` :

```python
from app.routers import incidents

app.include_router(incidents.router)
```

If you forget this, the endpoint won't be reachable. The CI/pre-commit won't catch it — only a runtime curl or test will.

## Common gotchas

- `dashboard-api` requires **pylint 10.00/10**. Even one unused import or missing docstring breaks the commit. Don't be sloppy.
- Other IALab repos require pylint ≥ 9.5/10.
- For **protected routes**, omitting `Depends(get_current_user)` is a security bug — flag it explicitly.
- For **SQLModel queries**, never trust relationships to be eager-loaded unless they use the custom `Relationship` wrapper from `app/core/db_relationship.py` (default lazy=selectin). See the `ialab-sqlmodel-relationship` skill.
- The `_current_user` underscore is correct Python convention (unused-by-name). pylint accepts it.
- For **new routes that read external data** (Anthropic, Netty), the service must use the existing caching layer (see `ialab-anthropic-haiku-sonnet`, `services/netty/api/cache.py`).
- **Tests** : add `app/tests/test_<domain>.py` mirroring existing fixtures (see `cesaretbrutus/app/tests/conftest.py` for the canonical setup).

## Reference files

- `IALAB/platform/dashboard-api/app/routers/incidents.py` — canonical thin router
- `IALAB/platform/dashboard-api/CLAUDE.md:104-111` — FastAPI patterns section
- `IALAB/platform/monitoring/app/main.py` — router registration pattern
- `IALAB/CetB/cesaretbrutus/app/main.py` — main with exception handlers + scheduler lifespan
