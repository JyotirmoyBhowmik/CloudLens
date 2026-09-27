"""Pricing Status Engine with Stored Conditions (Prompt 21 Item 158).

Enforces:
- Seven-state pricing classification: FREE, FREE TIER, CONDITIONAL FREE, PAID, ESTIMATED, UNKNOWN, NOT APPLICABLE.
- Stored conditions explaining the exact rationale behind every classification.
- STRICT PROHIBITION: Never default an unknown status to free or to zero.
- Complete defensibility tying classification to catalogue records and source traceability.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from domain.models.enums import PricingStatus
from domain.models.exceptions import UndefendedFreeStatusException
from domain.pricing.models import PricingRecord
from domain.pricing.statement_composer import PricingStatementComposer
from domain.pricing.traceability import SourceTraceability

logger = logging.getLogger(__name__)

# Canonical resource types with no standalone billing construct
NON_BILLABLE_RESOURCE_TYPES: set[str] = {
    "resource_group",
    "security_group_rule",
    "tag_binding",
    "iam_policy_attachment",
    "route_table_entry",
}


class PricingStatusClassification(BaseModel):
    """Computed pricing classification with stored defensible conditions (Item 158)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: PricingStatus
    conditions: list[str] = Field(
        min_length=1,
        description="Explicit list of conditions and thresholds that produced this classification",
    )
    statement: str = Field(..., description="Human-readable condition-grounded pricing sentence")
    rule_id: str = Field(..., description="Classification rule identifier for auditability")
    evaluated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp when status was computed in UTC",
    )
    traceability: SourceTraceability | None = Field(
        default=None,
        description="Source provenance reference (None for UNKNOWN or NOT_APPLICABLE)",
    )
    is_defensible: bool = Field(
        default=True, description="Whether statement has verifiable provenance"
    )

    @model_validator(mode="after")
    def validate_defensible_status(self) -> PricingStatusClassification:
        """Enforces that a bare 'Free' cannot be emitted and free statuses require defensible conditions."""
        if self.status in (
            PricingStatus.FREE,
            PricingStatus.FREE_TIER,
            PricingStatus.CONDITIONAL_FREE,
        ):
            if not self.conditions or not any(c.strip() for c in self.conditions):
                raise UndefendedFreeStatusException(
                    "A bare 'FREE' status is strictly prohibited without explicit conditions (Item 159)."
                )
            if self.statement.strip().lower() in ("free", "free.", "is free"):
                raise UndefendedFreeStatusException(
                    "A bare 'Free' statement cannot be emitted by the status engine."
                )
        return self


class PricingStatusEngine:
    """Evaluates services and resources against the 7-state pricing classification."""

    @classmethod
    def evaluate(
        cls,
        record: PricingRecord | None = None,
        resource_type: str | None = None,
        is_estimated: bool = False,
        dependent_services: list[str] | None = None,
        free_condition: str | None = None,
    ) -> PricingStatusClassification:
        """Computes pricing status and stores conditions alongside it.

        STRICT PROHIBITION: Never default an unknown status to free or to zero!
        """
        now = datetime.now(UTC)

        # 1. Non-billable structural constructs
        if resource_type and resource_type.lower() in NON_BILLABLE_RESOURCE_TYPES:
            return PricingStatusClassification(
                status=PricingStatus.NOT_APPLICABLE,
                conditions=[
                    f"Resource type '{resource_type}' is an organizational or metadata construct.",
                    "No standalone provider billing metric or consumption charge applies.",
                ],
                statement="Not applicable: Structural or metadata entity with no standalone charge.",
                rule_id="RULE-PSE-07-NOT-APPLICABLE",
                evaluated_at=now,
                traceability=None,
                is_defensible=True,
            )

        # 2. Unknown status (Record missing or unmapped in catalogue)
        # STRICT PROHIBITION: Never default unknown to free or zero!
        if record is None:
            return PricingStatusClassification(
                status=PricingStatus.UNKNOWN,
                conditions=[
                    "No matching rate card or SKU found in the active pricing catalogue.",
                    "Price rate resolution is pending or SKU is unmapped.",
                    "Classification strictly withheld per Prompt 21 (Never defaulted to Free or Zero).",
                ],
                statement="Unknown: Pricing rate card unresolved in catalogue. Not defaulted to free.",
                rule_id="RULE-PSE-06-UNKNOWN",
                evaluated_at=now,
                traceability=None,
                is_defensible=True,
            )

        # 3. Estimated rates
        if is_estimated:
            stmt = PricingStatementComposer.compose_statement_for_record(
                record=record,
                dependent_services=dependent_services,
                free_condition=free_condition,
            )
            return PricingStatusClassification(
                status=PricingStatus.ESTIMATED,
                conditions=[
                    "Rate is derived through algorithmic approximation or surrogate proxy metrics.",
                    *stmt.conditions,
                ],
                statement=f"Estimated: {stmt.text}",
                rule_id="RULE-PSE-05-ESTIMATED",
                evaluated_at=now,
                traceability=stmt.traceability,
                is_defensible=True,
            )

        # 4. Free Tier (Included allowance before billable rates activate)
        if record.free_allowance is not None and record.free_allowance.quantity > 0:
            stmt = PricingStatementComposer.compose_free_allowance_statement(record)
            return PricingStatusClassification(
                status=PricingStatus.FREE_TIER,
                conditions=stmt.conditions,
                statement=stmt.text,
                rule_id="RULE-PSE-02-FREE-TIER",
                evaluated_at=now,
                traceability=stmt.traceability,
                is_defensible=True,
            )

        # 5. Free vs Conditional Free
        if record.unit_price == 0.0:
            cond = free_condition or str(record.attributes.get("free_condition", ""))
            if (
                cond
                and cond.strip()
                and cond.strip().lower() not in ("free", "free.", "none", "n/a")
            ) or record.attributes.get("is_free"):
                if not cond or not cond.strip():
                    raise UndefendedFreeStatusException(
                        "A bare 'FREE' status cannot be emitted without explicit conditions."
                    )
                stmt = PricingStatementComposer.compose_free_statement(
                    record, free_condition=cond.strip()
                )
                return PricingStatusClassification(
                    status=PricingStatus.FREE,
                    conditions=stmt.conditions,
                    statement=stmt.text,
                    rule_id="RULE-PSE-01-FREE",
                    evaluated_at=now,
                    traceability=stmt.traceability,
                    is_defensible=True,
                )

            deps = (
                dependent_services
                or record.attributes.get("dependent_services")
                or ["underlying infrastructure", "data transfer"]
            )
            prereq = str(record.attributes.get("prerequisite_condition", "standard configuration"))
            stmt = PricingStatementComposer.compose_conditional_free_statement(
                record=record,
                prerequisite_condition=prereq,
                dependent_services=deps,
            )
            return PricingStatusClassification(
                status=PricingStatus.CONDITIONAL_FREE,
                conditions=stmt.conditions,
                statement=stmt.text,
                rule_id="RULE-PSE-03-CONDITIONAL-FREE",
                evaluated_at=now,
                traceability=stmt.traceability,
                is_defensible=True,
            )

        # 6. Paid (Standard billable consumption)
        stmt = PricingStatementComposer.compose_paid_statement(record)
        return PricingStatusClassification(
            status=PricingStatus.PAID,
            conditions=stmt.conditions,
            statement=stmt.text,
            rule_id="RULE-PSE-04-PAID",
            evaluated_at=now,
            traceability=stmt.traceability,
            is_defensible=True,
        )
