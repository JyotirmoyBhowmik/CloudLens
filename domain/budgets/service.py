"""Budget Management Domain Service Facade (Prompt 28).

Enforces:
- Prompt 28: Budgets at all seventeen scope types with full field set.
- Prompt 28: Support monthly, quarterly, annual, fiscal-year and custom periods aligned to tenant fiscal calendar.
- Prompt 28: Evaluation producing actual utilisation, forecast utilisation, variance and state on every cycle.
- Prompt 28: Overlap and over-allocation detection (child vs parent, unallocated remainder, logical vs native overlap).
- Prompt 28: Approval workflow: budgets above approval limit enter PENDING_APPROVAL and require formal approval decision.
- Prompt 28: Budget templates per scope type providing default period, thresholds and recipients.
- Prompt 28: Provider-native budgets imported read-only for comparison, visually and structurally distinct.
- Negative constraint: Do NOT silently prevent logical and native budgets from overlapping; flag and explain instead.
- Negative constraint: Do NOT evaluate a budget before its effective date.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, date, datetime
from typing import Any

from domain.audit.service import AuditEventCreate, get_audit_service
from domain.budgets.calendar import BudgetPeriodCalendar
from domain.budgets.evaluator import BudgetEvaluator
from domain.budgets.models import (
    BudgetAmendment,
    BudgetAmendRequest,
    BudgetApprovalDecision,
    BudgetApprovalStatus,
    BudgetApproveRequest,
    BudgetCreateRequest,
    BudgetEntity,
    BudgetEvaluationResult,
    BudgetHierarchySummary,
    BudgetOverlapWarning,
    BudgetRejectRequest,
    BudgetSourceType,
    BudgetTemplate,
    NativeBudgetImportRequest,
)
from domain.budgets.overlap import BudgetOverlapDetector
from domain.budgets.repository import BudgetRepository, get_budget_repository
from domain.budgets.templates import get_template_for_scope, list_all_budget_templates
from domain.models.base import ProvenanceRecord
from domain.models.enums import (
    AuditEventType,
    BudgetScopeType,
    CloudProvider,
    OriginType,
)
from domain.models.exceptions import (
    BudgetApprovalNotAllowedException,
    BudgetNotFoundException,
    BudgetPendingApprovalException,
    InvalidBudgetAmountException,
    NativeBudgetReadOnlyException,
)
from domain.tenant.context import TenantContext
from masterdata.service import MasterDataService, get_master_data_service

logger = logging.getLogger(__name__)

DEFAULT_APPROVAL_LIMIT: float = 10000.0  # Budgets > $10,000 require approval


class BudgetService:
    """Enterprise domain service managing lifecycle, approval, overlap analysis,

    and financial evaluation of cloud budgets.
    """

    def __init__(
        self,
        repository: BudgetRepository | None = None,
        evaluator: BudgetEvaluator | None = None,
        overlap_detector: BudgetOverlapDetector | None = None,
        calendar: BudgetPeriodCalendar | None = None,
        master_service: MasterDataService | None = None,
        approval_threshold: float = DEFAULT_APPROVAL_LIMIT,
    ) -> None:
        self.repository = repository or get_budget_repository()
        self.master_service = master_service or get_master_data_service()
        self.calendar = calendar or BudgetPeriodCalendar(self.master_service)
        self.evaluator = evaluator or BudgetEvaluator(self.calendar)
        self.overlap_detector = overlap_detector or BudgetOverlapDetector()
        self.approval_threshold = approval_threshold

    # ==========================================================================
    # 1. Budget Creation & Overlap Analysis
    # ==========================================================================

    def create_budget(
        self,
        request: BudgetCreateRequest,
        *,
        tenant_context: TenantContext,
    ) -> tuple[BudgetEntity, list[BudgetOverlapWarning]]:
        """Creates a new CloudLens budget.

        If amount exceeds the approval threshold, the budget enters PENDING_APPROVAL.
        Detects and returns all overlap warnings (same scope, child over-allocation, logical vs native).
        """
        today = date.today()

        if request.amount <= 0.0:
            raise InvalidBudgetAmountException(request.amount)

        # Check approval requirement based on configurable threshold
        if request.amount > self.approval_threshold:
            status = BudgetApprovalStatus.PENDING_APPROVAL
        else:
            status = (
                BudgetApprovalStatus.ACTIVE
                if request.effective_date <= today
                else BudgetApprovalStatus.APPROVED
            )

        budget_id = f"bgt-{tenant_context.tenant_id[:8]}-{request.scope_type.value.lower()}-{uuid.uuid4().hex[:8]}"

        entity = BudgetEntity(
            id=budget_id,
            tenant_id=tenant_context.tenant_id,
            name=request.name,
            scope_type=request.scope_type,
            scope_id=request.scope_id,
            parent_budget_id=request.parent_budget_id,
            period=request.period,
            amount=request.amount,
            currency=request.currency.upper(),
            thresholds=request.thresholds,
            alert_recipients=request.alert_recipients,
            escalation=request.escalation,
            forecast_threshold=request.forecast_threshold,
            effective_date=request.effective_date,
            expiry_date=request.expiry_date,
            owner=request.owner,
            approval_status=status,
            rollover_policy=request.rollover_policy,
            notes=request.notes,
            budget_source=BudgetSourceType.CLOUDLENS_LOGICAL,
            is_native=False,
            is_read_only=False,
            source_provenance=ProvenanceRecord(
                source_system="cloudlens-budget-service",
                origin_type=OriginType.CURATED,
            ),
        )

        saved = self.repository.save(entity, tenant_context=tenant_context)

        # Detect overlaps across existing tenant budgets
        all_budgets = self.repository.list_all(tenant_context=tenant_context)
        warnings = self.overlap_detector.detect_overlaps(saved, all_budgets)

        # Record audit event
        self._record_audit_event(
            event_type=AuditEventType.BUDGET_CREATED,
            actor_id=tenant_context.actor_id or "user",
            action="BUDGET_CREATED",
            resource_id=saved.id,
            details={
                "name": saved.name,
                "scope_type": saved.scope_type.value,
                "scope_id": saved.scope_id,
                "amount": saved.amount,
                "approval_status": saved.approval_status.value,
                "overlap_warnings_count": len(warnings),
            },
            tenant_context=tenant_context,
        )

        return saved, warnings

    # ==========================================================================
    # 2. Budget Amendment & Audit Trail
    # ==========================================================================

    def amend_budget(
        self,
        budget_id: str,
        request: BudgetAmendRequest,
        *,
        tenant_context: TenantContext,
    ) -> BudgetEntity:
        """Amends a budget allocation ceiling, tracking full amendment history.

        If new amount exceeds approval limit, the budget transitions to PENDING_APPROVAL.
        """
        budget = self.get_budget(budget_id, tenant_context=tenant_context)
        if budget.is_read_only or budget.is_native:
            raise NativeBudgetReadOnlyException(
                budget_id=budget.id,
                provider=budget.native_provider.value if budget.native_provider else None,
            )

        if request.new_amount <= 0.0:
            raise InvalidBudgetAmountException(request.new_amount)

        previous_amount = budget.amount
        actor_id = tenant_context.actor_id or "admin"

        amendment = BudgetAmendment(
            previous_amount=previous_amount,
            new_amount=request.new_amount,
            actor_id=actor_id,
            reason=request.reason,
            timestamp=datetime.now(UTC),
        )

        budget.amendments.append(amendment)
        budget.amount = request.new_amount
        budget.updated_at = datetime.now(UTC)

        # If amended amount exceeds threshold, require approval
        if request.new_amount > self.approval_threshold:
            budget.approval_status = BudgetApprovalStatus.PENDING_APPROVAL
        elif budget.approval_status == BudgetApprovalStatus.PENDING_APPROVAL:
            # Reverted to below threshold
            budget.approval_status = (
                BudgetApprovalStatus.ACTIVE
                if budget.effective_date <= date.today()
                else BudgetApprovalStatus.APPROVED
            )

        saved = self.repository.save(budget, tenant_context=tenant_context)

        self._record_audit_event(
            event_type=AuditEventType.BUDGET_AMENDED,
            actor_id=actor_id,
            action="BUDGET_AMENDED",
            resource_id=saved.id,
            details={
                "previous_amount": previous_amount,
                "new_amount": request.new_amount,
                "reason": request.reason,
                "approval_status": saved.approval_status.value,
            },
            tenant_context=tenant_context,
        )

        return saved

    # ==========================================================================
    # 3. Approval Workflow (Approval & Rejection)
    # ==========================================================================

    def approve_budget(
        self,
        budget_id: str,
        request: BudgetApproveRequest,
        *,
        tenant_context: TenantContext,
    ) -> BudgetEntity:
        """Approves a budget in PENDING_APPROVAL state, recording approver and comment."""
        budget = self.get_budget(budget_id, tenant_context=tenant_context)
        if budget.is_read_only or budget.is_native:
            raise NativeBudgetReadOnlyException(
                budget_id=budget.id,
                provider=budget.native_provider.value if budget.native_provider else None,
            )

        if budget.approval_status != BudgetApprovalStatus.PENDING_APPROVAL:
            raise BudgetApprovalNotAllowedException(
                f"Budget '{budget_id}' is in status '{budget.approval_status.value}' and does not require approval."
            )

        actor_id = tenant_context.actor_id or "approver"
        decision = BudgetApprovalDecision(
            decision=BudgetApprovalStatus.APPROVED,
            decided_by=actor_id,
            comment=request.comment,
            decided_at=datetime.now(UTC),
        )

        budget.approval_decision = decision
        budget.approval_status = (
            BudgetApprovalStatus.ACTIVE
            if budget.effective_date <= date.today()
            else BudgetApprovalStatus.APPROVED
        )
        budget.updated_at = datetime.now(UTC)

        # Update last amendment with approver_id if applicable
        if budget.amendments:
            budget.amendments[-1].approver_id = actor_id

        saved = self.repository.save(budget, tenant_context=tenant_context)

        self._record_audit_event(
            event_type=AuditEventType.BUDGET_APPROVED,
            actor_id=actor_id,
            action="BUDGET_APPROVED",
            resource_id=saved.id,
            details={
                "approved_by": actor_id,
                "comment": request.comment,
                "amount": saved.amount,
                "new_status": saved.approval_status.value,
            },
            tenant_context=tenant_context,
        )

        return saved

    def reject_budget(
        self,
        budget_id: str,
        request: BudgetRejectRequest,
        *,
        tenant_context: TenantContext,
    ) -> BudgetEntity:
        """Rejects a budget in PENDING_APPROVAL state."""
        budget = self.get_budget(budget_id, tenant_context=tenant_context)
        if budget.is_read_only or budget.is_native:
            raise NativeBudgetReadOnlyException(
                budget_id=budget.id,
                provider=budget.native_provider.value if budget.native_provider else None,
            )

        if budget.approval_status != BudgetApprovalStatus.PENDING_APPROVAL:
            raise BudgetApprovalNotAllowedException(
                f"Budget '{budget_id}' is in status '{budget.approval_status.value}' and does not require approval."
            )

        actor_id = tenant_context.actor_id or "approver"
        decision = BudgetApprovalDecision(
            decision=BudgetApprovalStatus.REJECTED,
            decided_by=actor_id,
            comment=request.comment,
            decided_at=datetime.now(UTC),
        )

        budget.approval_decision = decision
        budget.approval_status = BudgetApprovalStatus.REJECTED
        budget.updated_at = datetime.now(UTC)

        saved = self.repository.save(budget, tenant_context=tenant_context)

        self._record_audit_event(
            event_type=AuditEventType.BUDGET_REJECTED,
            actor_id=actor_id,
            action="BUDGET_REJECTED",
            resource_id=saved.id,
            details={
                "rejected_by": actor_id,
                "comment": request.comment,
                "amount": saved.amount,
            },
            tenant_context=tenant_context,
        )

        return saved

    # ==========================================================================
    # 4. Provider-Native Read-Only Budget Import
    # ==========================================================================

    def import_native_budget(
        self,
        request: NativeBudgetImportRequest,
        *,
        tenant_context: TenantContext,
    ) -> BudgetEntity:
        """Imports a provider-native budget as read-only for comparison with CloudLens budgets.
        Native budgets are structurally and visually distinct and immutable.
        """
        provider_cloud = CloudProvider(request.provider.value.lower())
        budget_id = f"native-{provider_cloud.value.lower()}-{request.native_budget_id}"

        entity = BudgetEntity(
            id=budget_id,
            tenant_id=tenant_context.tenant_id,
            name=f"[{provider_cloud.value.upper()} Native] {request.native_budget_name}",
            scope_type=request.scope_type,
            scope_id=request.scope_id,
            period=request.period,
            amount=request.amount,
            currency=request.currency.upper(),
            effective_date=request.effective_date,
            expiry_date=request.expiry_date,
            owner=request.owner,
            approval_status=BudgetApprovalStatus.ACTIVE,  # Native budgets are pre-active in cloud
            notes=request.notes,
            budget_source=BudgetSourceType.PROVIDER_NATIVE,
            is_native=True,
            is_read_only=True,
            native_provider=provider_cloud,
            native_budget_id=request.native_budget_id,
            native_budget_name=request.native_budget_name,
            source_provenance=ProvenanceRecord(
                source_system=f"{provider_cloud.value.lower()}-native-budget-sync",
                origin_type=OriginType.DISCOVERED,
            ),
        )

        saved = self.repository.save(entity, tenant_context=tenant_context)

        self._record_audit_event(
            event_type=AuditEventType.BUDGET_NATIVE_IMPORTED,
            actor_id=tenant_context.actor_id or "provider-sync",
            action="BUDGET_NATIVE_IMPORTED",
            resource_id=saved.id,
            details={
                "provider": provider_cloud.value,
                "native_budget_id": request.native_budget_id,
                "native_budget_name": request.native_budget_name,
                "amount": request.amount,
            },
            tenant_context=tenant_context,
        )

        return saved

    # ==========================================================================
    # 5. Financial Evaluation
    # ==========================================================================

    def evaluate_budget(
        self,
        budget_id: str,
        *,
        as_of: date | None = None,
        actual_spend: float | None = None,
        tenant_context: TenantContext,
    ) -> BudgetEvaluationResult:
        """Evaluates actual utilisation, forecast, variance, and threshold state.

        Negative Constraint: Never evaluates a budget before its effective date.
        """
        budget = self.get_budget(budget_id, tenant_context=tenant_context)

        # Enforce approval gate: Budgets in PENDING_APPROVAL cannot be active
        if budget.approval_status == BudgetApprovalStatus.PENDING_APPROVAL:
            raise BudgetPendingApprovalException(
                budget_id=budget.id,
                amount=budget.amount,
                threshold=self.approval_threshold,
            )

        result = self.evaluator.evaluate(
            budget,
            as_of=as_of,
            actual_spend=actual_spend,
        )

        self._record_audit_event(
            event_type=AuditEventType.BUDGET_EVALUATED,
            actor_id=tenant_context.actor_id or "evaluator",
            action="BUDGET_EVALUATED",
            resource_id=budget.id,
            details={
                "actual_spend": result.actual_spend,
                "actual_utilisation": result.actual_utilisation,
                "state": result.state.value,
                "is_effective": result.is_effective,
            },
            tenant_context=tenant_context,
        )

        return result

    # ==========================================================================
    # 6. Hierarchy, Overlap & Template Analysis
    # ==========================================================================

    def get_budget_hierarchy(
        self,
        budget_id: str,
        *,
        tenant_context: TenantContext,
    ) -> BudgetHierarchySummary:
        """Returns hierarchical child budget rollup and unallocated remainder."""
        parent = self.get_budget(budget_id, tenant_context=tenant_context)
        children = self.repository.get_children(budget_id, tenant_context=tenant_context)
        return self.overlap_detector.analyze_hierarchy(parent, children)

    def get_budget_overlaps(
        self,
        budget_id: str,
        *,
        tenant_context: TenantContext,
    ) -> list[BudgetOverlapWarning]:
        """Returns detected overlaps and dual-accounting explanations for this budget."""
        budget = self.get_budget(budget_id, tenant_context=tenant_context)
        all_budgets = self.repository.list_all(tenant_context=tenant_context)
        return self.overlap_detector.detect_overlaps(budget, all_budgets)

    def get_templates(self) -> list[BudgetTemplate]:
        """Returns pre-configured templates for all seventeen scope types."""
        return list_all_budget_templates()

    def get_template_for_scope(self, scope_type: BudgetScopeType) -> BudgetTemplate:
        """Retrieves default period, thresholds, and recipients for a specific scope type."""
        return get_template_for_scope(scope_type)

    # ==========================================================================
    # 7. Queries & Deletion
    # ==========================================================================

    def get_budget(self, budget_id: str, *, tenant_context: TenantContext) -> BudgetEntity:
        """Retrieves a budget entity, raising BudgetNotFoundException if absent."""
        budget = self.repository.get(budget_id, tenant_context=tenant_context)
        if not budget:
            raise BudgetNotFoundException(budget_id)
        return budget

    def list_budgets(
        self,
        *,
        tenant_context: TenantContext,
        scope_type: BudgetScopeType | None = None,
        scope_id: str | None = None,
        approval_status: BudgetApprovalStatus | None = None,
        is_native: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[BudgetEntity]:
        """Lists budgets with multi-dimensional filtering."""
        filter_params: dict[str, Any] = {}
        if scope_type:
            filter_params["scope_type"] = scope_type
        if scope_id:
            filter_params["scope_id"] = scope_id
        if approval_status:
            filter_params["approval_status"] = approval_status
        if is_native is not None:
            filter_params["is_native"] = is_native

        return self.repository.list(
            tenant_context=tenant_context,
            filter_params=filter_params,
            limit=limit,
            offset=offset,
        )

    def delete_budget(self, budget_id: str, *, tenant_context: TenantContext) -> bool:
        """Deletes a budget. Native budgets cannot be deleted."""
        budget = self.get_budget(budget_id, tenant_context=tenant_context)
        if budget.is_native or budget.is_read_only:
            raise NativeBudgetReadOnlyException(
                budget_id=budget.id,
                provider=budget.native_provider.value if budget.native_provider else None,
            )
        return self.repository.delete(budget_id, tenant_context=tenant_context)

    # ==========================================================================
    # 8. Audit Helper
    # ==========================================================================

    def _record_audit_event(
        self,
        *,
        event_type: AuditEventType,
        actor_id: str,
        action: str,
        resource_id: str,
        details: dict[str, Any],
        tenant_context: TenantContext,
    ) -> None:
        """Appends structured audit log event."""
        try:
            audit_svc = get_audit_service()
            audit_svc.append_event(
                tenant_context=tenant_context,
                event_in=AuditEventCreate(
                    event_type=event_type,
                    actor_id=actor_id,
                    action=action,
                    resource_id=resource_id,
                    resource_type="BUDGET",
                    details=details,
                ),
            )
        except Exception as e:
            logger.warning("Failed to append budget audit event: %s", e)


# Singleton service instance
_budget_service: BudgetService | None = None


def get_budget_service() -> BudgetService:
    """Returns singleton BudgetService instance."""
    global _budget_service
    if _budget_service is None:
        _budget_service = BudgetService()
    return _budget_service


def reset_budget_service() -> None:
    """Resets singleton BudgetService instance for testing."""
    global _budget_service
    _budget_service = None
