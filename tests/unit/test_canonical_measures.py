"""Unit Tests for Four-State Null Discipline on Measures.

Acceptance Criteria:
- A measure can be set to NOT_SUPPORTED and renders distinctly from zero in a unit test.
- Bare nulls are banned for measures (cannot use a nullable decimal to mean 'no data').
"""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from domain.models.enums import MeasureNullState
from domain.models.exceptions import MeasureAbsentException, MeasureNullForbiddenException
from domain.models.facts import CostFact
from domain.models.measures import FinancialMeasure, Measure


def test_measure_renders_not_supported_distinctly_from_zero():
    """Acceptance: A measure can be set to NOT_SUPPORTED and renders distinctly from zero."""
    unsupported_measure = FinancialMeasure.not_supported()
    zero_measure = FinancialMeasure.of(Decimal("0.00"))

    # Assert internal state
    assert unsupported_measure.is_null is True
    assert unsupported_measure.is_present is False
    assert unsupported_measure.null_state == MeasureNullState.NOT_SUPPORTED

    assert zero_measure.is_null is False
    assert zero_measure.is_present is True
    assert zero_measure.value == Decimal("0.00")

    # Assert rendered representation is distinctly different from zero
    rendered_unsupported = unsupported_measure.render()
    rendered_zero = zero_measure.render()

    assert rendered_unsupported == "NOT_SUPPORTED"
    assert rendered_zero == "0.00"
    assert rendered_unsupported != rendered_zero
    assert str(unsupported_measure) != str(zero_measure)


def test_bare_null_is_strictly_forbidden_for_measures():
    """Constraint: Do not use a nullable decimal to mean 'no data'; bare nulls are banned."""
    with pytest.raises(MeasureNullForbiddenException) as exc_info:
        Measure(value=None, null_state=None)
    assert "Bare null (None) is strictly forbidden" in str(exc_info.value)

    with pytest.raises(MeasureNullForbiddenException):
        Measure.of(None)  # type: ignore[arg-type]


def test_all_four_null_states_render_distinctly():
    """Verify all 4 null states (NO_COST, NO_DATA, NOT_APPLICABLE, NOT_SUPPORTED)."""
    m_no_cost = FinancialMeasure.no_cost()
    m_no_data = FinancialMeasure.no_data()
    m_not_app = FinancialMeasure.not_applicable()
    m_not_supp = FinancialMeasure.not_supported()

    assert m_no_cost.render() == "NO_COST"
    assert m_no_data.render() == "NO_DATA"
    assert m_not_app.render() == "NOT_APPLICABLE"
    assert m_not_supp.render() == "NOT_SUPPORTED"

    # None of them render as "0" or "0.00" or empty
    for m in (m_no_cost, m_no_data, m_not_app, m_not_supp):
        assert m.render() != "0"
        assert m.render() != "0.00"
        assert m.render() != ""

    # Accessing .value on absent measure raises MeasureAbsentException
    with pytest.raises(MeasureAbsentException) as exc_info:
        _ = m_no_data.value
    assert "NO_DATA" in str(exc_info.value)

    # .value_or fallback works as expected
    assert m_no_data.value_or(Decimal("99.99")) == Decimal("99.99")


def test_pydantic_fact_model_rejects_bare_null_and_accepts_measures():
    """Verify Pydantic Fact model enforces 4-state null discipline on input validation."""
    from datetime import UTC, datetime

    now = datetime.now(UTC)

    # Valid model with explicit measure states
    fact = CostFact(
        tenant_id="tenant-acme",
        scope_id="scope-sub-1",
        charge_period_start=now,
        charge_period_end=now,
        billed_cost=FinancialMeasure.of(Decimal("450.75")),
        effective_cost=FinancialMeasure.of(Decimal("412.30")),
        contracted_cost=FinancialMeasure.not_supported(),
        list_cost=FinancialMeasure.no_cost(),
    )
    assert fact.billed_cost.value == Decimal("450.75")
    assert fact.contracted_cost.null_state == MeasureNullState.NOT_SUPPORTED
    assert fact.list_cost.null_state == MeasureNullState.NO_COST

    # Banning bare null: attempting to pass bare None to billed_cost must fail
    with pytest.raises((MeasureNullForbiddenException, ValidationError)):
        CostFact(
            tenant_id="tenant-acme",
            scope_id="scope-sub-1",
            charge_period_start=now,
            charge_period_end=now,
            billed_cost=None,  # type: ignore[arg-type]
            effective_cost=FinancialMeasure.of(Decimal("10.00")),
        )
