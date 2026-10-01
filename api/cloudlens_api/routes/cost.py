"""CloudLens FOCUS Cost Ingestion, Normalisation, Restatement, and Currency Routes (Prompt 22 / Track E).

Enforces:
- CST-001, CST-002, CST-003, CST-004, CST-008, CST-012, FR-802, FR-803.
- Ingestion of bulk provider billing data with atomic partition replacement.
- Direct FOCUS mapping retaining billed, effective, list, and contracted costs.
- Restatement detection, prior values retention, and audit trail retrieval.
- 4-step drill-through hierarchy governed by financial-detail RBAC.
- Query-time currency conversion with mandatory disclosure text.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field

from api.cloudlens_api.tenant_context import get_authenticated_tenant_context
from domain.cost.calculation import (
    PreDeploymentEstimateRequest,
    PreDeploymentEstimateResult,
    PreDeploymentEstimator,
    get_pre_deployment_estimator,
)
from domain.cost.currency_service import (
    CurrencyConversionService,
    get_currency_service,
)
from domain.cost.models import (
    ConvertedCostFigure,
    CostAggregateNode,
    CostPresentationBasis,
    CostRestatementRecord,
    IngestionJobResult,
)
from domain.cost.pipeline import CostIngestionPipeline, get_cost_pipeline
from domain.cost.repository import CostFactRepository, get_cost_repository
from domain.models.enums import ChargeCategory
from domain.pricing.traceability import FreshnessIndicator
from domain.tenant.context import TenantContext

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/cost", tags=["Cost Ingestion & FOCUS"])


class CostSummaryResponse(BaseModel):
    """Consolidated cost summary for tenant and billing period."""

    billing_period: str | None
    row_count: int
    presentation_basis: CostPresentationBasis
    billed_cost: ConvertedCostFigure
    effective_cost: ConvertedCostFigure
    list_cost: ConvertedCostFigure | None = None
    contracted_cost: ConvertedCostFigure | None = None
    realised_discount_value: ConvertedCostFigure | None = None
    freshness: FreshnessIndicator


class BulkCostIngestRequest(BaseModel):
    """Payload to trigger bulk cost ingestion."""

    provider: str = Field(..., min_length=1, description="Cloud provider identifier")
    schema_version: str = Field(..., min_length=1, description="Dataset schema version")
    scope_id: str = Field(..., min_length=1, description="Target scope identifier")
    records: list[dict[str, Any]] = Field(..., min_length=1, description="Raw billing line items")
    lookback_window_months: int = Field(
        default=3, ge=1, le=12, description="Restatement lookback window"
    )


@router.post("/ingest", response_model=IngestionJobResult, status_code=status.HTTP_201_CREATED)
async def ingest_cost_dataset(
    payload: BulkCostIngestRequest,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    pipeline: CostIngestionPipeline = Depends(get_cost_pipeline),
) -> IngestionJobResult:
    """Ingests provider billing dataset, normalises to FOCUS, and replaces partitions atomically."""
    return pipeline.execute_bulk_ingestion(
        dataset=payload.records,
        provider=payload.provider,
        schema_version=payload.schema_version,
        scope_id=payload.scope_id,
        tenant_context=tenant_context,
        lookback_months=payload.lookback_window_months,
    )


@router.get("/summary", response_model=CostSummaryResponse, status_code=status.HTTP_200_OK)
async def get_cost_summary(
    billing_period: str | None = Query(default=None, description="Billing period format YYYY-MM"),
    target_currency: str = Query(
        default="USD", min_length=3, max_length=3, description="Target currency"
    ),
    presentation_basis: CostPresentationBasis = Query(
        default=CostPresentationBasis.BILLED, description="BILLED or AMORTISED basis"
    ),
    scope_id: str | None = Query(default=None, description="Scope ID filter"),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    repository: CostFactRepository = Depends(get_cost_repository),
    pipeline: CostIngestionPipeline = Depends(get_cost_pipeline),
    currency_service: CurrencyConversionService = Depends(get_currency_service),
) -> CostSummaryResponse:
    """Returns aggregated cost metrics with query-time currency conversion and basis disclosure."""
    facts = repository.get_all_facts(
        tenant_context=tenant_context,
        billing_period=billing_period,
        scope_id=scope_id,
    )

    billed_sum = sum(
        (f.billed_cost.value for f in facts if f.billed_cost.is_present), Decimal("0.0")
    )
    effective_sum = sum(
        (f.effective_cost.value for f in facts if f.effective_cost.is_present), Decimal("0.0")
    )
    list_sum = sum(
        (f.list_cost.value for f in facts if f.list_cost and f.list_cost.is_present),
        Decimal("0.0"),
    )
    contracted_sum = sum(
        (
            f.contracted_cost.value
            for f in facts
            if f.contracted_cost and f.contracted_cost.is_present
        ),
        Decimal("0.0"),
    )
    discount_sum = sum(
        (
            f.realised_discount_value.value
            for f in facts
            if f.realised_discount_value and f.realised_discount_value.is_present
        ),
        Decimal("0.0"),
    )

    native_currency = facts[0].billing_currency if facts else "USD"

    conv_billed = currency_service.convert_at_query_time(
        amount=round(billed_sum, 2),
        from_currency=native_currency,
        to_currency=target_currency,
        presentation_basis=presentation_basis,
    )
    conv_effective = currency_service.convert_at_query_time(
        amount=round(effective_sum, 2),
        from_currency=native_currency,
        to_currency=target_currency,
        presentation_basis=presentation_basis,
    )
    conv_list = (
        currency_service.convert_at_query_time(
            amount=round(list_sum, 2),
            from_currency=native_currency,
            to_currency=target_currency,
            presentation_basis=presentation_basis,
        )
        if any(f.list_cost and f.list_cost.is_present for f in facts)
        else None
    )

    conv_contracted = (
        currency_service.convert_at_query_time(
            amount=round(contracted_sum, 2),
            from_currency=native_currency,
            to_currency=target_currency,
            presentation_basis=presentation_basis,
        )
        if any(f.contracted_cost and f.contracted_cost.is_present for f in facts)
        else None
    )

    conv_discount = (
        currency_service.convert_at_query_time(
            amount=round(discount_sum, 2),
            from_currency=native_currency,
            to_currency=target_currency,
            presentation_basis=presentation_basis,
        )
        if any(f.realised_discount_value and f.realised_discount_value.is_present for f in facts)
        else None
    )

    freshness = pipeline.get_freshness_marker(tenant_context.tenant_id)

    return CostSummaryResponse(
        billing_period=billing_period,
        row_count=len(facts),
        presentation_basis=presentation_basis,
        billed_cost=conv_billed,
        effective_cost=conv_effective,
        list_cost=conv_list,
        contracted_cost=conv_contracted,
        realised_discount_value=conv_discount,
        freshness=freshness,
    )


@router.get(
    "/restatements", response_model=list[CostRestatementRecord], status_code=status.HTTP_200_OK
)
async def list_cost_restatements(
    provider: str | None = Query(default=None, description="Cloud provider filter"),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    repository: CostFactRepository = Depends(get_cost_repository),
) -> list[CostRestatementRecord]:
    """Retrieves detected cost restatement audit logs for tenant."""
    return repository.list_restatements(
        tenant_context=tenant_context,
        provider=provider,
    )


@router.get("/drill-through", response_model=CostAggregateNode, status_code=status.HTTP_200_OK)
async def drill_through_cost(
    billing_period: str | None = Query(default=None, description="Billing period (YYYY-MM)"),
    scope_id: str | None = Query(default=None, description="Level 1 filter: Scope ID"),
    service_id: str | None = Query(default=None, description="Level 2 filter: Service ID"),
    charge_category: ChargeCategory | None = Query(
        default=None, description="Level 3 filter: Charge Category"
    ),
    has_financial_permission: bool = Query(
        default=True, description="RBAC check for financial-detail permission"
    ),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    repository: CostFactRepository = Depends(get_cost_repository),
) -> CostAggregateNode:
    """Executes hierarchical drill-down from aggregate to individual charge lines.

    Level 4 access requires financial detail permissions; otherwise returns 403 Forbidden.
    """
    return repository.drill_down(
        tenant_context=tenant_context,
        scope_id=scope_id,
        service_id=service_id,
        charge_category=charge_category,
        billing_period=billing_period,
        has_financial_permission=has_financial_permission,
    )


@router.post(
    "/estimate",
    response_model=PreDeploymentEstimateResult,
    status_code=status.HTTP_200_OK,
)
async def calculate_pre_deployment_estimate(
    request: PreDeploymentEstimateRequest,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    estimator: PreDeploymentEstimator = Depends(get_pre_deployment_estimator),
) -> PreDeploymentEstimateResult:
    """Calculates pre-deployment estimated costs ('What will this cost?') across time horizons (Prompt 23).

    Produces hourly, daily, monthly, and annualised costs with cost-driver decomposition
    and full derivation.
    """
    # Inherit tenant scope if not explicitly overridden
    effective_req = request.model_copy(
        update={"tenant_id": request.tenant_id or tenant_context.tenant_id}
    )
    return estimator.estimate(effective_req)


@router.get(
    "/estimate/supported-services",
    status_code=status.HTTP_200_OK,
)
async def get_estimate_supported_services(
    _tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> dict[str, Any]:
    """Returns supported cloud providers, core services, and default configurations."""
    return {
        "providers": ["aws", "azure", "gcp", "oci"],
        "core_categories": ["COMPUTE", "DATABASE", "OBJECT_STORAGE", "BLOCK_STORAGE"],
        "services": {
            "aws": ["AmazonEC2", "AmazonRDS", "AmazonS3", "AmazonEBS"],
            "azure": ["Virtual Machines", "Azure SQL Database", "Blob Storage", "Managed Disks"],
            "gcp": ["Compute Engine", "Cloud SQL", "Cloud Storage", "Persistent Disk"],
            "oci": ["Compute", "Base Database Service", "Object Storage", "Block Volume"],
        },
        "extensible": True,
    }
