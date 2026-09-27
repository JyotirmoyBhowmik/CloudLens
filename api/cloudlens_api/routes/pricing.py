"""CloudLens Pricing Catalogue API Routes (Prompt 20 / Track E / API-028).

Enforces:
- PR-001, PR-002, PR-008, PR-016: Centralised, effective-dated pricing catalogue.
- Historical point-in-time rate resolution with contracted rate precedence.
- Structured Tier, Volume, and Free Allowance representations.
- Pricing variance change detection and audit trails.
- Unknown-SKU gap reporting and tracking.
"""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field

from domain.pricing.models import (
    PointInTimePricingQuery,
    PricingChangeRecord,
    PricingRecord,
    RateType,
    ResolvedPriceQuote,
    UnknownSkuRecord,
)
from domain.pricing.service import PricingCatalogueService, get_pricing_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/pricing", tags=["Pricing Catalogue"])


class PricingCatalogResponse(BaseModel):
    """Paginated response model for pricing catalogue queries."""

    items: list[PricingRecord]
    total: int
    page: int
    page_size: int


class IngestPricingResponse(BaseModel):
    """Response model for pricing record ingestion."""

    record: PricingRecord
    change_signal: PricingChangeRecord | None = None


class ResolveUnknownSkuRequest(BaseModel):
    """Payload to resolve an unknown SKU gap entry."""

    provider: str = Field(..., min_length=1)
    service_sku: str = Field(..., min_length=1)
    resolved_pricing_id: str = Field(..., min_length=1)
    notes: str | None = None


@router.get("/catalog", response_model=PricingCatalogResponse, status_code=status.HTTP_200_OK)
async def list_pricing_catalog(
    provider: str | None = Query(
        default=None, description="Cloud provider filter (aws, azure, gcp, oci)"
    ),
    service: str | None = Query(default=None, description="Service name substring filter"),
    sku: str | None = Query(default=None, description="Service SKU code substring filter"),
    region: str | None = Query(default=None, description="Datacenter region filter"),
    dimension: str | None = Query(
        default=None, description="Pricing dimension code filter (e.g. DIM-03)"
    ),
    rate_type: RateType | None = Query(
        default=None, description="Rate type filter (LIST, CONTRACTED)"
    ),
    effective_date: datetime | None = Query(
        default=None,
        description="Historical point-in-time filter; if omitted returns current active records",
    ),
    include_historical: bool = Query(
        default=False,
        description="Whether to include superseded historical SCD Type 2 versions",
    ),
    page: int = Query(default=1, ge=1, description="Page index"),
    page_size: int = Query(default=50, ge=1, le=200, description="Items per page"),
    service_engine: PricingCatalogueService = Depends(get_pricing_service),
) -> PricingCatalogResponse:
    """Lists pricing catalogue records with multi-dimensional filtering and point-in-time support."""
    items, total = service_engine.list_catalog(
        provider=provider,
        service=service,
        sku=sku,
        region=region,
        dimension=dimension,
        rate_type=rate_type,
        effective_date=effective_date,
        include_historical=include_historical,
        page=page,
        page_size=page_size,
    )
    return PricingCatalogResponse(items=items, total=total, page=page, page_size=page_size)


@router.post("/resolve", response_model=ResolvedPriceQuote, status_code=status.HTTP_200_OK)
async def resolve_pricing_rate(
    query: PointInTimePricingQuery,
    service_engine: PricingCatalogueService = Depends(get_pricing_service),
) -> ResolvedPriceQuote:
    """Evaluates the exact effective rate for an organisation on a specific past or current date.

    Where a contracted or negotiated rate exists, list rate is NEVER presented as
    the organisation's rate, but both are retained to verify realized discount.
    """
    return service_engine.resolve_price_at_date(
        provider=query.provider,
        service_sku=query.service_sku,
        service=query.service,
        region=query.region,
        pricing_dimension=query.pricing_dimension,
        query_date=query.query_date,
        tenant_id=query.tenant_id,
        prefer_contracted=query.prefer_contracted,
    )


@router.post("/records", response_model=IngestPricingResponse, status_code=status.HTTP_201_CREATED)
async def ingest_pricing_record(
    record: PricingRecord,
    service_engine: PricingCatalogueService = Depends(get_pricing_service),
) -> IngestPricingResponse:
    """Ingests a pricing record following SCD Type 2 rules.

    Emits a Pricing Change Signal if the rate has changed relative to the previous version.
    """
    stored_rec, change = service_engine.ingest_price_record(record)
    return IngestPricingResponse(record=stored_rec, change_signal=change)


@router.get("/changes", response_model=list[PricingChangeRecord], status_code=status.HTTP_200_OK)
async def list_pricing_changes(
    provider: str | None = Query(default=None, description="Provider filter"),
    sku: str | None = Query(default=None, description="SKU filter"),
    since: datetime | None = Query(default=None, description="Changes detected after timestamp"),
    service_engine: PricingCatalogueService = Depends(get_pricing_service),
) -> list[PricingChangeRecord]:
    """Retrieves detected rate change records and variance audits."""
    return service_engine.list_pricing_changes(provider=provider, sku=sku, since=since)


@router.get("/unknown-skus", response_model=list[UnknownSkuRecord], status_code=status.HTTP_200_OK)
async def list_unknown_skus(
    provider: str | None = Query(default=None, description="Provider filter"),
    status_filter: str | None = Query(
        default=None, alias="status", description="UNRESOLVED or RESOLVED"
    ),
    service_engine: PricingCatalogueService = Depends(get_pricing_service),
) -> list[UnknownSkuRecord]:
    """Retrieves unknown SKU gap reports generated by the ingestion pipeline."""
    return service_engine.list_unknown_skus(provider=provider, status=status_filter)


@router.post(
    "/unknown-skus/resolve",
    response_model=UnknownSkuRecord | None,
    status_code=status.HTTP_200_OK,
)
async def resolve_unknown_sku(
    payload: ResolveUnknownSkuRequest,
    service_engine: PricingCatalogueService = Depends(get_pricing_service),
) -> UnknownSkuRecord | None:
    """Manually marks an unknown SKU gap entry as resolved to a pricing catalogue record."""
    return service_engine.repository.mark_unknown_sku_resolved(
        provider=payload.provider,
        service_sku=payload.service_sku,
        resolved_pricing_id=payload.resolved_pricing_id,
        notes=payload.notes,
    )
