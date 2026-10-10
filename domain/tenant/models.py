"""Tenant Domain Model (Prompt P04 / Prompt P12)."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from pydantic import Field, model_validator
from domain.models.base import CanonicalEntity


class TenantType(StrEnum):
    """Canonical tenant environment types (Prompt P12)."""

    PRODUCTION = "PRODUCTION"
    NON_PRODUCTION = "NON_PRODUCTION"
    DEMO = "DEMO"


class TenantStatus(StrEnum):
    """Lifecycle operational status of tenant organization."""

    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"


class Tenant(CanonicalEntity):
    """Authoritative tenant organization entity (Prompt P04 / P12)."""

    id: str = Field(..., description="Unique tenant identifier (e.g. 'tenant-snpl-prod')")
    code: str = Field(default="", description="Unique uppercase tenant code (e.g. 'SNPL_PROD')")
    name: str = Field(..., description="Tenant organization display name")
    type: TenantType = Field(default=TenantType.PRODUCTION, description="Tenant environment type")
    reporting_currency: str = Field(default="USD", description="Default reporting currency ISO code")
    fiscal_year_start: int = Field(default=1, ge=1, le=12, description="Fiscal year start month (1-12)")
    iana_timezone: str = Field(default="UTC", description="IANA Time Zone identifier (e.g. 'UTC')")
    retention_profile: str = Field(default="STANDARD", description="Data retention policy profile")
    status: TenantStatus = Field(default=TenantStatus.ACTIVE, description="Lifecycle operational status")
    suspension_reason: str | None = Field(default=None, description="Reason recorded when tenant is suspended")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Creation timestamp in UTC"
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Last update timestamp in UTC"
    )

    @model_validator(mode="after")
    def populate_default_code(self) -> "Tenant":
        if not self.code and self.id:
            raw_id = self.id
            if raw_id.startswith("tenant-"):
                self.code = raw_id[len("tenant-"):].replace("-", "_").upper()
            elif raw_id.startswith("ten-"):
                self.code = raw_id[len("ten-"):].replace("-", "_").upper()
            else:
                self.code = raw_id.replace("-", "_").upper()
        return self
