"""Canonical Domain Enums for CloudLens Enterprise Data Model."""

from enum import StrEnum


class ProviderType(StrEnum):
    """Supported cloud providers and canonical system boundary."""

    AWS = "aws"
    AZURE = "azure"
    GCP = "gcp"
    OCI = "oci"
    CANONICAL = "canonical"


# Alias for CloudProvider across domain layers
CloudProvider = ProviderType


class ScopeRole(StrEnum):
    """Canonical roles for multi-cloud scope hierarchy (Prompt 05 Item 31)."""

    TENANT = "TENANT"
    ROOT_GROUP = "ROOT_GROUP"
    GROUP = "GROUP"
    BILLING_BOUNDARY = "BILLING_BOUNDARY"
    SUB_GROUP = "SUB_GROUP"
    BILLING_ACCOUNT = "BILLING_ACCOUNT"


class ScopeAbsenceReason(StrEnum):
    """Explicit reasons why a scope level may be absent in a given provider topology."""

    NOT_APPLICABLE_TO_PROVIDER = "NOT_APPLICABLE_TO_PROVIDER"
    FLAT_TOPOLOGY = "FLAT_TOPOLOGY"
    NOT_PROVISIONED = "NOT_PROVISIONED"


class MeasureNullState(StrEnum):
    """Four-state null discipline for measures (Prompt 05 Item 36).

    Bare nulls are banned for all measures. Every absent measure must explicitly declare:
    - NO_COST: Incurred genuinely 0 cost/consumption, verified by provider.
    - NO_DATA: Telemetry or billing record not received / missing for period.
    - NOT_APPLICABLE: Metric does not apply to this service or pricing construct.
    - NOT_SUPPORTED: The provider does not emit or export this metric.
    """

    NO_COST = "NO_COST"
    NO_DATA = "NO_DATA"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    NOT_SUPPORTED = "NOT_SUPPORTED"


class PricingStatus(StrEnum):
    """Canonical resource pricing classification per BBP Section 16."""

    FREE = "FREE"
    FREE_TIER = "FREE_TIER"
    CONDITIONAL_FREE = "CONDITIONAL_FREE"
    PAID = "PAID"
    ESTIMATED = "ESTIMATED"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class OriginType(StrEnum):
    """Data provenance origin for Data Dictionary per Prompt 05 Item 38."""

    DISCOVERED = "DISCOVERED"  # Discovered automatically by cloud provider connectors
    DERIVED = "DERIVED"  # Computed or calculated by domain engines (e.g. FOCUS effective cost)
    CURATED = "CURATED"  # Manually entered, tagged, or overridden by enterprise administrators


class ServiceCategory(StrEnum):
    """Standardized service categories across all cloud providers."""

    COMPUTE = "COMPUTE"
    STORAGE = "STORAGE"
    NETWORKING = "NETWORKING"
    DATABASE = "DATABASE"
    SECURITY_IDENTITY = "SECURITY_IDENTITY"
    ANALYTICS = "ANALYTICS"
    AI_ML = "AI_ML"
    MANAGEMENT_GOVERNANCE = "MANAGEMENT_GOVERNANCE"
    INTEGRATION = "INTEGRATION"
    DEVELOPER_TOOLS = "DEVELOPER_TOOLS"
    OTHER = "OTHER"


class RuntimeStatus(StrEnum):
    """Operational lifecycle state of a cloud resource."""

    RUNNING = "RUNNING"
    STOPPED = "STOPPED"
    TERMINATED = "TERMINATED"
    DEALLOCATED = "DEALLOCATED"
    SUSPENDED = "SUSPENDED"
    UNKNOWN = "UNKNOWN"


class ChargeCategory(StrEnum):
    """FOCUS 1.0 charge categories for CostFacts."""

    USAGE = "Usage"
    PURCHASE = "Purchase"
    ADJUSTMENT = "Adjustment"
    TAX = "Tax"
    CREDIT = "Credit"


class CostSourceType(StrEnum):
    """Six canonical cost source types per FOCUS and Prompt 47 Item 29 / Prompt 36."""

    INVOICE = "INVOICE"
    METERED = "METERED"
    ESTIMATED = "ESTIMATED"
    ALLOCATED = "ALLOCATED"
    ADJUSTED = "ADJUSTED"
    AMORTISED = "AMORTISED"


class PricingModel(StrEnum):
    """Standard pricing model definitions."""

    ON_DEMAND = "OnDemand"
    SPOT = "Spot"
    RESERVED_1_YR = "Reserved1Yr"
    RESERVED_3_YR = "Reserved3Yr"
    TIERED = "Tiered"


class BudgetPeriod(StrEnum):
    """Budget cycle frequency (Prompt 28)."""

    MONTHLY = "MONTHLY"
    QUARTERLY = "QUARTERLY"
    ANNUAL = "ANNUAL"
    FISCAL_YEAR = "FISCAL_YEAR"
    CUSTOM = "CUSTOM"


