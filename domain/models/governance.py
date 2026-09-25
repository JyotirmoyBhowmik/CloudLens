"""Governance, Policy, Budgeting, and Lifecycle Entities.

Enforces Prompt 05 Item 34:
"Implement the governance entities: Budget, Forecast, ThresholdSet, ThresholdState,
Policy, PolicyFinding, Dependency, Alert, Notification, SyncJob, AuditEvent, Override."
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import Field

from domain.models.base import CanonicalEntity
from domain.models.enums import (
    AlertSeverity,
    AlertStatus,
    BudgetPeriod,
    DependencyDirection,
    DependencyType,
    NotificationChannel,
    NotificationStatus,
    PolicySeverity,
    PolicyStatus,
    ProviderType,
    SyncJobStatus,
)
from domain.models.measures import FinancialMeasure
from domain.rules.thresholds import ThresholdBand


class ThresholdSet(CanonicalEntity):
    """Configured percentage evaluation boundaries for budget consumption."""

    name: str = Field(..., description="Threshold configuration profile name")
    amber_percentage: Decimal = Field(
        default=Decimal("80.0"), description="Warning threshold percentage"
    )
    red_percentage: Decimal = Field(
        default=Decimal("90.0"), description="Action required threshold percentage"
    )
    critical_percentage: Decimal = Field(
        default=Decimal("100.0"), description="Breach threshold percentage"
    )


class ThresholdState(CanonicalEntity):
    """Evaluated runtime budget band status snapshot."""

    budget_id: str = Field(..., description="Target Budget ID")
    current_spend: FinancialMeasure = Field(..., description="Current consumption amount")
    current_band: ThresholdBand = Field(
        ..., description="Evaluated band: NORMAL, AMBER, RED, CRITICAL"
    )
    evaluated_at: datetime = Field(..., description="Evaluation timestamp in UTC")


class Budget(CanonicalEntity):
    """Financial ceiling allocation for a specific Scope node."""

    tenant_id: str = Field(..., description="Organization tenant ID")
    scope_id: str = Field(..., description="Target Scope node ID (Subscription, Account, Group)")
    name: str = Field(..., description="Budget descriptor")
    amount: FinancialMeasure = Field(..., description="Budgeted currency ceiling (no bare nulls)")
    period: BudgetPeriod = Field(
        default=BudgetPeriod.MONTHLY, description="MONTHLY, QUARTERLY, or ANNUAL"
    )
    start_date: date = Field(..., description="Budget cycle start date")
    end_date: date | None = Field(default=None, description="Optional cycle end date")
    threshold_set_id: str | None = Field(default=None, description="Linked ThresholdSet profile ID")


class Forecast(CanonicalEntity):
    """Predictive cost projection."""

    budget_id: str | None = Field(default=None, description="Associated Budget ID if applicable")
    scope_id: str = Field(..., description="Target Scope ID")
    forecast_period_start: datetime = Field(..., description="Projection period start in UTC")
    forecast_period_end: datetime = Field(..., description="Projection period end in UTC")
    projected_amount: FinancialMeasure = Field(..., description="Projected spend amount")
    confidence_score: float = Field(default=0.95, description="Statistical confidence (0.0 to 1.0)")
    forecast_model: str = Field(
        default="ENSEMBLE", description="Model algorithm used (LINEAR, ARIMA, ENSEMBLE)"
    )


class Policy(CanonicalEntity):
    """FinOps and cloud governance rule definition."""

    name: str = Field(..., description="Policy rule title")
    rule_type: str = Field(
        ..., description="Rule category: TAG_COMPLIANCE, BUDGET_CAP, IDLE_RESOURCE"
    )
    severity: PolicySeverity = Field(
        default=PolicySeverity.MEDIUM, description="Policy breach severity"
    )
    parameters: dict[str, Any] = Field(
        default_factory=dict, description="Rule evaluation criteria and thresholds"
    )


class PolicyFinding(CanonicalEntity):
    """Detected non-compliance incident."""

    policy_id: str = Field(..., description="Violated Policy ID")
    resource_id: str = Field(..., description="Non-compliant Resource ID")
    status: PolicyStatus = Field(
        default=PolicyStatus.OPEN, description="OPEN, RESOLVED, SUPPRESSED"
    )
    details: str = Field(..., description="Descriptive explanation of non-compliance")
    detected_at: datetime = Field(..., description="Detection timestamp in UTC")


class Dependency(CanonicalEntity):
    """Cross-resource operational dependency link."""

    source_resource_id: str = Field(..., description="Dependent Resource ID")
    target_resource_id: str = Field(..., description="Prerequisite Resource ID")
    dependency_type: DependencyType = Field(default=DependencyType.NETWORK, description="Link type")
    direction: DependencyDirection = Field(
        default=DependencyDirection.OUTBOUND, description="Link direction"
    )


class Alert(CanonicalEntity):
    """High-priority platform notification event."""

    tenant_id: str = Field(..., description="Organization tenant ID")
    alert_type: str = Field(..., description="Alert classification (e.g. BUDGET_EXCEEDED, ANOMALY)")
    severity: AlertSeverity = Field(
        default=AlertSeverity.WARNING, description="Alert urgency level"
    )
    message: str = Field(..., description="Human-readable notification text")
    status: AlertStatus = Field(
        default=AlertStatus.ACTIVE, description="ACTIVE, ACKNOWLEDGED, RESOLVED"
    )
    triggered_at: datetime = Field(..., description="Trigger timestamp in UTC")


class Notification(CanonicalEntity):
    """Outbound dispatch of an Alert to communication channels."""

    alert_id: str = Field(..., description="Associated Alert ID")
    channel: NotificationChannel = Field(..., description="EMAIL, SLACK, WEBHOOK, PAGERDUTY, TEAMS")
    recipient: str = Field(..., description="Destination address, URL, or channel name")
    status: NotificationStatus = Field(
        default=NotificationStatus.PENDING, description="PENDING, SENT, FAILED"
    )
    sent_at: datetime | None = Field(default=None, description="Dispatch timestamp in UTC")


class SyncJob(CanonicalEntity):
    """Connector data ingestion and reconciliation execution audit."""

    connector_type: ProviderType = Field(..., description="Target cloud provider connector")
    scope_id: str = Field(..., description="Target root scope node")
    status: SyncJobStatus = Field(
        default=SyncJobStatus.SCHEDULED, description="Job progress status"
    )
    started_at: datetime = Field(..., description="Execution start in UTC")
    completed_at: datetime | None = Field(default=None, description="Completion timestamp in UTC")
    rows_ingested: int = Field(default=0, description="Total normalized records processed")
    error_message: str | None = Field(default=None, description="Error diagnostics if failed")


class AuditEvent(CanonicalEntity):
    """Immutable enterprise compliance audit log record."""

    tenant_id: str = Field(..., description="Organization tenant ID")
    actor_id: str = Field(..., description="Identity of principal who performed mutation")
    action: str = Field(
        ..., description="Action descriptor (e.g. SCOPE_REPARENTED, BUDGET_MODIFIED)"
    )
    entity_type: str = Field(..., description="Target entity class name")
    entity_id: str = Field(..., description="Target entity ID")
    payload_before: dict[str, Any] | None = Field(default=None, description="Pre-mutation snapshot")
    payload_after: dict[str, Any] | None = Field(default=None, description="Post-mutation snapshot")
    timestamp: datetime = Field(..., description="Mutation timestamp in UTC")
    correlation_id: str = Field(..., description="Distributed tracing correlation ID")


class Override(CanonicalEntity):
    """Administrative manual curation or cost adjustment override."""

    entity_type: str = Field(..., description="Target entity class name (e.g. Resource, CostFact)")
    entity_id: str = Field(..., description="Target entity ID")
    field_name: str = Field(..., description="Target attribute name being overridden")
    override_value: Any = Field(..., description="Curated value applied over discovered data")
    reason: str = Field(..., description="Business justification for manual override")
    created_by: str = Field(..., description="Admin email or principal identifier")
    expires_at: datetime | None = Field(
        default=None, description="Optional sunset expiration timestamp"
    )
