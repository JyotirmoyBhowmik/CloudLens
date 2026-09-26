"""Fact Entities Aligned with FinOps Open Cost & Usage Specification (FOCUS) v1.0.

Enforces Prompt 05 Item 33 & 36:
1. CostFact (FOCUS-aligned, per BBP Section 17.4), UsageFact, RuntimeState, PricingDimension, PricingRecord.
2. Four-state null discipline enforced on every measure (billed_cost, effective_cost, usage_quantity, cpu_utilization, etc.).
   Bare nulls are banned.
"""

from datetime import datetime
from decimal import Decimal

from pydantic import Field

from domain.models.base import CanonicalEntity
from domain.models.enums import ChargeCategory, CostSourceType, PricingModel, RuntimeStatus
from domain.models.measures import FinancialMeasure, QuantityMeasure


class CostFact(CanonicalEntity):
    """FOCUS 1.0-compliant billing charge line fact entity."""

    tenant_id: str = Field(..., description="Organization tenant ID")
    scope_id: str = Field(..., description="Scope ID in force at time of charge")
    resource_id: str | None = Field(
        default=None, description="Optional associated canonical Resource ID"
    )
    charge_period_start: datetime = Field(..., description="Start of charge interval in UTC")
    charge_period_end: datetime = Field(..., description="End of charge interval in UTC")
    charge_category: ChargeCategory = Field(
        default=ChargeCategory.USAGE, description="FOCUS charge category"
    )
    cost_source: CostSourceType = Field(
        default=CostSourceType.INVOICE, description="FOCUS cost source classification"
    )
    charge_subcategory: str | None = Field(
        default=None, description="Pricing construct: On-Demand, Spot, Reserved"
    )
    billed_cost: FinancialMeasure = Field(
        ..., description="Invoice billed cost enforcing four-state null discipline (no bare nulls)"
    )
    effective_cost: FinancialMeasure = Field(
        ..., description="Amortised effective cost including commitment discounts (no bare nulls)"
    )
    contracted_cost: FinancialMeasure = Field(
        default_factory=FinancialMeasure.not_applicable,
        description="Negotiated customer contracted rate (no bare nulls)",
    )
    list_cost: FinancialMeasure = Field(
        default_factory=FinancialMeasure.not_applicable,
        description="Published provider catalog price before discounts (no bare nulls)",
    )
    billing_currency: str = Field(default="USD", description="ISO 4217 currency code")
    pricing_quantity: QuantityMeasure = Field(
        default_factory=QuantityMeasure.not_applicable,
        description="Billed consumption quantity (no bare nulls)",
    )
    pricing_unit: str | None = Field(
        default=None, description="Unit of measure (e.g. Hours, GB-Month)"
    )


class UsageFact(CanonicalEntity):
    """Operational metric consumption fact entity."""

    tenant_id: str = Field(..., description="Organization tenant ID")
    scope_id: str = Field(..., description="Scope ID in force")
    resource_id: str = Field(..., description="Associated canonical Resource ID")
    period_start: datetime = Field(..., description="Observation start in UTC")
    period_end: datetime = Field(..., description="Observation end in UTC")
    metric_name: str = Field(
        ..., description="Metric descriptor (e.g. ComputeHours, NetworkEgressBytes)"
    )
    usage_quantity: QuantityMeasure = Field(
        ..., description="Observed numeric usage quantity enforcing four-state null discipline"
    )
    usage_unit: str = Field(..., description="Normalized unit (Hours, Bytes, Requests)")


class RuntimeState(CanonicalEntity):
    """Runtime activity and capacity utilization snapshot for idle detection."""

    resource_id: str = Field(..., description="Target canonical Resource ID")
    status: RuntimeStatus = Field(
        default=RuntimeStatus.RUNNING, description="Current operational state"
    )
    cpu_utilization_avg: QuantityMeasure = Field(
        default_factory=QuantityMeasure.not_supported,
        description="Average CPU utilization percentage (0-100) or 4-state null",
    )
    memory_utilization_avg: QuantityMeasure = Field(
        default_factory=QuantityMeasure.not_supported,
        description="Average RAM utilization percentage (0-100) or 4-state null",
    )
    observed_at: datetime = Field(..., description="Snapshot observation timestamp in UTC")
    is_idle: bool | None = Field(
        default=None, description="Flag indicating idle status per FinOps thresholds"
    )


class PricingDimension(CanonicalEntity):
    """Reconciled pricing dimension metadata entity (reconciled across 29 dimensions)."""

    dimension_name: str = Field(
        ..., description="Standardized dimension name (e.g. vCPU-Hours, Storage-GB-Month)"
    )
    unit: str = Field(..., description="Standard unit identifier")
    description: str = Field(..., description="Description of rate calculation metric")
    tier_minimum: Decimal | None = Field(default=None, description="Tier bracket lower bound")
    tier_maximum: Decimal | None = Field(default=None, description="Tier bracket upper bound")


class PricingRecord(CanonicalEntity):
    """Specific catalog price entry per service, resource type, and dimension."""

    service_id: str = Field(..., description="Target Service ID")
    resource_type_id: str = Field(..., description="Target ResourceType ID")
    pricing_dimension_name: str = Field(..., description="Applicable dimension name")
    rate: FinancialMeasure = Field(
        ..., description="Rate amount enforcing four-state null discipline"
    )
    currency: str = Field(default="USD", description="Currency code")
    pricing_model: PricingModel = Field(
        default=PricingModel.ON_DEMAND, description="Applicable model"
    )
    effective_date: datetime = Field(..., description="Catalog rate effective date in UTC")
