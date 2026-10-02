"""Budget Domain Models (Prompt 28).

Enforces:
- Prompt 28: Budgets at all seventeen scope types:
  organisation, provider, management group, subscription, AWS OU, AWS account,
  GCP folder, GCP project, OCI compartment, resource group, application,
  environment, service, resource, cost centre, business unit and project.
- Prompt 28: Full field set: name, scope (scope_type, scope_id), period, amount,
  currency, thresholds, alert recipients, escalation, forecast threshold,
  effective date, expiry date, owner, approval status, rollover policy, notes.
- Prompt 28: Approval workflow: budgets above configurable threshold enter PENDING_APPROVAL.
- Prompt 28: Overlap, over-allocation and double-counting detection.
- Prompt 28: Read-only provider-native budget imports visually and structurally distinct.
- Negative constraint: Do NOT silently prevent logical and native budgets from overlapping; flag and explain instead.
- Negative constraint: Do NOT evaluate a budget before its effective date.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any

from pydantic import BaseModel, Field, computed_field, field_validator, model_validator

from domain.models.base import CanonicalEntity
from domain.models.enums import (
    BudgetApprovalStatus,
    BudgetPeriod,
    BudgetRolloverPolicy,
    BudgetScopeType,
    BudgetSourceType,
    CloudProvider,
    ProviderType,
)
from domain.models.exceptions import (
    InvalidBudgetAmountException,
    InvalidBudgetDatesException,
)
from domain.thresholds.models import ThresholdState


class BudgetThreshold(BaseModel):
    """Notification and alerting trigger line for budget utilisation."""

    percentage: float = Field(
        ...,
        gt=0.0,
        description="Percentage of total allocated budget (e.g. 50.0, 80.0, 100.0, 120.0)",
    )
    amount: float | None = Field(
        default=None,
        description="Optional absolute spend amount corresponding to this threshold",
    )
    band: str = Field(
        default="WARNING",
        description="Alert severity classification: INFO, WARNING, HIGH, CRITICAL",
    )
    recipients: list[str] = Field(
        default_factory=list,
        description="Notification routing destinations (emails, slack webhooks, user IDs)",
    )


class BudgetEscalation(BaseModel):
    """Escalation routing policy when budget breaches remain unacknowledged."""

    escalate_to: str = Field(
        ...,
        description="Target escalated manager, distribution list, or FinOps lead",
    )
    after_hours: int = Field(
        default=24,
        ge=1,
        description="Elapsed hours before escalation triggers",
    )
    threshold_pct: float = Field(
        default=100.0,
        description="Threshold percentage at or above which escalation applies",
    )


class BudgetAmendment(BaseModel):
    """Immutable audit record of budget adjustments (Prompt 28 & CST-018 / AC-033)."""

    id: str = Field(
        default_factory=lambda: f"bgt-amend-{uuid.uuid4().hex[:8]}",
        description="Amendment record ID",
    )
    previous_amount: float = Field(
        ...,
        description="Pre-amendment budget ceiling",
    )
    new_amount: float = Field(
        ...,
        description="Post-amendment budget ceiling",
    )
    actor_id: str = Field(
        ...,
        description="Identity of the requester who initiated the amendment",
    )
    approver_id: str | None = Field(
        default=None,
        description="Identity of approving manager if required",
    )
    reason: str = Field(
        ...,
        description="Mandatory business rationale for amendment",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp when amendment occurred",
    )


class BudgetApprovalDecision(BaseModel):
    """Formal workflow sign-off decision recorded for budget activation."""

    decision: BudgetApprovalStatus = Field(
        ...,
        description="Approval outcome: APPROVED or REJECTED",
    )
    decided_by: str = Field(
        ...,
        description="Identity of the approver",
    )
    comment: str = Field(
        ...,
        min_length=5,
        description="Justification or review comment",
    )
    decided_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Decision timestamp in UTC",
    )


class BudgetEntity(CanonicalEntity):
    """First-class canonical domain entity tracking financial budget ceilings."""

    tenant_id: str = Field(
        ...,
        description="Tenant boundary isolating budget governance",
    )
    name: str = Field(
        ...,
        description="Descriptive budget title",
    )
    scope_type: BudgetScopeType = Field(
        ...,
        description="One of the seventeen canonical scope types",
    )
    scope_id: str = Field(
        ...,
        description="Identifier of target scope node (e.g. account ID, app-name, cost-centre code)",
    )
    parent_budget_id: str | None = Field(
        default=None,
        description="Optional parent budget ID for hierarchy inheritance and rollup",
    )
    period: BudgetPeriod = Field(
        default=BudgetPeriod.MONTHLY,
        description="MONTHLY, QUARTERLY, ANNUAL, FISCAL_YEAR, or CUSTOM",
    )
    amount: float = Field(
        ...,
        gt=0.0,
        description="Financial budget allocation ceiling",
    )
    currency: str = Field(
        default="USD",
        description="ISO currency code (USD, EUR, GBP, etc.)",
    )
    thresholds: list[BudgetThreshold] = Field(
        default_factory=list,
        description="Alerting thresholds (e.g. 50%, 80%, 100%, 120%)",
    )
    alert_recipients: list[str] = Field(
        default_factory=list,
        description="Default notification recipients",
    )
    escalation: BudgetEscalation | None = Field(
        default=None,
        description="Escalation policy for unresolved breaches",
    )
    forecast_threshold: float | None = Field(
        default=100.0,
        description="Forecast spend percentage threshold triggering early warning alert",
    )
    effective_date: date = Field(
        ...,
        description="Date from which the budget becomes operational and evaluable",
    )
    expiry_date: date | None = Field(
        default=None,
        description="Optional date after which budget is no longer active",
    )
    owner: str = Field(
        ...,
        description="FinOps or Business Unit owner responsible for budget",
    )
    approval_status: BudgetApprovalStatus = Field(
        default=BudgetApprovalStatus.DRAFT,
        description="Workflow approval status (DRAFT, PENDING_APPROVAL, APPROVED, REJECTED, ACTIVE)",
    )
    approval_decision: BudgetApprovalDecision | None = Field(
        default=None,
        description="Recorded approval decision if processed",
    )
    rollover_policy: BudgetRolloverPolicy = Field(
        default=BudgetRolloverPolicy.NONE,
        description="Rollover policy for unspent/overspent balances at cycle close",
    )
    notes: str | None = Field(
        default=None,
        description="Administrative notes or governance context",
    )
    budget_source: BudgetSourceType = Field(
        default=BudgetSourceType.CLOUDLENS_LOGICAL,
        description="CLOUDLENS_LOGICAL or PROVIDER_NATIVE",
    )
    is_native: bool = Field(
        default=False,
        description="True if imported read-only from cloud provider native budget",
    )
    is_read_only: bool = Field(
        default=False,
        description="Read-only flag: provider-imported budgets cannot be mutated",
    )
    native_provider: CloudProvider | None = Field(
        default=None,
        description="Origin provider (AWS, Azure, GCP, OCI) if native",
    )
    native_budget_id: str | None = Field(
        default=None,
        description="Native provider budget identifier",
    )
    native_budget_name: str | None = Field(
        default=None,
        description="Native provider budget title",
    )
    amendments: list[BudgetAmendment] = Field(
        default_factory=list,
        description="Immutable audit history of previous amount, new amount, actor, approver, reason",
    )

    @model_validator(mode="after")
    def validate_budget_rules(self) -> BudgetEntity:
        if self.amount <= 0.0:
            raise InvalidBudgetAmountException(self.amount)
        if self.expiry_date and self.expiry_date < self.effective_date:
            raise InvalidBudgetDatesException(
                f"Budget expiry_date ({self.expiry_date}) cannot be before effective_date ({self.effective_date})."
            )
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_logical(self) -> bool:
        """Returns True if this budget is an organizational or application logical grouping."""
        return self.scope_type.is_logical()

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_active(self) -> bool:
        """Returns True if the budget is currently operational."""
        return self.approval_status in (
            BudgetApprovalStatus.ACTIVE,
            BudgetApprovalStatus.APPROVED,
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def display_source_badge(self) -> str:
        """Visual badge ensuring provider-imported budgets are clearly distinguished."""
        if self.is_native:
            return f"[PROVIDER NATIVE - {self.native_provider.value.upper() if self.native_provider else 'CLOUD'} - READ ONLY]"
        return "[CLOUDLENS LOGICAL]"


# ==============================================================================
# Evaluation, Overlap & Hierarchy DTOs
# ==============================================================================


class BudgetEvaluationResult(BaseModel):
    """Real-time financial evaluation of budget consumption and burn rate."""

    budget_id: str
    budget_name: str
    scope_type: BudgetScopeType
    scope_id: str
    currency: str
    amount: float
    actual_spend: float
    actual_utilisation: float
    forecast_spend: float
    forecast_utilisation: float
    variance: float
    variance_pct: float
    state: ThresholdState
    state_color: str
    is_breached: bool
    is_effective: bool
    effective_date: date
    expiry_date: date | None = None
    period_start: date
    period_end: date
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    predicted_breach_date: date | None = None
    notes: str | None = None


class BudgetOverlapWarning(BaseModel):
    """Detected overlap or over-allocation condition."""

    budget_id: str
    budget_name: str
    overlapping_budget_id: str
    overlapping_budget_name: str
    overlap_type: str  # CHILD_OVER_ALLOCATION, LOGICAL_NATIVE_OVERLAP, SAME_SCOPE_DUPLICATE
    scope_type: BudgetScopeType
    scope_id: str
    overlapping_scope_type: BudgetScopeType
    overlapping_scope_id: str
    explanation: str
    severity: str  # WARNING, INFO


class BudgetHierarchySummary(BaseModel):
    """Hierarchy allocation and unallocated remainder summary."""

    parent_budget_id: str
    parent_budget_name: str
    parent_amount: float
    total_child_allocated: float
    unallocated_remainder: float
    is_over_allocated: bool
    child_count: int
    children: list[dict[str, Any]] = Field(default_factory=list)


class BudgetTemplate(BaseModel):
    """Pre-configured budget template for a given scope type."""

    code: str
    scope_type: BudgetScopeType
    display_name: str
    description: str
    default_period: BudgetPeriod
    default_thresholds: list[BudgetThreshold]
    default_alert_recipients: list[str] = Field(default_factory=list)
    suggested_forecast_threshold: float = 100.0


# ==============================================================================
# API Request / Response DTOs
# ==============================================================================


class BudgetCreateRequest(BaseModel):
    """Payload to create a new CloudLens budget (Prompt 28 / API-038)."""

    name: str = Field(..., min_length=2)
    scope_type: BudgetScopeType
    scope_id: str = Field(..., min_length=1)
    parent_budget_id: str | None = None
    period: BudgetPeriod = BudgetPeriod.MONTHLY
    amount: float = Field(..., gt=0.0)
    currency: str = "USD"
    thresholds: list[BudgetThreshold] = Field(
        default_factory=lambda: [
            BudgetThreshold(percentage=80.0, band="WARNING"),
            BudgetThreshold(percentage=100.0, band="CRITICAL"),
        ]
    )
    alert_recipients: list[str] = Field(default_factory=list)
    escalation: BudgetEscalation | None = None
    forecast_threshold: float | None = 100.0
    effective_date: date
    expiry_date: date | None = None
    owner: str = Field(..., min_length=2)
    rollover_policy: BudgetRolloverPolicy = BudgetRolloverPolicy.NONE
    notes: str | None = None

    @field_validator("scope_type", mode="before")
    @classmethod
    def parse_scope_type(cls, v: Any) -> Any:
        if isinstance(v, str):
            return BudgetScopeType(v.upper())
        return v

    @field_validator("period", mode="before")
    @classmethod
    def parse_period(cls, v: Any) -> Any:
        if isinstance(v, str):
            return BudgetPeriod(v.upper())
        return v


class BudgetAmendRequest(BaseModel):
    """Payload to amend an existing budget allocation (Prompt 28 / API-039)."""

    new_amount: float = Field(..., gt=0.0)
    reason: str = Field(..., min_length=5)


class BudgetApproveRequest(BaseModel):
    """Payload to record a formal budget approval decision."""

    comment: str = Field(..., min_length=5)


class BudgetRejectRequest(BaseModel):
    """Payload to record a formal budget rejection."""

    comment: str = Field(..., min_length=5)


class NativeBudgetImportRequest(BaseModel):
    """Payload to import a provider-native budget as read-only for comparison."""

    provider: ProviderType
    native_budget_id: str
    native_budget_name: str
    scope_type: BudgetScopeType
    scope_id: str
    period: BudgetPeriod = BudgetPeriod.MONTHLY
    amount: float = Field(..., gt=0.0)
    currency: str = "USD"
    effective_date: date
    expiry_date: date | None = None
    owner: str = "Provider Sync"
    notes: str | None = "Imported read-only from cloud provider native budget"