class PolicySeverity(StrEnum):
    """Governance policy violation severity."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class PolicyStatus(StrEnum):
    """Governance finding resolution status."""

    OPEN = "OPEN"
    RESOLVED = "RESOLVED"
    SUPPRESSED = "SUPPRESSED"


class DependencyType(StrEnum):
    """Cross-resource dependency relationships (Prompt 32 / BBP Section 24)."""

    # Eight Canonical Relationship Types (Prompt 32)
    LOGICAL_DEPENDENCY = "LOGICAL_DEPENDENCY"
    NETWORK_CONNECTIVITY = "NETWORK_CONNECTIVITY"
    APPLICATION_DEPENDENCY = "APPLICATION_DEPENDENCY"
    DATA_FLOW = "DATA_FLOW"
    SECURITY_RELATIONSHIP = "SECURITY_RELATIONSHIP"
    SHARED_SERVICE = "SHARED_SERVICE"
    BILLING_RELATIONSHIP = "BILLING_RELATIONSHIP"
    PARENT_CHILD = "PARENT_CHILD"

    # Backward-compatible values for legacy fixtures
    NETWORK = "NETWORK"
    STORAGE_ATTACHMENT = "STORAGE_ATTACHMENT"
    IAM_ROLE = "IAM_ROLE"
    DATABASE_CLIENT = "DATABASE_CLIENT"
    EVENT_SUBSCRIPTION = "EVENT_SUBSCRIPTION"


# Canonical alias for relationship type
RelationshipType = DependencyType


class DependencyDirection(StrEnum):
    """Directionality of resource dependency."""

    INBOUND = "INBOUND"
    OUTBOUND = "OUTBOUND"
    BIDIRECTIONAL = "BIDIRECTIONAL"


class AlertSeverity(StrEnum):
    """Alert notification severity level."""

    INFO = "INFO"
    WARNING = "WARNING"
    HIGH = "HIGH"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class AlertStatus(StrEnum):
    """Alert lifecycle state."""

    ACTIVE = "ACTIVE"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"
    AUTO_RESOLVED = "AUTO_RESOLVED"
    GROUPED = "GROUPED"
    SUPPRESSED = "SUPPRESSED"


class AlertLifecycleStatus(StrEnum):
    """Canonical lifecycle states of an alert entity (Prompt 31)."""

    ACTIVE = "ACTIVE"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"
    AUTO_RESOLVED = "AUTO_RESOLVED"
    GROUPED = "GROUPED"
    SUPPRESSED = "SUPPRESSED"


class AlertType(StrEnum):
    """Canonical twenty alert types plus storm grouping (Prompt 31, Prompt 31B, FR-560)."""

    BUDGET_THRESHOLD = "BUDGET_THRESHOLD"
    FORECAST_BUDGET_BREACH = "FORECAST_BUDGET_BREACH"
    RUNTIME_BREACH = "RUNTIME_BREACH"
    USAGE_THRESHOLD = "USAGE_THRESHOLD"
    UNEXPECTED_COST_INCREASE = "UNEXPECTED_COST_INCREASE"
    MISSING_DATA = "MISSING_DATA"
    STALE_CONNECTOR = "STALE_CONNECTOR"
    CONNECTOR_FAILURE = "CONNECTOR_FAILURE"
    RESOURCE_WITHOUT_OWNER = "RESOURCE_WITHOUT_OWNER"
    RESOURCE_WITHOUT_MANDATORY_TAGS = "RESOURCE_WITHOUT_MANDATORY_TAGS"
    DEPENDENCY_CHANGE = "DEPENDENCY_CHANGE"
    NEW_SERVICE_DETECTED = "NEW_SERVICE_DETECTED"
    DELETED_SERVICE = "DELETED_SERVICE"
    UNEXPECTED_RESOURCE_CREATION = "UNEXPECTED_RESOURCE_CREATION"
    CREDENTIAL_EXPIRING = "CREDENTIAL_EXPIRING"
    RECONCILIATION_FAILED = "RECONCILIATION_FAILED"
    # Extended master catalogue alert types (Prompt 31B, Addendum B)
    QUOTA_HEADROOM_LOW = "QUOTA_HEADROOM_LOW"
    COMMITMENT_EXPIRING = "COMMITMENT_EXPIRING"
    PROVISIONING_REQUEST_DECIDED = "PROVISIONING_REQUEST_DECIDED"
    ANALYTICAL_EXTRACT_LATE_OR_EMPTY = "ANALYTICAL_EXTRACT_LATE_OR_EMPTY"
    # Scope storm parent alert
    SCOPE_STORM_GROUPED = "SCOPE_STORM_GROUPED"
    # Extended operational alerts & aliases
    QUOTA_HEADROOM_BREACH = "QUOTA_HEADROOM_BREACH"
    CREDENTIAL_EXPIRED = "CREDENTIAL_EXPIRED"


class ContextualAlertType(StrEnum):
    """Six inline contextual alert types (Prompt 31)."""

    COST_INFORMATION = "COST_INFORMATION"
    FREE_TIER = "FREE_TIER"
    BUDGET = "BUDGET"
    FORECAST = "FORECAST"
    PRICING_CHANGE = "PRICING_CHANGE"
    PRICING_UNAVAILABLE = "PRICING_UNAVAILABLE"


class ContextualAlertVisibility(StrEnum):
    """UI presentation surfaces for contextual alerts (Prompt 31)."""

    PAGE_INLINE = "PAGE_INLINE"
    RESOURCE_HEADER = "RESOURCE_HEADER"
    BILLING_BANNER = "BILLING_BANNER"
    MODAL = "MODAL"


class DeliveryOutcome(StrEnum):
    """Delivery tracking outcome for alert dispatches (Prompt 31)."""

    DELIVERED = "DELIVERED"
    FAILED = "FAILED"
    QUEUED = "QUEUED"
    SUPPRESSED_QUIET_HOURS = "SUPPRESSED_QUIET_HOURS"
    BUFFERED_FOR_DIGEST = "BUFFERED_FOR_DIGEST"
    GROUPED_INTO_STORM = "GROUPED_INTO_STORM"


class EscalationState(StrEnum):
    """Escalation progression states for unacknowledged alerts (Prompt 31)."""

    NONE = "NONE"
    PENDING = "PENDING"
    ESCALATED = "ESCALATED"
    ACKNOWLEDGED = "ACKNOWLEDGED"


class NotificationChannel(StrEnum):
    """Outbound alerting delivery channels."""

    EMAIL = "EMAIL"
    SLACK = "SLACK"
    WEBHOOK = "WEBHOOK"
    PAGERDUTY = "PAGERDUTY"
    TEAMS = "TEAMS"
    IN_APP = "IN_APP"
    JIRA = "JIRA"
    SERVICENOW = "SERVICENOW"


class NotificationStatus(StrEnum):
    """Notification dispatch outcome."""

    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"


class SyncJobStatus(StrEnum):
    """Connector ingestion job status."""

    SCHEDULED = "SCHEDULED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class SyncType(StrEnum):
    """The seven canonical synchronization execution modes (Prompt 15 Item 97)."""

    INITIAL_DISCOVERY = "initial_discovery"
    FULL_SYNC = "full_sync"
    INCREMENTAL_SYNC = "incremental_sync"
    SCHEDULED_SYNC = "scheduled_sync"
    MANUAL_SYNC = "manual_sync"
    ON_DEMAND_SINGLE_ENTITY_REFRESH = "on_demand_single_entity_refresh"
    BACKFILL = "backfill"


class WizardStep(StrEnum):
    """The thirteen canonical onboarding wizard progression steps (Prompt 15 Item 100)."""

    SELECT_PROVIDER = "select_provider"
    SELECT_CONNECTION_METHOD = "select_connection_method"
    ENTER_CREDENTIALS = "enter_credentials"
    VALIDATE_CREDENTIALS = "validate_credentials"
    VALIDATE_PERMISSIONS = "validate_permissions"
    DISCOVER_SCOPES = "discover_scopes"
    SELECT_SCOPES = "select_scopes"
    CONFIGURE_SYNCHRONISATION = "configure_synchronisation"
    CONFIGURE_COST_INGESTION = "configure_cost_ingestion"
    CONFIGURE_RESOURCE_DISCOVERY = "configure_resource_discovery"
    CONFIGURE_USAGE_MONITORING = "configure_usage_monitoring"
    CONFIGURE_BUDGETS_THRESHOLDS = "configure_budgets_thresholds"
    TEST_ALERT_DELIVERY = "test_alert_delivery"
    COMPLETE = "complete"


class SyncStageStatus(StrEnum):
    """Execution status of visible stages during first synchronization (Prompt 15B Item 21)."""

    NOT_STARTED = "not_started"
    RUNNING = "running"
    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"


class QuarantineReason(StrEnum):
    """Dead-letter quarantine classifications for ingested data failure (Prompt 15 Item 99)."""

    SCHEMA_VIOLATION = "SCHEMA_VIOLATION"
    MONETARY_SANITY_FAILURE = "MONETARY_SANITY_FAILURE"
    MISSING_REQUIRED_FIELDS = "MISSING_REQUIRED_FIELDS"
    UNPARSEABLE_PAYLOAD = "UNPARSEABLE_PAYLOAD"
    RATE_LIMIT_EXHAUSTED = "RATE_LIMIT_EXHAUSTED"


class QuarantineStatus(StrEnum):
    """Lifecycle status of a quarantined dead-letter record (Prompt 15 Item 99)."""

    QUARANTINED = "QUARANTINED"
    REVIEWED = "REVIEWED"
    REPROCESSED = "REPROCESSED"
    DISCARDED = "DISCARDED"


class SystemRole(StrEnum):
    """Nine built-in canonical roles for enterprise FinOps RBAC (Prompt 49A Item 9)."""

    GLOBAL_ADMIN = "GLOBAL_ADMIN"
    TENANT_ADMIN = "TENANT_ADMIN"
    FINOPS_ADMIN = "FINOPS_ADMIN"
    FINOPS_ANALYST = "FINOPS_ANALYST"
    FINOPS_VIEWER = "FINOPS_VIEWER"
    CLOUD_ARCHITECT = "CLOUD_ARCHITECT"
    DEVELOPER = "DEVELOPER"
    SECURITY_AUDITOR = "SECURITY_AUDITOR"
    TENANT_USER = "TENANT_USER"


class ProviderCapability(StrEnum):
    """Supported cloud provider capability groups (Prompt 49A Item 11, AM-07)."""

    C01_HIERARCHY = "C-01"
    C02_INVENTORY = "C-02"
    C03_COST = "C-03"
    C04_USAGE = "C-04"
    C11_PRICING = "C-11"
    C18_QUOTA = "C-18"


class ConnectorCapability(StrEnum):
    """The seventeen canonical connector capabilities (Prompt 14 Item 89, BBP Section 26)."""

    AUTHENTICATE = "authenticate"
    VALIDATE_PERMISSIONS = "validate_permissions"
    DISCOVER_ORGANIZATIONS = "discover_organizations"
    DISCOVER_ACCOUNTS = "discover_accounts"
    DISCOVER_HIERARCHY = "discover_hierarchy"
    DISCOVER_RESOURCES = "discover_resources"
    DISCOVER_SERVICES = "discover_services"
    COLLECT_COST_BULK = "collect_cost_bulk"
    COLLECT_COST_QUERY = "collect_cost_query"
    COLLECT_USAGE = "collect_usage"
    COLLECT_PRICING_PUBLIC = "collect_pricing_public"
    COLLECT_PRICING_NEGOTIATED = "collect_pricing_negotiated"
    COLLECT_TAGS = "collect_tags"
    DISCOVER_RELATIONSHIPS = "discover_relationships"
    COLLECT_BUDGETS = "collect_budgets"
    HEALTH_STATUS = "health_status"
    PROVIDER_METADATA = "provider_metadata"


class ConnectorLifecycleState(StrEnum):
    """Connector lifecycle states and transitions (Prompt 14 Item 91)."""

    REGISTERED = "REGISTERED"
    CREDENTIAL_BOUND = "CREDENTIAL_BOUND"
    VALIDATED = "VALIDATED"
    ACTIVE = "ACTIVE"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"
    SUSPENDED = "SUSPENDED"


class CapabilityHealth(StrEnum):
    """Health state of an individual capability (Prompt 14 Item 91)."""

    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"
    DISABLED = "DISABLED"


class CircuitBreakerState(StrEnum):
    """Circuit breaker state for capability calls (Prompt 14 Item 92)."""

    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class AuthMethod(StrEnum):
    """Platform authentication mechanism (Prompt 10 Items 64, 65, 67)."""

    OIDC = "OIDC"
    SAML = "SAML"
    BREAK_GLASS = "BREAK_GLASS"
    CLIENT_CREDENTIALS = "CLIENT_CREDENTIALS"


class UserStatus(StrEnum):
    """Platform user lifecycle state (Prompt 10 Item 66)."""

    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"
    LOCKED = "LOCKED"


class TokenType(StrEnum):
    """Cryptographic token classifications (Prompt 10 Items 66-68)."""

    ACCESS = "ACCESS"
    REFRESH = "REFRESH"
    STEP_UP = "STEP_UP"
    MACHINE_ACCESS = "MACHINE_ACCESS"


class StepUpAction(StrEnum):
    """Protected operations mandating step-up authentication (Prompt 10 Item 68)."""

    CREDENTIAL_CREATION = "CREDENTIAL_CREATION"
    OVERRIDE_APPLICATION = "OVERRIDE_APPLICATION"
    BUDGET_APPROVAL = "BUDGET_APPROVAL"


class GrantEffect(StrEnum):
    """Effect of a scope grant (Prompt 11 Item 71-72)."""

    ALLOW = "ALLOW"
    DENY = "DENY"


class GranteeType(StrEnum):
    """Subject type receiving a scope grant (Prompt 11 Item 71)."""

    USER = "USER"
    ROLE = "ROLE"


class FinancialSensitivity(StrEnum):
    """Financial data visibility tiers (Prompt 11 Item 71, 73)."""

    FULL_FINANCIAL_DETAIL = "FULL_FINANCIAL_DETAIL"
    COST_TOTALS_ONLY = "COST_TOTALS_ONLY"
    NON_FINANCIAL = "NON_FINANCIAL"


class ScopingDimension(StrEnum):
    """Eight canonical scoping dimensions for fine-grained authorization (Prompt 11 Item 71)."""

    PROVIDER = "provider"
    ACCOUNT_BILLING_BOUNDARY = "account_billing_boundary"
    HIERARCHY_SUBTREE = "hierarchy_subtree"
    PROJECT_APPLICATION = "project_application"
    COST_CENTRE_BUSINESS_UNIT = "cost_centre_business_unit"
    FINANCIAL_DATA_SENSITIVITY = "financial_data_sensitivity"
    ADMINISTRATIVE = "administrative"
    RESOURCE_EXCEPTION = "resource_exception"


class CredentialType(StrEnum):
    """Supported cloud provider authentication mechanism types (Prompt 12 Item 77)."""

    ROLE_ARN = "ROLE_ARN"
    OIDC_FEDERATION = "OIDC_FEDERATION"
    SERVICE_PRINCIPAL = "SERVICE_PRINCIPAL"
    SERVICE_ACCOUNT_KEY = "SERVICE_ACCOUNT_KEY"
    API_SIGNING_KEY = "API_SIGNING_KEY"
    CLIENT_SECRET = "CLIENT_SECRET"


class RotationState(StrEnum):
    """Lifecycle rotation state for provider credentials (Prompt 12 Item 78)."""

    ACTIVE = "ACTIVE"
    ROTATING = "ROTATING"
    RETIRED = "RETIRED"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"


class AuditEventType(StrEnum):
    """Full canonical taxonomy of audit event types (Prompt 13 Item 86)."""

    # Authentication & Session
    AUTH_LOGIN_SUCCESS = "AUTH_LOGIN_SUCCESS"
    AUTH_LOGIN_FAILURE = "AUTH_LOGIN_FAILURE"
    AUTH_LOGOUT = "AUTH_LOGOUT"
    AUTH_SESSION_REVOKED = "AUTH_SESSION_REVOKED"
    AUTH_STEP_UP_CHALLENGE = "AUTH_STEP_UP_CHALLENGE"
    AUTH_STEP_UP_VERIFIED = "AUTH_STEP_UP_VERIFIED"
    AUTH_BREAK_GLASS_USED = "AUTH_BREAK_GLASS_USED"

    # Authorization
    AUTHORISATION_DENIED = "AUTHORISATION_DENIED"

    # Configuration & Master Data
    CONFIG_CHANGED = "CONFIG_CHANGED"

    # Overrides
    OVERRIDE_CREATED = "OVERRIDE_CREATED"
    OVERRIDE_REVERTED = "OVERRIDE_REVERTED"
    OVERRIDE_EXPIRED = "OVERRIDE_EXPIRED"

    # Exports
    EXPORT_GENERATED = "EXPORT_GENERATED"

    # Credentials
    CREDENTIAL_CREATED = "CREDENTIAL_CREATED"
    CREDENTIAL_ROTATED = "CREDENTIAL_ROTATED"
    CREDENTIAL_RETIRED = "CREDENTIAL_RETIRED"
    CREDENTIAL_REVOKED = "CREDENTIAL_REVOKED"

    # Roles and Grants
    ROLE_ASSIGNED = "ROLE_ASSIGNED"
    ROLE_REVOKED = "ROLE_REVOKED"
    GRANT_CREATED = "GRANT_CREATED"
    GRANT_REVOKED = "GRANT_REVOKED"

    # Budgets and Thresholds
    BUDGET_CHANGED = "BUDGET_CHANGED"
    BUDGET_CREATED = "BUDGET_CREATED"
    BUDGET_AMENDED = "BUDGET_AMENDED"
    BUDGET_APPROVED = "BUDGET_APPROVED"
    BUDGET_REJECTED = "BUDGET_REJECTED"
    BUDGET_EVALUATED = "BUDGET_EVALUATED"
    BUDGET_NATIVE_IMPORTED = "BUDGET_NATIVE_IMPORTED"
    BUDGET_OVERLAP_DETECTED = "BUDGET_OVERLAP_DETECTED"
    THRESHOLD_CHANGED = "THRESHOLD_CHANGED"

    # Dependencies (Prompt 32)
    MANUAL_DEPENDENCY_EDIT = "MANUAL_DEPENDENCY_EDIT"
    DEPENDENCY_EDGE_CREATED = "DEPENDENCY_EDGE_CREATED"
    DEPENDENCY_EDGE_UPDATED = "DEPENDENCY_EDGE_UPDATED"
    DEPENDENCY_EDGE_DELETED = "DEPENDENCY_EDGE_DELETED"
    DEPENDENCY_DISCOVERY_COMPLETED = "DEPENDENCY_DISCOVERY_COMPLETED"
    DEPENDENCY_CONFLICT_SURFACED = "DEPENDENCY_CONFLICT_SURFACED"
    DEPENDENCY_CONFLICT_RESOLVED = "DEPENDENCY_CONFLICT_RESOLVED"
    DEPENDENCY_EDGE_MARKED_STALE = "DEPENDENCY_EDGE_MARKED_STALE"
    DEPENDENCY_BULK_IMPORTED = "DEPENDENCY_BULK_IMPORTED"
    DEPENDENCY_BILLING_SYNCED = "DEPENDENCY_BILLING_SYNCED"

    # Reports
    REPORT_GENERATED = "REPORT_GENERATED"
    REPORT_DOWNLOADED = "REPORT_DOWNLOADED"

    # Tamper & Isolation Violations
    AUDIT_MUTATION_ATTEMPT = "AUDIT_MUTATION_ATTEMPT"
    CROSS_TENANT_ACCESS_ATTEMPT = "CROSS_TENANT_ACCESS_ATTEMPT"

    # Connector Lifecycle & Capabilities (Prompt 14)
    CONNECTOR_REGISTERED = "CONNECTOR_REGISTERED"
    CONNECTOR_CREDENTIAL_BOUND = "CONNECTOR_CREDENTIAL_BOUND"
    CONNECTOR_PROBED = "CONNECTOR_PROBED"
    CONNECTOR_STATE_CHANGED = "CONNECTOR_STATE_CHANGED"
    CONNECTOR_CAPABILITY_DEGRADED = "CONNECTOR_CAPABILITY_DEGRADED"
    CONNECTOR_CAPABILITY_RECOVERED = "CONNECTOR_CAPABILITY_RECOVERED"
    CONNECTOR_RATE_LIMITED = "CONNECTOR_RATE_LIMITED"
    CONNECTOR_CIRCUIT_OPENED = "CONNECTOR_CIRCUIT_OPENED"
    CONNECTOR_PAYLOAD_LANDED = "CONNECTOR_PAYLOAD_LANDED"
    CONNECTOR_QUOTA_EXHAUSTED = "CONNECTOR_QUOTA_EXHAUSTED"

    # Sync Orchestration & Ingestion (Prompt 15)
    SYNC_STARTED = "SYNC_STARTED"
    SYNC_COMPLETED = "SYNC_COMPLETED"
    SYNC_PARTIAL = "SYNC_PARTIAL"
    SYNC_FAILED = "SYNC_FAILED"
    PAYLOAD_QUARANTINED = "PAYLOAD_QUARANTINED"
    WIZARD_STARTED = "WIZARD_STARTED"
    WIZARD_STEP_SAVED = "WIZARD_STEP_SAVED"
    WIZARD_COMPLETED = "WIZARD_COMPLETED"
    SCHEDULE_UPDATED = "SCHEDULE_UPDATED"
    DIAGNOSTIC_EXECUTION = "DIAGNOSTIC_EXECUTION"
    FAILOVER_TRIGGERED = "FAILOVER_TRIGGERED"
    ALERT_TEST_DISPATCHED = "ALERT_TEST_DISPATCHED"
    FIRST_SYNC_PROGRESS_VIEWED = "FIRST_SYNC_PROGRESS_VIEWED"

    # Usage & Monitoring (Prompt 25)
    MONITORING_TYPE_OVERRIDDEN = "MONITORING_TYPE_OVERRIDDEN"
    USAGE_EXPECTATION_CHANGED = "USAGE_EXPECTATION_CHANGED"
    TELEMETRY_GAP_DETECTED = "TELEMETRY_GAP_DETECTED"

    # Runtime & Schedules (Prompt 26)
    RUNTIME_SCHEDULE_ATTACHED = "RUNTIME_SCHEDULE_ATTACHED"
    RUNTIME_SCHEDULE_BREACH_DETECTED = "RUNTIME_SCHEDULE_BREACH_DETECTED"
    RUNTIME_EXEMPTION_CREATED = "RUNTIME_EXEMPTION_CREATED"
    RUNTIME_EXEMPTION_EXPIRED = "RUNTIME_EXEMPTION_EXPIRED"

    # Threshold Engine (Prompt 27)
    THRESHOLD_RULE_CREATED = "THRESHOLD_RULE_CREATED"
    THRESHOLD_RULE_UPDATED = "THRESHOLD_RULE_UPDATED"
    THRESHOLD_STATE_TRANSITIONED = "THRESHOLD_STATE_TRANSITIONED"
    THRESHOLD_OVERRIDE_CREATED = "THRESHOLD_OVERRIDE_CREATED"
    THRESHOLD_OVERRIDE_EXPIRED = "THRESHOLD_OVERRIDE_EXPIRED"
    THRESHOLD_STORM_GROUPED = "THRESHOLD_STORM_GROUPED"

    # Quota & Limits Headroom (Prompt 54)
    QUOTA_DISCOVERED = "QUOTA_DISCOVERED"
    QUOTA_MANUAL_RECORDED = "QUOTA_MANUAL_RECORDED"
    QUOTA_HEADROOM_ALERT_DISPATCHED = "QUOTA_HEADROOM_ALERT_DISPATCHED"
    QUOTA_INCREASE_REQUESTED = "QUOTA_INCREASE_REQUESTED"
    QUOTA_INCREASE_STATUS_UPDATED = "QUOTA_INCREASE_STATUS_UPDATED"
    QUOTA_REMEDIATION_TASK_CREATED = "QUOTA_REMEDIATION_TASK_CREATED"

    # Forecasting Engine (Prompt 29)
    FORECAST_GENERATED = "FORECAST_GENERATED"
    FORECAST_FALLBACK_TRIGGERED = "FORECAST_FALLBACK_TRIGGERED"
    FORECAST_RECOMPUTED_AFTER_RESTATEMENT = "FORECAST_RECOMPUTED_AFTER_RESTATEMENT"
    FORECAST_ACCURACY_RECORDED = "FORECAST_ACCURACY_RECORDED"

    # Policy Engine (Prompt 30)
    POLICY_CREATED = "POLICY_CREATED"
    POLICY_UPDATED = "POLICY_UPDATED"
    POLICY_VERSIONED = "POLICY_VERSIONED"
    POLICY_ENABLED = "POLICY_ENABLED"
    POLICY_DISABLED = "POLICY_DISABLED"
    POLICY_EVALUATED = "POLICY_EVALUATED"
    POLICY_FINDING_RECORDED = "POLICY_FINDING_RECORDED"
    POLICY_FINDING_CLEARED = "POLICY_FINDING_CLEARED"
    POLICY_EXEMPTION_CREATED = "POLICY_EXEMPTION_CREATED"
    POLICY_EXEMPTION_EXPIRED = "POLICY_EXEMPTION_EXPIRED"

    # Alerting & Notifications (Prompt 31, Prompt 31B)
    ALERT_GENERATED = "ALERT_GENERATED"
    ALERT_ACKNOWLEDGED = "ALERT_ACKNOWLEDGED"
    ALERT_RESOLVED = "ALERT_RESOLVED"
    ALERT_AUTO_RESOLVED = "ALERT_AUTO_RESOLVED"
    ALERT_GROUPED = "ALERT_GROUPED"
    ALERT_ESCALATED = "ALERT_ESCALATED"
    ALERT_DELIVERED = "ALERT_DELIVERED"
    ALERT_DELIVERY_FAILED = "ALERT_DELIVERY_FAILED"
    GOVERNANCE_EXCEPTION_RAISED = "GOVERNANCE_EXCEPTION_RAISED"
    CONTEXTUAL_ALERT_DISPLAYED = "CONTEXTUAL_ALERT_DISPLAYED"
    CONTEXTUAL_ALERT_DISMISSED = "CONTEXTUAL_ALERT_DISMISSED"
    COMMITMENT_EXPIRING_ALERT_DISPATCHED = "COMMITMENT_EXPIRING_ALERT_DISPATCHED"
    PROVISIONING_REQUEST_DECIDED_ALERT_DISPATCHED = "PROVISIONING_REQUEST_DECIDED_ALERT_DISPATCHED"
    ANALYTICAL_EXTRACT_LATE_OR_EMPTY_ALERT_DISPATCHED = (
        "ANALYTICAL_EXTRACT_LATE_OR_EMPTY_ALERT_DISPATCHED"
    )
    GOVERNANCE_TASK_CREATED = "GOVERNANCE_TASK_CREATED"

    # Workflow & Approval Engine (Prompt 50)
    WORKFLOW_REQUEST_CREATED = "WORKFLOW_REQUEST_CREATED"
    WORKFLOW_REQUEST_SUBMITTED = "WORKFLOW_REQUEST_SUBMITTED"
    WORKFLOW_STAGE_APPROVED = "WORKFLOW_STAGE_APPROVED"
    WORKFLOW_STAGE_REJECTED = "WORKFLOW_STAGE_REJECTED"
    WORKFLOW_REQUEST_APPROVED = "WORKFLOW_REQUEST_APPROVED"
    WORKFLOW_REQUEST_REJECTED = "WORKFLOW_REQUEST_REJECTED"
    WORKFLOW_REQUEST_WITHDRAWN = "WORKFLOW_REQUEST_WITHDRAWN"
    WORKFLOW_REQUEST_ESCALATED = "WORKFLOW_REQUEST_ESCALATED"
    WORKFLOW_REQUEST_EXPIRED = "WORKFLOW_REQUEST_EXPIRED"
    WORKFLOW_REQUEST_APPLIED = "WORKFLOW_REQUEST_APPLIED"
    WORKFLOW_APPLICATION_FAILED = "WORKFLOW_APPLICATION_FAILED"
    WORKFLOW_DELEGATION_REGISTERED = "WORKFLOW_DELEGATION_REGISTERED"
    WORKFLOW_INFO_REQUESTED = "WORKFLOW_INFO_REQUESTED"

    # Remediation & Accountability Engine (Prompt 51)
    REMEDIATION_TASK_CREATED = "REMEDIATION_TASK_CREATED"
    REMEDIATION_TASK_ASSIGNED = "REMEDIATION_TASK_ASSIGNED"
    REMEDIATION_TASK_STATUS_CHANGED = "REMEDIATION_TASK_STATUS_CHANGED"
    REMEDIATION_TASK_RESOLVED = "REMEDIATION_TASK_RESOLVED"
    REMEDIATION_TASK_VERIFIED = "REMEDIATION_TASK_VERIFIED"
    REMEDIATION_TASK_REOPENED = "REMEDIATION_TASK_REOPENED"
    REMEDIATION_TASK_CLOSED = "REMEDIATION_TASK_CLOSED"
    REMEDIATION_TASK_DEFERRED = "REMEDIATION_TASK_DEFERRED"
    REMEDIATION_TASK_RISK_ACCEPTED = "REMEDIATION_TASK_RISK_ACCEPTED"
    REMEDIATION_TASK_DUPLICATED = "REMEDIATION_TASK_DUPLICATED"
    REMEDIATION_SAVING_REALISED = "REMEDIATION_SAVING_REALISED"
    REMEDIATION_TASK_ESCALATED = "REMEDIATION_TASK_ESCALATED"
    REMEDIATION_TASK_ITSM_MIRRORED = "REMEDIATION_TASK_ITSM_MIRRORED"


class OverrideClass(StrEnum):
    """Categorisation of operational and governance overrides (Prompt 13 Item 87)."""

    BUDGET_THRESHOLD = "BUDGET_THRESHOLD"
    TAG_POLICY = "TAG_POLICY"
    RATE_CARD = "RATE_CARD"
    FEATURE_FLAG = "FEATURE_FLAG"
    ALLOCATION_RULE = "ALLOCATION_RULE"
    RETENTION_PERIOD = "RETENTION_PERIOD"
    ALERT_DELIVERY_FAILURE = "ALERT_DELIVERY_FAILURE"
    MONITORING_TYPE = "MONITORING_TYPE"
    USAGE_EXPECTATION = "USAGE_EXPECTATION"
    RUNTIME_SCHEDULE = "RUNTIME_SCHEDULE"
    RUNTIME_EXEMPTION = "RUNTIME_EXEMPTION"
    THRESHOLD_RULE = "THRESHOLD_RULE"
    QUOTA_LIMIT = "QUOTA_LIMIT"
    FORECAST_RULE = "FORECAST_RULE"
    POLICY_EXEMPTION = "POLICY_EXEMPTION"


class OverrideStatus(StrEnum):
    """Lifecycle status of an override record (Prompt 13 Item 87)."""

    ACTIVE = "ACTIVE"
    REVERTED = "REVERTED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


# ==============================================================================
# Quota & Service Limits Enums (Prompt 54)
# ==============================================================================


class QuotaScopeType(StrEnum):
    """Scope level at which a service limit or capacity constraint applies (Prompt 54)."""

    ACCOUNT = "ACCOUNT"
    SUBSCRIPTION = "SUBSCRIPTION"
    PROJECT = "PROJECT"
    COMPARTMENT = "COMPARTMENT"
    REGION = "REGION"
    GLOBAL = "GLOBAL"


class QuotaServiceAffectingType(StrEnum):
    """Whether quota exhaustion causes service outages or request throttling (Prompt 54)."""

    SERVICE_AFFECTING = "SERVICE_AFFECTING"
    THROTTLING = "THROTTLING"


class QuotaSourceType(StrEnum):
    """Source classification for a quota limit value (Prompt 54)."""

    PROVIDER = "PROVIDER"
    MANUAL = "MANUAL"


class QuotaHeadroomState(StrEnum):
    """Operational health state of quota headroom (Prompt 54)."""

    NORMAL = "NORMAL"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    EXHAUSTED = "EXHAUSTED"
    UNKNOWN = "UNKNOWN"
    NOT_SUPPORTED = "NOT_SUPPORTED"


class QuotaIncreaseRequestStatus(StrEnum):
    """Status of a quota increase request with the cloud provider (Prompt 54)."""

    REQUESTED = "REQUESTED"
    PENDING_PROVIDER = "PENDING_PROVIDER"
    GRANTED = "GRANTED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class QuotaCoverage(StrEnum):
    """Degree of programmatic quota coverage exposed by the provider (Prompt 54)."""

    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    NOT_SUPPORTED = "NOT_SUPPORTED"


# ==============================================================================
# Budget Model Enums (Prompt 28)
# ==============================================================================


class BudgetScopeType(StrEnum):
    """Seventeen canonical scope types at which budgets can be defined (Prompt 28)."""

    ORGANISATION = "ORGANISATION"
    PROVIDER = "PROVIDER"
    MANAGEMENT_GROUP = "MANAGEMENT_GROUP"
    SUBSCRIPTION = "SUBSCRIPTION"
    AWS_OU = "AWS_OU"
    AWS_ACCOUNT = "AWS_ACCOUNT"
    GCP_FOLDER = "GCP_FOLDER"
    GCP_PROJECT = "GCP_PROJECT"
    OCI_COMPARTMENT = "OCI_COMPARTMENT"
    RESOURCE_GROUP = "RESOURCE_GROUP"
    APPLICATION = "APPLICATION"
    ENVIRONMENT = "ENVIRONMENT"
    SERVICE = "SERVICE"
    RESOURCE = "RESOURCE"
    COST_CENTRE = "COST_CENTRE"
    BUSINESS_UNIT = "BUSINESS_UNIT"
    PROJECT = "PROJECT"

    def is_logical(self) -> bool:
        """Returns True if the scope is an organizational or application logical grouping."""
        return self in (
            BudgetScopeType.ORGANISATION,
            BudgetScopeType.BUSINESS_UNIT,
            BudgetScopeType.COST_CENTRE,
            BudgetScopeType.APPLICATION,
            BudgetScopeType.ENVIRONMENT,
            BudgetScopeType.PROJECT,
            BudgetScopeType.SERVICE,
        )

    def is_native(self) -> bool:
        """Returns True if the scope is a cloud provider native infrastructure boundary."""
        return self in (
            BudgetScopeType.PROVIDER,
            BudgetScopeType.MANAGEMENT_GROUP,
            BudgetScopeType.SUBSCRIPTION,
            BudgetScopeType.AWS_OU,
            BudgetScopeType.AWS_ACCOUNT,
            BudgetScopeType.GCP_FOLDER,
            BudgetScopeType.GCP_PROJECT,
            BudgetScopeType.OCI_COMPARTMENT,
            BudgetScopeType.RESOURCE_GROUP,
            BudgetScopeType.RESOURCE,
        )


class BudgetApprovalStatus(StrEnum):
    """Lifecycle workflow approval status of a budget (Prompt 28)."""

    DRAFT = "DRAFT"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    ARCHIVED = "ARCHIVED"


class BudgetRolloverPolicy(StrEnum):
    """Policy for unspent or overspent funds at period close (Prompt 28 Phase 2)."""

    NONE = "NONE"
    ROLLOVER_SURPLUS = "ROLLOVER_SURPLUS"
    ROLLOVER_DEFICIT = "ROLLOVER_DEFICIT"
    RESET = "RESET"


class BudgetSourceType(StrEnum):
    """Source provenance of a budget: CloudLens logical vs imported provider-native (Prompt 28)."""

    CLOUDLENS_LOGICAL = "CLOUDLENS_LOGICAL"
    PROVIDER_NATIVE = "PROVIDER_NATIVE"


# ==============================================================================
# Forecasting Engine Enums (Prompt 29)
# ==============================================================================


class ForecastMethod(StrEnum):
    """Forecasting algorithms supporting MVP and Phase 2 progression (Prompt 29)."""

    # MVP methods
    RUN_RATE = "RUN_RATE"
    HISTORICAL_AVERAGE = "HISTORICAL_AVERAGE"
    MOVING_AVERAGE = "MOVING_AVERAGE"

    # Phase 2 methods (flag-gated)
    TREND_REGRESSION = "TREND_REGRESSION"
    SEASONALITY_DECOMPOSITION = "SEASONALITY_DECOMPOSITION"
    PROVIDER_PUBLISHED = "PROVIDER_PUBLISHED"
    USER_ADJUSTMENT = "USER_ADJUSTMENT"

    def is_mvp(self) -> bool:
        """Returns True if method is part of MVP baseline."""
        return self in (
            ForecastMethod.RUN_RATE,
            ForecastMethod.HISTORICAL_AVERAGE,
            ForecastMethod.MOVING_AVERAGE,
        )

    def is_phase2(self) -> bool:
        """Returns True if method is gated behind a Phase 2 feature flag."""
        return not self.is_mvp()

    def minimum_history_days(self) -> int:
        """Returns the documented minimum history in days required for this method."""
        if self == ForecastMethod.RUN_RATE:
            return 3
        elif self == ForecastMethod.MOVING_AVERAGE:
            return 7
        elif self == ForecastMethod.HISTORICAL_AVERAGE:
            return 14
        elif self == ForecastMethod.TREND_REGRESSION:
            return 14
        elif self == ForecastMethod.SEASONALITY_DECOMPOSITION:
            return 28
        elif self == ForecastMethod.PROVIDER_PUBLISHED:
            return 1
        elif self == ForecastMethod.USER_ADJUSTMENT:
            return 3
        return 3

    def feature_flag_key(self) -> str | None:
        """Returns the associated feature flag key if Phase 2 gated."""
        flags = {
            ForecastMethod.TREND_REGRESSION: "enable_trend_regression_forecasting",
            ForecastMethod.SEASONALITY_DECOMPOSITION: "enable_seasonality_forecasting",
            ForecastMethod.PROVIDER_PUBLISHED: "enable_provider_published_forecasting",
            ForecastMethod.USER_ADJUSTMENT: "enable_user_adjustment_forecasting",
        }
        return flags.get(self)


class ForecastConfidence(StrEnum):
    """Confidence rating of the forecast based on data sufficiency and volatility (Prompt 29)."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class CostTrend(StrEnum):
    """Cost momentum and trajectory direction (Prompt 29)."""

    STABLE = "STABLE"
    INCREASING = "INCREASING"
    DECREASING = "DECREASING"
    SPIKING = "SPIKING"
    VOLATILE = "VOLATILE"


