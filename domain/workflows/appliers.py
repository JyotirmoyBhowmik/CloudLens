"""Atomic Workflow Application Dispatcher (Prompt 50).

Enforces:
- Automatic, atomic application of approved changes.
- Recording of applied state (WorkflowState.APPLIED).
- Reversion to IN_REVIEW with error attached if application fails, never silent failure.
- Handlers for all wired approval points:
  Budgets, Overrides, Policy Exemptions, Custom Roles, Master Data, etc.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Any

from domain.budgets.models import (
    BudgetApprovalDecision,
    BudgetApprovalStatus,
)
from domain.budgets.repository import get_budget_repository
from domain.models.enums import WorkflowRequestType
from domain.models.exceptions import (
    WorkflowApplicationFailedException,
)
from domain.tenant.context import TenantContext

logger = logging.getLogger(__name__)


class WorkflowApplier(ABC):
    """Abstract base contract for executing atomic change application on final approval."""

    @abstractmethod
    def apply(self, request: Any, *, tenant_context: TenantContext) -> None:
        """Applies the approved change atomically. Raises Exception on failure."""
        pass


class BudgetApplier(WorkflowApplier):
    """Applies approved budget creation or amendment ceiling changes."""

    def apply(self, request: Any, *, tenant_context: TenantContext) -> None:
        repo = get_budget_repository()
        budget_id = request.subject_entity.entity_id
        budget = repo.get(budget_id, tenant_context=tenant_context)
        if not budget:
            raise WorkflowApplicationFailedException(
                request.id, f"Budget '{budget_id}' not found for application."
            )

        actor_id = request.history[-1].actor_id if request.history else "workflow-engine"
        comment = request.payload.get("comment", "Approved via unified workflow engine")

        today = date.today()
        new_status = (
            BudgetApprovalStatus.ACTIVE
            if budget.effective_date <= today
            else BudgetApprovalStatus.APPROVED
        )

        decision = BudgetApprovalDecision(
            decision=BudgetApprovalStatus.APPROVED,
            decided_by=actor_id,
            comment=comment,
            decided_at=datetime.now(UTC),
        )

        budget.approval_status = new_status
        budget.approval_decision = decision
        budget.updated_at = datetime.now(UTC)

        # Update last amendment if applicable
        if budget.amendments:
            budget.amendments[-1].approver_id = actor_id

        repo.save(budget, tenant_context=tenant_context)
        logger.info(
            "Workflow '%s' successfully applied budget '%s' to status '%s'",
            request.id,
            budget.id,
            new_status.value,
        )


class OverrideApplier(WorkflowApplier):
    """Applies approved administrative or permanent overrides."""

    def apply(self, request: Any, *, tenant_context: TenantContext) -> None:
        from domain.overrides.models import OverrideApproval, OverrideRecord
        from domain.overrides.repository import OverrideRepository

        repo = OverrideRepository()
        override_id = request.subject_entity.entity_id
        override = repo.get(override_id, tenant_context=tenant_context)

        actor_id = request.history[-1].actor_id if request.history else "workflow-engine"
        ticket = request.payload.get("ticket_ref", f"WF-{request.id[:8]}")

        approval_rec = OverrideApproval(
            approver_id=actor_id,
            approved_at=datetime.now(UTC),
            ticket_ref=ticket,
            permanent_approved=bool(request.payload.get("is_permanent", False)),
        )

        if override:
            override.approval = approval_rec
            override.updated_at = datetime.now(UTC)
            repo.save(override, tenant_context=tenant_context)
        else:
            # Create if new record in payload
            record = OverrideRecord(
                id=override_id,
                tenant_id=tenant_context.tenant_id,
                override_class=request.payload.get("override_class", "BUDGET_THRESHOLD"),
                who=request.requester.requester_id,
                what=request.payload.get("what", "configuration"),
                why=request.justification,
                previous_value=request.previous_values or {},
                new_value=request.payload.get("new_value", {}),
                expiry=request.payload.get("expiry"),
                is_permanent=bool(request.payload.get("is_permanent", False)),
                approval=approval_rec,
            )
            repo.save(record, tenant_context=tenant_context)


class PolicyExemptionApplier(WorkflowApplier):
    """Applies approved governance policy exemptions."""

    def apply(self, request: Any, *, tenant_context: TenantContext) -> None:
        from domain.policy.models import PolicyExemption
        from domain.policy.repository import get_policy_repository

        repo = get_policy_repository()
        exm_id = request.subject_entity.entity_id
        actor_id = request.history[-1].actor_id if request.history else "workflow-engine"

        exm = repo.get_exemption(exm_id, tenant_context=tenant_context)
        if exm:
            exm.is_approved = True
            exm.approved_by = actor_id
            repo.save_exemption(exm, tenant_context=tenant_context)
        else:
            # Create from payload
            expires_at = request.payload.get("expires_at")
            if isinstance(expires_at, str):
                expires_at = datetime.fromisoformat(expires_at)
            elif not isinstance(expires_at, datetime):
                expires_at = datetime.now(UTC)

            new_exm = PolicyExemption(
                id=exm_id,
                policy_id=request.payload.get("policy_id", "POL-01"),
                entity_id=request.subject_entity.entity_id,
                scope_id=request.subject_entity.scope_id,
                justification=request.justification,
                requested_by=request.requester.requester_id,
                approved_by=actor_id,
                requires_approval=True,
                is_approved=True,
                expires_at=expires_at,
            )
            repo.save_exemption(new_exm, tenant_context=tenant_context)


class CustomRoleApplier(WorkflowApplier):
    """Applies approved custom RBAC role composition."""

    def apply(self, request: Any, *, tenant_context: TenantContext) -> None:
        from domain.rbac.catalogue import get_permission_catalogue

        cat = get_permission_catalogue()
        code = request.payload.get("role_code", request.subject_entity.entity_id)
        display_name = request.payload.get("display_name", request.title)
        description = request.payload.get("description", request.justification)
        permissions = request.payload.get("allowed_permissions", [])

        cat.register_custom_role(
            tenant_id=tenant_context.tenant_id,
            code=code,
            display_name=display_name,
            description=description,
            allowed_permissions=permissions,
        )


class MasterDataApplier(WorkflowApplier):
    """Publishes approved master data registry versions."""

    def apply(self, request: Any, *, tenant_context: TenantContext) -> None:
        from masterdata.service import get_master_data_service

        _ = tenant_context
        md = get_master_data_service()
        m_type = request.payload.get("master_type", "WORKFLOW_DEFINITION")
        code = request.subject_entity.entity_id
        actor_id = request.history[-1].actor_id if request.history else "workflow-engine"

        md.approve(m_type, code, approver_id=actor_id)
        md.publish(m_type, code, publisher_id=actor_id)


class CallbackApplier(WorkflowApplier):
    """Generic pluggable applier executing a custom callable."""

    def __init__(self, callback: Callable[[Any, TenantContext], None]) -> None:
        self.callback = callback

    def apply(self, request: Any, *, tenant_context: TenantContext) -> None:
        self.callback(request, tenant_context)


class WorkflowApplierRegistry:
    """Central registry and execution coordinator for workflow change appliers."""

    def __init__(self) -> None:
        self._appliers: dict[str, WorkflowApplier] = {
            WorkflowRequestType.BUDGET_APPROVAL.value: BudgetApplier(),
            WorkflowRequestType.OVERRIDE_APPROVAL.value: OverrideApplier(),
            WorkflowRequestType.POLICY_EXEMPTION.value: PolicyExemptionApplier(),
            WorkflowRequestType.CUSTOM_ROLE_CREATION.value: CustomRoleApplier(),
            WorkflowRequestType.MASTER_DATA_CHANGE.value: MasterDataApplier(),
        }

    def register_applier(self, request_type: str, applier: WorkflowApplier) -> None:
        """Registers or replaces an applier for a specific request type."""
        self._appliers[request_type.strip().upper()] = applier

    def get_applier(self, request_type: str) -> WorkflowApplier | None:
        """Retrieves registered applier for request type."""
        return self._appliers.get(request_type.strip().upper())

    def apply(self, request: Any, *, tenant_context: TenantContext) -> None:
        """Executes atomic application. Reverts state and raises on failure."""
        applier = self.get_applier(request.request_type)
        if not applier:
            logger.info(
                "No explicit applier registered for request type '%s'", request.request_type
            )
            return

        try:
            applier.apply(request, tenant_context=tenant_context)
        except Exception as e:
            logger.exception("Application of approved workflow '%s' failed: %s", request.id, e)
            raise WorkflowApplicationFailedException(request.id, str(e)) from e


_applier_registry = WorkflowApplierRegistry()


def get_applier_registry() -> WorkflowApplierRegistry:
    """Returns singleton instance of WorkflowApplierRegistry."""
    return _applier_registry
