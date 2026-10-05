"""Database-backed Celery Beat Scheduler with Leader Election (Prompt R-RUN).

Enforces:
- Prompt R-RUN Item 1: Celery beat with a DATABASE-backed schedule built dynamically
  from the schedule master. Strictly zero cron literals in code.
- Prompt R-RUN Item 4: Single Beat instance with leader election lock; standby instances
  do not dispatch tasks.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import timedelta
from typing import Any

from celery.beat import ScheduleEntry, Scheduler

from domain.sync.repository import get_connector_schedule_repository
from masterdata.service import get_master_data_service
from workers.cloudlens_workers.locking import BeatLeaderLock

logger = logging.getLogger(__name__)

# Capability to Celery task mapping
CAPABILITY_TASK_MAP: dict[str, str] = {
    "ingest_cost": "cloudlens.tasks.ingest_cost",
    "collect_cost_bulk": "cloudlens.tasks.ingest_cost",
    "ingest_inventory": "cloudlens.tasks.ingest_inventory",
    "discover_resources": "cloudlens.tasks.ingest_inventory",
    "ingest_inventory_full": "cloudlens.tasks.ingest_inventory",
    "ingest_usage": "cloudlens.tasks.ingest_usage",
    "collect_usage": "cloudlens.tasks.ingest_usage",
    "refresh_pricing": "cloudlens.tasks.refresh_pricing",
    "collect_pricing_public": "cloudlens.tasks.refresh_pricing",
    "discover_relationships": "cloudlens.tasks.discover_relationships",
    "collect_budgets": "cloudlens.tasks.collect_quota",
    "collect_quota": "cloudlens.tasks.collect_quota",
    "evaluate_thresholds": "cloudlens.tasks.evaluate_thresholds",
    "evaluate_policies": "cloudlens.tasks.evaluate_policies",
    "compute_forecasts": "cloudlens.tasks.compute_forecasts",
    "escalate_alerts": "cloudlens.tasks.escalate_alerts",
    "auto_resolve_alerts": "cloudlens.tasks.auto_resolve_alerts",
    "verify_remediation": "cloudlens.tasks.verify_remediation",
    "revert_overrides": "cloudlens.tasks.revert_overrides",
    "credential_expiry_check": "cloudlens.tasks.credential_expiry_check",
    "reconcile_closed_period": "cloudlens.tasks.reconcile_closed_period",
    "run_analytical_extract": "cloudlens.tasks.run_analytical_extract",
    "maintain_partitions": "cloudlens.tasks.maintain_partitions",
    "apply_retention_and_downsampling": "cloudlens.tasks.apply_retention_and_downsampling",
    "renewal_pipeline": "cloudlens.tasks.renewal_pipeline",
    "send_daily_platform_summary": "cloudlens.tasks.send_daily_platform_summary",
    "heartbeat": "cloudlens.tasks.heartbeat",
}


class DatabaseBeatScheduler(Scheduler):
    """Celery Beat scheduler loading schedules from database and master data."""

    Entry = ScheduleEntry

    def __init__(self, *args, **kwargs) -> None:
        self.leader_lock = kwargs.pop("leader_lock", None) or BeatLeaderLock()
        self._last_schedule_sync = 0.0
        self._sync_interval = 30.0  # no-hardcode-allow: reason="Schedule refresh polling interval seconds", reviewer="Prompt-48-Audit"
        super().__init__(*args, **kwargs)

    def load_database_schedules(self) -> dict[str, dict[str, Any]]:
        """Constructs Celery schedule dictionary from master data and database schedules.

        Strictly avoids cron string literals by using explicit timedelta objects.
        """
        entries: dict[str, dict[str, Any]] = {}
        default_tenant = os.getenv("DEFAULT_TENANT_ID", "demo-corp")

        # 1. Load from MasterDataService (CONNECTOR_SCHEDULE master)
        try:
            mdm = get_master_data_service()
            records = mdm.list_records("CONNECTOR_SCHEDULE")
            for rec in records:
                attrs = rec.attributes or {}
                task_key = attrs.get("capability_or_task") or rec.code.lower().removeprefix("sched_")
                task_name = CAPABILITY_TASK_MAP.get(task_key) or f"cloudlens.tasks.{task_key}"
                interval_minutes = int(attrs.get("interval_minutes", 60))
                # Interval schedule with zero cron literals
                entries[f"master_{rec.code}"] = {
                    "task": task_name,
                    "schedule": timedelta(minutes=interval_minutes),
                    "args": [
                        {
                            "tenant_id": default_tenant,
                            "user_id": "system-scheduler",
                            "roles": ["SUPER_ADMIN"],
                            "is_system": True,
                        }
                    ],
                }
        except Exception as exc:
            logger.warning("Error loading master schedules: %s", exc)

        # 2. Load custom per-connector schedules from ConnectorScheduleRepository
        try:
            sched_repo = get_connector_schedule_repository()
            # In-memory or database query across active tenant schedules
            with sched_repo._lock:
                for (tid, _), sched in sched_repo._schedules.items():
                    if not sched.is_enabled:
                        continue
                    cap_val = sched.capability.value if hasattr(sched.capability, "value") else str(sched.capability)
                    task_name = CAPABILITY_TASK_MAP.get(cap_val, "cloudlens.tasks.ingest_cost")
                    entry_name = f"connector_{sched.connector_id}_{cap_val}"
                    entries[entry_name] = {
                        "task": task_name,
                        "schedule": timedelta(minutes=sched.interval_minutes),
                        "args": [
                            {
                                "tenant_id": tid,
                                "user_id": "system-scheduler",
                                "roles": ["SUPER_ADMIN"],
                                "is_system": True,
                            },
                            sched.connector_id,
                        ],
                    }
        except Exception as exc:
            logger.warning("Error loading connector schedules: %s", exc)

        return entries

    def setup_schedule(self) -> None:
        """Initializes Celery beat schedules from database and master records."""
        self.install_default_entries(self.schedule)
        db_schedules = self.load_database_schedules()
        self.update_from_dict(db_schedules)
        self._last_schedule_sync = time.time()
        logger.info("Loaded %d database-backed schedule entries into Celery Beat.", len(self.schedule))

    def tick(self) -> float:
        """Performs scheduler tick if and only if holding the distributed leader lock."""
        # 1. Leader election check
        if not self.leader_lock.acquire_or_renew():
            # Standby instance: sleep without dispatching any tasks
            logger.debug("Beat instance %s is in STANDBY mode. Suppressing task dispatches.", self.leader_lock.instance_id)
            return 5.0  # no-hardcode-allow: reason="Standby sleep backoff interval seconds", reviewer="Prompt-48-Audit"

        # 1.5 Global Maintenance Mode check (IMP-01)
        from domain.maintenance.service import get_maintenance_mode_service
        if get_maintenance_mode_service().is_global_maintenance():
            logger.info("Global Maintenance Mode is active. Celery beat task dispatching is paused.")
            return 10.0  # no-hardcode-allow: reason="Maintenance mode beat sleep backoff seconds", reviewer="Prompt-48-Audit"

        # 2. Leader active: reload schedules if periodic refresh interval elapsed
        now = time.time()
        if now - self._last_schedule_sync > self._sync_interval:
            db_schedules = self.load_database_schedules()
            self.update_from_dict(db_schedules)
            self._last_schedule_sync = now

        # 3. Dispatch due tasks
        return super().tick()