class ForecastMilestone(StrEnum):
    """Evaluation checkpoint for tracking forecast error and accuracy over period lifecycle (Prompt 29)."""

    M25 = "M25"
    M50 = "M50"
    M75 = "M75"
    PERIOD_CLOSE = "PERIOD_CLOSE"


# ==============================================================================
# Policy Engine Enums (Prompt 30)
# ==============================================================================


class PolicyCategory(StrEnum):
    """Functional taxonomy of governance policies (Prompt 30, BBP Section 34)."""

    BUDGET = "BUDGET"
    RUNTIME = "RUNTIME"
    USAGE = "USAGE"
    COST_THRESHOLD = "COST_THRESHOLD"
    TAGGING = "TAGGING"
    NAMING = "NAMING"
    OWNERSHIP = "OWNERSHIP"
    CONNECTOR_HEALTH = "CONNECTOR_HEALTH"
    DATA_RETENTION = "DATA_RETENTION"
    ACCESS = "ACCESS"
    ZERO_USAGE_COST = "ZERO_USAGE_COST"
    REGION_COMPLIANCE = "REGION_COMPLIANCE"
    IDLE_RESOURCE = "IDLE_RESOURCE"
    STORAGE_HYGIENE = "STORAGE_HYGIENE"
    SKU_RESTRICTION = "SKU_RESTRICTION"
    QUOTA_CAPACITY = "QUOTA_CAPACITY"
    FINANCIAL_GOVERNANCE = "FINANCIAL_GOVERNANCE"
    BILLING_INTEGRITY = "BILLING_INTEGRITY"
    PROVISIONING_GOVERNANCE = "PROVISIONING_GOVERNANCE"


