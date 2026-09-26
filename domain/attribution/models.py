"""Attribution, Ownership Resolution, and Allocation Domain Models.

Enforces:
1. Prompt 08 Item 55 & 56: Ownership resolution 6-level precedence and governance exceptions.
2. Prompt 08 Item 57: Allocation rule evaluation, split validation (sum to 100%), and explainability.
3. Prompt 08 Item 58: Unallocated cost visibility.
4. Prompt 08 Item 59: Curated-field protection.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator

from domain.models.exceptions import InvalidSplitRuleException


class OwnershipResolutionRule(str, Enum):
    """Deterministic precedence order for ownership attribution (BBP Section 16.2)."""

    MANUAL_ASSIGNMENT = "MANUAL_ASSIGNMENT"
    OWNERSHIP_TAG = "OWNERSHIP_TAG"
    INHERITED_TAG = "INHERITED_TAG"
    SCOPE_RULE = "SCOPE_RULE"
    APPLICATION_RULE = "APPLICATION_RULE"
    UNRESOLVED = "UNRESOLVED"


class OwnershipResolutionResult(BaseModel):
    """Result of ownership evaluation recording the winning rule and audit provenance."""

    resource_id: str = Field(..., description="Target Resource ID")
    owner_id: str | None = Field(
        default=None, description="Assigned Owner ID or email (None if unresolved)"
    )
    owner_email: str | None = Field(default=None, description="Contact email address if available")
    winning_rule: OwnershipResolutionRule = Field(
        ..., description="Specific rule in precedence chain that produced result"
    )
    rule_description: str = Field(
        ..., description="Human-readable explanation of how owner was determined"
    )
    is_resolved: bool = Field(
        ..., description="Whether an accountable owner was successfully resolved"
    )
    resolved_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp of resolution",
    )
    governance_exception: str | None = Field(
        default=None,
        description="Governance exception details if outcome is UNRESOLVED",
    )


class AllocationRuleType(str, Enum):
    """Allocation rule types evaluated with first-match-wins order (BBP Section 17.5)."""

    DIRECT_RESOURCE = "DIRECT_RESOURCE"
    TAG_RULE = "TAG_RULE"
    SCOPE_RULE = "SCOPE_RULE"
    SERVICE_RULE = "SERVICE_RULE"
    SPLIT_RULE = "SPLIT_RULE"
    UNALLOCATED = "UNALLOCATED"


class AllocationSplitType(str, Enum):
    """Methodology for splitting shared costs."""

    PROPORTIONAL = "PROPORTIONAL"
    FIXED = "FIXED"


class AllocationSplitTarget(BaseModel):
    """Target destination for split cost allocation."""

    cost_center_code: str = Field(..., description="Target CostCenter accounting code")
    business_unit_code: str | None = Field(default=None, description="Target BusinessUnit code")
    percentage: Decimal = Field(..., description="Allocation percentage share (e.g. 50.0)")


class AllocationRule(BaseModel):
    """Declarative FinOps cost allocation rule."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = Field(..., description="Descriptive rule title")
    rule_type: AllocationRuleType = Field(..., description="Precedence tier of rule")
    priority: int = Field(
        default=100,
        description="Execution order within same rule type tier (lower executes first)",
    )
    # Match predicates
    match_resource_id: str | None = Field(default=None, description="Exact resource ID to match")
    match_tag_key: str | None = Field(default=None, description="Normalized tag key to match")
    match_tag_value: str | None = Field(
        default=None, description="Tag value to match (None matches key presence)"
    )
    match_scope_id: str | None = Field(
        default=None, description="Scope or parent hierarchy node ID"
    )
    match_service_id: str | None = Field(default=None, description="Canonical service code or ID")
    match_service_category: str | None = Field(default=None, description="FOCUS service category")
    # Targets
    target_cost_center_code: str | None = Field(
        default=None, description="Destination cost center code"
    )
    target_business_unit_code: str | None = Field(
        default=None, description="Destination business unit code"
    )
    target_project_code: str | None = Field(default=None, description="Destination project code")
    # Split configuration
    split_type: AllocationSplitType | None = Field(
        default=None, description="PROPORTIONAL or FIXED split"
    )
    split_targets: list[AllocationSplitTarget] = Field(
        default_factory=list, description="Target shares for SPLIT_RULE"
    )
    is_active: bool = Field(default=True, description="Whether rule is currently active")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_split_percentages(self) -> "AllocationRule":
        """Rejects split rules that do not sum to exactly 100% at save/validation time."""
        if self.rule_type == AllocationRuleType.SPLIT_RULE:
            if not self.split_targets:
                raise InvalidSplitRuleException(
                    f"Split rule '{self.name}' must have at least one split target."
                )
            total = sum(t.percentage for t in self.split_targets)
            if total != Decimal("100.0"):
                raise InvalidSplitRuleException(
                    f"Split rule '{self.name}' percentages sum to {total}%, expected exactly 100.0%."
                )
        return self


class AllocatedCostRow(BaseModel):
    """Materialised cost attribution row with explainability lineage."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    cost_fact_id: str = Field(..., description="Originating CostFact ID")
    resource_id: str | None = Field(default=None, description="Target resource ID")
    scope_id: str = Field(..., description="Target scope hierarchy ID")
    total_cost: Decimal = Field(..., description="Original billed or effective cost")
    allocated_amount: Decimal = Field(..., description="Amount allocated to this destination")
    currency: str = Field(default="USD", description="Currency code")
    cost_center_code: str = Field(..., description="Attributed CostCenter or 'UNALLOCATED'")
    business_unit_code: str | None = Field(default=None)
    project_code: str | None = Field(default=None)
    winning_rule_type: AllocationRuleType = Field(
        ..., description="Rule type tier that won the attribution"
    )
    winning_rule_id: str | None = Field(
        default=None, description="ID of the matching allocation rule"
    )
    winning_rule_name: str = Field(
        ..., description="Name of the matching rule or 'Unallocated Fallback'"
    )
    rule_explanation: str = Field(
        ..., description="Full audit explanation of why and how cost was allocated"
    )
    split_percentage: Decimal | None = Field(
        default=None, description="Share percentage if generated by split rule"
    )
    allocated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class CuratedField(str, Enum):
    """Protected resource attributes that survive discovery synchronisation."""

    OWNER = "owner_id"
    APPLICATION = "application_id"
    ENVIRONMENT = "environment_id"
    COST_CENTER = "cost_center_id"
    MONITORING_TYPE = "monitoring_type"


class CuratedFieldRecord(BaseModel):
    """Tracks manual curation applied to a resource attribute."""

    resource_id: str = Field(..., description="Target Resource ID")
    field_name: CuratedField = Field(..., description="Attribute under curation")
    curated_value: Any = Field(..., description="Curated value")
    curated_by: str = Field(..., description="Principal/user who set the curated value")
    curated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp of manual curation",
    )
    reason: str = Field(default="Manual curation", description="Business justification")
