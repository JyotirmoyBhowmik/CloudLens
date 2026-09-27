"""CloudLens Connector Lifecycle State Machine & Failure Isolation (Prompt 14 Item 91).

Enforces:
- Seven canonical lifecycle states:
  Registered, Credential bound, Validated, Active, Degraded, Failed, Suspended.
- Validated state transitions with audit event logging.
- Per-capability failure isolation: a failure in cost ingestion never halts inventory sync.
- Dynamic evaluation of overall connector health from per-capability states.
"""

from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime

from connectors.contract.circuit_breaker import CircuitBreakerRegistry, circuit_breaker_registry
from connectors.contract.models import (
    CapabilityErrorDetail,
    CapabilityHealthRecord,
)
from domain.audit.service import AuditService, get_audit_service
from domain.models.enums import (
    AuditEventType,
    CapabilityHealth,
    CircuitBreakerState,
    ConnectorCapability,
    ConnectorLifecycleState,
)
from domain.models.exceptions import (
    InvalidConnectorStateTransitionException,
    MissingTenantContextException,
)
from domain.tenant.context import TenantContext

logger = logging.getLogger(__name__)

# Foundational capabilities whose failure breaks the entire connector
FOUNDATIONAL_CAPABILITIES = {
    ConnectorCapability.AUTHENTICATE,
    ConnectorCapability.VALIDATE_PERMISSIONS,
}

# Legal lifecycle transitions map
ALLOWED_TRANSITIONS: dict[ConnectorLifecycleState, set[ConnectorLifecycleState]] = {
    ConnectorLifecycleState.REGISTERED: {
        ConnectorLifecycleState.CREDENTIAL_BOUND,
        ConnectorLifecycleState.SUSPENDED,
    },
    ConnectorLifecycleState.CREDENTIAL_BOUND: {
        ConnectorLifecycleState.VALIDATED,
        ConnectorLifecycleState.FAILED,
        ConnectorLifecycleState.SUSPENDED,
    },
    ConnectorLifecycleState.VALIDATED: {
        ConnectorLifecycleState.ACTIVE,
        ConnectorLifecycleState.DEGRADED,
        ConnectorLifecycleState.FAILED,
        ConnectorLifecycleState.SUSPENDED,
    },
    ConnectorLifecycleState.ACTIVE: {
        ConnectorLifecycleState.DEGRADED,
        ConnectorLifecycleState.FAILED,
        ConnectorLifecycleState.SUSPENDED,
    },
    ConnectorLifecycleState.DEGRADED: {
        ConnectorLifecycleState.ACTIVE,
        ConnectorLifecycleState.FAILED,
        ConnectorLifecycleState.SUSPENDED,
    },
    ConnectorLifecycleState.FAILED: {
        ConnectorLifecycleState.CREDENTIAL_BOUND,
        ConnectorLifecycleState.VALIDATED,
        ConnectorLifecycleState.SUSPENDED,
    },
    ConnectorLifecycleState.SUSPENDED: {
        ConnectorLifecycleState.REGISTERED,
        ConnectorLifecycleState.CREDENTIAL_BOUND,
        ConnectorLifecycleState.VALIDATED,
        ConnectorLifecycleState.ACTIVE,
        ConnectorLifecycleState.FAILED,
    },
}


