"""Real-Database Integration Test: Sync History Survives Restart (Prompt P05).

Enforces:
- Pattern P1/P4: Authoritative PostgreSQL persistence across process restarts for all Sync & Connector entities:
  1. Sync Jobs & execution history (SqlSyncJobRepository)
  2. Pagination Checkpoints (SqlCheckpointStore)
  3. Quarantine Records (SqlQuarantineRepository)
  4. First-Sync Progress Reports (SqlFirstSyncProgressRepository)
  5. Connector Schedules (SqlConnectorScheduleRepository)
  6. Raw Landing Metadata (RawLandingService / SqlRawLandingStore)
  7. Notification Dispatch Logs (SqlNotificationLogRepository)
  8. Connector Registrations & Capabilities (SqlConnectorRepository)

Each proof strictly writes in Instance A, discards Instance A, creates fresh Instance B,
and retrieves from PostgreSQL to verify zero in-memory dependencies.
"""

import hashlib
import uuid
from datetime import UTC, datetime

import pytest

from connectors.contract.checkpoint_store import SqlCheckpointStore
from connectors.contract.models import RawLandingRecord
from connectors.contract.raw_landing import RawLandingService
from domain.connectors.models import ConnectorEntity
from domain.connectors.repository import SqlConnectorRepository
from domain.models.enums import (
    ConnectorCapability,
    ConnectorLifecycleState,
    NotificationChannel,
    NotificationStatus,
    ProviderType,
    QuarantineReason,
    QuarantineStatus,
    SyncJobStatus,
    SyncStageStatus,
    SyncType,
)
from domain.notification.models import NotificationLogRecord
from domain.notification.repository import SqlNotificationLogRepository
from domain.sync.first_sync_models import FirstSyncProgressReport, FirstSyncStage
from domain.sync.models import ConnectorSchedule, QuarantineRecord, SyncJob
from domain.sync.repository import (
    SqlConnectorScheduleRepository,
    SqlFirstSyncProgressRepository,
    SqlQuarantineRepository,
    SqlSyncJobRepository,
)
from domain.tenant.context import TenantContext
from domain.tenant.models import Tenant
from domain.tenant.repository import SqlTenantRepository

pytestmark = [pytest.mark.realdb]


async def _create_test_tenant() -> tuple[TenantContext, str, str]:
    """Sets up an authoritative tenant in PostgreSQL for test isolation."""
    tenant_id = f"ten-{uuid.uuid4().hex[:12]}"
    user_id = f"usr-{uuid.uuid4().hex[:12]}"
    now = datetime.now(UTC)

    tenant_repo = SqlTenantRepository()
    tenant = Tenant(
        id=tenant_id,
        name=f"Sync History Tenant {tenant_id}",
        reporting_currency="USD",
        created_at=now,
        updated_at=now,
    )
    await tenant_repo.save(tenant)
    ctx = TenantContext(tenant_id=tenant_id, user_id=user_id)
    return ctx, tenant_id, user_id


