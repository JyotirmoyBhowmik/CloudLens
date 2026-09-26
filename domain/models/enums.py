"""Canonical Domain Enums for CloudLens Enterprise Data Model."""

from enum import StrEnum


class ProviderType(StrEnum):
    """Supported cloud providers and canonical system boundary."""

    AWS = "aws"
    AZURE = "azure"
    GCP = "gcp"
    OCI = "oci"
    CANONICAL = "canonical"


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
    """Budget cycle frequency."""

    MONTHLY = "MONTHLY"
    QUARTERLY = "QUARTERLY"
    ANNUAL = "ANNUAL"


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
    """Cross-resource dependency relationships."""

    NETWORK = "NETWORK"
    STORAGE_ATTACHMENT = "STORAGE_ATTACHMENT"
    IAM_ROLE = "IAM_ROLE"
    DATABASE_CLIENT = "DATABASE_CLIENT"
    EVENT_SUBSCRIPTION = "EVENT_SUBSCRIPTION"


class DependencyDirection(StrEnum):
    """Directionality of resource dependency."""

    INBOUND = "INBOUND"
    OUTBOUND = "OUTBOUND"
    BIDIRECTIONAL = "BIDIRECTIONAL"


class AlertSeverity(StrEnum):
    """Alert notification severity level."""

    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class AlertStatus(StrEnum):
    """Alert lifecycle state."""

    ACTIVE = "ACTIVE"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"


class NotificationChannel(StrEnum):
    """Outbound alerting delivery channels."""

    EMAIL = "EMAIL"
    SLACK = "SLACK"
    WEBHOOK = "WEBHOOK"
    PAGERDUTY = "PAGERDUTY"
    TEAMS = "TEAMS"


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
    FAILED = "FAILED"


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