class ConnectorLifecycleManager:
    """Manages lifecycle states and per-capability health records for connectors."""

    def __init__(
        self,
        audit_service: AuditService | None = None,
        cb_registry: CircuitBreakerRegistry | None = None,
    ) -> None:
        self._audit = audit_service or get_audit_service()
        self._breakers = cb_registry or circuit_breaker_registry
        # Map: (tenant_id, connector_id) -> ConnectorLifecycleState
        self._states: dict[tuple[str, str], ConnectorLifecycleState] = {}
        # Map: (tenant_id, connector_id, capability) -> CapabilityHealthRecord
        self._capability_health: dict[tuple[str, str, str], CapabilityHealthRecord] = {}
        self._lock = threading.Lock()

    def get_state(self, tenant_id: str, connector_id: str) -> ConnectorLifecycleState:
        """Returns the current lifecycle state of the connector, defaulting to REGISTERED."""
        with self._lock:
            return self._states.get((tenant_id, connector_id), ConnectorLifecycleState.REGISTERED)

    def transition_state(
        self,
        tenant_context: TenantContext,
        connector_id: str,
        target_state: ConnectorLifecycleState,
        reason: str | None = None,
        actor: str = "SYSTEM_LIFECYCLE",
    ) -> ConnectorLifecycleState:
        """Transitions connector to target state if legal. Records audit event."""
        if not tenant_context or not tenant_context.tenant_id:
            raise MissingTenantContextException(
                "Cannot transition connector state without authenticated TenantContext."
            )

        tenant_id = tenant_context.tenant_id
        key = (tenant_id, connector_id)

        with self._lock:
            current_state = self._states.get(key, ConnectorLifecycleState.REGISTERED)

            if current_state == target_state:
                return current_state

            allowed_targets = ALLOWED_TRANSITIONS.get(current_state, set())
            if target_state not in allowed_targets:
                raise InvalidConnectorStateTransitionException(
                    current_state=current_state.value,
                    attempted_state=target_state.value,
                )

            self._states[key] = target_state

        logger.info(
            "Connector %s transitioned: %s -> %s (reason: %s)",
            connector_id,
            current_state.value,
            target_state.value,
            reason or "normal lifecycle operation",
        )

        self._audit.record_event(
            tenant_context=tenant_context,
            event_type=AuditEventType.CONNECTOR_STATE_CHANGED,
            actor=actor,
            payload={
                "connector_id": connector_id,
                "previous_state": current_state.value,
                "new_state": target_state.value,
                "reason": reason or "State transition executed",
            },
        )
        return target_state

    def record_capability_failure(
        self,
        tenant_context: TenantContext,
        connector_id: str,
        capability: ConnectorCapability,
        error_detail: CapabilityErrorDetail,
        actor: str = "SYSTEM_CONNECTOR",
    ) -> CapabilityHealthRecord:
        """Records an execution failure for a single capability.

        Enforces failure isolation: Non-foundational failure degrades only this capability
        and transitions connector to DEGRADED without halting other capabilities.
        """
        if not tenant_context or not tenant_context.tenant_id:
            raise MissingTenantContextException(
                "Cannot record failure without authenticated TenantContext."
            )

        tenant_id = tenant_context.tenant_id
        cap_key = (tenant_id, connector_id, capability.value)
        breaker = self._breakers.get_breaker(connector_id, capability)
        breaker.record_failure(error_detail.verbatim_error)

        with self._lock:
            existing = self._capability_health.get(cap_key)
            failures = (existing.consecutive_failures + 1) if existing else 1
            last_success = existing.last_success_at if existing else None

            # Non-foundational vs foundational degradation logic
            if capability in FOUNDATIONAL_CAPABILITIES:
                new_health = CapabilityHealth.FAILED
            else:
                new_health = CapabilityHealth.DEGRADED

            record = CapabilityHealthRecord(
                capability=capability,
                health=new_health,
                circuit_state=breaker.state,
                consecutive_failures=failures,
                last_success_at=last_success,
                last_failure_at=datetime.now(UTC),
                error_detail=error_detail,
            )
            self._capability_health[cap_key] = record

        # Determine if overall connector state should transition
        current_state = self.get_state(tenant_id, connector_id)
        if capability in FOUNDATIONAL_CAPABILITIES:
            if current_state in (
                ConnectorLifecycleState.ACTIVE,
                ConnectorLifecycleState.DEGRADED,
                ConnectorLifecycleState.VALIDATED,
            ):
                self.transition_state(
                    tenant_context=tenant_context,
                    connector_id=connector_id,
                    target_state=ConnectorLifecycleState.FAILED,
                    reason=f"Foundational capability '{capability.value}' failed: {error_detail.plain_language_explanation}",
                    actor=actor,
                )
        else:
            if current_state == ConnectorLifecycleState.ACTIVE:
                self.transition_state(
                    tenant_context=tenant_context,
                    connector_id=connector_id,
                    target_state=ConnectorLifecycleState.DEGRADED,
                    reason=f"Capability '{capability.value}' degraded: {error_detail.plain_language_explanation}",
                    actor=actor,
                )

        self._audit.record_event(
            tenant_context=tenant_context,
            event_type=AuditEventType.CONNECTOR_CAPABILITY_DEGRADED,
            actor=actor,
            payload={
                "connector_id": connector_id,
                "capability": capability.value,
                "health": new_health.value,
                "consecutive_failures": failures,
                "verbatim_error": error_detail.verbatim_error,
                "plain_language_explanation": error_detail.plain_language_explanation,
            },
        )
        return record

    def record_capability_success(
        self,
        tenant_context: TenantContext,
        connector_id: str,
        capability: ConnectorCapability,
        actor: str = "SYSTEM_CONNECTOR",
    ) -> CapabilityHealthRecord:
        """Records a successful execution for a capability, potentially recovering degraded state."""
        if not tenant_context or not tenant_context.tenant_id:
            raise MissingTenantContextException(
                "Cannot record success without authenticated TenantContext."
            )

        tenant_id = tenant_context.tenant_id
        cap_key = (tenant_id, connector_id, capability.value)
        breaker = self._breakers.get_breaker(connector_id, capability)
        breaker.record_success()

        was_degraded = False
        with self._lock:
            existing = self._capability_health.get(cap_key)
            if existing and existing.health in (CapabilityHealth.DEGRADED, CapabilityHealth.FAILED):
                was_degraded = True

            last_failure = existing.last_failure_at if existing else None
            record = CapabilityHealthRecord(
                capability=capability,
                health=CapabilityHealth.HEALTHY,
                circuit_state=breaker.state,
                consecutive_failures=0,
                last_success_at=datetime.now(UTC),
                last_failure_at=last_failure,
                error_detail=None,
            )
            self._capability_health[cap_key] = record

        if was_degraded:
            self._audit.record_event(
                tenant_context=tenant_context,
                event_type=AuditEventType.CONNECTOR_CAPABILITY_RECOVERED,
                actor=actor,
                payload={
                    "connector_id": connector_id,
                    "capability": capability.value,
                    "health": CapabilityHealth.HEALTHY.value,
                },
            )
            # Check if all other capabilities are healthy to restore ACTIVE
            self._recheck_connector_health(tenant_context, connector_id, actor)

        return record

    def _recheck_connector_health(
        self,
        tenant_context: TenantContext,
        connector_id: str,
        actor: str,
    ) -> None:
        """Checks if all tracked capabilities are healthy and restores ACTIVE if degraded."""
        tenant_id = tenant_context.tenant_id
        current_state = self.get_state(tenant_id, connector_id)
        if current_state != ConnectorLifecycleState.DEGRADED:
            return

        with self._lock:
            prefix = (tenant_id, connector_id)
            records = [v for k, v in self._capability_health.items() if (k[0], k[1]) == prefix]
            has_unhealthy = any(
                r.health in (CapabilityHealth.DEGRADED, CapabilityHealth.FAILED)
                or r.circuit_state == CircuitBreakerState.OPEN
                for r in records
            )

        if not has_unhealthy:
            self.transition_state(
                tenant_context=tenant_context,
                connector_id=connector_id,
                target_state=ConnectorLifecycleState.ACTIVE,
                reason="All capabilities recovered to HEALTHY state",
                actor=actor,
            )

    def get_capability_health(
        self,
        tenant_id: str,
        connector_id: str,
        capability: ConnectorCapability,
    ) -> CapabilityHealthRecord:
        """Returns health record for a capability, defaulting to HEALTHY."""
        cap_key = (tenant_id, connector_id, capability.value)
        breaker = self._breakers.get_breaker(connector_id, capability)
        with self._lock:
            rec = self._capability_health.get(cap_key)
            if not rec:
                rec = CapabilityHealthRecord(
                    capability=capability,
                    health=CapabilityHealth.HEALTHY,
                    circuit_state=breaker.state,
                )
            return rec

    def get_all_capability_health(
        self,
        tenant_id: str,
        connector_id: str,
    ) -> dict[ConnectorCapability, CapabilityHealthRecord]:
        """Returns all capability health records for a connector."""
        prefix = (tenant_id, connector_id)
        with self._lock:
            return {
                ConnectorCapability(k[2]): v
                for k, v in self._capability_health.items()
                if (k[0], k[1]) == prefix
            }

    def reset_for_test(self) -> None:
        """Clears states for testing."""
        with self._lock:
            self._states.clear()
            self._capability_health.clear()


# Global lifecycle manager singleton
connector_lifecycle_manager = ConnectorLifecycleManager()
