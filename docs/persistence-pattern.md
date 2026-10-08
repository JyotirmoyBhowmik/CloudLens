# Enterprise Persistence Architecture Pattern (Prompt P03)

## 1. Architectural Principles & Mandates

The CloudLens platform strictly forbids stateful, uncoordinated in-memory storage (`dict` / `list` singletons) in production paths. All persistence follows a strict hexagonal architectural boundary adhering to the following rules:

1. **Protocol-Driven Contracts (Pattern P1)**: Every domain persistence contract is defined as a Python `Protocol` with `@runtime_checkable` in `domain/<domain>/repository.py`.
2. **SQLAlchemy 2.0 Async (Pattern P1)**: The production implementation `Sql<Name>Repository` utilizes async sessions (`AsyncSession`), asyncpg, and connection pooling. Sync database engines are strictly banned from request paths.
3. **Fakes Isolated to Test Harnesses (Pattern P2)**: `InMemory<Name>Repository` implementations are relegated exclusively to `tests/fakes/` and prohibited from production runtime builds.
4. **Dependency Injection (Pattern P3)**: Repositories are injected into services and FastAPI endpoints via `Depends()`. Module-level singletons holding mutable dictionaries are abolished.
5. **Row-Level Security Isolation (Pattern P4)**: Every multi-tenant database session must invoke `get_tenant_session(tenant_id)` which executes `SET LOCAL app.current_tenant_id` within the transaction. All tenant tables enforce `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY`.
6. **Non-Owner Application Roles (Pattern P5)**: Database requests run under the `cloudlens_app` role (`NOBYPASSRLS`, `NOSUPERUSER`) preventing accidental RLS bypass.
7. **Production Startup Guard (Pattern P6)**: Any attempt to start staging or production with an `InMemory` repository or missing database URL immediately halts execution with a non-zero exit code (`sys.exit(1)`).

---

## 2. Canonical Repository Template

### A. Repository Protocol & Implementation (`domain/<domain>/repository.py`)

```python
"""Domain Repository Contract and PostgreSQL Implementation."""

from __future__ import annotations

import json
from typing import Any, Protocol, runtime_checkable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_tenant_session
from domain.<domain>.models import EntityModel


@runtime_checkable
class EntityRepository(Protocol):
    """Authoritative repository protocol for Entity."""

    async def get(self, entity_id: str, session: AsyncSession | None = None) -> EntityModel | None:
        """Fetch entity by ID under tenant RLS boundary."""
        ...

    async def save(self, entity: EntityModel, session: AsyncSession | None = None) -> EntityModel:
        """Persist or update entity under tenant RLS boundary."""
        ...

    async def delete(self, entity_id: str, session: AsyncSession | None = None) -> bool:
        """Delete entity under tenant RLS boundary."""
        ...


class SqlEntityRepository:
    """PostgreSQL production implementation with RLS enforcement."""

    is_in_memory: bool = False

    async def get(self, entity_id: str, session: AsyncSession | None = None) -> EntityModel | None:
        if session is not None:
            return await self._get_with_session(entity_id, session)
        async with get_tenant_session() as sess:
            return await self._get_with_session(entity_id, sess)

    async def _get_with_session(self, entity_id: str, session: AsyncSession) -> EntityModel | None:
        query = text("""
            SELECT id, tenant_id, data, updated_at
            FROM entities
            WHERE id = :eid
            LIMIT 1;
        """)
        result = await session.execute(query, {"eid": entity_id})
        row = result.fetchone()
        if not row:
            return None
        return EntityModel.model_validate(row[2])

    async def save(self, entity: EntityModel, session: AsyncSession | None = None) -> EntityModel:
        if session is not None:
            return await self._save_with_session(entity, session)
        async with get_tenant_session(entity.tenant_id) as sess:
            res = await self._save_with_session(entity, sess)
            await sess.commit()
            return res

    async def _save_with_session(self, entity: EntityModel, session: AsyncSession) -> EntityModel:
        query = text("""
            INSERT INTO entities (id, tenant_id, data, updated_at)
            VALUES (:id, :tenant_id, CAST(:data AS jsonb), NOW())
            ON CONFLICT (id)
            DO UPDATE SET
                data = EXCLUDED.data,
                updated_at = NOW();
        """)
        await session.execute(
            query,
            {
                "id": entity.id,
                "tenant_id": entity.tenant_id,
                "data": json.dumps(entity.model_dump(mode="json")),
            },
        )
        return entity
```

### B. In-Memory Fake for Unit Tests (`tests/fakes/<domain>.py`)

```python
"""In-memory fake for isolated unit testing."""

from domain.<domain>.models import EntityModel
from sqlalchemy.ext.asyncio import AsyncSession


class InMemoryEntityRepository:
    is_in_memory: bool = True

    def __init__(self) -> None:
        self._items: dict[str, EntityModel] = {}

    async def get(self, entity_id: str, session: AsyncSession | None = None) -> EntityModel | None:
        return self._items.get(entity_id)

    async def save(self, entity: EntityModel, session: AsyncSession | None = None) -> EntityModel:
        self._items[entity.id] = entity
        return entity

    async def delete(self, entity_id: str, session: AsyncSession | None = None) -> bool:
        return bool(self._items.pop(entity_id, None))
```

### C. FastAPI Route Injection (`api/cloudlens_api/routes/<domain>.py`)

```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.cloudlens_api.tenant_context import require_auth
from db.session import get_db_session
from domain.<domain>.repository import EntityRepository, get_entity_repository
from domain.tenant.context import TenantContext

router = APIRouter(prefix="/api/v1/entities", tags=["Entities"])


@router.get("/{entity_id}")
async def get_entity(
    entity_id: str,
    tc: TenantContext = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
    repo: EntityRepository = Depends(get_entity_repository),
):
    entity = await repo.get(entity_id, session=session)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    return entity
```

### D. Alembic Migration & RLS Policy Template

```python
"""Alembic migration for Entity table and RLS policy."""

def upgrade() -> None:
    op.create_table(
        "entities",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("data", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_entities_tenant", "entities", ["tenant_id"])

    # Enforce RLS
    op.execute("ALTER TABLE entities ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE entities FORCE ROW LEVEL SECURITY;")
    op.execute("""
        CREATE POLICY tenant_isolation_entities ON entities
        FOR ALL TO PUBLIC
        USING (
            tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')
            OR tenant_id = NULLIF(current_setting('cloudlens.current_tenant_id', true), '')
            OR current_setting('cloudlens.bypass_rls', true) = 'on'
        )
        WITH CHECK (
            tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')
            OR tenant_id = NULLIF(current_setting('cloudlens.current_tenant_id', true), '')
            OR current_setting('cloudlens.bypass_rls', true) = 'on'
        );
    """)
```
