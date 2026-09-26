"""CloudLens Canonical Domain Models.

Provider-agnostic domain model enabling four clouds (AWS, Azure, GCP, OCI) to be compared
without destroying what makes each one different.
"""

from domain.models.base import CanonicalEntity, ProvenanceRecord
from domain.models.enums import (
    AlertSeverity,
    AlertStatus,
    BudgetPeriod,
    ChargeCategory,
    CostSourceType,
    DependencyDirection,
    DependencyType,
    MeasureNullState,
    NotificationChannel,
    NotificationStatus,
    OriginType,
    PolicySeverity,
    PolicyStatus,
    PricingModel,
    PricingStatus,
    ProviderType,
    RuntimeStatus,
    ScopeAbsenceReason,
    ScopeRole,
    ServiceCategory,
    SyncJobStatus,
)
from domain.models.exceptions import (
    DemoModeSafetyException,
    DomainModelException,
    HistoricalAttributionException,
    InvalidScopeHierarchyException,
    MeasureAbsentException,
    MeasureNullForbiddenException,
)
from domain.models.facts import (
    CostFact,
    PricingDimension,
    PricingRecord,
    RuntimeState,
    UsageFact,
)
from domain.models.governance import (
    Alert,
    AuditEvent,
    Budget,
    Dependency,
    Forecast,
    Notification,
    Override,
    Policy,
    PolicyFinding,
    SyncJob,
    ThresholdSet,
    ThresholdState,
)
from domain.models.inventory import (
    Application,
    AvailabilityZone,
    BusinessUnit,
    CostCenter,
    Environment,
    Owner,
    Project,
    Region,
    Resource,
    ResourceType,
    Service,
    Tag,
)
from domain.models.measures import FinancialMeasure, Measure, QuantityMeasure
from domain.models.scope import Scope, ScopeHistory, ScopeTree

__all__ = [
    # Base & Provenance
    "CanonicalEntity",
    "ProvenanceRecord",
    # Enums
    "ProviderType",
    "ScopeRole",
    "ScopeAbsenceReason",
    "MeasureNullState",
    "PricingStatus",
    "OriginType",
    "ServiceCategory",
    "RuntimeStatus",
    "ChargeCategory",
    "CostSourceType",
    "PricingModel",
    "BudgetPeriod",
    "PolicySeverity",
    "PolicyStatus",
    "DependencyType",
    "DependencyDirection",
    "AlertSeverity",
    "AlertStatus",
    "NotificationChannel",
    "NotificationStatus",
    "SyncJobStatus",
    # Exceptions
    "DomainModelException",
    "DemoModeSafetyException",
    "MeasureNullForbiddenException",
    "MeasureAbsentException",
    "InvalidScopeHierarchyException",
    "HistoricalAttributionException",
    # Measures
    "Measure",
    "FinancialMeasure",
    "QuantityMeasure",
    # Scope
    "Scope",
    "ScopeHistory",
    "ScopeTree",
    # Inventory
    "Tag",
    "Service",
    "ResourceType",
    "Region",
    "AvailabilityZone",
    "Owner",
    "BusinessUnit",
    "CostCenter",
    "Project",
    "Application",
    "Environment",
    "Resource",
    # Facts
    "CostFact",
    "UsageFact",
    "RuntimeState",
    "PricingDimension",
    "PricingRecord",
    # Governance
    "ThresholdSet",
    "ThresholdState",
    "Budget",
    "Forecast",
    "Policy",
    "PolicyFinding",
    "Dependency",
    "Alert",
    "Notification",
    "SyncJob",
    "AuditEvent",
    "Override",
]