class PolicyMode(StrEnum):
    """Execution mode of a governance policy (Prompt 30)."""

    SIMULATE = "SIMULATE"
    ENFORCE = "ENFORCE"


class PolicyEffect(StrEnum):
    """Remediation or governance consequence of a policy violation (Prompt 30, Prompt 31B)."""

    AUDIT_FINDING = "AUDIT_FINDING"
    DENY = "DENY"
    FLAG = "FLAG"
    QUARANTINE_TAG = "QUARANTINE_TAG"
    NOTIFY = "NOTIFY"
    GOVERNANCE_EXCEPTION = "GOVERNANCE_EXCEPTION"
    REMEDIATION_TASK = "REMEDIATION_TASK"


class EvaluationOutcome(StrEnum):
    """Result of policy condition evaluation against an entity (Prompt 30)."""

    COMPLIANT = "COMPLIANT"
    VIOLATION = "VIOLATION"
    NOT_EVALUABLE = "NOT_EVALUABLE"
    EXEMPTED = "EXEMPTED"


class FindingLifecycleStatus(StrEnum):
    """Lifecycle status of a policy violation finding (Prompt 30)."""

    OPEN = "OPEN"
    CLEARED = "CLEARED"
    EXEMPTED = "EXEMPTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"


class ConditionOperator(StrEnum):
    """Declarative operators for policy condition expressions (Prompt 30)."""

    EQUALS = "EQUALS"
    NOT_EQUALS = "NOT_EQUALS"
    GREATER_THAN = "GREATER_THAN"
    GREATER_THAN_OR_EQUAL = "GREATER_THAN_OR_EQUAL"
    LESS_THAN = "LESS_THAN"
    LESS_THAN_OR_EQUAL = "LESS_THAN_OR_EQUAL"
    CONTAINS = "CONTAINS"
    NOT_CONTAINS = "NOT_CONTAINS"
    IN = "IN"
    NOT_IN = "NOT_IN"
    MATCHES_REGEX = "MATCHES_REGEX"
    IS_NULL = "IS_NULL"
    IS_NOT_NULL = "IS_NOT_NULL"
    ALL_PRESENT = "ALL_PRESENT"
    ANY_PRESENT = "ANY_PRESENT"
    IN_APPROVED_LIST = "IN_APPROVED_LIST"
    NOT_IN_APPROVED_LIST = "NOT_IN_APPROVED_LIST"


