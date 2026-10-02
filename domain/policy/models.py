"""Governance Policy Domain Models (Prompt 30, BBP Section 34, FR-740 to FR-746).

Enforces:
- FR-740: Governance policies must be declarative, versioned, and definable without code modification or deployment.
- FR-741: Policies must support simulate and enforce modes, with simulation producing findings without alerting.
- FR-742: A policy condition that cannot be evaluated for an entity must produce 'Not Evaluable', never False.
- FR-743: Policy exemptions must be time-boxed, justified, approved, and reported while active.
- FR-744: Policy violation findings must be deduplicated against open findings for the same entity and condition.
- FR-745: Governance exception counts and resolution times must be trended over time and reportable.
- FR-746: Default policies (POL-01 to POL-16), disabled by default except connector health.
- Negative constraint: Do NOT enable policies by default (only connector health is enabled).
- Negative constraint: Do NOT let a missing field produce a violation (must be NOT_EVALUABLE).
- Negative constraint: Do NOT allow an exemption without justification and expiry.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from pydantic import BaseModel, Field, field_validator

from domain.models.base import CanonicalEntity, ProvenanceRecord
from domain.models.enums import (
    ConditionOperator,
    EvaluationOutcome,
    FindingLifecycleStatus,
    LogicalOperator,
    OriginType,
    PolicyCategory,
    PolicyEffect,
    PolicyMode,
    PolicySeverity,
)
from domain.models.exceptions import InvalidExemptionException, PolicyValidationException

# ==============================================================================
# Declarative Condition Specification
# ==============================================================================


class DeclarativeCondition(BaseModel):
    """Declarative logical condition evaluated over canonical entity fields and measures."""

    operator: ConditionOperator | None = Field(
        default=None,
        description="Comparison operator for leaf condition (e.g. GREATER_THAN, EQUALS, CONTAINS)",
    )
    field: str | None = Field(
        default=None,
        description="Dot-notated canonical field path (e.g. 'tags.CostCenter', 'metrics.cpu_utilization', 'spend_actual')",
    )
    value: Any = Field(
        default=None,
        description="Literal comparison value (scalar, list of approved values, numeric threshold, or regex)",
    )
    logical_op: LogicalOperator | None = Field(
        default=None,
        description="Logical combinator for composite conditions (AND, OR, NOT)",
    )
    children: list[DeclarativeCondition] = Field(
        default_factory=list,
        description="Nested child conditions when logical_op is specified",
    )

    @field_validator("children")
    @classmethod
    def validate_composite_or_leaf(
        cls, children: list[DeclarativeCondition]
    ) -> list[DeclarativeCondition]:
        return children

    def validate_semantics(self) -> None:
        """Validates condition structure rules."""
        if self.logical_op is not None:
            if not self.children:
                raise PolicyValidationException(
                    f"Composite condition with '{self.logical_op.value}' must specify at least one child condition."
                )
            for child in self.children:
                child.validate_semantics()
        else:
            if self.operator is None:
                raise PolicyValidationException("Leaf condition must specify a valid 'operator'.")
            if self.field is None or not self.field.strip():
                raise PolicyValidationException(
                    "Leaf condition must specify a non-empty 'field' path."
                )


# ==============================================================================
# Target Selector Specification
# ==============================================================================


class TargetSelector(BaseModel):
    """Defines entity scoping criteria for policy application."""

    resource_types: list[str] = Field(
        default_factory=list,
        description="Specific resource types to target (empty implies all)",
    )
    providers: list[str] = Field(
        default_factory=list,
        description="Cloud provider types (AWS, AZURE, GCP, OCI) to target (empty implies all)",
    )
    scope_types: list[str] = Field(
        default_factory=list,
        description="Organizational scope levels (ORGANISATION, SUBSCRIPTION, etc.) to target",
    )
    scope_ids: list[str] = Field(
        default_factory=list,
        description="Target scope identifiers (empty implies all scopes)",
    )
    environments: list[str] = Field(
        default_factory=list,
        description="Target deployment environments (PROD, DEV, STAGING, etc.)",
    )
    tag_filters: dict[str, str] = Field(
        default_factory=dict,
        description="Required tag key-value pairs for entity targeting",
    )

    def matches(self, entity_data: dict[str, Any]) -> bool:
        """Determines if an entity meets this target selector criteria."""
        if self.resource_types:
            r_type = entity_data.get("resource_type") or entity_data.get("type")
            if r_type not in self.resource_types:
                return False

        if self.providers:
            prov = entity_data.get("provider") or entity_data.get("cloud_provider")
            if prov not in self.providers:
                return False

        if self.scope_types:
            s_type = entity_data.get("scope_type")
            if s_type not in self.scope_types:
                return False

        if self.scope_ids:
            s_id = entity_data.get("scope_id")
            if s_id not in self.scope_ids:
                return False

        if self.environments:
            env = entity_data.get("environment") or entity_data.get("env")
            if env not in self.environments:
                return False

        if self.tag_filters:
            entity_tags = entity_data.get("tags") or {}
            for k, v in self.tag_filters.items():
                if entity_tags.get(k) != v:
                    return False

        return True


# ==============================================================================
# Policy Exemption Model
# ==============================================================================


class PolicyExemption(BaseModel):
    """Time-boxed, justified governance exemption (Prompt 30, FR-743)."""

    id: str = Field(
        default_factory=lambda: f"exm-{uuid.uuid4().hex[:12]}",
        description="Unique exemption identifier",
    )
    policy_id: str = Field(..., description="Target policy identifier")
    entity_id: str | None = Field(
        default=None,
        description="Specific entity ID exempted (None implies policy-wide or scope-wide)",
    )
    scope_id: str | None = Field(
        default=None,
        description="Specific scope ID exempted",
    )
    justification: str = Field(
        ...,
        description="Mandatory business and technical rationale for granting exemption",
    )
    requested_by: str = Field(default="system", description="Identity requesting exemption")
    approved_by: str | None = Field(
        default=None,
        description="Authorized governance reviewer approving exemption",
    )
    requires_approval: bool = Field(
        default=False,
        description="Whether this exemption requires formal approval before becoming active",
    )
    is_approved: bool = Field(
        default=True,
        description="Approval state",
    )
    created_at: dt.datetime = Field(
        default_factory=lambda: dt.datetime.now(dt.UTC),
        description="Timestamp exemption was created",
    )
    expires_at: dt.datetime = Field(
        ...,
        description="Mandatory expiration timestamp; exemption reverts once passed",
    )

    @field_validator("justification")
    @classmethod
    def validate_justification_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise InvalidExemptionException(
                "Exemption justification is mandatory and cannot be empty."
            )
        return v.strip()

    def is_active(self, as_of: dt.datetime | None = None) -> bool:
        """Determines if exemption is active, approved, and not expired."""
        now = as_of or dt.datetime.now(dt.UTC)
        if not self.is_approved:
            return False
        return self.expires_at > now

    def matches_entity(self, entity_id: str, scope_id: str | None = None) -> bool:
        """Checks if this exemption applies to the given entity or scope."""
        if self.entity_id is not None:
            return self.entity_id == entity_id
        if self.scope_id is not None:
            return self.scope_id == scope_id
        return True


# ==============================================================================
# Policy Definition Model
# ==============================================================================


class PolicyDefinition(CanonicalEntity):
    """Authoritative, declarative, and versioned governance policy (Prompt 30, FR-740)."""

    id: str = Field(..., description="Stable policy identifier (e.g. 'POL-01', 'POL-08')")
    source_provenance: ProvenanceRecord = Field(
        default_factory=lambda: ProvenanceRecord(
            source_system="governance-policy-engine",
            origin_type=OriginType.CURATED,
        ),
        description="Lineage and origin tracking",
    )
    version: int = Field(default=1, description="Integer version incremented upon modification")
    name: str = Field(..., description="Display title of the governance policy")
    description: str = Field(..., description="Clear explanation of the policy intent and impact")
    category: PolicyCategory = Field(..., description="Functional taxonomy category")
    target_selector: TargetSelector = Field(
        default_factory=TargetSelector,
        description="Entity targeting criteria",
    )
    condition: DeclarativeCondition = Field(
        ...,
        description="Declarative logical condition evaluated over canonical fields and measures",
    )
    effect: PolicyEffect = Field(
        default=PolicyEffect.AUDIT_FINDING,
        description="Governance consequence on violation",
    )
    severity: PolicySeverity = Field(
        default=PolicySeverity.MEDIUM,
        description="Operational severity of detected violation",
    )
    evaluation_schedule: str = Field(
        default="DAILY",
        description="Evaluation cadence ('HOURLY', 'DAILY', or cron expression)",
    )
    mode: PolicyMode = Field(
        default=PolicyMode.SIMULATE,
        description="Execution mode: SIMULATE (findings only, no alerts) or ENFORCE (alerts raised)",
    )
    enabled: bool = Field(
        default=False,
        description="Whether the policy is actively evaluated in standard cycles",
    )
    created_at: dt.datetime = Field(
        default_factory=lambda: dt.datetime.now(dt.UTC),
        description="Creation timestamp",
    )
    updated_at: dt.datetime = Field(
        default_factory=lambda: dt.datetime.now(dt.UTC),
        description="Last update timestamp",
    )
    updated_by: str = Field(default="system", description="Identity who last modified the policy")
    is_default: bool = Field(
        default=False,
        description="True for system-seeded default policies (POL-01 to POL-16)",
    )


# ==============================================================================
# Policy Evaluation Finding Model
# ==============================================================================


class PolicyFinding(BaseModel):
    """Recorded observation of a policy violation or simulation outcome (Prompt 30, FR-741, FR-744)."""

    id: str = Field(
        default_factory=lambda: f"fnd-{uuid.uuid4().hex[:12]}",
        description="Unique finding identifier",
    )
    policy_id: str = Field(..., description="Violated policy stable identifier")
    policy_version: int = Field(
        ...,
        description="Exact policy version that produced this finding (FR-740 version retention)",
    )
    entity_id: str = Field(..., description="Target cloud entity identifier")
    entity_name: str = Field(default="", description="Target cloud entity display name")
    entity_type: str = Field(default="", description="Resource or scope type")
    provider: str = Field(default="", description="Cloud provider (AWS, AZURE, GCP, OCI, etc.)")
    scope_id: str = Field(default="", description="Parent organizational scope identifier")
    severity: PolicySeverity = Field(..., description="Observed violation severity")
    category: PolicyCategory = Field(..., description="Policy category")
    mode: PolicyMode = Field(
        ...,
        description="Mode during evaluation: SIMULATE (alerts suppressed) or ENFORCE",
    )
    lifecycle_status: FindingLifecycleStatus = Field(
        default=FindingLifecycleStatus.OPEN,
        description="Finding status: OPEN, CLEARED, EXEMPTED, ACKNOWLEDGED",
    )
    observed_value: Any = Field(
        default=None,
        description="Empirical value extracted from entity during evaluation",
    )
    expected_value: Any = Field(
        default=None,
        description="Expected threshold or rule value",
    )
    condition_summary: str = Field(
        default="",
        description="Human-readable statement of condition that failed",
    )
    is_alertable: bool = Field(
        default=False,
        description="True if finding should trigger an active alert notification",
    )
    alerts_suppressed: bool = Field(
        default=True,
        description="True if alerts were suppressed due to SIMULATE mode or active exemption",
    )
    consecutive_occurrences: int = Field(
        default=1,
        description="Number of evaluation cycles finding has persisted without clearing",
    )
    first_detected_at: dt.datetime = Field(
        default_factory=lambda: dt.datetime.now(dt.UTC),
        description="Timestamp first detected",
    )
    last_evaluated_at: dt.datetime = Field(
        default_factory=lambda: dt.datetime.now(dt.UTC),
        description="Timestamp of most recent evaluation cycle",
    )
    cleared_at: dt.datetime | None = Field(
        default=None,
        description="Timestamp finding was resolved because condition cleared",
    )
    exemption_id: str | None = Field(
        default=None,
        description="Active exemption ID that suppressed or excused this finding",
    )


# ==============================================================================
# Evaluation Result
# ==============================================================================


class PolicyEvaluationResult(BaseModel):
    """Detailed evaluation result for a single entity against a single policy (Prompt 30, FR-742)."""

    policy_id: str = Field(..., description="Evaluated policy ID")
    policy_version: int = Field(..., description="Evaluated policy version")
    entity_id: str = Field(..., description="Target entity ID")
    outcome: EvaluationOutcome = Field(
        ...,
        description="Result outcome: COMPLIANT, VIOLATION, NOT_EVALUABLE, EXEMPTED",
    )
    reason: str = Field(
        ...,
        description="Explanatory rationale for outcome (especially for NOT_EVALUABLE)",
    )
    observed_value: Any = Field(default=None, description="Observed value from entity")
    expected_value: Any = Field(default=None, description="Expected value from policy")
    missing_fields: list[str] = Field(
        default_factory=list,
        description="List of fields referenced by policy that provider does not supply",
    )
    evaluated_at: dt.datetime = Field(
        default_factory=lambda: dt.datetime.now(dt.UTC),
        description="Evaluation timestamp",
    )


# ==============================================================================
# Governance Exception Trending Models
# ==============================================================================


class GovernanceTrendPoint(BaseModel):
    """Temporal snapshot of open, new, and cleared governance findings (Prompt 30, FR-745)."""

    date: dt.date = Field(..., description="Snapshot calendar date")
    total_open: int = Field(default=0, description="Total active unresolved findings on this date")
    new_findings: int = Field(default=0, description="New findings detected on this date")
    cleared_findings: int = Field(default=0, description="Findings resolved/cleared on this date")
    net_change: int = Field(default=0, description="Net change in open exceptions (new - cleared)")
    by_severity: dict[str, int] = Field(
        default_factory=dict,
        description="Breakdown of open findings by severity",
    )
    by_category: dict[str, int] = Field(
        default_factory=dict,
        description="Breakdown of open findings by policy category",
    )


class GovernanceTrendReport(BaseModel):
    """Aggregated governance exception trend analysis over an evaluation window (Prompt 30, FR-745)."""

    tenant_id: str = Field(..., description="Tenant identifier")
    start_date: dt.date = Field(..., description="Report start date")
    end_date: dt.date = Field(..., description="Report end date")
    points: list[GovernanceTrendPoint] = Field(
        default_factory=list,
        description="Daily trend snapshots",
    )
    current_open_count: int = Field(default=0, description="Currently active open findings")
    total_detected_in_period: int = Field(default=0, description="Sum of newly detected findings")
    total_cleared_in_period: int = Field(default=0, description="Sum of cleared findings")
    mttr_hours: float = Field(
        default=0.0,
        description="Mean Time to Resolution (hours) for findings cleared during window",
    )
    resolution_rate_pct: float = Field(
        default=0.0,
        description="Percentage of detected findings resolved (cleared / detected * 100)",
    )


# ==============================================================================
# API Request / Response DTOs
# ==============================================================================


class PolicyCreateDTO(BaseModel):
    """Request payload for creating a governance policy without code deployment."""

    id: str = Field(..., description="Stable policy identifier (e.g. 'POL-CUSTOM-01')")
    name: str = Field(..., description="Display title")
    description: str = Field(..., description="Policy description")
    category: PolicyCategory = Field(..., description="Policy category")
    target_selector: TargetSelector = Field(default_factory=TargetSelector)
    condition: DeclarativeCondition = Field(...)
    effect: PolicyEffect = Field(default=PolicyEffect.AUDIT_FINDING)
    severity: PolicySeverity = Field(default=PolicySeverity.MEDIUM)
    evaluation_schedule: str = Field(default="DAILY")
    mode: PolicyMode = Field(default=PolicyMode.SIMULATE)
    enabled: bool = Field(default=False)


class PolicyUpdateDTO(BaseModel):
    """Request payload for updating an existing policy and creating a new version."""

    name: str | None = None
    description: str | None = None
    category: PolicyCategory | None = None
    target_selector: TargetSelector | None = None
    condition: DeclarativeCondition | None = None
    effect: PolicyEffect | None = None
    severity: PolicySeverity | None = None
    evaluation_schedule: str | None = None
    mode: PolicyMode | None = None
    enabled: bool | None = None


class PolicyEnableToggleDTO(BaseModel):
    """Payload to enable or disable a policy dynamically."""

    enabled: bool = Field(..., description="True to enable, False to disable")


class PolicyExemptionCreateDTO(BaseModel):
    """Payload to create a time-boxed justified exemption."""

    policy_id: str = Field(..., description="Target policy identifier")
    entity_id: str | None = Field(default=None, description="Optional entity ID")
    scope_id: str | None = Field(default=None, description="Optional scope ID")
    justification: str = Field(..., description="Mandatory business/technical rationale")
    expires_at: dt.datetime = Field(..., description="Mandatory expiration timestamp")
    requires_approval: bool = Field(default=False)
    approved_by: str | None = None


class PolicySimulationRequest(BaseModel):
    """Payload to execute policy simulation against target entity records."""

    policy_id: str | None = Field(
        default=None,
        description="Existing policy ID to simulate, or provide inline definition",
    )
    inline_policy: PolicyCreateDTO | None = Field(
        default=None,
        description="Inline declarative policy to test before saving",
    )
    entities: list[dict[str, Any]] = Field(
        ...,
        description="List of entity data dictionaries to test against",
    )


class PolicySimulationResponse(BaseModel):
    """Result of policy simulation execution."""

    policy_id: str
    policy_version: int
    mode: PolicyMode = PolicyMode.SIMULATE
    total_evaluated: int
    violations_count: int
    compliant_count: int
    not_evaluable_count: int
    exempted_count: int
    alerts_raised: int = 0  # Always 0 in simulation mode per Prompt 30
    findings: list[PolicyFinding] = Field(default_factory=list)
    results: list[PolicyEvaluationResult] = Field(default_factory=list)


class PolicyEvaluationBatchRequest(BaseModel):
    """Request payload for running a live evaluation cycle."""

    entities: list[dict[str, Any]] = Field(
        ...,
        description="List of entity data dictionaries to evaluate",
    )
    policy_ids: list[str] | None = Field(
        default=None,
        description="Optional subset of policy IDs to evaluate (defaults to all enabled)",
    )


class PolicyEvaluationBatchResponse(BaseModel):
    """Results from live evaluation batch."""

    total_entities: int
    total_evaluations: int
    violations_detected: int
    new_findings_created: int
    existing_findings_updated: int
    findings_cleared: int
    not_evaluable_count: int
    exempted_count: int
    alerts_generated: int
    findings: list[PolicyFinding] = Field(default_factory=list)
