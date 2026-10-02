"""Declarative Task Creation Engine Driven by Master Data Rules (Prompt 51).

Enforces:
- Master-Data-Driven Configuration: Task creation per detection source is governed
  by declarative rules in the master data catalogue, never hard-coded.
- 12 Canonical Detection Sources:
  1. Unowned resource
  2. Missing mandatory tag
  3. Schedule breach with excess cost
  4. Budget breach
  5. Forecast breach
  6. Idle or orphaned resource
  7. Stale connector
  8. Credential expiring
  9. Reconciliation variance
  10. Unknown SKU
  11. Unclassified resource type
  12. Master-data gap
"""

from __future__ import annotations

import datetime as dt
import logging
import uuid
from typing import Any

from domain.models.enums import TaskPriority, TaskSource, TaskState
from domain.remediation.assignment import AssignmentResolver
from domain.remediation.models import (
    RemediationTask,
    SubjectEntity,
    TaskCreationRule,
)
from domain.remediation.repository import RemediationRepository, get_remediation_repository
from domain.tenant.context import TenantContext
from domain.workflows.sla import SLAEngine
from masterdata.service import MasterDataService, get_master_data_service

logger = logging.getLogger(__name__)


class TaskCreationEngine:
    """Evaluates incoming detection events and instantiates remediation tasks per master data rules."""

    def __init__(
        self,
        repository: RemediationRepository | None = None,
        resolver: AssignmentResolver | None = None,
        sla_engine: SLAEngine | None = None,
        master_data_service: MasterDataService | None = None,
    ) -> None:
        self.repository = repository or get_remediation_repository()
        self.master_data_service = master_data_service or get_master_data_service()
        self.resolver = resolver or AssignmentResolver(self.master_data_service)
        self.sla_engine = sla_engine or SLAEngine(self.master_data_service)

    def create_from_source(
        self,
        source: TaskSource,
        subject: SubjectEntity,
        evidence: dict[str, Any],
        payload: dict[str, Any] | None = None,
        *,
        tenant_context: TenantContext,
    ) -> RemediationTask | None:
        """Instantiates and assigns a remediation task based on master data configuration."""
        data = payload or {}

        # 1. Lookup governing master data creation rule
        rule = self._lookup_creation_rule(source, tenant_context=tenant_context)
        if not rule or not rule.enabled:
            logger.info(
                f"Task creation for source '{source.value}' is disabled or not configured in master data."
            )
            return None

        # 2. Extract or calculate estimated financial impact / saving
        estimated_saving = None
        if rule.estimated_saving_formula:
            field_key = rule.estimated_saving_formula
            val = data.get(field_key) or evidence.get(field_key)
            if val is not None:
                try:
                    estimated_saving = float(val)
                except (ValueError, TypeError):
                    pass

        if estimated_saving is None:
            raw_cost = (
                data.get("excess_cost")
                or data.get("estimated_saving")
                or evidence.get("excess_cost")
            )
            if raw_cost is not None:
                try:
                    estimated_saving = float(raw_cost)
                except (ValueError, TypeError):
                    pass

        # 3. Resolve assignee using ownership hierarchy
        tags = data.get("tags") or evidence.get("tags")
        scope_owner = data.get("scope_owner_id") or evidence.get("scope_owner_id")
        app_owner = data.get("app_owner_id") or evidence.get("app_owner_id")

        assignee_id, assignee_type, rule_used = self.resolver.resolve(
            subject=subject,
            resource=data.get("resource"),
            tags=tags,
            scope_owner_id=scope_owner,
            app_owner_id=app_owner,
            fallback_queue_id=data.get("fallback_queue_id"),
        )

        # 4. Compute working-hours SLA due date
        now = dt.datetime.now(dt.UTC)
        sla_hours = int(data.get("sla_working_hours") or rule.default_sla_hours)
        due_date = self.sla_engine.calculate_due_date(
            start_time=now,
            sla_working_hours=sla_hours,
            tenant_id=tenant_context.tenant_id,
        )

        priority = data.get("priority") or rule.default_priority
        if isinstance(priority, str):
            priority = TaskPriority(priority)

        # 5. Build task headline & narrative
        default_title = f"Remediate {rule.category.value.replace('_', ' ').title()}: {subject.entity_name or subject.entity_id}"
        title = str(data.get("title") or default_title)

        default_desc = (
            f"Automated detection from {source.value} identified a {rule.category.value} condition "
            f"on {subject.entity_type} '{subject.entity_id}'. Immediate remediation required."
        )
        description = str(data.get("description") or default_desc)

        task_id = f"rem-task-{tenant_context.tenant_id[:8]}-{uuid.uuid4().hex[:8]}"

        task = RemediationTask(
            id=task_id,
            tenant_id=tenant_context.tenant_id,
            source=source,
            subject_entity=subject,
            title=title,
            description=description,
            evidence_linkage=evidence,
            assignee_id=assignee_id,
            assignee_type=assignee_type,
            assigning_actor="SYSTEM_CREATION_ENGINE",
            assignment_rule=rule_used,
            priority=priority,
            due_date=due_date,
            sla_working_hours=float(sla_hours),
            estimated_saving=estimated_saving,
            state=TaskState.OPEN,
            category=rule.category,
            alert_id=data.get("alert_id"),
            finding_id=data.get("finding_id"),
        )

        task.add_history(
            action="CREATED",
            actor_id="system-task-engine",
            from_state=None,
            to_state=TaskState.OPEN.value,
            note=f"Task automatically created from source '{source.value}' with {rule_used.value} assignment.",
            details={"sla_hours": sla_hours, "estimated_saving": estimated_saving},
        )

        # If assignee resolved, advance to ASSIGNED state
        task.state = TaskState.ASSIGNED
        task.add_history(
            action="ASSIGNED",
            actor_id="system-assignment-engine",
            from_state=TaskState.OPEN.value,
            to_state=TaskState.ASSIGNED.value,
            note=f"Assigned to {assignee_type} '{assignee_id}' via rule '{rule_used.value}'.",
        )

        saved = self.repository.save(task, tenant_context=tenant_context)
        logger.info(
            f"Created remediation task '{saved.id}' for entity '{subject.entity_id}' "
            f"[Source: {source.value}, Assignee: {assignee_id}, SLA: {sla_hours}h]."
        )
        return saved

    def _lookup_creation_rule(
        self, source: TaskSource, *, tenant_context: TenantContext
    ) -> TaskCreationRule | None:
        """Retrieves creation rule from repository or master data."""
        rule = self.repository.get_creation_rule(source.value, tenant_context=tenant_context)
        if rule:
            return rule

        # Fallback to master data catalogue
        try:
            records = self.master_data_service.list_records("TASK_CREATION_RULE")
            for rec in records:
                attrs = rec.attributes or {}
                if attrs.get("source_code") == source.value:
                    return TaskCreationRule(
                        code=rec.code,
                        source_code=source,
                        enabled=attrs.get("enabled", True),
                        category=attrs.get("category", "CUSTOM"),
                        default_priority=attrs.get("default_priority", "MEDIUM"),
                        estimated_saving_formula=attrs.get("estimated_saving_formula"),
                        auto_assign=attrs.get("auto_assign", True),
                        default_sla_hours=attrs.get("default_sla_hours", 48),
                    )
        except Exception:
            pass
        return None
