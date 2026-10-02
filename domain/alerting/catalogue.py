"""Authoritative Master Data Alert Catalogue (Prompt 31, Prompt 31B, BBP Section 35.1, FR-560).

Enforces:
- FR-560: The system must support all twenty alert types (AL-01 to AL-20) defined in the alert catalogue.
- Closes defect D-08: Alert catalogue extends with four Addendum B types (AL-17 to AL-20).
- All twenty alert types resolve from master data with no code-side enumeration.
- Master data recipient routing roles for automated governance dispatch without special-casing.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from domain.models.enums import AlertSeverity, AlertType


class AlertCatalogueDefinition(BaseModel):
    """Immutable master data definition of a canonical alert type in the catalogue."""

    id: str = Field(..., description="Stable catalogue identifier (AL-01 to AL-20)")
    code: str = Field(..., description="Canonical programmatic code identifier")
    name: str = Field(..., description="Human-readable title")
    alert_type: AlertType = Field(..., description="AlertType enum member")
    default_severity: AlertSeverity = Field(..., description="Default operational severity")
    description: str = Field(..., description="Detailed description of alert semantics")
    trigger_condition: str = Field(..., description="Empirical condition triggering the alert")
    default_routing_roles: list[str] = Field(
        default_factory=list, description="Target recipient roles resolved from master data"
    )
    event_name: str = Field(..., description="Canonical outbound event name (Prompt 60)")
    category: str = Field(default="OPERATIONAL", description="Functional category")


_DEFAULT_CATALOGUE: list[AlertCatalogueDefinition] = [
    # AL-01: Budget Threshold
    AlertCatalogueDefinition(
        id="AL-01",
        code="BUDGET_THRESHOLD",
        name="Budget Threshold Exceeded",
        alert_type=AlertType.BUDGET_THRESHOLD,
        default_severity=AlertSeverity.WARNING,
        description="Triggered when cumulative spend exceeds a configured budget percentage threshold.",
        trigger_condition="Actual spend > configured threshold % of budget amount",
        default_routing_roles=["owner", "budget_owner"],
        event_name="alert.budget_threshold",
        category="FINANCIAL",
    ),
    # AL-02: Forecast Budget Breach
    AlertCatalogueDefinition(
        id="AL-02",
        code="FORECAST_BUDGET_BREACH",
        name="Predicted Budget Overrun Breach",
        alert_type=AlertType.FORECAST_BUDGET_BREACH,
        default_severity=AlertSeverity.HIGH,
        description="Triggered when forward-looking run-rate or trend forecast projects spend exceeding 100% of budget before end of period.",
        trigger_condition="Forecast end-of-period cost > budget amount",
        default_routing_roles=["owner", "budget_owner"],
        event_name="alert.forecast_budget_breach",
        category="FINANCIAL",
    ),
    # AL-03: Runtime Breach
    AlertCatalogueDefinition(
        id="AL-03",
        code="RUNTIME_BREACH",
        name="Runtime Schedule Adherence Breach",
        alert_type=AlertType.RUNTIME_BREACH,
        default_severity=AlertSeverity.WARNING,
        description="Triggered when compute resources operate outside scheduled business hours without active exemption.",
        trigger_condition="Resource running state detected outside schedule window and warning/critical tolerance",
        default_routing_roles=["owner", "technical_owner"],
        event_name="alert.runtime_breach",
        category="OPERATIONAL",
    ),
    # AL-04: Usage Threshold
    AlertCatalogueDefinition(
        id="AL-04",
        code="USAGE_THRESHOLD",
        name="Resource Usage Metric Spike",
        alert_type=AlertType.USAGE_THRESHOLD,
        default_severity=AlertSeverity.WARNING,
        description="Triggered when monitored resource consumption metrics breach defined utilization bands.",
        trigger_condition="Observed usage metric value breaches threshold band",
        default_routing_roles=["owner", "technical_owner"],
        event_name="alert.usage_threshold",
        category="OPERATIONAL",
    ),
    # AL-05: Unexpected Cost Increase
    AlertCatalogueDefinition(
        id="AL-05",
        code="UNEXPECTED_COST_INCREASE",
        name="Unexpected Spend Surge Anomaly",
        alert_type=AlertType.UNEXPECTED_COST_INCREASE,
        default_severity=AlertSeverity.HIGH,
        description="Triggered when daily or hourly spend accelerates beyond baseline growth tolerance.",
        trigger_condition="Observed spend velocity exceeds baseline by configured growth percentage",
        default_routing_roles=["owner", "finops_lead"],
        event_name="alert.unexpected_cost_increase",
        category="FINANCIAL",
    ),
    # AL-06: Missing Data
    AlertCatalogueDefinition(
        id="AL-06",
        code="MISSING_DATA",
        name="Billing Telemetry Ingestion Missing Data",
        alert_type=AlertType.MISSING_DATA,
        default_severity=AlertSeverity.HIGH,
        description="Triggered when expected provider billing line items or metric telemetry feeds are interrupted.",
        trigger_condition="Ingestion window elapses with zero records received when data was expected",
        default_routing_roles=["cloud_administrator", "platform_administrator"],
        event_name="alert.missing_data",
        category="INTEGRATION",
    ),
    # AL-07: Stale Connector
    AlertCatalogueDefinition(
        id="AL-07",
        code="STALE_CONNECTOR",
        name="Cloud Provider Connector Synchronization Stale",
        alert_type=AlertType.STALE_CONNECTOR,
        default_severity=AlertSeverity.WARNING,
        description="Triggered when a cloud provider integration exceeds maximum synchronization latency SLA.",
        trigger_condition="Time since last successful synchronization > freshness threshold hours",
        default_routing_roles=["cloud_administrator"],
        event_name="alert.stale_connector",
        category="INTEGRATION",
    ),
    # AL-08: Connector Failure
    AlertCatalogueDefinition(
        id="AL-08",
        code="CONNECTOR_FAILURE",
        name="Cloud Provider Connector Synchronization Failure",
        alert_type=AlertType.CONNECTOR_FAILURE,
        default_severity=AlertSeverity.CRITICAL,
        description="Triggered when connector discovery or extraction fails with permanent or authentication errors.",
        trigger_condition="Connector sync run terminates with fatal exception or exhausted retries",
        default_routing_roles=["cloud_administrator"],
        event_name="alert.connector_failure",
        category="INTEGRATION",
    ),
    # AL-09: Resource Without Owner
    AlertCatalogueDefinition(
        id="AL-09",
        code="RESOURCE_WITHOUT_OWNER",
        name="Unassigned Resource Ownership Anomaly",
        alert_type=AlertType.RESOURCE_WITHOUT_OWNER,
        default_severity=AlertSeverity.WARNING,
        description="Triggered when discovered cloud infrastructure lacks technical and business ownership metadata.",
        trigger_condition="Resource tags and metadata contain no owner, Owner, contact, or team attribute",
        default_routing_roles=["cloud_administrator", "scope_owner"],
        event_name="alert.resource_without_owner",
        category="GOVERNANCE",
    ),
    # AL-10: Resource Without Mandatory Tags
    AlertCatalogueDefinition(
        id="AL-10",
        code="RESOURCE_WITHOUT_MANDATORY_TAGS",
        name="Mandatory Governance Tagging Missing",
        alert_type=AlertType.RESOURCE_WITHOUT_MANDATORY_TAGS,
        default_severity=AlertSeverity.WARNING,
        description="Triggered when resources lack required governance tags (CostCenter, Environment, Owner).",
        trigger_condition="Required mandatory tags missing from resource metadata",
        default_routing_roles=["owner", "scope_owner"],
        event_name="alert.resource_without_mandatory_tags",
        category="GOVERNANCE",
    ),
    # AL-11: Dependency Change
    AlertCatalogueDefinition(
        id="AL-11",
        code="DEPENDENCY_CHANGE",
        name="Topology Dependency Relationship Modification",
        alert_type=AlertType.DEPENDENCY_CHANGE,
        default_severity=AlertSeverity.INFO,
        description="Triggered when critical infrastructure upstream or downstream dependencies are altered.",
        trigger_condition="Topology graph edge changed for mapped critical service dependency",
        default_routing_roles=["technical_owner"],
        event_name="alert.dependency_change",
        category="OPERATIONAL",
    ),
    # AL-12: New Service Detected
    AlertCatalogueDefinition(
        id="AL-12",
        code="NEW_SERVICE_DETECTED",
        name="New Cloud Service Type Discovered",
        alert_type=AlertType.NEW_SERVICE_DETECTED,
        default_severity=AlertSeverity.INFO,
        description="Triggered when an estate introduces a newly detected cloud service family not previously seen.",
        trigger_condition="Service family code absent from estate historical service catalogue",
        default_routing_roles=["cloud_administrator", "procurement"],
        event_name="alert.new_service_detected",
        category="GOVERNANCE",
    ),
    # AL-13: Deleted Service
    AlertCatalogueDefinition(
        id="AL-13",
        code="DELETED_SERVICE",
        name="Deregistered Cloud Service Deletion",
        alert_type=AlertType.DELETED_SERVICE,
        default_severity=AlertSeverity.INFO,
        description="Triggered when a previously tracked service family is completely terminated or removed.",
        trigger_condition="Active count of service family drops to zero across monitored scopes",
        default_routing_roles=["cloud_administrator"],
        event_name="alert.deleted_service",
        category="OPERATIONAL",
    ),
    # AL-14: Unexpected Resource Creation
    AlertCatalogueDefinition(
        id="AL-14",
        code="UNEXPECTED_RESOURCE_CREATION",
        name="Unapproved Out-of-Band Resource Creation",
        alert_type=AlertType.UNEXPECTED_RESOURCE_CREATION,
        default_severity=AlertSeverity.HIGH,
        description="Triggered when high-cost resources are provisioned outside approved deployment windows.",
        trigger_condition="Discovered resource creation event with no matching approved change or tag",
        default_routing_roles=["cloud_administrator", "security_lead"],
        event_name="alert.unexpected_resource_creation",
        category="GOVERNANCE",
    ),
    # AL-15: Credential Expiring
    AlertCatalogueDefinition(
        id="AL-15",
        code="CREDENTIAL_EXPIRING",
        name="Connector Authentication Credential Expiring",
        alert_type=AlertType.CREDENTIAL_EXPIRING,
        default_severity=AlertSeverity.WARNING,
        description="Triggered when OAuth certificates, service principal secrets, or IAM keys approach expiry.",
        trigger_condition="Credential expiration date <= configured warning lead time days",
        default_routing_roles=["cloud_administrator"],
        event_name="alert.credential_expiring",
        category="SECURITY",
    ),
    # AL-16: Reconciliation Failed
    AlertCatalogueDefinition(
        id="AL-16",
        code="RECONCILIATION_FAILED",
        name="Invoice and Metered Usage Reconciliation Mismatch",
        alert_type=AlertType.RECONCILIATION_FAILED,
        default_severity=AlertSeverity.CRITICAL,
        description="Triggered when invoiced FOCUS charges disagree with metered line items beyond acceptable tolerance.",
        trigger_condition="Abs(invoiced_total - metered_total) > reconciliation tolerance",
        default_routing_roles=["finops_lead", "procurement"],
        event_name="alert.reconciliation_failed",
        category="FINANCIAL",
    ),
    # AL-17: Quota Headroom Low (Prompt 31B, Addendum B, closes D-08)
    AlertCatalogueDefinition(
        id="AL-17",
        code="QUOTA_HEADROOM_LOW",
        name="Quota Headroom Low",
        alert_type=AlertType.QUOTA_HEADROOM_LOW,
        default_severity=AlertSeverity.WARNING,  # default severity medium rising to high as exhaustion date approaches
        description="Triggered at predicted exhaustion minus lead time minus safety margin for cloud provider service limits.",
        trigger_condition="Days until exhaustion <= provider lead time + safety margin (severity elevates to HIGH as date approaches)",
        default_routing_roles=["technical_owner", "cloud_administrator"],
        event_name="alert.quota_headroom_low",
        category="CAPACITY",
    ),
    # AL-18: Commitment Expiring (Prompt 31B, Addendum B, closes D-08)
    AlertCatalogueDefinition(
        id="AL-18",
        code="COMMITMENT_EXPIRING",
        name="Commitment Reservation Expiring",
        alert_type=AlertType.COMMITMENT_EXPIRING,
        default_severity=AlertSeverity.WARNING,
        description="Triggered at configured renewal lead time before compute reservation, savings plan, or committed use discount expires.",
        trigger_condition="Commitment end date - current date <= configured renewal lead time days",
        default_routing_roles=["commitment_owner", "procurement"],
        event_name="alert.commitment_expiring",
        category="FINANCIAL",
    ),
    # AL-19: Provisioning Request Decided (Prompt 31B, Addendum B, closes D-08)
    AlertCatalogueDefinition(
        id="AL-19",
        code="PROVISIONING_REQUEST_DECIDED",
        name="Provisioning Request Decided",
        alert_type=AlertType.PROVISIONING_REQUEST_DECIDED,
        default_severity=AlertSeverity.INFO,
        description="Triggered when an infrastructure provisioning request has been reviewed and decided (approved or rejected).",
        trigger_condition="State transition of provisioning request to APPROVED or REJECTED",
        default_routing_roles=["requester"],
        event_name="alert.provisioning_request_decided",
        category="GOVERNANCE",
    ),
    # AL-20: Analytical Extract Late or Empty (Prompt 31B, Addendum B, closes D-08)
    AlertCatalogueDefinition(
        id="AL-20",
        code="ANALYTICAL_EXTRACT_LATE_OR_EMPTY",
        name="Analytical Extract Late or Empty",
        alert_type=AlertType.ANALYTICAL_EXTRACT_LATE_OR_EMPTY,
        default_severity=AlertSeverity.INFO,
        description="Triggered when a scheduled analytical export extract is delayed beyond SLA or completes with zero records.",
        trigger_condition="Extract job run exceeds SLA completion deadline or produces empty recordset (0 bytes / 0 rows)",
        default_routing_roles=["platform_administrator"],
        event_name="alert.analytical_extract_late_or_empty",
        category="INTEGRATION",
    ),
]


def get_default_alert_catalogue() -> list[AlertCatalogueDefinition]:
    """Returns the complete, authoritative master data catalogue of default alert types (AL-01 to AL-20)."""
    return [d.model_copy() for d in _DEFAULT_CATALOGUE]


def get_alert_catalogue_map() -> dict[str, AlertCatalogueDefinition]:
    """Returns alert catalogue definitions indexed by ID (e.g. 'AL-01', 'AL-17')."""
    return {d.id: d.model_copy() for d in _DEFAULT_CATALOGUE}


def get_alert_definition_by_id(alert_id: str) -> AlertCatalogueDefinition | None:
    """Finds an alert catalogue definition by its stable catalogue ID (e.g. 'AL-17')."""
    clean_id = alert_id.strip().upper()
    for definition in _DEFAULT_CATALOGUE:
        if definition.id.upper() == clean_id:
            return definition.model_copy()
    return None


def get_alert_definition_by_type(
    alert_type: AlertType | str,
) -> AlertCatalogueDefinition | None:
    """Finds an alert catalogue definition by its AlertType enum or string representation."""
    type_str = alert_type.value if isinstance(alert_type, AlertType) else str(alert_type)
    # Support backwards-compatible alias
    if type_str == "QUOTA_HEADROOM_BREACH":
        type_str = "QUOTA_HEADROOM_LOW"

    for definition in _DEFAULT_CATALOGUE:
        if definition.alert_type.value == type_str or definition.code == type_str:
            return definition.model_copy()
    return None
