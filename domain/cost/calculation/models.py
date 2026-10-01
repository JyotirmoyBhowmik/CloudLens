"""Data Models and DTOs for Cost Calculation and Pre-Deployment Estimation (Prompt 23).

Enforces:
- Four-Value Separation: List price, Estimated cost, Actual cost, and Forecast cost are distinct types.
- Derivation Output: Every calculation produces an auditable derivation explaining rate, tier, allowance, discount, etc.
- Pre-Deployment Estimator DTOs across compute, managed database, object storage, and block storage.
- Cost-Driver Decomposition models for drill-through into contributing components.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from domain.models.enums import PricingStatus
from domain.pricing.cost_sources import (
    ActualBilledCost,
    ActualCost,
    CostSourceClassification,
    CostValue,
    EstimatedCost,
    EstimatedEffectiveCost,
    ForecastCost,
    ForecastCostValue,
    ListPrice,
    ProviderListPrice,
)
from domain.pricing.models import RateType


class RuntimeScheduleType(StrEnum):
    """Runtime operating schedule types for cloud resources."""

    CONTINUOUS_24_7 = "CONTINUOUS_24_7"  # 730 hours/month standard
    BUSINESS_HOURS_8X5 = "BUSINESS_HOURS_8X5"  # 173.33 hours/month (8 hrs * 5 days/wk)
    CUSTOM_HOURS = "CUSTOM_HOURS"  # Explicit user-specified hours per month
    FRACTIONAL_MONTH = "FRACTIONAL_MONTH"  # Active for a fraction of days in month


class CostCategoryType(StrEnum):
    """Canonical categories for cost-driver decomposition."""

    COMPUTE = "COMPUTE"
    STORAGE = "STORAGE"
    NETWORK = "NETWORK"
    DATABASE = "DATABASE"
    BACKUP = "BACKUP"
    LICENSING = "LICENSING"
    OTHER = "OTHER"


class TierStepDerivation(BaseModel):
    """Audit breakdown for an individual bracket evaluated in a tiered pricing model."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    bracket_index: int = Field(..., ge=0, description="0-indexed bracket tier")
    tier_start: Decimal = Field(..., description="Lower threshold of this bracket")
    tier_end: Decimal | None = Field(default=None, description="Upper threshold; None if unbounded")
    bracket_rate: Decimal = Field(..., description="Unit rate charged in this bracket")
    units_in_bracket: Decimal = Field(
        ..., description="Consumption quantity allocated to this bracket"
    )
    flat_fee: Decimal = Field(
        default=Decimal("0.00"), description="Fixed base fee for this bracket"
    )
    bracket_subtotal: Decimal = Field(
        ..., description="Unrounded or rounded cost from this bracket"
    )


class CostDerivation(BaseModel):
    """First-class derivation output explaining every calculated figure (Prompt 23 / Prompt 40)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    rate_applied: Decimal = Field(..., description="Exact unit rate applied")
    rate_type_applied: RateType = Field(
        default=RateType.LIST, description="LIST or CONTRACTED rate"
    )
    pricing_dimension: str = Field(..., description="Pricing dimension code (e.g. DIM-03)")
    pricing_dimension_name: str = Field(default="", description="Descriptive dimension name")
    quantity_consumed: Decimal = Field(..., description="Raw usage quantity before allowances")
    unit: str = Field(..., description="Unit of consumption (e.g. Hrs, GB-Mo)")
    tier_structure_applied: bool = Field(
        default=False, description="True if tiered pricing was evaluated"
    )
    tier_breakdown: list[TierStepDerivation] = Field(
        default_factory=list, description="Brackets breakdown"
    )
    free_allowance_deducted: Decimal = Field(
        default=Decimal("0.00"), description="Free allowance subtracted"
    )
    free_allowance_unit: str | None = Field(default=None, description="Unit of free allowance")
    net_billable_quantity: Decimal = Field(
        ..., description="Quantity charged after free tier deduction"
    )
    minimum_charge_applied: bool = Field(
        default=False, description="True if floor minimum charge applied"
    )
    minimum_charge_amount: Decimal = Field(
        default=Decimal("0.00"), description="Minimum charge threshold"
    )
    discount_applied_amount: Decimal = Field(
        default=Decimal("0.00"), description="Monetary discount saved"
    )
    discount_applied_percentage: Decimal = Field(
        default=Decimal("0.00"), description="Percentage discount rate"
    )
    discount_reference: str | None = Field(
        default=None, description="Contract/Agreement reference ID"
    )
    commitment_applied: str | None = Field(
        default=None, description="Reservation or savings plan applied"
    )
    assumptions: dict[str, Any] = Field(
        default_factory=dict, description="User and engine assumptions"
    )
    step_by_step_explanation: list[str] = Field(
        default_factory=list, description="Human-readable audit derivation steps"
    )
    retrieval_timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp when pricing was retrieved",
    )
    pricing_source: str = Field(default="cloudlens_catalog", description="Pricing catalogue source")
    pricing_source_url: str | None = Field(
        default=None, description="Provider documentation/pricing URL"
    )
    effective_date: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Effective date of the rate card",
    )
    currency: str = Field(default="USD", description="Currency ISO 4217 code")
    is_stale: bool = Field(
        default=False, description="Whether pricing freshness threshold was exceeded"
    )
    stale_reason: str | None = Field(default=None, description="Reason if pricing data is stale")


class CostDriverComponent(BaseModel):
    """Discrete contributing component in cost-driver decomposition (Prompt 23)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    category: CostCategoryType = Field(..., description="Decomposition category")
    name: str = Field(..., description="Human-readable component title")
    monthly_cost: EstimatedCost = Field(..., description="Monthly cost as EstimatedCost")
    percentage_of_total: Decimal = Field(
        ...,
        ge=Decimal("0.00"),
        le=Decimal("100.00"),
        description="Percentage of overall monthly estimate",
    )
    derivation: CostDerivation = Field(..., description="Complete audit derivation for this driver")
    drillable_details: dict[str, Any] = Field(
        default_factory=dict, description="Configuration parameters"
    )


