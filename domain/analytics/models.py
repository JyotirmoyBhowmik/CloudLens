"""Semantic Layer, Analytical Extract & BI Feed Data Models (Prompt 56 / BBP Section 36 & 39).

Enforces:
- Star-schema view set over canonical model: FactCostAndUsage at the center with 16 conformed dimensions.
- All field names designed for business users, not developers.
- Pre-computed derived measures (billed, effective, list, contracted, realised discount,
  budget, variance, utilisation, forecast, unallocated, allocated, estimated, reconciliation variance).
- Preservation of the four null states (ZERO, NO_DATA, NOT_APPLICABLE, NOT_SUPPORTED) without flattening.
- Scope-bound extract manifest with cryptographic checksums and supersession policy.
- Isolated analytical query request and response contracts.
"""

from __future__ import annotations

import datetime as dt
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SemanticDataQualityNullState(StrEnum):
    """The four canonical null states plus value-present for BI measures (Prompt 05 / 56)."""

    VALUE_PRESENT = "VALUE_PRESENT"
    ZERO = "ZERO"
    NO_DATA = "NO_DATA"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    NOT_SUPPORTED = "NOT_SUPPORTED"


# ==============================================================================
# 1. Conformed Dimension Models (Business-Friendly Naming)
# ==============================================================================


class DimDateRecord(BaseModel):
    """Conformed Date and Fiscal Period Dimension."""

    DateKey: int = Field(..., description="Integer date key in YYYYMMDD format, e.g. 20260915")
    FullDate: str = Field(..., description="Calendar date in ISO YYYY-MM-DD format")
    CalendarYear: int = Field(..., description="Gregorian calendar year")
    CalendarQuarter: str = Field(..., description="Calendar quarter, e.g. Q3")
    CalendarMonth: int = Field(..., description="Calendar month number (1-12)")
    FiscalYear: str = Field(..., description="Authoritative corporate fiscal year, e.g. FY2026")
    FiscalQuarter: str = Field(..., description="Corporate fiscal quarter, e.g. FQ3")
    FiscalPeriod: str = Field(..., description="Fiscal period identifier, e.g. FP09")
    DayOfWeekName: str = Field(..., description="Full day of week name, e.g. Tuesday")
    IsWorkingDay: bool = Field(..., description="Whether date falls on an enterprise working day")


class DimScopeRecord(BaseModel):
    """Conformed Organizational Scope & Hierarchy Dimension."""

    ScopeKey: str = Field(..., description="Surrogate key for the organizational scope")
    ScopeIdentifier: str = Field(
        ..., description="Canonical scope identifier, e.g. scp-retail-prod"
    )
    ScopeName: str = Field(..., description="Human-readable business scope name")
    ScopeType: str = Field(
        ..., description="Scope type: ACCOUNT, SUBSCRIPTION, PROJECT, BUSINESS_UNIT"
    )
    ParentScopeIdentifier: str | None = Field(
        default=None, description="Parent scope identifier in hierarchy"
    )
    HierarchyPath: str = Field(
        ..., description="Full materialized hierarchy path, e.g. /Global/Retail/Production"
    )
    OrganizationalUnit: str = Field(..., description="Top-level organizational unit")


class DimProviderRecord(BaseModel):
    """Conformed Cloud Provider Dimension."""

    ProviderKey: str = Field(..., description="Cloud provider code: AWS, AZURE, GCP, OCI")
    ProviderName: str = Field(..., description="Full legal commercial name of cloud provider")
    ProviderAccountId: str = Field(..., description="Provider billing or root account identifier")
    ProviderAccountName: str = Field(
        ..., description="Designated display name for provider account"
    )


class DimServiceRecord(BaseModel):
    """Conformed Cloud Service & Category Dimension."""

    ServiceKey: str = Field(..., description="Surrogate key for cloud service")
    ServiceCategory: str = Field(
        ..., description="FOCUS-aligned taxonomy: Compute, Storage, Database, Networking"
    )
    ServiceName: str = Field(
        ..., description="Standard commercial service name, e.g. Amazon Elastic Compute Cloud"
    )
    ServiceCode: str = Field(..., description="Provider technical service code, e.g. AmazonEC2")


