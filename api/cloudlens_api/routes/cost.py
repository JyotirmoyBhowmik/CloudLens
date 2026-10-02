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
from pydantic import BaseModel, ConfigDict, Field

from api.cloudlens_api.conventions.filtering import decode_cursor, encode_cursor
from api.cloudlens_api.conventions.models import ResponseMetadata
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
from domain.cost.reconciliation import (
    CostReconciliationEngine,
    EstimateVsActualItem,
    EstimateVsActualReport,
    ExecutiveTrustIndicator,
    InvestigationStatus,
    ReconciliationHistorySummary,
    ReconciliationInvestigationItem,
    ReconciliationReport,
    ReconciliationRepository,
    ReconciliationStatus,
    RunReconciliationRequest,
    get_cost_reconciliation_engine,
    get_reconciliation_repository,
)
from domain.cost.repository import CostFactRepository, get_cost_repository
from domain.models.enums import ChargeCategory
from domain.models.exceptions import (
    ReconciliationReportNotFoundException,
)
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


# ==============================================================================
# Cost Reconciliation & Executive Trust Endpoints (Prompt 24)
# ==============================================================================


class UpdateInvestigationRequest(BaseModel):
    """Payload to update investigation status and auditor notes."""

    status: InvestigationStatus
    notes: str | None = None


class EvaluateEstimateVsActualRequest(BaseModel):
    """Payload to evaluate pre-deployment estimates against actual FOCUS billed costs."""

    billing_period: str = Field(
        ..., min_length=7, max_length=7, description="Billing period YYYY-MM"
    )
    estimates: list[dict[str, Any]] = Field(
        ..., min_length=1, description="List of pre-deployment estimates"
    )


class AdjustCostFactRequest(BaseModel):
    """Payload attempting to adjust cost data (strictly forbidden by Prompt 24)."""

    cost_fact_id: str = Field(..., min_length=1, description="Cost fact ID")
    adjusted_amount: Decimal = Field(..., description="Target adjusted amount")


@router.post(
    "/reconciliation/run",
    response_model=ReconciliationReport,
    status_code=status.HTTP_200_OK,
)
async def run_cost_reconciliation(
    request: RunReconciliationRequest,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    engine: CostReconciliationEngine = Depends(get_cost_reconciliation_engine),
) -> ReconciliationReport:
    """Executes period reconciliation comparing platform normalised total against authoritative provider total.

    Enforces finalisation lag check, tolerance evaluation, deterministic variance classification,
    and non-editorialised framing statement.
    """
    return engine.run_reconciliation(request, tenant_context=tenant_context)


@router.get(
    "/reconciliation/reports",
    response_model=list[ReconciliationReport],
    status_code=status.HTTP_200_OK,
)
async def list_reconciliation_reports(
    billing_period: str | None = Query(default=None, description="Billing period format YYYY-MM"),
    provider: str | None = Query(default=None, description="Cloud provider identifier"),
    scope_id: str | None = Query(default=None, description="Scope identifier"),
    recon_status: ReconciliationStatus | None = Query(
        default=None, alias="status", description="Filter by PASS or FAILED"
    ),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    repository: ReconciliationRepository = Depends(get_reconciliation_repository),
) -> list[ReconciliationReport]:
    """Lists reconciliation audit reports for tenant with optional filters."""
    filters = {
        "billing_period": billing_period,
        "provider": provider,
        "scope_id": scope_id,
        "status": recon_status,
    }
    return repository.list(
        tenant_context=tenant_context,
        filter_params=filters,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/reconciliation/reports/{report_id}",
    response_model=ReconciliationReport,
    status_code=status.HTTP_200_OK,
)
async def get_reconciliation_report(
    report_id: str,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    repository: ReconciliationRepository = Depends(get_reconciliation_repository),
) -> ReconciliationReport:
    """Retrieves a single reconciliation report by ID.

    Returns 404 if report is not found.
    """
    report = repository.get(report_id, tenant_context=tenant_context)
    if not report:
        raise ReconciliationReportNotFoundException(report_id)
    return report


