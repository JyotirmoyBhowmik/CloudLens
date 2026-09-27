"""Source Traceability and Data Freshness Engine (Prompt 21 Items 162 & 163).

Enforces:
- Source traceability on every pricing and cost statement:
  pricing source, retrieval timestamp, region, currency, effective date, and official provider link.
- ACCEPTANCE: No pricing statement can be produced without a source reference and an effective date.
- Data freshness as a first-class computed attribute with configurable thresholds per data class.
- ACCEPTANCE: A stale pricing value is flagged with its last known retrieval date.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from domain.models.exceptions import MissingTraceabilityException


class DataClassType(StrEnum):
    """Data classes with discrete freshness policies."""

    INVENTORY = "INVENTORY"  # Resources, tags, hierarchy
    PRICING = "PRICING"  # Rate cards, SKU catalogs
    BILLING_ACTUALS = "BILLING_ACTUALS"  # Cost details, CUR, invoices
    USAGE_METRICS = "USAGE_METRICS"  # CPU, memory, IOPS, data transfer
    BUDGETS = "BUDGETS"  # Provider budgets and alerts


# Default staleness thresholds in hours per BBP Section 29 / Prompt 15 Item 98
DEFAULT_STALENESS_THRESHOLDS_HOURS: dict[DataClassType, float] = {
    DataClassType.INVENTORY: 6.0,  # Inventory full sync daily, incremental 4-6h
    DataClassType.PRICING: 168.0,  # Pricing weekly refresh (7 days)
    DataClassType.BILLING_ACTUALS: 24.0,  # Invoices / cost 4-8h in open period, daily general
    DataClassType.USAGE_METRICS: 4.0,  # Usage hourly to daily
    DataClassType.BUDGETS: 24.0,  # Provider budgets daily
}


class SourceTraceability(BaseModel):
    """Source traceability discipline making every pricing statement defensible (Item 162)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    pricing_source: str = Field(
        ...,
        min_length=1,
        description="Catalogue source (e.g. aws_price_list_bulk, azure_price_sheet)",
    )
    source_url: str = Field(
        ...,
        min_length=1,
        description="Official provider pricing or documentation reference link",
    )
    retrieval_timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp when rate was ingested in UTC",
    )
    region: str = Field(..., min_length=1, description="Datacenter region")
    currency: str = Field(default="USD", min_length=3, max_length=3)
    effective_date: datetime = Field(
        ..., description="UTC date from which this rate is legally effective"
    )
    is_verified: bool = Field(default=True, description="Whether source URL has been validated")

    @field_validator("pricing_source")
    @classmethod
    def validate_source(cls, v: str) -> str:
        if not v or not v.strip():
            raise MissingTraceabilityException("Pricing source cannot be empty.")
        return v.strip()

    @field_validator("source_url")
    @classmethod
    def validate_source_url(cls, v: str) -> str:
        if not v or not v.strip():
            raise MissingTraceabilityException("Official provider source_url is required.")
        return v.strip()

    @field_validator("effective_date", "retrieval_timestamp")
    @classmethod
    def ensure_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            return v.replace(tzinfo=UTC)
        return v.astimezone(UTC)


class FreshnessIndicator(BaseModel):
    """Computed freshness status for provider-derived values (Item 163)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    data_class: DataClassType
    last_known_retrieval_date: datetime = Field(
        ..., description="Timestamp of the most recent successful data retrieval"
    )
    staleness_threshold_hours: float = Field(
        ..., gt=0.0, description="Configured staleness boundary in hours"
    )
    is_stale: bool = Field(
        ..., description="Computed dynamically: True if (now - retrieved_at) > threshold"
    )
    age_hours: float = Field(..., ge=0.0, description="Elapsed hours since retrieval")
    evaluation_timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp when freshness was evaluated",
    )

    @classmethod
    def compute(
        cls,
        retrieved_at: datetime,
        data_class: DataClassType = DataClassType.PRICING,
        custom_threshold_hours: float | None = None,
        as_of: datetime | None = None,
    ) -> FreshnessIndicator:
        """Dynamically computes freshness status rather than assuming fresh."""
        now = as_of or datetime.now(UTC)
        target_retrieved = (
            retrieved_at.astimezone(UTC)
            if retrieved_at.tzinfo
            else retrieved_at.replace(tzinfo=UTC)
        )
        target_now = now.astimezone(UTC) if now.tzinfo else now.replace(tzinfo=UTC)

        threshold = (
            custom_threshold_hours
            if custom_threshold_hours is not None
            else DEFAULT_STALENESS_THRESHOLDS_HOURS.get(data_class, 168.0)
        )

        age = max(0.0, (target_now - target_retrieved).total_seconds() / 3600.0)
        is_stale = age > threshold

        return cls(
            data_class=data_class,
            last_known_retrieval_date=target_retrieved,
            staleness_threshold_hours=threshold,
            is_stale=is_stale,
            age_hours=round(age, 2),
            evaluation_timestamp=target_now,
        )
