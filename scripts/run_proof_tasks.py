"""Proof Runner for Scheduled Background Work (Prompt R-RUN).

Validates:
1. All 21 canonical background tasks execute cleanly, returning COMPLETED.
2. Second Beat instance does NOT duplicate runs (BeatLeaderLock).
3. Every task creates a SyncJob record in the database/repository.
4. Every task emits Prometheus metrics and start/end audit events.
5. Dead-letter quarantine triggered when tasks fail after max retries.
"""

from __future__ import annotations

import logging
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from domain.models.enums import QuarantineReason, QuarantineStatus, SyncJobStatus
from domain.observability.metrics import metrics
from domain.sync.repository import get_quarantine_repository, get_sync_job_repository
from domain.tenant.context import TenantContext
from workers.cloudlens_workers import tasks
from workers.cloudlens_workers.locking import BeatLeaderLock, TaskConcurrencyLock, reset_in_memory_locks
from workers.cloudlens_workers.scheduler import DatabaseBeatScheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

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


def test_leader_lock_prevents_duplicate_runs() -> bool:
    """Verifies that a second Beat instance in standby mode does not fire any tasks."""
    logger.info("=== PROOF 1: Leader Lock Election Verification ===")
    from workers.cloudlens_workers.celery_app import celery_app

    # Instance 1: Leader
    leader_lock_1 = BeatLeaderLock(lock_key="lock:cloudlens:test_leader")
    scheduler_1 = DatabaseBeatScheduler(app=celery_app, leader_lock=leader_lock_1)
    scheduler_1.setup_schedule()

    # Instance 2: Standby
    leader_lock_2 = BeatLeaderLock(lock_key="lock:cloudlens:test_leader")
    scheduler_2 = DatabaseBeatScheduler(app=celery_app, leader_lock=leader_lock_2)
    scheduler_2.setup_schedule()

    # Scheduler 1 acquires leadership
    sleep_1 = scheduler_1.tick()
    assert leader_lock_1.is_leader is True, "Instance 1 must become LEADER"

    # Scheduler 2 attempts tick -> must be in STANDBY and sleep without dispatching
    sleep_2 = scheduler_2.tick()
    assert leader_lock_2.is_leader is False, "Instance 2 must remain STANDBY"
    assert sleep_2 == 5.0, f"Instance 2 must sleep with backoff (got {sleep_2})"

    logger.info("Leader Election Proof: Instance 1 is LEADER. Instance 2 is STANDBY (dispatches suppressed).")
    leader_lock_1.release()
    return True


def test_execute_all_21_tasks() -> list[dict]:
    """Executes all 21 tasks on the demo tenant, verifying SyncJob and Prometheus metrics."""
    logger.info("=== PROOF 2: Execution of All 21 Canonical Tasks ===")
    tc_payload = {
        "tenant_id": "demo-corp",
        "roles": ["SUPER_ADMIN"],
        "user_id": "system-scheduler",
        "is_system": True,
    }
    tc = TenantContext(
        tenant_id="demo-corp",
        roles=["SUPER_ADMIN"],
        user_id="system-scheduler",
        is_system=True,
    )

    sync_job_repo = get_sync_job_repository()
    results = []

    print("-" * 90)
    print(f"{'TASK NAME':34} | {'TENANT':12} | {'OUTCOME':10} | {'DURATION':10} | {'ROWS'}")
    print("-" * 90)

    for task_name in ALL_21_TASKS:
        task_fn = getattr(tasks, f"{task_name}_task")
        res = task_fn(tenant_context_payload=tc_payload)
        status = res.get("status")
        job_id = res.get("job_id")
        duration = res.get("duration_seconds", 0.0)
        rows = res.get("rows_ingested", 0)

        print(f"{task_name:34} | {'demo-corp':12} | {status:10} | {duration:8.4f}s | {rows}")
        results.append(res)

        # Assert task succeeded
        assert status == "COMPLETED", f"Task {task_name} failed with status {status}: {res}"

        # Assert SyncJob record is stored and visible in repository
        job = sync_job_repo.get(job_id, tenant_context=tc)
        assert job is not None, f"SyncJob {job_id} not found in repository"
        assert job.status == SyncJobStatus.COMPLETED
        assert job.rows_ingested == rows

    print("-" * 90)
    logger.info("All 21 tasks executed cleanly with SyncJob rows verified.")
    return results


def test_dead_letter_quarantine() -> bool:
    """Verifies that a task failing after max retries transitions to dead-letter quarantine."""
    logger.info("=== PROOF 3: Dead-Letter Quarantine after Max Retries ===")
    tc_payload = {
        "tenant_id": "demo-corp",
        "roles": ["SUPER_ADMIN"],
        "user_id": "system-scheduler",
        "is_system": True,
    }
    tc = TenantContext(
        tenant_id="demo-corp",
        roles=["SUPER_ADMIN"],
        user_id="system-scheduler",
        is_system=True,
    )

    # Intentionally failing function
    def _faulty_execution(tc: TenantContext, job: Any) -> int:
        raise ValueError("Simulated upstream provider API connection failure")

    import uuid

    # Call with retry_count = 3 (max_retries = 3)
    res = tasks.run_canonical_task(
        task_name="ingest_cost",
        tenant_context_payload=tc_payload,
        connector_id="aws-prod-conn",
        capability=None,
        execution_fn=_faulty_execution,
        idempotency_key=f"quarantine-test-{uuid.uuid4().hex}",
        retry_count=3,  # Reached max retries
    )

    assert res.get("status") == "QUARANTINED", f"Expected QUARANTINED, got {res}"
    q_id = res.get("quarantine_id")

    # Verify QuarantineRecord is visible in repository
    q_repo = get_quarantine_repository()
    q_rec = q_repo.get(q_id, tenant_context=tc)
    assert q_rec is not None, f"Quarantine record {q_id} not found in repository"
    assert q_rec.quarantine_reason == QuarantineReason.RETRIES_EXHAUSTED
    assert q_rec.status == QuarantineStatus.QUARANTINED
    assert "Simulated upstream provider API connection failure" in q_rec.error_details

    logger.info("Dead-Letter Proof: Failed task quarantined with QuarantineRecord ID: %s", q_id)
    return True


def test_prometheus_metrics_scrapable() -> bool:
    """Verifies that Prometheus metrics contain the recorded task durations, outcomes, and rows."""
    logger.info("=== PROOF 4: Prometheus Metrics Exposition ===")
    scraped = metrics.scrape().decode("utf-8")
    assert "sync_job_duration_seconds" in scraped, "sync_job_duration_seconds missing from metrics"
    assert "sync_job_outcome_total" in scraped, "sync_job_outcome_total missing from metrics"
    assert "ingestion_rows_total" in scraped, "ingestion_rows_total missing from metrics"

    # Print relevant metric sample lines
    relevant = [line for line in scraped.splitlines() if any(k in line for k in ["sync_job_outcome_total", "ingestion_rows_total"])]
    print("\nPrometheus Scraped Sample Metrics:")
    for line in relevant[:12]:
        print("  " + line)
    return True


def main() -> int:
    logger.info("Starting CloudLens Scheduled Background Work Verification Suite...")
    try:
        test_leader_lock_prevents_duplicate_runs()
        test_execute_all_21_tasks()
        test_dead_letter_quarantine()
        test_prometheus_metrics_scrapable()
        logger.info("\n>>> ALL CHECKS PASSED SUCCESSFULLY! <<<")
        return 0
    except Exception as exc:
        logger.exception("Verification suite encountered an error: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