@router.get(
    "/reconciliation/executive-trust",
    response_model=ExecutiveTrustIndicator,
    status_code=status.HTTP_200_OK,
)
async def get_executive_trust_indicator(
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    engine: CostReconciliationEngine = Depends(get_cost_reconciliation_engine),
) -> ExecutiveTrustIndicator:
    """Surfaces the executive adoption trust indicator.

    Single most important number for platform credibility.
    STRICT: Failed reconciliations are NEVER suppressed from this metric.
    """
    return engine.compute_executive_trust_indicator(tenant_context=tenant_context)


@router.get(
    "/reconciliation/investigations",
    response_model=list[ReconciliationInvestigationItem],
    status_code=status.HTTP_200_OK,
)
async def list_reconciliation_investigations(
    investigation_status: InvestigationStatus | None = Query(
        default=None, alias="status", description="Investigation status filter"
    ),
    provider: str | None = Query(default=None, description="Provider filter"),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    repository: ReconciliationRepository = Depends(get_reconciliation_repository),
) -> list[ReconciliationInvestigationItem]:
    """Lists reconciliation investigation items raised when tolerance failed."""
    return repository.list_investigation_items(
        tenant_context=tenant_context,
        status=investigation_status,
        provider=provider,
    )


@router.patch(
    "/reconciliation/investigations/{item_id}",
    response_model=ReconciliationInvestigationItem,
    status_code=status.HTTP_200_OK,
)
async def update_reconciliation_investigation(
    item_id: str,
    body: UpdateInvestigationRequest,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    repository: ReconciliationRepository = Depends(get_reconciliation_repository),
) -> ReconciliationInvestigationItem:
    """Updates investigation item lifecycle status and auditor investigation notes."""
    return repository.update_investigation_item(
        item_id=item_id,
        status=body.status,
        notes=body.notes,
        tenant_context=tenant_context,
    )


@router.get(
    "/reconciliation/history",
    response_model=ReconciliationHistorySummary,
    status_code=status.HTTP_200_OK,
)
async def get_reconciliation_history(
    provider: str | None = Query(default=None, description="Optional provider filter"),
    scope_id: str | None = Query(default=None, description="Optional scope filter"),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    engine: CostReconciliationEngine = Depends(get_cost_reconciliation_engine),
) -> ReconciliationHistorySummary:
    """Returns chronological reconciliation history and variance trend direction."""
    return engine.get_reconciliation_history_trend(
        tenant_context=tenant_context,
        provider=provider,
        scope_id=scope_id,
    )


@router.post(
    "/reconciliation/estimate-vs-actual/evaluate",
    response_model=EstimateVsActualReport,
    status_code=status.HTTP_200_OK,
)
async def evaluate_estimate_accuracy(
    payload: EvaluateEstimateVsActualRequest,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    engine: CostReconciliationEngine = Depends(get_cost_reconciliation_engine),
) -> EstimateVsActualReport:
    """Evaluates pre-deployment estimates against actual billed FOCUS costs.

    Separate from platform-vs-provider reconciliation to evaluate platform estimation accuracy.
    """
    return engine.evaluate_estimate_vs_actual(
        billing_period=payload.billing_period,
        estimates=payload.estimates,
        tenant_context=tenant_context,
    )


@router.get(
    "/reconciliation/estimate-vs-actual",
    response_model=list[EstimateVsActualItem],
    status_code=status.HTTP_200_OK,
)
async def list_estimate_vs_actual_items(
    billing_period: str | None = Query(default=None, description="Billing period format YYYY-MM"),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    repository: ReconciliationRepository = Depends(get_reconciliation_repository),
) -> list[EstimateVsActualItem]:
    """Lists line-by-line estimate vs actual comparison items."""
    return repository.list_estimate_vs_actual(
        tenant_context=tenant_context,
        billing_period=billing_period,
    )


@router.post(
    "/reconciliation/adjust-fact",
    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
)
async def adjust_cost_fact_for_match(
    payload: AdjustCostFactRequest,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    engine: CostReconciliationEngine = Depends(get_cost_reconciliation_engine),
) -> None:
    """Strictly forbidden endpoint demonstrating enforcement of Prompt 24 negative constraint.

    'Do not adjust ingested cost data to force a match.'
    Always raises ReconciliationAdjustmentForbiddenException.
    """
    engine.adjust_cost_data_for_match(
        cost_fact_id=payload.cost_fact_id,
        tenant_context=tenant_context,
    )


