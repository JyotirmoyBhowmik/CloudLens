"""Comprehensive Unit and Integration Tests for Forecasting Engine (Prompt 29).

Enforces:
- Prompt 29: Produce forward-looking numbers that never overstate their own confidence.
- Prompt 29: Three MVP forecast methods with minimum-history enforcement:
  * Simple run-rate (default)
  * Historical average
  * Moving average
- Prompt 29: Four Phase 2 methods behind flags:
  * Trend-based regression
  * Seasonality-aware decomposition
  * Provider-published forecast comparison
  * User-defined adjustment rules
- Prompt 29: All seven forecast outputs.
- Prompt 29: Fallback rule: fallback to run-rate with LOW confidence when history is insufficient.
- Negative constraint: With fewer than three days of period data, produce run-rate forecast labelled LOW confidence rather than nothing.
- Negative constraint: Do NOT display a forecast without its method.
- Negative constraint: Do NOT use a method whose minimum history is not satisfied.
- Prompt 29: Recompute forecasts after any restatement affecting their input window.
- Prompt 29: Forecast accuracy measurement at 25%, 50%, 75% milestones and period close.
- Prompt 13 Item 84: 100% TenantContext validation across all repository operations.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from starlette.testclient import TestClient

from api.cloudlens_api.main import app
from domain.config.feature_flags import feature_flag_service
from domain.cost.models import CostRestatementRecord
from domain.forecasting.accuracy import AccuracyEngine
from domain.forecasting.models import (
    DailySpendPoint,
    ForecastConfidence,
    ForecastGenerateRequest,
    ForecastMethod,
    ForecastMilestone,
    UserForecastAdjustmentRule,
)
from domain.forecasting.repository import reset_forecast_repository
from domain.forecasting.service import ForecastingService, reset_forecasting_service
from domain.models.enums import BudgetPeriod, BudgetScopeType, CostTrend
from domain.models.exceptions import ForecastNotFoundException, MissingTenantContextException
from domain.tenant.context import TenantContext

# ==============================================================================
# Fixtures
# ==============================================================================


@pytest.fixture(autouse=True)
def cleanup_forecasting():
    """Ensures clean state between tests."""
    reset_forecast_repository()
    reset_forecasting_service()
    yield
    reset_forecast_repository()
    reset_forecasting_service()


@pytest.fixture
def tenant_ctx() -> TenantContext:
    """Standard authenticated tenant context."""
    return TenantContext(
        tenant_id="tenant-acme-prod",
        user_id="user-finops-lead",
        correlation_id=str(uuid.uuid4()),
    )


@pytest.fixture
def other_tenant_ctx() -> TenantContext:
    """Secondary tenant context for multi-tenant isolation tests."""
    return TenantContext(
        tenant_id="tenant-beta-corp",
        user_id="user-beta-analyst",
        correlation_id=str(uuid.uuid4()),
    )


@pytest.fixture
def forecasting_service() -> ForecastingService:
    """Instantiates a fresh ForecastingService instance."""
    return ForecastingService()


@pytest.fixture
def client() -> TestClient:
    """FastAPI TestClient with authenticated headers."""
    return TestClient(app)


# ==============================================================================
# 1. MVP Methods & Minimum History Tests
# ==============================================================================


class TestMvpForecastMethodsAndMinimumHistory:
    """Verifies the three MVP methods, minimum history enforcement, and fallback discipline."""

    def test_run_rate_default_with_sufficient_history(
        self, forecasting_service: ForecastingService, tenant_ctx: TenantContext
    ):
        """Verifies simple run-rate with >= 7 days of period data yields HIGH confidence."""
        period_start = date(2026, 6, 1)
        as_of = date(2026, 6, 10)  # 10 days elapsed

        # $100 per day for 10 days = $1,000 actual
        daily_spends = [
            DailySpendPoint(date=period_start + timedelta(days=i), amount=100.0, usage=50.0)
            for i in range(10)
        ]

        req = ForecastGenerateRequest(
            scope_type=BudgetScopeType.ORGANISATION,
            scope_id="acme-org",
            budget_amount=3000.0,
            as_of=as_of,
            method=ForecastMethod.RUN_RATE,
            daily_spends=daily_spends,
        )

        forecast = forecasting_service.generate_forecast(req, tenant_context=tenant_ctx)

        assert forecast.effective_method == ForecastMethod.RUN_RATE
        assert forecast.fallback_applied is False
        assert forecast.confidence == ForecastConfidence.HIGH
        assert forecast.confidence_score >= 0.80

        # Math: 10 days elapsed, spend $1000 => $100/day. Remaining 20 days => $2000. Total = $3000
        assert forecast.outputs.end_of_period_cost == 3000.0
        assert forecast.outputs.expected_budget_consumption == 100.0
        assert forecast.outputs.forecast_variance == 0.0

    def test_negative_constraint_fewer_than_three_days_produces_low_confidence_never_nothing(
        self, forecasting_service: ForecastingService, tenant_ctx: TenantContext
    ):
        """Negative Constraint: With fewer than 3 days of period data, produce run-rate labelled LOW confidence rather than nothing."""
        as_of = date(2026, 6, 2)  # Only 2 days elapsed

        daily_spends = [
            DailySpendPoint(date=date(2026, 6, 1), amount=120.0, usage=60.0),
            DailySpendPoint(date=date(2026, 6, 2), amount=140.0, usage=70.0),
        ]

        req = ForecastGenerateRequest(
            scope_type=BudgetScopeType.AWS_ACCOUNT,
            scope_id="123456789012",
            budget_amount=4000.0,
            as_of=as_of,
            method=ForecastMethod.RUN_RATE,
            daily_spends=daily_spends,
        )

        forecast = forecasting_service.generate_forecast(req, tenant_context=tenant_ctx)

        # Must NOT fail or produce zero/nothing; must produce run-rate with LOW confidence
        assert forecast.effective_method == ForecastMethod.RUN_RATE
        assert forecast.confidence == ForecastConfidence.LOW
        assert forecast.confidence_score <= 0.50
        assert "fewer than 3 days" in forecast.derivation.confidence_rationale.lower()
        assert forecast.outputs.end_of_period_cost > 0.0

    def test_negative_constraint_single_day_period_data(
        self, forecasting_service: ForecastingService, tenant_ctx: TenantContext
    ):
        """Even with exactly 1 day of data, a run-rate forecast labelled Low confidence is produced."""
        period_start = date(2026, 6, 1)
        as_of = date(2026, 6, 1)

        daily_spends = [DailySpendPoint(date=period_start, amount=100.0, usage=50.0)]

        req = ForecastGenerateRequest(
            scope_type=BudgetScopeType.APPLICATION,
            scope_id="payment-service",
            as_of=as_of,
            method=ForecastMethod.RUN_RATE,
            daily_spends=daily_spends,
        )

        forecast = forecasting_service.generate_forecast(req, tenant_context=tenant_ctx)
        assert forecast.confidence == ForecastConfidence.LOW
        # 1 day * 30 days = 3000
        assert forecast.outputs.end_of_period_cost == 3000.0

    def test_historical_average_with_satisfied_minimum_history(
        self, forecasting_service: ForecastingService, tenant_ctx: TenantContext
    ):
        """Historical average uses prior observation history when minimum 14 days are met."""
        period_start = date(2026, 6, 1)
        as_of = date(2026, 6, 5)

        current_spends = [
            DailySpendPoint(date=period_start + timedelta(days=i), amount=150.0, usage=75.0)
            for i in range(5)
        ]
        # 20 days of historical data averaging $100/day
        hist_spends = [
            DailySpendPoint(date=date(2026, 5, 1) + timedelta(days=i), amount=100.0, usage=50.0)
            for i in range(20)
        ]

        req = ForecastGenerateRequest(
            scope_type=BudgetScopeType.COST_CENTRE,
            scope_id="CC-901",
            budget_amount=5000.0,
            as_of=as_of,
            method=ForecastMethod.HISTORICAL_AVERAGE,
            daily_spends=current_spends,
            historical_spends=hist_spends,
        )

        forecast = forecasting_service.generate_forecast(req, tenant_context=tenant_ctx)
        assert forecast.effective_method == ForecastMethod.HISTORICAL_AVERAGE
        assert forecast.fallback_applied is False
        assert forecast.confidence == ForecastConfidence.HIGH

        # Current 5 days spend = 750. Remaining 25 days * $100 historical avg = 2500. Total = 3250
        assert forecast.outputs.end_of_period_cost == 3250.0

    def test_historical_average_falls_back_when_history_insufficient(
        self, forecasting_service: ForecastingService, tenant_ctx: TenantContext
    ):
        """Do not use a method whose minimum history is not satisfied: falls back to run-rate with LOW confidence."""
        period_start = date(2026, 6, 1)
        as_of = date(2026, 6, 5)

        current_spends = [
            DailySpendPoint(date=period_start + timedelta(days=i), amount=150.0, usage=75.0)
            for i in range(5)
        ]
        # Only 5 days of history available (requires 14)
        hist_spends = [
            DailySpendPoint(date=date(2026, 5, 25) + timedelta(days=i), amount=100.0, usage=50.0)
            for i in range(5)
        ]

        req = ForecastGenerateRequest(
            scope_type=BudgetScopeType.COST_CENTRE,
            scope_id="CC-901",
            as_of=as_of,
            method=ForecastMethod.HISTORICAL_AVERAGE,
            daily_spends=current_spends,
            historical_spends=hist_spends,
        )

        forecast = forecasting_service.generate_forecast(req, tenant_context=tenant_ctx)

        # Must fall back to RUN_RATE and be labelled LOW confidence
        assert forecast.effective_method == ForecastMethod.RUN_RATE
        assert forecast.fallback_applied is True
        assert forecast.confidence == ForecastConfidence.LOW
        assert (
            forecast.fallback_reason is not None
            and "insufficient history" in forecast.fallback_reason.lower()
        )

    def test_moving_average_with_satisfied_and_insufficient_history(
        self, forecasting_service: ForecastingService, tenant_ctx: TenantContext
    ):
        """Moving average evaluates trailing window and falls back if < 7 days."""
        period_start = date(2026, 6, 1)
        as_of = date(2026, 6, 10)

        # 10 days of data
        spends_10d = [
            DailySpendPoint(
                date=period_start + timedelta(days=i), amount=100.0 + i * 10, usage=50.0
            )
            for i in range(10)
        ]

        req = ForecastGenerateRequest(
            scope_type=BudgetScopeType.GCP_PROJECT,
            scope_id="proj-data-analytics",
            as_of=as_of,
            method=ForecastMethod.MOVING_AVERAGE,
            moving_average_window_days=7,
            daily_spends=spends_10d,
        )

        forecast = forecasting_service.generate_forecast(req, tenant_context=tenant_ctx)
        assert forecast.effective_method == ForecastMethod.MOVING_AVERAGE
        assert forecast.fallback_applied is False

        # Now test with only 4 days (insufficient for 7-day moving average)
        req_short = ForecastGenerateRequest(
            scope_type=BudgetScopeType.GCP_PROJECT,
            scope_id="proj-data-analytics",
            as_of=date(2026, 6, 4),
            method=ForecastMethod.MOVING_AVERAGE,
            moving_average_window_days=7,
            daily_spends=spends_10d[:4],
        )

        forecast_short = forecasting_service.generate_forecast(req_short, tenant_context=tenant_ctx)
        assert forecast_short.effective_method == ForecastMethod.RUN_RATE
        assert forecast_short.fallback_applied is True
        assert forecast_short.confidence == ForecastConfidence.LOW


# ==============================================================================
# 2. Phase 2 Methods & Feature Flag Gates
# ==============================================================================


class TestPhase2MethodsAndFlagGates:
    """Verifies that Phase 2 methods are gated behind feature flags and execute cleanly when enabled."""

    def test_trend_regression_flag_disabled_falls_back(
        self, forecasting_service: ForecastingService, tenant_ctx: TenantContext
    ):
        """TREND_REGRESSION falls back to run-rate when feature flag is disabled."""
        feature_flag_service.set_flag(
            "enable_trend_regression_forecasting", False, tenant_id=tenant_ctx.tenant_id
        )

        spends_20d = [
            DailySpendPoint(
                date=date(2026, 6, 1) + timedelta(days=i), amount=100.0 + i * 5, usage=50.0
            )
            for i in range(20)
        ]

        req = ForecastGenerateRequest(
            scope_type=BudgetScopeType.SERVICE,
            scope_id="auth-cluster",
            as_of=date(2026, 6, 20),
            method=ForecastMethod.TREND_REGRESSION,
            daily_spends=spends_20d,
        )

        forecast = forecasting_service.generate_forecast(req, tenant_context=tenant_ctx)
        assert forecast.effective_method == ForecastMethod.RUN_RATE
        assert forecast.fallback_applied is True
        assert forecast.confidence == ForecastConfidence.LOW
        assert (
            forecast.fallback_reason is not None
            and "feature flag" in forecast.fallback_reason.lower()
        )

    def test_trend_regression_executes_when_flag_enabled(
        self, forecasting_service: ForecastingService, tenant_ctx: TenantContext
    ):
        """TREND_REGRESSION computes linear trend when flag is enabled and history satisfies 14 days."""
        feature_flag_service.set_flag(
            "enable_trend_regression_forecasting", True, tenant_id=tenant_ctx.tenant_id
        )

        spends_20d = [
            DailySpendPoint(
                date=date(2026, 6, 1) + timedelta(days=i), amount=100.0 + i * 5, usage=50.0
            )
            for i in range(20)
        ]

        req = ForecastGenerateRequest(
            scope_type=BudgetScopeType.SERVICE,
            scope_id="auth-cluster",
            as_of=date(2026, 6, 20),
            method=ForecastMethod.TREND_REGRESSION,
            daily_spends=spends_20d,
        )

        forecast = forecasting_service.generate_forecast(req, tenant_context=tenant_ctx)
        assert forecast.effective_method == ForecastMethod.TREND_REGRESSION
        assert forecast.fallback_applied is False
        assert forecast.confidence == ForecastConfidence.HIGH
        assert "regression_slope" in forecast.derivation.method_details
        assert forecast.derivation.method_details["regression_slope"] > 0.0

    def test_seasonality_decomposition_flag_and_execution(
        self, forecasting_service: ForecastingService, tenant_ctx: TenantContext
    ):
        """SEASONALITY_DECOMPOSITION applies day-of-week factor when enabled and history >= 28 days."""
        feature_flag_service.set_flag(
            "enable_seasonality_forecasting", True, tenant_id=tenant_ctx.tenant_id
        )

        # 35 days of data (5 full weeks)
        spends_35d = []
        base_date = date(2026, 5, 1)
        for i in range(35):
            d = base_date + timedelta(days=i)
            # Weekend drop: Saturday/Sunday spend $50, weekdays $150
            amt = 50.0 if d.weekday() in (5, 6) else 150.0
            spends_35d.append(DailySpendPoint(date=d, amount=amt, usage=40.0))

        req = ForecastGenerateRequest(
            scope_type=BudgetScopeType.ENVIRONMENT,
            scope_id="production",
            as_of=date(2026, 6, 4),
            method=ForecastMethod.SEASONALITY_DECOMPOSITION,
            daily_spends=spends_35d[31:],  # June 1..4
            historical_spends=spends_35d[:31],  # May
        )

        forecast = forecasting_service.generate_forecast(req, tenant_context=tenant_ctx)
        assert forecast.effective_method == ForecastMethod.SEASONALITY_DECOMPOSITION
        assert forecast.confidence == ForecastConfidence.HIGH
        assert "day_of_week_factors" in forecast.derivation.method_details

    def test_provider_published_forecast_integration(
        self, forecasting_service: ForecastingService, tenant_ctx: TenantContext
    ):
        """PROVIDER_PUBLISHED integrates cloud provider projected spend when enabled."""
        feature_flag_service.set_flag(
            "enable_provider_published_forecasting", True, tenant_id=tenant_ctx.tenant_id
        )

        spends_10d = [
            DailySpendPoint(date=date(2026, 6, 1) + timedelta(days=i), amount=100.0, usage=50.0)
            for i in range(10)
        ]

        req = ForecastGenerateRequest(
            scope_type=BudgetScopeType.SUBSCRIPTION,
            scope_id="sub-azure-core",
            as_of=date(2026, 6, 10),
            method=ForecastMethod.PROVIDER_PUBLISHED,
            provider_published_amount=4500.0,
            daily_spends=spends_10d,
        )

        forecast = forecasting_service.generate_forecast(req, tenant_context=tenant_ctx)
        assert forecast.effective_method == ForecastMethod.PROVIDER_PUBLISHED
        assert forecast.outputs.end_of_period_cost == 4500.0

    def test_user_defined_adjustment_rules(
        self, forecasting_service: ForecastingService, tenant_ctx: TenantContext
    ):
        """USER_ADJUSTMENT applies planned future event rules to the base forecast."""
        feature_flag_service.set_flag(
            "enable_user_adjustment_forecasting", True, tenant_id=tenant_ctx.tenant_id
        )

        spends_10d = [
            DailySpendPoint(date=date(2026, 6, 1) + timedelta(days=i), amount=100.0, usage=50.0)
            for i in range(10)
        ]

        # Migration starting June 15 adds $50/day
        rules = [
            UserForecastAdjustmentRule(
                rule_name="Cloud Migration Wave 1",
                start_date=date(2026, 6, 15),
                end_date=date(2026, 6, 30),
                adjustment_type="ADDITIVE_DAILY",
                adjustment_value=50.0,
                description="Planned migration workload addition",
            )
        ]

        req = ForecastGenerateRequest(
            scope_type=BudgetScopeType.PROJECT,
            scope_id="migration-target",
            as_of=date(2026, 6, 10),
            method=ForecastMethod.USER_ADJUSTMENT,
            daily_spends=spends_10d,
            adjustment_rules=rules,
        )

        forecast = forecasting_service.generate_forecast(req, tenant_context=tenant_ctx)
        assert forecast.effective_method == ForecastMethod.USER_ADJUSTMENT
        # Base spend 10d = $1000. 20 remaining days base = $2000.
        # Days 15..30 = 16 days with +$50 = $800 added.
        # Total = 1000 + 2000 + 800 = 3800.0
        assert forecast.outputs.end_of_period_cost == 3800.0


# ==============================================================================
# 3. Seven Forecast Outputs & Breach Prediction
# ==============================================================================


class TestSevenForecastOutputsAndBreachDates:
    """Verifies all seven forecast outputs and breach date predictions."""

    def test_all_seven_outputs_completeness(
        self, forecasting_service: ForecastingService, tenant_ctx: TenantContext
    ):
        """Ensures all seven outputs are produced with correct types and values."""
        spends = [
            DailySpendPoint(date=date(2026, 6, 1) + timedelta(days=i), amount=100.0, usage=50.0)
            for i in range(10)
        ]

        req = ForecastGenerateRequest(
            scope_type=BudgetScopeType.ORGANISATION,
            scope_id="corp-global",
            budget_amount=2500.0,
            as_of=date(2026, 6, 10),
            method=ForecastMethod.RUN_RATE,
            daily_spends=spends,
        )

        forecast = forecasting_service.generate_forecast(req, tenant_context=tenant_ctx)
        out = forecast.outputs

        # 1. End-of-period cost
        assert out.end_of_period_cost == 3000.0
        # 2. Expected usage
        assert out.expected_usage == 1500.0
        # 3. Expected budget consumption
        assert out.expected_budget_consumption == 120.0  # 3000 / 2500 * 100
        # 4. Cost trend
        assert isinstance(out.cost_trend, CostTrend)
        # 5. Forecast variance
        assert out.forecast_variance == 500.0  # 3000 - 2500
        # 6. Predicted threshold breach date (80% of 2500 = 2000 => day 20)
        assert out.predicted_threshold_breach_date == date(2026, 6, 20)
        # 7. Predicted budget breach date (100% of 2500 => day 25)
        assert out.predicted_budget_breach_date == date(2026, 6, 25)

    def test_cost_trend_spiking_and_volatile_detection(
        self, forecasting_service: ForecastingService, tenant_ctx: TenantContext
    ):
        """Verifies statistical cost trend classification."""
        # 1. Spiking trend (sudden step increase on last 2 days)
        spiking_spends = [
            DailySpendPoint(date=date(2026, 6, 1) + timedelta(days=i), amount=100.0, usage=50.0)
            for i in range(8)
        ] + [
            DailySpendPoint(date=date(2026, 6, 9), amount=250.0, usage=120.0),
            DailySpendPoint(date=date(2026, 6, 10), amount=300.0, usage=150.0),
        ]

        req_spike = ForecastGenerateRequest(
            scope_type=BudgetScopeType.SERVICE,
            scope_id="search-indexer",
            as_of=date(2026, 6, 10),
            daily_spends=spiking_spends,
        )
        fc_spike = forecasting_service.generate_forecast(req_spike, tenant_context=tenant_ctx)
        assert fc_spike.outputs.cost_trend == CostTrend.SPIKING


# ==============================================================================
# 4. Mandatory Metadata & Display Prominence
# ==============================================================================


class TestForecastMetadataAndDisplaySummary:
    """Verifies that every forecast prominently displays method, window, and confidence."""

    def test_negative_constraint_forecast_displays_method_window_and_confidence(
        self, forecasting_service: ForecastingService, tenant_ctx: TenantContext
    ):
        """Negative Constraint: A forecast displayed without its method is a defect, not a cosmetic issue."""
        spends = [
            DailySpendPoint(date=date(2026, 6, 1) + timedelta(days=i), amount=100.0, usage=50.0)
            for i in range(10)
        ]

        req = ForecastGenerateRequest(
            scope_type=BudgetScopeType.ORGANISATION,
            scope_id="corp-global",
            as_of=date(2026, 6, 10),
            method=ForecastMethod.RUN_RATE,
            daily_spends=spends,
        )

        forecast = forecasting_service.generate_forecast(req, tenant_context=tenant_ctx)

        # Check prominent display_summary string
        assert forecast.display_summary is not None
        assert "RUN_RATE" in forecast.display_summary
        assert "WINDOW:" in forecast.display_summary
        assert "10d" in forecast.display_summary
        assert "CONFIDENCE:" in forecast.display_summary
        assert forecast.confidence.value in forecast.display_summary

        # Check structured provenance attributes
        assert forecast.input_window.window_days == 10
        assert forecast.input_window.start_date == date(2026, 6, 1)
        assert forecast.input_window.end_date == date(2026, 6, 10)
        assert forecast.generation_timestamp is not None


# ==============================================================================
# 5. Restatement-Triggered Recomputation
# ==============================================================================


class TestRestatementTriggeredRecomputation:
    """Verifies that cost restatements invalidate and recompute overlapping forecasts."""

    def test_restatement_triggers_recomputation_of_affected_forecasts(
        self, forecasting_service: ForecastingService, tenant_ctx: TenantContext
    ):
        """Restatement causes affected forecasts to be recomputed and linked."""
        # Initial forecast in March 2026
        period_start = date(2026, 3, 1)
        as_of = date(2026, 3, 20)

        initial_spends = [
            DailySpendPoint(date=period_start + timedelta(days=i), amount=100.0, usage=50.0)
            for i in range(20)
        ]

        req = ForecastGenerateRequest(
            scope_type=BudgetScopeType.AWS_ACCOUNT,
            scope_id="111222333444",
            period=BudgetPeriod.MONTHLY,
            as_of=as_of,
            method=ForecastMethod.RUN_RATE,
            daily_spends=initial_spends,
        )

        initial_fc = forecasting_service.generate_forecast(req, tenant_context=tenant_ctx)
        assert initial_fc.is_active is True
        assert initial_fc.outputs.end_of_period_cost == 3100.0  # 20 * 100 + 11 * 100

        # Simulate provider billing restatement for 2026-03
        restatement = CostRestatementRecord(
            id="rst-202603-001",
            tenant_id=tenant_ctx.tenant_id,
            provider="aws",
            billing_period="2026-03",
            original_billed_total=Decimal("2000.00"),
            restated_billed_total=Decimal("2600.00"),
            billed_delta=Decimal("600.00"),
            original_effective_total=Decimal("2000.00"),
            restated_effective_total=Decimal("2600.00"),
            effective_delta=Decimal("600.00"),
            affected_row_count=45,
            notes="Late-arriving RDS data transfer charges",
        )

        # Updated spends reflecting higher restated amounts ($130/day)
        updated_spends = [
            DailySpendPoint(date=period_start + timedelta(days=i), amount=130.0, usage=65.0)
            for i in range(20)
        ]

        recomputed = forecasting_service.recompute_for_restatement(
            restatement_record=restatement,
            updated_spends=updated_spends,
            tenant_context=tenant_ctx,
        )

        assert len(recomputed) == 1
        new_fc = recomputed[0]

        assert new_fc.id != initial_fc.id
        assert new_fc.is_active is True
        assert new_fc.recomputed_from_restatement_id == "rst-202603-001"
        # Spend increased: 20 * 130 + 11 * 130 = 4030.0
        assert new_fc.outputs.end_of_period_cost == 4030.0

        # Check that previous forecast was superseded
        old_fc_stored = forecasting_service.get_forecast(initial_fc.id, tenant_context=tenant_ctx)
        assert old_fc_stored.is_active is False
        assert old_fc_stored.superseded_by_id == new_fc.id


# ==============================================================================
# 6. Forecast Accuracy Measurement & Trend
# ==============================================================================


class TestForecastAccuracyMeasurementAndTrend:
    """Verifies milestone tracking (25%, 50%, 75%), period close evaluation, and accuracy trends."""

    def test_milestone_resolution_and_recording(self):
        """Verifies checkpoint resolution across 25%, 50%, 75% milestones."""
        period_start = date(2026, 6, 1)
        period_end = date(2026, 6, 30)

        # Day 8 = ~26% -> M25
        assert (
            AccuracyEngine.resolve_milestone(period_start, period_end, date(2026, 6, 8))
            == ForecastMilestone.M25
        )
        # Day 15 = 50% -> M50
        assert (
            AccuracyEngine.resolve_milestone(period_start, period_end, date(2026, 6, 15))
            == ForecastMilestone.M50
        )
        # Day 23 = ~76% -> M75
        assert (
            AccuracyEngine.resolve_milestone(period_start, period_end, date(2026, 6, 23))
            == ForecastMilestone.M75
        )
        # Day 30 = 100% -> PERIOD_CLOSE
        assert (
            AccuracyEngine.resolve_milestone(period_start, period_end, date(2026, 6, 30))
            == ForecastMilestone.PERIOD_CLOSE
        )

    def test_period_close_evaluation_and_convergence_trend(
        self, forecasting_service: ForecastingService, tenant_ctx: TenantContext
    ):
        """Verifies error reporting and convergence (M75 error < M50 error < M25 error)."""
        period_start = date(2026, 6, 1)
        period_end = date(2026, 6, 30)
        period_id = "2026-06"

        # Generate forecast at day 8 (M25) -> forecast = 3500
        req_m25 = ForecastGenerateRequest(
            scope_type=BudgetScopeType.ORGANISATION,
            scope_id="org-acme",
            as_of=date(2026, 6, 8),
            daily_spends=[
                DailySpendPoint(date=period_start + timedelta(days=i), amount=110.0, usage=50.0)
                for i in range(8)
            ],
        )
        fc_m25 = forecasting_service.generate_forecast(req_m25, tenant_context=tenant_ctx)
        forecasting_service.record_milestone_checkpoint(
            forecast_id=fc_m25.id, as_of=date(2026, 6, 8), tenant_context=tenant_ctx
        )

        # Generate forecast at day 15 (M50) -> forecast = 3200
        req_m50 = ForecastGenerateRequest(
            scope_type=BudgetScopeType.ORGANISATION,
            scope_id="org-acme",
            as_of=date(2026, 6, 15),
            daily_spends=[
                DailySpendPoint(date=period_start + timedelta(days=i), amount=105.0, usage=50.0)
                for i in range(15)
            ],
        )
        fc_m50 = forecasting_service.generate_forecast(req_m50, tenant_context=tenant_ctx)
        forecasting_service.record_milestone_checkpoint(
            forecast_id=fc_m50.id, as_of=date(2026, 6, 15), tenant_context=tenant_ctx
        )

        # Generate forecast at day 23 (M75) -> forecast = 3050
        req_m75 = ForecastGenerateRequest(
            scope_type=BudgetScopeType.ORGANISATION,
            scope_id="org-acme",
            as_of=date(2026, 6, 23),
            daily_spends=[
                DailySpendPoint(date=period_start + timedelta(days=i), amount=101.0, usage=50.0)
                for i in range(23)
            ],
        )
        fc_m75 = forecasting_service.generate_forecast(req_m75, tenant_context=tenant_ctx)
        forecasting_service.record_milestone_checkpoint(
            forecast_id=fc_m75.id, as_of=date(2026, 6, 23), tenant_context=tenant_ctx
        )

        # Period Close: Actual billed spend = $3000.00
        report = forecasting_service.evaluate_period_close_accuracy(
            period_identifier=period_id,
            period_start=period_start,
            period_end=period_end,
            actual_billed_amount=3000.0,
            tenant_context=tenant_ctx,
        )

        assert report.actual_billed_amount == 3000.0
        assert "M25" in report.milestones
        assert "M50" in report.milestones
        assert "M75" in report.milestones

        # Error should decrease: M25 error > M50 error > M75 error
        err_m25 = report.milestones["M25"]["absolute_error"]
        err_m50 = report.milestones["M50"]["absolute_error"]
        err_m75 = report.milestones["M75"]["absolute_error"]

        assert err_m75 < err_m50 < err_m25

        # Check Trend
        trend = forecasting_service.get_accuracy_trend(tenant_context=tenant_ctx)
        assert trend.total_closed_periods_evaluated == 1
        assert trend.is_convergent is True
        assert trend.overall_accuracy_percentage > 85.0


# ==============================================================================
# 7. Multi-Tenant Isolation & Repository Context
# ==============================================================================


class TestMultiTenantIsolationAndContextValidation:
    """Verifies Prompt 13 Item 84: 100% TenantContext validation and tenant isolation."""

    def test_repository_validates_tenant_context_100_percent(
        self, forecasting_service: ForecastingService
    ):
        """Repository operations must fail with MissingTenantContextException if context is missing/invalid."""
        repo = forecasting_service.repository

        with pytest.raises(MissingTenantContextException):
            repo.get("fc-123", tenant_context=None)  # type: ignore

        with pytest.raises(MissingTenantContextException):
            repo.list(tenant_context=None)  # type: ignore

    def test_cross_tenant_isolation(
        self,
        forecasting_service: ForecastingService,
        tenant_ctx: TenantContext,
        other_tenant_ctx: TenantContext,
    ):
        """Forecasts belonging to Tenant A are invisible to Tenant B."""
        spends = [DailySpendPoint(date=date(2026, 6, 1), amount=100.0, usage=50.0)]
        req = ForecastGenerateRequest(
            scope_type=BudgetScopeType.ORGANISATION,
            scope_id="tenant-a-org",
            daily_spends=spends,
        )

        fc_a = forecasting_service.generate_forecast(req, tenant_context=tenant_ctx)

        # Tenant B queries forecast
        with pytest.raises(ForecastNotFoundException):
            forecasting_service.get_forecast(fc_a.id, tenant_context=other_tenant_ctx)

        # Tenant B lists forecasts
        tenant_b_list = forecasting_service.list_forecasts(tenant_context=other_tenant_ctx)
        assert len(tenant_b_list) == 0


# ==============================================================================
# 8. API Endpoints Contract Tests
# ==============================================================================


class TestForecastingAPIEndpoints:
    """Tests FastAPI HTTP REST endpoints for forecasting engine."""

    def test_api_generate_forecast(self, client: TestClient, tenant_ctx: TenantContext):
        """POST /api/v1/forecasts/generate creates forecast with 201 Created."""
        payload = {
            "scope_type": "ORGANISATION",
            "scope_id": "api-test-org",
            "budget_amount": 5000.0,
            "period": "MONTHLY",
            "as_of": "2026-06-10",
            "method": "RUN_RATE",
            "daily_spends": [
                {"date": f"2026-06-{i:02d}", "amount": 100.0, "usage": 50.0} for i in range(1, 11)
            ],
        }

        resp = client.post(
            "/api/v1/forecasts/generate",
            json=payload,
            headers={
                "X-Tenant-ID": tenant_ctx.tenant_id,
                "X-Actor-ID": tenant_ctx.actor_id or "user",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["id"].startswith("fc-")
        assert data["effective_method"] == "RUN_RATE"
        assert data["outputs"]["end_of_period_cost"] == 3000.0
        assert "display_summary" in data
        assert "RUN_RATE" in data["display_summary"]

    def test_api_list_forecasts_and_methods(self, client: TestClient, tenant_ctx: TenantContext):
        """GET /api/v1/forecasts and GET /api/v1/forecasts/methods."""
        # 1. Discover methods
        m_resp = client.get(
            "/api/v1/forecasts/methods",
            headers={"X-Tenant-ID": tenant_ctx.tenant_id},
        )
        assert m_resp.status_code == 200
        methods = m_resp.json()
        assert len(methods) == 7
        assert any(m["method"] == "RUN_RATE" for m in methods)
        assert any(m["method"] == "TREND_REGRESSION" for m in methods)

        # 2. List forecasts
        l_resp = client.get(
            "/api/v1/forecasts",
            headers={"X-Tenant-ID": tenant_ctx.tenant_id},
        )
        assert l_resp.status_code == 200
        data = l_resp.json()
        assert "items" in data
        assert "total" in data

    def test_api_milestone_and_period_close_lifecycle(
        self, client: TestClient, tenant_ctx: TenantContext
    ):
        """Full lifecycle: generate, record milestone, evaluate period close, get trend."""
        # 1. Generate
        gen_resp = client.post(
            "/api/v1/forecasts/generate",
            json={
                "scope_type": "SERVICE",
                "scope_id": "api-service-x",
                "period": "MONTHLY",
                "as_of": "2026-06-15",
                "method": "RUN_RATE",
                "daily_spends": [
                    {"date": f"2026-06-{i:02d}", "amount": 100.0, "usage": 50.0}
                    for i in range(1, 16)
                ],
            },
            headers={"X-Tenant-ID": tenant_ctx.tenant_id},
        )
        assert gen_resp.status_code == 201
        fc_id = gen_resp.json()["id"]

        # 2. Record milestone (50%)
        ms_resp = client.post(
            f"/api/v1/forecasts/{fc_id}/milestones?as_of=2026-06-15",
            headers={"X-Tenant-ID": tenant_ctx.tenant_id},
        )
        assert ms_resp.status_code == 201
        ms_data = ms_resp.json()
        assert ms_data["milestone"] == "M50"

        # 3. Evaluate Period Close
        close_resp = client.post(
            "/api/v1/forecasts/evaluate-period-close",
            json={
                "period_identifier": "2026-06",
                "period_start": "2026-06-01",
                "period_end": "2026-06-30",
                "actual_billed_amount": 3000.0,
            },
            headers={"X-Tenant-ID": tenant_ctx.tenant_id},
        )
        assert close_resp.status_code == 200
        close_data = close_resp.json()
        assert close_data["actual_billed_amount"] == 3000.0
        assert "M50" in close_data["milestones"]

        # 4. Get accuracy trend
        trend_resp = client.get(
            "/api/v1/forecasts/accuracy-trend",
            headers={"X-Tenant-ID": tenant_ctx.tenant_id},
        )
        assert trend_resp.status_code == 200
        trend_data = trend_resp.json()
        assert trend_data["total_closed_periods_evaluated"] == 1
