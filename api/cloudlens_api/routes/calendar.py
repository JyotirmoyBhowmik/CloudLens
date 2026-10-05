"""Calendar & Expiry Timeline Endpoint (Prompt R-FEAT / IMP-10).

Exposes:
- GET /api/v1/commitments/calendar: Unified 5-stream operational calendar
  (credentials, certificates, cloud commitments, contracts/licences, budget closes).
"""

from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Query, status

from domain.commitments.calendar import get_commitment_calendar_service

router = APIRouter(prefix="/api/v1/commitments", tags=["Commitment & Expiry Calendar"])


@router.get("/calendar", status_code=status.HTTP_200_OK, summary="Unified Expiry Calendar (IMP-10)")
def get_commitment_calendar(
    lookahead_days: int = Query(default=90, ge=1, le=365, description="Lookahead horizon in days"),
) -> dict[str, Any]:
    """Returns a unified calendar aggregating credential, certificate, commitment, licence, and fiscal closes."""
    service = get_commitment_calendar_service()
    return service.get_calendar_events(lookahead_days=lookahead_days)
