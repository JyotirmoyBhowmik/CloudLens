"""Domain Models for Governance-Layer Mock Estate Extension (Prompt 47B).

Enforces:
- Quota mock data across all headroom states (Healthy, Warning, Breach Imminent, Exhausted, Not Supported, Manual).
- Provisioning requests across all eight workflow states with approved-to-actual tracking and unapproved deployment detection.
- Remediation tasks across all eleven states with false-resolved verification reopening.
- Showback statements across 3 business units over 2 periods with dispute, acceptance, unallocated, and restatement cases.
- Approver inbox populated with all workflow types, escalation, and delegation.
- Commitment portfolio mock data (coverage, over-committed, under-committed, renewal window).
- Budget planning mock data (open cycle, top-down target, partial submissions, gap).
- Master-data gap items, import history, and analytical extract run history.
- Screen verification models for Mandate M3 (S-01 to S-27).
"""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

# ==============================================================================
# 1. Forward Demo Models (Commitments, Planning, Analytical Extracts)
# ==============================================================================


class CommitmentStatus(StrEnum):
    ACTIVE = "ACTIVE"
    EXPIRING_SOON = "EXPIRING_SOON"
    EXPIRED = "EXPIRED"


class CommitmentType(StrEnum):
    SAVINGS_PLAN = "SAVINGS_PLAN"
    RESERVED_INSTANCE = "RESERVED_INSTANCE"
    COMMITTED_USE_DISCOUNT = "COMMITTED_USE_DISCOUNT"


class CommitmentPortfolioItem(BaseModel):
    """Commitment, reservation, and savings plan for Prompt 58 demonstration."""

    commitment_id: str
    provider: str
    name: str
    commitment_type: CommitmentType
    term_months: int
    hourly_committed_rate: Decimal
    monthly_commitment: Decimal
    current_coverage_pct: Decimal
    current_utilisation_pct: Decimal
    start_date: str
    end_date: str
    days_to_expiry: int
    status: CommitmentStatus
    is_over_committed: bool = False
    is_under_committed: bool = False
    in_renewal_window: bool = False
    notes: str = ""


class BudgetPlanningSubmission(BaseModel):
    """Bottom-up budget planning proposal by a business unit (Prompt 57 demo)."""

    business_unit_id: str
    business_unit_name: str
    submitted_amount: Decimal
    submitted_by: str
    submitted_at: str
    status: str = "SUBMITTED"


class BudgetPlanningCycle(BaseModel):
    """Forward-looking budget planning cycle showing top-down target and gap (Prompt 57 demo)."""

    cycle_id: str
    cycle_name: str
    fiscal_year: str
    status: str = "OPEN"
    top_down_target: Decimal
    total_submitted: Decimal
    planning_gap: Decimal
    submissions: list[BudgetPlanningSubmission] = Field(default_factory=list)
    notes: str = ""


class AnalyticalExtractRunStatus(StrEnum):
    COMPLETED = "COMPLETED"
    DELAYED = "DELAYED"
    EMPTY = "EMPTY"
    FAILED = "FAILED"


class AnalyticalExtractRun(BaseModel):
    """Analytical FOCUS data feed scheduled extract run history (Prompt 56 demo)."""

    run_id: str
    period: str
    format: str = "PARQUET"
    destination_uri: str
    status: AnalyticalExtractRunStatus
    row_count: int
    file_size_mb: Decimal
    started_at: str
    completed_at: str | None = None
    delay_reason: str | None = None


class MasterDataGapItem(BaseModel):
    """Master data discrepancy or unmapped element for MDM governance demonstration."""

    gap_id: str
    entity_type: str
    key_identifier: str
    gap_type: str  # UNMAPPED_TAG, MISSING_COST_CENTRE, UNCLASSIFIED_SKU
    severity: str  # HIGH, MEDIUM, LOW
    suggested_action: str
    detected_at: str


class BulkImportJobSummary(BaseModel):
    """Historical bulk import execution summary (Prompt 53 demo)."""

    job_id: str
    source_filename: str
    is_dry_run: bool
    total_rows: int
    successful_rows: int
    error_rows: int
    executed_at: str
    executed_by: str
    status: str


# ==============================================================================
# 2. Complete Governance Mock Estate Result
# ==============================================================================


class GovernanceMockEstateResult(BaseModel):
    """Comprehensive governance and control mock dataset (Prompt 47B / Mandate M3)."""

    tenant_id: str
    seed: int
    generated_at: str

    # 1. Quotas (Prompt 54)
    quotas: list[dict[str, Any]] = Field(default_factory=list)
    quota_remediation_tasks: list[dict[str, Any]] = Field(default_factory=list)

    # 2. Provisioning Gate (Prompt 55)
    saved_estimates: list[dict[str, Any]] = Field(default_factory=list)
    provisioning_requests: list[dict[str, Any]] = Field(default_factory=list)
    estimate_actual_trackings: list[dict[str, Any]] = Field(default_factory=list)
    unapproved_findings: list[dict[str, Any]] = Field(default_factory=list)

    # 3. Remediation & Tasks (Prompt 51)
    remediation_tasks: list[dict[str, Any]] = Field(default_factory=list)
    false_resolved_task_id: str = "task-demo-false-resolved"

    # 4. Showback & Allocation Statements (Prompt 52)
    showback_statements: list[dict[str, Any]] = Field(default_factory=list)
    statement_adjustments: list[dict[str, Any]] = Field(default_factory=list)
    statement_disputes: list[dict[str, Any]] = Field(default_factory=list)
    disputed_line_statement_id: str = ""
    restated_statement_id: str = ""

    # 5. Workflow Engine & Inbox (Prompt 50)
    workflow_requests: list[dict[str, Any]] = Field(default_factory=list)
    escalated_request_id: str = ""
    delegated_request_id: str = ""

    # 6. Forward Demo Estates (Prompts 56, 57, 58)
    commitments: list[CommitmentPortfolioItem] = Field(default_factory=list)
    budget_planning: BudgetPlanningCycle | None = None
    analytical_extract_runs: list[AnalyticalExtractRun] = Field(default_factory=list)
    master_data_gaps: list[MasterDataGapItem] = Field(default_factory=list)
    import_jobs: list[BulkImportJobSummary] = Field(default_factory=list)


# ==============================================================================
# 3. Screen Verification Models (Mandate M3: Screens S-01 to S-27)
# ==============================================================================


class ScreenVerificationItem(BaseModel):
    """Verification outcome for an individual screen S-01 to S-27."""

    screen_code: str = Field(..., description="Screen code (e.g. S-01, S-15, S-27)")
    screen_name: str = Field(..., description="Screen title")
    domain_module: str = Field(..., description="Governing domain module")
    has_meaningful_data: bool = Field(..., description="True if demonstrable data is present")
    record_count: int = Field(..., description="Number of demonstrable records found")
    highlight_metric: str = Field(..., description="Key demonstration metric/state")
    sample_identifier: str = Field(..., description="Primary sample record ID")


class ScreenVerificationReport(BaseModel):
    """End-to-end Mandate M3 verification report covering all 27 screens."""

    tenant_id: str
    verified_at: str
    total_screens: int = 27
    passed_screens: int
    failed_screens: int
    is_m3_compliant: bool
    screens: list[ScreenVerificationItem] = Field(default_factory=list)