class DimResourceRecord(BaseModel):
    """Conformed Cloud Resource Dimension."""

    ResourceKey: str = Field(..., description="Surrogate key for cloud resource")
    ResourceIdentifier: str = Field(
        ..., description="Canonical or native resource ID, e.g. i-0abc12345678"
    )
    ResourceName: str = Field(..., description="User-assigned or discovered resource tag name")
    ResourceType: str = Field(..., description="Cloud provider resource classification type")
    RegionIdentifier: str = Field(..., description="Provider region code, e.g. us-east-1")
    AvailabilityZone: str | None = Field(
        default=None, description="Specific availability zone, e.g. us-east-1a"
    )


class DimApplicationRecord(BaseModel):
    """Conformed Business Application Dimension."""

    ApplicationKey: str = Field(..., description="Surrogate key for application")
    ApplicationIdentifier: str = Field(
        ..., description="Enterprise CMDB or tag application code, e.g. APP-CHECKOUT"
    )
    ApplicationName: str = Field(
        ..., description="Official business name of application, e.g. Payments & Checkout"
    )
    CriticalityTier: str = Field(
        ..., description="Operational tier: TIER_1_CRITICAL, TIER_2_BUSINESS, TIER_3_SUPPORT"
    )


class DimEnvironmentRecord(BaseModel):
    """Conformed Environment Lifecycle Dimension."""

    EnvironmentKey: str = Field(..., description="Environment code: PROD, STAGE, DEV, TEST, DR")
    EnvironmentCode: str = Field(..., description="Standardized environment identifier")
    EnvironmentName: str = Field(
        ..., description="Descriptive environment classification: Production, Staging, etc."
    )


class DimOwnerRecord(BaseModel):
    """Conformed Accountable Owner Dimension."""

    OwnerKey: str = Field(..., description="Primary accountable email address or group")
    OwnerEmail: str = Field(..., description="Owner corporate email address")
    OwnerName: str = Field(..., description="Full display name of responsible owner")
    OwnerType: str = Field(
        ..., description="Accountability category: TECHNICAL, BUSINESS, FINANCIAL"
    )


class DimCostCentreRecord(BaseModel):
    """Conformed Cost Centre Dimension."""

    CostCentreKey: str = Field(..., description="Enterprise cost centre code, e.g. CC-1040")
    CostCentreCode: str = Field(..., description="Canonical cost centre code")
    CostCentreName: str = Field(
        ..., description="Department or business description of cost centre"
    )
    DepartmentName: str = Field(
        ..., description="Parent department name, e.g. Engineering & Platform"
    )


class DimBusinessUnitRecord(BaseModel):
    """Conformed Business Unit Dimension."""

    BusinessUnitKey: str = Field(
        ..., description="Corporate business unit identifier, e.g. BU-RETAIL"
    )
    BusinessUnitCode: str = Field(..., description="Standard business unit code")
    BusinessUnitName: str = Field(
        ..., description="Executive commercial business unit title, e.g. Global Retail"
    )
    DivisionName: str = Field(..., description="Corporate division grouping")


class DimProjectRecord(BaseModel):
    """Conformed Project & Capitalisation Dimension."""

    ProjectKey: str = Field(..., description="Project code, e.g. PRJ-2026-CLOUD-MOD")
    ProjectCode: str = Field(..., description="Enterprise project management system code")
    ProjectName: str = Field(..., description="Official initiative project title")
    FundingSource: str = Field(
        ..., description="Financial source: OPEX_OPERATIONAL, CAPEX_CAPITALISED, GRANT"
    )


class DimRegionRecord(BaseModel):
    """Conformed Geographic Region & Sovereignty Dimension."""

    RegionKey: str = Field(..., description="Region key, e.g. us-east-1")
    RegionIdentifier: str = Field(..., description="Technical cloud provider region code")
    ProviderName: str = Field(..., description="Cloud provider code")
    GeographicArea: str = Field(
        ..., description="Global continental area: North America, Europe, Asia Pacific"
    )
    SovereignBoundary: str = Field(
        ..., description="Jurisdictional boundary, e.g. United States, European Union"
    )


