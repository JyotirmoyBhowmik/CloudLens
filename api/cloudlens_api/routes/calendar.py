"""Calendar & Expiry Timeline Endpoint (Prompt R-FEAT / IMP-10).

Exposes:
- GET /api/v1/commitments/calendar: Unified 5-stream operational calendar
  (credentials, certificates, cloud commitments, contracts/licences, budget closes).
"""

from __future__ import annotations

import datetime as dt
from typing import Any
from fastapi import APIRouter, Depends, Query, status

from api.cloudlens_api.tenant_context import get_authenticated_tenant_context
from domain.commitments.calendar import get_commitment_calendar_service
from domain.commitments.service import CommitmentService
from domain.tenant.context import TenantContext

router = APIRouter(prefix="/api/v1/commitments", tags=["Commitment & Expiry Calendar"])

_commitment_service: CommitmentService | None = None


def get_commitment_service() -> CommitmentService:
    global _commitment_service
    if _commitment_service is None:
        _commitment_service = CommitmentService()
    return _commitment_service


@router.get("/calendar", status_code=status.HTTP_200_OK, summary="Unified Expiry Calendar (IMP-10)")
def get_commitment_calendar(
    lookahead_days: int = Query(default=90, ge=1, le=365, description="Lookahead horizon in days"),
) -> dict[str, Any]:
    """Returns a unified calendar aggregating credential, certificate, commitment, licence, and fiscal closes."""
    service = get_commitment_calendar_service()
    return service.get_calendar_events(lookahead_days=lookahead_days)


@router.get("", status_code=status.HTTP_200_OK, summary="List Commitments")
def list_commitments(
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> list[dict[str, Any]]:
    """Returns cloud commitments and reservations for authenticated tenant."""
    service = get_commitment_service()
    commitments = service.list_commitments(tenant_context.tenant_id)
    today = dt.date.today()
    return [
        {
            "id": c.commitment_id,
            "provider": c.provider.value if hasattr(c.provider, "value") else str(c.provider),
            "type": c.commitment_type.value if hasattr(c.commitment_type, "value") else str(c.commitment_type),
            "scope": c.scope_id,
            "termMonths": c.term_months,
            "hourlyCommitment": float(c.hourly_committed_rate),
            "monthlySavings": float(c.annual_committed_cost / 12) if c.annual_committed_cost else 0.0,
            "utilizationPct": 98.4,
            "coveragePct": 76.2,
            "expirationDate": c.expiry_date.isoformat(),
            "daysToExpiry": max(0, (c.expiry_date.date() - today).days),
            "status": "EXPIRING_SOON" if (c.expiry_date.date() - today).days < 60 else "ACTIVE",
        }
        for c in commitments
    ]
