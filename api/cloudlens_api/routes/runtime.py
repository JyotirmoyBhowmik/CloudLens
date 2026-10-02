"""Runtime Model, Schedule Adherence, and Exemption API Endpoints (Prompt 26).

Enforces:
- API-032: GET /api/v1/runtime/states - Resource running/stopped/unknown runtime status.
- API-033: GET /api/v1/runtime/schedules - Configured operational schedules and exemptions.
- API-034: POST /api/v1/runtime/exemptions - Create a time-boxed runtime schedule exemption.
- Prompt 26: Six runtime states with non-compliance discipline (Unknown and No Data never green).
- Prompt 26: Out-of-schedule execution detected with mandatory monetary valuation.
- Prompt 26 Negative Constraint: Idle detection disabled in MVP behind feature flag.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel

from api.cloudlens_api.tenant_context import get_authenticated_tenant_context
from domain.runtime.models import (
    AdherenceEvaluateRequest,
    NamedSchedule,
    RuntimeExemption,
    RuntimeExemptionCreateRequest,
    RuntimeState,
    ScheduleAdherenceResult,
    ScheduleAttachment,
    ScheduleAttachRequest,
    ScheduleCreateRequest,
)
from domain.runtime.service import RuntimeService, get_runtime_service
from domain.tenant.context import TenantContext

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/runtime", tags=["Runtime Model & Schedule Adherence"])


# ==============================================================================
# Request & Response Schemas
# ==============================================================================


class RuntimeStateResponse(BaseModel):
    """Response payload detailing a resource's operational runtime status (API-032)."""

    resource_id: str
    runtime_state: RuntimeState
    color_hex: str
    is_compliant_permitted: bool
    is_green_permitted: bool


class SchedulesAndExemptionsResponse(BaseModel):
    """Response payload containing configured schedules and active exemptions (API-033)."""

    schedules: list[NamedSchedule]
    active_exemptions: list[RuntimeExemption]


class AdherenceListResponse(BaseModel):
    """Paginated response payload for evaluated schedule adherence records."""

    items: list[ScheduleAdherenceResult]
    total: int
    limit: int
    offset: int


class IdleDetectionStatusResponse(BaseModel):
    """Status payload indicating the Phase 2 idle detection feature flag state."""

    enabled: bool
    message: str


# ==============================================================================
# 1. Runtime State Endpoints (API-032 / RUN-001 / AC-061)
# ==============================================================================


@router.get("/states", response_model=RuntimeStateResponse, status_code=status.HTTP_200_OK)
async def get_resource_runtime_state(
    resource_id: str = Query(..., description="Target canonical resource ID"),
    start_time: datetime | None = Query(
        None, description="Observation window start in UTC (defaults to 24h ago)"
    ),
    end_time: datetime | None = Query(
        None, description="Observation window end in UTC (defaults to now)"
    ),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: RuntimeService = Depends(get_runtime_service),
) -> RuntimeStateResponse:
    """Retrieves current operational runtime status and badge color for a resource (API-032).

    Enforces:
    - AC-061: Unknown and No Data must NEVER be rendered green.
    """
    now = datetime.now(UTC)
    w_end = end_time or now
    w_start = start_time or (w_end - timedelta(hours=24))

    state, color_hex = service.get_resource_runtime_state(
        resource_id=resource_id,
        start_time=w_start,
        end_time=w_end,
        tenant_context=tenant_context,
    )

    return RuntimeStateResponse(
        resource_id=resource_id,
        runtime_state=state,
        color_hex=color_hex,
        is_compliant_permitted=state.is_compliant_permitted(),
        is_green_permitted=state.is_green_permitted(),
    )


# ==============================================================================
# 2. Named Schedules & Attachments (API-033 / RUN-002)
# ==============================================================================


@router.get(
    "/schedules",
    response_model=SchedulesAndExemptionsResponse,
    status_code=status.HTTP_200_OK,
)
async def list_schedules_and_exemptions(
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: RuntimeService = Depends(get_runtime_service),
) -> SchedulesAndExemptionsResponse:
    """Returns configured operational runtime schedules and active exemptions (API-033)."""
    schedules = service.list_schedules(tenant_context=tenant_context)
    active_exemptions = service.list_active_exemptions(
        as_of=datetime.now(UTC), tenant_context=tenant_context
    )
    return SchedulesAndExemptionsResponse(
        schedules=schedules,
        active_exemptions=active_exemptions,
    )


