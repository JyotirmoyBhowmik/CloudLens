"""Pricing Statement Composer (Prompt 21 Item 159).

Enforces:
- FREE is NEVER displayed without the conditions under which it is free.
- STRICT PROHIBITION: The composer NEVER generates any number itself.
  Every number comes strictly from the catalogue entity.
- ACCEPTANCE: A bare 'Free' cannot be emitted; the composer requires conditions.
- ACCEPTANCE: No pricing statement can be produced without a source reference and effective date.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from domain.models.enums import PricingStatus
from domain.models.exceptions import (
    MissingTraceabilityException,
    UndefendedFreeStatusException,
)
from domain.pricing.models import PricingRecord
from domain.pricing.traceability import SourceTraceability


class PricingStatement(BaseModel):
    """Defensible statement output with complete provenance."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str = Field(..., min_length=5, description="Full human-readable statement")
    status: PricingStatus
    conditions: list[str] = Field(default_factory=list, description="Explicit conditions")
    traceability: SourceTraceability

    @model_validator(mode="after")
    def validate_statement(self) -> PricingStatement:
        """Enforces that a bare 'Free' cannot be emitted and free statements require conditions."""
        if self.status in (
            PricingStatus.FREE,
            PricingStatus.FREE_TIER,
            PricingStatus.CONDITIONAL_FREE,
        ):
            if not self.conditions or not any(c.strip() for c in self.conditions):
                raise UndefendedFreeStatusException(
                    "Free pricing statements strictly require explicit, defensible conditions."
                )
            if self.text.strip().lower() in ("free", "free.", "is free"):
                raise UndefendedFreeStatusException(
                    "A bare 'Free' statement cannot be emitted per Prompt 21 Item 159."
                )
        if not self.traceability.pricing_source or not self.traceability.source_url:
            raise MissingTraceabilityException(
                "A pricing statement cannot be produced without a source reference and effective date."
            )
        return self


