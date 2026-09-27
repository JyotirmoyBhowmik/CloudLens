"""Pricing Catalogue Domain Models and Data Transfer Objects (Prompt 20 / BBP Sections 18 & 39.2).

Enforces:
- Full 20-attribute pricing entity set per Master Brief Section 8 and BBP 39.2.
- Slowly Changing Dimension (SCD Type 2) tracking with explicit versioning and effective date intervals.
- Structured Tier and Volume models with graduated and volume-break calculation support.
- Structured Free Allowance models with non-null assertions and numeric bounds.
- STRICT PROHIBITION: Free tier is NEVER modeled as a boolean flag.
- Structured Discount and Commitment tracking.
- Pricing change records for automated variance detection and signal emission.
- Unknown-SKU tracking to preserve ingestion pipeline fault tolerance.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from domain.models.exceptions import InvalidFreeAllowanceException, InvalidPricingTierException


class RateType(StrEnum):
    """Classification of price rate card."""

    LIST = "LIST"  # Public list / retail rate
    CONTRACTED = "CONTRACTED"  # Enterprise negotiated rate (e.g. EDP, Price Sheet, UCC)
    PROMOTIONAL = "PROMOTIONAL"  # Promotional campaign rate
    OVERRIDE = "OVERRIDE"  # Curated manual rate override


class PricingTierModel(StrEnum):
    """Tiered pricing aggregation mode."""

    GRADUATED = "GRADUATED"  # Incremental brackets (first 50 TB, next 450 TB, etc.)
    VOLUME = "VOLUME"  # All units charged at highest volume threshold rate


class FreeAllowance(BaseModel):
    """Structured free allowance definition (Prompt 20 / BBP Section 18.2 DIM-26).

    STRICT PROHIBITION: Free allowance is NEVER modeled as a boolean flag.
    Always models quantity, unit, reset period, and post-allowance rate.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    quantity: float = Field(..., ge=0.0, description="Included usage allowance quantity")
    unit: str = Field(
        ..., min_length=1, description="Unit of measure for allowance (e.g. Hrs, GB-Mo)"
    )
    reset_period: str = Field(
        default="MONTHLY",
        description="Allowance reset cadence (MONTHLY, BILLING_CYCLE, ANNUAL, ONE_TIME)",
    )
    post_allowance_rate: float = Field(
        default=0.0,
        ge=0.0,
        description="Unit rate charged once free allowance is exhausted",
    )
    is_exhaustible: bool = Field(
        default=True,
        description="Whether consumption decrements the allowance",
    )

    def __init__(self, **data: Any) -> None:
        try:
            super().__init__(**data)
        except Exception as e:
            if isinstance(e, InvalidFreeAllowanceException):
                raise
            raise InvalidFreeAllowanceException(f"Invalid free allowance specification: {e}") from e

    @field_validator("quantity")
    @classmethod
    def validate_quantity(cls, v: float) -> float:
        if v < 0.0:
            raise InvalidFreeAllowanceException("Free allowance quantity cannot be negative.")
        return v

    @field_validator("unit")
    @classmethod
    def validate_unit(cls, v: str) -> str:
        if not v or not v.strip():
            raise InvalidFreeAllowanceException("Free allowance unit must be non-empty string.")
        return v.strip()


