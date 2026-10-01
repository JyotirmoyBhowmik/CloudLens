"""Provider API Call-Volume and Telemetry Cost Estimator (Prompt 25).

Enforces:
- Prompt 25: Call-volume estimator that predicts provider API call volume implied by a proposed
  metric configuration, exposed in the onboarding wizard before the configuration is enabled.
- Prompt 25: Acceptance - 'The call-volume estimate appears before a high-cardinality configuration is enabled.'
- Cardinality discipline: Cost control preventing monitoring telemetry costs from exceeding insight value.
"""

from __future__ import annotations

import logging
import math
from decimal import Decimal

from domain.models.enums import ProviderType
from domain.usage.models import (
    CallVolumeEstimate,
    CallVolumeEstimateRequest,
    CardinalityRisk,
    CollectionGranularity,
    MonitoringType,
)
from domain.usage.registry import get_allowable_metrics

logger = logging.getLogger(__name__)

# Provider API batch limits and unit pricing per 1,000 calls (USD)
PROVIDER_BATCH_SIZES: dict[ProviderType, int] = {
    ProviderType.AWS: 100,  # CloudWatch GetMetricData batches up to 500 metrics; practical batch ~100
    ProviderType.AZURE: 50,  # Azure Monitor batch querying
    ProviderType.GCP: 50,  # GCP Cloud Monitoring batch
    ProviderType.OCI: 50,  # OCI Telemetry service batch
}

PROVIDER_PRICE_PER_1K_CALLS_USD: dict[ProviderType, Decimal] = {
    ProviderType.AWS: Decimal("0.010"),  # $0.01 per 1,000 GetMetricData requests
    ProviderType.AZURE: Decimal("0.010"),  # $0.01 per 1,000 batch query requests
    ProviderType.GCP: Decimal("0.010"),  # $0.01 per 1,000 read API requests
    ProviderType.OCI: Decimal("0.0015"),  # $0.0015 per 1,000 telemetry calls
}


class CallVolumeEstimator:
    """Predicts API call volume and cost impact of metric collection configurations."""

    @classmethod
    def estimate(cls, request: CallVolumeEstimateRequest) -> CallVolumeEstimate:
        """Computes projected provider API calls and financial implications."""
        res_count = request.resource_count
        if res_count == 0:
            return CallVolumeEstimate(
                resource_count=0,
                granularity=request.granularity,
                metrics_per_resource_avg=0,
                total_active_metrics=0,
                daily_api_calls=0,
                monthly_api_calls=0,
                estimated_monthly_cost_usd=Decimal("0.00"),
                cardinality_risk=CardinalityRisk.LOW,
                warnings=[],
                recommendations=["Zero resources specified; no API calls will be generated."],
            )

        # 1. Determine active monitoring types and metric density
        mtypes = request.monitoring_types
        if not mtypes:
            # Default cross-section of common monitoring types
            mtypes = [
                MonitoringType.RUNTIME_BASED,
                MonitoringType.STORAGE_BASED,
                MonitoringType.VOLUME_BASED,
            ]

        total_metrics_count = 0
        for mt in mtypes:
            total_metrics_count += len(get_allowable_metrics(mt))

        metrics_per_res_avg = max(1, math.ceil(total_metrics_count / len(mtypes)))
        total_active_metrics = res_count * metrics_per_res_avg

        # 2. Granularity poll frequency
        polls_per_day: float
        if request.granularity == CollectionGranularity.HOURLY:
            polls_per_day = 24.0
        elif request.granularity == CollectionGranularity.DAILY:
            polls_per_day = 1.0
        else:  # MONTHLY
            polls_per_day = 1.0 / 30.0

        # 3. Batching & API calls calculation
        base_batch_size = PROVIDER_BATCH_SIZES.get(request.provider, 50)
        effective_batch_size = max(1, int(base_batch_size * request.batch_efficiency_factor))

        batches_per_cycle = math.ceil(total_active_metrics / effective_batch_size)
        daily_calls = max(1, math.ceil(batches_per_cycle * polls_per_day))
        monthly_calls = daily_calls * 30

        # 4. Projected cost in USD
        price_per_1k = PROVIDER_PRICE_PER_1K_CALLS_USD.get(request.provider, Decimal("0.010"))
        monthly_cost = (Decimal(str(monthly_calls)) / Decimal("1000")) * price_per_1k
        monthly_cost = monthly_cost.quantize(Decimal("0.01"))

        # 5. Risk tier classification
        warnings: list[str] = []
        recommendations: list[str] = []

        if monthly_calls >= 1_000_000:
            risk = CardinalityRisk.CRITICAL
            warnings.append(
                f"CRITICAL CARDINALITY: Configuration generates {monthly_calls:,} API calls/month "
                f"costing approximately ${monthly_cost:.2f} USD."
            )
            recommendations.append(
                "MANDATORY ACTION: Switch granularity from HOURLY to DAILY or enable cost-materiality "
                "filtering to avoid excessive cloud provider telemetry billing."
            )
        elif monthly_calls >= 100_000:
            risk = CardinalityRisk.HIGH
            warnings.append(
                f"HIGH CARDINALITY: Configuration generates {monthly_calls:,} API calls/month."
            )
            recommendations.append(
                "Consider enabling cost-materiality threshold filtering to exclude low-spend resources."
            )
        elif monthly_calls >= 10_000:
            risk = CardinalityRisk.MEDIUM
            recommendations.append(
                "Moderate call volume. Suitable for standard production monitoring."
            )
        else:
            risk = CardinalityRisk.LOW
            recommendations.append(
                "Low call volume. Well within standard cloud provider free/cheap tier allowances."
            )

        return CallVolumeEstimate(
            resource_count=res_count,
            granularity=request.granularity,
            metrics_per_resource_avg=metrics_per_res_avg,
            total_active_metrics=total_active_metrics,
            daily_api_calls=daily_calls,
            monthly_api_calls=monthly_calls,
            estimated_monthly_cost_usd=monthly_cost,
            cardinality_risk=risk,
            warnings=warnings,
            recommendations=recommendations,
        )
