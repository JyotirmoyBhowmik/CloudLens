"""Threshold Engine API Endpoints (Prompt 27).

Enforces:
- API-035: GET /api/v1/thresholds - Configured threshold rules, contiguous bands, and anti-flapping parameters.
- API-036: POST /api/v1/thresholds - Create/configure threshold rule with validated contiguous bands.
- POST /api/v1/thresholds/evaluate - Evaluate value against threshold with 5-tier precedence and anti-flapping.
- POST /api/v1/thresholds/overrides - Create temporary or administrative threshold override.
- GET /api/v1/thresholds/overrides - List threshold overrides.
- POST /api/v1/thresholds/preview - Historical simulation (Phase 2 capability behind feature flag).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel

from api.cloudlens_api.tenant_context import get_authenticated_tenant_context
from domain.tenant.context import TenantContext
from domain.thresholds.models import (
    ThresholdBasis,
    ThresholdEvaluateRequest,
    ThresholdEvaluationResult,
    ThresholdOverride,
    ThresholdOverrideCreateRequest,
    ThresholdRule,
    ThresholdRuleCreateRequest,
)
from domain.thresholds.preview import (
    HistoricalDataPoint,
    ThresholdPreviewSimulationResult,
)
from domain.thresholds.service import ThresholdService, get_threshold_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/thresholds", tags=["Threshold Engine & Anti-Flapping"])


# ==============================================================================
# Request & Response Schemas
# ==============================================================================


class ThresholdRuleListResponse(BaseModel):
    """Paginated list of configured threshold rules (API-035)."""

    items: list[ThresholdRule]
    total: int
    limit: int
    offset: int


class ThresholdOverrideListResponse(BaseModel):
    """List of active and configured threshold overrides."""

    items: list[ThresholdOverride]
    total: int


class ThresholdPreviewRequest(BaseModel):
    """Payload to simulate a rule over historical series (Phase 2)."""

    rule: ThresholdRule
    data_points: list[HistoricalDataPoint]
    scope_id: str | None = None


# ==============================================================================
# 1. Threshold Rules Endpoints (API-035 / API-036)
# ==============================================================================


@router.get("", response_model=ThresholdRuleListResponse, status_code=status.HTTP_200_OK)
async def list_threshold_rules(
    basis: ThresholdBasis | None = Query(None, description="Optional basis filter"),
    limit: int = Query(
        50,  # no-hardcode-allow: reason="standard pagination default", reviewer="finops-lead"
        ge=1,
        le=200,
        description="Page limit",
    ),
    offset: int = Query(
        0,  # no-hardcode-allow: reason="standard pagination default", reviewer="finops-lead"
        ge=0,
        description="Page offset",
    ),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: ThresholdService = Depends(get_threshold_service),
) -> ThresholdRuleListResponse:
    """Lists configured threshold rules, contiguous bands, and anti-flapping parameters (API-035)."""
    rules = service.list_rules(tenant_context=tenant_context, basis=basis)
    total = len(rules)
    paged = rules[offset : offset + limit]
    return ThresholdRuleListResponse(
        items=paged,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=ThresholdRule, status_code=status.HTTP_201_CREATED)
async def create_threshold_rule(
    payload: ThresholdRuleCreateRequest,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: ThresholdService = Depends(get_threshold_service),
) -> ThresholdRule:
    """Creates a new threshold rule with strict non-overlapping contiguous band validation (API-036).

    Enforces Prompt 27 rule:
    - Bands are contiguous and non-overlapping, rejected at save time if not.
    """
    return service.create_rule(
        payload,
        actor_id=tenant_context.user_id or "system",
        tenant_context=tenant_context,
    )


@router.get("/{rule_id}", response_model=ThresholdRule, status_code=status.HTTP_200_OK)
async def get_threshold_rule(
    rule_id: str,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: ThresholdService = Depends(get_threshold_service),
) -> ThresholdRule:
    """Retrieves a specific threshold rule by ID."""
    return service.get_rule(rule_id, tenant_context=tenant_context)


# ==============================================================================
# 2. Threshold Overrides Endpoints
# ==============================================================================


@router.get(
    "/overrides",
    response_model=ThresholdOverrideListResponse,
    status_code=status.HTTP_200_OK,
)
async def list_threshold_overrides(
    target_id: str | None = Query(None, description="Optional target entity/scope filter"),
    active_only: bool = Query(True, description="Filter for currently active overrides"),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: ThresholdService = Depends(get_threshold_service),
) -> ThresholdOverrideListResponse:
    """Lists active and configured threshold overrides."""
    overrides = service.list_overrides(
        tenant_context=tenant_context, target_id=target_id, active_only=active_only
    )
    return ThresholdOverrideListResponse(items=overrides, total=len(overrides))


@router.post(
    "/overrides",
    response_model=ThresholdOverride,
    status_code=status.HTTP_201_CREATED,
)
async def create_threshold_override(
    payload: ThresholdOverrideCreateRequest,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: ThresholdService = Depends(get_threshold_service),
) -> ThresholdOverride:
    """Creates a temporary or administrative threshold override with mandatory recorded rationale.

    Enforces:
    - Temporary override requires mandatory reason (>= 20 chars) and auto-expiry timestamp.
    """
    return service.create_override(
        payload,
        actor_id=tenant_context.user_id or "system",
        tenant_context=tenant_context,
    )


# ==============================================================================
# 3. Threshold Evaluation Endpoint
# ==============================================================================


@router.post(
    "/evaluate",
    response_model=ThresholdEvaluationResult,
    status_code=status.HTTP_200_OK,
)
async def evaluate_threshold(
    payload: ThresholdEvaluateRequest,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: ThresholdService = Depends(get_threshold_service),
) -> ThresholdEvaluationResult:
    """Evaluates an entity's metric value following strict 5-tier precedence and anti-flapping.

    Enforces:
    - 5-tier resolution (Temporary override -> Admin override -> Local rule -> Ancestor -> Tenant default).
    - Source disclosure (AC-064 / FR-262).
    - Anti-flapping controls (dwell time, asymmetric hysteresis, cool-down, storm grouping, data quality gate).
    - Idempotency: unchanged inputs produce identical states.
    """
    return service.evaluate_entity(payload, tenant_context=tenant_context)


# ==============================================================================
# 4. Phase 2 Preview Simulation Endpoint (Flag-gated)
# ==============================================================================


@router.post(
    "/preview",
    response_model=ThresholdPreviewSimulationResult,
    status_code=status.HTTP_200_OK,
)
async def preview_threshold_simulation(
    payload: ThresholdPreviewRequest,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: ThresholdService = Depends(get_threshold_service),
) -> ThresholdPreviewSimulationResult:
    """Simulates a threshold rule against historical series.

    Strictly gated by ENABLE_THRESHOLD_PREVIEW flag (raises ThresholdPreviewDisabledException in MVP).
    """
    return service.preview_rule(
        rule=payload.rule,
        data_points=payload.data_points,
        scope_id=payload.scope_id,
        tenant_context=tenant_context,
    )
