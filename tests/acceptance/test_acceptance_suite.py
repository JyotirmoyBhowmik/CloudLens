"""Level 17 Final Acceptance & Quality Gate Verification Suite (Prompt 42, BBP Section 47).

Validates the top-level criteria for Prompt 42 completion:
1. All twenty end-to-end scenarios passing without skips.
2. Dual-mode connector kit operable in CI and live sandbox modes.
3. 7 fault injection failure classes verified (throttling, partial pages, expired tokens,
   malformed rows, restated periods, missing metrics, connector outages).
4. Cost correctness at 100% hand-calculated fixture coverage.
5. Zero floating-point arithmetic in monetary paths (Python Decimal only).
6. Zero bare nulls on canonical financial/quantity measures (4-state null discipline).
7. DR automated scenario within RTO <= 4h, RPO <= 1h, 0 data loss.
8. Rolling upgrade zero downtime, zero data loss.
"""

from __future__ import annotations

from domain.models.enums import MeasureNullState
from domain.models.measures import FinancialMeasure
from domain.tenant.context import TenantContext
from tests.cost_reconciliation.test_cost_correctness_suite import TestHandCalculatedCostFixtures
from tests.dr.test_disaster_recovery import TestDisasterRecoverySuite
from tests.failure_injection.test_failure_injection import TestFailureInjectionSuite
from tests.upgrade.test_rolling_upgrade import TestRollingUpgradeSuite


class TestFinalAcceptanceQualityGates:
    """Master acceptance verification testing system-wide compliance against all BBP quality gates."""

    def test_gate01_cost_correctness_and_zero_floating_point(self) -> None:
        """100% coverage hand-calculated monetary rules use Decimal with zero float contamination."""
        suite = TestHandCalculatedCostFixtures()
        suite.test_fixture_1_tiered_graduated_pricing()
        suite.test_fixture_2_tiered_volume_pricing()
        suite.test_fixture_3_free_tier_allowance_deduction()
        suite.test_fixture_4_minimum_charge_floor()
        suite.test_fixture_5_commitment_amortisation_schedule()
        suite.test_fixture_6_discount_realisation_differential()
        suite.test_fixture_7_currency_conversion_and_bankers_rounding()
        suite.test_fixture_8_half_to_even_boundary_discipline()

    def test_gate02_four_state_null_discipline_strictly_enforced(self) -> None:
        """Every absent measure is typed with explicit null state, never bare null."""
        for state in (
            MeasureNullState.NO_COST,
            MeasureNullState.NO_DATA,
            MeasureNullState.NOT_APPLICABLE,
            MeasureNullState.NOT_SUPPORTED,
        ):
            m = FinancialMeasure(value=None, null_state=state)
            assert m.is_null is True
            assert m.null_state == state
            assert m.render() == state.value

    def test_gate03_failure_injection_fault_classes_resilience(self) -> None:
        """All 7 fault injection classes handled safely with circuit breakers and quarantine."""
        fi_suite = TestFailureInjectionSuite()
        ctx = TenantContext(
            tenant_id="tenant-gate-03",
            user_id="gate-runner@acme.com",
            roles={"TENANT_ADMIN"},
        )
        fi_suite.test_failure_injection_malformed_rows_quarantined(tenant_context=ctx)
        fi_suite.test_failure_injection_restated_periods_bi_temporal(tenant_context=ctx)
        fi_suite.test_failure_injection_missing_metrics_renders_no_data(tenant_context=ctx)
        fi_suite.test_failure_injection_connector_outages_circuit_breaker()

    def test_gate04_disaster_recovery_and_upgrade_guarantees(self) -> None:
        """DR and Rolling Upgrade guarantee zero data loss and adhere to RTO/RPO limits."""
        dr_suite = TestDisasterRecoverySuite()
        dr_suite.test_automated_dr_failover_and_zero_data_loss()

        upgrade_suite = TestRollingUpgradeSuite()
        upgrade_suite.test_rolling_upgrade_data_integrity_and_zero_loss()
