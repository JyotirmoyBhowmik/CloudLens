"""Real-Database Append-Only Immutability Tests for audit_event (Prompt P04).

Enforces:
- Direct SQL UPDATE on audit_event is rejected with DB exception PERMISSION_DENIED.
- Direct SQL DELETE on audit_event is rejected with DB exception PERMISSION_DENIED.
- Proves database-level trigger enforcement.
"""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from db.session import get_tenant_session

pytestmark = [pytest.mark.realdb]


@pytest.mark.asyncio
async def test_audit_event_update_rejected_by_database():
    """Proves that UPDATE on audit_event is rejected by PostgreSQL trigger."""
    tenant_id = f"ten-{uuid.uuid4().hex[:8]}"
    event_id = f"aud-{uuid.uuid4().hex[:12]}"
    now = datetime.now(UTC)

    # 1. Insert an audit event record under tenant context
    async with get_tenant_session(tenant_id) as session:
        insert_query = text("""
            INSERT INTO audit_event (
                id, occurred_at, tenant_id, actor_id, action, entity_type, entity_id, correlation_id,
                event_type, actor_roles, details, previous_event_hash, event_hash, ip_address, user_agent
            )
            VALUES (
                :id, :occurred_at, :tenant_id, :actor_id, 'CONFIG_SET', 'system', 'sys-001', 'corr-1',
                'SYSTEM_CONFIGURATION_CHANGED', '[]'::jsonb, '{}'::jsonb, NULL, 'hash-genesis', '127.0.0.1', 'pytest'
            );
        """)
        await session.execute(
            insert_query,
            {
                "id": event_id,
                "occurred_at": now,
                "tenant_id": tenant_id,
                "actor_id": "test-actor@cloudlens.internal",
            },
        )
        await session.commit()

    # 2. Attempt direct SQL UPDATE on audit_event
    async with get_tenant_session(tenant_id) as session:
        update_query = text("""
            UPDATE audit_event
            SET action = 'TAMPERED_ACTION'
            WHERE tenant_id = :tenant_id AND id = :id;
        """)
        with pytest.raises(DBAPIError) as exc_info:
            await session.execute(update_query, {"tenant_id": tenant_id, "id": event_id})
            await session.commit()

        assert "PERMISSION_DENIED" in str(exc_info.value)
        assert "append-only" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_audit_event_delete_rejected_by_database():
    """Proves that DELETE on audit_event is rejected by PostgreSQL trigger."""
    tenant_id = f"ten-{uuid.uuid4().hex[:8]}"
    event_id = f"aud-{uuid.uuid4().hex[:12]}"
    now = datetime.now(UTC)

    # 1. Insert an audit event record under tenant context
    async with get_tenant_session(tenant_id) as session:
        insert_query = text("""
            INSERT INTO audit_event (
                id, occurred_at, tenant_id, actor_id, action, entity_type, entity_id, correlation_id,
                event_type, actor_roles, details, previous_event_hash, event_hash, ip_address, user_agent
            )
            VALUES (
                :id, :occurred_at, :tenant_id, :actor_id, 'CONFIG_SET', 'system', 'sys-001', 'corr-1',
                'SYSTEM_CONFIGURATION_CHANGED', '[]'::jsonb, '{}'::jsonb, NULL, 'hash-genesis', '127.0.0.1', 'pytest'
            );
        """)
        await session.execute(
            insert_query,
            {
                "id": event_id,
                "occurred_at": now,
                "tenant_id": tenant_id,
                "actor_id": "test-actor@cloudlens.internal",
            },
        )
        await session.commit()

    # 2. Attempt direct SQL DELETE on audit_event
    async with get_tenant_session(tenant_id) as session:
        delete_query = text("""
            DELETE FROM audit_event
            WHERE tenant_id = :tenant_id AND id = :id;
        """)
        with pytest.raises(DBAPIError) as exc_info:
            await session.execute(delete_query, {"tenant_id": tenant_id, "id": event_id})
            await session.commit()

        assert "PERMISSION_DENIED" in str(exc_info.value)
        assert "append-only" in str(exc_info.value).lower()
