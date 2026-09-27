"""Information-Panel Content Model (Prompt 21 Item 164).

Enforces:
- Comprehensive structured payload designed for Prompt 40 UI rendering.
- Covers pricing model, region, configuration, rate, monthly estimate, free-tier status,
  allowance, additional usage rate, currency, billing unit, transfer/storage notes,
  discount & commitment applicability, tax treatment, source traceability, and data freshness.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from domain.models.enums import PricingStatus
from domain.pricing.cost_sources import CostValue
from domain.pricing.models import FreeAllowance, PricingRecord
from domain.pricing.status_engine import (
    PricingStatusClassification,
    PricingStatusEngine,
)
from domain.pricing.traceability import (
    DataClassType,
    FreshnessIndicator,
    SourceTraceability,
)


class PricingInformationPanel(BaseModel):
    """Complete structured payload rendered by the cloud resource information panel (Item 164)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    resource_id: str | None = Field(default=None, description="Target resource identifier")
    service: str = Field(..., description="Service display name")
    service_sku: str | None = Field(default=None, description="Provider native SKU code")
    pricing_model: str = Field(..., description="Model: OnDemand, Tiered, Reserved, etc.")
    region: str = Field(..., description="Datacenter region")
    configuration: dict[str, Any] = Field(
        default_factory=dict, description="Hardware or service attributes"
    )
    unit_rate: float = Field(..., ge=0.0, description="Applicable unit price")
    monthly_estimate: float | None = Field(
        default=None, description="Calculated monthly run-rate estimate"
    )
    pricing_status: PricingStatus = Field(..., description="7-state pricing classification")
    pricing_status_conditions: list[str] = Field(
        default_factory=list, description="Explicit conditions for classification"
    )
    pricing_statement: str = Field(..., description="Defensible natural language sentence")
    free_tier_status: str = Field(..., description="Free tier classification description")
    free_tier_allowance: FreeAllowance | None = Field(
        default=None, description="Structured allowance quantity and post-rate"
    )
    additional_usage_rate: float | None = Field(
        default=None, description="Rate charged once free allowance is exhausted"
    )
    currency: str = Field(default="USD", description="Currency ISO 4217 code")
    billing_unit: str = Field(..., description="Unit of measure (e.g. Hrs, GB-Mo)")
    data_transfer_note: str | None = Field(
        default="Standard internet egress charges apply beyond free allowances.",
        description="Egress and inter-region transfer considerations",
    )
    storage_note: str | None = Field(
        default="Persistent storage billed independently from compute runtime.",
        description="Attached storage billing rules",
    )
    discount_applicability: str | None = Field(
        default=None, description="Enterprise discount program applicability"
    )
    commitment_applicability: str | None = Field(
        default=None, description="Savings Plan or Reserved Instance eligibility"
    )
    tax_treatment: str | None = Field(
        default="Exclusive of applicable sales tax or VAT.",
        description="Statutory tax disclosure",
    )
    source_traceability: SourceTraceability = Field(
        ..., description="Provenance, effective date, and provider documentation URL"
    )
    freshness: FreshnessIndicator = Field(
        ..., description="Freshness evaluation and staleness boundary"
    )
    caveats: list[str] = Field(
        default_factory=list,
        description="Defensible caveats, exceptions, and billing edge cases (Item 163)",
    )
    related_metrics: list[str] = Field(
        default_factory=list,
        description="Key performance and utilization metrics correlated with this resource's cost (Item 163)",
    )
    cost_breakdown: list[CostValue] = Field(
        default_factory=list,
        description="Structurally segregated cost records (Actual, Estimated, Forecast, etc.)",
    )


class InformationPanelBuilder:
    """Constructs defensible information panels from catalogue and resource data."""

    @classmethod
    def build_from_record(
        cls,
        record: PricingRecord,
        resource_id: str | None = None,
        monthly_hours: float = 730.0,
        cost_breakdown: list[CostValue] | None = None,
        custom_configuration: dict[str, Any] | None = None,
        custom_caveats: list[str] | None = None,
        custom_related_metrics: list[str] | None = None,
    ) -> PricingInformationPanel:
        """Constructs an information panel payload from a catalogue record."""
        classification: PricingStatusClassification = PricingStatusEngine.evaluate(record=record)

        # Monthly estimate calculation (e.g. 730 hours for compute)
        monthly_est: float | None = None
        if record.unit_price > 0:
            if "hr" in record.unit.lower():
                monthly_est = round(record.unit_price * monthly_hours, 2)
            elif "gb-mo" in record.unit.lower():
                monthly_est = round(record.unit_price * 100.0, 2)  # Baseline 100 GB
            else:
                monthly_est = round(record.unit_price * 1.0, 2)

        free_status_desc = "Standard Paid Service (No free tier)"
        add_rate: float | None = None
        if record.free_allowance:
            free_status_desc = f"Included Free Tier ({record.free_allowance.quantity:g} {record.free_allowance.unit})"
            add_rate = record.free_allowance.post_allowance_rate

        traceability = classification.traceability or SourceTraceability(
            pricing_source=record.source,
            source_url=record.source_url or "https://aws.amazon.com/pricing/",
            retrieval_timestamp=record.retrieved_at,
            region=record.region,
            currency=record.currency,
            effective_date=record.effective_from,
        )

        freshness = FreshnessIndicator.compute(
            retrieved_at=record.retrieved_at,
            data_class=DataClassType.PRICING,
        )

        pricing_model_desc = "On-Demand"
        if record.tier and record.tier.brackets:
            pricing_model_desc = f"Tiered ({record.tier.pricing_model.value})"

        discount_note = None
        if record.discount_info:
            discount_note = (
                f"{record.discount_info.discount_percentage:g}% discount applied via "
                f"{record.discount_info.contract_reference or 'Enterprise Agreement'}."
            )

        commitment_note = None
        if record.commitment_info and record.commitment_info.commitment_type != "NONE":
            commitment_note = (
                f"Eligible for {record.commitment_info.commitment_type} "
                f"({record.commitment_info.term_months}-month term)."
            )

        default_caveats = [
            "Data transfer egress beyond free tier is charged according to regional destination rates.",
            "Associated storage, snapshots, and IOPS are metered and billed separately.",
            "Prices exclude statutory VAT, sales taxes, or withholding taxes unless explicitly stated.",
        ]
        default_metrics = [
            "CPU Utilization (%)",
            "Memory Working Set (MB)",
            "Network In/Out (Bytes)",
            "Disk Read/Write Operations",
        ]

        return PricingInformationPanel(
            resource_id=resource_id,
            service=record.service,
            service_sku=record.service_sku,
            pricing_model=pricing_model_desc,
            region=record.region,
            configuration=custom_configuration or record.attributes,
            unit_rate=record.unit_price,
            monthly_estimate=monthly_est,
            pricing_status=classification.status,
            pricing_status_conditions=classification.conditions,
            pricing_statement=classification.statement,
            free_tier_status=free_status_desc,
            free_tier_allowance=record.free_allowance,
            additional_usage_rate=add_rate,
            currency=record.currency,
            billing_unit=record.unit,
            discount_applicability=discount_note,
            commitment_applicability=commitment_note,
            source_traceability=traceability,
            freshness=freshness,
            caveats=custom_caveats if custom_caveats is not None else default_caveats,
            related_metrics=custom_related_metrics
            if custom_related_metrics is not None
            else default_metrics,
            cost_breakdown=cost_breakdown or [],
        )
