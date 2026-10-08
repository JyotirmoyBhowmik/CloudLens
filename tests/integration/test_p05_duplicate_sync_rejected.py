"""Real-Database Integration Test: Duplicate Sync Rejected by DB Constraint (Prompt P05).

Enforces:
- Database unique idempotency constraint on sync_jobs:
  uq_sync_jobs_idempotency UNIQUE NULLS NOT DISTINCT (
      tenant_id, connector_id, capability, period_start, period_end, dataset_version
  )
- Prevents concurrent or duplicate ingestion runs for identical period/capability slices.
- Rejection must occur at the PostgreSQL database schema constraint level (IntegrityError).
"""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError

from domain.connectors.models import ConnectorEntity
from domain.connectors.repository import SqlConnectorRepository
from domain.models.enums import (
    ConnectorCapability,
    ConnectorLifecycleState,
    ProviderType,
    SyncJobStatus,
    SyncType,
)
from domain.sync.models import SyncJob
from domain.sync.repository import SqlSyncJobRepository
from domain.tenant.context import TenantContext
from domain.tenant.models import Tenant
from domain.tenant.repository import SqlTenantRepository

pytestmark = [pytest.mark.realdb]


@pytest.mark.asyncio
async def test_duplicate_sync_rejected_by_db_constraint():
    """Verify that duplicate sync jobs with identical idempotency dimensions are rejected by PostgreSQL."""
    tenant_id = f"ten-{uuid.uuid4().hex[:12]}"
    user_id = f"usr-{uuid.uuid4().hex[:12]}"
    connector_id = f"conn-{uuid.uuid4().hex[:12]}"
    now = datetime.now(UTC)

    # 1. Setup tenant & connector
    tenant_repo = SqlTenantRepository()
    tenant = Tenant(
        id=tenant_id,
        name=f"Idempotency Tenant {tenant_id}",
        reporting_currency="USD",
        created_at=now,
        updated_at=now,
    )
    await tenant_repo.save(tenant)
    ctx = TenantContext(tenant_id=tenant_id, user_id=user_id)

    connector_repo = SqlConnectorRepository()
    connector = ConnectorEntity(
        id=connector_id,
        tenant_id=tenant_id,
        provider=ProviderType.AWS,
        name="Production Cost Exporter",
        lifecycle_state=ConnectorLifecycleState.ACTIVE,
        declared_capabilities=[ConnectorCapability.COLLECT_COST_BULK.value],
        verified_capabilities=[ConnectorCapability.COLLECT_COST_BULK.value],
        created_at=now,
        updated_at=now,
    )
    await connector_repo.save_async(connector, tenant_context=ctx)

    sync_repo = SqlSyncJobRepository()

    period_start = datetime(2026, 10, 1, 0, 0, 0, tzinfo=UTC)
    period_end = datetime(2026, 10, 2, 0, 0, 0, tzinfo=UTC)
    capability = ConnectorCapability.COLLECT_COST_BULK
    dataset_version = "v1"

    # -------------------------------------------------------------------------
    # 2. Insert First Sync Job
    # -------------------------------------------------------------------------
    job_1_id = f"job-{uuid.uuid4().hex[:12]}"
    job_1 = SyncJob(
        id=job_1_id,
        tenant_id=tenant_id,
        connector_id=connector_id,
        connector_type=ProviderType.AWS,
        scope_id="default-scope",
        sync_type=SyncType.INCREMENTAL_SYNC,
        capability=capability,
        dataset_version=dataset_version,
        idempotency_key=f"idem-{job_1_id}",
        period_start=period_start,
        period_end=period_end,
        scopes_requested=["billing-bucket-1"],
        scopes_completed=[],
        scopes_failed=[],
        status=SyncJobStatus.RUNNING,
        started_at=now,
        completed_at=None,
        rows_ingested=0,
        error_message=None,
        created_at=now,
    )

    saved_1 = await sync_repo.save_async(job_1, tenant_context=ctx)
    assert saved_1.id == job_1_id

    # -------------------------------------------------------------------------
    # 3. Attempt Duplicate Insert With Distinct Job ID but Matching Dimensions
    # -------------------------------------------------------------------------
    job_2_id = f"job-{uuid.uuid4().hex[:12]}"
    job_2 = SyncJob(
        id=job_2_id,
        tenant_id=tenant_id,
        connector_id=connector_id,
        connector_type=ProviderType.AWS,
        scope_id="default-scope",
        sync_type=SyncType.INCREMENTAL_SYNC,
        capability=capability,
        dataset_version=dataset_version,
        idempotency_key=f"idem-{job_2_id}",
        period_start=period_start,
        period_end=period_end,
        scopes_requested=["billing-bucket-1"],
        scopes_completed=[],
        scopes_failed=[],
        status=SyncJobStatus.SCHEDULED,
        started_at=now,
        completed_at=None,
        rows_ingested=0,
        error_message=None,
        created_at=now,
    )

    # Must be rejected by PostgreSQL schema constraint uq_sync_jobs_idempotency
    with pytest.raises(IntegrityError) as exc_info:
        await sync_repo.save_async(job_2, tenant_context=ctx)

    assert "uq_sync_jobs_idempotency" in str(exc_info.value).lower() or "unique constraint" in str(exc_info.value).lower()

    # -------------------------------------------------------------------------
    # 4. Insert Job with Different Period (Should Succeed)
    # -------------------------------------------------------------------------
    job_3_id = f"job-{uuid.uuid4().hex[:12]}"
    job_3 = SyncJob(
        id=job_3_id,
        tenant_id=tenant_id,
        connector_id=connector_id,
        connector_type=ProviderType.AWS,
        scope_id="default-scope",
        sync_type=SyncType.INCREMENTAL_SYNC,
        capability=capability,
        dataset_version=dataset_version,
        idempotency_key=f"idem-{job_3_id}",
        period_start=datetime(2026, 10, 2, 0, 0, 0, tzinfo=UTC),
        period_end=datetime(2026, 10, 3, 0, 0, 0, tzinfo=UTC),
        scopes_requested=["billing-bucket-1"],
        scopes_completed=[],
        scopes_failed=[],
        status=SyncJobStatus.RUNNING,
        started_at=now,
        completed_at=None,
        rows_ingested=0,
        error_message=None,
        created_at=now,
    )
    saved_3 = await sync_repo.save_async(job_3, tenant_context=ctx)
    assert saved_3.id == job_3_id

    # -------------------------------------------------------------------------
    # 5. Insert Job with Different Capability (Should Succeed)
    # -------------------------------------------------------------------------
    job_4_id = f"job-{uuid.uuid4().hex[:12]}"
    job_4 = SyncJob(
        id=job_4_id,
        tenant_id=tenant_id,
        connector_id=connector_id,
        connector_type=ProviderType.AWS,
        scope_id="default-scope",
        sync_type=SyncType.INCREMENTAL_SYNC,
        capability=ConnectorCapability.COLLECT_COST_QUERY,
        dataset_version=dataset_version,
        idempotency_key=f"idem-{job_4_id}",
        period_start=period_start,
        period_end=period_end,
        scopes_requested=["billing-bucket-1"],
        scopes_completed=[],
        scopes_failed=[],
        status=SyncJobStatus.RUNNING,
        started_at=now,
        completed_at=None,
        rows_ingested=0,
        error_message=None,
        created_at=now,
    )
    saved_4 = await sync_repo.save_async(job_4, tenant_context=ctx)
    assert saved_4.id == job_4_id
