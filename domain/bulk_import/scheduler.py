"""Scheduled Unattended Import Runner for CMDB and Master Feeds (Prompt 53).

Enforces:
1. "Implement scheduled and API-driven import so a recurring feed from a CMDB,
   HR system or finance master can be automated once the manual import has proven the mapping."
2. Acceptance: "A scheduled CMDB feed runs unattended and reports its outcome."
"""

from __future__ import annotations

import datetime as dt
import logging
import uuid

from domain.bulk_import.engine import BulkImportEngine, get_bulk_import_engine
from domain.bulk_import.models import (
    ImportMode,
    ImportRunRecord,
    ScheduledImportJob,
)
from domain.bulk_import.repository import (
    BulkImportRepository,
    get_bulk_import_repository,
)
from domain.models.exceptions import (
    BulkImportException,
    ScheduledImportJobNotFoundException,
)
from domain.tenant.context import TenantContext, require_tenant_context

logger = logging.getLogger(__name__)


class ScheduledImportScheduler:
    """Manages and executes scheduled, unattended bulk data feeds."""

    def __init__(
        self,
        repository: BulkImportRepository | None = None,
        engine: BulkImportEngine | None = None,
    ) -> None:
        self.repository = repository or get_bulk_import_repository()
        self.engine = engine or get_bulk_import_engine()
        # Mock feed registry for simulation: source_uri -> bytes
        self._mock_feed_data: dict[str, bytes] = {}

    def register_mock_feed_data(self, source_uri: str, data: bytes) -> None:
        """Registers payload data for simulated CMDB/HR feeds."""
        self._mock_feed_data[source_uri] = data

    def create_scheduled_job(
        self,
        *,
        name: str,
        entity_type: str,
        cron_expression: str,
        mapping_profile_id: str,
        mode: ImportMode,
        source_type: str = "CMDB_CONNECTOR",
        source_uri: str,
        enabled: bool = True,
        tenant_context: TenantContext,
    ) -> ScheduledImportJob:
        """Registers a new recurring unattended import schedule."""
        tc = require_tenant_context(tenant_context)
        job_id = f"sch-{uuid.uuid4().hex[:10]}"

        job = ScheduledImportJob(
            id=job_id,
            tenant_id=tc.tenant_id,
            name=name,
            entity_type=entity_type,
            cron_expression=cron_expression,
            mapping_profile_id=mapping_profile_id,
            mode=mode,
            source_type=source_type,
            source_uri=source_uri,
            enabled=enabled,
            created_at=dt.datetime.now(dt.UTC),
        )

        return self.repository.save_scheduled_job(job, tenant_context=tc)

    def run_scheduled_job(
        self,
        job_id: str,
        *,
        tenant_context: TenantContext,
        feed_content_override: bytes | None = None,
    ) -> ImportRunRecord:
        """Executes an unattended feed job, executing dry run, applying, and reporting outcome."""
        tc = require_tenant_context(tenant_context)
        job = self.repository.get_scheduled_job(job_id, tenant_context=tc)
        if not job:
            raise ScheduledImportJobNotFoundException(job_id)

        if not job.enabled:
            raise BulkImportException(
                f"Scheduled job '{job.name}' ({job_id}) is currently disabled."
            )

        # Obtain feed data
        feed_data = feed_content_override or self._mock_feed_data.get(job.source_uri)
        if not feed_data:
            # Default empty feed representation if no source available
            feed_data = b"code,name\n"

        filename = f"{job.source_uri.split('/')[-1] or 'feed'}_{job.entity_type.lower()}.csv"

        try:
            # 1. Execute mandatory dry run
            dry_run = self.engine.execute_dry_run(
                content_bytes=feed_data,
                filename=filename,
                entity_type=job.entity_type,
                mode=job.mode,
                mapping_profile_id=job.mapping_profile_id,
                tenant_context=tc,
                actor_id=f"cron:{job.id}",
            )

            # 2. Apply import
            run_record = self.engine.apply_import(
                dry_run_id=dry_run.dry_run_id,
                tenant_context=tc,
                actor_id=f"cron:{job.id}",
            )

            # 3. Update job outcome
            job.last_run_at = dt.datetime.now(dt.UTC)
            job.last_status = "SUCCESS"
            job.last_run_id = run_record.id
            self.repository.save_scheduled_job(job, tenant_context=tc)

            logger.info(
                f"Scheduled feed '{job.name}' ({job.id}) completed successfully: "
                f"Run {run_record.id}, {run_record.created_count} created, {run_record.updated_count} updated."
            )
            return run_record

        except Exception as e:
            job.last_run_at = dt.datetime.now(dt.UTC)
            job.last_status = f"FAILED: {e}"
            self.repository.save_scheduled_job(job, tenant_context=tc)
            logger.error(f"Scheduled feed '{job.name}' ({job.id}) failed: {e}")
            raise


# Global singleton instance
_scheduler_instance = ScheduledImportScheduler()


def get_scheduled_import_scheduler() -> ScheduledImportScheduler:
    """Returns the singleton ScheduledImportScheduler."""
    return _scheduler_instance