class LogicalOperator(StrEnum):
    """Compound condition combinators (Prompt 30)."""

    AND = "AND"
    OR = "OR"
    NOT = "NOT"


class WorkflowState(StrEnum):
    """Lifecycle states of a workflow request (Prompt 50).

    States: Draft, Submitted, In Review, Approved, Rejected, Withdrawn, Expired, Applied.
    """

    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    IN_REVIEW = "IN_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    WITHDRAWN = "WITHDRAWN"
    EXPIRED = "EXPIRED"
    APPLIED = "APPLIED"


class ApprovalChainMode(StrEnum):
    """Execution mode of an approval chain stage (Prompt 50)."""

    SERIAL = "SERIAL"
    PARALLEL = "PARALLEL"


class DecisionOutcome(StrEnum):
    """Actions an approver can take on a pending request (Prompt 50)."""

    APPROVE = "APPROVE"
    REJECT = "REJECT"
    REQUEST_MORE_INFO = "REQUEST_MORE_INFO"


class ApproverResolutionType(StrEnum):
    """Dynamic resolution strategy for stage approvers (Prompt 50)."""

    ROLE = "ROLE"
    SCOPE_OWNERSHIP = "SCOPE_OWNERSHIP"
    COST_CENTRE_OWNER = "COST_CENTRE_OWNER"
    BUSINESS_UNIT_OWNER = "BUSINESS_UNIT_OWNER"
    BUDGET_OWNER = "BUDGET_OWNER"
    EXPLICIT_LIST = "EXPLICIT_LIST"


