"""Audit Service & Cryptographic Stream Chaining (Prompt 13 Item 86).

Enforces:
- Full taxonomy event ingestion into append-only tenant stream.
- Cryptographic SHA-256 hash chaining for tamper evidence.
- Mechanical immutability: attempts to update or delete audit records by any role
  (including Super Admin) are rejected, and the mutation attempt is itself audited.
"""

import hashlib
import json
import threading
import uuid
from datetime import UTC, datetime
from typing import Any

from domain.audit.models import (
    AuditEvent,
    AuditEventCreate,
    AuditEventFilter,
)
from domain.audit.repository import AuditRepository
from domain.models.enums import AuditEventType
from domain.models.exceptions import (
    AuditRecordNotFoundException,
    AuditTamperForbiddenException,
)
from domain.observability import get_logger
from domain.tenant.context import TenantContext, require_tenant_context

logger = get_logger("cloudlens.domain.audit")


class AuditService:
    """Enterprise append-only audit stream management service."""

    def __init__(self, repository: AuditRepository | None = None) -> None:
        self.repository = repository or AuditRepository()
        self._lock = threading.Lock()

    def _compute_hash(
        self,
        tenant_id: str,
        event_type: AuditEventType,
        actor_id: str,
        resource_type: str,
        resource_id: str,
        timestamp: datetime,
        previous_event_hash: str | None,
        details: dict[str, Any],
    ) -> str:
        """Computes deterministic cryptographic SHA-256 hash chaining to previous event."""
        payload_str = json.dumps(details, sort_keys=True, default=str)
        chain_input = (
            f"{tenant_id}:{event_type.value}:{actor_id}:{resource_type}:{resource_id}:"
            f"{timestamp.isoformat()}:{previous_event_hash or 'GENESIS'}:{payload_str}"
        )
        return hashlib.sha256(chain_input.encode("utf-8")).hexdigest()

    def append_event(
        self,
        tenant_context: TenantContext,
        event_in: AuditEventCreate,
    ) -> AuditEvent:
        """Appends a new event into the tenant's cryptographically chained audit stream."""
        tc = require_tenant_context(tenant_context)
        now = datetime.now(UTC)

        with self._lock:
            last_event = self.repository.get_last_event(tenant_context=tc)
            prev_hash = last_event.event_hash if last_event else None

            event_id = f"aud-{uuid.uuid4().hex[:16]}"
            event_hash = self._compute_hash(
                tenant_id=tc.tenant_id,
                event_type=event_in.event_type,
                actor_id=event_in.actor_id,
                resource_type=event_in.resource_type,
                resource_id=event_in.resource_id,
                timestamp=now,
                previous_event_hash=prev_hash,
                details=event_in.details,
            )

            event = AuditEvent(
                id=event_id,
                tenant_id=tc.tenant_id,
                event_type=event_in.event_type,
                actor_id=event_in.actor_id,
                actor_roles=event_in.actor_roles,
                action=event_in.action,
                resource_type=event_in.resource_type,
                resource_id=event_in.resource_id,
                details=event_in.details,
                correlation_id=event_in.correlation_id or tc.correlation_id,
                ip_address=event_in.ip_address,
                user_agent=event_in.user_agent,
                timestamp=now,
                previous_event_hash=prev_hash,
                event_hash=event_hash,
            )

            persisted = self.repository.save(event, tenant_context=tc)

        logger.info(
            "Audit event appended",
            extra={
                "tenant_id": tc.tenant_id,
                "event_id": event_id,
                "event_type": event_in.event_type.value,
                "actor_id": event_in.actor_id,
                "action": event_in.action,
            },
        )
        return persisted

    def list_events(
        self,
        tenant_context: TenantContext,
        filter_params: AuditEventFilter | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AuditEvent]:
        """Lists audit events for tenant."""
        tc = require_tenant_context(tenant_context)
        return self.repository.list(
            tenant_context=tc, filter_params=filter_params, limit=limit, offset=offset
        )

    def get_event(self, tenant_context: TenantContext, event_id: str) -> AuditEvent:
        """Retrieves an individual audit event."""
        tc = require_tenant_context(tenant_context)
        event = self.repository.get(event_id, tenant_context=tc)
        if event is None:
            raise AuditRecordNotFoundException(event_id)
        return event

    def verify_stream_integrity(self, tenant_context: TenantContext) -> bool:
        """Verifies cryptographic hash chain continuity across all events for tenant."""
        tc = require_tenant_context(tenant_context)
        events = self.repository.list(tenant_context=tc, limit=100000, offset=0)

        expected_prev_hash: str | None = None
        for event in events:
            if event.previous_event_hash != expected_prev_hash:
                logger.error(
                    "Audit hash chain broken: previous_event_hash mismatch",
                    extra={
                        "event_id": event.id,
                        "expected": expected_prev_hash,
                        "found": event.previous_event_hash,
                    },
                )
                return False

            recalculated_hash = self._compute_hash(
                tenant_id=tc.tenant_id,
                event_type=event.event_type,
                actor_id=event.actor_id,
                resource_type=event.resource_type,
                resource_id=event.resource_id,
                timestamp=event.timestamp,
                previous_event_hash=expected_prev_hash,
                details=event.details,
            )
            if recalculated_hash != event.event_hash:
                logger.error(
                    "Audit event hash tampered or corrupted",
                    extra={
                        "event_id": event.id,
                        "expected": recalculated_hash,
                        "found": event.event_hash,
                    },
                )
                return False

            expected_prev_hash = event.event_hash

        return True

    def attempt_mutation(
        self,
        tenant_context: TenantContext,
        event_id: str,
        operation: str,
    ) -> None:
        """Rejects any attempt to update or delete an audit record and audits the attempt itself.

        Acceptance Criteria:
        "No role, including Super Admin, can edit or delete an audit record;
         the attempt is itself audited."
        """
        tc = require_tenant_context(tenant_context)

        # 1. Record the mutation attempt in the audit stream
        self.append_event(
            tenant_context=tc,
            event_in=AuditEventCreate(
                event_type=AuditEventType.AUDIT_MUTATION_ATTEMPT,
                actor_id=tc.user_id,
                actor_roles=tc.roles,
                action=f"ILLEGAL_{operation.upper()}",
                resource_type="AUDIT_EVENT",
                resource_id=event_id,
                details={
                    "attempted_operation": operation,
                    "target_event_id": event_id,
                    "is_superuser": tc.is_superuser,
                    "violation": "SEC-015 immutable audit violation",
                },
                correlation_id=tc.correlation_id,
            ),
        )

        # 2. Refuse mechanically
        raise AuditTamperForbiddenException(
            f"Audit records are immutable and append-only at the database and application level. "
            f"Operation '{operation}' is strictly forbidden across all roles (Prompt 13 Item 86). "
            f"This tampering attempt has been recorded in the immutable audit stream."
        )


_GLOBAL_AUDIT_SERVICE: AuditService | None = None
_AUDIT_LOCK = threading.Lock()


def get_audit_service() -> AuditService:
    """Singleton accessor for AuditService."""
    global _GLOBAL_AUDIT_SERVICE
    with _AUDIT_LOCK:
        if _GLOBAL_AUDIT_SERVICE is None:
            _GLOBAL_AUDIT_SERVICE = AuditService()
        return _GLOBAL_AUDIT_SERVICE


def reset_audit_service() -> None:
    """Resets audit service for test isolation."""
    global _GLOBAL_AUDIT_SERVICE
    with _AUDIT_LOCK:
        _GLOBAL_AUDIT_SERVICE = AuditService()
