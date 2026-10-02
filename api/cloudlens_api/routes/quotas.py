"""Quota, Service Limits, and Headroom API Endpoints (Prompt 54).

Enforces:
- API-050: Filterable quota view per provider, scope, and service with headroom trends.
- Prompt 54: Headroom summary endpoint for provider dashboards.
- Prompt 54: Administrator manual quota limit registration with mandatory source notes.
- Prompt 54: Formal quota increase request tracking with lead-time calculation.
- Prompt 54: Threshold overrides for headroom alerting parameters.
- Prompt 54: Remediation tasks viewable and linked to capacity forecasts.
- Prompt 13 Item 84: 100% TenantContext validation.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel

from api.cloudlens_api.tenant_context import get_authenticated_tenant_context
from connectors.simulator.connector import ProviderSimulatorConnector
from connectors.simulator.models import SimulatorProfile
from domain.models.enums import (
    CloudProvider,
    QuotaHeadroomState,
    QuotaScopeType,
)
from domain.quotas.models import (
    QuotaEntity,
    QuotaIncreaseCreateRequest,
    QuotaIncreaseRequest,
    QuotaIncreaseUpdateRequest,
    QuotaManualCreateRequest,
    QuotaOverrideRequest,
    QuotaRemediationTask,
    QuotaSummaryResponse,
)
from domain.quotas.service import QuotaService, get_quota_service
from domain.tenant.context import TenantContext

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/quotas", tags=["Quotas & Service Limits"])


# ==============================================================================
# Response Models
# ==============================================================================


class QuotaListResponse(BaseModel):
    """Paginated list of cloud service quotas (API-050)."""

    items: list[QuotaEntity]
    total: int
    limit: int
    offset: int


# ==============================================================================
# Endpoints
# ==============================================================================


@router.get(
    "",
    response_model=QuotaListResponse,
    summary="List cloud service quotas (API-050)",
    description="Returns filterable inventory of quotas, limits, and headroom states across connected providers.",
)
async def list_quotas(
    provider: str | None = Query(None, description="Filter by cloud provider"),
    service_code: str | None = Query(
        None, description="Filter by cloud service (ec2, compute, vpc, etc.)"
    ),
    scope_type: QuotaScopeType | None = Query(None, description="Filter by scope hierarchy level"),
    scope_id: str | None = Query(None, description="Filter by specific scope ID"),
    headroom_status: str | None = Query(
        None, alias="status", description="Filter by headroom state"
    ),
    is_manual: bool | None = Query(None, description="Filter by manual vs provider-discovered"),
    limit: int = Query(
        50, ge=1, le=500
    ),  # no-hardcode-allow: reason="standard pagination default", reviewer="finops-lead"
    offset: int = Query(
        0, ge=0
    ),  # no-hardcode-allow: reason="standard pagination default", reviewer="finops-lead"
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: QuotaService = Depends(get_quota_service),
) -> QuotaListResponse:
    """Provides filterable inventory list of all quotas (API-050)."""
    provider_enum = None
    if provider:
        try:
            provider_enum = CloudProvider(provider.lower())
        except ValueError:
            pass

    status_enum = None
    if headroom_status:
        try:
            status_enum = QuotaHeadroomState(headroom_status.upper())
        except ValueError:
            pass

    items = service.list_quotas(
        tenant_context=tenant_context,
        provider=provider_enum,
        service_code=service_code,
        scope_type=scope_type,
        scope_id=scope_id,
        status=status_enum,
        is_manual=is_manual,
        limit=limit,
        offset=offset,
    )
    total_count = service.repository.count(
        tenant_context=tenant_context,
        filter_params={
            "provider": provider_enum,
            "service_code": service_code,
            "scope_type": scope_type,
            "scope_id": scope_id,
            "status": status_enum,
            "is_manual": is_manual,
        },
    )
    return QuotaListResponse(
        items=items,
        total=total_count,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/summary/{provider}",
    response_model=QuotaSummaryResponse,
    summary="Provider dashboard headroom summary",
    description="Returns aggregate headroom counts and risk levels for an executive provider dashboard.",
)
async def get_provider_headroom_summary(
    provider: str,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: QuotaService = Depends(get_quota_service),
) -> QuotaSummaryResponse:
    """Generates executive provider headroom summary."""
    provider_enum = CloudProvider(provider.lower())
    return service.get_provider_summary(provider_enum, tenant_context=tenant_context)


@router.get(
    "/remediation-tasks",
    response_model=list[QuotaRemediationTask],
    summary="List quota remediation tasks",
    description="Returns actionable remediation tasks created when capacity exhaustion is predicted.",
)
async def list_remediation_tasks(
    quota_id: str | None = Query(None, description="Optional quota ID filter"),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: QuotaService = Depends(get_quota_service),
) -> list[QuotaRemediationTask]:
    """Lists generated remediation tasks."""
    return service.list_remediation_tasks(tenant_context=tenant_context, quota_id=quota_id)


@router.get(
    "/increase-requests",
    response_model=list[QuotaIncreaseRequest],
    summary="List quota increase requests",
    description="Returns tracked formal quota increase requests and their current status.",
)
async def list_increase_requests(
    quota_id: str | None = Query(None, description="Optional quota ID filter"),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: QuotaService = Depends(get_quota_service),
) -> list[QuotaIncreaseRequest]:
    """Lists tracked quota increase requests."""
    return service.list_increase_requests(tenant_context=tenant_context, quota_id=quota_id)


@router.get(
    "/{quota_id}",
    response_model=QuotaEntity,
    summary="Get quota detail and trend history",
    description="Returns single quota entity including rolling 3-month history and forecast metrics.",
)
async def get_quota_detail(
    quota_id: str,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: QuotaService = Depends(get_quota_service),
) -> QuotaEntity:
    """Retrieves full quota details including history and forecast dates."""
    return service.get_quota(quota_id, tenant_context=tenant_context)


@router.post(
    "/manual",
    response_model=QuotaEntity,
    status_code=status.HTTP_201_CREATED,
    summary="Record manual quota limit",
    description="Administrator registers a manual quota limit with mandatory source provenance note.",
)
async def create_manual_quota(
    request: QuotaManualCreateRequest,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: QuotaService = Depends(get_quota_service),
) -> QuotaEntity:
    """Registers manual quota limit with audit trail."""
    return service.record_manual_quota(
        request,
        tenant_context=tenant_context,
        actor_id=tenant_context.actor_id or "admin",
    )


@router.post(
    "/{quota_id}/overrides",
    response_model=QuotaEntity,
    summary="Configure headroom threshold and lead-time overrides",
    description="Applies customized warning/critical headroom percentages and lead times to a quota.",
)
async def apply_threshold_override(
    quota_id: str,
    request: QuotaOverrideRequest,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: QuotaService = Depends(get_quota_service),
) -> QuotaEntity:
    """Applies headroom threshold override with audit."""
    return service.apply_override(
        quota_id,
        request,
        tenant_context=tenant_context,
        actor_id=tenant_context.actor_id or "finops-engineer",
    )


@router.post(
    "/{quota_id}/increase-requests",
    response_model=QuotaIncreaseRequest,
    status_code=status.HTTP_201_CREATED,
    summary="Request quota limit increase",
    description="Files a formal quota limit increase request.",
)
async def create_increase_request(
    quota_id: str,
    request: QuotaIncreaseCreateRequest,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: QuotaService = Depends(get_quota_service),
) -> QuotaIncreaseRequest:
    """Files a formal quota increase request."""
    return service.create_increase_request(
        quota_id,
        request,
        tenant_context=tenant_context,
        actor_id=tenant_context.actor_id or "finops-engineer",
    )


@router.patch(
    "/increase-requests/{request_id}",
    response_model=QuotaIncreaseRequest,
    summary="Update quota increase request status",
    description="Updates request status (e.g. GRANTED) and computes actual lead time.",
)
async def update_increase_request(
    request_id: str,
    request: QuotaIncreaseUpdateRequest,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: QuotaService = Depends(get_quota_service),
) -> QuotaIncreaseRequest:
    """Updates status of a quota increase request."""
    return service.update_increase_request(
        request_id,
        request,
        tenant_context=tenant_context,
        actor_id=tenant_context.actor_id or "finops-engineer",
    )


@router.post(
    "/sync/{provider}",
    response_model=list[QuotaEntity],
    summary="Synchronize quotas from provider connector",
    description="Triggers live or simulated quota probing and updates history and forecast dates.",
)
async def sync_provider_quotas(
    provider: str,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: QuotaService = Depends(get_quota_service),
) -> list[QuotaEntity]:
    """Synchronizes quotas from cloud connector."""
    provider_enum = CloudProvider(provider.lower())
    profile = SimulatorProfile(provider_enum.value.lower())
    connector = ProviderSimulatorConnector(
        connector_id=f"conn-sim-{provider_enum.value.lower()}",
        tenant_id=tenant_context.tenant_id,
        profile=profile,
    )
    return service.sync_connector_quotas(
        connector,
        tenant_context=tenant_context,
        actor_id=tenant_context.actor_id or "system",
    )


@router.post(
    "/seed",
    response_model=list[QuotaEntity],
    status_code=status.HTTP_201_CREATED,
    summary="Seed demonstration multi-cloud quotas",
    description="Seeds realistic multi-cloud quotas with 3-month history and diverse headroom states.",
)
async def seed_sample_quotas(
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: QuotaService = Depends(get_quota_service),
) -> list[QuotaEntity]:
    """Seeds sample multi-cloud quotas for demo and testing."""
    return service.seed_sample_quotas_for_tenant(tenant_context=tenant_context)
