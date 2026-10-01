"""CloudLens Usage Telemetry, Monitoring Types, Expectations, and Ingestion Routes (Prompt 25).

Enforces:
- USE-001 to USE-010, FR-240 to FR-246, API-031, AC-051 to AC-053.
- Prompt 25: Fourteen canonical monitoring types (MT-01 to MT-14) + Quota Headroom (MT-15).
- Prompt 25: Per-resource monitoring type defaulting and override with audit.
- Prompt 25: Cardinality discipline - collect only metrics required by monitoring type.
- Prompt 25: Coarse granularity - hourly or daily. Sub-hourly collection is strictly forbidden.
- Prompt 25: Explicit gap recording as 'No Data' (never assumed zero).
- Prompt 25: Labeled interpolation only - silent interpolation is forbidden.
- Prompt 25: 4-level expectation inheritance (RESOURCE, SERVICE, SCOPE, TENANT).
- Prompt 25: Call-volume estimator and cost-materiality filter.
"""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field

from api.cloudlens_api.tenant_context import get_authenticated_tenant_context
from domain.models.measures import QuantityMeasure
from domain.tenant.context import TenantContext
from domain.usage.models import (
    CallVolumeEstimate,
    CallVolumeEstimateRequest,
    CollectionGranularity,
    ExpectationEvaluationResult,
    ExpectationLevel,
    MaterialityFilterConfig,
    MaterialityFilterResult,
    MonitoringType,
    MonitoringTypeDefinition,
    MonitoringTypeOverride,
    PreAggregatedUsageRecord,
    ResolvedMonitoringType,
    UsageExpectation,
    UsageIngestRequest,
    UsageQueryFilter,
)
from domain.usage.service import UsageService, get_usage_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/usage", tags=["Usage Telemetry & Monitoring"])


# ==============================================================================
# Request & Response Schemas
# ==============================================================================


class UsageMetricsResponse(BaseModel):
    """Response payload for queried usage metrics (API-031)."""

    items: list[PreAggregatedUsageRecord]
    total: int
    limit: int
    offset: int


class MonitoringTypeOverrideRequest(BaseModel):
    """Request payload to apply a per-resource monitoring type override with audit."""

    new_monitoring_type: MonitoringType
    who: str
    why: str = Field(..., min_length=20, description="Mandatory business rationale (min 20 chars)")
    native_type_name: str = ""
    canonical_type: str | None = None


class UsageIngestWrapper(BaseModel):
    """Ingestion request wrapper with resource classification hints."""

    request: UsageIngestRequest
    native_type_name: str = ""
    canonical_type: str | None = None


class MaterialityFilterRequest(BaseModel):
    """Payload to evaluate candidate resources against cost-materiality threshold."""

    candidates: list[dict[str, Any]]
    config: MaterialityFilterConfig | None = None


# ==============================================================================
# API Endpoints
# ==============================================================================


@router.get("/metrics", response_model=UsageMetricsResponse, status_code=status.HTTP_200_OK)
async def query_usage_metrics(
    resource_id: str | None = Query(None, description="Target resource ID"),
    scope_id: str | None = Query(None, description="Target scope ID"),
    metric_name: str | None = Query(None, description="Metric descriptor"),
    interval_start_gte: datetime | None = Query(None, description="Interval start on or after UTC"),
    interval_end_lte: datetime | None = Query(None, description="Interval end on or before UTC"),
    granularity: CollectionGranularity | None = Query(None, description="Collection granularity"),
    include_gaps: bool = Query(True, description="Whether to include recorded gaps in results"),
    limit: int = Query(
        50, ge=1, le=500, description="Pagination limit"
    ),  # no-hardcode-allow: reason="standard pagination default", reviewer="finops-lead"
    offset: int = Query(
        0, ge=0, description="Pagination offset"
    ),  # no-hardcode-allow: reason="standard pagination default", reviewer="finops-lead"
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: UsageService = Depends(get_usage_service),
) -> UsageMetricsResponse:
    """Queries pre-aggregated metric time series with multi-attribute filtering (API-031)."""
    filter_params = UsageQueryFilter(
        resource_id=resource_id,
        scope_id=scope_id,
        metric_name=metric_name,
        interval_start_gte=interval_start_gte,
        interval_end_lte=interval_end_lte,
        granularity=granularity,
        include_gaps=include_gaps,
        limit=limit,
        offset=offset,
    )
    items = service.query_metrics(filter_params, tenant_context=tenant_context)
    return UsageMetricsResponse(
        items=items,
        total=len(items),
        limit=limit,
        offset=offset,
    )


@router.post(
    "/collect",
    response_model=PreAggregatedUsageRecord,
    status_code=status.HTTP_201_CREATED,
)
async def collect_usage_metric(
    payload: UsageIngestWrapper,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: UsageService = Depends(get_usage_service),
) -> PreAggregatedUsageRecord:
    """Ingests a pre-aggregated usage metric, enforcing cardinality, granularity, and gap rules."""
    return service.ingest_usage(
        request=payload.request,
        native_type_name=payload.native_type_name,
        canonical_type=payload.canonical_type,
        tenant_context=tenant_context,
    )


