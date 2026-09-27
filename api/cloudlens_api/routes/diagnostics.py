"""CloudLens Connector Diagnostics and Failure Recovery API Routes (Prompt 15 Items 104, 105).

Enforces:
- Prompt 15 Item 104: Per-capability attempt, success, verbatim error, explanation, lag, headroom.
- Prompt 15 Item 105: Outage gap analysis and checkpoint resumption.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from api.cloudlens_api.tenant_context import get_authenticated_tenant_context
from connectors.diagnostics.service import get_diagnostics_service
from domain.diagnostics.models import ConnectorDiagnosticReport, OutageGapReport
from domain.models.enums import ConnectorCapability
from domain.tenant.context import TenantContext

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/connectors", tags=["Connector Diagnostics"])


class ResumeFromCheckpointRequest(BaseModel):
    capability: ConnectorCapability = Field(
        default=ConnectorCapability.DISCOVER_RESOURCES,
        description="Capability to resume from continuation token",
    )


@router.get("/{connector_id}/diagnostics", response_model=ConnectorDiagnosticReport)
async def get_connector_diagnostics(
    connector_id: str,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> ConnectorDiagnosticReport:
    """Returns detailed per-capability diagnostics, freshness lag, and quota headroom (Item 104)."""
    service = get_diagnostics_service()
    return service.get_diagnostics(connector_id=connector_id, tenant_context=tenant_context)


@router.get("/{connector_id}/outage-gap-report", response_model=OutageGapReport)
async def get_outage_gap_report(
    connector_id: str,
    outage_start: datetime | None = Query(
        default=None, description="Optional start timestamp of outage"
    ),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> OutageGapReport:
    """Analyzes downtime and identifies uncollected data periods and scopes for backfill (Item 105)."""
    service = get_diagnostics_service()
    return service.generate_outage_gap_report(
        connector_id=connector_id,
        outage_start=outage_start,
        tenant_context=tenant_context,
    )


@router.post("/{connector_id}/resume")
async def resume_connector_sync(
    connector_id: str,
    payload: ResumeFromCheckpointRequest,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> dict[str, Any]:
    """Resumes interrupted sync from continuation token checkpoint (Item 105)."""
    service = get_diagnostics_service()
    return await service.resume_from_checkpoint(
        connector_id=connector_id,
        capability=payload.capability,
        tenant_context=tenant_context,
    )
