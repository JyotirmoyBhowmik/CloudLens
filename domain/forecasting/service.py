"""Forecasting Domain Service Facade (Prompt 29).

Enforces:
- Prompt 29: Produce forward-looking numbers that never overstate their own confidence.
- Prompt 29: MVP methods: Simple run-rate (default), historical average, moving average.
- Prompt 29: Phase 2 methods behind flags: trend-based regression, seasonality-aware decomposition,
  provider-published forecast comparison, and user-defined adjustment rules.
- Prompt 29: All seven forecast outputs.
- Prompt 29: Fallback rule: fallback to run-rate with LOW confidence when history is insufficient.
- Prompt 29: Recompute forecasts after any restatement affecting their input window.
- Prompt 29: Forecast accuracy measurement at 25%, 50%, 75% milestones and period close.
- Prompt 13 Item 84: 100% TenantContext validation across all operations.
"""

from __future__ import annotations

import logging
import uuid
from calendar import monthrange
from datetime import UTC, date, datetime
from typing import Any

from domain.audit.service import AuditEventCreate, get_audit_service
from domain.budgets.calendar import BudgetPeriodCalendar
from domain.budgets.repository import BudgetRepository, get_budget_repository
from domain.config.feature_flags import feature_flag_service
from domain.cost.models import CostRestatementRecord
from domain.forecasting.accuracy import AccuracyEngine
from domain.forecasting.engine import ForecastingEngine
from domain.forecasting.models import (
    DailySpendPoint,
    ForecastAccuracyTrend,
    ForecastEntity,
    ForecastGenerateRequest,
    ForecastMethod,
    ForecastMethodInfo,
    ForecastMilestoneSnapshot,
    PeriodAccuracyReport,
)
from domain.forecasting.repository import ForecastRepository, get_forecast_repository
from domain.models.base import ProvenanceRecord
from domain.models.enums import (
    AuditEventType,
    BudgetPeriod,
    OriginType,
)
from domain.models.exceptions import (
    ForecastNotFoundException,
)
from domain.tenant.context import TenantContext

logger = logging.getLogger(__name__)


