"""Usage Telemetry Collector, Cardinality Controller, and Gap Manager (Prompt 25).

Enforces:
- Prompt 25: Cardinality discipline - collect only metrics required by monitoring type.
  "A storage resource collects storage metrics and not compute metrics."
  "Do not collect metrics a monitoring type does not require."
- Prompt 25: Coarse granularity - hourly or daily. Sub-hourly collection is strictly forbidden.
- Prompt 25: Pre-aggregated storage with recorded aggregation method.
- Prompt 25: Explicit gap recording as 'No Data' (never assumed zero).
- Prompt 25: Labeled interpolation only - silent interpolation is forbidden.
- Prompt 25: Downsampling policies (hourly rollups -> daily rollups per USE-006 / FR-245).
- Prompt 25: Statistical spike detection (USE-007 / FR-246).
"""

from __future__ import annotations

import logging
import math
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from domain.models.base import ProvenanceRecord
from domain.models.enums import OriginType
from domain.models.exceptions import (
    InterpolationLabelRequiredException,
    MetricNotApplicableException,
    SubHourlyCollectionForbiddenException,
)
from domain.models.measures import QuantityMeasure
from domain.tenant.context import TenantContext
from domain.usage.models import (
    AggregationMethod,
    CollectionGranularity,
    MonitoringType,
    PreAggregatedUsageRecord,
    SpikeStatus,
    UsageIngestRequest,
    UsageSpikeEvaluationResult,
)
from domain.usage.registry import (
    is_metric_allowed,
)
from domain.usage.repository import UsageRepository

logger = logging.getLogger(__name__)

SUB_HOURLY_DENIED_KEYWORDS = {"min", "minute", "sec", "second", "5m", "15m", "30m", "sub_hourly"}


