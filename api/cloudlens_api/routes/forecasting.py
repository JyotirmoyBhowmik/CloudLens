"""Forecasting Engine API Endpoints (Prompt 29).

Enforces:
- Prompt 29: Produce forward-looking numbers that never overstate their own confidence.
- Prompt 29: Support all 7 methods (3 MVP, 4 Phase 2 flag-gated) and all 7 outputs.
- Prompt 29: Prominent display of method, window, and confidence on every forecast.
- Prompt 29: Restatement-triggered recomputation.
- Prompt 29: Forecast accuracy measurement at 25%, 50%, 75% milestones and period close.
- Prompt 13 Item 84: 100% TenantContext validation.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field

from api.cloudlens_api.tenant_context import get_authenticated_tenant_context
from domain.cost.models import CostRestatementRecord
from domain.forecasting.models import (
    DailySpendPoint,
    ForecastAccuracyTrend,
    ForecastConfidence,
    ForecastEntity,
    ForecastGenerateRequest,
    ForecastMethod,
    ForecastMethodInfo,
    ForecastMilestoneSnapshot,
    PeriodAccuracyReport,
)
from domain.forecasting.service import ForecastingService, get_forecasting_service
from domain.models.enums import BudgetPeriod
from domain.tenant.context import TenantContext

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/forecasts", tags=["Forecasting Engine"])


# ==============================================================================
# Response Models
# ==============================================================================


class ForecastListResponse(BaseModel):
    """Paginated response containing calculated forecasts."""

    items: list[ForecastEntity]
    total: int
    limit: int
    offset: int


class ForecastRecomputeResponse(BaseModel):
    """Result of restatement-driven forecast recomputations."""

    recomputed_count: int
    items: list[ForecastEntity]


class RestatementRecomputePayload(BaseModel):
    """Request payload containing restatement record and updated daily spends."""

    restatement: CostRestatementRecord
    updated_spends: list[DailySpendPoint] = Field(default_factory=list)


class EvaluatePeriodClosePayload(BaseModel):
    """Request payload to evaluate forecast accuracy at period close."""

    period_identifier: str
    period_start: date
    period_end: date
    actual_billed_amount: float = Field(..., ge=0.0)
    scope_id: str | None = None


# ==============================================================================
# API Endpoints
# ==============================================================================


@router.post(
    "/generate",
    response_model=ForecastEntity,
    status_code=status.HTTP_201_CREATED,
    summary="Generate Forward-Looking Spend Forecast",
    description="Calculates a forward-looking forecast across MVP and Phase 2 algorithms with strict confidence discipline.",
)
async def generate_forecast(
    request: ForecastGenerateRequest,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: ForecastingService = Depends(get_forecasting_service),
) -> ForecastEntity:
    """Generates and persists a forward-looking spend projection (Prompt 29)."""
    return service.generate_forecast(request, tenant_context=tenant_context)


@router.get(
    "",
    response_model=ForecastListResponse,
    status_code=status.HTTP_200_OK,
    summary="List Forecast Projections",
    description="Retrieves tenant forecasts with optional filtering by scope, budget, method, and confidence.",
)
async def list_forecasts(
    scope_id: str | None = Query(None, description="Filter by scope node ID"),
    budget_id: str | None = Query(None, description="Filter by budget ceiling ID"),
    period: BudgetPeriod | None = Query(None, description="Filter by budget cadence"),
    method: ForecastMethod | None = Query(None, description="Filter by effective method"),
    confidence: ForecastConfidence | None = Query(None, description="Filter by confidence rating"),
    is_active: bool | None = Query(True, description="Filter by active status"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: ForecastingService = Depends(get_forecasting_service),
) -> ForecastListResponse:
    """Lists forecasts belonging to the authenticated tenant."""
    filter_params: dict[str, Any] = {}
    if scope_id:
        filter_params["scope_id"] = scope_id
    if budget_id:
        filter_params["budget_id"] = budget_id
    if period:
        filter_params["period"] = period
    if method:
        filter_params["effective_method"] = method
    if confidence:
        filter_params["confidence"] = confidence
    if is_active is not None:
        filter_params["is_active"] = is_active

    total = service.repository.count(tenant_context=tenant_context, filter_params=filter_params)
    items = service.list_forecasts(
        tenant_context=tenant_context,
        filter_params=filter_params,
        limit=limit,
        offset=offset,
    )
    return ForecastListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get(
    "/methods",
    response_model=list[ForecastMethodInfo],
    status_code=status.HTTP_200_OK,
    summary="List Supported Forecast Algorithms",
    description="Discovers all 7 forecast methods with MVP baseline vs Phase 2 flag status and minimum history requirements.",
)
async def list_supported_methods(
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: ForecastingService = Depends(get_forecasting_service),
) -> list[ForecastMethodInfo]:
    """Lists supported forecast algorithms with gating metadata."""
    return service.list_supported_methods(tenant_context=tenant_context)


@router.get(
    "/accuracy-trend",
    response_model=ForecastAccuracyTrend,
    status_code=status.HTTP_200_OK,
    summary="Get Multi-Period Forecast Accuracy Trend",
    description="Produces historical accuracy and convergence trends across closed periods and milestones (Prompt 29).",
)
async def get_accuracy_trend(
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: ForecastingService = Depends(get_forecasting_service),
) -> ForecastAccuracyTrend:
    """Retrieves forecast accuracy trend and error convergence metrics."""
    return service.get_accuracy_trend(tenant_context=tenant_context)


@router.get(
    "/{forecast_id}",
    response_model=ForecastEntity,
    status_code=status.HTTP_200_OK,
    summary="Get Forecast by ID",
    description="Retrieves a specific forecast record with its method, window, confidence, and mathematical derivation.",
)
async def get_forecast(
    forecast_id: str,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: ForecastingService = Depends(get_forecasting_service),
) -> ForecastEntity:
    """Retrieves single forecast projection by ID."""
    return service.get_forecast(forecast_id, tenant_context=tenant_context)


@router.post(
    "/{forecast_id}/milestones",
    response_model=ForecastMilestoneSnapshot,
    status_code=status.HTTP_201_CREATED,
    summary="Record Forecast Milestone Checkpoint",
    description="Records a snapshot at 25%, 50%, or 75% milestone for subsequent accuracy evaluation.",
)
async def record_milestone_checkpoint(
    forecast_id: str,
    as_of: date | None = Query(None, description="Milestone evaluation checkpoint date"),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: ForecastingService = Depends(get_forecasting_service),
) -> ForecastMilestoneSnapshot:
    """Records milestone snapshot for accuracy evaluation."""
    return service.record_milestone_checkpoint(
        forecast_id=forecast_id,
        as_of=as_of,
        tenant_context=tenant_context,
    )


@router.post(
    "/evaluate-period-close",
    response_model=PeriodAccuracyReport,
    status_code=status.HTTP_200_OK,
    summary="Evaluate Closed Period Forecast Accuracy",
    description="Evaluates all milestone forecasts recorded for a closed period against actual billed spend.",
)
async def evaluate_period_close(
    payload: EvaluatePeriodClosePayload,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: ForecastingService = Depends(get_forecasting_service),
) -> PeriodAccuracyReport:
    """Evaluates forecast accuracy for a closed billing period."""
    return service.evaluate_period_close_accuracy(
        period_identifier=payload.period_identifier,
        period_start=payload.period_start,
        period_end=payload.period_end,
        actual_billed_amount=payload.actual_billed_amount,
        scope_id=payload.scope_id,
        tenant_context=tenant_context,
    )


@router.post(
    "/recompute-restatement",
    response_model=ForecastRecomputeResponse,
    status_code=status.HTTP_200_OK,
    summary="Recompute Forecasts Affected by Cost Restatement",
    description="Recomputes all active forecasts whose input window or target period overlaps a detected restatement.",
)
async def recompute_for_restatement(
    payload: RestatementRecomputePayload,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: ForecastingService = Depends(get_forecasting_service),
) -> ForecastRecomputeResponse:
    """Recomputes forecasts affected by restated actuals."""
    recomputed = service.recompute_for_restatement(
        restatement_record=payload.restatement,
        updated_spends=payload.updated_spends,
        tenant_context=tenant_context,
    )
    return ForecastRecomputeResponse(
        recomputed_count=len(recomputed),
        items=recomputed,
    )
