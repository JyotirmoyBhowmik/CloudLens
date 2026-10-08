"""Tenant Domain Model (Prompt P04)."""

from datetime import UTC, datetime
from pydantic import Field
from domain.models.base import CanonicalEntity


class Tenant(CanonicalEntity):
    """Authoritative tenant organization entity."""

    id: str = Field(..., description="Unique tenant identifier (e.g. 'tenant-primary')")
    name: str = Field(..., description="Tenant organization display name")
    reporting_currency: str = Field(default="USD", description="Default reporting currency ISO code")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Creation timestamp in UTC"
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Last update timestamp in UTC"
    )
