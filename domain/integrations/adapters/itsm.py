"""ITSM Integration Adapter with Bidirectional Status Synchronisation (Prompt 60 / BBP Section 13.5).

Enforces:
- Inherits from BaseIntegrationAdapter with declared capabilities:
  AUTHENTICATE, HEALTH_CHECK, CREATE_TICKET, SYNC_STATUS, DISPATCH_EVENT.
- Master-data-driven severity-to-priority mapping.
- Deep links and empirical evidence payload preservation.
- Strict bidirectional synchronization: closing an external ticket closes the linked
  CloudLens remediation task; reopening the external ticket reopens the task.
  One problem must never become two records that disagree.
"""

from __future__ import annotations

import datetime as dt
import logging
import uuid

from domain.alerting.models import AlertEntity
from domain.integrations.contract import BaseIntegrationAdapter
from domain.integrations.models import (
    IntegrationConfig,
    ITSMTicket,
)
from domain.models.enums import (
    AlertSeverity,
    IntegrationCapability,
    TaskClosureCode,
    TaskPriority,
    TaskState,
)
from domain.remediation.models import RemediationHistoryEntry, RemediationTask
from domain.remediation.service import RemediationService
from domain.tenant.context import TenantContext

logger = logging.getLogger(__name__)

# Master Data Severity to ITSM Priority Mapping
SEVERITY_TO_ITSM_PRIORITY: dict[str, str] = {
    AlertSeverity.CRITICAL.value: "P1-Urgent",
    AlertSeverity.HIGH.value: "P2-High",
    AlertSeverity.WARNING.value: "P3-Medium",
    AlertSeverity.INFO.value: "P4-Low",
}

TASK_PRIORITY_TO_ITSM_PRIORITY: dict[TaskPriority, str] = {
    TaskPriority.CRITICAL: "P1-Urgent",
    TaskPriority.HIGH: "P2-High",
    TaskPriority.MEDIUM: "P3-Medium",
    TaskPriority.LOW: "P4-Low",
}

EXTERNAL_CLOSED_STATUSES = {"CLOSED", "RESOLVED", "DONE", "CANCELLED"}
EXTERNAL_OPEN_STATUSES = {"OPEN", "IN_PROGRESS", "REOPENED", "ACTIVE", "ASSIGNED"}