class WorkflowRequestType(StrEnum):
    """Canonical request types wired into the generic workflow engine (Prompt 50)."""

    BUDGET_APPROVAL = "BUDGET_APPROVAL"
    OVERRIDE_APPROVAL = "OVERRIDE_APPROVAL"
    POLICY_EXEMPTION = "POLICY_EXEMPTION"
    CUSTOM_ROLE_CREATION = "CUSTOM_ROLE_CREATION"
    MASTER_DATA_CHANGE = "MASTER_DATA_CHANGE"
    TENANT_LIFECYCLE = "TENANT_LIFECYCLE"
    CONNECTOR_DELETION = "CONNECTOR_DELETION"
    COST_MODEL_CHANGE = "COST_MODEL_CHANGE"
    ALLOCATION_RULE_CHANGE = "ALLOCATION_RULE_CHANGE"
    RETENTION_CHANGE = "RETENTION_CHANGE"
    RATE_CARD_UPLOAD = "RATE_CARD_UPLOAD"


class TaskState(StrEnum):
    """Lifecycle states of a remediation task (Prompt 51).

    Minimum 11 states: Open, Assigned, In Progress, Blocked, Awaiting Verification,
    Resolved, Verified, Closed, Rejected, Deferred, Duplicate.
    """

    OPEN = "OPEN"
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    BLOCKED = "BLOCKED"
    AWAITING_VERIFICATION = "AWAITING_VERIFICATION"
    RESOLVED = "RESOLVED"
    VERIFIED = "VERIFIED"
    CLOSED = "CLOSED"
    REJECTED = "REJECTED"
    DEFERRED = "DEFERRED"
    DUPLICATE = "DUPLICATE"