class UsageCollector:
    """Core usage ingestion engine enforcing cardinality, coarse granularity, and gap discipline."""

    def __init__(self, repository: UsageRepository) -> None:
        self.repository = repository

    # ==========================================================================
    # 1. Granularity & Cardinality Guards
    # ==========================================================================

    @staticmethod
    def validate_granularity(
        granularity: CollectionGranularity | str | int | timedelta,
    ) -> CollectionGranularity:
        """Validates that granularity is coarse-grained (HOURLY, DAILY, MONTHLY).

        Strict negative constraint: 'Do not implement sub-hourly collection.'
        """
        if isinstance(granularity, timedelta):
            if granularity.total_seconds() < 3600:
                raise SubHourlyCollectionForbiddenException(int(granularity.total_seconds()))
            if granularity.total_seconds() >= 86400:
                return CollectionGranularity.DAILY
            return CollectionGranularity.HOURLY

        if isinstance(granularity, int):
            if granularity < 3600:
                raise SubHourlyCollectionForbiddenException(granularity)
            if granularity >= 86400:
                return CollectionGranularity.DAILY
            return CollectionGranularity.HOURLY

        if isinstance(granularity, str):
            norm = granularity.strip().lower()
            if any(sub in norm for sub in SUB_HOURLY_DENIED_KEYWORDS):
                raise SubHourlyCollectionForbiddenException(granularity)
            try:
                return CollectionGranularity(granularity.upper())
            except ValueError as err:
                raise SubHourlyCollectionForbiddenException(granularity) from err

        if isinstance(granularity, CollectionGranularity):
            return granularity

        raise SubHourlyCollectionForbiddenException(str(granularity))

    @staticmethod
    def enforce_cardinality(
        monitoring_type: MonitoringType,
        metric_name: str,
        resource_id: str | None = None,
        strict: bool = True,
    ) -> bool:
        """Enforces that a metric is permissible under the resource's monitoring type.

        Strict negative constraint: 'Do not collect metrics a monitoring type does not require.'
        'A storage resource collects storage metrics and not compute metrics.'
        """
        if not is_metric_allowed(monitoring_type, metric_name):
            if strict:
                raise MetricNotApplicableException(
                    metric_name=metric_name,
                    monitoring_type=monitoring_type.value,
                    resource_id=resource_id,
                )
            logger.warning(
                "Cardinality discipline: filtered out unrequested metric '%s' for monitoring type '%s' on '%s'.",
                metric_name,
                monitoring_type.value,
                resource_id,
            )
            return False
        return True

    # ==========================================================================
    # 2. Ingestion & Pre-Aggregation
    # ==========================================================================

    def ingest_metric(
        self,
        request: UsageIngestRequest,
        resolved_monitoring_type: MonitoringType,
        *,
        tenant_context: TenantContext,
    ) -> PreAggregatedUsageRecord:
        """Ingests a usage metric datum, enforcing cardinality, granularity, and gap rules."""
        # 1. Granularity guard
        granularity = self.validate_granularity(request.granularity)

        # 2. Cardinality guard
        self.enforce_cardinality(
            monitoring_type=resolved_monitoring_type,
            metric_name=request.metric_name,
            resource_id=request.resource_id,
            strict=request.strict_cardinality,
        )

        # 3. Gap & Interpolation discipline
        is_gap = request.is_gap or request.quantity is None
        is_interpolated = False
        interpolation_label: str | None = None

        if is_gap and request.interpolate:
            # Interpolation requested
            if not request.interpolation_label or not request.interpolation_label.strip():
                raise InterpolationLabelRequiredException()
            is_interpolated = True
            interpolation_label = request.interpolation_label.strip()
            # If quantity is not provided during interpolation, default fallback
            qty_val = request.quantity if request.quantity is not None else Decimal("0.0")
            measure = QuantityMeasure.of(qty_val)
            is_gap = False  # Gap filled by labeled interpolation
        elif is_gap:
            # Explicit No Data telemetry gap
            measure = QuantityMeasure.no_data()
        else:
            assert request.quantity is not None
            measure = QuantityMeasure.of(request.quantity)

        # 4. Construct pre-aggregated usage record
        rec_id = f"uf-{uuid.uuid4().hex[:12]}"
        record = PreAggregatedUsageRecord(
            id=rec_id,
            tenant_id=tenant_context.tenant_id,
            scope_id=request.scope_id,
            resource_id=request.resource_id,
            metric_name=request.metric_name,
            interval_start=request.interval_start,
            interval_end=request.interval_end,
            granularity=granularity,
            aggregation_method=request.aggregation_method,
            usage_quantity=measure,
            usage_unit=request.unit,
            is_gap=is_gap,
            is_interpolated=is_interpolated,
            interpolation_label=interpolation_label,
            provider_native=request.provider_native,
            source_provenance=ProvenanceRecord(
                source_system=f"cloudlens-usage:{resolved_monitoring_type.value}",
                origin_type=OriginType.DISCOVERED,
                correlation_id=tenant_context.correlation_id or f"corr-{uuid.uuid4().hex[:12]}",
            ),
        )

        self.repository.save_usage_record(record, tenant_context=tenant_context)
        return record

    # ==========================================================================
    # 3. Downsampling Rollup Policy (USE-006 / FR-245)
    # ==========================================================================

    def roll_up_to_daily(
        self,
        resource_id: str,
        metric_name: str,
        target_date: datetime,
        *,
        tenant_context: TenantContext,
    ) -> PreAggregatedUsageRecord | None:
        """Rolls up hourly records for a given resource and metric into a daily pre-aggregated fact.

        Retains aggregation method and handles gaps explicitly.
        """
        day_start = datetime(
            target_date.year, target_date.month, target_date.day, 0, 0, 0, tzinfo=UTC
        )
        day_end = day_start + timedelta(days=1)

        from domain.usage.models import UsageQueryFilter

        hourly_records = self.repository.query_metrics(
            UsageQueryFilter(
                resource_id=resource_id,
                metric_name=metric_name,
                interval_start_gte=day_start,
                interval_end_lte=day_end,
                granularity=CollectionGranularity.HOURLY,
                include_gaps=True,
                limit=100,
            ),
            tenant_context=tenant_context,
        )

        if not hourly_records:
            return None

        scope_id = hourly_records[0].scope_id
        unit = hourly_records[0].usage_unit
        method = hourly_records[0].aggregation_method

        valid_values: list[Decimal] = []
        has_any_interpolation = False

        for rec in hourly_records:
            if not rec.is_gap and not rec.usage_quantity.is_null:
                valid_values.append(rec.usage_quantity.value)
            if rec.is_interpolated:
                has_any_interpolation = True

        if not valid_values:
            # 100% gap for the day
            daily_qty = QuantityMeasure.no_data()
            is_gap = True
        else:
            if method == AggregationMethod.SUM:
                aggregated_val = sum(valid_values)
            elif method == AggregationMethod.AVERAGE:
                aggregated_val = sum(valid_values) / Decimal(str(len(valid_values)))
            elif method == AggregationMethod.MAX:
                aggregated_val = max(valid_values)
            elif method == AggregationMethod.LAST:
                aggregated_val = valid_values[-1]
            else:
                aggregated_val = sum(valid_values)

            daily_qty = QuantityMeasure.of(aggregated_val)
            is_gap = False

        rollup_id = f"uf-rollup-{resource_id[:8]}-{metric_name[:8]}-{day_start.strftime('%Y%m%d')}"
        daily_record = PreAggregatedUsageRecord(
            id=rollup_id,
            tenant_id=tenant_context.tenant_id,
            scope_id=scope_id,
            resource_id=resource_id,
            metric_name=metric_name,
            interval_start=day_start,
            interval_end=day_end,
            granularity=CollectionGranularity.DAILY,
            aggregation_method=method,
            usage_quantity=daily_qty,
            usage_unit=unit,
            is_gap=is_gap,
            is_interpolated=has_any_interpolation,
            interpolation_label="ROLLUP_WITH_INTERPOLATED_SAMPLES"
            if has_any_interpolation
            else None,
            source_provenance=ProvenanceRecord(
                source_system="cloudlens-usage:hourly-rollup",
                origin_type=OriginType.DERIVED,
                correlation_id=tenant_context.correlation_id or f"corr-{uuid.uuid4().hex[:12]}",
            ),
        )

        self.repository.save_usage_record(daily_record, tenant_context=tenant_context)
        return daily_record

    # ==========================================================================
    # 4. Statistical Spike Detection (USE-007 / FR-246)
    # ==========================================================================

    @staticmethod
    def evaluate_consumption_spike(
        resource_id: str,
        metric_name: str,
        observed_value: Decimal,
        baseline_history: list[Decimal],
        sigma_threshold: Decimal = Decimal("3.0"),
    ) -> UsageSpikeEvaluationResult:
        """Detects usage spikes using baseline statistical standard deviations (USE-007 / FR-246)."""
        if len(baseline_history) < 3:
            return UsageSpikeEvaluationResult(
                resource_id=resource_id,
                metric_name=metric_name,
                baseline_mean=Decimal("0.0"),
                baseline_std_dev=Decimal("0.0"),
                observed_value=observed_value,
                z_score=Decimal("0.0"),
                threshold_sigma=sigma_threshold,
                status=SpikeStatus.INSUFFICIENT_DATA,
                message="Insufficient baseline history (minimum 3 samples required).",
            )

        n = len(baseline_history)
        mean_val = sum(baseline_history) / Decimal(str(n))
        variance = sum((x - mean_val) ** 2 for x in baseline_history) / Decimal(str(n))
        std_dev = Decimal(str(math.sqrt(float(variance))))

        if std_dev == Decimal("0.0"):
            # Completely constant baseline
            z_score = Decimal("0.0") if observed_value == mean_val else Decimal("999.0")
        else:
            z_score = (observed_value - mean_val) / std_dev

        is_spike = z_score >= sigma_threshold
        status = SpikeStatus.ANOMALOUS_SPIKE if is_spike else SpikeStatus.NORMAL

        msg = (
            f"Observed value {observed_value} is {z_score:.2f} standard deviations from mean {mean_val:.2f}."
            if is_spike
            else f"Observed value {observed_value} is within normal threshold ({z_score:.2f} sigma <= {sigma_threshold} sigma)."
        )

        return UsageSpikeEvaluationResult(
            resource_id=resource_id,
            metric_name=metric_name,
            baseline_mean=mean_val,
            baseline_std_dev=std_dev,
            observed_value=observed_value,
            z_score=z_score,
            threshold_sigma=sigma_threshold,
            status=status,
            message=msg,
        )
