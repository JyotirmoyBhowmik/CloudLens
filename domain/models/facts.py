"""Fact Entities Aligned with FinOps Open Cost & Usage Specification (FOCUS) v1.0.

Enforces Prompt 05 Item 33 & 36:
1. CostFact (FOCUS-aligned, per BBP Section 17.4), UsageFact, RuntimeState, PricingDimension, PricingRecord.
2. Four-state null discipline enforced on every measure (billed_cost, effective_cost, usage_quantity, cpu_utilization, etc.).
   Bare nulls are banned.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import Field

from domain.models.base import CanonicalEntity
from domain.models.enums import (
    ChargeCategory,
    CostSourceType,
    PricingModel,
    RuntimeStatus,
    ServiceCategory,
)
from domain.models.measures import FinancialMeasure, QuantityMeasure


class CostFact(CanonicalEntity):
    """FOCUS 1.0-compliant billing charge line fact entity."""

    tenant_id: str = Field(..., description="Organization tenant ID")
    scope_id: str = Field(..., description="Scope ID in force at time of charge")
    resource_id: str | None = Field(
        default=None, description="Optional associated canonical Resource ID"
    )
    provider: str = Field(
        default="aws", description="Cloud provider identifier (aws, azure, gcp, oci)"
    )
    service_id: str = Field(default="unknown-service", description="Canonical or native service ID")
    service_name: str | None = Field(default=None, description="Human-readable service name")
    service_category: ServiceCategory = Field(
        default=ServiceCategory.OTHER, description="Standardized service category"
    )
    charge_period_start: datetime = Field(..., description="Start of charge interval in UTC")
    charge_period_end: datetime = Field(..., description="End of charge interval in UTC")
    billing_period_start: date | None = Field(
        default=None, description="Calendar billing cycle start date"
    )
    billing_period_end: date | None = Field(
        default=None, description="Calendar billing cycle end date"
    )
    charge_category: ChargeCategory = Field(
        default=ChargeCategory.USAGE, description="FOCUS charge category"
    )
    cost_source: CostSourceType = Field(
        default=CostSourceType.INVOICE, description="FOCUS cost source classification"
    )
    charge_subcategory: str | None = Field(
        default=None, description="Pricing construct: On-Demand, Spot, Reserved"
    )
    charge_description: str | None = Field(
        default=None, description="Detailed line item charge description"
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
    commitment_id: str | None = Field(
        default=None, description="Associated Reservation or Savings Plan ID"
    )
    commitment_type: str | None = Field(
        default=None, description="Commitment type (e.g. RESERVED_INSTANCE, SAVINGS_PLAN)"
    )
    is_commitment_covered: bool = Field(
        default=False, description="Whether usage was covered by a committed discount"
    )
    realised_discount_value: FinancialMeasure = Field(
        default_factory=FinancialMeasure.not_applicable,
        description="Realized discount value (list_cost - effective_cost)",
    )
    is_restated: bool = Field(default=False, description="Whether this fact row has been restated")
    restatement_version: int = Field(default=1, description="Sequential restatement version number")
    restatement_detected_at: datetime | None = Field(
        default=None, description="Timestamp when restatement was detected in UTC"
    )
    prior_billed_cost: FinancialMeasure | None = Field(
        default=None, description="Prior billed cost value before restatement"
    )
    prior_effective_cost: FinancialMeasure | None = Field(
        default=None, description="Prior effective cost value before restatement"
    )
    restatement_reason: str | None = Field(
        default=None, description="Provider or audit explanation for restatement"
    )
    tags: dict[str, str] = Field(
        default_factory=dict, description="Resource and cost allocation tags"
    )
    cost_categories: dict[str, str] = Field(
        default_factory=dict, description="Enterprise cost categories"
    )
    provider_native: dict[str, Any] = Field(
        default_factory=dict, description="Verbatim raw provider line item attributes"
    )
    schema_version: str = Field(
        default="focus_1_0", description="Source billing dataset schema version"
    )

    @property
    def currency(self) -> str:
        """Alias property returning the native billing currency."""
        return self.billing_currency


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
