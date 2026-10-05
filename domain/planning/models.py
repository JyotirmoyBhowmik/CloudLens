"""Domain Models for Budget Planning & Scenario Modelling (Prompt 57).

Enforces:
- Fixed-point Decimal arithmetic on all monetary figures with ROUND_HALF_EVEN.
- First-class planning cycle object with master-data-driven calendar and scope owners.
- Bottom-up submissions with versioning and immutable approved state.
- Top-down target setting with multi-level gap analysis.
- Non-mutating what-if scenario modelling.
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import ROUND_HALF_EVEN, Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class PlanningBasisType(str, Enum):
    """Pre-populated basis methods for bottom-up budget proposals."""
    PRIOR_YEAR_ACTUAL = "PRIOR_YEAR_ACTUAL"
    CURRENT_YEAR_RUN_RATE = "CURRENT_YEAR_RUN_RATE"
    CURRENT_YEAR_FORECAST = "CURRENT_YEAR_FORECAST"
    ZERO_BASE = "ZERO_BASE"


class CycleStatus(str, Enum):
    """Lifecycle status of a planning cycle."""
    DRAFT = "DRAFT"
    OPEN_SUBMISSION = "OPEN_SUBMISSION"
    UNDER_REVIEW = "UNDER_REVIEW"
    APPROVED = "APPROVED"
    CLOSED = "CLOSED"


class SubmissionStatus(str, Enum):
    """Status of a bottom-up submission draft."""
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    REVISED = "REVISED"
    APPROVED = "APPROVED"


class AssumptionType(str, Enum):
    """Type of what-if scenario assumption."""
    GROWTH_RATE = "GROWTH_RATE"
    PROVIDER_MIGRATION = "PROVIDER_MIGRATION"
    COMMITMENT_PURCHASE = "COMMITMENT_PURCHASE"
    DECOMMISSIONING_PROGRAMME = "DECOMMISSIONING_PROGRAMME"
    PRICE_CHANGE = "PRICE_CHANGE"
    NEW_WORKLOAD = "NEW_WORKLOAD"


class PlanningScope(BaseModel):
    """Participating organizational scope in a planning cycle."""
    scope_type: str = Field(..., description="Scope level: TENANT, BUSINESS_UNIT, COST_CENTRE, PROJECT")
    scope_id: str = Field(..., description="Unique scope identifier")
    owner_id: str = Field(..., description="Responsible owner user identity")
    display_name: str | None = Field(default=None, description="Human readable scope title")


class PlanLineItem(BaseModel):
    """Line-level build-up element within a proposal."""
    item_id: str = Field(default_factory=lambda: f"item-{uuid.uuid4().hex[:8]}")
    service_category: str = Field(..., description="Cloud service category, e.g. COMPUTE, STORAGE, DATABASE")
    service_name: str = Field(..., description="Specific cloud service or resource group")
    proposed_amount: Decimal = Field(..., description="Monetary proposed figure in Decimal")
    rationale: str = Field(default="", description="Engineering or operational rationale")

    @field_validator("proposed_amount", mode="before")
    @classmethod
    def _coerce_decimal(cls, v: Any) -> Decimal:
        if isinstance(v, Decimal):
            return v
        return Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)


class PlanningCycle(BaseModel):
    """Master-data-governed planning cycle representing a fiscal planning window."""
    cycle_id: str = Field(default_factory=lambda: f"cycle-{uuid.uuid4().hex[:8]}")
    tenant_id: str = Field(..., description="Tenant identifier")
    name: str = Field(..., description="Cycle name, e.g. FY27 Budget Formulation")
    fiscal_period: str = Field(..., description="Target fiscal period, e.g. FY2027 or 2027-Q1")
    submission_window_start: dt.datetime
    submission_window_end: dt.datetime
    review_window_start: dt.datetime
    review_window_end: dt.datetime
    approval_deadline: dt.datetime
    participating_scopes: list[PlanningScope] = Field(default_factory=list)
    status: CycleStatus = Field(default=CycleStatus.DRAFT)
    default_basis: PlanningBasisType = Field(default=PlanningBasisType.PRIOR_YEAR_ACTUAL)
    created_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now(dt.UTC))
    updated_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now(dt.UTC))


class BottomUpSubmission(BaseModel):
    """Versioned bottom-up proposal submitted by a budget scope owner."""
    submission_id: str = Field(default_factory=lambda: f"sub-{uuid.uuid4().hex[:8]}")
    cycle_id: str
    tenant_id: str
    scope_type: str
    scope_id: str
    submitted_by: str
    version: int = Field(default=1, ge=1)
    basis_type: PlanningBasisType = Field(default=PlanningBasisType.PRIOR_YEAR_ACTUAL)
    baseline_amount: Decimal = Field(default=Decimal("0.00"))
    proposed_amount: Decimal = Field(..., description="Final submitted budget figure")
    justification: str = Field(..., min_length=5, description="Business justification for budget amount")
    line_items: list[PlanLineItem] = Field(default_factory=list)
    status: SubmissionStatus = Field(default=SubmissionStatus.DRAFT)
    workflow_request_id: str | None = None
    created_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now(dt.UTC))
    updated_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now(dt.UTC))

    @field_validator("baseline_amount", "proposed_amount", mode="before")
    @classmethod
    def _coerce_amount(cls, v: Any) -> Decimal:
        if isinstance(v, Decimal):
            return v
        return Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)


class TopDownTarget(BaseModel):
    """Executive or Finance-issued budget envelope target."""
    target_id: str = Field(default_factory=lambda: f"tgt-{uuid.uuid4().hex[:8]}")
    cycle_id: str
    tenant_id: str
    scope_type: str
    scope_id: str
    target_amount: Decimal
    issued_by: str
    issued_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now(dt.UTC))

    @field_validator("target_amount", mode="before")
    @classmethod
    def _coerce_target(cls, v: Any) -> Decimal:
        if isinstance(v, Decimal):
            return v
        return Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)


class TargetGapReport(BaseModel):
    """Financial gap report between executive targets and operational submissions."""
    cycle_id: str
    scope_type: str
    scope_id: str
    top_down_target: Decimal
    bottom_up_sum: Decimal
    gap: Decimal = Field(..., description="Sum of bottom-up minus top-down target")
    is_unfavourable: bool = Field(..., description="True if submissions exceed top-down budget envelope")
    child_breakdowns: list[dict[str, Any]] = Field(default_factory=list)


class ScenarioAssumption(BaseModel):
    """Atomic parameter assumption within a what-if financial model."""
    assumption_id: str = Field(default_factory=lambda: f"asm-{uuid.uuid4().hex[:8]}")
    assumption_type: AssumptionType
    description: str
    service_category: str | None = None
    provider_from: str | None = None
    provider_to: str | None = None
    percentage_change: Decimal | None = None
    fixed_delta: Decimal | None = None
    estimate_id: str | None = None

    @field_validator("percentage_change", "fixed_delta", mode="before")
    @classmethod
    def _coerce_decimal_opt(cls, v: Any) -> Decimal | None:
        if v is None:
            return None
        if isinstance(v, Decimal):
            return v
        return Decimal(str(v)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_EVEN)


class WhatIfScenario(BaseModel):
    """Named financial scenario applied on top of an untouched baseline."""
    scenario_id: str = Field(default_factory=lambda: f"scen-{uuid.uuid4().hex[:8]}")
    cycle_id: str
    name: str
    description: str
    baseline_amount: Decimal
    assumptions: list[ScenarioAssumption] = Field(default_factory=list)

    @field_validator("baseline_amount", mode="before")
    @classmethod
    def _coerce_baseline(cls, v: Any) -> Decimal:
        if isinstance(v, Decimal):
            return v
        return Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)


class ScenarioEvaluationResult(BaseModel):
    """Result of evaluating a scenario against baseline without mutating original figures."""
    scenario_id: str
    name: str
    baseline_amount: Decimal
    projected_amount: Decimal
    absolute_delta: Decimal
    percentage_delta: Decimal
    assumption_impacts: list[dict[str, Any]] = Field(default_factory=list)


class PlanAccuracyReport(BaseModel):
    """Post-period reconciliation measuring plan versus actual expenditure accuracy."""
    fiscal_period: str
    scope_id: str
    planned_amount: Decimal
    actual_amount: Decimal
    variance: Decimal
    accuracy_percentage: Decimal