class TaskPriority(StrEnum):
    """Urgency priorities for remediation tasks (Prompt 51)."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class TaskCategory(StrEnum):
    """Canonical categories of remediation tasks (Prompt 51)."""

    UNOWNED_RESOURCE = "UNOWNED_RESOURCE"
    TAG_COMPLIANCE = "TAG_COMPLIANCE"
    SCHEDULE_BREACH = "SCHEDULE_BREACH"
    BUDGET_BREACH = "BUDGET_BREACH"
    FORECAST_BREACH = "FORECAST_BREACH"
    IDLE_RESOURCE = "IDLE_RESOURCE"
    STALE_CONNECTOR = "STALE_CONNECTOR"
    CREDENTIAL_EXPIRING = "CREDENTIAL_EXPIRING"
    RECONCILIATION_VARIANCE = "RECONCILIATION_VARIANCE"
    UNKNOWN_SKU = "UNKNOWN_SKU"
    UNCLASSIFIED_RESOURCE = "UNCLASSIFIED_RESOURCE"
    MASTERDATA_GAP = "MASTERDATA_GAP"
    CUSTOM = "CUSTOM"


class TaskSource(StrEnum):
    """Originating trigger or detection source for remediation tasks (Prompt 51)."""

    ALERT = "ALERT"
    POLICY_FINDING = "POLICY_FINDING"
    GOVERNANCE_EXCEPTION = "GOVERNANCE_EXCEPTION"
    RECONCILIATION_VARIANCE = "RECONCILIATION_VARIANCE"
    MANUAL = "MANUAL"
    SCHEDULE_BREACH = "SCHEDULE_BREACH"
    BUDGET_BREACH = "BUDGET_BREACH"
    FORECAST_BREACH = "FORECAST_BREACH"
    UNOWNED_RESOURCE = "UNOWNED_RESOURCE"
    TAG_COMPLIANCE = "TAG_COMPLIANCE"
    IDLE_RESOURCE = "IDLE_RESOURCE"
    STALE_CONNECTOR = "STALE_CONNECTOR"
    CREDENTIAL_EXPIRING = "CREDENTIAL_EXPIRING"
    UNKNOWN_SKU = "UNKNOWN_SKU"
    UNCLASSIFIED_RESOURCE = "UNCLASSIFIED_RESOURCE"
    MASTERDATA_GAP = "MASTERDATA_GAP"


class TaskClosureCode(StrEnum):
    """Closure rationale codes for remediation tasks (Prompt 51)."""

    FIXED_AND_VERIFIED = "FIXED_AND_VERIFIED"
    FALSE_POSITIVE = "FALSE_POSITIVE"
    RISK_ACCEPTED = "RISK_ACCEPTED"
    DUPLICATE_SUPERSEDED = "DUPLICATE_SUPERSEDED"
    RESOURCE_TERMINATED = "RESOURCE_TERMINATED"


class TaskAssignmentRule(StrEnum):
    """Precedence rule used to resolve task assignee (Prompt 51)."""

    TECHNICAL_OWNER = "TECHNICAL_OWNER"
    SCOPE_OWNER = "SCOPE_OWNER"
    APPLICATION_OWNER = "APPLICATION_OWNER"
    FALLBACK_QUEUE = "FALLBACK_QUEUE"
    MANUAL = "MANUAL"


class RealisedSavingMethod(StrEnum):
    """Empirical method used to calculate realised savings (Prompt 51)."""

    SCHEDULE_EXCESS_AVOIDANCE = "SCHEDULE_EXCESS_AVOIDANCE"
    IDLE_TERMINATION_DELTA = "IDLE_TERMINATION_DELTA"
    RUN_RATE_ELIMINATION = "RUN_RATE_ELIMINATION"
    RIGHTSIZING_DIFF = "RIGHTSIZING_DIFF"
    DIRECT_ESTIMATE_VERIFIED = "DIRECT_ESTIMATE_VERIFIED"


# ==============================================================================
# Dependency & Topology Enums (Prompt 32 / BBP Section 24)
# ==============================================================================


class EntityReferenceType(StrEnum):
    """Supported entity reference types for dependency edges (Prompt 32)."""

    RESOURCE = "RESOURCE"
    SERVICE = "SERVICE"
    APPLICATION = "APPLICATION"
    SCOPE = "SCOPE"


class EdgeConfidenceLevel(StrEnum):
    """Honest confidence ratings across discovery and curation layers (Prompt 32)."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    AS_ASSERTED = "AS_ASSERTED"


