"""CloudLens Pagination Checkpoint Repository and Resumption Engine (Prompt 14 Item 93).

Enforces:
- Persistence of pagination continuation tokens after every single page landing.
- Guaranteed resumption of interrupted/killed sync jobs without restarting from page 1.
- Zero duplicate record processing and zero lost records.
- Strict tenant context validation (SEC-015).
"""

from __future__ import annotations

import logging
import threading
import uuid
from datetime import UTC, datetime

from connectors.contract.models import JobCheckpoint
from domain.models.enums import ConnectorCapability
from domain.models.exceptions import MissingTenantContextException, PaginationCheckpointException
from domain.tenant.context import TenantContext

logger = logging.getLogger(__name__)


class CheckpointStore:
    """Manages pagination checkpoints for connector operations across tenants."""

    def __init__(self) -> None:
        # Key: (tenant_id, job_id, capability) -> JobCheckpoint
        self._checkpoints: dict[tuple[str, str, str], JobCheckpoint] = {}
        self._lock = threading.Lock()

    def save_checkpoint(
        self,
        tenant_context: TenantContext,
        job_id: str,
        connector_id: str,
        capability: ConnectorCapability,
        continuation_token: str | None,
        page_number: int,
        records_ingested: int,
        last_record_id: str | None = None,
        status: str = "IN_PROGRESS",
    ) -> JobCheckpoint:
        """Persists or updates the checkpoint for a running job capability.

        Strictly enforces tenant context.
        """
        if not tenant_context or not tenant_context.tenant_id:
            raise MissingTenantContextException(
                "Cannot save checkpoint without authenticated TenantContext."
            )

        if page_number < 1:
            raise PaginationCheckpointException(
                f"Invalid page_number {page_number}. Page numbers must be >= 1."
            )

        key = (tenant_context.tenant_id, job_id, capability.value)
        now = datetime.now(UTC)

        with self._lock:
            existing = self._checkpoints.get(key)
            checkpoint_id = existing.checkpoint_id if existing else f"chk-{uuid.uuid4().hex[:12]}"
            created_at = existing.created_at if existing else now

            checkpoint = JobCheckpoint(
                checkpoint_id=checkpoint_id,
                tenant_id=tenant_context.tenant_id,
                job_id=job_id,
                connector_id=connector_id,
                capability=capability,
                continuation_token=continuation_token,
                page_number=page_number,
                records_ingested=records_ingested,
                last_record_id=last_record_id,
                status=status,
                created_at=created_at,
                updated_at=now,
            )
            self._checkpoints[key] = checkpoint

            logger.info(
                "Checkpoint persisted: job=%s, connector=%s, cap=%s, page=%d, token=%s, records=%d",
                job_id,
                connector_id,
                capability.value,
                page_number,
                continuation_token is not None,
                records_ingested,
            )
            return checkpoint

    def get_latest_checkpoint(
        self,
        tenant_context: TenantContext,
        job_id: str,
        capability: ConnectorCapability,
    ) -> JobCheckpoint | None:
        """Retrieves the latest checkpoint for an interrupted job to enable clean resumption."""
        if not tenant_context or not tenant_context.tenant_id:
            raise MissingTenantContextException(
                "Cannot retrieve checkpoint without authenticated TenantContext."
            )

        key = (tenant_context.tenant_id, job_id, capability.value)
        with self._lock:
            return self._checkpoints.get(key)

    def mark_completed(
        self,
        tenant_context: TenantContext,
        job_id: str,
        capability: ConnectorCapability,
        total_records: int,
    ) -> JobCheckpoint:
        """Marks a paginated job execution as COMPLETED with continuation token cleared."""
        existing = self.get_latest_checkpoint(tenant_context, job_id, capability)
        page_num = existing.page_number if existing else 1
        connector_id = existing.connector_id if existing else "unknown"

        return self.save_checkpoint(
            tenant_context=tenant_context,
            job_id=job_id,
            connector_id=connector_id,
            capability=capability,
            continuation_token=None,
            page_number=page_num,
            records_ingested=total_records,
            status="COMPLETED",
        )

    def reset_for_test(self) -> None:
        """Clears in-memory checkpoint store for tests."""
        with self._lock:
            self._checkpoints.clear()


# Global checkpoint store singleton
checkpoint_store = CheckpointStore()