# ==============================================================================
# Public API Surface Additions (API-024 through API-027 / Prompt 34)
# ==============================================================================


class CostTimeSeriesPoint(BaseModel):
    """Single point in a cost time series."""

    date: str
    dimension_value: str
    billed_cost: str
    effective_cost: str
    currency: str = "USD"


class CostTimeSeriesResponse(BaseModel):
    """Daily/monthly cost time series response (API-024)."""

    model_config = ConfigDict(populate_by_name=True)

    items: list[CostTimeSeriesPoint]
    total: int
    metadata: ResponseMetadata = Field(default_factory=ResponseMetadata, alias="_metadata")


class CostBreakdownSlice(BaseModel):
    """Single dimension category in a cost distribution."""

    dimension_value: str
    amount: str
    percentage: str
    currency: str = "USD"


class CostBreakdownResponse(BaseModel):
    """Cost breakdown distribution response (API-025)."""

    model_config = ConfigDict(populate_by_name=True)

    dimension: str
    total_cost: str
    slices: list[CostBreakdownSlice]
    currency: str = "USD"
    metadata: ResponseMetadata = Field(default_factory=ResponseMetadata, alias="_metadata")


class CostLineItemsResponse(BaseModel):
    """Paginated underlying FOCUS cost charge lines (API-026)."""

    model_config = ConfigDict(populate_by_name=True)

    items: list[dict[str, Any]]
    total: int
    next_cursor: str | None = None
    limit: int = 50
    metadata: ResponseMetadata = Field(default_factory=ResponseMetadata, alias="_metadata")


class CostReconciliationSummaryResponse(BaseModel):
    """Reconciled closed-period variance reports response (API-027)."""

    model_config = ConfigDict(populate_by_name=True)

    reports: list[ReconciliationReport]
    executive_trust: ExecutiveTrustIndicator | None = None
    total: int
    metadata: ResponseMetadata = Field(default_factory=ResponseMetadata, alias="_metadata")


@router.get("/timeseries", response_model=CostTimeSeriesResponse, status_code=status.HTTP_200_OK)
async def get_cost_timeseries(
    scope_id: str | None = Query(default=None, description="Scope filter"),
    dimension: str = Query(
        default="provider", description="Dimension to group by (provider, service, scope)"
    ),
    granularity: str = Query(default="DAILY", description="DAILY or MONTHLY"),
    billing_period: str | None = Query(default=None, description="Billing period (YYYY-MM)"),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    repository: CostFactRepository = Depends(get_cost_repository),
) -> CostTimeSeriesResponse:
    """Returns daily/monthly cost time series by scope and dimension (API-024)."""
    facts = repository.get_all_facts(tenant_context=tenant_context)
    points_map: dict[tuple[str, str], tuple[Decimal, Decimal]] = {}

    for f in facts:
        if scope_id and f.scope_id != scope_id:
            continue
        dt_str = f.charge_period_start.strftime("%Y-%m-%d" if granularity == "DAILY" else "%Y-%m")
        dim_val = getattr(f, dimension, None) or f.provider or "unknown"
        key = (dt_str, str(dim_val))
        prev_billed, prev_effective = points_map.get(key, (Decimal("0.00"), Decimal("0.00")))
        billed_dec = f.billed_cost.value_or(Decimal("0.00"))
        effective_dec = f.effective_cost.value_or(Decimal("0.00"))
        points_map[key] = (prev_billed + billed_dec, prev_effective + effective_dec)

    items = [
        CostTimeSeriesPoint(
            date=k[0],
            dimension_value=k[1],
            billed_cost=str(v[0]),
            effective_cost=str(v[1]),
            currency="USD",
        )
        for k, v in sorted(points_map.items())
    ]
    return CostTimeSeriesResponse(
        items=items,
        total=len(items),
        _metadata=ResponseMetadata(period=billing_period),
    )


