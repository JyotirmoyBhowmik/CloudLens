"""Canonical Default Policy Catalogue (Prompt 30, BBP Section 34, FR-746).

Enforces:
- FR-746: Ship sixteen default policies covering budget, runtime, usage, cost threshold,
  tagging, naming, ownership, connector health, data retention, access, zero-usage cost,
  and region compliance.
- Strict constraint: All disabled by default except connector health (POL-08),
  because a platform that starts shouting on day one gets muted on day two.
"""

from __future__ import annotations

import datetime as dt

from domain.models.enums import (
    ConditionOperator,
    PolicyCategory,
    PolicyEffect,
    PolicyMode,
    PolicySeverity,
)
from domain.policy.models import (
    DeclarativeCondition,
    PolicyDefinition,
    TargetSelector,
)


def get_default_policy_definitions() -> list[PolicyDefinition]:
    """Instantiates the authoritative catalogue of default policies (POL-01 to POL-18).

    All policies are disabled by default with mode=SIMULATE, EXCEPT POL-08 (Connector Health)
    which is enabled by default with mode=ENFORCE.
    """
    now = dt.datetime(2026, 1, 1, 0, 0, 0, tzinfo=dt.UTC)

    policies = [
        # POL-01: Budget
        PolicyDefinition(
            id="POL-01",
            version=1,
            name="Budget Overrun Guardrail",
            description="Identifies scopes where actual spend has exceeded 100% of the allocated budget amount.",
            category=PolicyCategory.BUDGET,
            target_selector=TargetSelector(),
            condition=DeclarativeCondition(
                operator=ConditionOperator.LESS_THAN_OR_EQUAL,
                field="budget_utilization_pct",
                value=100.0,
            ),
            effect=PolicyEffect.AUDIT_FINDING,
            severity=PolicySeverity.CRITICAL,
            evaluation_schedule="DAILY",
            mode=PolicyMode.SIMULATE,
            enabled=False,
            is_default=True,
            created_at=now,
            updated_at=now,
        ),
        # POL-02: Runtime
        PolicyDefinition(
            id="POL-02",
            version=1,
            name="Runtime Schedule Non-Adherence",
            description="Flags resources running outside their approved operational schedule or exceeding allowable off-hours runtime.",
            category=PolicyCategory.RUNTIME,
            target_selector=TargetSelector(resource_types=["COMPUTE_INSTANCE", "VIRTUAL_MACHINE"]),
            condition=DeclarativeCondition(
                operator=ConditionOperator.EQUALS,
                field="is_schedule_compliant",
                value=True,
            ),
            effect=PolicyEffect.AUDIT_FINDING,
            severity=PolicySeverity.HIGH,
            evaluation_schedule="HOURLY",
            mode=PolicyMode.SIMULATE,
            enabled=False,
            is_default=True,
            created_at=now,
            updated_at=now,
        ),
        # POL-03: Usage
        PolicyDefinition(
            id="POL-03",
            version=1,
            name="Usage Spike Exceeds Baseline",
            description="Flags resources whose current usage metric exceeds 150% of the 30-day baseline average.",
            category=PolicyCategory.USAGE,
            target_selector=TargetSelector(),
            condition=DeclarativeCondition(
                operator=ConditionOperator.LESS_THAN_OR_EQUAL,
                field="usage_ratio_to_baseline",
                value=1.5,
            ),
            effect=PolicyEffect.AUDIT_FINDING,
            severity=PolicySeverity.MEDIUM,
            evaluation_schedule="DAILY",
            mode=PolicyMode.SIMULATE,
            enabled=False,
            is_default=True,
            created_at=now,
            updated_at=now,
        ),
        # POL-04: Cost Threshold
        PolicyDefinition(
            id="POL-04",
            version=1,
            name="Cost Spike Velocity Guardrail",
            description="Detects sudden daily spend surges exceeding 100% growth compared to the historical baseline.",
            category=PolicyCategory.COST_THRESHOLD,
            target_selector=TargetSelector(),
            condition=DeclarativeCondition(
                operator=ConditionOperator.LESS_THAN_OR_EQUAL,
                field="cost_velocity_growth_pct",
                value=100.0,
            ),
            effect=PolicyEffect.AUDIT_FINDING,
            severity=PolicySeverity.HIGH,
            evaluation_schedule="DAILY",
            mode=PolicyMode.SIMULATE,
            enabled=False,
            is_default=True,
            created_at=now,
            updated_at=now,
        ),
        # POL-05: Tagging
        PolicyDefinition(
            id="POL-05",
            version=1,
            name="Mandatory Governance Tagging Compliance",
            description="Requires all cloud resources to bear mandatory CostCenter, Environment, and Owner tags.",
            category=PolicyCategory.TAGGING,
            target_selector=TargetSelector(),
            condition=DeclarativeCondition(
                operator=ConditionOperator.ALL_PRESENT,
                field="tags",
                value=["CostCenter", "Environment", "Owner"],
            ),
            effect=PolicyEffect.AUDIT_FINDING,
            severity=PolicySeverity.MEDIUM,
            evaluation_schedule="DAILY",
            mode=PolicyMode.SIMULATE,
            enabled=False,
            is_default=True,
            created_at=now,
            updated_at=now,
        ),
        # POL-06: Naming
        PolicyDefinition(
            id="POL-06",
            version=1,
            name="Enterprise Resource Naming Standard",
            description="Ensures all resource names follow standard convention: prefix-env-app-id.",
            category=PolicyCategory.NAMING,
            target_selector=TargetSelector(),
            condition=DeclarativeCondition(
                operator=ConditionOperator.MATCHES_REGEX,
                field="name",
                value=r"^[a-zA-Z0-9]+-[a-zA-Z0-9]+-[a-zA-Z0-9]+-[a-zA-Z0-9]+.*$",
            ),
            effect=PolicyEffect.AUDIT_FINDING,
            severity=PolicySeverity.LOW,
            evaluation_schedule="DAILY",
            mode=PolicyMode.SIMULATE,
            enabled=False,
            is_default=True,
            created_at=now,
            updated_at=now,
        ),
        # POL-07: Ownership
        PolicyDefinition(
            id="POL-07",
            version=1,
            name="Unassigned Resource Ownership Guardrail",
            description="Flags cloud resources that do not have an identified technical or business owner.",
            category=PolicyCategory.OWNERSHIP,
            target_selector=TargetSelector(),
            condition=DeclarativeCondition(
                operator=ConditionOperator.IS_NOT_NULL,
                field="owner",
                value=None,
            ),
            effect=PolicyEffect.AUDIT_FINDING,
            severity=PolicySeverity.MEDIUM,
            evaluation_schedule="DAILY",
            mode=PolicyMode.SIMULATE,
            enabled=False,
            is_default=True,
            created_at=now,
            updated_at=now,
        ),
        # POL-08: Connector Health (ENABLED BY DEFAULT)
        PolicyDefinition(
            id="POL-08",
            version=1,
            name="Connector Synchronization Freshness SLA",
            description="Monitors active connectors to ensure synchronization latency does not exceed 24 hours.",
            category=PolicyCategory.CONNECTOR_HEALTH,
            target_selector=TargetSelector(resource_types=["CONNECTOR"]),
            condition=DeclarativeCondition(
                operator=ConditionOperator.LESS_THAN_OR_EQUAL,
                field="hours_since_last_sync",
                value=24.0,
            ),
            effect=PolicyEffect.AUDIT_FINDING,
            severity=PolicySeverity.HIGH,
            evaluation_schedule="HOURLY",
            mode=PolicyMode.ENFORCE,
            enabled=True,  # The ONLY policy enabled by default!
            is_default=True,
            created_at=now,
            updated_at=now,
        ),
        # POL-09: Data Retention
        PolicyDefinition(
            id="POL-09",
            version=1,
            name="Data Retention & Snapshot Age Exceeded",
            description="Flags backup snapshots older than 90 days that violate corporate retention limits.",
            category=PolicyCategory.DATA_RETENTION,
            target_selector=TargetSelector(resource_types=["SNAPSHOT", "BACKUP"]),
            condition=DeclarativeCondition(
                operator=ConditionOperator.LESS_THAN_OR_EQUAL,
                field="snapshot_age_days",
                value=90.0,
            ),
            effect=PolicyEffect.AUDIT_FINDING,
            severity=PolicySeverity.MEDIUM,
            evaluation_schedule="DAILY",
            mode=PolicyMode.SIMULATE,
            enabled=False,
            is_default=True,
            created_at=now,
            updated_at=now,
        ),
        # POL-10: Access
        PolicyDefinition(
            id="POL-10",
            version=1,
            name="Unrestricted Public Ingress Access Guardrail",
            description="Flags storage buckets or compute firewalls configured with open public ingress access (0.0.0.0/0).",
            category=PolicyCategory.ACCESS,
            target_selector=TargetSelector(
                resource_types=["STORAGE_BUCKET", "SECURITY_GROUP", "FIREWALL"]
            ),
            condition=DeclarativeCondition(
                operator=ConditionOperator.EQUALS,
                field="has_public_access",
                value=False,
            ),
            effect=PolicyEffect.AUDIT_FINDING,
            severity=PolicySeverity.CRITICAL,
            evaluation_schedule="CONTINUOUS",
            mode=PolicyMode.SIMULATE,
            enabled=False,
            is_default=True,
            created_at=now,
            updated_at=now,
        ),
        # POL-11: Zero Usage Cost
        PolicyDefinition(
            id="POL-11",
            version=1,
            name="Zero-Usage Cost Elimination Guardrail",
            description="Identifies resources incurring charges while recording zero usage over the last 14 days.",
            category=PolicyCategory.ZERO_USAGE_COST,
            target_selector=TargetSelector(),
            condition=DeclarativeCondition(
                operator=ConditionOperator.EQUALS,
                field="is_zombie_resource",
                value=False,
            ),
            effect=PolicyEffect.AUDIT_FINDING,
            severity=PolicySeverity.HIGH,
            evaluation_schedule="DAILY",
            mode=PolicyMode.SIMULATE,
            enabled=False,
            is_default=True,
            created_at=now,
            updated_at=now,
        ),
        # POL-12: Region Compliance
        PolicyDefinition(
            id="POL-12",
            version=1,
            name="Approved Datacenter Regions Deployment Policy",
            description="Restricts cloud resources to approved data sovereignty and compliance regions.",
            category=PolicyCategory.REGION_COMPLIANCE,
            target_selector=TargetSelector(),
            condition=DeclarativeCondition(
                operator=ConditionOperator.IN_APPROVED_LIST,
                field="region",
                value=["us-east-1", "us-west-2", "eu-west-1", "eu-central-1", "ap-southeast-1"],
            ),
            effect=PolicyEffect.AUDIT_FINDING,
            severity=PolicySeverity.CRITICAL,
            evaluation_schedule="DAILY",
            mode=PolicyMode.SIMULATE,
            enabled=False,
            is_default=True,
            created_at=now,
            updated_at=now,
        ),
        # POL-13: Idle Resource
        PolicyDefinition(
            id="POL-13",
            version=1,
            name="Idle Compute Instance Rightsizing Guardrail",
            description="Flags compute instances with low average CPU utilization (under 5%) for over 7 consecutive days.",
            category=PolicyCategory.IDLE_RESOURCE,
            target_selector=TargetSelector(resource_types=["COMPUTE_INSTANCE", "VIRTUAL_MACHINE"]),
            condition=DeclarativeCondition(
                operator=ConditionOperator.GREATER_THAN_OR_EQUAL,
                field="avg_cpu_utilization",
                value=5.0,
            ),
            effect=PolicyEffect.AUDIT_FINDING,
            severity=PolicySeverity.LOW,
            evaluation_schedule="DAILY",
            mode=PolicyMode.SIMULATE,
            enabled=False,
            is_default=True,
            created_at=now,
            updated_at=now,
        ),
        # POL-14: Storage Hygiene
        PolicyDefinition(
            id="POL-14",
            version=1,
            name="Unattached Persistent Storage Cleanup Guardrail",
            description="Identifies unattached block storage volumes orphaned for more than 7 days.",
            category=PolicyCategory.STORAGE_HYGIENE,
            target_selector=TargetSelector(resource_types=["BLOCK_VOLUME", "STORAGE_DISK"]),
            condition=DeclarativeCondition(
                operator=ConditionOperator.EQUALS,
                field="is_attached",
                value=True,
            ),
            effect=PolicyEffect.AUDIT_FINDING,
            severity=PolicySeverity.MEDIUM,
            evaluation_schedule="DAILY",
            mode=PolicyMode.SIMULATE,
            enabled=False,
            is_default=True,
            created_at=now,
            updated_at=now,
        ),
        # POL-15: SKU Restriction
        PolicyDefinition(
            id="POL-15",
            version=1,
            name="High-Performance GPU/HPC SKU Provisioning Guardrail",
            description="Restricts provisioning of ultra-high-cost specialized GPU and compute families without prior approval.",
            category=PolicyCategory.SKU_RESTRICTION,
            target_selector=TargetSelector(resource_types=["COMPUTE_INSTANCE"]),
            condition=DeclarativeCondition(
                operator=ConditionOperator.NOT_IN,
                field="sku",
                value=["p4d.24xlarge", "p5.48xlarge", "Standard_ND96asr_v4", "a2-megagpu-16g"],
            ),
            effect=PolicyEffect.AUDIT_FINDING,
            severity=PolicySeverity.HIGH,
            evaluation_schedule="DAILY",
            mode=PolicyMode.SIMULATE,
            enabled=False,
            is_default=True,
            created_at=now,
            updated_at=now,
        ),
        # POL-16: Financial Governance
        PolicyDefinition(
            id="POL-16",
            version=1,
            name="Currency & Exchange Rate Freshness SLA",
            description="Flags stale exchange rates where published currency conversion latency exceeds 48 hours.",
            category=PolicyCategory.FINANCIAL_GOVERNANCE,
            target_selector=TargetSelector(),
            condition=DeclarativeCondition(
                operator=ConditionOperator.LESS_THAN_OR_EQUAL,
                field="fx_rate_age_hours",
                value=48.0,
            ),
            effect=PolicyEffect.AUDIT_FINDING,
            severity=PolicySeverity.MEDIUM,
            evaluation_schedule="DAILY",
            mode=PolicyMode.SIMULATE,
            enabled=False,
            is_default=True,
            created_at=now,
            updated_at=now,
        ),
        # POL-17: Quota Capacity (Prompt 31B, Addendum B, closes D-09)
        PolicyDefinition(
            id="POL-17",
            version=1,
            name="Quota Headroom Capacity Guardrail",
            description="Quota headroom below the configured threshold raises a finding and a task.",
            category=PolicyCategory.QUOTA_CAPACITY,
            target_selector=TargetSelector(),
            condition=DeclarativeCondition(
                operator=ConditionOperator.GREATER_THAN_OR_EQUAL,
                field="quota_headroom_pct",
                value=10.0,
            ),
            effect=PolicyEffect.AUDIT_FINDING,
            severity=PolicySeverity.HIGH,
            evaluation_schedule="DAILY",
            mode=PolicyMode.SIMULATE,
            enabled=False,  # Disabled by default
            is_default=True,
            created_at=now,
            updated_at=now,
        ),
        # POL-18: Gated Scope Provisioning Approval (Prompt 31B, Addendum B, closes D-09)
        PolicyDefinition(
            id="POL-18",
            version=1,
            name="Gated Scope Provisioning Approval Guardrail",
            description="A resource deployed in a gated scope with no matching approved provisioning request raises a governance exception and a task.",
            category=PolicyCategory.PROVISIONING_GOVERNANCE,
            target_selector=TargetSelector(),
            condition=DeclarativeCondition(
                operator=ConditionOperator.EQUALS,
                field="has_approved_provisioning_request",
                value=True,
            ),
            effect=PolicyEffect.GOVERNANCE_EXCEPTION,
            severity=PolicySeverity.CRITICAL,
            evaluation_schedule="CONTINUOUS",
            mode=PolicyMode.SIMULATE,
            enabled=False,  # Disabled by default
            is_default=True,
            created_at=now,
            updated_at=now,
        ),
    ]

    return policies
