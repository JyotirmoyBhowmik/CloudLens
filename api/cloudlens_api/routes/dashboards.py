"""Dashboards REST API Routes (Prompt 37).

Enforces:
- API endpoints for Executive, Provider, and Service dashboards.
- Dynamic period selection and comparison basis.
- Role-based landing dashboard resolution and user preference persistence.
- Widget-level data export in CSV and JSON formats.
- Full TenantContext dependency and standardized error responses.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

from api.cloudlens_api.tenant_context import get_authenticated_tenant_context
from domain.dashboards.models import (
    ComparisonBasis,
    DashboardPeriodType,
    ExecutiveDashboardResponse,
    ProviderDashboardResponse,
    RoleDefaultLanding,
    ServiceDashboardResponse,
    UserLandingPreference,
)
from domain.dashboards.service import DashboardService, get_dashboard_service
from domain.tenant.context import TenantContext

router = APIRouter(prefix="/api/v1/dashboards", tags=["Dashboards"])


class SetLandingPreferenceRequest(BaseModel):
    """Payload to configure default landing dashboard per role."""

    user_id: str = Field(..., description="Target user identifier")
    role: str = Field(..., description="Role title (e.g. EXECUTIVE, FINOPS, ENGINEERING)")
    landing_dashboard: str = Field(
        ..., description="Target dashboard view (EXECUTIVE, PROVIDER, SERVICE)"
    )
    provider: str | None = Field(
        default=None, description="Default provider if landing is PROVIDER"
    )
    service_id: str | None = Field(
        default=None, description="Default service if landing is SERVICE"
    )


@router.get("/executive", response_model=ExecutiveDashboardResponse, status_code=status.HTTP_200_OK)
async def get_executive_dashboard(
    period_id: str | None = Query(
        default=None, description="Billing period format YYYY-MM or YYYY-QX"
    ),
    period_type: DashboardPeriodType = Query(
        default=DashboardPeriodType.MONTH, description="Period type"
    ),
    comparison_basis: ComparisonBasis = Query(
        default=ComparisonBasis.POP, description="POP or YOY comparison"
    ),
    custom_start: date | None = Query(default=None, description="Start date for custom range"),
    custom_end: date | None = Query(default=None, description="End date for custom range"),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: DashboardService = Depends(get_dashboard_service),
) -> ExecutiveDashboardResponse:
    """Retrieves full Executive Dashboard rendered from pre-computed aggregates (Prompt 37)."""
    return service.get_executive_dashboard(
        tenant_context=tenant_context,
        period_id=period_id,
        period_type=period_type,
        comparison_basis=comparison_basis,
        custom_start=custom_start,
        custom_end=custom_end,
    )


@router.get(
    "/providers/{provider}",
    response_model=ProviderDashboardResponse,
    status_code=status.HTTP_200_OK,
)
async def get_provider_dashboard(
    provider: str,
    period_id: str | None = Query(default=None, description="Billing period"),
    period_type: DashboardPeriodType = Query(default=DashboardPeriodType.MONTH),
    comparison_basis: ComparisonBasis = Query(default=ComparisonBasis.POP),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: DashboardService = Depends(get_dashboard_service),
) -> ProviderDashboardResponse:
    """Retrieves Provider Dashboard strictly rendered in that provider's native vocabulary."""
    try:
        return service.get_provider_dashboard(
            provider=provider,
            tenant_context=tenant_context,
            period_id=period_id,
            period_type=period_type,
            comparison_basis=comparison_basis,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.get(
    "/services/{service_id}",
    response_model=ServiceDashboardResponse,
    status_code=status.HTTP_200_OK,
)
async def get_service_dashboard(
    service_id: str,
    period_id: str | None = Query(default=None, description="Billing period"),
    period_type: DashboardPeriodType = Query(default=DashboardPeriodType.MONTH),
    comparison_basis: ComparisonBasis = Query(default=ComparisonBasis.POP),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: DashboardService = Depends(get_dashboard_service),
) -> ServiceDashboardResponse:
    """Retrieves Service Dashboard with all 16 canonical panels."""
    return service.get_service_dashboard(
        service_id=service_id,
        tenant_context=tenant_context,
        period_id=period_id,
        period_type=period_type,
        comparison_basis=comparison_basis,
    )


@router.get("/landing", response_model=RoleDefaultLanding, status_code=status.HTTP_200_OK)
async def get_role_landing_dashboard(
    user_id: str = Query(default="usr-current-user", description="User ID"),
    role: str = Query(default="EXECUTIVE", description="User active role"),
    service: DashboardService = Depends(get_dashboard_service),
) -> RoleDefaultLanding:
    """Retrieves default landing dashboard configuration for user role."""
    return service.get_role_landing_dashboard(user_id=user_id, role=role)


@router.post("/landing", response_model=UserLandingPreference, status_code=status.HTTP_200_OK)
async def set_user_landing_preference(
    payload: SetLandingPreferenceRequest,
    service: DashboardService = Depends(get_dashboard_service),
) -> UserLandingPreference:
    """Saves user custom default landing dashboard."""
    return service.set_user_landing_preference(
        user_id=payload.user_id,
        role=payload.role,
        landing_dashboard=payload.landing_dashboard,
        provider=payload.provider,
        service_id=payload.service_id,
    )


@router.get("/export/{widget_id}", status_code=status.HTTP_200_OK)
async def export_widget_data(
    widget_id: str,
    format: str = Query(default="CSV", description="Export format: CSV or JSON"),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: DashboardService = Depends(get_dashboard_service),
) -> Response:
    """Exports underlying widget dataset to CSV or JSON format."""
    try:
        content, media_type = service.export_widget_data(
            widget_id=widget_id,
            export_format=format,
            tenant_context=tenant_context,
        )
        ext = "json" if format.upper() == "JSON" else "csv"
        headers = {"Content-Disposition": f'attachment; filename="{widget_id}_export.{ext}"'}
        return Response(content=content, media_type=media_type, headers=headers)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