class TierBracket(BaseModel):
    """Discrete volume bracket within a tiered rate structure."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tier_start: float = Field(default=0.0, ge=0.0, description="Lower volume boundary inclusive")
    tier_end: float | None = Field(
        default=None,
        description="Upper volume boundary exclusive; None if unbounded",
    )
    tier_unit_rate: float = Field(..., ge=0.0, description="Unit rate within this bracket")
    flat_fee: float = Field(
        default=0.0,
        ge=0.0,
        description="Fixed base fee for entering or residing in this bracket",
    )

    @field_validator("tier_unit_rate")
    @classmethod
    def validate_rate(cls, v: float) -> float:
        if v < 0.0:
            raise InvalidPricingTierException("Tier unit rate cannot be negative.")
        return v


class TierStructure(BaseModel):
    """Structured tiered and volume pricing configuration (Prompt 20 / DIM-24, DIM-25)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    pricing_model: PricingTierModel = Field(
        default=PricingTierModel.GRADUATED,
        description="Graduated incremental or volume all-units pricing",
    )
    brackets: list[TierBracket] = Field(
        default_factory=list,
        description="Ordered list of volume tier brackets",
    )

    def __init__(self, **data: Any) -> None:
        try:
            super().__init__(**data)
        except Exception as e:
            if isinstance(e, InvalidPricingTierException):
                raise
            raise InvalidPricingTierException(f"Invalid pricing tier structure: {e}") from e

    @field_validator("brackets")
    @classmethod
    def validate_brackets_order(cls, brackets: list[TierBracket]) -> list[TierBracket]:
        if not brackets:
            return brackets
        # Verify monotonicity of brackets
        for i in range(len(brackets) - 1):
            curr_end = brackets[i].tier_end
            next_start = brackets[i + 1].tier_start
            if curr_end is None:
                raise InvalidPricingTierException(
                    "Only the last bracket in a tier structure may have an unbounded tier_end (None)."
                )
            if curr_end > next_start:
                raise InvalidPricingTierException(
                    f"Overlapping tier brackets: bracket[{i}].tier_end ({curr_end}) > bracket[{i + 1}].tier_start ({next_start})."
                )
        return brackets

    def calculate_cost(self, quantity: float) -> float:
        """Calculates total cost for given usage quantity across brackets."""
        if quantity <= 0.0 or not self.brackets:
            return 0.0

        if self.pricing_model == PricingTierModel.VOLUME:
            # All units charged at highest qualified bracket rate
            for bracket in reversed(self.brackets):
                if quantity >= bracket.tier_start:
                    return (quantity * bracket.tier_unit_rate) + bracket.flat_fee
            return quantity * self.brackets[0].tier_unit_rate

        # Graduated / incremental tiered calculation
        total_cost = 0.0
        remaining = quantity
        for bracket in self.brackets:
            if remaining <= 0.0:
                break
            bracket_capacity = (
                (bracket.tier_end - bracket.tier_start)
                if bracket.tier_end is not None
                else remaining
            )
            units_in_bracket = min(remaining, bracket_capacity)
            total_cost += (units_in_bracket * bracket.tier_unit_rate) + bracket.flat_fee
            remaining -= units_in_bracket

        return total_cost


class DiscountInfo(BaseModel):
    """Contractual, negotiated, or volume discount details."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    discount_type: str = Field(
        default="PERCENTAGE",
        description="PERCENTAGE, NEGOTIATED_FIXED, or TIERED_DISCOUNT",
    )
    discount_percentage: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
        description="Discount percentage relative to public list price",
    )
    contract_reference: str | None = Field(
        default=None,
        description="Enterprise Agreement ID, EDP ID, MCA Amendment, or UCC identifier",
    )
    description: str | None = Field(
        default=None,
        description="Human-readable discount title or rationale",
    )


class CommitmentInfo(BaseModel):
    """Commitment, reservation, and savings plan parameters."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    commitment_type: str = Field(
        default="NONE",
        description="NONE, SAVINGS_PLAN, RESERVED_INSTANCE, UCC, COMMITTED_USE",
    )
    term_months: int = Field(default=0, ge=0, description="Commitment term in months (12, 36)")
    payment_option: str = Field(
        default="NO_UPFRONT",
        description="NO_UPFRONT, PARTIAL_UPFRONT, ALL_UPFRONT",
    )
    upfront_cost: float = Field(
        default=0.0,
        ge=0.0,
        description="Upfront capital payment if applicable",
    )
    hourly_commitment: float | None = Field(
        default=None,
        ge=0.0,
        description="Spend commitment rate ($/hr) for flexible savings plans",
    )


