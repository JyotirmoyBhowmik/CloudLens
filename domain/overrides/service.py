"""Override Management Service & Automatic Expiry Engine (Prompt 13 Item 87).

Enforces:
- Mandatory eight attributes: who, what, why (min length >= 20 chars), when,
  previous value, new value, expiry, approval where required.
- Prohibition of unapproved permanent overrides.
- Automatic reversion of expired overrides with audit trail emission.
"""

import threading
import uuid
from datetime import UTC, datetime

from domain.audit.models import AuditEventCreate
from domain.audit.service import AuditService, get_audit_service
from domain.models.enums import AuditEventType, OverrideStatus
from domain.models.exceptions import (
    OverrideNotFoundException,
    OverrideValidationException,
    PermanentOverrideNotAllowedException,
)
from domain.observability import get_logger
from domain.overrides.models import (
    OverrideCreateRequest,
    OverrideRecord,
)
from domain.overrides.repository import OverrideRepository
from domain.tenant.context import TenantContext, require_tenant_context

logger = get_logger("cloudlens.domain.overrides")


class OverrideService:
    """Operational and governance override management service."""

    def __init__(
        self,
        repository: OverrideRepository | None = None,
        audit_service: AuditService | None = None,
    ) -> None:
        self.repository = repository or OverrideRepository()
        self.audit_service = audit_service or get_audit_service()
        self._lock = threading.Lock()

    def create_override(
        self,
        tenant_context: TenantContext,
        req: OverrideCreateRequest,
    ) -> OverrideRecord:
        """Creates and activates an override record after validating all 8 mandatory attributes."""
        tc = require_tenant_context(tenant_context)
        now = datetime.now(UTC)

        # 1. Validate Expiry vs Permanent constraints
        if req.is_permanent:
            if not req.approval or not req.approval.permanent_approved:
                raise PermanentOverrideNotAllowedException(
                    "Permanent overrides require explicit governance approval with permanent_approved=True "
                    "and a verified change control ticket reference."
                )
        else:
            if req.expiry is None:
                raise OverrideValidationException(
                    "Expiry timestamp is mandatory for temporary overrides (Prompt 13 Item 87)."
                )
            if req.expiry <= now:
                raise OverrideValidationException(
                    f"Override expiry timestamp '{req.expiry.isoformat()}' must be strictly in the future."
                )

        override_id = f"ovr-{uuid.uuid4().hex[:12]}"
        record = OverrideRecord(
            id=override_id,
            tenant_id=tc.tenant_id,
            override_class=req.override_class,
            who=req.who,
            what=req.what,
            why=req.why,
            when=now,
            previous_value=req.previous_value,
            new_value=req.new_value,
            expiry=req.expiry,
            is_permanent=req.is_permanent,
            approval=req.approval,
            status=OverrideStatus.ACTIVE,
            correlation_id=tc.correlation_id,
        )

        with self._lock:
            saved = self.repository.save(record, tenant_context=tc)

            # Audit override creation
            self.audit_service.append_event(
                tenant_context=tc,
                event_in=AuditEventCreate(
                    event_type=AuditEventType.OVERRIDE_CREATED,
                    actor_id=req.who,
                    actor_roles=tc.roles,
                    action="APPLY_OVERRIDE",
                    resource_type=f"OVERRIDE_{req.override_class.value}",
                    resource_id=req.what,
                    details={
                        "override_id": override_id,
                        "what": req.what,
                        "why": req.why,
                        "previous_value": req.previous_value,
                        "new_value": req.new_value,
                        "is_permanent": req.is_permanent,
                        "expiry": req.expiry.isoformat() if req.expiry else None,
                        "approval": req.approval.model_dump() if req.approval else None,
                    },
                    correlation_id=tc.correlation_id,
                ),
            )

        logger.info(
            "Override created and audited",
            extra={"tenant_id": tc.tenant_id, "override_id": override_id, "what": req.what},
        )
        return saved

    def get_override(self, tenant_context: TenantContext, override_id: str) -> OverrideRecord:
        """Retrieves an override record within caller's tenant boundary."""
        tc = require_tenant_context(tenant_context)
        record = self.repository.get(override_id, tenant_context=tc)
        if record is None:
            raise OverrideNotFoundException(override_id)
        return record

    def list_overrides(
        self,
        tenant_context: TenantContext,
        limit: int = 50,
        offset: int = 0,
    ) -> list[OverrideRecord]:
        """Lists overrides for tenant."""
        tc = require_tenant_context(tenant_context)
        return self.repository.list(tenant_context=tc, limit=limit, offset=offset)

    def revert_override(
        self,
        tenant_context: TenantContext,
        override_id: str,
        reason: str,
        actor_id: str,
    ) -> OverrideRecord:
        """Manually reverts an active override and audits the reversion."""
        tc = require_tenant_context(tenant_context)
        record = self.get_override(tenant_context=tc, override_id=override_id)

        if record.status != OverrideStatus.ACTIVE:
            raise OverrideValidationException(
                f"Cannot revert override '{override_id}' in status '{record.status.value}'."
            )

        now = datetime.now(UTC)
        record.status = OverrideStatus.REVERTED
        record.reverted_at = now
        record.reverted_by = actor_id
        record.reversion_reason = reason

        with self._lock:
            saved = self.repository.save(record, tenant_context=tc)

            # Audit manual reversion
            self.audit_service.append_event(
                tenant_context=tc,
                event_in=AuditEventCreate(
                    event_type=AuditEventType.OVERRIDE_REVERTED,
                    actor_id=actor_id,
                    actor_roles=tc.roles,
                    action="REVERT_OVERRIDE",
                    resource_type=f"OVERRIDE_{record.override_class.value}",
                    resource_id=record.what,
                    details={
                        "override_id": record.id,
                        "what": record.what,
                        "reversion_reason": reason,
                        "restored_value": record.previous_value,
                        "overridden_value": record.new_value,
                    },
                    correlation_id=tc.correlation_id,
                ),
            )

        logger.info(
            "Override reverted manually",
            extra={"tenant_id": tc.tenant_id, "override_id": override_id, "reverted_by": actor_id},
        )
        return saved

    def revert_expired_overrides(self, tenant_context: TenantContext) -> list[OverrideRecord]:
        """Scans and automatically reverts expired overrides, auditing each reversion.

        Acceptance Criteria:
        "An expired override reverts automatically and the reversion is audited."
        """
        tc = require_tenant_context(tenant_context)
        now = datetime.now(UTC)
        reverted_list: list[OverrideRecord] = []

        with self._lock:
            active_overrides = self.repository.list_active(tenant_context=tc)

            for record in active_overrides:
                if not record.is_permanent and record.expiry is not None and record.expiry <= now:
                    record.status = OverrideStatus.EXPIRED
                    record.reverted_at = now
                    record.reverted_by = "system:automatic_reversion"
                    record.reversion_reason = f"Automatic expiration: configured expiry '{record.expiry.isoformat()}' reached."

                    saved = self.repository.save(record, tenant_context=tc)
                    reverted_list.append(saved)

                    # Audit automatic expiry reversion
                    self.audit_service.append_event(
                        tenant_context=tc,
                        event_in=AuditEventCreate(
                            event_type=AuditEventType.OVERRIDE_EXPIRED,
                            actor_id="system:automatic_reversion",
                            actor_roles=["SYSTEM"],
                            action="EXPIRE_OVERRIDE",
                            resource_type=f"OVERRIDE_{record.override_class.value}",
                            resource_id=record.what,
                            details={
                                "override_id": record.id,
                                "what": record.what,
                                "expiry_timestamp": record.expiry.isoformat(),
                                "reverted_at": now.isoformat(),
                                "restored_value": record.previous_value,
                                "expired_value": record.new_value,
                            },
                            correlation_id=tc.correlation_id,
                        ),
                    )

        if reverted_list:
            logger.info(
                "Expired overrides reverted automatically",
                extra={"tenant_id": tc.tenant_id, "count": len(reverted_list)},
            )
        return reverted_list


_GLOBAL_OVERRIDE_SERVICE: OverrideService | None = None
_OVERRIDE_LOCK = threading.Lock()


def get_override_service() -> OverrideService:
    """Singleton accessor for OverrideService."""
    global _GLOBAL_OVERRIDE_SERVICE
    with _OVERRIDE_LOCK:
        if _GLOBAL_OVERRIDE_SERVICE is None:
            _GLOBAL_OVERRIDE_SERVICE = OverrideService()
        return _GLOBAL_OVERRIDE_SERVICE


def reset_override_service() -> None:
    """Resets override service for test isolation."""
    global _GLOBAL_OVERRIDE_SERVICE
    with _OVERRIDE_LOCK:
        _GLOBAL_OVERRIDE_SERVICE = OverrideService()
