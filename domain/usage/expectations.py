"""Usage Expectation Engine with 4-Level Inheritance and Status Evaluation (Prompt 25).

Enforces:
- Prompt 25: Expectation definition at resource, service, scope and tenant level with inheritance.
- Prompt 25: Multi-band thresholds (Amber >= 80%, Red >= 100%).
- AC-051: Storage resource with 5 TB expectation shows Amber above 80% (4 TB) and Red above 100% (5 TB).
- AC-052: API service with 10M call expectation shows Amber above 8M (80%) and Red above 10M (100%).
- AC-053: Metric telemetry gap is displayed explicitly as 'No Data' and never as zero usage.
- Unit conversions through the declarative unit catalogue (USE-005 / Prompt 07).
"""

from __future__ import annotations

import logging
from decimal import Decimal

from domain.models.measures import QuantityMeasure
from domain.tenant.context import TenantContext
from domain.usage.models import (
    ExpectationEvaluationResult,
    ExpectationLevel,
    ExpectationStatus,
    MonitoringType,
    ResolvedExpectation,
    UsageExpectation,
)
from domain.usage.repository import UsageRepository
from normalisation.units.converter import convert_unit

logger = logging.getLogger(__name__)


class ExpectationEngine:
    """Resolves and evaluates usage expectations across the 4-level inheritance tree."""

    def __init__(self, repository: UsageRepository) -> None:
        self.repository = repository

    # ==========================================================================
    # 1. Four-Level Inheritance Resolution
    # ==========================================================================

    def resolve_expectation(
        self,
        resource_id: str,
        service_id: str,
        scope_id: str,
        monitoring_type: MonitoringType,
        *,
        tenant_context: TenantContext,
    ) -> ResolvedExpectation | None:
        """Traverses the 4-level hierarchy to resolve the active expectation.

        Precedence (highest to lowest):
        1. RESOURCE (explicit resource override)
        2. SERVICE  (service-wide expectation)
        3. SCOPE    (account/subscription/folder expectation)
        4. TENANT   (enterprise tenant baseline)
        """
        lineage: list[ExpectationLevel] = []

        # 1. Level: RESOURCE
        lineage.append(ExpectationLevel.RESOURCE)
        res_exps = self.repository.list_expectations(
            tenant_context=tenant_context,
            level=ExpectationLevel.RESOURCE,
            target_id=resource_id,
        )
        for exp in res_exps:
            if exp.monitoring_type == monitoring_type:
                return ResolvedExpectation(
                    resource_id=resource_id,
                    effective_expectation=exp,
                    source_level=ExpectationLevel.RESOURCE,
                    is_inherited=False,
                    is_overridden=True,
                    lineage=lineage,
                )

        # 2. Level: SERVICE
        lineage.append(ExpectationLevel.SERVICE)
        svc_exps = self.repository.list_expectations(
            tenant_context=tenant_context,
            level=ExpectationLevel.SERVICE,
            target_id=service_id,
        )
        for exp in svc_exps:
            if exp.monitoring_type == monitoring_type:
                return ResolvedExpectation(
                    resource_id=resource_id,
                    effective_expectation=exp,
                    source_level=ExpectationLevel.SERVICE,
                    is_inherited=True,
                    is_overridden=False,
                    lineage=lineage,
                )

        # 3. Level: SCOPE
        lineage.append(ExpectationLevel.SCOPE)
        scope_exps = self.repository.list_expectations(
            tenant_context=tenant_context,
            level=ExpectationLevel.SCOPE,
            target_id=scope_id,
        )
        for exp in scope_exps:
            if exp.monitoring_type == monitoring_type:
                return ResolvedExpectation(
                    resource_id=resource_id,
                    effective_expectation=exp,
                    source_level=ExpectationLevel.SCOPE,
                    is_inherited=True,
                    is_overridden=False,
                    lineage=lineage,
                )

        # 4. Level: TENANT
        lineage.append(ExpectationLevel.TENANT)
        tenant_exps = self.repository.list_expectations(
            tenant_context=tenant_context,
            level=ExpectationLevel.TENANT,
            target_id=tenant_context.tenant_id,
        )
        for exp in tenant_exps:
            if exp.monitoring_type == monitoring_type:
                return ResolvedExpectation(
                    resource_id=resource_id,
                    effective_expectation=exp,
                    source_level=ExpectationLevel.TENANT,
                    is_inherited=True,
                    is_overridden=False,
                    lineage=lineage,
                )

        return None

    # ==========================================================================
    # 2. Usage Evaluation Against Expectation
    # ==========================================================================

    def evaluate_usage(
        self,
        resource_id: str,
        metric_name: str,
        observed_quantity: QuantityMeasure,
        observed_unit: str,
        resolved_expectation: ResolvedExpectation | None,
    ) -> ExpectationEvaluationResult:
        """Evaluates observed metric usage against the active expectation.

        Enforces:
        - AC-051: Storage resource with 5 TB expectation shows Amber above 80% and Red above 100%.
        - AC-052: API service with 10M call expectation shows Amber above 8M and Red above 10M.
        - AC-053: Metric telemetry gap is displayed explicitly as 'No Data' and never as zero usage.
        """
        # 1. Telemetry Gap Handling (AC-053 / USE-004)
        if observed_quantity.is_null:
            return ExpectationEvaluationResult(
                resource_id=resource_id,
                metric_name=metric_name,
                actual_value_display="No Data",
                actual_quantity=observed_quantity,
                expected_value=None,
                expected_unit=None,
                utilisation_percentage=None,
                status=ExpectationStatus.NO_DATA,
                is_gap=True,
                explanation="Metric telemetry gap is displayed explicitly as 'No Data' and never as zero usage.",
                resolved_expectation=resolved_expectation,
            )

        actual_val = observed_quantity.value
        actual_display = f"{actual_val} {observed_unit}"

        # If no expectation configured, default to NORMAL
        if not resolved_expectation:
            return ExpectationEvaluationResult(
                resource_id=resource_id,
                metric_name=metric_name,
                actual_value_display=actual_display,
                actual_quantity=observed_quantity,
                expected_value=None,
                expected_unit=None,
                utilisation_percentage=None,
                status=ExpectationStatus.NORMAL,
                is_gap=False,
                explanation="No usage expectation defined; consumption observed without baseline limit.",
                resolved_expectation=None,
            )

        exp = resolved_expectation.effective_expectation

        # 2. Extract benchmark expectation value and unit
        expected_benchmark, benchmark_unit = self._extract_benchmark_target(exp)

        if expected_benchmark is None or expected_benchmark <= Decimal("0"):
            return ExpectationEvaluationResult(
                resource_id=resource_id,
                metric_name=metric_name,
                actual_value_display=actual_display,
                actual_quantity=observed_quantity,
                expected_value=expected_benchmark,
                expected_unit=benchmark_unit,
                utilisation_percentage=None,
                status=ExpectationStatus.NORMAL,
                is_gap=False,
                explanation="Expectation target is zero or undefined; treated as unconstrained.",
                resolved_expectation=resolved_expectation,
            )

        # 3. Unit normalisation
        normalized_actual = actual_val
        if benchmark_unit and observed_unit and benchmark_unit.upper() != observed_unit.upper():
            try:
                # Convert actual to expectation benchmark unit through declarative catalogue
                normalized_actual = convert_unit(
                    value=actual_val,
                    from_unit=observed_unit,
                    to_unit=benchmark_unit,
                )
            except Exception as err:
                logger.warning(
                    "Unit conversion failed between %s and %s: %s; using unconverted comparison.",
                    observed_unit,
                    benchmark_unit,
                    err,
                )
                normalized_actual = actual_val

        # 4. Compute utilisation percentage
        utilisation_pct = (normalized_actual / expected_benchmark) * Decimal("100.0")

        # 5. Multi-band threshold evaluation
        amber_pct = exp.warning_threshold_pct
        red_pct = exp.critical_threshold_pct

        if utilisation_pct >= red_pct:
            status = ExpectationStatus.RED
            status_desc = (
                f"Critical utilization breach ({utilisation_pct:.1f}% >= {red_pct:.1f}% threshold)"
            )
        elif utilisation_pct >= amber_pct:
            status = ExpectationStatus.AMBER
            status_desc = f"Warning utilization threshold reached ({utilisation_pct:.1f}% >= {amber_pct:.1f}% threshold)"
        else:
            status = ExpectationStatus.NORMAL
            status_desc = f"Normal utilization within expectation ({utilisation_pct:.1f}% < {amber_pct:.1f}% threshold)"

        origin_desc = (
            f"Overridden at {resolved_expectation.source_level.value}"
            if resolved_expectation.is_overridden
            else f"Inherited from {resolved_expectation.source_level.value}"
        )
        explanation = (
            f"{status_desc}. Expected: {expected_benchmark} {benchmark_unit or ''} ({origin_desc})."
        )

        return ExpectationEvaluationResult(
            resource_id=resource_id,
            metric_name=metric_name,
            actual_value_display=actual_display,
            actual_quantity=observed_quantity,
            expected_value=expected_benchmark,
            expected_unit=benchmark_unit,
            utilisation_percentage=utilisation_pct,
            status=status,
            is_gap=False,
            explanation=explanation,
            resolved_expectation=resolved_expectation,
        )

    @staticmethod
    def _extract_benchmark_target(exp: UsageExpectation) -> tuple[Decimal | None, str | None]:
        """Extracts the appropriate benchmark expectation target and unit based on monitoring type."""
        mtype = exp.monitoring_type

        if mtype in (MonitoringType.STORAGE_BASED, MonitoringType.VOLUME_BASED):
            if exp.expected_capacity is not None:
                return exp.expected_capacity, exp.expected_capacity_unit or "Bytes"

        if mtype in (MonitoringType.REQUEST_BASED, MonitoringType.API_CALL_BASED):
            if exp.expected_requests is not None:
                return exp.expected_requests, "Requests"

        if mtype in (MonitoringType.RUNTIME_BASED, MonitoringType.SCHEDULE_BASED):
            if exp.expected_hours_per_day is not None:
                return exp.expected_hours_per_day, "Hours"

        if mtype == MonitoringType.USER_BASED:
            if exp.expected_seats is not None:
                return Decimal(str(exp.expected_seats)), "Seats"

        if mtype == MonitoringType.RESERVED_COMMITTED_USAGE:
            if exp.committed_units is not None:
                return exp.committed_units, "Units"

        if exp.expected_quantity_per_period is not None:
            return exp.expected_quantity_per_period, None

        return None, None
