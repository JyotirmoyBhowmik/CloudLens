"""Domain models for Information Icons, Contextual Alerts, and Explanation Layer (Prompt 40).

Satisfies Master Brief Sections 4, 5, 50, 51, 52, 53:
- Full 17-field content model for Information Icon
- Eleven standard explanation panels
- Six inline contextual alerts with acknowledgement and audit
- Product-wide data freshness surface with staleness warnings
- Source traceability display
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from domain.alerting.models import ContextualAlert
from domain.pricing.information_panel import PricingInformationPanel
from domain.pricing.traceability import DataClassType, FreshnessIndicator, SourceTraceability


class StandardExplanationPanelType(StrEnum):
    """The eleven standard explanation panels specified by Master Brief Section 50."""

    WHAT_IS_THIS_SERVICE = "WHAT_IS_THIS_SERVICE"
    HOW_IS_IT_PRICED = "HOW_IS_IT_PRICED"
    WHY_IS_IT_FREE = "WHY_IS_IT_FREE"
    WHAT_CAUSES_ADDITIONAL_CHARGES = "WHAT_CAUSES_ADDITIONAL_CHARGES"
    WHAT_USAGE_IS_INCLUDED_IN_FREE_TIER = "WHAT_USAGE_IS_INCLUDED_IN_FREE_TIER"
    WHAT_IS_INCLUDED_IN_ESTIMATE = "WHAT_IS_INCLUDED_IN_ESTIMATE"
    WHAT_IS_EXCLUDED = "WHAT_IS_EXCLUDED"
    WHAT_PROVIDER_SOURCE_WAS_USED = "WHAT_PROVIDER_SOURCE_WAS_USED"
    WHEN_WAS_PRICING_LAST_RETRIEVED = "WHEN_WAS_PRICING_LAST_RETRIEVED"
    WHY_DOES_ACTUAL_BILLING_DIFFER = "WHY_DOES_ACTUAL_BILLING_DIFFER"
    WHAT_DEPENDENCY_IS_RESPONSIBLE = "WHAT_DEPENDENCY_IS_RESPONSIBLE"


class StandardExplanationPanel(BaseModel):
    """One of the eleven standard explanation panels answering estate questions with defensible facts."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    panel_type: StandardExplanationPanelType = Field(
        ..., description="One of the eleven canonical explanation types"
    )
    title: str = Field(..., description="Panel heading (e.g. 'What is this service')")
    headline: str = Field(..., description="High-level takeaway or summary sentence")
    narrative: str = Field(
        ...,
        description="Defensible plain-language explanation strictly derived from catalogue/calculation facts",
    )
    key_facts: dict[str, Any] = Field(
        default_factory=dict,
        description="Structured key-value metrics and parameters, zero unsupported numbers",
    )
    source_citation: str = Field(
        ..., description="Authoritative source citation (e.g. 'AWS Price List API v2026-09-01')"
    )
    source_url: str = Field(
        ..., description="Direct link to official provider documentation or price card"
    )
    last_verified_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp when explanation facts were verified",
    )
    conditions: list[str] = Field(
        default_factory=list,
        description="Mandatory qualification conditions (critical for free tier and estimates)",
    )
    rule_reference: str | None = Field(
        default=None, description="Internal rule or policy identifier (e.g. 'POL-03', 'EST-01')"
    )


class FreshnessSurfaceItem(BaseModel):
    """Individual data class freshness status on the global/page freshness surface."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    data_class: DataClassType = Field(
        ..., description="Data class (PRICING, BILLING_ACTUALS, USAGE_METRICS, INVENTORY)"
    )
    label: str = Field(..., description="Display label (e.g. 'Pricing Catalogue')")
    stated_time_text: str = Field(
        ...,
        description="Natural language stated time (e.g. 'pricing retrieved 2 hours ago')",
    )
    last_retrieved_at: datetime = Field(
        ..., description="Exact UTC timestamp of the most recent data retrieval"
    )
    age_hours: float = Field(..., ge=0.0, description="Elapsed hours since retrieval")
    staleness_threshold_hours: float = Field(
        ..., gt=0.0, description="Configured SLA staleness boundary in hours"
    )
    is_stale: bool = Field(
        ..., description="True if age_hours exceeds configured staleness_threshold_hours"
    )
    warning_message: str | None = Field(
        default=None,
        description="Prominent warning message if data class is stale or delayed",
    )
    provider: str = Field(
        default="CloudLens Aggregator", description="Provider or subsystem origin"
    )
    status: str = Field(default="FRESH", description="'FRESH', 'DELAYED', or 'STALE'")


class FreshnessSurfaceOverview(BaseModel):
    """Data freshness surface across the product (Prompt 40 Item 163)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    evaluated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Evaluation timestamp in UTC",
    )
    items: list[FreshnessSurfaceItem] = Field(
        ..., description="Freshness status items for all 4 required data classes"
    )
    has_staleness_warning: bool = Field(
        ..., description="True if any data class exceeds its staleness threshold"
    )
    overall_sla_breached: bool = Field(
        default=False, description="True if any data class exceeds its staleness threshold"
    )
    stale_count: int = Field(default=0, ge=0, description="Count of stale data classes")


class CostExplanationPayload(BaseModel):
    """Mandatory explanation payload attached to every pricing or cost value."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    metric_name: str = Field(
        ..., description="Name of the cost metric (e.g. 'Current Month Actual Cost')"
    )
    amount: float | None = Field(default=None, description="Numeric cost figure")
    currency: str = Field(default="USD", min_length=3, max_length=3)
    pricing_source: str = Field(..., min_length=1, description="Official provider price source")
    source_url: str = Field(..., min_length=1, description="Direct provider URL link")
    retrieval_timestamp: datetime = Field(..., description="Ingestion UTC timestamp")
    effective_date: datetime = Field(
        ..., description="Date from which the rate is legally effective"
    )
    region: str = Field(..., min_length=1, description="Datacenter region")
    cost_basis: str = Field(
        default="BILLED", description="Basis: BILLED, EFFECTIVE, LIST, CONTRACTED, AMORTISED"
    )
    derivation_formula: str | None = Field(
        default=None, description="Mathematical formula or attribution equation"
    )
    free_condition: str | None = Field(
        default=None, description="Explicit qualification condition if marked free"
    )
    is_stale: bool = Field(default=False, description="Whether pricing source is stale")
    staleness_warning: str | None = Field(
        default=None, description="Visible warning if pricing source is stale"
    )
    information_panel: PricingInformationPanel | None = Field(
        default=None, description="Full 17-field structured Information Panel if available"
    )


class ResourceExplanationSuite(BaseModel):
    """Full explanation suite for a service or resource, containing all 11 standard panels."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    resource_id: str = Field(..., description="Canonical resource ID or service identifier")
    service_name: str = Field(..., description="Display service name")
    provider: str = Field(..., description="Cloud provider (aws, azure, gcp, oci)")
    region: str = Field(..., description="Datacenter region")
    panels: list[StandardExplanationPanel] = Field(
        ..., description="All eleven standard explanation panels"
    )
    information_panel: PricingInformationPanel = Field(
        ..., description="Prompt 21 Item 164 17-field structured information panel"
    )
    freshness: FreshnessIndicator = Field(..., description="Pricing freshness status")
    source_traceability: SourceTraceability = Field(
        ..., description="Source provenance, effective date, and URL"
    )
    is_pricing_stale: bool = Field(
        default=False, description="Whether pricing data exceeds staleness threshold"
    )
    contextual_alerts: list[ContextualAlert] = Field(
        default_factory=list,
        description="Inline contextual alerts attached to this resource",
    )
