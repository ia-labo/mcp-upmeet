---
name: ialab-sqlmodel-relationship
description: Use when creating or modifying a SQLModel relationship (FK, many-to-many, computed property) in an IALab repository — detect via `.ialab-standards.json` at repo root (IALab harness marker) AND `sqlmodel` dependency AND `app/core/config.py` or `app/database.py` with explicit model registration. Forces the custom `Relationship` wrapper (lazy=selectin), import order in `app/core/config.py`, and the dynamic-not-stored pattern for `commission_achieved`/`cap` on cesaretbrutus. Skip on non-IALab repos.
---

# IALab SQLModel relationship

## Activation criteria

- `.ialab-standards.json` exists at repo root (IALab harness marker, posed by `ialab-template`)
- `sqlmodel` in `pyproject.toml` dependencies
- Task involves adding a model class, an FK, a `Relationship(...)`, or modifying a computed property

## Two non-obvious rules

### Rule 1 — Use the custom `Relationship` wrapper, not SQLModel's default

SQLModel's default `Relationship` is **lazy by default**, which causes N+1 queries in async contexts. CesaretBrutus introduced a wrapper that sets `lazy='selectin'` by default :

```python
# ❌ Bad — N+1 risk
from sqlmodel import Relationship

class Agent(SQLModel, table=True):
    sales: list["Sale"] = Relationship(back_populates="agent")

# ✅ Good
from app.core.db_relationship import Relationship

class Agent(SQLModel, table=True):
    sales: list["Sale"] = Relationship(back_populates="agent")
```

Reference : `IALAB/CetB/cesaretbrutus/app/core/db_relationship.py` and the rule in `CetB/cesaretbrutus/CLAUDE.md:131-138`.

For repos that don't have this wrapper yet (e.g., `monitoring`), still use `lazy='selectin'` explicitly :

```python
sales: list["Sale"] = Relationship(back_populates="agent", sa_relationship_kwargs={"lazy": "selectin"})
```

### Rule 2 — Import the model in `app/core/config.py` (or equivalent)

For SQLModel to register the table, the model module must be imported **somewhere** at startup. The convention in IALab repos is to import every model in `app/core/config.py` :

```python
# app/core/config.py
# Order matters : FK dependencies first
from app.models import User  # noqa: F401
from app.company.model import Company  # noqa: F401
from app.agent.model import Agent  # noqa: F401  (depends on Company)
from app.sale.model import Sale  # noqa: F401   (depends on Agent)
```

If you add a new model and forget this step, the table will not appear in `SQLModel.metadata.tables` and migrations won't catch it.

Reference : `cesaretbrutus/CLAUDE.md:131-138`.

## Cesaretbrutus-specific gotchas (dynamic computed fields)

`Agent.commission_achieved` and `Agent.cap` are **NOT stored fields you update**. They are computed dynamically via methods :

```python
# ❌ NEVER do this
agent.commission_achieved = 50_000  # forbidden — field is deprecated
agent.set_commission_achieved(50_000)  # forbidden — logs warning

# ✅ Always compute via method
current = agent.get_commission_achieved(db, as_of_date=date.today())
current_cap = agent.get_cap(db, as_of_date=date.today())
```

- Baseline date : `COMMISSION_BASELINE_DATE = 2025-09-30` (stored constant).
- Date reference for commissions : `sale.date_of_deed` (not `sale.created_at`, not payment date).
- Anniversary cycles : automatically respected — `get_commission_achieved` only counts since last anniversary.

In API responses, use `AgentRead.from_orm_with_relations(agent, db)` to inject computed values — this is the canonical pattern.

Reference : `CetB/cesaretbrutus/CLAUDE.md:276-301`.

## Adding a new domain module — full checklist

1. Create the directory : `app/<domain>/` with `__init__.py`, `model.py`, `schemas.py`, `controller.py` (router), `crud.py`, `services.py`.
2. Define the model in `model.py` using the custom `Relationship` wrapper.
3. Import the model in `app/core/config.py` (respect FK order).
4. Use `SQLModel.Field(..., foreign_key="other_table.id", ondelete="CASCADE")` for relationships.
5. Add computed properties with `@property` if business logic is needed.
6. Register the router in `app/main.py` (see `ialab-fastapi-endpoint` skill).
7. Generate the Alembic migration : `poetry run alembic revision --autogenerate -m "add <domain> table"`.
8. **Inspect the migration file** — autogenerate is not perfect. Verify FK directions, indexes, server defaults.
9. `poetry run alembic upgrade head` in dev DB.

## Gotchas

- `cesaretbrutus` uses **psycopg2** (sync) with QueuePool (pool_size=10, max_overflow=10, pool_recycle=1800). `monitoring` and `dashboard-api` use **asyncpg** (async). Don't mix patterns — match the repo's existing dialect.
- `cesaretbrutus/CLAUDE.md` mentions database timeouts set to 1 day in the connection string — that's intentional for long sync operations.
- For the very large `models.py` files, splitting at ~300 lines into subpackages is the documented convention (`monitoring/CLAUDE.md:62-73`). Re-export from `__init__.py`.

## Reference files

- `IALAB/CetB/cesaretbrutus/app/core/db_relationship.py` — wrapper definition
- `IALAB/CetB/cesaretbrutus/app/core/config.py` — model registration
- `IALAB/CetB/cesaretbrutus/app/agent/model.py` — canonical model with computed properties
- `IALAB/CetB/cesaretbrutus/app/cap/commission.py` — `get_cap`, `get_commission_achieved` reference implementations
