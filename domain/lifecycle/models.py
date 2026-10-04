"""Domain Models for Resource Lifecycle and Decommissioning (Prompt 59).

Enforces:
- 10-state lifecycle state model as master data:
  REQUESTED -> PROVISIONED -> ACTIVE -> IDLE_CANDIDATE -> DECOMMISSION_PROPOSED ->
  DECOMMISSION_APPROVED -> STOPPED -> PENDING_DELETION -> DELETED -> RETIRED.
- Mandatory dependency impact check with cross-team owner sign-off.
- Staged stop-observe-delete path with soak window and stopped-but-not-deleted surfacing.
- Cost-stop verification from actual billing data.
- Orphan/residue detection with costed tasks.
- Realised saving credit into ledger from actuals (never from estimates).
- Read-only safety guard: CloudLens never touches provider delete APIs.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal, ROUND_HALF_EVEN
from enum import Enum
from typing import Any
import uuid

from pydantic import BaseModel, Field, field_validator


class LifecycleState(str, Enum):
    """The 10 canonical lifecycle states governing cloud resources."""
    REQUESTED = "REQUESTED"
    PROVISIONED = "PROVISIONED"
    ACTIVE = "ACTIVE"
    IDLE_CANDIDATE = "IDLE_CANDIDATE"
    DECOMMISSION_PROPOSED = "DECOMMISSION_PROPOSED"
    DECOMMISSION_APPROVED = "DECOMMISSION_APPROVED"
    STOPPED = "STOPPED"
    PENDING_DELETION = "PENDING_DELETION"
    DELETED = "DELETED"
    RETIRED = "RETIRED"


class OrphanResourceType(str, Enum):
    """Classification of orphaned cloud residue left behind after incomplete decommissioning."""
    UNATTACHED_DISK = "UNATTACHED_DISK"
    UNUSED_IP_ADDRESS = "UNUSED_IP_ADDRESS"
    ORPHAN_SNAPSHOT = "ORPHAN_SNAPSHOT"
    SOURCELESS_BACKUP = "SOURCELESS_BACKUP"
    EMPTY_SCOPE = "EMPTY_SCOPE"


class DependencyAcknowledgement(BaseModel):
    """Cross-team sign-off acknowledging downstream impact of decommissioning."""
    dependency_id: str
    source_resource_id: str
    dependent_resource_id: str
    dependency_type: str = Field(..., description="Type of dependency, e.g. NETWORK, SERVICE_CALL, DATABASE")
    dependent_owner_team: str
    proposer_owner_team: str
    confidence: Decimal = Field(default=Decimal("1.00"))
    is_cross_team: bool = False
    is_acknowledged: bool = False
    acknowledged_by: str | None = None
    acknowledged_at: dt.datetime | None = None

    @field_validator("confidence", mode="before")
    @classmethod
    def _coerce_confidence(cls, v: Any) -> Decimal:
        if isinstance(v, Decimal):
            return v
        return Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)


class RetentionObligation(BaseModel):
    """Statutory or compliance data retention hold recorded against a resource."""
    obligation_id: str = Field(default_factory=lambda: f"ret-{uuid.uuid4().hex[:8]}")
    retention_basis: str = Field(..., description="Legal basis, e.g. SEC-Rule-17a-4, GDPR-7YR, TAX-AUDIT")
    mandatory_until: dt.datetime
    is_satisfied: bool = False
    satisfied_by: str | None = None
    satisfied_at: dt.datetime | None = None
    signoff_notes: str | None = None


class LifecycleResource(BaseModel):
    """Resource tracking state, transitions, and decommissioning history."""
    resource_id: str
    tenant_id: str
    owner_team: str
    service_type: str
    current_state: LifecycleState = Field(default=LifecycleState.ACTIVE)
    monthly_run_rate: Decimal = Field(default=Decimal("0.00"))
    storage_cost_rate: Decimal = Field(default=Decimal("0.00"))
    stopped_at: dt.datetime | None = None
    deleted_at: dt.datetime | None = None
    retired_at: dt.datetime | None = None
    retention_obligation: RetentionObligation | None = None
    inbound_dependencies: list[DependencyAcknowledgement] = Field(default_factory=list)

    @field_validator("monthly_run_rate", "storage_cost_rate", mode="before")
    @classmethod
    def _coerce_rate(cls, v: Any) -> Decimal:
        if isinstance(v, Decimal):
            return v
        return Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)


class DecommissioningRequest(BaseModel):
    """Formal decommissioning request entering Prompt 50 workflow."""
    request_id: str = Field(default_factory=lambda: f"dcom-{uuid.uuid4().hex[:8]}")
    programme_id: str | None = None
    resource_ids: list[str]
    proposing_actor: str
    proposer_team: str
    justification: str
    intended_date: dt.datetime
    estimated_monthly_saving: Decimal
    workflow_request_id: str | None = None
    is_approved: bool = False
    approved_by: str | None = None
    approved_at: dt.datetime | None = None
    created_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))

    @field_validator("estimated_monthly_saving", mode="before")
    @classmethod
    def _coerce_saving(cls, v: Any) -> Decimal:
        if isinstance(v, Decimal):
            return v
        return Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)


class StoppedResourceSurfaced(BaseModel):
    """Resource surfaced because it remained stopped past its soak window without deletion."""
    resource_id: str
    owner_team: str
    stopped_at: dt.datetime
    days_in_stopped_state: int
    ongoing_storage_cost: Decimal
    alert_level: str = "WARNING"

    @field_validator("ongoing_storage_cost", mode="before")
    @classmethod
    def _coerce_storage(cls, v: Any) -> Decimal:
        if isinstance(v, Decimal):
            return v
        return Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)


class OrphanResidueItem(BaseModel):
    """Detected orphan or cloud residue resource."""
    residue_id: str = Field(default_factory=lambda: f"res-{uuid.uuid4().hex[:8]}")
    resource_id: str
    residue_type: OrphanResourceType
    associated_scope: str
    monthly_waste_cost: Decimal
    task_created_id: str | None = None
    detected_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))

    @field_validator("monthly_waste_cost", mode="before")
    @classmethod
    def _coerce_cost(cls, v: Any) -> Decimal:
        if isinstance(v, Decimal):
            return v
        return Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)


class DecommissioningProgramme(BaseModel):
    """Named programme grouping multiple resources for strategic decommissioning."""
    programme_id: str = Field(default_factory=lambda: f"prog-{uuid.uuid4().hex[:8]}")
    tenant_id: str
    name: str
    description: str
    target_completion_date: dt.datetime
    resource_ids: list[str] = Field(default_factory=list)
    projected_monthly_savings: Decimal = Field(default=Decimal("0.00"))
    realised_monthly_savings: Decimal = Field(default=Decimal("0.00"))

    @field_validator("projected_monthly_savings", "realised_monthly_savings", mode="before")
    @classmethod
    def _coerce_prog_money(cls, v: Any) -> Decimal:
        if isinstance(v, Decimal):
            return v
        return Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)


class DecommissioningProgrammeView(BaseModel):
    """Aggregated programme progress and savings report."""
    programme_id: str
    name: str
    total_resources: int
    state_breakdown: dict[str, int]
    projected_monthly_savings: Decimal
    realised_monthly_savings: Decimal
    outstanding_dependencies_count: int