@router.get(
    "/monitoring-types",
    response_model=list[MonitoringTypeDefinition],
    status_code=status.HTTP_200_OK,
)
async def list_all_monitoring_types(
    service: UsageService = Depends(get_usage_service),
) -> list[MonitoringTypeDefinition]:
    """Lists all fifteen canonical monitoring types (MT-01 to MT-15)."""
    return service.list_monitoring_types()


@router.get(
    "/resources/{resource_id}/monitoring-type",
    response_model=ResolvedMonitoringType,
    status_code=status.HTTP_200_OK,
)
async def get_resource_monitoring_type(
    resource_id: str,
    native_type_name: str = Query("", description="Native provider resource type"),
    canonical_type: str | None = Query(None, description="Canonical normalized resource type"),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: UsageService = Depends(get_usage_service),
) -> ResolvedMonitoringType:
    """Resolves active monitoring type for a resource, checking overrides before catalogue defaults."""
    return service.resolve_monitoring_type(
        resource_id=resource_id,
        native_type_name=native_type_name,
        canonical_type=canonical_type,
        tenant_context=tenant_context,
    )


@router.post(
    "/resources/{resource_id}/monitoring-type/override",
    response_model=MonitoringTypeOverride,
    status_code=status.HTTP_200_OK,
)
async def override_resource_monitoring_type(
    resource_id: str,
    payload: MonitoringTypeOverrideRequest,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: UsageService = Depends(get_usage_service),
) -> MonitoringTypeOverride:
    """Applies a per-resource monitoring type override with mandatory audit trail."""
    return service.override_monitoring_type(
        resource_id=resource_id,
        new_monitoring_type=payload.new_monitoring_type,
        who=payload.who,
        why=payload.why,
        native_type_name=payload.native_type_name,
        canonical_type=payload.canonical_type,
        tenant_context=tenant_context,
    )


@router.get(
    "/expectations",
    response_model=list[UsageExpectation],
    status_code=status.HTTP_200_OK,
)
async def list_usage_expectations(
    level: ExpectationLevel | None = Query(None, description="Filter by level"),
    target_id: str | None = Query(None, description="Filter by target ID"),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: UsageService = Depends(get_usage_service),
) -> list[UsageExpectation]:
    """Lists configured usage expectations across RESOURCE, SERVICE, SCOPE, and TENANT levels."""
    return service.list_expectations(
        tenant_context=tenant_context,
        level=level,
        target_id=target_id,
    )


@router.post(
    "/expectations",
    response_model=UsageExpectation,
    status_code=status.HTTP_201_CREATED,
)
async def create_or_update_usage_expectation(
    expectation: UsageExpectation,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: UsageService = Depends(get_usage_service),
) -> UsageExpectation:
    """Creates or updates a usage expectation in the 4-level hierarchy."""
    return service.save_expectation(expectation, tenant_context=tenant_context)


@router.get(
    "/resources/{resource_id}/expectation",
    response_model=ExpectationEvaluationResult,
    status_code=status.HTTP_200_OK,
)
async def evaluate_resource_expectation(
    resource_id: str,
    service_id: str = Query("", description="Service ID for inheritance"),
    scope_id: str = Query("", description="Scope ID for inheritance"),
    metric_name: str = Query("", description="Target metric name"),
    quantity: Decimal | None = Query(None, description="Observed numeric quantity or None for gap"),
    unit: str = Query("", description="Observed unit"),
    is_gap: bool = Query(False, description="Whether telemetry has a gap"),
    native_type_name: str = Query("", description="Native provider resource type"),
    canonical_type: str | None = Query(None, description="Canonical resource type"),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: UsageService = Depends(get_usage_service),
) -> ExpectationEvaluationResult:
    """Evaluates observed usage against resolved expectation through 4-level inheritance."""
    if is_gap or quantity is None:
        observed_qty = QuantityMeasure.no_data()
    else:
        observed_qty = QuantityMeasure.of(quantity)

    return service.evaluate_resource_usage(
        resource_id=resource_id,
        service_id=service_id,
        scope_id=scope_id,
        metric_name=metric_name,
        observed_quantity=observed_qty,
        observed_unit=unit,
        native_type_name=native_type_name,
        canonical_type=canonical_type,
        tenant_context=tenant_context,
    )


@router.post(
    "/call-volume-estimate",
    response_model=CallVolumeEstimate,
    status_code=status.HTTP_200_OK,
)
async def calculate_call_volume_estimate(
    request: CallVolumeEstimateRequest,
    service: UsageService = Depends(get_usage_service),
) -> CallVolumeEstimate:
    """Predicts provider API call volume and costs for proposed metric configuration."""
    return service.estimate_call_volume(request)


@router.post(
    "/materiality-filter",
    response_model=MaterialityFilterResult,
    status_code=status.HTTP_200_OK,
)
async def apply_cost_materiality_filter(
    payload: MaterialityFilterRequest,
    service: UsageService = Depends(get_usage_service),
) -> MaterialityFilterResult:
    """Filters candidate resources to exclude those below cost materiality threshold."""
    return service.filter_by_materiality(payload.candidates, payload.config)