class EdgeCriticality(StrEnum):
    """Operational criticality of a dependency edge (Prompt 32)."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class EdgeStatus(StrEnum):
    """Lifecycle status of a dependency relationship edge (Prompt 32)."""

    ACTIVE = "ACTIVE"
    STALE = "STALE"
    CONFLICT = "CONFLICT"
    RESOLVED = "RESOLVED"
    DELETED = "DELETED"
    SUPERSEDED = "SUPERSEDED"


class EdgeProvenanceType(StrEnum):
    """Provenance origin of a dependency edge (Prompt 32)."""

    DISCOVERED = "DISCOVERED"
    MANUAL = "MANUAL"
    IMPORTED = "IMPORTED"
    INFERRED = "INFERRED"


class DiscoveryLayer(StrEnum):
    """The four discovery layers + explicit naming inference (Prompt 32)."""

    STRUCTURAL = "STRUCTURAL"
    NETWORK = "NETWORK"
    PROVIDER_PLATFORM = "PROVIDER_PLATFORM"
    CURATED_APPLICATION = "CURATED_APPLICATION"
    INFERRED_NAMING = "INFERRED_NAMING"


class ConflictResolutionAction(StrEnum):
    """Action taken to resolve a discovered vs manual edge conflict (Prompt 32)."""

    KEEP_MANUAL = "KEEP_MANUAL"
    ACCEPT_DISCOVERED = "ACCEPT_DISCOVERED"
    MERGE = "MERGE"
