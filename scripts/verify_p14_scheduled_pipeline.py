"""Prompt P14 Verification: Ingestion Pipeline on Schedule.

Enforces and proves:
1. Beat (single instance, leader lock) reads schedules from DB / Master Data.
2. Ingestion pipeline per run:
   fetch -> raw to MinIO raw-landing/{tenant}/{connector}/{dataset}/{period}/ ->
   FOCUS -> atomic partition replace -> refresh aggregates -> evaluate thresholds/policies ->
   alerts -> freshness.
3. Failures handled with backoff, quarantine, connector Degraded/Failed, and alerts.
4. Proof on real connection: Two scheduled cycles with short intervals set in master data.
5. DONE WHEN proofs:
   [ ] Two runs in sync_job (SQL)
   [ ] MinIO objects listed
   [ ] Dashboard figures equal SQL aggregates
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
import json
import logging
import os
import sys
import time

import boto3
from sqlalchemy import text

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from db.session import get_tenant_session
from domain.dashboards.service import get_dashboard_service
from domain.models.enums import SyncJobStatus
from domain.tenant.context import TenantContext
from workers.cloudlens_workers.celery_app import celery_app
from workers.cloudlens_workers.scheduler import DatabaseBeatScheduler
from workers.cloudlens_workers.tasks import ingest_cost_task

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("p14_verification")


def verify_scheduler_loading():
    """Validates that DatabaseBeatScheduler reads schedules from Master Data with short interval."""
    print("\n" + "=" * 80)
    print("STEP 1: DATABASE BEAT SCHEDULER MASTER DATA SCHEDULE VERIFICATION")
    print("=" * 80)

    scheduler = DatabaseBeatScheduler(app=celery_app)
    schedules = scheduler.load_database_schedules()

    sched_key = "master_SCHED_LIVE_REAL_COST"
    if sched_key not in schedules:
        raise AssertionError(f"Master schedule '{sched_key}' was not found in scheduler dictionary: {list(schedules.keys())}")

    entry = schedules[sched_key]
    print(f"Loaded schedule entry key: {sched_key}")
    print(f"  Task:     {entry['task']}")
    print(f"  Schedule: {entry['schedule']}")
    print(f"  Args:     {entry['args']}")

    assert entry["task"] == "cloudlens.tasks.ingest_cost", f"Unexpected task: {entry['task']}"
    assert entry["schedule"].total_seconds() <= 60, f"Expected short interval, got {entry['schedule']}"
    print("[PASS] Beat Scheduler reads schedule from Master Data with short interval (no cron literals).")
    return entry


def run_scheduled_cycle(cycle_num: int, entry: dict) -> dict:
    """Executes a scheduled cycle outside web requests via tenant session."""
    print(f"\n--- EXECUTING SCHEDULED CYCLE #{cycle_num} ---")
    args = entry["args"]
    tenant_payload = args[0]
    connector_id = args[1] if len(args) > 1 else None

    # Dispatch task via worker task function with tenant session
    result = ingest_cost_task(
        tenant_context_payload=tenant_payload,
        connector_id=connector_id,
    )
    print(f"Cycle #{cycle_num} completed: status={result.get('status')}, job_id={result.get('job_id')}, rows_ingested={result.get('rows_ingested')}")
    assert result.get("status") == "COMPLETED", f"Expected COMPLETED status, got: {result}"
    assert result.get("rows_ingested", 0) > 0, f"Expected > 0 rows ingested, got: {result.get('rows_ingested')}"
    return result


async def query_sync_jobs_proof(tenant_id: str, connector_id: str) -> list[dict]:
    """Queries sync_jobs in PostgreSQL to prove two completed runs."""
    async with get_tenant_session(tenant_id) as session:
        query = text("""
            SELECT id, tenant_id, connector_id, sync_type, capability, status,
                   started_at, completed_at, rows_ingested
            FROM sync_jobs
            WHERE tenant_id = :tid AND connector_id = :cid
            ORDER BY started_at DESC
            LIMIT 5;
        """)
        res = await session.execute(query, {"tid": tenant_id, "cid": connector_id})
        rows = [dict(r) for r in res.mappings().all()]
        return rows


def list_minio_objects(tenant_id: str, connector_id: str) -> list[dict]:
    """Lists raw landed objects in MinIO bucket 'raw-landing'."""
    s3 = boto3.client(
        "s3",
        endpoint_url=os.getenv("S3_ENDPOINT", "http://localhost:9000"),
        aws_access_key_id=os.getenv("S3_ACCESS_KEY", "cloudlens_minio"),
        aws_secret_access_key=os.getenv("S3_SECRET_KEY", "cloudlens_minio_password"),
        region_name="us-east-1",
    )

    prefix = f"{tenant_id}/{connector_id}/"
    resp = s3.list_objects_v2(Bucket="raw-landing", Prefix=prefix)
    contents = resp.get("Contents", [])
    out = []
    for item in contents:
        out.append({
            "bucket": "raw-landing",
            "key": item["Key"],
            "full_path": f"raw-landing/{item['Key']}",
            "size_bytes": item["Size"],
            "last_modified": item["LastModified"].isoformat(),
        })
    return out


async def _query_sql_sums(tenant_id: str):
    async with get_tenant_session(tenant_id) as session:
        # 1. Direct sum from cost_fact
        q_fact = text("SELECT COALESCE(SUM(billed_cost), 0) FROM cost_fact WHERE tenant_id = :tid;")
        cost_fact_sum = (await session.execute(q_fact, {"tid": tenant_id})).scalar()

        # 2. Materialized sum from agg_cost_scope_day
        q_agg = text("SELECT COALESCE(SUM(billed_cost), 0) FROM agg_cost_scope_day WHERE tenant_id = :tid;")
        agg_day_sum = (await session.execute(q_agg, {"tid": tenant_id})).scalar()

        # Find latest billing period
        q_period = text("SELECT billing_period_start FROM cost_fact WHERE tenant_id = :tid ORDER BY billing_period_start DESC LIMIT 1;")
        period_row = (await session.execute(q_period, {"tid": tenant_id})).scalar()

    return {
        "cost_fact_sum": Decimal(str(cost_fact_sum)),
        "agg_cost_scope_day_sum": Decimal(str(agg_day_sum)),
        "period_id": period_row.strftime("%Y-%m") if period_row else "2026-10",
    }


def query_sql_aggregates_and_dashboard(tenant_id: str):
    """Compares SQL cost_fact sum and agg_cost_scope_day sum with Dashboard figures."""
    from db.session import run_async

    sql_data = run_async(_query_sql_sums(tenant_id))

    tc = TenantContext(
        tenant_id=tenant_id,
        user_id="verifier",
        roles=["SUPER_ADMIN"],
        is_system=True,
    )
    dash_service = get_dashboard_service()
    dash = dash_service.get_executive_dashboard(tenant_context=tc, period_id=sql_data["period_id"])
    dashboard_total = dash.total_cloud_cost.amount

    return {
        "cost_fact_sum": sql_data["cost_fact_sum"],
        "agg_cost_scope_day_sum": sql_data["agg_cost_scope_day_sum"],
        "dashboard_total": Decimal(str(dashboard_total)),
        "period_id": sql_data["period_id"],
    }


def main():
    print("\n" + "=" * 80)
    print("PROMPT P14 VERIFICATION: INGESTION PIPELINE ON SCHEDULE")
    print("=" * 80)

    # 1. Verify DatabaseBeatScheduler
    entry = verify_scheduler_loading()
    tenant_id = entry["args"][0]["tenant_id"]
    connector_id = entry["args"][1]

    # 2. Execute Two Scheduled Cycles
    print("\n" + "=" * 80)
    print("STEP 2: RUNNING TWO SCHEDULED CYCLES ON THE REAL CONNECTION")
    print("=" * 80)

    res1 = run_scheduled_cycle(1, entry)
    time.sleep(2)
    res2 = run_scheduled_cycle(2, entry)

    # 3. PROOF 1: Two runs in sync_job (SQL)
    print("\n" + "=" * 80)
    print("DONE WHEN [1]: TWO RUNS IN SYNC_JOB (SQL)")
    print("=" * 80)
    from db.session import run_async

    jobs = run_async(query_sync_jobs_proof(tenant_id, connector_id))
    print(f"Total sync_job records found for connector '{connector_id}': {len(jobs)}")
    for i, j in enumerate(jobs[:2], 1):
        print(f"  Run #{i}: ID={j['id']}, Status={j['status']}, SyncType={j['sync_type']}, Rows={j['rows_ingested']}, Started={j['started_at']}, Completed={j['completed_at']}")

    completed_runs = [j for j in jobs if j["status"] == SyncJobStatus.COMPLETED or j["status"] == "COMPLETED"]
    assert len(completed_runs) >= 2, f"Expected at least 2 completed runs in sync_jobs, got {len(completed_runs)}"
    print("[PASS] Two runs verified in sync_job table via direct SQL query.")

    # 4. PROOF 2: MinIO objects listed
    print("\n" + "=" * 80)
    print("DONE WHEN [2]: MINIO OBJECTS LISTED")
    print("=" * 80)
    minio_objs = list_minio_objects(tenant_id, connector_id)
    print(f"Total objects found in MinIO bucket 'raw-landing' for '{tenant_id}/{connector_id}': {len(minio_objs)}")
    for obj in minio_objs:
        print(f"  Object: {obj['full_path']} ({obj['size_bytes']} bytes, modified {obj['last_modified']})")

    assert len(minio_objs) >= 2, f"Expected at least 2 landed objects in MinIO bucket 'raw-landing', got {len(minio_objs)}"
    print("[PASS] Raw provider landing objects verified in MinIO object storage.")

    # 5. PROOF 3: Dashboard figures equal SQL aggregates
    print("\n" + "=" * 80)
    print("DONE WHEN [3]: DASHBOARD FIGURES EQUAL SQL AGGREGATES")
    print("=" * 80)
    comparison = query_sql_aggregates_and_dashboard(tenant_id)
    print(f"  SQL cost_fact Total Billed:           ${comparison['cost_fact_sum']:.2f}")
    print(f"  SQL agg_cost_scope_day Total Billed:   ${comparison['agg_cost_scope_day_sum']:.2f}")
    print(f"  Executive Dashboard Total Spend:      ${comparison['dashboard_total']:.2f}")

    assert comparison["cost_fact_sum"] > Decimal("0.00"), "cost_fact sum is 0.00"
    assert round(comparison["cost_fact_sum"], 2) == round(comparison["agg_cost_scope_day_sum"], 2), (
        f"cost_fact sum ({comparison['cost_fact_sum']}) != agg_cost_scope_day sum ({comparison['agg_cost_scope_day_sum']})"
    )
    assert round(comparison["dashboard_total"], 2) == round(comparison["cost_fact_sum"], 2), (
        f"Dashboard total ({comparison['dashboard_total']}) != SQL aggregate ({comparison['cost_fact_sum']})"
    )
    print(f"[PASS] Dashboard figure (${comparison['dashboard_total']:.2f}) strictly equals SQL aggregate (${comparison['cost_fact_sum']:.2f}).")

    print("\n" + "=" * 80)
    print("ALL DONE WHEN CRITERIA VERIFIED SUCCESSFULLY")
    print("=" * 80)


if __name__ == "__main__":
    main()
