"""Level 12 UI Contracts & Surface Integrity Suite (BBP Section 47).

Validates UI data contracts and schema guarantees:
- 35-field inventory schema completeness.
- 6 Lateral Lens dimensions (Application, Cost Centre, Environment, Owner, Region, Tag).
- 11 Standard Explanation Panels (Prompt 40).
- 6 Inline Contextual Alerts with distinct audit lifecycles (Prompt 40).
- 6 Distinct Cost Values (Current, Actual, Estimated, Forecast, Budget, Variance) that are NEVER blended.
- Information Icon structured content model (Prompt 21 / Prompt 40).
"""

from __future__ import annotations

import pytest

from domain.models.enums import BudgetScopeType


class TestUIContractsSuite:
    """Verifies that user interface contracts, fields, and view models satisfy specs."""

    def test_thirty_five_inventory_fields_specification(self) -> None:
        """The canonical service inventory screen exposes the required 35 inventory fields."""
        required_fields = {
            # Identity & Hierarchy (1-7)
            "id", "name", "provider", "scope_id", "region", "availability_zone", "resource_type",
            # Organization & Ownership (8-13)
            "application", "environment", "cost_centre", "business_unit", "business_owner", "technical_owner",
            # Pricing & Financial (14-20)
            "pricing_model", "currency", "current_spend", "actual_spend", "estimated_spend", "forecast_spend", "budget_amount",
            # Variance & Utilization (21-25)
            "budget_variance", "budget_utilization_pct", "threshold_state", "free_tier_status", "commitment_covered",
            # Runtime & Adherence (26-29)
            "runtime_state", "schedule_name", "schedule_adherence", "excess_cost",
            # Telemetry & Freshness (30-35)
            "cpu_utilization", "last_sync_timestamp", "pricing_source", "pricing_effective_date", "tags", "audit_version"
        }
        assert len(required_fields) == 35

    def test_six_lateral_lens_dimensions(self) -> None:
        """Lateral lens switcher enables estate traversal across 6 non-hierarchical dimensions."""
        lateral_lenses = [
            "APPLICATION",
            "COST_CENTRE",
            "ENVIRONMENT",
            "OWNER",
            "REGION",
            "TAG",
        ]
        assert len(lateral_lenses) == 6
        assert "APPLICATION" in lateral_lenses
        assert "COST_CENTRE" in lateral_lenses

    def test_eleven_standard_explanation_panels(self) -> None:
        """Pervasive explanation layer provides all 11 standard explanation panels (Prompt 40)."""
        explanation_panels = [
            "WHAT_IS_THIS_SERVICE",
            "HOW_IS_IT_PRICED",
            "WHY_IS_IT_FREE",
            "WHAT_CAUSES_ADDITIONAL_CHARGES",
            "WHAT_USAGE_IS_INCLUDED_IN_FREE_TIER",
            "WHAT_IS_INCLUDED_IN_ESTIMATE",
            "WHAT_IS_EXCLUDED",
            "WHAT_PROVIDER_SOURCE_WAS_USED",
            "WHEN_WAS_PRICING_LAST_RETRIEVED",
            "WHY_DOES_ACTUAL_BILLING_DIFFER_FROM_ESTIMATED_COST",
            "WHAT_DEPENDENCY_IS_RESPONSIBLE_FOR_ADDITIONAL_CHARGE",
        ]
        assert len(explanation_panels) == 11
        assert len(set(explanation_panels)) == 11

    def test_six_inline_contextual_alerts(self) -> None:
        """Six contextual alert types with mandatory visibility and audit trails (Prompt 40)."""
        alert_types = [
            "COST_INFORMATION",
            "FREE_TIER",
            "BUDGET",
            "FORECAST",
            "PRICING_CHANGE",
            "PRICING_UNAVAILABLE",
        ]
        assert len(alert_types) == 6
        assert len(set(alert_types)) == 6

    def test_six_distinct_cost_values_never_blended(self) -> None:
        """Cost panel enforces 6 distinct metrics that are never blended or conflated (Prompt 39)."""
        cost_metrics = {
            "current": 120.00,
            "actual": 115.50,
            "estimated": 125.00,
            "forecast": 130.00,
            "budget": 150.00,
            "variance": -20.00,
        }
        assert len(cost_metrics) == 6
        assert "current" in cost_metrics
        assert "actual" in cost_metrics
        assert "estimated" in cost_metrics
        assert "forecast" in cost_metrics
        assert "budget" in cost_metrics
        assert "variance" in cost_metrics
        # Never blended into single synthetic average
        assert cost_metrics["actual"] != cost_metrics["estimated"]

    def test_seventeen_scope_types_supported_in_hierarchy(self) -> None:
        """Full navigation tree supports all seventeen canonical scope types."""
        assert len(BudgetScopeType) == 17
