"""Canonical Domain Enums for CloudLens Enterprise Data Model."""

from enum import Enum


class ProviderType(str, Enum):
    """Supported cloud providers and canonical system boundary."""

    AWS = "aws"
    AZURE = "azure"
    GCP = "gcp"
    OCI = "oci"
    CANONICAL = "canonical"


class ScopeRole(str, Enum):
    """Canonical roles for multi-cloud scope hierarchy (Prompt 05 Item 31)."""

    TENANT = "TENANT"
    ROOT_GROUP = "ROOT_GROUP"
    GROUP = "GROUP"
    BILLING_BOUNDARY = "BILLING_BOUNDARY"
    SUB_GROUP = "SUB_GROUP"
    BILLING_ACCOUNT = "BILLING_ACCOUNT"


class ScopeAbsenceReason(str, Enum):
    """Explicit reasons why a scope level may be absent in a given provider topology."""

    NOT_APPLICABLE_TO_PROVIDER = "NOT_APPLICABLE_TO_PROVIDER"
    FLAT_TOPOLOGY = "FLAT_TOPOLOGY"
    NOT_PROVISIONED = "NOT_PROVISIONED"


class MeasureNullState(str, Enum):
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


class PricingStatus(str, Enum):
    """Canonical resource pricing classification per BBP Section 16."""

    FREE = "FREE"
    FREE_TIER = "FREE_TIER"
    CONDITIONAL_FREE = "CONDITIONAL_FREE"
    PAID = "PAID"
    ESTIMATED = "ESTIMATED"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class OriginType(str, Enum):
    """Data provenance origin for Data Dictionary per Prompt 05 Item 38."""

    DISCOVERED = "DISCOVERED"  # Discovered automatically by cloud provider connectors
    DERIVED = "DERIVED"  # Computed or calculated by domain engines (e.g. FOCUS effective cost)
    CURATED = "CURATED"  # Manually entered, tagged, or overridden by enterprise administrators


class ServiceCategory(str, Enum):
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
    OTHER = "OTHER"


class RuntimeStatus(str, Enum):
    """Operational lifecycle state of a cloud resource."""

    RUNNING = "RUNNING"
    STOPPED = "STOPPED"
    TERMINATED = "TERMINATED"
    DEALLOCATED = "DEALLOCATED"
    SUSPENDED = "SUSPENDED"
    UNKNOWN = "UNKNOWN"


class ChargeCategory(str, Enum):
    """FOCUS 1.0 charge categories for CostFacts."""

    USAGE = "Usage"
    PURCHASE = "Purchase"
    ADJUSTMENT = "Adjustment"
    TAX = "Tax"
    CREDIT = "Credit"


class PricingModel(str, Enum):
    """Standard pricing model definitions."""

    ON_DEMAND = "OnDemand"
    SPOT = "Spot"
    RESERVED_1_YR = "Reserved1Yr"
    RESERVED_3_YR = "Reserved3Yr"
    TIERED = "Tiered"


class BudgetPeriod(str, Enum):
    """Budget cycle frequency."""

    MONTHLY = "MONTHLY"
    QUARTERLY = "QUARTERLY"
    ANNUAL = "ANNUAL"


class PolicySeverity(str, Enum):
    """Governance policy violation severity."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class PolicyStatus(str, Enum):
    """Governance finding resolution status."""

    OPEN = "OPEN"
    RESOLVED = "RESOLVED"
    SUPPRESSED = "SUPPRESSED"


class DependencyType(str, Enum):
    """Cross-resource dependency relationships."""

    NETWORK = "NETWORK"
    STORAGE_ATTACHMENT = "STORAGE_ATTACHMENT"
    IAM_ROLE = "IAM_ROLE"
    DATABASE_CLIENT = "DATABASE_CLIENT"
    EVENT_SUBSCRIPTION = "EVENT_SUBSCRIPTION"


class DependencyDirection(str, Enum):
    """Directionality of resource dependency."""

    INBOUND = "INBOUND"
    OUTBOUND = "OUTBOUND"
    BIDIRECTIONAL = "BIDIRECTIONAL"


class AlertSeverity(str, Enum):
    """Alert notification severity level."""

    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class AlertStatus(str, Enum):
    """Alert lifecycle state."""

    ACTIVE = "ACTIVE"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"


class NotificationChannel(str, Enum):
    """Outbound alerting delivery channels."""

    EMAIL = "EMAIL"
    SLACK = "SLACK"
    WEBHOOK = "WEBHOOK"
    PAGERDUTY = "PAGERDUTY"
    TEAMS = "TEAMS"


class NotificationStatus(str, Enum):
    """Notification dispatch outcome."""

    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"


class SyncJobStatus(str, Enum):
    """Connector ingestion job status."""

    SCHEDULED = "SCHEDULED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