# -----------------------------------------------------------------------------
# 1. Sync Job History Survives Restart
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_sync_job_history_survives_process_restart():
    ctx, tenant_id, _ = await _create_test_tenant()
    now = datetime.now(UTC)
    job_id = f"job-{uuid.uuid4().hex[:12]}"
    connector_id = f"conn-{uuid.uuid4().hex[:12]}"

    # Process A writes
    repo_a = SqlSyncJobRepository()
    job = SyncJob(
        id=job_id,
        tenant_id=tenant_id,
        connector_id=connector_id,
        connector_type=ProviderType.AWS,
        scope_id="billing-scope-1",
        sync_type=SyncType.FULL_SYNC,
        capability=ConnectorCapability.COLLECT_COST_BULK,
        dataset_version="v2026.1",
        idempotency_key=f"idem-{job_id}",
        period_start=datetime(2026, 9, 1, 0, 0, 0, tzinfo=UTC),
        period_end=datetime(2026, 9, 30, 23, 59, 59, tzinfo=UTC),
        scopes_requested=["us-east-1", "us-west-2"],
        scopes_completed=[],
        scopes_failed=[],
        status=SyncJobStatus.RUNNING,
        started_at=now,
        completed_at=None,
        rows_ingested=0,
        error_message=None,
        created_at=now,
    )
    await repo_a.save_async(job, tenant_context=ctx)
    del repo_a

    # Process B reads and updates
    repo_b = SqlSyncJobRepository()
    loaded_b = await repo_b.get_async(job_id, tenant_context=ctx)
    assert loaded_b is not None
    assert loaded_b.id == job_id
    assert loaded_b.tenant_id == tenant_id
    assert loaded_b.connector_id == connector_id
    assert loaded_b.capability == ConnectorCapability.COLLECT_COST_BULK
    assert loaded_b.status == SyncJobStatus.RUNNING
    assert loaded_b.scopes_requested == ["us-east-1", "us-west-2"]

    # Process B finishes the job
    completed_time = datetime.now(UTC)
    loaded_b.status = SyncJobStatus.COMPLETED
    loaded_b.scopes_completed = ["us-east-1", "us-west-2"]
    loaded_b.rows_ingested = 45200
    loaded_b.completed_at = completed_time
    await repo_b.save_async(loaded_b, tenant_context=ctx)
    del repo_b

    # Process C confirms completed state persisted
    repo_c = SqlSyncJobRepository()
    loaded_c = await repo_c.get_async(job_id, tenant_context=ctx)
    assert loaded_c is not None
    assert loaded_c.status == SyncJobStatus.COMPLETED
    assert loaded_c.scopes_completed == ["us-east-1", "us-west-2"]
    assert loaded_c.rows_ingested == 45200
    assert loaded_c.completed_at is not None


# -----------------------------------------------------------------------------
# 2. Checkpoints Survive Restart
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_checkpoint_survives_process_restart():
    ctx, tenant_id, _ = await _create_test_tenant()
    job_id = f"job-{uuid.uuid4().hex[:12]}"
    connector_id = f"conn-{uuid.uuid4().hex[:12]}"

    # Process A writes checkpoint
    store_a = SqlCheckpointStore()
    saved_chk = await store_a.save_checkpoint_async(
        tenant_context=ctx,
        job_id=job_id,
        connector_id=connector_id,
        capability=ConnectorCapability.COLLECT_COST_BULK,
        continuation_token="nextToken_page_42",
        page_number=42,
        records_ingested=42000,
        last_record_id="rec-abc-999",
        status="IN_PROGRESS",
    )
    assert saved_chk is not None
    del store_a

    # Process B reads checkpoint
    store_b = SqlCheckpointStore()
    loaded_chk = await store_b.get_checkpoint_async(
        tenant_id=tenant_id,
        job_id=job_id,
        capability=ConnectorCapability.COLLECT_COST_BULK,
    )
    assert loaded_chk is not None
    assert loaded_chk.job_id == job_id
    assert loaded_chk.connector_id == connector_id
    assert loaded_chk.page_number == 42
    assert loaded_chk.continuation_token == "nextToken_page_42"
    assert loaded_chk.records_ingested == 42000
    assert loaded_chk.last_record_id == "rec-abc-999"


# -----------------------------------------------------------------------------
# 3. Quarantine Records Survive Restart
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_quarantine_record_survives_process_restart():
    ctx, tenant_id, _ = await _create_test_tenant()
    now = datetime.now(UTC)
    quarantine_id = f"q-{uuid.uuid4().hex[:12]}"
    connector_id = f"conn-{uuid.uuid4().hex[:12]}"
    job_id = f"job-{uuid.uuid4().hex[:12]}"

    # Process A writes quarantine record
    repo_a = SqlQuarantineRepository()
    record = QuarantineRecord(
        id=quarantine_id,
        tenant_id=tenant_id,
        connector_id=connector_id,
        job_id=job_id,
        capability=ConnectorCapability.COLLECT_COST_BULK,
        quarantine_reason=QuarantineReason.SCHEMA_VIOLATION,
        error_details="Field 'line_item_amount' is null; strict numeric constraint violated.",
        payload_summary={"line_number": 8192, "provider_cost_code": "EC2-Compute"},
        raw_payload_path="tenants/ten-1/landings/raw_corrupted_chunk.json",
        status=QuarantineStatus.QUARANTINED,
        quarantined_at=now,
        resolved_at=None,
        resolved_by=None,
    )
    await repo_a.save_async(record, tenant_context=ctx)
    del repo_a

    # Process B reads quarantine record
    repo_b = SqlQuarantineRepository()
    loaded_b = await repo_b.get_async(quarantine_id, tenant_context=ctx)
    assert loaded_b is not None
    assert loaded_b.id == quarantine_id
    assert loaded_b.connector_id == connector_id
    assert loaded_b.quarantine_reason == QuarantineReason.SCHEMA_VIOLATION
    assert "strict numeric constraint violated" in loaded_b.error_details
    assert loaded_b.payload_summary["line_number"] == 8192
    assert loaded_b.status == QuarantineStatus.QUARANTINED


