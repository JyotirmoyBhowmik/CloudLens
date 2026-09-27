"""CloudLens Raw Payload Landing Service (Prompt 14 Item 95).

Enforces:
- Every ingestion run writes its raw provider payload to object storage before normalisation.
- Complete immutability: Landing records cannot be overwritten.
- Strict tenant partitioning under object storage: tenants/{tenant_id}/landings/... (SEC-015).
- Schema versioning and cryptographic SHA256 integrity digest computation.
- Audit event generation (CONNECTOR_PAYLOAD_LANDED).
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from connectors.contract.models import RawLandingRecord
from domain.audit.service import AuditService, get_audit_service
from domain.models.enums import AuditEventType, ConnectorCapability
from domain.models.exceptions import (
    MissingTenantContextException,
    RawLandingException,
)
from domain.tenant.context import TenantContext
from domain.tenant.object_store import InMemoryTenantObjectStorage, TenantObjectStorage

logger = logging.getLogger(__name__)


class RawLandingService:
    """Manages the landing of raw provider payloads to tenant-scoped object storage."""

    def __init__(
        self,
        object_storage: TenantObjectStorage | None = None,
        audit_service: AuditService | None = None,
    ) -> None:
        self._storage = object_storage or InMemoryTenantObjectStorage()
        self._audit = audit_service or get_audit_service()
        # In-memory index of landing records: landing_id -> RawLandingRecord
        self._landings: dict[str, RawLandingRecord] = {}

    def land_raw_payload(
        self,
        tenant_context: TenantContext,
        connector_id: str,
        run_id: str,
        capability: ConnectorCapability,
        page_number: int,
        raw_payload: Any,
        schema_version: str = "2026-09-01",
        actor: str = "SYSTEM_INGESTION",
    ) -> RawLandingRecord:
        """Serializes and lands the immutable raw provider payload before normalization."""
        if not tenant_context or not tenant_context.tenant_id:
            raise MissingTenantContextException(
                "Cannot land raw payload without authenticated TenantContext."
            )

        tenant_id = tenant_context.tenant_id
        landing_id = f"land-{uuid.uuid4().hex[:12]}"
        now = datetime.now(UTC)

        # 1. Deterministic JSON serialization
        try:
            payload_bytes = json.dumps(
                raw_payload,
                sort_keys=True,
                default=str,
                ensure_ascii=False,
            ).encode("utf-8")
        except Exception as e:
            raise RawLandingException(f"Failed to serialize raw payload to JSON: {e}") from e

        # 2. Cryptographic SHA-256 Checksum
        sha256_digest = hashlib.sha256(payload_bytes).hexdigest()
        byte_size = len(payload_bytes)

        # 3. Determine record count
        record_count = 0
        if isinstance(raw_payload, list):
            record_count = len(raw_payload)
        elif isinstance(raw_payload, dict):
            # Check for common collection keys
            items = (
                raw_payload.get("items") or raw_payload.get("records") or raw_payload.get("data")
            )
            if isinstance(items, list):
                record_count = len(items)
            else:
                record_count = 1

        # 4. Storage Key: relative key (TenantObjectStorage handles tenant prefix automatically)
        relative_key = (
            f"landings/{connector_id}/{capability.value}/{run_id}/page_{page_number}.json"
        )

        # Check immutability: Ensure no overwrite of existing landed key
        if self._storage.object_exists(tenant_context=tenant_context, key=relative_key):
            existing_data = self._storage.get_object(
                tenant_context=tenant_context, key=relative_key
            )
            if existing_data != payload_bytes:
                raise RawLandingException(
                    f"Landing file '{relative_key}' already exists with different contents. "
                    "Raw landings are immutable and cannot be overwritten."
                )

        # 5. Write to tenant object store
        self._storage.put_object(
            tenant_context=tenant_context,
            key=relative_key,
            data=payload_bytes,
            content_type="application/json",
        )

        full_storage_path = f"tenants/{tenant_id}/{relative_key}"

        landing_record = RawLandingRecord(
            landing_id=landing_id,
            tenant_id=tenant_id,
            connector_id=connector_id,
            run_id=run_id,
            capability=capability,
            schema_version=schema_version,
            storage_path=full_storage_path,
            sha256_checksum=sha256_digest,
            byte_size=byte_size,
            record_count=record_count,
            landed_at=now,
        )

        self._landings[landing_id] = landing_record

        # 6. Audit recording
        self._audit.record_event(
            tenant_context=tenant_context,
            event_type=AuditEventType.CONNECTOR_PAYLOAD_LANDED,
            actor=actor,
            payload={
                "landing_id": landing_id,
                "connector_id": connector_id,
                "run_id": run_id,
                "capability": capability.value,
                "storage_path": full_storage_path,
                "sha256_checksum": sha256_digest,
                "byte_size": byte_size,
                "record_count": record_count,
                "schema_version": schema_version,
            },
        )

        logger.info(
            "Raw payload landed successfully: id=%s, connector=%s, cap=%s, path=%s, size=%d bytes, sha256=%s",
            landing_id,
            connector_id,
            capability.value,
            full_storage_path,
            byte_size,
            sha256_digest,
        )
        return landing_record

    def get_landing(self, landing_id: str) -> RawLandingRecord | None:
        """Retrieves landing metadata by ID."""
        return self._landings.get(landing_id)

    def list_landings(
        self,
        tenant_context: TenantContext,
        connector_id: str | None = None,
        capability: ConnectorCapability | None = None,
    ) -> list[RawLandingRecord]:
        """Lists landing metadata records filtered by tenant and optional connector/capability."""
        if not tenant_context or not tenant_context.tenant_id:
            raise MissingTenantContextException(
                "Cannot list landings without authenticated TenantContext."
            )

        results = [
            rec for rec in self._landings.values() if rec.tenant_id == tenant_context.tenant_id
        ]
        if connector_id:
            results = [rec for rec in results if rec.connector_id == connector_id]
        if capability:
            results = [rec for rec in results if rec.capability == capability]
        return results

    def reset_for_test(self) -> None:
        """Resets landing records for tests."""
        self._landings.clear()


# Global raw landing service singleton
raw_landing_service = RawLandingService()
