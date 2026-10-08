"""In-memory fake checkpoint store for test harnesses."""

from __future__ import annotations

import threading
import uuid
from datetime import UTC, datetime

from connectors.contract.models import JobCheckpoint
from domain.models.enums import ConnectorCapability
from domain.models.exceptions import MissingTenantContextException, PaginationCheckpointException
from domain.tenant.context import TenantContext


class InMemoryCheckpointStore:
    """Tenant-isolated in-memory fake checkpoint store."""

    is_in_memory: bool = True

    def __init__(self) -> None:
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
        if not tenant_context or not tenant_context.tenant_id:
            raise MissingTenantContextException("Cannot save checkpoint without authenticated TenantContext.")
        if page_number < 1:
            raise PaginationCheckpointException(f"Invalid page_number {page_number}. Page numbers must be >= 1.")

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
            return checkpoint

    def get_checkpoint(
        self,
        tenant_id: str,
        job_id: str,
        capability: str | ConnectorCapability,
    ) -> JobCheckpoint | None:
        cap_val = capability.value if isinstance(capability, ConnectorCapability) else str(capability)
        key = (tenant_id, job_id, cap_val)
        with self._lock:
            return self._checkpoints.get(key)

    def get_latest_checkpoint(
        self,
        tenant_context: TenantContext,
        job_id: str,
        capability: ConnectorCapability,
    ) -> JobCheckpoint | None:
        if not tenant_context or not tenant_context.tenant_id:
            raise MissingTenantContextException("Cannot retrieve checkpoint without authenticated TenantContext.")
        return self.get_checkpoint(tenant_context.tenant_id, job_id, capability)

    def mark_completed(
        self,
        tenant_context: TenantContext,
        job_id: str,
        capability: ConnectorCapability,
        total_records: int,
    ) -> JobCheckpoint:
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
        with self._lock:
            self._checkpoints.clear()