# -----------------------------------------------------------------------------
# 4. First-Sync Progress Survives Restart
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_first_sync_progress_survives_process_restart():
    ctx, tenant_id, _ = await _create_test_tenant()
    now = datetime.now(UTC)
    report_id = f"fs-{uuid.uuid4().hex[:12]}"
    session_id = f"wiz-{uuid.uuid4().hex[:12]}"
    connector_id = f"conn-{uuid.uuid4().hex[:12]}"

    stages = [
        FirstSyncStage(
            stage_id="stage-1",
            name="Discover services",
            capability=ConnectorCapability.DISCOVER_SERVICES,
            status=SyncStageStatus.COMPLETE,
            items_count=24,
            expected_duration_seconds=30,
            elapsed_time_seconds=12,
            latency_explanation="Synchronous provider metadata query",
        ),
        FirstSyncStage(
            stage_id="stage-2",
            name="Retrieve cost data",
            capability=ConnectorCapability.COLLECT_COST_BULK,
            status=SyncStageStatus.RUNNING,
            items_count=1200,
            expected_duration_seconds=3600,
            elapsed_time_seconds=180,
            latency_explanation="Billing export pipeline latency",
        ),
    ]

    # Process A writes
    repo_a = SqlFirstSyncProgressRepository()
    report = FirstSyncProgressReport(
        id=report_id,
        tenant_id=tenant_id,
        session_id=session_id,
        connector_id=connector_id,
        initial_sync_job_id="job-init-123",
        overall_status="RUNNING",
        stages=stages,
        total_stages=5,
        completed_stages=1,
        estimated_time_to_first_cost_seconds=7200,
        landing_destination=f"/onboarding/first-sync-progress?session={session_id}",
        created_at=now,
        updated_at=now,
    )
    await repo_a.save_async(report, tenant_context=ctx)
    del repo_a

    # Process B reads
    repo_b = SqlFirstSyncProgressRepository()
    loaded_b = await repo_b.get_async(report_id, tenant_context=ctx)
    assert loaded_b is not None
    assert loaded_b.id == report_id
    assert loaded_b.session_id == session_id
    assert loaded_b.overall_status == "RUNNING"
    assert len(loaded_b.stages) == 2
    assert loaded_b.stages[0].status == SyncStageStatus.COMPLETE
    assert loaded_b.stages[0].items_count == 24
    assert loaded_b.stages[1].status == SyncStageStatus.RUNNING


# -----------------------------------------------------------------------------
# 5. Connector Schedules Survive Restart
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_connector_schedule_survives_process_restart():
    ctx, tenant_id, _ = await _create_test_tenant()
    now = datetime.now(UTC)
    schedule_id = f"sched-{uuid.uuid4().hex[:12]}"
    connector_id = f"conn-{uuid.uuid4().hex[:12]}"

    # Process A writes
    repo_a = SqlConnectorScheduleRepository()
    sched = ConnectorSchedule(
        id=schedule_id,
        tenant_id=tenant_id,
        connector_id=connector_id,
        capability=ConnectorCapability.COLLECT_COST_BULK,
        interval_minutes=360,
        cron_expression="0 */6 * * *",
        lookback_days=3,
        is_enabled=True,
        last_run_at=None,
        last_successful_run_at=None,
        next_run_at=now,
        created_at=now,
        updated_at=now,
    )
    await repo_a.save_async(sched, tenant_context=ctx)
    del repo_a

    # Process B reads
    repo_b = SqlConnectorScheduleRepository()
    loaded_b = await repo_b.get_async(schedule_id, tenant_context=ctx)
    assert loaded_b is not None
    assert loaded_b.id == schedule_id
    assert loaded_b.connector_id == connector_id
    assert loaded_b.cron_expression == "0 */6 * * *"
    assert loaded_b.interval_minutes == 360
    assert loaded_b.is_enabled is True