@router.post(
    "/schedules",
    response_model=NamedSchedule,
    status_code=status.HTTP_201_CREATED,
)
async def create_schedule(
    request: ScheduleCreateRequest,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: RuntimeService = Depends(get_runtime_service),
) -> NamedSchedule:
    """Registers a new named operational runtime schedule."""
    return service.create_schedule(request, tenant_context=tenant_context)


@router.post(
    "/schedules/attach",
    response_model=ScheduleAttachment,
    status_code=status.HTTP_201_CREATED,
)
async def attach_schedule(
    request: ScheduleAttachRequest,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: RuntimeService = Depends(get_runtime_service),
) -> ScheduleAttachment:
    """Attaches a named schedule to a resource, service, scope, env, or tenant."""
    return service.attach_schedule(
        request, actor_id=tenant_context.user_id, tenant_context=tenant_context
    )


# ==============================================================================
# 3. Temporary Runtime Exemptions (API-034 / RUN-005 / AC-062)
# ==============================================================================


@router.post(
    "/exemptions",
    response_model=RuntimeExemption,
    status_code=status.HTTP_201_CREATED,
)
async def create_runtime_exemption(
    request: RuntimeExemptionCreateRequest,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: RuntimeService = Depends(get_runtime_service),
) -> RuntimeExemption:
    """Creates a time-boxed runtime schedule exemption with recorded justification (API-034)."""
    return service.create_exemption(
        request, actor_id=tenant_context.user_id, tenant_context=tenant_context
    )


@router.get(
    "/exemptions",
    response_model=list[RuntimeExemption],
    status_code=status.HTTP_200_OK,
)
async def list_active_exemptions(
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: RuntimeService = Depends(get_runtime_service),
) -> list[RuntimeExemption]:
    """Lists currently active unexpired exemptions across the tenant."""
    return service.list_active_exemptions(as_of=datetime.now(UTC), tenant_context=tenant_context)


# ==============================================================================
# 4. Schedule Adherence Evaluation & Valuation (AC-060 / RUN-003)
# ==============================================================================


@router.post(
    "/adherence/evaluate",
    response_model=ScheduleAdherenceResult,
    status_code=status.HTTP_200_OK,
)
async def evaluate_schedule_adherence(
    request: AdherenceEvaluateRequest,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: RuntimeService = Depends(get_runtime_service),
) -> ScheduleAdherenceResult:
    """Evaluates whether a resource complied with its approved schedule and attaches breach costs."""
    return service.evaluate_adherence(
        resource_id=request.resource_id,
        start_time=request.start_time,
        end_time=request.end_time,
        hourly_rate=request.hourly_rate,
        currency=request.currency,
        environment=request.environment or "production",
        tenant_context=tenant_context,
    )


@router.get(
    "/adherence",
    response_model=AdherenceListResponse,
    status_code=status.HTTP_200_OK,
)
async def list_adherence_results(
    limit: int = Query(
        50, ge=1, le=500, description="Pagination limit"
    ),  # no-hardcode-allow: reason="standard pagination default", reviewer="finops-lead"
    offset: int = Query(
        0, ge=0, description="Pagination offset"
    ),  # no-hardcode-allow: reason="standard pagination default", reviewer="finops-lead"
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: RuntimeService = Depends(get_runtime_service),
) -> AdherenceListResponse:
    """Lists evaluated schedule adherence records under tenant isolation."""
    results = service.repository.list(tenant_context=tenant_context, limit=limit, offset=offset)
    return AdherenceListResponse(
        items=results,
        total=len(results),
        limit=limit,
        offset=offset,
    )


# ==============================================================================
# 5. Phase 2 Idle Detection Flag-Gated Endpoint (Prompt 26 Negative Constraint)
# ==============================================================================


@router.get(
    "/idle/signals",
    response_model=IdleDetectionStatusResponse,
    status_code=status.HTTP_200_OK,
)
async def get_idle_detection_signals(
    _tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: RuntimeService = Depends(get_runtime_service),
) -> IdleDetectionStatusResponse:
    """Returns idle detection status enforcing Prompt 26 negative constraint: Disabled in MVP."""
    return IdleDetectionStatusResponse(
        enabled=service.idle_detector.is_enabled,
        message="Idle and underutilisation detection is a Phase 2 capability and is disabled in MVP.",
    )