class DimTagRecord(BaseModel):
    """Conformed Resource Tag Dimension."""

    TagKey: str = Field(..., description="Surrogate hash key for tag combination")
    TagKeyName: str = Field(..., description="Attributed tag key, e.g. Environment, CostCenter")
    TagValue: str = Field(..., description="Assigned tag value")
    TagComplianceStatus: str = Field(
        ..., description="Tag governance status: COMPLIANT, NON_COMPLIANT, MISSING"
    )


class DimPricingRecord(BaseModel):
    """Conformed Pricing Model & SKU Dimension."""

    PricingKey: str = Field(..., description="Product SKU or price quote key")
    PricingCategory: str = Field(
        ..., description="Pricing model: ON_DEMAND, RESERVED, SPOT, SAVINGS_PLAN"
    )
    RateType: str = Field(..., description="Rate dimension: Hourly, PerGigabyteMonth, RequestCount")
    SkuIdentifier: str = Field(..., description="Provider specific product SKU code")
    PricingCurrency: str = Field(default="USD", description="Currency of published catalog rate")


class DimCommitmentRecord(BaseModel):
    """Conformed Capacity & Spend Commitment Dimension."""

    CommitmentKey: str = Field(..., description="Commitment identifier or NONE")
    CommitmentType: str = Field(
        ..., description="Type: RESERVED_INSTANCE, SAVINGS_PLAN, COMMITTED_USE_DISCOUNT, NONE"
    )
    CommitmentIdentifier: str | None = Field(
        default=None, description="Native reservation or contract ID"
    )
    TermDurationMonths: int = Field(
        default=0, description="Contract duration term in months: 12, 36, 0"
    )


class DimChargeCategoryRecord(BaseModel):
    """Conformed Charge Classification Dimension."""

    ChargeCategoryKey: str = Field(
        ..., description="Classification key: USAGE, PURCHASE, CREDIT, TAX, REFUND"
    )
    ChargeCategoryName: str = Field(..., description="Primary FOCUS charge category")
    ChargeSubCategory: str = Field(
        default="Standard", description="Subcategory: OnDemand, AmortisedCommitment, etc."
    )


# ==============================================================================
# 2. Central Fact Table (FactCostAndUsage) with Derived Measures
# ==============================================================================