# -----------------------------------------------------------------------------
# 6. Raw Landing Metadata Survives Restart
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_raw_landing_metadata_survives_process_restart():
    ctx, tenant_id, _ = await _create_test_tenant()
    now = datetime.now(UTC)
    landing_id = f"land-{uuid.uuid4().hex[:12]}"
    connector_id = f"conn-{uuid.uuid4().hex[:12]}"
    payload_bytes = b'{"billing_data": [{"cost": 10.5, "currency": "USD"}]}'
    sha256 = hashlib.sha256(payload_bytes).hexdigest()

    # Process A writes
    landing_service_a = RawLandingService()
    record = RawLandingRecord(
        landing_id=landing_id,
        tenant_id=tenant_id,
        connector_id=connector_id,
        run_id="run-test-001",
        capability=ConnectorCapability.COLLECT_COST_BULK,
        schema_version="1.0.0",
        storage_path=f"tenants/{tenant_id}/landings/{landing_id}.json",
        sha256_checksum=sha256,
        byte_size=len(payload_bytes),
        record_count=1,
        landed_at=now,
    )
    await landing_service_a._insert_landing_db(record)
    del landing_service_a

    # Process B reads directly from database
    landing_service_b = RawLandingService()
    reloaded = await landing_service_b.get_landing_async(landing_id)
    assert reloaded is not None
    assert reloaded.landing_id == landing_id
    assert reloaded.tenant_id == tenant_id
    assert reloaded.sha256_checksum == sha256
    assert reloaded.byte_size == len(payload_bytes)
    assert reloaded.record_count == 1


# -----------------------------------------------------------------------------
# 7. Notification Logs Survive Restart
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_notification_log_survives_process_restart():
    ctx, tenant_id, _ = await _create_test_tenant()
    now = datetime.now(UTC)
    log_id = f"notif-{uuid.uuid4().hex[:12]}"

    # Process A writes
    repo_a = SqlNotificationLogRepository()
    record = NotificationLogRecord(
        id=log_id,
        tenant_id=tenant_id,
        channel=NotificationChannel.WEBHOOK,
        recipient="https://hooks.slack.com/services/T00/B00/X00",
        status=NotificationStatus.SENT,
        message="AWS Sync successfully finalized 45200 rows.",
        error_message=None,
        is_test=False,
        metadata={"details": "All chunks reconciled"},
        created_at=now,
    )
    await repo_a.save_async(record, tenant_context=ctx)
    del repo_a

    # Process B reads
    repo_b = SqlNotificationLogRepository()
    loaded_b = await repo_b.get_async(log_id, tenant_context=ctx)
    assert loaded_b is not None
    assert loaded_b.id == log_id
    assert loaded_b.channel == NotificationChannel.WEBHOOK
    assert loaded_b.status == NotificationStatus.SENT
    assert loaded_b.message == "AWS Sync successfully finalized 45200 rows."


# -----------------------------------------------------------------------------
# 8. Connector Registrations Survive Restart
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_connector_registration_survives_process_restart():
    ctx, tenant_id, _ = await _create_test_tenant()
    now = datetime.now(UTC)
    connector_id = f"conn-{uuid.uuid4().hex[:12]}"

    # Process A writes
    repo_a = SqlConnectorRepository()
    connector = ConnectorEntity(
        id=connector_id,
        tenant_id=tenant_id,
        provider=ProviderType.AZURE,
        name="Enterprise Azure EA Ingestion",
        lifecycle_state=ConnectorLifecycleState.ACTIVE,
        declared_capabilities=[ConnectorCapability.COLLECT_COST_BULK.value],
        verified_capabilities=[ConnectorCapability.COLLECT_COST_BULK.value],
        created_at=now,
        updated_at=now,
    )
    await repo_a.save_async(connector, tenant_context=ctx)
    del repo_a

    # Process B reads
    repo_b = SqlConnectorRepository()
    loaded_b = await repo_b.get_async(connector_id, tenant_context=ctx)
    assert loaded_b is not None
    assert loaded_b.id == connector_id
    assert loaded_b.provider == ProviderType.AZURE
    assert loaded_b.name == "Enterprise Azure EA Ingestion"
    assert loaded_b.lifecycle_state == ConnectorLifecycleState.ACTIVE
    assert loaded_b.verified_capabilities == [ConnectorCapability.COLLECT_COST_BULK.value]
