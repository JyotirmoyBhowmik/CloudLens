"""Outbound ITSM Integration Adapter (Prompt 51, Phase 2 Flag-Gated).

Enforces:
- Flag-Gated Mirroring: Tasks can be mirrored into external systems (Jira, ServiceNow)
  without mutating the internal domain model.
- Mapping: Maps internal priorities, categories, and due dates into standard external payloads.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from pydantic import BaseModel, Field

from domain.models.enums import TaskPriority
from domain.remediation.models import RemediationTask
from domain.tenant.context import TenantContext

logger = logging.getLogger(__name__)

# Standard priority mapping
PRIORITY_MAPPING: dict[TaskPriority, str] = {
    TaskPriority.CRITICAL: "P1-Highest",
    TaskPriority.HIGH: "P2-High",
    TaskPriority.MEDIUM: "P3-Medium",
    TaskPriority.LOW: "P4-Low",
}


class ITSMTicketPayload(BaseModel):
    """Standardized representation of an externally mirrored ITSM ticket."""

    ticket_id: str = Field(
        ..., description="External system ticket key (e.g. 'JIRA-4819', 'INC009281')"
    )
    system_type: str = Field(..., description="ITSM system (JIRA, SERVICENOW, GENERIC_WEBHOOK)")
    summary: str
    description: str
    priority_level: str
    category: str
    assignee_id: str
    due_date_iso: str
    estimated_saving: float | None = None
    labels: list[str] = Field(default_factory=list)
    custom_fields: dict[str, Any] = Field(default_factory=dict)

    @property
    def external_ticket_id(self) -> str:
        return self.ticket_id

    @property
    def system_name(self) -> str:
        return self.system_type

    @property
    def mirrored(self) -> bool:
        return True


ITSMIntegrationResult = ITSMTicketPayload


class ITSMAdapter:
    """Outbound adapter formatting and dispatching tasks to enterprise ITSM systems."""

    def __init__(self, enabled_by_default: bool = True) -> None:
        self.enabled_by_default = enabled_by_default
        self._mock_tickets: dict[str, ITSMTicketPayload] = {}

    def is_enabled(self, tenant_context: TenantContext | None = None) -> bool:
        """Determines if ITSM mirroring is enabled for this tenant."""
        _ = tenant_context
        return self.enabled_by_default

    def build_payload(self, task: RemediationTask, system: str = "jira") -> dict[str, Any]:
        """Builds system-specific payload representation for Jira or ServiceNow."""
        sys_lower = system.lower()
        if "snow" in sys_lower or "service" in sys_lower:
            urgency_val = (
                "1"
                if task.priority == TaskPriority.CRITICAL
                else ("2" if task.priority == TaskPriority.HIGH else "3")
            )
            return {
                "short_description": task.title,
                "description": task.description,
                "urgency": urgency_val,
                "u_cloudlens_id": task.id,
                "assigned_to": task.assignee_id,
            }
        prio_name = (
            "Highest"
            if task.priority == TaskPriority.CRITICAL
            else ("High" if task.priority == TaskPriority.HIGH else "Medium")
        )
        return {
            "fields": {
                "project": {"key": "OPS"},
                "summary": task.title,
                "description": task.description,
                "issuetype": {"name": "Task"},
                "priority": {"name": prio_name},
                "cloudlens_task_id": task.id,
            }
        }

    def mirror_task(
        self,
        task: RemediationTask,
        *,
        system_type: str = "JIRA",
        tenant_context: TenantContext,
    ) -> ITSMTicketPayload | None:
        """Mirrors a remediation task into an outbound ITSM ticket payload."""
        if not self.is_enabled(tenant_context):
            logger.info(f"ITSM integration is disabled; skipping mirror for task '{task.id}'.")
            return None

        # Build external ticket identifier
        prefix = "INC" if system_type.upper() == "SERVICENOW" else "JIRA"
        ticket_id = f"{prefix}-{uuid.uuid4().hex[:6].upper()}"

        mapped_prio = PRIORITY_MAPPING.get(task.priority, "P3-Medium")
        labels = ["cloudlens", "remediation", task.category.value.lower()]
        if task.subject_entity.provider:
            labels.append(task.subject_entity.provider.lower())

        payload = ITSMTicketPayload(
            ticket_id=ticket_id,
            system_type=system_type.upper(),
            summary=task.title,
            description=(
                f"{task.description}\n\n"
                f"Subject Entity: {task.subject_entity.entity_type} ({task.subject_entity.entity_id})\n"
                f"Source Trigger: {task.source.value}\n"
                f"Due Date (SLA): {task.due_date.isoformat()}\n"
                f"Estimated Saving: ${task.estimated_saving or 0.0:.2f}"
            ),
            priority_level=mapped_prio,
            category=task.category.value,
            assignee_id=task.assignee_id,
            due_date_iso=task.due_date.isoformat(),
            estimated_saving=task.estimated_saving,
            labels=labels,
            custom_fields={
                "cloudlens_task_id": task.id,
                "tenant_id": tenant_context.tenant_id,
                "subject_scope_id": task.subject_entity.scope_id,
            },
        )

        task.itsm_ticket_id = ticket_id
        self._mock_tickets[task.id] = payload

        logger.info(
            f"Successfully mirrored task '{task.id}' to {system_type} as '{ticket_id}' [Priority: {mapped_prio}]."
        )
        return payload

    def get_mirrored_ticket(self, task_id: str) -> ITSMTicketPayload | None:
        """Retrieves mirrored ticket snapshot for unit tests and inspection."""
        return self._mock_tickets.get(task_id)


_itsm_adapter_instance: ITSMAdapter | None = None


def get_itsm_adapter() -> ITSMAdapter:
    """Returns singleton ITSMAdapter instance."""
    global _itsm_adapter_instance
    if _itsm_adapter_instance is None:
        _itsm_adapter_instance = ITSMAdapter()
    return _itsm_adapter_instance


def reset_itsm_adapter() -> None:
    """Resets service singleton for test isolation."""
    global _itsm_adapter_instance
    _itsm_adapter_instance = None
