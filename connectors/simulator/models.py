"""Data Models and DTOs for CloudLens Provider Simulator (Prompt 47 Item 23).

Defines:
- SimulatorProfile: Azure-shaped, AWS-shaped, GCP-shaped, and OCI-shaped profiles.
- RateLimitConfig: Simulated rate limits, burst allowance, and throttling behavior.
- PaginationParams & PaginatedResponse: Standard cursor/token pagination.
- RawLandingPayload: Immutable raw payload landings mimicking real provider ingestion.
"""

import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class SimulatorProfile(StrEnum):
    """Four provider-shaped simulator profiles reproducing native structures (Prompt 47 Item 23)."""

    AWS = "aws"
    AZURE = "azure"
    GCP = "gcp"
    OCI = "oci"


class RateLimitConfig(BaseModel):
    """Simulated rate limiting configuration."""

    requests_per_second: float = Field(
        default=50.0, ge=1.0, description="Maximum sustained requests per second before throttling"
    )
    burst_capacity: int = Field(default=100, ge=1, description="Burst bucket capacity")
    simulate_throttling: bool = Field(
        default=True, description="Whether to simulate rate limit headers and throttling exceptions"
    )


class PaginationParams(BaseModel):
    """Pagination query parameters for simulated endpoints."""

    page_size: int = Field(default=50, ge=1, le=1000, description="Items per page")
    page_token: str | None = Field(default=None, description="Opaque pagination token / cursor")


class PaginatedResponse(BaseModel):
    """Paginated collection returned by simulated discovery and billing APIs."""

    items: list[dict[str, Any]] = Field(
        default_factory=list, description="Page of native item dicts"
    )
    next_page_token: str | None = Field(
        default=None, description="Opaque token for next page or None if done"
    )
    total_items: int = Field(default=0, description="Total matching records across all pages")
    page_number: int = Field(default=1, description="1-indexed sequence page number")


class RawLandingPayload(BaseModel):
    """Raw landing payload stored in simulated ingestion bucket."""

    landing_id: str = Field(..., description="Unique landing identifier")
    connector_id: str = Field(..., description="Originating connector ID")
    profile: SimulatorProfile = Field(..., description="Native provider profile shape")
    payload_type: str = Field(
        ..., description="Payload type: hierarchy, inventory, cost_export, usage_metrics"
    )
    raw_content: Any = Field(..., description="Native un-normalized provider JSON payload")
    landed_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Landing timestamp in UTC"
    )
    byte_size: int = Field(default=0, description="Byte size of raw payload")
    sha256_checksum: str = Field(..., description="Cryptographic SHA256 integrity hash")

    @classmethod
    def create(
        cls,
        landing_id: str,
        connector_id: str,
        profile: SimulatorProfile,
        payload_type: str,
        raw_content: Any,
    ) -> "RawLandingPayload":
        """Factory constructor computing size and sha256 checksum."""
        encoded = json.dumps(raw_content, sort_keys=True, default=str).encode("utf-8")
        checksum = hashlib.sha256(encoded).hexdigest()
        return cls(
            landing_id=landing_id,
            connector_id=connector_id,
            profile=profile,
            payload_type=payload_type,
            raw_content=raw_content,
            byte_size=len(encoded),
            sha256_checksum=checksum,
        )
