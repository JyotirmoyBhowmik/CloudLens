"""Analytics Export, BI Feed & Semantic Layer REST API Endpoints (Prompt 56).

Enforces:
- Full TenantContext validation on all routes.
- Triggering and tracking scheduled/ad-hoc analytical extracts with manifest verification.
- Isolated read-only analytical query path (rate-limited, strictly decoupled from OLTP).
- Access to semantic data dictionary, FOCUS mapping table, and reference monthly cost pack.
- Standard response metadata envelope and enterprise error responses.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field

from api.cloudlens_api.conventions.models import ResponseMetadata
from api.cloudlens_api.tenant_context import get_authenticated_tenant_context
from domain.analytics.models import (
    AnalyticalExtractManifest,
    AnalyticalQueryRequest,
    AnalyticalQueryResponse,
    AnalyticsExtractJob,
    SemanticDataDictionaryField,
)
from domain.analytics.service import AnalyticsService, get_analytics_service
from domain.models.exceptions import (
    AnalyticsExtractNotFoundException,
    AnalyticsRateLimitExceededException,
    EmptyExtractException,
    TransactionalPathAccessForbiddenException,
)
from domain.tenant.context import TenantContext

router = APIRouter(prefix="/api/v1/analytics", tags=["Analytics & Semantic Layer"])


class TriggerExtractRequest(BaseModel):
    """Payload to trigger an analytical extract."""

    period: str = Field(..., description="Target billing period partition, e.g. '2026-09'")
    service_identity_id: str = Field(
        default="svc-finance-bi",
        description="Declared service principal or machine identity",
    )
    service_identity_name: str = Field(
        default="Enterprise PowerBI / Databricks Feed",
        description="Friendly title of service identity",
    )
    scope_grants: list[str] = Field(
        default_factory=lambda: ["*"],
        description="Authorized scope grants binding this extract run",
    )
    is_restatement: bool = Field(
        default=False,
        description="Set to true if this run re-emits a corrected historical period",
    )


class ExtractListResponse(BaseModel):
    """List of analytical extracts."""

    extracts: list[AnalyticsExtractJob]
    total_count: int
    metadata: ResponseMetadata = Field(default_factory=ResponseMetadata, alias="_metadata")


@router.post("/extracts", response_model=AnalyticsExtractJob, status_code=status.HTTP_202_ACCEPTED)
def trigger_analytical_extract(
    payload: TriggerExtractRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: AnalyticsService = Depends(get_analytics_service),
) -> AnalyticsExtractJob:
    """Triggers generation of a partitioned analytical extract with conformed dimensions and manifest."""
    _ = idempotency_key
    try:
        job, _ = service.run_extract(
            period=payload.period,
            service_identity_id=payload.service_identity_id,
            service_identity_name=payload.service_identity_name,
            scope_grants=payload.scope_grants,
            tenant_context=tenant_context,
            is_restatement=payload.is_restatement,
        )
        return job
    except EmptyExtractException as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.get("/extracts", response_model=ExtractListResponse)
def list_analytical_extracts(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: AnalyticsService = Depends(get_analytics_service),
) -> ExtractListResponse:
    """Lists analytical extract execution history for the authenticated tenant."""
    jobs = service.list_extracts(tenant_context=tenant_context, limit=limit, offset=offset)
    total = len(service.list_extracts(tenant_context=tenant_context, limit=5000, offset=0))
    return ExtractListResponse(
        extracts=jobs,
        total_count=total,
        _metadata=ResponseMetadata(),
    )


@router.get("/extracts/{extract_id}", response_model=AnalyticsExtractJob)
def get_analytical_extract(
    extract_id: str,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: AnalyticsService = Depends(get_analytics_service),
) -> AnalyticsExtractJob:
    """Retrieves metadata for a specific analytical extract execution."""
    try:
        return service.get_extract(extract_id, tenant_context=tenant_context)
    except AnalyticsExtractNotFoundException as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/extracts/{extract_id}/manifest", response_model=AnalyticalExtractManifest)
def get_extract_manifest(
    extract_id: str,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: AnalyticsService = Depends(get_analytics_service),
) -> AnalyticalExtractManifest:
    """Retrieves the authoritative cryptographic manifest for an analytical extract."""
    try:
        return service.get_manifest(extract_id, tenant_context=tenant_context)
    except AnalyticsExtractNotFoundException as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/query", response_model=AnalyticalQueryResponse)
def execute_analytical_query(
    request: AnalyticalQueryRequest,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: AnalyticsService = Depends(get_analytics_service),
) -> AnalyticalQueryResponse:
    """Executes a multi-dimensional query against the isolated read-only analytical semantic layer."""
    try:
        return service.execute_query(request, tenant_context=tenant_context)
    except TransactionalPathAccessForbiddenException as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except AnalyticsRateLimitExceededException as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc


@router.get("/dictionary", response_model=list[SemanticDataDictionaryField])
def get_data_dictionary(
    service: AnalyticsService = Depends(get_analytics_service),
) -> list[SemanticDataDictionaryField]:
    """Returns the published Semantic Layer Data Dictionary."""
    return service.get_data_dictionary()


@router.get("/reference/cost-pack")
def get_reference_monthly_cost_pack(
    period: str = Query(default="2026-09", description="Billing period, e.g. 2026-09"),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: AnalyticsService = Depends(get_analytics_service),
) -> dict[str, Any]:
    """Generates the reference monthly cost pack from the semantic layer without touching OLTP."""
    return service.get_reference_monthly_cost_pack(tenant_context=tenant_context, period=period)


@router.get("/reference/focus-mapping")
def get_semantic_to_focus_mapping(
    service: AnalyticsService = Depends(get_analytics_service),
) -> list[dict[str, str]]:
    """Returns the mapping table from CloudLens Semantic Layer to FinOps FOCUS 1.0."""
    return service.get_semantic_to_focus_mapping()
