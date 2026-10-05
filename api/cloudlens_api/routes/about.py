"""About and Release Information Endpoint (Prompt R-FEAT / IMP-06).

Exposes /api/v1/about returning:
- version
- commit hash
- migration head
- release notes
- environment metadata
"""

from __future__ import annotations

from typing import Any
from fastapi import APIRouter, status

from domain.release.service import get_release_service

router = APIRouter(prefix="/api/v1", tags=["About & Release"])


@router.get("/about", status_code=status.HTTP_200_OK)
def get_about_info() -> dict[str, Any]:
    """Returns platform version, commit hash, database migration head, and release notes."""
    return get_release_service().get_release_info()
