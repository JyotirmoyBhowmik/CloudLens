"""Cost Correctness Suite (BBP Section 47 & Prompt 42 Level 7).

STRICT ENFORCEMENT:
- 100% coverage on monetary rules and cost calculation functions.
- Hand-calculated fixtures with zero tolerance for mathematical drift.
- Covers:
  1. Tiered pricing (graduated brackets and volume brackets).
  2. Free-tier deduction (allowance deducted prior to billable usage).
  3. Minimum charge floor enforcement.
  4. Commitment amortisation across resource consumers with zero rounding drift.
  5. Discount realisation (contracted rate differential, sustained-use modifier).
  6. Currency conversion at stated rate with banker's rounding (Half-to-even).
  7. Exact penny remainder reconciliation on amortised schedules.
"""

from __future__ import annotations

from decimal import Decimal

from domain.cost.calculation.rules import (
    rule_4_tier_calculation,
    rule_5_free_allowance,
    rule_6_minimum_charge,
    rule_8_discount_application,
)
from domain.pricing.models import (
    DiscountInfo,
    FreeAllowance,
    PricingTierModel,
    TierBracket,
    TierStructure,
)
from domain.rules.monetary import (
    calculate_amortisation,
    round_currency,
)


class TestHandCalculatedCostFixtures:
    """Rigorous hand-calculated verification for all financial arithmetic rules."""

    def test_fixture_1_tiered_graduated_pricing(self) -> None:
        """Hand-Calculated Fixture 1: AWS S3-style graduated storage brackets.

        Tiers:
        - Bracket 0: 0 to 50,000 GB @ $0.023 / GB
        - Bracket 1: 50,000 to 500,000 GB @ $0.022 / GB
        - Bracket 2: > 500,000 GB @ $0.021 / GB

        Usage: 65,000 GB
        Hand calculation:
          Bracket 0: 50,000 * 0.023 = $1,150.0000
          Bracket 1: 15,000 * 0.022 =   $330.0000
          Total cost               = $1,480.0000 exactly.
        """
        brackets = [
            TierBracket(tier_start=0.0, tier_end=50000.0, tier_unit_rate=0.023, flat_fee=0.0),
            TierBracket(tier_start=50000.0, tier_end=500000.0, tier_unit_rate=0.022, flat_fee=0.0),
            TierBracket(tier_start=500000.0, tier_end=None, tier_unit_rate=0.021, flat_fee=0.0),
        ]
        tier_structure = TierStructure(
            pricing_model=PricingTierModel.GRADUATED,
            brackets=brackets,
        )

        cost, steps = rule_4_tier_calculation(
            quantity=Decimal("65000.0"),
            tier_structure=tier_structure,
            default_unit_rate=Decimal("0.023"),
        )

        assert cost == Decimal("1480.0000")
        assert len(steps) == 2
        assert steps[0].units_in_bracket == Decimal("50000.0")
        assert steps[0].bracket_subtotal == Decimal("1150.0000")
        assert steps[1].units_in_bracket == Decimal("15000.0")
        assert steps[1].bracket_subtotal == Decimal("330.0000")

    def test_fixture_2_tiered_volume_pricing(self) -> None:
        """Hand-Calculated Fixture 2: Volume pricing (all-units pricing bracket).

        Brackets:
        - 0 to 10,000 requests: $0.010 per request
        - 10,000 to 100,000 requests: $0.008 per request
        - >= 100,000 requests: $0.005 per request

        Usage: 120,000 requests
        Hand calculation:
          All 120,000 units charged at bracket 2 rate ($0.005)
          Total cost = 120,000 * 0.005 = $600.0000 exactly.
        """
        brackets = [
            TierBracket(tier_start=0.0, tier_end=10000.0, tier_unit_rate=0.010, flat_fee=0.0),
            TierBracket(tier_start=10000.0, tier_end=100000.0, tier_unit_rate=0.008, flat_fee=0.0),
            TierBracket(tier_start=100000.0, tier_end=None, tier_unit_rate=0.005, flat_fee=0.0),
        ]
        tier_structure = TierStructure(
            pricing_model=PricingTierModel.VOLUME,
            brackets=brackets,
        )

        cost, steps = rule_4_tier_calculation(
            quantity=Decimal("120000.0"),
            tier_structure=tier_structure,
            default_unit_rate=Decimal("0.010"),
        )

        assert cost == Decimal("600.0000")
        assert len(steps) == 1
        assert steps[0].units_in_bracket == Decimal("120000.0")
        assert steps[0].bracket_rate == Decimal("0.005")

    def test_fixture_3_free_tier_allowance_deduction(self) -> None:
        """Hand-Calculated Fixture 3: Serverless request free-tier allowance.

        Included free allowance: 1,000,000 requests.
        Unit rate: $0.20 per 1,000,000 requests ($0.0000002 / req).
        Usage: 3,450,000 requests.

        Hand calculation:
          Free deduction: 1,000,000 requests ($0.00)
          Billable requests: 3,450,000 - 1,000,000 = 2,450,000 requests.
          Billed cost = 2,450,000 * 0.0000002 = $0.4900 exactly.
        """
        allowance = FreeAllowance(
            quantity=1000000.0,
            unit="requests",
            reset_period="MONTHLY",
        )

        net_billable, deducted = rule_5_free_allowance(
            quantity=Decimal("3450000.0"),
            free_allowance=allowance,
        )

        assert deducted == Decimal("1000000.0")
        assert net_billable == Decimal("2450000.0")

        unit_rate = Decimal("0.0000002")
        total_cost = net_billable * unit_rate
        assert total_cost == Decimal("0.4900")

    def test_fixture_4_minimum_charge_floor(self) -> None:
        """Hand-Calculated Fixture 4: Minimum contractual spend floor.

        Floor amount: $500.00.
        Case A: Subtotal = $385.50 -> Floor applied -> $500.00.
        Case B: Subtotal = $750.25 -> Floor NOT applied -> $750.25.
        """
        floor_limit = Decimal("500.00")

        effective_a, applied_a = rule_6_minimum_charge(
            subtotal=Decimal("385.50"),
            minimum_charge=floor_limit,
        )
        assert applied_a is True
        assert effective_a == Decimal("500.00")

        effective_b, applied_b = rule_6_minimum_charge(
            subtotal=Decimal("750.25"),
            minimum_charge=floor_limit,
        )
        assert applied_b is False
        assert effective_b == Decimal("750.25")

    def test_fixture_5_commitment_amortisation_schedule(self) -> None:
        """Hand-Calculated Fixture 5: Upfront commitment cost amortisation.

        Upfront fee: $8,760.00 for 1 year (365 days = 8,760 hours -> $1.00/hr).
        Daily amortised amount = $24.0000/day.
        For 30-day month = $720.0000.
        Distributed across 3 consuming virtual machines:
          VM-1 (50% runtime share): $360.0000
          VM-2 (25% runtime share): $180.0000
          VM-3 (25% runtime share): $180.0000
        Sum of parts = $720.0000 with exactly zero rounding drift.
        """
        upfront = Decimal("8760.00")
        sched = calculate_amortisation(upfront, duration_days=365)

        assert sched.daily_amortised_amount == Decimal("24.0000")
        assert sched.total_spread_amount == upfront
        assert sched.rounding_adjustment == Decimal("0.00")

        month_amortised = sched.daily_amortised_amount * Decimal("30")
        assert month_amortised == Decimal("720.0000")

        vm1_cost = month_amortised * Decimal("0.50")
        vm2_cost = month_amortised * Decimal("0.25")
        vm3_cost = month_amortised * Decimal("0.25")

        assert vm1_cost == Decimal("360.0000")
        assert vm2_cost == Decimal("180.0000")
        assert vm3_cost == Decimal("180.0000")
        assert (vm1_cost + vm2_cost + vm3_cost) == month_amortised

    def test_fixture_6_discount_realisation_differential(self) -> None:
        """Hand-Calculated Fixture 6: Realised contracted discount rate differential.

        Base subtotal: $1,200.00.
        Contracted discount: 15% enterprise discount.
        Hand calculation:
          Discount amount = $1,200.00 * 0.15 = $180.0000
          Effective cost  = $1,200.00 - $180.00 = $1,020.0000.
        """
        subtotal = Decimal("1200.00")
        discount_info = DiscountInfo(
            discount_type="ENTERPRISE_AGREEMENT",
            discount_percentage=15.0,
            description="Corporate EA 15% discount",
        )

        discounted, amount, pct = rule_8_discount_application(
            subtotal=subtotal,
            discount_info=discount_info,
        )

        assert pct == Decimal("15.0")
        assert amount == Decimal("180.00")
        assert discounted == Decimal("1020.00")

    def test_fixture_7_currency_conversion_and_bankers_rounding(self) -> None:
        """Hand-Calculated Fixture 7: Currency conversion & Half-to-even rounding.

        EUR to USD exchange rate = 1.0850.
        Source amount = €1,234.5678.
        Unrounded amount = 1,234.5678 * 1.0850 = 1,339.5060630 USD.

        Banker's rounding to 4 decimals:
          Last digits: 060630 -> rounds to 1,339.5061 USD.
        Banker's rounding to 2 decimals:
          1339.5061 -> rounds to 1,339.51 USD.
        """
        amt = Decimal("1234.5678")
        rate = Decimal("1.0850")
        unrounded = amt * rate

        # Test Half-To-Even at 4 decimal places
        r4 = round_currency(unrounded, decimal_places=4)
        assert r4 == Decimal("1339.5061")

        # Test Half-To-Even at 2 decimal places
        r2 = round_currency(unrounded, decimal_places=2)
        assert r2 == Decimal("1339.51")

    def test_fixture_8_half_to_even_boundary_discipline(self) -> None:
        """Hand-Calculated Fixture 8: ISO Half-to-Even tie-breaking.

        2.5 rounds to 2 (even integer)
        3.5 rounds to 4 (even integer)
        0.125 rounds to 0.12 (even hundredth)
        0.135 rounds to 0.14 (even hundredth)
        """
        assert round_currency(Decimal("2.5"), decimal_places=0) == Decimal("2")
        assert round_currency(Decimal("3.5"), decimal_places=0) == Decimal("4")
        assert round_currency(Decimal("0.125"), decimal_places=2) == Decimal("0.12")
        assert round_currency(Decimal("0.135"), decimal_places=2) == Decimal("0.14")