class PreDeploymentEstimateRequest(BaseModel):
    """Input parameters for pre-deployment estimation ('What will this cost?')."""

    model_config = ConfigDict(extra="forbid")

    provider: str = Field(
        ..., min_length=1, description="Provider identifier (aws, azure, gcp, oci)"
    )
    service: str = Field(
        ..., min_length=1, description="Service name (e.g. AmazonEC2, Virtual Machines)"
    )
    region: str = Field(..., min_length=1, description="Datacenter region code")
    instance_type: str | None = Field(
        default=None, description="Compute size / instance type / VM sku"
    )
    operating_system: str = Field(default="Linux", description="Operating system (Linux, Windows)")
    storage_gb: float = Field(
        default=0.0, ge=0.0, description="Attached disk/storage volume size in GB"
    )
    storage_type: str | None = Field(
        default=None, description="Disk performance class (e.g. gp3, Premium_SSD)"
    )
    public_ip: bool = Field(
        default=False, description="Whether resource uses a public IPv4 address"
    )
    data_transfer_out_gb: float = Field(
        default=0.0, ge=0.0, description="Estimated monthly egress transfer in GB"
    )
    runtime_schedule_type: RuntimeScheduleType = Field(
        default=RuntimeScheduleType.CONTINUOUS_24_7,
        description="Operating runtime schedule",
    )
    custom_runtime_hours: float | None = Field(
        default=None, ge=0.0, le=744.0, description="Custom hours/month if CUSTOM_HOURS schedule"
    )
    database_engine: str | None = Field(
        default=None, description="Database engine (PostgreSQL, MySQL, SQLServer)"
    )
    backup_storage_gb: float = Field(
        default=0.0, ge=0.0, description="Backup/snapshot storage capacity in GB"
    )
    target_currency: str = Field(
        default="USD", min_length=3, max_length=3, description="Reporting currency"
    )
    tenant_id: str | None = Field(default=None, description="Tenant scope for contracted rates")
    assumptions: dict[str, Any] = Field(
        default_factory=dict, description="Additional custom assumptions"
    )


class PreDeploymentEstimateResult(BaseModel):
    """Result of pre-deployment estimation across multiple time horizons."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: str = Field(..., description="Provider identifier")
    service: str = Field(..., description="Service name")
    region: str = Field(..., description="Datacenter region")
    currency: str = Field(default="USD", description="Currency ISO 4217 code")
    pricing_status: PricingStatus = Field(
        ..., description="Classification (PAID, FREE, ESTIMATED, UNKNOWN)"
    )
    hourly_cost: EstimatedCost = Field(..., description="Estimated cost per hour")
    daily_cost: EstimatedCost = Field(..., description="Estimated cost per day")
    monthly_cost: EstimatedCost = Field(
        ..., description="Estimated cost per standard month (730 hrs or schedule)"
    )
    annualised_cost: EstimatedCost = Field(
        ..., description="Annualised estimated cost (monthly * 12)"
    )
    cost_drivers: list[CostDriverComponent] = Field(
        default_factory=list,
        description="Contributing cost drivers (compute, storage, network, etc.)",
    )
    overall_derivation: CostDerivation = Field(..., description="Full mathematical derivation")
    assumptions: dict[str, Any] = Field(
        default_factory=dict, description="Active estimation assumptions"
    )
    unavailability_reason: str | None = Field(
        default=None, description="Reason if pricing is UNKNOWN"
    )
    last_known_pricing_date: datetime | None = Field(
        default=None, description="Last known pricing timestamp"
    )


__all__ = [
    "ActualBilledCost",
    "ActualCost",
    "CostCategoryType",
    "CostDerivation",
    "CostDriverComponent",
    "CostSourceClassification",
    "CostValue",
    "EstimatedCost",
    "EstimatedEffectiveCost",
    "ForecastCost",
    "ForecastCostValue",
    "ListPrice",
    "PreDeploymentEstimateRequest",
    "PreDeploymentEstimateResult",
    "ProviderListPrice",
    "RuntimeScheduleType",
    "TierStepDerivation",
]