class PricingRecord(BaseModel):
    """Full 20-attribute enterprise pricing catalogue entity (Prompt 20 / BBP Section 39.2).

    Preserves SCD Type 2 semantics with immutable historical records and versioning.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()), description="Unique pricing record ID"
    )
    tenant_id: str | None = Field(
        default=None,
        description="Tenant ID for contracted rates; None for global public catalog",
    )

    # 1. Provider
    provider: str = Field(
        ..., min_length=1, description="Provider identifier (aws, azure, gcp, oci)"
    )
    # 2. Service
    service: str = Field(
        ..., min_length=1, description="Provider service name (e.g. AmazonEC2, Compute Engine)"
    )
    # 3. Service SKU where available
    service_sku: str | None = Field(default=None, description="Native SKU code where available")
    # 4. Resource type
    resource_type: str = Field(
        ..., min_length=1, description="Canonical resource type classification"
    )
    # 5. Region
    region: str = Field(..., min_length=1, description="Provider datacenter region code")
    # 6. Pricing dimension
    pricing_dimension: str = Field(
        ..., min_length=1, description="Pricing dimension code (DIM-01 to DIM-29)"
    )
    # 7. Unit
    unit: str = Field(
        ..., min_length=1, description="Unit of measure (e.g. hours, GB-month, requests)"
    )
    # 8. Unit price
    unit_price: float = Field(..., ge=0.0, description="Unit price for the pricing dimension")
    # 9. Currency
    currency: str = Field(default="USD", description="Currency ISO 4217 code")
    # 10. Free allowance
    free_allowance: FreeAllowance | None = Field(
        default=None,
        description="Structured free allowance; NEVER a boolean flag",
    )
    # 11. Tier
    tier: TierStructure | None = Field(
        default=None, description="Structured volume or graduated tiers"
    )
    # 12. Minimum charge
    minimum_charge: float = Field(default=0.0, ge=0.0, description="Minimum billing floor charge")
    # 13. Effective date
    effective_from: datetime = Field(
        ..., description="Timestamp from which this rate is effective in UTC"
    )
    # 14. Expiration date where applicable
    effective_to: datetime | None = Field(
        default=None,
        description="Timestamp when rate expired or was superseded; None if currently active",
    )
    # 15. Discount information
    discount_info: DiscountInfo | None = Field(default=None, description="Discount details")
    # 16. Commitment information
    commitment_info: CommitmentInfo | None = Field(default=None, description="Commitment details")
    # 17. Source
    source: str = Field(
        ...,
        description="Catalog source (e.g. aws_price_list_bulk, azure_price_sheet, gcp_billing_catalog, oci_rate_card)",
    )
    # 18. Source URL or reference
    source_url: str | None = Field(default=None, description="Source URL or documentation link")
    # 19. Retrieval timestamp
    retrieved_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp when pricing was retrieved",
    )
    # 20. Provider-specific attribute bag
    attributes: dict[str, Any] = Field(
        default_factory=dict,
        description="Provider-specific attribute bag (instanceType, os, etc.)",
    )

    # Architectural SCD Type 2 & Precedence controls
    rate_type: RateType = Field(
        default=RateType.LIST,
        description="LIST retail rate or CONTRACTED negotiated rate",
    )
    is_active: bool = Field(default=True, description="Whether this rate is currently active")
    version: int = Field(default=1, ge=1, description="SCD Type 2 monotonic version sequence")

    @field_validator("effective_from")
    @classmethod
    def ensure_utc_effective_from(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            return v.replace(tzinfo=UTC)
        return v.astimezone(UTC)

    @field_validator("effective_to")
    @classmethod
    def ensure_utc_effective_to(cls, v: datetime | None) -> datetime | None:
        if v is None:
            return None
        if v.tzinfo is None:
            return v.replace(tzinfo=UTC)
        return v.astimezone(UTC)

    def is_effective_on(self, query_date: datetime) -> bool:
        """Evaluates whether this pricing record was effective on query_date."""
        target = query_date if query_date.tzinfo else query_date.replace(tzinfo=UTC)
        target = target.astimezone(UTC)
        if target < self.effective_from:
            return False
        if self.effective_to is not None and target >= self.effective_to:
            return False
        return True


class PricingChangeRecord(BaseModel):
    """Variance detection record generated when a rate change is discovered (Prompt 20)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Change audit ID")
    tenant_id: str | None = Field(default=None, description="Tenant scope ID")
    provider: str = Field(..., description="Cloud provider identifier")
    service: str = Field(..., description="Service name")
    service_sku: str | None = Field(default=None, description="Service SKU code")
    region: str = Field(..., description="Datacenter region")
    pricing_dimension: str = Field(..., description="Pricing dimension code")
    rate_type: RateType = Field(..., description="LIST or CONTRACTED rate type")
    old_unit_price: float = Field(..., ge=0.0, description="Superseded unit price")
    new_unit_price: float = Field(..., ge=0.0, description="Newly effective unit price")
    absolute_change: float = Field(..., description="new_unit_price - old_unit_price")
    percentage_change: float = Field(
        ..., description="Percentage variance ((new - old) / old) * 100"
    )
    effective_from: datetime = Field(..., description="Effective timestamp of the new price")
    detected_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp change was detected",
    )
    source: str = Field(..., description="Detection source")
    notes: str | None = Field(default=None, description="Contextual change notes")