class ITSMAdapter(BaseIntegrationAdapter):
    """ITSM Adapter supporting Jira, ServiceNow, and generic ticketing systems."""

    def __init__(
        self,
        config: IntegrationConfig,
        declared_capabilities: set[IntegrationCapability] | None = None,
    ) -> None:
        super().__init__(config, declared_capabilities)
        # In-memory ticket store: external_ticket_id -> ITSMTicket
        self._tickets: dict[str, ITSMTicket] = {}
        # Task ID to external_ticket_id reverse index
        self._task_to_ticket: dict[str, str] = {}
        # Alert ID to external_ticket_id reverse index
        self._alert_to_ticket: dict[str, str] = {}

    @property
    def adapter_name(self) -> str:
        return f"{self.config.custom_attributes.get('system_type', 'jira').lower()}_itsm"

    def default_capabilities(self) -> set[IntegrationCapability]:
        return {
            IntegrationCapability.AUTHENTICATE,
            IntegrationCapability.HEALTH_CHECK,
            IntegrationCapability.CREATE_TICKET,
            IntegrationCapability.SYNC_STATUS,
            IntegrationCapability.DISPATCH_EVENT,
        }

    def map_severity_to_priority(self, severity_or_priority: str | TaskPriority) -> str:
        """Translates CloudLens severity or task priority into enterprise ITSM priority."""
        if isinstance(severity_or_priority, TaskPriority):
            return TASK_PRIORITY_TO_ITSM_PRIORITY.get(severity_or_priority, "P3-Medium")
        val = str(severity_or_priority).upper()
        return SEVERITY_TO_ITSM_PRIORITY.get(val, "P3-Medium")

    def build_deep_link(self, entity_type: str, entity_id: str, tenant_id: str) -> str:
        """Constructs canonical web deep link pointing back to CloudLens entity."""
        base_url = self.config.custom_attributes.get("app_base_url", "https://app.cloudlens.io")
        path = "tasks" if entity_type.upper() == "TASK" else "alerts"
        return f"{base_url}/tenants/{tenant_id}/{path}/{entity_id}"

    def create_ticket_from_task(
        self,
        task: RemediationTask,
        *,
        tenant_context: TenantContext,
    ) -> ITSMTicket:
        """Generates an ITSM ticket mirroring a CloudLens remediation task."""

        def _action() -> ITSMTicket:
            sys_type = self.config.custom_attributes.get("system_type", "JIRA").upper()
            prefix = "INC" if "SERVICE" in sys_type or "SNOW" in sys_type else "OPS"
            ext_id = f"{prefix}-{uuid.uuid4().hex[:6].upper()}"

            deep_link = self.build_deep_link("TASK", task.id, tenant_context.tenant_id)
            priority = self.map_severity_to_priority(task.priority)

            evidence_summary = (
                f"Subject: {task.subject_entity.entity_type} ({task.subject_entity.entity_id})\n"
                f"Trigger Source: {task.source.value}\n"
                f"Estimated Saving: ${task.estimated_saving or 0.0:.2f}"
            )

            ticket = ITSMTicket(
                external_system=sys_type,
                external_ticket_id=ext_id,
                cloudlens_entity_type="TASK",
                cloudlens_entity_id=task.id,
                title=task.title,
                description=f"{task.description}\n\nDeep Link: {deep_link}\n\n{evidence_summary}",
                priority=priority,
                status="OPEN",
                evidence_summary=evidence_summary,
                deep_link=deep_link,
            )

            self._tickets[ext_id] = ticket
            self._task_to_ticket[task.id] = ext_id
            task.itsm_ticket_id = ext_id

            logger.info(
                "Created ITSM ticket '%s' for remediation task '%s' [Priority: %s]",
                ext_id,
                task.id,
                priority,
            )
            return ticket

        return self.execute_with_resilience(
            IntegrationCapability.CREATE_TICKET,
            "create_ticket_from_task",
            _action,
        )

    def create_ticket_from_alert(
        self,
        alert: AlertEntity,
        *,
        tenant_context: TenantContext,
    ) -> ITSMTicket:
        """Generates an ITSM ticket mirroring a CloudLens alert."""

        def _action() -> ITSMTicket:
            sys_type = self.config.custom_attributes.get("system_type", "JIRA").upper()
            prefix = "INC" if "SERVICE" in sys_type or "SNOW" in sys_type else "ALERT"
            ext_id = f"{prefix}-{uuid.uuid4().hex[:6].upper()}"

            deep_link = self.build_deep_link("ALERT", alert.id, tenant_context.tenant_id)
            priority = self.map_severity_to_priority(alert.severity.value)

            evidence_summary = (
                f"Summary: {alert.evidence.summary}\n"
                f"Datapoints: {len(alert.evidence.datapoints)}\n"
                f"Observed at: {alert.evidence.observed_at.isoformat()}"
            )

            ticket = ITSMTicket(
                external_system=sys_type,
                external_ticket_id=ext_id,
                cloudlens_entity_type="ALERT",
                cloudlens_entity_id=alert.id,
                title=f"[{alert.severity.value}] {alert.title}",
                description=f"{alert.description}\n\nDeep Link: {deep_link}\n\n{evidence_summary}",
                priority=priority,
                status="OPEN",
                evidence_summary=evidence_summary,
                deep_link=deep_link,
            )

            self._tickets[ext_id] = ticket
            self._alert_to_ticket[alert.id] = ext_id

            logger.info(
                "Created ITSM ticket '%s' for alert '%s' [Priority: %s]",
                ext_id,
                alert.id,
                priority,
            )
            return ticket

        return self.execute_with_resilience(
            IntegrationCapability.CREATE_TICKET,
            "create_ticket_from_alert",
            _action,
        )

    def sync_external_ticket_status(
        self,
        external_ticket_id: str,
        new_external_status: str,
        actor_id: str,
        reason: str | None = None,
        *,
        remediation_service: RemediationService | None = None,
        remediation_task: RemediationTask | None = None,
        tenant_context: TenantContext | None = None,
    ) -> ITSMTicket:
        """Bidirectionally synchronises external ticket status with internal CloudLens task.

        Acceptance requirement:
        - Closing an external ticket closes the linked CloudLens task.
        - Reopening the external ticket reopens the linked CloudLens task.
        - One problem must never become two records that disagree.
        """

        def _action() -> ITSMTicket:
            ticket = self._tickets.get(external_ticket_id)
            if not ticket:
                raise KeyError(f"External ticket '{external_ticket_id}' not found in adapter registry.")

            old_status = ticket.status
            norm_new = new_external_status.upper().strip()
            ticket.status = norm_new
            ticket.last_synced_at = dt.datetime.now(dt.UTC)

            # Synchronize with linked task if provided or found
            target_task = remediation_task
            if not target_task and remediation_service and tenant_context:
                target_task = remediation_service.get_task(
                    ticket.cloudlens_entity_id, tenant_context=tenant_context
                )

            if target_task:
                if norm_new in EXTERNAL_CLOSED_STATUSES:
                    # External ticket is closed -> close internal CloudLens task
                    if target_task.state != TaskState.CLOSED:
                        prev_state = target_task.state
                        target_task.state = TaskState.CLOSED
                        target_task.closure_code = TaskClosureCode.FIXED_AND_VERIFIED
                        target_task.history.append(
                            RemediationHistoryEntry(
                                actor_id=actor_id,
                                action="CLOSED",
                                from_state=prev_state.value if hasattr(prev_state, "value") else str(prev_state),
                                to_state=TaskState.CLOSED.value,
                                reason=reason or f"Synchronised from external ITSM ticket {external_ticket_id}",
                                note=f"Status synchronized via {self.adapter_name}",
                            )
                        )
                        logger.info(
                            "Bidirectional sync: Closing ITSM ticket '%s' closed task '%s'.",
                            external_ticket_id,
                            target_task.id,
                        )
                elif norm_new in EXTERNAL_OPEN_STATUSES:
                    # External ticket is reopened/in progress -> reopen internal task
                    if target_task.state in {TaskState.CLOSED, TaskState.RESOLVED, TaskState.REJECTED}:
                        prev_state = target_task.state
                        target_task.state = TaskState.IN_PROGRESS
                        target_task.history.append(
                            RemediationHistoryEntry(
                                actor_id=actor_id,
                                action="REOPENED",
                                from_state=prev_state.value if hasattr(prev_state, "value") else str(prev_state),
                                to_state=TaskState.IN_PROGRESS.value,
                                reason=reason or f"Synchronised reopening from external ITSM ticket {external_ticket_id}",
                                note=f"Status synchronized via {self.adapter_name}",
                            )
                        )
                        logger.info(
                            "Bidirectional sync: Reopening ITSM ticket '%s' reopened task '%s'.",
                            external_ticket_id,
                            target_task.id,
                        )

            logger.info(
                "ITSM ticket '%s' transitioned status from '%s' to '%s'.",
                external_ticket_id,
                old_status,
                norm_new,
            )
            return ticket

        return self.execute_with_resilience(
            IntegrationCapability.SYNC_STATUS,
            "sync_external_ticket_status",
            _action,
        )

    def get_ticket(self, external_ticket_id: str) -> ITSMTicket | None:
        """Retrieves ticket mirror by external ID."""
        return self._tickets.get(external_ticket_id)

    def get_ticket_for_task(self, task_id: str) -> ITSMTicket | None:
        """Retrieves ticket mirror linked to a specific remediation task."""
        ext_id = self._task_to_ticket.get(task_id)
        return self._tickets.get(ext_id) if ext_id else None
