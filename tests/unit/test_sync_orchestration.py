"""Unit Tests for Synchronization Orchestration, Schedules, and Reliability (Prompt 15 Items 97-99).

Enforces:
- Prompt 15 Item 97: All seven sync types:
  1. initial_discovery
  2. full_sync
  3. incremental_sync
  4. scheduled_sync
  5. manual_sync
  6. on_demand_single_entity_refresh
  7. backfill
- Prompt 15 Item 98: Per-connector, per-capability schedules and cadence warnings.
- Prompt 15 Item 99: Reliability guarantees:
  - Idempotency keyed on (connector_id, capability, period, dataset_version).
  - Partial failure recording per scope (one failing scope never fails the entire sync job).
  - Data validation and dead-letter quarantine for monetary sanity / schema errors.
  - Sync lag computation and freshness monitoring.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from connectors.simulator.connector import ProviderSimulatorConnector
from connectors.simulator.models import SimulatorProfile
from connectors.sync.orchestrator import SyncOrchestrator
from connectors.sync.scheduler import SyncScheduler
from connectors.sync.validator import IngestionDataValidator
from domain.models.enums import (
    ConnectorCapability,
    QuarantineReason,
    QuarantineStatus,
    SyncJobStatus,
    SyncType,
)
from domain.sync.repository import (
    ConnectorScheduleRepository,
    QuarantineRepository,
    SyncJobRepository,
)
from domain.tenant.context import TenantContext


@pytest.fixture
def tenant_context() -> TenantContext:
    return TenantContext(
        tenant_id="tenant-sync-test",
        user_id="finops-admin-user",
        roles=["FINOPS_ADMIN"],
        correlation_id="corr-sync-test-001",
    )


@pytest.fixture
def sync_job_repo() -> SyncJobRepository:
    return SyncJobRepository()


@pytest.fixture
def quarantine_repo() -> QuarantineRepository:
    return QuarantineRepository()


@pytest.fixture
def schedule_repo() -> ConnectorScheduleRepository:
    return ConnectorScheduleRepository()


@pytest.fixture
def sim_connector() -> ProviderSimulatorConnector:
    return ProviderSimulatorConnector(
        connector_id="conn-sim-aws-01",
        tenant_id="tenant-sync-test",
        profile=SimulatorProfile.AWS,
    )


# ==============================================================================
# 1. Seven Sync Types (Item 97)
# ==============================================================================


@pytest.mark.asyncio
async def test_orchestrator_initial_discovery_sync(
    sim_connector: ProviderSimulatorConnector, tenant_context: TenantContext
):
    """Item 97: Initial discovery bootstraps hierarchy, services, and inventory."""
    orchestrator = SyncOrchestrator()
    job = await orchestrator.execute_sync(
        connector=sim_connector,
        sync_type=SyncType.INITIAL_DISCOVERY,
        tenant_context=tenant_context,
        target_scopes=["111122223333"],
    )

    assert job.status == SyncJobStatus.COMPLETED
    assert job.sync_type == SyncType.INITIAL_DISCOVERY
    assert job.rows_ingested > 0
    assert len(job.scopes_completed) == 1
    assert len(job.scopes_failed) == 0


@pytest.mark.asyncio
async def test_orchestrator_all_seven_sync_types(
    sim_connector: ProviderSimulatorConnector, tenant_context: TenantContext
):
    """Item 97: Verifies all 7 sync types run successfully through the orchestrator."""
    orchestrator = SyncOrchestrator()
    sync_types = [
        SyncType.INITIAL_DISCOVERY,
        SyncType.FULL_SYNC,
        SyncType.INCREMENTAL_SYNC,
        SyncType.SCHEDULED_SYNC,
        SyncType.MANUAL_SYNC,
        SyncType.ON_DEMAND_SINGLE_ENTITY_REFRESH,
        SyncType.BACKFILL,
    ]

    for st in sync_types:
        job = await orchestrator.execute_sync(
            connector=sim_connector,
            sync_type=st,
            tenant_context=tenant_context,
            target_scopes=["111122223333"],
            allow_idempotent_skip=False,
        )
        assert job.status in (SyncJobStatus.COMPLETED, SyncJobStatus.PARTIAL_SUCCESS)
        assert job.sync_type == st
        assert job.rows_ingested >= 0
        assert job.completed_at is not None


# ==============================================================================
# 2. Per-Connector, Per-Capability Schedules & Cadence Warnings (Item 98)
# ==============================================================================


def test_scheduler_default_intervals_match_tenant_settings(
    tenant_context: TenantContext, schedule_repo: ConnectorScheduleRepository
):
    """Item 98: Verifies recommended default intervals (inventory 4-6h, cost 4-8h, usage 1h, pricing weekly)."""
    scheduler = SyncScheduler(schedule_repo=schedule_repo)
    schedules = scheduler.get_default_schedules("conn-test-01", tenant_context)
    sched_map = {s.capability: s for s in schedules}

    # Inventory: 4 hours = 240 mins
    assert sched_map[ConnectorCapability.DISCOVER_RESOURCES].interval_minutes == 240  # 4 * 60
    # Cost: 6 hours = 360 mins, lookback = 3 days
    assert sched_map[ConnectorCapability.COLLECT_COST_BULK].interval_minutes == 360  # 6 * 60
    assert sched_map[ConnectorCapability.COLLECT_COST_BULK].lookback_days == 3
    # Usage: 1 hour = 60 mins
    assert sched_map[ConnectorCapability.COLLECT_USAGE].interval_minutes == 60  # 1 * 60
    # Pricing: 168 hours = 10080 mins
    assert (
        sched_map[ConnectorCapability.COLLECT_PRICING_PUBLIC].interval_minutes == 10080
    )  # 168 * 60
    # Relationships: 24 hours = 1440 mins
    assert sched_map[ConnectorCapability.DISCOVER_RELATIONSHIPS].interval_minutes == 1440  # 24 * 60
    # Budgets: 24 hours = 1440 mins
    assert sched_map[ConnectorCapability.COLLECT_BUDGETS].interval_minutes == 1440  # 24 * 60


def test_scheduler_cadence_warning_cost_under_four_hours(
    tenant_context: TenantContext, schedule_repo: ConnectorScheduleRepository
):
    """Item 98: Warns (does not block) when interval is unlikely to yield new data."""
    scheduler = SyncScheduler(schedule_repo=schedule_repo)

    # 1. Cost set to 60 minutes (less than provider export update frequency of 4 hours)
    warning = scheduler.check_interval_cadence(
        capability=ConnectorCapability.COLLECT_COST_BULK,
        interval_minutes=60,
        tenant_context=tenant_context,
    )
    assert warning is not None
    assert "shorter than recommended cadence" in warning.warning_message
    assert warning.recommended_min_hours == 4.0

    # 2. Update does not block: schedule is saved successfully
    sched, returned_warn = scheduler.update_schedule(
        connector_id="conn-warn-test",
        capability=ConnectorCapability.COLLECT_COST_BULK,
        interval_minutes=60,
        lookback_days=3,
        is_enabled=True,
        tenant_context=tenant_context,
    )
    assert sched.interval_minutes == 60
    assert returned_warn is not None


def test_scheduler_cadence_warning_pricing_under_daily(
    tenant_context: TenantContext, schedule_repo: ConnectorScheduleRepository
):
    """Item 98: Pricing interval under 24 hours produces cadence warning."""
    scheduler = SyncScheduler(schedule_repo=schedule_repo)
    warning = scheduler.check_interval_cadence(
        capability=ConnectorCapability.COLLECT_PRICING_PUBLIC,
        interval_minutes=120,  # 2 hours
        tenant_context=tenant_context,
    )
    assert warning is not None
    assert "catalogs" in warning.warning_message.lower()


# ==============================================================================
# 3. Reliability: Idempotency (Item 99)
# ==============================================================================


@pytest.mark.asyncio
async def test_idempotency_prevents_duplicate_runs(
    sim_connector: ProviderSimulatorConnector, tenant_context: TenantContext
):
    """Item 99: Idempotency keyed on (connector_id, capability, period, dataset_version)."""
    orchestrator = SyncOrchestrator()
    period_start = datetime(2026, 9, 1, 0, 0, tzinfo=UTC)
    period_end = datetime(2026, 9, 2, 0, 0, tzinfo=UTC)

    # First run: executes normally
    job1 = await orchestrator.execute_sync(
        connector=sim_connector,
        sync_type=SyncType.SCHEDULED_SYNC,
        tenant_context=tenant_context,
        capability=ConnectorCapability.DISCOVER_RESOURCES,
        target_scopes=["scope-alpha"],
        period_start=period_start,
        period_end=period_end,
        dataset_version="v2.1",
        allow_idempotent_skip=True,
    )
    assert job1.status == SyncJobStatus.COMPLETED

    # Second run with identical parameters: skipped and returns cached job
    job2 = await orchestrator.execute_sync(
        connector=sim_connector,
        sync_type=SyncType.SCHEDULED_SYNC,
        tenant_context=tenant_context,
        capability=ConnectorCapability.DISCOVER_RESOURCES,
        target_scopes=["scope-alpha"],
        period_start=period_start,
        period_end=period_end,
        dataset_version="v2.1",
        allow_idempotent_skip=True,
    )
    assert job2.id == job1.id
    assert job2.idempotency_key == job1.idempotency_key


# ==============================================================================
# 4. Reliability: Partial-Failure Isolation per Scope (Item 99)
# ==============================================================================


class PartialFailureMockConnector(ProviderSimulatorConnector):
    """Simulates a connector where one scope fails while others succeed."""

    async def discover_resources(self, scope_id: str = "root", pagination: Any = None) -> Any:
        if scope_id == "failing-scope-403":
            raise PermissionError("AccessDenied: Account 403 denied assume role permission")
        return await super().discover_resources(scope_id=scope_id, pagination=pagination)


@pytest.mark.asyncio
async def test_partial_failure_isolation_one_failing_scope_never_fails_job(
    tenant_context: TenantContext,
):
    """Item 99: One failing scope records partial failure and never halts or fails entire sync."""
    connector = PartialFailureMockConnector(
        connector_id="conn-partial-test",
        tenant_id=tenant_context.tenant_id,
        profile=SimulatorProfile.AWS,
    )
    orchestrator = SyncOrchestrator()

    scopes = ["healthy-scope-1", "failing-scope-403", "healthy-scope-2"]
    job = await orchestrator.execute_sync(
        connector=connector,
        sync_type=SyncType.FULL_SYNC,
        tenant_context=tenant_context,
        capability=ConnectorCapability.DISCOVER_RESOURCES,
        target_scopes=scopes,
        allow_idempotent_skip=False,
    )

    # Status must be PARTIAL_SUCCESS, not FAILED
    assert job.status == SyncJobStatus.PARTIAL_SUCCESS
    assert "healthy-scope-1" in job.scopes_completed
    assert "healthy-scope-2" in job.scopes_completed
    assert "failing-scope-403" in job.scopes_failed
    assert len(job.scope_results) == 3

    # Check that failed scope has recorded error
    failed_result = next(r for r in job.scope_results if r["scope_id"] == "failing-scope-403")
    assert failed_result["status"] == "FAILED"
    assert "AccessDenied" in failed_result["error_message"]
    assert job.rows_ingested > 0


# ==============================================================================
# 5. Reliability: Data Validation & Dead-Letter Quarantine (Item 99)
# ==============================================================================


def test_validator_quarantines_negative_cost_not_credit(tenant_context: TenantContext):
    """Item 99: Negative billed cost on regular Usage charge is quarantined for monetary sanity."""
    validator = IngestionDataValidator()
    bad_cost_record = {
        "record_id": "rec-neg-001",
        "scope_id": "acc-111",
        "charge_category": "Usage",
        "billed_cost": -150.0,
        "currency": "USD",
    }
    is_valid, reason, msg = validator.validate_single_record(
        bad_cost_record, ConnectorCapability.COLLECT_COST_BULK, tenant_context
    )
    assert not is_valid
    assert reason == QuarantineReason.MONETARY_SANITY_FAILURE
    assert msg is not None
    assert "strictly forbidden" in msg


def test_validator_allows_negative_cost_for_credit(tenant_context: TenantContext):
    """Item 99: Negative billed cost is accepted if charge category is Credit."""
    validator = IngestionDataValidator()
    valid_credit = {
        "record_id": "rec-credit-001",
        "scope_id": "acc-111",
        "charge_category": "Credit",
        "billed_cost": -50.0,
        "currency": "USD",
    }
    is_valid, reason, msg = validator.validate_single_record(
        valid_credit, ConnectorCapability.COLLECT_COST_BULK, tenant_context
    )
    assert is_valid
    assert reason is None


def test_validator_quarantines_astronomical_cost(tenant_context: TenantContext):
    """Item 99: Monetary sanity check flags single line item exceeding threshold."""
    validator = IngestionDataValidator()
    astronomical_record = {
        "record_id": "rec-huge-001",
        "scope_id": "acc-111",
        "charge_category": "Usage",
        "billed_cost": 5000000.0,  # 5 million > 1 million limit
        "currency": "USD",
    }
    is_valid, reason, msg = validator.validate_single_record(
        astronomical_record, ConnectorCapability.COLLECT_COST_BULK, tenant_context
    )
    assert not is_valid
    assert reason == QuarantineReason.MONETARY_SANITY_FAILURE
    assert msg is not None
    assert "exceeds maximum allowed" in msg


def test_validator_quarantines_missing_required_fields(tenant_context: TenantContext):
    """Item 99: Missing required fields routes payload to quarantine."""
    validator = IngestionDataValidator()
    broken_record = {
        "record_id": "rec-broken-001",
        # missing scope_id, billed_cost, currency
    }
    is_valid, reason, msg = validator.validate_single_record(
        broken_record, ConnectorCapability.COLLECT_COST_BULK, tenant_context
    )
    assert not is_valid
    assert reason == QuarantineReason.MISSING_REQUIRED_FIELDS


def test_batch_validation_routes_defective_to_quarantine_repo(
    tenant_context: TenantContext, quarantine_repo: QuarantineRepository
):
    """Item 99: Batch validation preserves valid records and saves defective records to quarantine repo."""
    validator = IngestionDataValidator(quarantine_repo=quarantine_repo)
    records = [
        {
            "record_id": "ok-1",
            "scope_id": "acc-1",
            "charge_category": "Usage",
            "billed_cost": 10.0,
            "currency": "USD",
        },
        {
            "record_id": "bad-2",
            "scope_id": "acc-1",
            "charge_category": "Usage",
            "billed_cost": -99.0,
            "currency": "USD",
        },
        {
            "record_id": "ok-3",
            "scope_id": "acc-1",
            "charge_category": "Usage",
            "billed_cost": 25.0,
            "currency": "USD",
        },
    ]

    valid, quarantined = validator.validate_and_quarantine_batch(
        records=records,
        capability=ConnectorCapability.COLLECT_COST_BULK,
        connector_id="conn-val-test",
        job_id="job-val-001",
        tenant_context=tenant_context,
    )

    assert len(valid) == 2
    assert len(quarantined) == 1
    assert quarantined[0].quarantine_reason == QuarantineReason.MONETARY_SANITY_FAILURE
    assert quarantined[0].status == QuarantineStatus.QUARANTINED

    # Verify persisted in quarantine repository
    saved = quarantine_repo.get(quarantined[0].id, tenant_context=tenant_context)
    assert saved is not None
    assert saved.id == quarantined[0].id


# ==============================================================================
# 6. Reliability: Sync Lag Computation & Freshness (Item 99)
# ==============================================================================


@pytest.mark.asyncio
async def test_sync_lag_computation_and_staleness(tenant_context: TenantContext):
    """Item 99: Lag computation (now - last_successful_sync) and staleness warning."""
    connector = ProviderSimulatorConnector(
        connector_id="conn-lag-test-99",
        tenant_id=tenant_context.tenant_id,
        profile=SimulatorProfile.AWS,
    )
    orchestrator = SyncOrchestrator()

    # Before any sync: lag is reported stale with warning
    lag_before = orchestrator.get_sync_lag(
        connector_id=connector.connector_id,
        capability=ConnectorCapability.DISCOVER_RESOURCES,
        tenant_context=tenant_context,
    )
    assert lag_before.is_stale is True
    assert lag_before.last_successful_sync is None

    # Run a sync
    await orchestrator.execute_sync(
        connector=connector,
        sync_type=SyncType.SCHEDULED_SYNC,
        tenant_context=tenant_context,
        capability=ConnectorCapability.DISCOVER_RESOURCES,
        allow_idempotent_skip=False,
    )

    # After sync: lag is fresh (<10 seconds) and not stale
    lag_after = orchestrator.get_sync_lag(
        connector_id=connector.connector_id,
        capability=ConnectorCapability.DISCOVER_RESOURCES,
        tenant_context=tenant_context,
    )
    assert lag_after.is_stale is False
    assert lag_after.last_successful_sync is not None
    assert lag_after.lag_seconds < 10.0