class FactCostAndUsageRecord(BaseModel):
    """Central Star-Schema Fact Table with Pre-Computed Derived Measures (Prompt 56)."""

    model_config = ConfigDict(populate_by_name=True)

    # Primary surrogate and tenant partition keys
    FactKey: str = Field(..., description="Surrogate UUID or composite hash for fact row")
    TenantId: str = Field(..., description="Corporate tenant identifier")
    ChargePeriod: str = Field(..., description="Billing period partition, e.g. 2026-09")
    ChargeDateKey: int = Field(..., description="Foreign key to DimDate (YYYYMMDD)")

    # Conformed Dimension Foreign Keys
    ScopeKey: str = Field(..., description="Foreign key to DimScope")
    ProviderKey: str = Field(..., description="Foreign key to DimProvider")
    ServiceKey: str = Field(..., description="Foreign key to DimService")
    ResourceKey: str = Field(..., description="Foreign key to DimResource")
    ApplicationKey: str = Field(..., description="Foreign key to DimApplication")
    EnvironmentKey: str = Field(..., description="Foreign key to DimEnvironment")
    OwnerKey: str = Field(..., description="Foreign key to DimOwner")
    CostCentreKey: str = Field(..., description="Foreign key to DimCostCentre")
    BusinessUnitKey: str = Field(..., description="Foreign key to DimBusinessUnit")
    ProjectKey: str = Field(..., description="Foreign key to DimProject")
    RegionKey: str = Field(..., description="Foreign key to DimRegion")
    TagKey: str = Field(..., description="Foreign key to DimTag")
    PricingKey: str = Field(..., description="Foreign key to DimPricing")
    CommitmentKey: str = Field(..., description="Foreign key to DimCommitment")
    ChargeCategoryKey: str = Field(..., description="Foreign key to DimChargeCategory")

    # Derived Pre-Computed Measures (Computed once for all BI reports)
    BilledCostAmount: float = Field(..., description="Invoice billed cost in presentation currency")
    EffectiveCostAmount: float = Field(
        ..., description="Amortised effective cost reflecting committed discounts"
    )
    ListCostAmount: float = Field(
        ..., description="Un-discounted published public retail catalog cost"
    )
    ContractedCostAmount: float = Field(..., description="Pre-agreed contracted customer rate cost")
    RealisedDiscountAmount: float = Field(
        ..., description="Realised savings: ListCostAmount - EffectiveCostAmount"
    )
    BudgetAmount: float = Field(..., description="Allocated target budget for scope in period")
    BudgetVarianceAmount: float = Field(
        ..., description="Spend variance: BilledCostAmount - BudgetAmount"
    )
    BudgetUtilisationPercentage: float = Field(
        ..., description="Utilisation ratio: (BilledCost / Budget) * 100"
    )
    SpendForecastAmount: float = Field(
        ..., description="Projected period spend based on run-rate and models"
    )
    UnallocatedCostAmount: float = Field(
        ..., description="Portion of cost unallocated to applications"
    )
    AllocatedCostAmount: float = Field(
        ..., description="Portion of cost attributed via business allocation rules"
    )
    EstimatedCostAmount: float = Field(
        ..., description="Pre-deployment architectural estimated cost"
    )
    ReconciliationVarianceAmount: float = Field(
        ..., description="Variance vs authoritative provider invoice"
    )
    UsageQuantity: float = Field(
        ..., description="Measured consumable quantity (hours, GBs, invocations)"
    )

    # Preserved Four Null States & Data Quality Governance (Never flattened into generic null)
    BilledCostNullState: SemanticDataQualityNullState = Field(
        default=SemanticDataQualityNullState.VALUE_PRESENT,
        description="Preserved null state: VALUE_PRESENT, ZERO, NO_DATA, NOT_APPLICABLE, NOT_SUPPORTED",
    )
    UsageQuantityNullState: SemanticDataQualityNullState = Field(
        default=SemanticDataQualityNullState.VALUE_PRESENT,
        description="Preserved null state for usage quantity",
    )
    OverallQualityNullState: SemanticDataQualityNullState = Field(
        default=SemanticDataQualityNullState.VALUE_PRESENT,
        description="Row-level data completeness classification",
    )

    # Governance Context
    ProviderFreshnessTimestamp: str = Field(
        ..., description="UTC timestamp of provider telemetry freshness"
    )
    CostBasis: str = Field(
        default="BILLED", description="Cost basis: BILLED, EFFECTIVE, LIST, CONTRACTED"
    )
    Currency: str = Field(default="USD", description="Currency code (ISO 4217)")
    CurrencyExchangeRate: float = Field(
        default=1.0, description="Exchange rate applied to convert from source"
    )
    CurrencyRateDate: str = Field(..., description="Effective date of applied FX rate")
    CostSourceType: str = Field(
        default="INVOICE", description="Source: INVOICE, METERED, ESTIMATED, ADJUSTED"
    )
    PricingStatus: str = Field(
        default="CONFIRMED", description="Pricing state: CONFIRMED, ESTIMATED, UNKNOWN_SKU"
    )
    IsRestated: bool = Field(default=False, description="Whether record is an amended restatement")
    ExtractVersion: int = Field(
        default=1, description="Sequential version stamp of extract partition"
    )


# ==============================================================================
# 3. Extract Manifest & Observability Models
# ==============================================================================


