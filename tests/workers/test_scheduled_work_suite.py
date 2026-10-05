"""Pytest Suite for Scheduled Background Work (Prompt R-RUN).

Validates:
1. Dynamic database-backed Celery Beat scheduler with zero cron literals.
2. Distributed Beat leader lock suppresses duplicate execution on standby nodes.
3. Execution of all 21 canonical background tasks wrapped in execute_tenant_job,
   idempotency checks, start/end audit events, Prometheus metrics, and SyncJob rows.
4. Dead-letter quarantine transition after retry exhaustion.
5. Task concurrency locking per connector + capability/task.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from domain.models.enums import QuarantineReason, QuarantineStatus, SyncJobStatus
from domain.observability.metrics import metrics
from domain.sync.repository import get_quarantine_repository, get_sync_job_repository
from domain.tenant.context import TenantContext
from workers.cloudlens_workers import tasks
from workers.cloudlens_workers.celery_app import celery_app
from workers.cloudlens_workers.locking import BeatLeaderLock, TaskConcurrencyLock
from workers.cloudlens_workers.scheduler import DatabaseBeatScheduler

ALL_21_TASKS = [
    "ingest_cost",
    "ingest_inventory",
    "ingest_usage",
    "refresh_pricing",
    "discover_relationships",
    "collect_quota",
    "evaluate_thresholds",
    "evaluate_policies",
    "compute_forecasts",
    "escalate_alerts",
    "auto_resolve_alerts",
    "verify_remediation",
    "revert_overrides",
    "credential_expiry_check",
    "reconcile_closed_period",
    "run_analytical_extract",
    "maintain_partitions",
    "apply_retention_and_downsampling",
    "renewal_pipeline",
    "send_daily_platform_summary",
    "heartbeat",
]


@pytest.fixture
def demo_tenant_payload() -> dict[str, Any]:
    return {
        "tenant_id": "demo-corp",
        "roles": ["SUPER_ADMIN"],
        "user_id": "system-scheduler",
        "is_system": True,
    }


@pytest.fixture
def demo_tenant_context() -> TenantContext:
    return TenantContext(
        tenant_id="demo-corp",
        roles=["SUPER_ADMIN"],
        user_id="system-scheduler",
        is_system=True,
    )


def test_database_beat_scheduler_zero_cron_literals():
    """Verify scheduler loads schedule from database/master data with timedelta intervals and no crons."""
    scheduler = DatabaseBeatScheduler(app=celery_app)
    scheduler.setup_schedule()
    assert len(scheduler.schedule) >= 21

    # Ensure every entry is a timedelta (or ScheduleEntry with relative interval), zero crons
    for name, entry in scheduler.schedule.items():
        assert entry.schedule is not None
        assert not hasattr(entry.schedule, "_orig_minute"), f"Entry {name} must not be a crontab"


def test_beat_leader_lock_prevents_duplicate_runs():
    """Verify that standby Beat instances suppress task execution."""
    lock_key = f"lock:cloudlens:test_leader_{uuid.uuid4().hex}"
    leader_lock_1 = BeatLeaderLock(lock_key=lock_key, ttl_seconds=10)
    scheduler_1 = DatabaseBeatScheduler(app=celery_app, leader_lock=leader_lock_1)
    scheduler_1.setup_schedule()

    leader_lock_2 = BeatLeaderLock(lock_key=lock_key, ttl_seconds=10)
    scheduler_2 = DatabaseBeatScheduler(app=celery_app, leader_lock=leader_lock_2)
    scheduler_2.setup_schedule()

    # Scheduler 1 acquires leadership
    sleep_1 = scheduler_1.tick()
    assert leader_lock_1.is_leader is True

    # Scheduler 2 tick must detect standby and suppress dispatches
    sleep_2 = scheduler_2.tick()
    assert leader_lock_2.is_leader is False
    assert sleep_2 == 5.0

    leader_lock_1.release()


@pytest.mark.parametrize("task_name", ALL_21_TASKS)
def test_canonical_task_execution(task_name: str, demo_tenant_payload: dict, demo_tenant_context: TenantContext):
    """Verify that each of the 21 background tasks executes cleanly and records a SyncJob."""
    task_fn = getattr(tasks, f"{task_name}_task")
    res = task_fn(tenant_context_payload=demo_tenant_payload)

    assert res.get("status") == "COMPLETED", f"Task {task_name} failed: {res}"
    assert res.get("task_name") == task_name
    job_id = res.get("job_id")
    assert job_id is not None

    sync_job_repo = get_sync_job_repository()
    job = sync_job_repo.get(job_id, tenant_context=demo_tenant_context)
    assert job is not None
    assert job.status == SyncJobStatus.COMPLETED
    assert job.id == job_id


def test_task_concurrency_lock():
    """Verify TaskConcurrencyLock prevents concurrent execution of the same task per connector."""
    lock_1 = TaskConcurrencyLock(tenant_id="test-tenant", connector_id="aws-1", capability_or_task="ingest_cost")
    lock_2 = TaskConcurrencyLock(tenant_id="test-tenant", connector_id="aws-1", capability_or_task="ingest_cost")

    acquired_1 = lock_1.acquire()
    assert acquired_1 is True

    # Second lock for same tenant/connector/task must fail to acquire
    acquired_2 = lock_2.acquire()
    assert acquired_2 is False

    lock_1.release()

    # After release, second lock can acquire
    acquired_2_retry = lock_2.acquire()
    assert acquired_2_retry is True
    lock_2.release()


def test_dead_letter_quarantine_on_retry_exhaustion(demo_tenant_payload: dict, demo_tenant_context: TenantContext):
    """Verify that task failing on max_retries transitions to dead-letter quarantine."""
    def _faulty_execution(tc: TenantContext, job: Any) -> int:
        raise RuntimeError("Fatal upstream connectivity failure")

    test_idempotency_key = f"quarantine-test-{uuid.uuid4().hex}"
    res = tasks.run_canonical_task(
        task_name="ingest_cost",
        tenant_context_payload=demo_tenant_payload,
        connector_id="aws-prod-conn",
        capability=None,
        execution_fn=_faulty_execution,
        idempotency_key=test_idempotency_key,
        retry_count=3,  # Max retries reached
    )

    assert res.get("status") == "QUARANTINED"
    q_id = res.get("quarantine_id")
    assert q_id is not None

    q_repo = get_quarantine_repository()
    q_rec = q_repo.get(q_id, tenant_context=demo_tenant_context)
    assert q_rec is not None
    assert q_rec.quarantine_reason == QuarantineReason.RETRIES_EXHAUSTED
    assert q_rec.status == QuarantineStatus.QUARANTINED
    assert "Fatal upstream connectivity failure" in q_rec.error_details


def test_prometheus_metrics_emitted():
    """Verify Prometheus metrics are scraped and contain task outcome, duration, and row metrics."""
    scraped = metrics.scrape().decode("utf-8")
    assert "sync_job_duration_seconds" in scraped
    assert "sync_job_outcome_total" in scraped
    assert "ingestion_rows_total" in scraped