class UnknownSkuRecord(BaseModel):
    """Gap record created when ingestion encounters an unknown SKU (Prompt 20 Unknown-SKU Path).

    Ensures ingestion pipelines never fail when encountering uncatalogued SKUs.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Gap record ID")
    tenant_id: str | None = Field(default=None, description="Tenant ID context")
    provider: str = Field(..., min_length=1, description="Cloud provider identifier")
    service_sku: str = Field(..., min_length=1, description="Unrecognised SKU code")
    service_hint: str | None = Field(default=None, description="Service name hint from raw data")
    region_hint: str | None = Field(default=None, description="Region hint from raw data")
    raw_payload: dict[str, Any] = Field(
        default_factory=dict,
        description="Raw ingestion record context for debugging",
    )
    status: str = Field(
        default="UNRESOLVED",
        description="UNRESOLVED, RESOLVED, or ON_DEMAND_FETCHED",
    )
    occurrence_count: int = Field(default=1, ge=1, description="Count of occurrences seen")
    first_seen_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="First occurrence timestamp",
    )
    last_seen_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Most recent occurrence timestamp",
    )
    resolved_pricing_id: str | None = Field(
        default=None,
        description="ID of resolved PricingRecord once ingested",
    )
    resolution_notes: str | None = Field(default=None, description="Resolution notes")


class ResolvedPriceQuote(BaseModel):
    """Point-in-time pricing resolution result applying contracted rate precedence.

    Where a contracted/negotiated rate exists, list rate is NEVER presented as
    the organisation's rate, but both are retained so the realised discount is tracked.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: str
    service: str
    service_sku: str | None
    region: str
    pricing_dimension: str
    query_date: datetime
    effective_price: float = Field(
        ...,
        description="Exact price applicable to the organisation on query_date",
    )
    list_price: float = Field(
        ...,
        description="Baseline public retail list price on query_date",
    )
    rate_type_applied: RateType = Field(
        ...,
        description="Rate type used for effective_price (CONTRACTED or LIST)",
    )
    realized_discount_amount: float = Field(
        default=0.0,
        description="Unit discount amount (list_price - effective_price)",
    )
    realized_discount_percent: float = Field(
        default=0.0,
        description="Percentage discount relative to list price",
    )
    currency: str = "USD"
    unit: str
    tier: TierStructure | None = None
    free_allowance: FreeAllowance | None = None
    minimum_charge: float = 0.0
    record_id: str
    record_version: int
    pricing_source: str
    is_contracted_precedence_applied: bool = False


class PointInTimePricingQuery(BaseModel):
    """Input parameters for a point-in-time pricing query."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: str = Field(..., min_length=1)
    service_sku: str | None = None
    service: str | None = None
    resource_type: str | None = None
    region: str = Field(..., min_length=1)
    pricing_dimension: str = Field(default="DIM-03")
    query_date: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Point-in-time timestamp to evaluate against SCD Type 2 history",
    )
    tenant_id: str | None = None
    prefer_contracted: bool = True
