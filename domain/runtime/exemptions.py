"""Temporary Runtime Schedule Exemption Manager (Prompt 26 Item 163).

Enforces:
- RUN-005 / FR-254: Temporary runtime exemptions must be time-boxed, require recorded justification,
  be fully audited, and expire automatically.
- AC-062: An exemption suppresses the alert, appears in the active-exemption report and expires automatically.
- Enterprise discipline: Minimum 20 characters recorded reason; automatic reversion when expired.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from domain.audit.service import AuditEventCreate, get_audit_service
from domain.models.enums import AuditEventType
from domain.models.exceptions import (
    ExemptionReasonTooShortException,
    InvalidScheduleException,
)
from domain.runtime.models import RuntimeExemption, RuntimeExemptionCreateRequest
from domain.tenant.context import TenantContext

if TYPE_CHECKING:
    from domain.runtime.repository import RuntimeRepository

logger = logging.getLogger(__name__)


class ExemptionManager:
    """Manages lifecycle of temporary runtime schedule exemptions."""

    def __init__(self, repository: RuntimeRepository) -> None:
        self.repository = repository

    def create_exemption(
        self,
        request: RuntimeExemptionCreateRequest,
        *,
        actor_id: str,
        tenant_context: TenantContext,
    ) -> RuntimeExemption:
        """Creates a time-boxed runtime schedule exemption with recorded justification."""
        now = datetime.now(UTC)

        # 1. Validate reason length
        trimmed_reason = request.reason.strip()
        min_chars = 20
        if len(trimmed_reason) < min_chars:
            raise ExemptionReasonTooShortException(length=len(trimmed_reason), min_length=min_chars)

        # 2. Validate expiration date
        if request.expires_at <= now:
            raise InvalidScheduleException(
                f"Exemption expiration '{request.expires_at.isoformat()}' must be strictly in the future."
            )

        valid_from = request.valid_from or now

        exemption = RuntimeExemption(
            tenant_id=tenant_context.tenant_id,
            resource_id=request.resource_id,
            schedule_id=request.schedule_id,
            reason=trimmed_reason,
            created_by=actor_id,
            valid_from=valid_from,
            expires_at=request.expires_at,
            is_active=True,
        )

        self.repository.save_exemption(exemption, tenant_context=tenant_context)

        # 3. Emit enterprise audit event
        try:
            audit_svc = get_audit_service()
            audit_svc.append_event(
                tenant_context=tenant_context,
                event_in=AuditEventCreate(
                    event_type=AuditEventType.RUNTIME_EXEMPTION_CREATED,
                    actor_id=actor_id,
                    actor_roles=tenant_context.roles,
                    action="RUNTIME_EXEMPTION_CREATED",
                    resource_type="RESOURCE",
                    resource_id=request.resource_id,
                    details={
                        "exemption_id": exemption.id,
                        "resource_id": request.resource_id,
                        "schedule_id": request.schedule_id,
                        "reason": trimmed_reason,
                        "valid_from": valid_from.isoformat(),
                        "expires_at": request.expires_at.isoformat(),
                    },
                    correlation_id=tenant_context.correlation_id,
                ),
            )
        except Exception as audit_err:
            logger.warning(
                "Failed to log audit event for runtime exemption creation: %s", audit_err
            )

        return exemption

    def get_active_exemption_for_resource(
        self,
        resource_id: str,
        *,
        as_of: datetime | None = None,
        tenant_context: TenantContext,
    ) -> RuntimeExemption | None:
        """Retrieves active unexpired exemption for a resource, automatically expiring stale ones."""
        check_time = as_of or datetime.now(UTC)
        exemptions = self.repository.list_exemptions_for_resource(
            resource_id, tenant_context=tenant_context
        )

        for exemp in exemptions:
            if not exemp.is_active:
                continue
            if exemp.expires_at <= check_time:
                # Stale exemption: automatically expire and audit
                self._expire_exemption(exemp, tenant_context=tenant_context)
                continue
            if exemp.valid_from <= check_time < exemp.expires_at:
                return exemp

        return None

    def list_active_exemptions(
        self,
        *,
        as_of: datetime | None = None,
        tenant_context: TenantContext,
    ) -> list[RuntimeExemption]:
        """Lists all currently active unexpired exemptions across the tenant (active report)."""
        check_time = as_of or datetime.now(UTC)
        all_exemptions = self.repository.list_all_exemptions(tenant_context=tenant_context)
        active: list[RuntimeExemption] = []

        for exemp in all_exemptions:
            if not exemp.is_active:
                continue
            if exemp.expires_at <= check_time:
                self._expire_exemption(exemp, tenant_context=tenant_context)
            else:
                active.append(exemp)

        return active

    def _expire_exemption(
        self, exemption: RuntimeExemption, *, tenant_context: TenantContext
    ) -> None:
        """Marks an exemption expired and emits an audit trail entry."""
        exemption.is_active = False
        self.repository.save_exemption(exemption, tenant_context=tenant_context)

        try:
            audit_svc = get_audit_service()
            audit_svc.append_event(
                tenant_context=tenant_context,
                event_in=AuditEventCreate(
                    event_type=AuditEventType.RUNTIME_EXEMPTION_EXPIRED,
                    actor_id="system",
                    actor_roles=["SYSTEM"],
                    action="RUNTIME_EXEMPTION_EXPIRED",
                    resource_type="RESOURCE",
                    resource_id=exemption.resource_id,
                    details={
                        "exemption_id": exemption.id,
                        "resource_id": exemption.resource_id,
                        "expired_at": exemption.expires_at.isoformat(),
                        "reason": exemption.reason,
                    },
                    correlation_id=tenant_context.correlation_id,
                ),
            )
        except Exception as audit_err:
            logger.warning(
                "Failed to log audit event for runtime exemption expiration: %s", audit_err
            )
