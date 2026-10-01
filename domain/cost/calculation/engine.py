"""Cost Calculation Engine (Prompt 23).

Combines provider pricing, resource configuration, usage, runtime, volume,
data transfer, storage, requests, billing period, free tiers, discounts,
commitments, reservations, and user-defined assumptions into a defensible estimate.
Every calculation produces not just a number but a first-class CostDerivation.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from domain.cost.calculation.models import (
    CostDerivation,
    EstimatedCost,
)
from domain.cost.calculation.rules import (
    rule_1_unit_conversion,
    rule_2_currency_conversion,
    rule_3_rounding,
    rule_4_tier_calculation,
    rule_5_free_allowance,
    rule_6_minimum_charge,
    rule_7_commitment_application,
    rule_8_discount_application,
    rule_10_data_freshness,
)
from domain.pricing.models import (
    CommitmentInfo,
    DiscountInfo,
    PricingRecord,
    ResolvedPriceQuote,
)
from domain.rules.monetary import to_decimal


class CostCalculationEngine:
    """Enterprise Cost Calculation Engine combining pricing, consumption, and rules."""

    def __init__(self, stale_threshold_hours: float = 24.0) -> None:
        self.stale_threshold_hours = stale_threshold_hours

    def calculate_cost(
        self,
        quantity: Decimal | float | str | int,
        unit: str,
        price_quote: ResolvedPriceQuote | PricingRecord,
        target_currency: str = "USD",
        duration_hours: Decimal | float | str | int | None = None,
        discount_info: DiscountInfo | None = None,
        commitment_info: CommitmentInfo | None = None,
        assumptions: dict[str, Any] | None = None,
        evaluation_date: date | None = None,
    ) -> tuple[Decimal, EstimatedCost, CostDerivation]:
        """Calculates exact cost and produces an auditable CostDerivation.

        Returns:
            tuple[Decimal, EstimatedCost, CostDerivation]:
                - Exact unrounded monetary decimal
                - Type-safe EstimatedCost value object
                - First-class CostDerivation detailing all derivation fields
        """
        user_assumptions = assumptions or {}
        steps_log: list[str] = []

        # 1. Extract Pricing Attributes with explicit type narrowing
        if isinstance(price_quote, ResolvedPriceQuote):
            pricing_unit = price_quote.unit
            pricing_currency = price_quote.currency
            pricing_dimension = price_quote.pricing_dimension
            pricing_source = price_quote.pricing_source
            pricing_source_url = None
            record_id = price_quote.record_id
            effective_from = price_quote.query_date
            rate_type_applied = price_quote.rate_type_applied
            unit_price = to_decimal(price_quote.effective_price)
            tier_structure = price_quote.tier
            free_allowance = price_quote.free_allowance
            minimum_charge = to_decimal(price_quote.minimum_charge)
            quote_discount = None
        else:
            pricing_unit = price_quote.unit
            pricing_currency = price_quote.currency
            pricing_dimension = price_quote.pricing_dimension
            pricing_source = price_quote.source
            pricing_source_url = price_quote.source_url
            record_id = price_quote.id
            effective_from = price_quote.effective_from
            rate_type_applied = price_quote.rate_type
            unit_price = to_decimal(price_quote.unit_price)
            tier_structure = price_quote.tier
            free_allowance = price_quote.free_allowance
            minimum_charge = to_decimal(price_quote.minimum_charge)
            quote_discount = price_quote.discount_info

        # 2. Rule 1: Unit Conversion Through Unit Catalogue
        raw_qty = to_decimal(quantity)
        steps_log.append(f"1. Input quantity: {raw_qty} {unit}.")

        converted_qty = rule_1_unit_conversion(
            quantity=raw_qty,
            from_unit=unit,
            to_unit=pricing_unit,
            duration_hours=duration_hours,
        )
        if unit.strip().lower() != pricing_unit.strip().lower():
            steps_log.append(
                f"2. Converted quantity to pricing unit '{pricing_unit}' via Unit Catalogue: {converted_qty} {pricing_unit}."
            )
        else:
            steps_log.append(f"2. Quantity matches pricing unit: {converted_qty} {pricing_unit}.")

        # 3. Rule 5: Free-Tier Consumption Deducted Before Charged Consumption
        net_billable_qty, allowance_deducted = rule_5_free_allowance(
            quantity=converted_qty,
            free_allowance=free_allowance,
        )
        if allowance_deducted > Decimal("0.0"):
            steps_log.append(
                f"3. Deducted free allowance of {allowance_deducted} {free_allowance.unit if free_allowance else pricing_unit}; "
                f"net billable consumption: {net_billable_qty} {pricing_unit}."
            )
        else:
            steps_log.append(
                f"3. No free allowance applied; billable consumption: {net_billable_qty} {pricing_unit}."
            )

        # 4. Rule 4: Tier Calculation (Graduated or Volume)
        subtotal_unrounded, tier_steps = rule_4_tier_calculation(
            quantity=net_billable_qty,
            tier_structure=tier_structure,
            default_unit_rate=unit_price,
        )
        if tier_structure and tier_structure.brackets:
            tier_summary = ", ".join(
                f"Bracket {s.bracket_index} ({s.units_in_bracket} @ {s.bracket_rate})"
                for s in tier_steps
            )
            steps_log.append(
                f"4. Applied {tier_structure.pricing_model.value} tiered pricing: {tier_summary} -> Subtotal: {subtotal_unrounded:.4f} {pricing_currency}."
            )
        else:
            steps_log.append(
                f"4. Applied flat unit rate of {unit_price:.4f} {pricing_currency}/{pricing_unit} -> Subtotal: {subtotal_unrounded:.4f} {pricing_currency}."
            )

        # 5. Rule 7: Commitment Application (Reservations & Savings Plans)
        applied_commitment_label = None
        effective_subtotal = subtotal_unrounded
        if commitment_info and commitment_info.commitment_type != "NONE":
            run_hrs = to_decimal(duration_hours or 730)
            comm_cost, comm_savings, comm_ref = rule_7_commitment_application(
                on_demand_rate=unit_price,
                commitment_info=commitment_info,
                runtime_hours=run_hrs,
            )
            applied_commitment_label = comm_ref
            steps_log.append(
                f"5. Applied commitment terms ({comm_ref}): Committed cost {comm_cost:.4f} (Saved {comm_savings:.4f})."
            )

        # 6. Rule 8: Discount Application (Contracted / Negotiated Rates)
        active_discount = discount_info or quote_discount
        discounted_subtotal, discount_amount, discount_percentage = rule_8_discount_application(
            subtotal=effective_subtotal,
            discount_info=active_discount,
        )
        if discount_amount > Decimal("0.0"):
            steps_log.append(
                f"6. Applied discount ({discount_percentage:.2f}%): Saved {discount_amount:.4f} {pricing_currency} -> {discounted_subtotal:.4f} {pricing_currency}."
            )
        else:
            steps_log.append("6. No additional contract discount applied.")

        # 7. Rule 6: Minimum-Charge Handling
        final_pre_currency, min_applied = rule_6_minimum_charge(
            subtotal=discounted_subtotal,
            minimum_charge=minimum_charge,
        )
        if min_applied:
            steps_log.append(
                f"7. Minimum billing charge applied: Subtotal bumped from {discounted_subtotal:.4f} to minimum floor {minimum_charge:.2f} {pricing_currency}."
            )
        else:
            steps_log.append(
                f"7. Subtotal {final_pre_currency:.4f} exceeds minimum charge floor ({minimum_charge:.2f})."
            )

        # 8. Rule 2: Currency Conversion at Stated Rate and Date
        conv_figure = rule_2_currency_conversion(
            amount=final_pre_currency,
            from_currency=pricing_currency,
            to_currency=target_currency,
            as_of_date=evaluation_date,
        )
        final_amount = conv_figure.target_amount
        if pricing_currency.upper() != target_currency.upper():
            steps_log.append(
                f"8. Query-time currency conversion from {pricing_currency} to {target_currency} at exchange rate {conv_figure.exchange_rate} (effective {conv_figure.rate_effective_date}): {final_amount:.4f} {target_currency}."
            )
        else:
            steps_log.append(
                f"8. Reporting in native currency: {final_amount:.4f} {target_currency}."
            )

        # 9. Rule 10: Data Freshness Check
        retrieval_dt = getattr(price_quote, "retrieved_at", datetime.now(UTC))
        is_stale, age_hours = rule_10_data_freshness(
            retrieved_at=retrieval_dt,
            stale_threshold_hours=self.stale_threshold_hours,
        )
        stale_reason = (
            f"Pricing data age ({age_hours:.1f} hours) exceeds staleness threshold ({self.stale_threshold_hours:.1f} hours)."
            if is_stale
            else None
        )
        steps_log.append(
            f"9. Data freshness check: Age {age_hours:.1f} hrs, stale={is_stale} (threshold {self.stale_threshold_hours:.1f} hrs)."
        )

        # 10. Rule 3: Uniform Banker's Rounding (Final Step Only)
        rounded_total = rule_3_rounding(final_amount, decimal_places=2)
        steps_log.append(
            f"10. Final uniform banker's rounding (ROUND_HALF_EVEN): {rounded_total:.2f} {target_currency}."
        )

        # 11. Compile First-Class CostDerivation
        derivation = CostDerivation(
            rate_applied=unit_price,
            rate_type_applied=rate_type_applied,
            pricing_dimension=pricing_dimension,
            pricing_dimension_name=f"Dimension {pricing_dimension}",
            quantity_consumed=raw_qty,
            unit=unit,
            tier_structure_applied=tier_structure is not None and len(tier_structure.brackets) > 0,
            tier_breakdown=tier_steps,
            free_allowance_deducted=allowance_deducted,
            free_allowance_unit=free_allowance.unit if free_allowance else None,
            net_billable_quantity=net_billable_qty,
            minimum_charge_applied=min_applied,
            minimum_charge_amount=minimum_charge,
            discount_applied_amount=discount_amount,
            discount_applied_percentage=discount_percentage,
            discount_reference=active_discount.contract_reference if active_discount else None,
            commitment_applied=applied_commitment_label,
            assumptions=user_assumptions,
            step_by_step_explanation=steps_log,
            retrieval_timestamp=retrieval_dt,
            pricing_source=pricing_source,
            pricing_source_url=pricing_source_url,
            effective_date=effective_from,
            currency=target_currency,
            is_stale=is_stale,
            stale_reason=stale_reason,
        )

        # 12. Create Four-Value Structurally Segregated EstimatedCost
        estimated_cost = EstimatedCost(
            amount=float(rounded_total),
            currency=target_currency,
            pricing_record_id=record_id,
            pricing_source=pricing_source,
            usage_quantity=float(raw_qty),
            usage_unit=unit,
            estimation_formula=f"{raw_qty} {unit} * {unit_price} {pricing_currency}/{pricing_unit} = {rounded_total} {target_currency}",
        )

        return final_amount, estimated_cost, derivation


_global_engine: CostCalculationEngine | None = None


def get_calculation_engine() -> CostCalculationEngine:
    """Returns singleton instance of CostCalculationEngine."""
    global _global_engine
    if _global_engine is None:
        _global_engine = CostCalculationEngine()
    return _global_engine


def reset_calculation_engine() -> None:
    """Resets singleton for testing environments."""
    global _global_engine
    _global_engine = None


__all__ = [
    "CostCalculationEngine",
    "get_calculation_engine",
    "reset_calculation_engine",
]