class AnalyticalExtractManifest(BaseModel):
    """Authoritative Manifest accompanying every scheduled and ad-hoc extract (Prompt 56)."""

    extract_id: str = Field(..., description="Unique UUID identifying the extract run")
    tenant_id: str = Field(..., description="Corporate tenant identifier")
    service_identity_id: str = Field(
        ..., description="Named service principal or actor requesting extract"
    )
    service_identity_name: str = Field(..., description="Display title of service identity")
    scope_grants: list[str] = Field(
        default_factory=list, description="Explicit scope grants binding the extract"
    )
    period: str = Field(..., description="Extracted partition period, e.g. 2026-09")
    version: int = Field(
        default=1, description="Partition version stamp (incremented on restatements)"
    )
    supersedes_version: int | None = Field(
        default=None, description="Prior version completely superseded by this extract"
    )
    schema_version: str = Field(
        default="1.0.0", description="Semantic layer schema version specification"
    )
    record_count: int = Field(..., description="Total fact records contained in dataset")
    file_checksums: dict[str, str] = Field(
        default_factory=dict, description="SHA-256 cryptographic hashes for all generated files"
    )
    generated_at: str = Field(..., description="ISO 8601 UTC timestamp of extract completion")
    watermark_timestamp: str = Field(
        ..., description="High-watermark timestamp of underlying ingestion stream"
    )
    governance_context: dict[str, Any] = Field(
        default_factory=dict,
        description="Freshness per provider, FX rates, and cost basis parameters",
    )
    access_filtering_occurred: bool = Field(
        default=False,
        description="Whether records were restricted by service identity scope grants",
    )
    filtering_disclosure: str | None = Field(
        default=None, description="Audit disclosure proving extract obeyed RBAC constraints"
    )
    supersession_policy: str = Field(
        default="Higher version number unconditionally supersedes earlier versions for this tenant and period partition.",
        description="Authoritative instruction for downstream BI ingestion pipelines",
    )


class AnalyticsExtractJob(BaseModel):
    """Lifecycle record for an analytical extract execution."""

    id: str
    tenant_id: str
    service_identity_id: str
    period: str
    version: int
    status: str = Field(default="PENDING", description="PENDING, RUNNING, COMPLETED, FAILED")
    row_count: int = 0
    duration_ms: float = 0.0
    schema_version: str = "1.0.0"
    watermark: str = ""
    storage_destination: str = ""
    failure_reason: str | None = None
    created_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now(dt.UTC))
    completed_at: dt.datetime | None = None
    manifest: AnalyticalExtractManifest | None = None


# ==============================================================================
# 4. Isolated Analytical Query Path DTOs
# ==============================================================================


class AnalyticalQueryRequest(BaseModel):
    """Request payload for the isolated read-only analytical query path."""

    dimensions: list[str] = Field(
        default_factory=lambda: ["BusinessUnitName"],
        description="Group-by dimensions from semantic layer (e.g. BusinessUnitName, ServiceCategory, CalendarMonth)",
    )
    measures: list[str] = Field(
        default_factory=lambda: ["BilledCostAmount", "BudgetAmount", "RealisedDiscountAmount"],
        description="Aggregate measures to compute (e.g. BilledCostAmount, EffectiveCostAmount, BudgetVarianceAmount)",
    )
    filters: dict[str, Any] = Field(
        default_factory=dict,
        description="Dimension filters, e.g. {'ProviderKey': 'AWS', 'EnvironmentKey': 'PROD'}",
    )
    period: str | None = Field(default=None, description="Billing period filter (e.g. 2026-09)")
    limit: int = Field(default=100, ge=1, le=5000, description="Maximum rows to return")
    offset: int = Field(default=0, ge=0, description="Offset for pagination")


class AnalyticalQueryResponse(BaseModel):
    """Response payload returned by the isolated analytical query path."""

    model_config = ConfigDict(populate_by_name=True)

    columns: list[str] = Field(
        ..., description="Ordered list of returned dimension and measure names"
    )
    rows: list[dict[str, Any]] = Field(..., description="Aggregated result rows")
    total_rows: int = Field(..., description="Total available matched rows")
    execution_time_ms: float = Field(..., description="Query execution duration in milliseconds")
    isolation_mode: str = Field(
        default="ISOLATED_ANALYTICAL_REPLICA",
        description="Proof of isolation from transactional database OLTP path",
    )
    metadata: dict[str, Any] = Field(default_factory=dict, alias="_metadata")


# ==============================================================================
# 5. Data Dictionary Model
# ==============================================================================


class SemanticDataDictionaryField(BaseModel):
    """Entry in the published Semantic Layer Data Dictionary."""

    TableName: str
    ColumnName: str
    BusinessName: str
    DataType: str
    Description: str
    DerivationFormula: str | None = None
    NullStatePolicy: str
    SampleValue: str