class PricingStatementComposer:
    """Produces condition-grounded, defensible natural language pricing statements.

    Every number in these statements originates directly from the catalogue record.
    """

    @classmethod
    def compose_free_allowance_statement(
        cls,
        record: PricingRecord,
        traceability: SourceTraceability | None = None,
    ) -> PricingStatement:
        """Produces: 'Free up to {quantity} {unit} ({reset_period}) with charges of {post_rate} {currency}/{unit} beyond it.'

        All numbers are sourced from record.free_allowance.
        """
        trace = traceability or cls._derive_traceability(record)
        allowance = record.free_allowance

        if not allowance:
            raise UndefendedFreeStatusException(
                "Cannot compose free allowance statement without a structured FreeAllowance entity."
            )

        if allowance.quantity <= 0.0 and allowance.post_allowance_rate <= 0.0:
            raise UndefendedFreeStatusException(
                "A bare 'FREE' status is forbidden. Explicit conditions and thresholds are required."
            )

        # Quantity and rates come strictly from catalogue allowance, never synthesized
        qty_str = f"{allowance.quantity:g}"
        rate_str = f"{allowance.post_allowance_rate:g}"
        unit_str = allowance.unit
        period_str = allowance.reset_period.lower().replace("_", " ")

        if "request" in unit_str.lower() or "call" in unit_str.lower():
            text = (
                f"Free for {qty_str} {unit_str} ({period_str}) with additional requests "
                f"billed at {rate_str} {record.currency} per {unit_str}."
            )
        else:
            text = (
                f"Free up to {qty_str} {unit_str} ({period_str}) with charges of "
                f"{rate_str} {record.currency} per {unit_str} beyond it."
            )

        conditions = [
            f"Included free allowance: {qty_str} {unit_str} per {period_str}",
            f"Overage rate: {rate_str} {record.currency} per {unit_str}",
        ]

        return PricingStatement(
            text=text,
            status=PricingStatus.FREE_TIER,
            conditions=conditions,
            traceability=trace,
        )

    @classmethod
    def compose_conditional_free_statement(
        cls,
        record: PricingRecord,
        prerequisite_condition: str,
        dependent_services: list[str] | None = None,
        traceability: SourceTraceability | None = None,
    ) -> PricingStatement:
        """Produces: 'No separate service charge, but dependent services ({services}) may incur charges.'"""
        trace = traceability or cls._derive_traceability(record)

        if not prerequisite_condition or not prerequisite_condition.strip():
            raise UndefendedFreeStatusException(
                "A bare 'FREE' cannot be emitted for conditional services without explicit conditions."
            )

        deps = dependent_services or ["storage", "data transfer"]
        dep_str = ", ".join(deps)
        text = (
            f"No separate service charge ({prerequisite_condition}), "
            f"but dependent services ({dep_str}) may incur charges."
        )

        conditions = [
            f"Prerequisite: {prerequisite_condition}",
            f"Dependent billable services: {dep_str}",
        ]

        return PricingStatement(
            text=text,
            status=PricingStatus.CONDITIONAL_FREE,
            conditions=conditions,
            traceability=trace,
        )

    @classmethod
    def compose_free_statement(
        cls,
        record: PricingRecord,
        free_condition: str,
        traceability: SourceTraceability | None = None,
    ) -> PricingStatement:
        """Produces: 'Free: {free_condition}.'

        Enforces: FREE is never emitted without explicit conditions (Prompt 21 Item 159).
        """
        trace = traceability or cls._derive_traceability(record)

        if not free_condition or not free_condition.strip():
            raise UndefendedFreeStatusException(
                "A bare 'FREE' status or statement is strictly prohibited without explicit conditions."
            )

        cond = free_condition.strip()
        if cond.lower() in ("free", "free.", "is free", "none", "n/a"):
            raise UndefendedFreeStatusException(
                "A bare 'FREE' status or statement is strictly prohibited without explicit conditions."
            )

        text = f"Free: {cond}."
        conditions = [f"Condition: {cond}"]

        return PricingStatement(
            text=text,
            status=PricingStatus.FREE,
            conditions=conditions,
            traceability=trace,
        )

    @classmethod
    def compose_paid_statement(
        cls,
        record: PricingRecord,
        traceability: SourceTraceability | None = None,
    ) -> PricingStatement:
        """Produces statement for standard billable rates: 'Billed at {rate} {currency} per {unit}.'"""
        trace = traceability or cls._derive_traceability(record)
        rate_str = f"{record.unit_price:g}"
        unit_str = record.unit

        if record.tier and record.tier.brackets:
            first_bracket = record.tier.brackets[0]
            last_bracket = record.tier.brackets[-1]
            first_rate = f"{first_bracket.tier_unit_rate:g}"
            last_rate = f"{last_bracket.tier_unit_rate:g}"
            text = (
                f"Tiered pricing starting at {first_rate} {record.currency} per {unit_str} "
                f"graduating to {last_rate} {record.currency} per {unit_str}."
            )
            conditions = [
                f"Model: {record.tier.pricing_model.value}",
                f"Starting tier: {first_rate} {record.currency}/{unit_str}",
                f"Highest volume tier: {last_rate} {record.currency}/{unit_str}",
            ]
        else:
            text = f"Billed at {rate_str} {record.currency} per {unit_str}."
            conditions = [f"Base unit rate: {rate_str} {record.currency}/{unit_str}"]

        if record.minimum_charge > 0.0:
            min_str = f"{record.minimum_charge:g}"
            text += f" Subject to a minimum charge of {min_str} {record.currency}."
            conditions.append(f"Minimum floor charge: {min_str} {record.currency}")

        return PricingStatement(
            text=text,
            status=PricingStatus.PAID,
            conditions=conditions,
            traceability=trace,
        )

    @classmethod
    def compose_statement_for_record(
        cls,
        record: PricingRecord,
        dependent_services: list[str] | None = None,
        free_condition: str | None = None,
        traceability: SourceTraceability | None = None,
    ) -> PricingStatement:
        """Dispatches to appropriate template based on catalogue fields without hardcoding numbers."""
        if record.free_allowance is not None and record.free_allowance.quantity > 0:
            return cls.compose_free_allowance_statement(record, traceability)
        elif record.unit_price == 0.0:
            cond = free_condition or str(record.attributes.get("free_condition", ""))
            if (
                cond
                and cond.strip()
                and cond.strip().lower() not in ("free", "free.", "none", "n/a")
            ):
                return cls.compose_free_statement(
                    record=record,
                    free_condition=cond.strip(),
                    traceability=traceability,
                )
            if record.attributes.get("is_free"):
                raise UndefendedFreeStatusException(
                    "A bare 'FREE' status cannot be emitted without explicit conditions."
                )
            deps = dependent_services or record.attributes.get("dependent_services")
            prereq = str(
                record.attributes.get("prerequisite_condition", "standard resource deployment")
            )
            return cls.compose_conditional_free_statement(
                record=record,
                prerequisite_condition=prereq,
                dependent_services=deps,
                traceability=traceability,
            )
        else:
            return cls.compose_paid_statement(record, traceability)

    @classmethod
    def _derive_traceability(cls, record: PricingRecord) -> SourceTraceability:
        """Extracts and validates traceability from catalogue entity."""
        if not record.source or not record.source_url:
            raise MissingTraceabilityException(
                f"PricingRecord {record.id} lacks required source reference or source URL."
            )
        return SourceTraceability(
            pricing_source=record.source,
            source_url=record.source_url,
            retrieval_timestamp=record.retrieved_at,
            region=record.region,
            currency=record.currency,
            effective_date=record.effective_from,
        )
