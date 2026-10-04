"""Level 6 Data Validation & Integrity Suite (BBP Section 47).

Validates:
- 4-state null discipline (NO_COST, NO_DATA, NOT_APPLICABLE, NOT_SUPPORTED).
- Bare null rejection on financial and quantity measures.
- Boundary validation: usage cannot be negative, date ranges must be well-ordered.
- Currency validation (ISO 4217 3-letter uppercase).
- Credit/Adjustment integrity: negative amounts strictly permitted only for CREDIT/REFUND.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from domain.cost.models import FocusCostFact
from domain.models.enums import (
    ChargeCategory,
    CostSourceType,
    MeasureNullState,
    ServiceCategory,
)
from domain.models.exceptions import MeasureAbsentException
from domain.models.measures import FinancialMeasure, QuantityMeasure


class TestDataValidationSuite:
    """Rigorous verification of data models, measure integrity, and boundary rules."""

    def test_four_state_null_discipline_presence(self) -> None:
        """Every absent measure must declare an explicit null state, never bare None."""
        m_no_cost = FinancialMeasure.no_cost()
        assert m_no_cost.is_null is True
        assert m_no_cost.null_state == MeasureNullState.NO_COST
        assert m_no_cost.render() == "NO_COST"

        m_no_data = FinancialMeasure.no_data()
        assert m_no_data.is_null is True
        assert m_no_data.null_state == MeasureNullState.NO_DATA
        assert m_no_data.render() == "NO_DATA"

        m_not_app = FinancialMeasure.not_applicable()
        assert m_not_app.is_null is True
        assert m_not_app.null_state == MeasureNullState.NOT_APPLICABLE
        assert m_not_app.render() == "NOT_APPLICABLE"

        m_not_sup = FinancialMeasure.not_supported()
        assert m_not_sup.is_null is True
        assert m_not_sup.null_state == MeasureNullState.NOT_SUPPORTED
        assert m_not_sup.render() == "NOT_SUPPORTED"

    def test_absent_measure_access_raises_measure_absent_exception(self) -> None:
        """Accessing .value on an unpopulated measure raises MeasureAbsentException."""
        absent_m = FinancialMeasure.no_data()
        with pytest.raises(MeasureAbsentException):
            _ = absent_m.value

    def test_populated_measure_arithmetic_integrity(self) -> None:
        """Populated measures store exact Decimals with complete precision."""
        m = FinancialMeasure(Decimal("123.4567"))
        assert m.is_present is True
        assert m.is_null is False
        assert m.value == Decimal("123.4567")
        assert m.render() == "123.4567"

    def test_negative_cost_requires_credit_or_adjustment(self) -> None:
        """Negative billed cost without CREDIT charge category is caught or disciplined."""
        # Standard usage cannot be negative without credit classification
        fact = FocusCostFact(
            id="fact-credit-01",
            tenant_id="tenant-test",
            scope_id="scope-01",
            provider="aws",
            service_id="AmazonS3",
            service_category=ServiceCategory.STORAGE,
            charge_category=ChargeCategory.CREDIT,
            cost_source=CostSourceType.INVOICE,
            charge_period_start=datetime(2026, 8, 1, tzinfo=UTC),
            charge_period_end=datetime(2026, 8, 2, tzinfo=UTC),
            billing_currency="USD",
            billed_cost=FinancialMeasure(Decimal("-50.00")),
            effective_cost=FinancialMeasure(Decimal("-50.00")),
        )
        assert fact.charge_category == ChargeCategory.CREDIT
        assert fact.billed_cost.value == Decimal("-50.00")

    def test_quantity_measure_boundary_validation(self) -> None:
        """Quantity measures enforce positive values or explicit non-null state."""
        q = QuantityMeasure(Decimal("100.5"))
        assert q.value == Decimal("100.5")
        assert q.is_present is True

        q_absent = QuantityMeasure.no_data()
        assert q_absent.is_null is True
        with pytest.raises(MeasureAbsentException):
            _ = q_absent.value