@router.get("/breakdown", response_model=CostBreakdownResponse, status_code=status.HTTP_200_OK)
async def get_cost_breakdown(
    by: str = Query(
        default="provider", description="Breakdown dimension: provider, service, application, owner"
    ),
    billing_period: str | None = Query(default=None, description="Billing period format YYYY-MM"),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    repository: CostFactRepository = Depends(get_cost_repository),
) -> CostBreakdownResponse:
    """Returns cost distribution by provider, service, application, or owner (API-025)."""
    facts = repository.get_all_facts(tenant_context=tenant_context)
    breakdown_map: dict[str, Decimal] = {}
    total_spend = Decimal("0.00")

    attr_name = "service_name" if by == "service" else by
    for f in facts:
        val = getattr(f, attr_name, None) or getattr(f, by, None) or f.provider or "Unallocated"
        val_str = str(val)
        cost = f.effective_cost.value_or(Decimal("0.00"))
        breakdown_map[val_str] = breakdown_map.get(val_str, Decimal("0.00")) + cost
        total_spend += cost

    slices: list[CostBreakdownSlice] = []
    for k, v in sorted(breakdown_map.items(), key=lambda x: x[1], reverse=True):
        pct = (
            (v / total_spend * Decimal("100.0")).quantize(Decimal("0.01"))
            if total_spend > Decimal("0.00")
            else Decimal("0.00")
        )
        slices.append(
            CostBreakdownSlice(
                dimension_value=k,
                amount=str(v),
                percentage=f"{pct}%",
                currency="USD",
            )
        )

    return CostBreakdownResponse(
        dimension=by,
        total_cost=str(total_spend),
        slices=slices,
        currency="USD",
        _metadata=ResponseMetadata(period=billing_period),
    )


@router.get("/line-items", response_model=CostLineItemsResponse, status_code=status.HTTP_200_OK)
async def list_cost_line_items(
    scope_id: str | None = Query(default=None, description="Scope filter"),
    provider: str | None = Query(default=None, description="Provider filter"),
    service_name: str | None = Query(default=None, description="Service name filter"),
    billing_period: str | None = Query(default=None, description="Billing period (YYYY-MM)"),
    limit: int = Query(default=50, ge=1, le=500, description="Page limit"),
    cursor: str | None = Query(default=None, description="Pagination cursor"),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    repository: CostFactRepository = Depends(get_cost_repository),
) -> CostLineItemsResponse:
    """Returns paginated underlying FOCUS cost charge lines (API-026)."""
    offset = decode_cursor(cursor)
    all_facts = repository.get_all_facts(tenant_context=tenant_context)

    filtered: list[dict[str, Any]] = []
    for f in all_facts:
        if scope_id and f.scope_id != scope_id:
            continue
        if provider and f.provider.lower() != provider.lower():
            continue
        if service_name and f.service_name and service_name.lower() not in f.service_name.lower():
            continue
        filtered.append(f.model_dump())

    total = len(filtered)
    sliced = filtered[offset : offset + limit]
    next_cursor = encode_cursor(offset + limit) if (offset + limit) < total else None

    return CostLineItemsResponse(
        items=sliced,
        total=total,
        next_cursor=next_cursor,
        limit=limit,
        _metadata=ResponseMetadata(period=billing_period),
    )


@router.get(
    "/reconciliation",
    response_model=CostReconciliationSummaryResponse,
    status_code=status.HTTP_200_OK,
)
async def get_cost_reconciliation_summary(
    billing_period: str | None = Query(default=None, description="Billing period format YYYY-MM"),
    provider: str | None = Query(default=None, description="Provider filter"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    engine: CostReconciliationEngine = Depends(get_cost_reconciliation_engine),
    repository: ReconciliationRepository = Depends(get_reconciliation_repository),
) -> CostReconciliationSummaryResponse:
    """Returns reconciled closed-period variance reports and trust indicator (API-027)."""
    reports = repository.list(
        tenant_context=tenant_context,
        filter_params={"billing_period": billing_period, "provider": provider},
        limit=limit,
        offset=offset,
    )
    trust = engine.compute_executive_trust_indicator(tenant_context=tenant_context)
    return CostReconciliationSummaryResponse(
        reports=reports,
        executive_trust=trust,
        total=len(reports),
        _metadata=ResponseMetadata(period=billing_period),
    )