class ForecastingService:
    """Enterprise domain service orchestrating predictive spend projections and accuracy governance."""

    def __init__(
        self,
        repository: ForecastRepository | None = None,
        engine: ForecastingEngine | None = None,
        accuracy_engine: AccuracyEngine | None = None,
        calendar: BudgetPeriodCalendar | None = None,
        budget_repository: BudgetRepository | None = None,
    ) -> None:
        self.repository = repository or get_forecast_repository()
        self.engine = engine or ForecastingEngine()
        self.accuracy_engine = accuracy_engine or AccuracyEngine()
        self.calendar = calendar or BudgetPeriodCalendar()
        self.budget_repository = budget_repository or get_budget_repository()

    # ==========================================================================
    # 1. Forecast Generation & Fallback Discipline
    # ==========================================================================

    def generate_forecast(
        self,
        request: ForecastGenerateRequest,
        *,
        tenant_context: TenantContext,
    ) -> ForecastEntity:
        """Generates, validates, and persists a forward-looking spend projection.

        Enforces minimum-history rules, flag gates, fallback to run-rate with LOW confidence,
        and prominent display summary metadata.
        """
        eval_date = request.as_of or date.today()

        # Resolve period bounds
        period_start, period_end = self._resolve_period_bounds(
            period=request.period,
            as_of=eval_date,
        )

        # Inherit budget ceiling if linked
        target_budget_amount = request.budget_amount
        target_scope_type = request.scope_type
        target_scope_id = request.scope_id

        if request.budget_id:
            budget = self.budget_repository.get(request.budget_id, tenant_context=tenant_context)
            if budget:
                if target_budget_amount is None:
                    target_budget_amount = budget.amount
                target_scope_type = budget.scope_type
                target_scope_id = budget.scope_id
                period_start = budget.effective_date
                if budget.expiry_date:
                    period_end = budget.expiry_date

        # Execute computational engine
        engine_instance = ForecastingEngine(tenant_id=tenant_context.tenant_id)
        (
            effective_method,
            fallback_applied,
            fallback_reason,
            confidence,
            confidence_score,
            input_window,
            outputs,
            derivation,
        ) = engine_instance.compute_forecast(
            period_start=period_start,
            period_end=period_end,
            as_of=eval_date,
            requested_method=request.method,
            daily_spends=request.daily_spends,
            historical_spends=request.historical_spends,
            budget_amount=target_budget_amount,
            warning_threshold_pct=request.warning_threshold_pct,
            moving_average_window_days=request.moving_average_window_days,
            provider_published_amount=request.provider_published_amount,
            adjustment_rules=request.adjustment_rules,
        )

        # Deactivate previous active forecast for this exact scope and period
        prev_forecast = self.repository.find_active_by_scope(
            scope_id=target_scope_id,
            period_start=period_start,
            period_end=period_end,
            tenant_context=tenant_context,
        )

        new_forecast_id = f"fc-{uuid.uuid4().hex[:12]}"

        if prev_forecast:
            updated_prev = ForecastEntity(
                id=prev_forecast.id,
                tenant_id=prev_forecast.tenant_id,
                scope_type=prev_forecast.scope_type,
                scope_id=prev_forecast.scope_id,
                budget_id=prev_forecast.budget_id,
                currency=prev_forecast.currency,
                period=prev_forecast.period,
                period_start=prev_forecast.period_start,
                period_end=prev_forecast.period_end,
                requested_method=prev_forecast.requested_method,
                effective_method=prev_forecast.effective_method,
                fallback_applied=prev_forecast.fallback_applied,
                fallback_reason=prev_forecast.fallback_reason,
                confidence=prev_forecast.confidence,
                confidence_score=prev_forecast.confidence_score,
                input_window=prev_forecast.input_window,
                generation_timestamp=prev_forecast.generation_timestamp,
                outputs=prev_forecast.outputs,
                derivation=prev_forecast.derivation,
                is_active=False,
                superseded_by_id=new_forecast_id,
                superseded_at=datetime.now(UTC),
                recomputed_from_restatement_id=prev_forecast.recomputed_from_restatement_id,
                display_summary=prev_forecast.display_summary,
                source_provenance=prev_forecast.source_provenance,
            )
            self.repository.save(updated_prev, tenant_context=tenant_context)

        # Create new forecast entity
        entity = ForecastEntity.create(
            id=new_forecast_id,
            tenant_id=tenant_context.tenant_id,
            scope_type=target_scope_type,
            scope_id=target_scope_id,
            budget_id=request.budget_id,
            currency=request.currency,
            period=request.period,
            period_start=period_start,
            period_end=period_end,
            requested_method=request.method,
            effective_method=effective_method,
            fallback_applied=fallback_applied,
            fallback_reason=fallback_reason,
            confidence=confidence,
            confidence_score=confidence_score,
            input_window=input_window,
            outputs=outputs,
            derivation=derivation,
        )

        entity.source_provenance = ProvenanceRecord(
            source_system="CloudLens-Forecasting-Engine",
            origin_type=OriginType.DERIVED,
            correlation_id=tenant_context.correlation_id or f"corr-{uuid.uuid4().hex[:12]}",
        )

        saved = self.repository.save(entity, tenant_context=tenant_context)

        # Audit events
        if fallback_applied:
            self._record_audit_event(
                event_type=AuditEventType.FORECAST_FALLBACK_TRIGGERED,
                actor_id=tenant_context.actor_id or "system",
                action="FORECAST_FALLBACK_TRIGGERED",
                resource_id=saved.id,
                details={
                    "requested_method": request.method.value,
                    "effective_method": effective_method.value,
                    "reason": fallback_reason,
                    "confidence": confidence.value,
                },
                tenant_context=tenant_context,
            )

        self._record_audit_event(
            event_type=AuditEventType.FORECAST_GENERATED,
            actor_id=tenant_context.actor_id or "system",
            action="FORECAST_GENERATED",
            resource_id=saved.id,
            details={
                "method": effective_method.value,
                "confidence": confidence.value,
                "end_of_period_cost": outputs.end_of_period_cost,
                "expected_usage": outputs.expected_usage,
                "scope_id": saved.scope_id,
                "period_start": period_start.isoformat(),
                "period_end": period_end.isoformat(),
            },
            tenant_context=tenant_context,
        )

        return saved

    def get_forecast(
        self,
        forecast_id: str,
        *,
        tenant_context: TenantContext,
    ) -> ForecastEntity:
        """Retrieves a single forecast record by ID."""
        forecast = self.repository.get(forecast_id, tenant_context=tenant_context)
        if not forecast:
            raise ForecastNotFoundException(forecast_id)
        return forecast

    def list_forecasts(
        self,
        *,
        tenant_context: TenantContext,
        filter_params: dict[str, Any] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ForecastEntity]:
        """Lists forecasts within tenant boundary."""
        return self.repository.list(
            tenant_context=tenant_context,
            filter_params=filter_params,
            limit=limit,
            offset=offset,
        )

    # ==========================================================================
    # 2. Restatement-Triggered Recomputation
    # ==========================================================================

    def recompute_for_restatement(
        self,
        restatement_record: CostRestatementRecord,
        updated_spends: list[DailySpendPoint],
        *,
        tenant_context: TenantContext,
    ) -> list[ForecastEntity]:
        """Recomputes all active forecasts affected by a detected cost restatement (Prompt 29).

        Identifies forecasts whose input window or target period spans the restated cycle,
        recomputes them using restated actuals, and links them to the restatement record ID.
        """
        # Parse billing period into date bounds (e.g. '2026-03' -> 2026-03-01 to 2026-03-31)
        try:
            parts = restatement_record.billing_period.split("-")
            year, month = int(parts[0]), int(parts[1])
            _, last_day = monthrange(year, month)
            restated_start = date(year, month, 1)
            restated_end = date(year, month, last_day)
        except Exception:
            restated_start = date.today().replace(day=1)
            _, last_day = monthrange(restated_start.year, restated_start.month)
            restated_end = date(restated_start.year, restated_start.month, last_day)

        # Find overlapping active forecasts
        affected = self.repository.find_by_period_overlap(
            start_date=restated_start,
            end_date=restated_end,
            tenant_context=tenant_context,
        )

        recomputed_results: list[ForecastEntity] = []

        for old_f in affected:
            # Recompute forecast with updated spends
            req = ForecastGenerateRequest(
                scope_type=old_f.scope_type,
                scope_id=old_f.scope_id,
                budget_id=old_f.budget_id,
                period=old_f.period,
                as_of=old_f.input_window.end_date,
                method=old_f.requested_method,
                daily_spends=updated_spends,
                historical_spends=[],
                currency=old_f.currency,
            )

            # Generate new forecast
            new_f = self.generate_forecast(req, tenant_context=tenant_context)

            # Mark restatement linkage on new forecast
            linked_f = ForecastEntity(
                id=new_f.id,
                tenant_id=new_f.tenant_id,
                scope_type=new_f.scope_type,
                scope_id=new_f.scope_id,
                budget_id=new_f.budget_id,
                currency=new_f.currency,
                period=new_f.period,
                period_start=new_f.period_start,
                period_end=new_f.period_end,
                requested_method=new_f.requested_method,
                effective_method=new_f.effective_method,
                fallback_applied=new_f.fallback_applied,
                fallback_reason=new_f.fallback_reason,
                confidence=new_f.confidence,
                confidence_score=new_f.confidence_score,
                input_window=new_f.input_window,
                generation_timestamp=new_f.generation_timestamp,
                outputs=new_f.outputs,
                derivation=new_f.derivation,
                is_active=True,
                recomputed_from_restatement_id=restatement_record.id,
                display_summary=new_f.display_summary,
                source_provenance=new_f.source_provenance,
            )
            saved_linked = self.repository.save(linked_f, tenant_context=tenant_context)
            recomputed_results.append(saved_linked)

            # Audit event
            self._record_audit_event(
                event_type=AuditEventType.FORECAST_RECOMPUTED_AFTER_RESTATEMENT,
                actor_id=tenant_context.actor_id or "system",
                action="FORECAST_RECOMPUTED_AFTER_RESTATEMENT",
                resource_id=saved_linked.id,
                details={
                    "restatement_id": restatement_record.id,
                    "previous_forecast_id": old_f.id,
                    "new_forecast_id": saved_linked.id,
                    "scope_id": saved_linked.scope_id,
                    "restated_billed_total": str(restatement_record.restated_billed_total),
                },
                tenant_context=tenant_context,
            )

        return recomputed_results

    # ==========================================================================
    # 3. Forecast Accuracy Measurement & Milestones
    # ==========================================================================

    def record_milestone_checkpoint(
        self,
        forecast_id: str,
        as_of: date | None = None,
        *,
        tenant_context: TenantContext,
    ) -> ForecastMilestoneSnapshot:
        """Records a forecast snapshot at 25%, 50%, 75% or period close (Prompt 29)."""
        forecast = self.get_forecast(forecast_id, tenant_context=tenant_context)
        check_date = as_of or date.today()

        milestone = self.accuracy_engine.resolve_milestone(
            period_start=forecast.period_start,
            period_end=forecast.period_end,
            as_of=check_date,
        )

        period_id = f"{forecast.period_start.year:04d}-{forecast.period_start.month:02d}"

        snapshot = ForecastMilestoneSnapshot(
            tenant_id=tenant_context.tenant_id,
            scope_id=forecast.scope_id,
            budget_id=forecast.budget_id,
            period_identifier=period_id,
            period_start=forecast.period_start,
            period_end=forecast.period_end,
            milestone=milestone,
            checkpoint_date=check_date,
            forecast_id=forecast.id,
            forecast_amount=forecast.outputs.end_of_period_cost,
            method=forecast.effective_method,
            confidence=forecast.confidence,
        )

        saved = self.repository.save_milestone(snapshot, tenant_context=tenant_context)

        self._record_audit_event(
            event_type=AuditEventType.FORECAST_ACCURACY_RECORDED,
            actor_id=tenant_context.actor_id or "system",
            action="FORECAST_MILESTONE_RECORDED",
            resource_id=saved.id,
            details={
                "forecast_id": forecast.id,
                "milestone": milestone.value,
                "forecast_amount": saved.forecast_amount,
                "period_identifier": period_id,
            },
            tenant_context=tenant_context,
        )

        return saved

    def evaluate_period_close_accuracy(
        self,
        *,
        period_identifier: str,
        period_start: date,
        period_end: date,
        actual_billed_amount: float,
        scope_id: str | None = None,
        tenant_context: TenantContext,
    ) -> PeriodAccuracyReport:
        """Evaluates actual billed cost against recorded milestone forecasts at period close (Prompt 29)."""
        milestones = self.repository.list_milestones(
            period_identifier=period_identifier,
            scope_id=scope_id,
            tenant_context=tenant_context,
        )

        report = self.accuracy_engine.evaluate_period_close(
            period_identifier=period_identifier,
            period_start=period_start,
            period_end=period_end,
            actual_billed_amount=actual_billed_amount,
            milestone_snapshots=milestones,
        )

        # Update saved milestones with evaluation metrics
        for ms in milestones:
            updated_ms = self.accuracy_engine.evaluate_milestone_accuracy(ms, actual_billed_amount)
            self.repository.save_milestone(updated_ms, tenant_context=tenant_context)

        return report

    def get_accuracy_trend(
        self,
        *,
        tenant_context: TenantContext,
    ) -> ForecastAccuracyTrend:
        """Produces historical accuracy trend across closed periods and milestones (Prompt 29)."""
        all_milestones = self.repository.list_milestones(tenant_context=tenant_context)

        # Group by period_identifier
        period_groups: dict[str, list[ForecastMilestoneSnapshot]] = {}
        for m in all_milestones:
            period_groups.setdefault(m.period_identifier, []).append(m)

        period_reports: list[PeriodAccuracyReport] = []
        for period_id, m_list in sorted(period_groups.items()):
            # Find evaluate closed periods where actual_billed_amount is recorded
            evaluated = [m for m in m_list if m.actual_billed_amount is not None]
            if evaluated:
                act = evaluated[0].actual_billed_amount or 0.0
                rep = self.accuracy_engine.evaluate_period_close(
                    period_identifier=period_id,
                    period_start=m_list[0].period_start,
                    period_end=m_list[0].period_end,
                    actual_billed_amount=act,
                    milestone_snapshots=evaluated,
                )
                period_reports.append(rep)

        return self.accuracy_engine.build_accuracy_trend(
            tenant_id=tenant_context.tenant_id,
            period_reports=period_reports,
        )

    # ==========================================================================
    # 4. Method Catalogue Discovery
    # ==========================================================================

    def list_supported_methods(
        self,
        *,
        tenant_context: TenantContext,
    ) -> list[ForecastMethodInfo]:
        """Returns catalogue of all 7 forecast methods with MVP vs Phase 2 gating metadata."""
        results: list[ForecastMethodInfo] = []

        descriptions = {
            ForecastMethod.RUN_RATE: (
                "Simple Run-Rate (Default)",
                "Extrapolates remaining period spend using daily velocity of the active cycle.",
            ),
            ForecastMethod.HISTORICAL_AVERAGE: (
                "Historical Average",
                "Applies mean daily spend across prior closed observation cycles.",
            ),
            ForecastMethod.MOVING_AVERAGE: (
                "Moving Average",
                "Projects future consumption using a configurable trailing window.",
            ),
            ForecastMethod.TREND_REGRESSION: (
                "Trend-Based Regression",
                "Fits linear regression trajectory over historical spend points (Phase 2).",
            ),
            ForecastMethod.SEASONALITY_DECOMPOSITION: (
                "Seasonality-Aware Decomposition",
                "Decomposes cyclical day-of-week patterns to model weekly rhythms (Phase 2).",
            ),
            ForecastMethod.PROVIDER_PUBLISHED: (
                "Provider-Published Forecast",
                "Ingests cloud provider native forecast alongside CloudLens model (Phase 2).",
            ),
            ForecastMethod.USER_ADJUSTMENT: (
                "User-Defined Adjustment Rules",
                "Applies additive, multiplicative, or one-off adjustments for planned events (Phase 2).",
            ),
        }

        for method in ForecastMethod:
            name, desc = descriptions.get(method, (method.value, "Forecasting algorithm"))
            flag_key = method.feature_flag_key()
            is_enabled = True
            if flag_key:
                is_enabled = feature_flag_service.evaluate(flag_key, tenant_context.tenant_id)

            results.append(
                ForecastMethodInfo(
                    method=method,
                    display_name=name,
                    description=desc,
                    minimum_history_days=method.minimum_history_days(),
                    is_mvp=method.is_mvp(),
                    is_enabled=is_enabled,
                    feature_flag_key=flag_key,
                )
            )

        return results

    # ==========================================================================
    # 5. Internal Helpers
    # ==========================================================================

    def _resolve_period_bounds(self, period: BudgetPeriod, as_of: date) -> tuple[date, date]:
        """Resolves period start and end dates based on cadence and as_of date."""
        if period == BudgetPeriod.MONTHLY:
            start_date = as_of.replace(day=1)
            _, last_day = monthrange(as_of.year, as_of.month)
            end_date = as_of.replace(day=last_day)
            return start_date, end_date
        elif period == BudgetPeriod.QUARTERLY:
            q_start_month = ((as_of.month - 1) // 3) * 3 + 1
            q_end_month = q_start_month + 2
            start_date = date(as_of.year, q_start_month, 1)
            _, last_day = monthrange(as_of.year, q_end_month)
            end_date = date(as_of.year, q_end_month, last_day)
            return start_date, end_date
        elif period == BudgetPeriod.ANNUAL:
            start_date = date(as_of.year, 1, 1)
            end_date = date(as_of.year, 12, 31)
            return start_date, end_date

        # Default to current month
        start_date = as_of.replace(day=1)
        _, last_day = monthrange(as_of.year, as_of.month)
        end_date = as_of.replace(day=last_day)
        return start_date, end_date

    def _record_audit_event(
        self,
        *,
        event_type: AuditEventType,
        actor_id: str,
        action: str,
        resource_id: str,
        details: dict[str, Any],
        tenant_context: TenantContext,
    ) -> None:
        """Appends structured audit log event."""
        try:
            audit_svc = get_audit_service()
            audit_svc.append_event(
                tenant_context=tenant_context,
                event_in=AuditEventCreate(
                    event_type=event_type,
                    actor_id=actor_id,
                    action=action,
                    resource_id=resource_id,
                    resource_type="FORECAST",
                    details=details,
                ),
            )
        except Exception as e:
            logger.warning("Failed to append forecast audit event: %s", e)


# Singleton instance
_forecasting_service: ForecastingService | None = None


def get_forecasting_service() -> ForecastingService:
    """Returns singleton ForecastingService instance."""
    global _forecasting_service
    if _forecasting_service is None:
        _forecasting_service = ForecastingService()
    return _forecasting_service


def reset_forecasting_service() -> None:
    """Resets singleton ForecastingService instance for test teardown."""
    global _forecasting_service
    _forecasting_service = None
