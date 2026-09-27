"""CloudLens Connector Contract Domain Models (Prompt 14 / BBP Section 26).

Enforces:
- Capability profile and runtime probing results.
- Checkpointed pagination with continuation tokens.
- Hourly quota diagnostics and headroom tracking.
- Immutable raw landing metadata with cryptographic SHA256 checksums.
- Per-capability health and circuit breaker status records.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

from domain.config.tenant_settings import ConnectorSettings
from domain.models.enums import (
    CapabilityHealth,
    CircuitBreakerState,
    ConnectorCapability,
    ProviderType,
)

T = TypeVar("T")
_defaults = ConnectorSettings()


class PaginationParams(BaseModel):
    """Pagination parameters enforcing bounded page sizes (Prompt 14 Item 93)."""

    page_size: int = Field(
        default=_defaults.default_page_size,
        ge=1,
        le=_defaults.max_page_size,
        description="Bounded page size limit (no unbounded enumeration allowed)",
    )
    continuation_token: str | None = Field(
        default=None,
        description="Opaque provider continuation token for resuming pagination",
    )
    page_token: str | None = Field(
        default=None,
        description="Alias for continuation_token for simulator compatibility",
    )
    page_number: int = Field(
        default=1,
        ge=1,
        description="1-based page sequence number within current ingestion run",
    )


class PagedResult(list, Generic[T]):
    """Paged collection that is list-compatible and holds pagination metadata."""

    def __init__(
        self,
        items: list[T],
        continuation_token: str | None = None,
        is_truncated: bool = False,
        total_records: int | None = None,
    ) -> None:
        super().__init__(items)
        self.items: list[T] = items
        self.continuation_token: str | None = continuation_token
        self.is_truncated: bool = is_truncated
        self.total_records: int | None = total_records

    def __repr__(self) -> str:
        return (
            f"PagedResult(count={len(self.items)}, "
            f"has_more={self.is_truncated or bool(self.continuation_token)}, "
            f"continuation_token={self.continuation_token})"
        )


class AuthResult(BaseModel):
    """Result of provider authentication probe (Prompt 14 Item 89)."""

    authenticated: bool = Field(..., description="Whether authentication handshake succeeded")
    identity: str = Field(
        ..., description="Authenticated principal ARN, client ID or service account"
    )
    provider: str = Field(..., description="Provider identifier code")
    expires_at: datetime | None = Field(
        default=None, description="Optional temporary credential expiry"
    )
    attributes: dict[str, Any] = Field(default_factory=dict, description="Provider auth metadata")


class PermissionValidationResult(BaseModel):
    """Result of least-privilege permission validation probe (Prompt 14 Item 89)."""

    valid: bool = Field(..., description="Whether required permissions are satisfied")
    provider: str = Field(..., description="Provider identifier code")
    capabilities: list[str] = Field(
        default_factory=list, description="Verified available capability codes"
    )
    missing_permissions: dict[str, list[str]] = Field(
        default_factory=dict, description="Map of capability to missing API permissions"
    )
    raw_details: dict[str, Any] = Field(
        default_factory=dict, description="Verbatim provider response metadata"
    )


class CapabilityErrorDetail(BaseModel):
    """Structured error preserving verbatim provider response and plain-language explanation."""

    capability: ConnectorCapability = Field(..., description="Capability encountering failure")
    verbatim_error: str = Field(
        ..., description="Raw provider error message or API response payload"
    )
    plain_language_explanation: str = Field(
        ..., description="Plain-language human explanation of the failure"
    )
    status_code: int | None = Field(default=None, description="HTTP status code if applicable")
    failed_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Failure timestamp"
    )


class CapabilityHealthRecord(BaseModel):
    """Individual capability operational state and circuit status (Prompt 14 Item 91)."""

    capability: ConnectorCapability = Field(..., description="Capability being monitored")
    health: CapabilityHealth = Field(
        default=CapabilityHealth.HEALTHY, description="Current health status"
    )
    circuit_state: CircuitBreakerState = Field(
        default=CircuitBreakerState.CLOSED, description="Circuit breaker state"
    )
    consecutive_failures: int = Field(default=0, ge=0, description="Consecutive failure count")
    last_success_at: datetime | None = Field(
        default=None, description="Timestamp of last successful invocation"
    )
    last_failure_at: datetime | None = Field(
        default=None, description="Timestamp of last failed invocation"
    )
    error_detail: CapabilityErrorDetail | None = Field(
        default=None, description="Most recent error detail"
    )


class CapabilityProfile(BaseModel):
    """Comprehensive capability profile resulting from runtime probing (Prompt 14 Item 90)."""

    connector_id: str = Field(..., description="Unique connector identifier")
    tenant_id: str = Field(..., description="Owning tenant identifier")
    declared_capabilities: set[ConnectorCapability] = Field(
        default_factory=set, description="Set of capabilities statically declared by the connector"
    )
    verified_capabilities: set[ConnectorCapability] = Field(
        default_factory=set, description="Set of capabilities validated via runtime probing"
    )
    degraded_capabilities: dict[ConnectorCapability, CapabilityErrorDetail] = Field(
        default_factory=dict, description="Map of capabilities that failed probing or execution"
    )
    health_records: dict[ConnectorCapability, CapabilityHealthRecord] = Field(
        default_factory=dict, description="Per-capability health states"
    )
    probed_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Timestamp of capability probe"
    )

    def is_verified(self, capability: ConnectorCapability) -> bool:
        """Checks if a capability was successfully verified and is active."""
        return capability in self.verified_capabilities

    def is_healthy(self, capability: ConnectorCapability) -> bool:
        """Checks if capability is verified and currently healthy (not circuit broken)."""
        if not self.is_verified(capability):
            return False
        rec = self.health_records.get(capability)
        if not rec:
            return True
        return (
            rec.health == CapabilityHealth.HEALTHY and rec.circuit_state != CircuitBreakerState.OPEN
        )


class JobCheckpoint(BaseModel):
    """Job checkpoint model persisted after every page for resumption without duplication (Prompt 14 Item 93)."""

    checkpoint_id: str = Field(..., description="Unique checkpoint identifier")
    tenant_id: str = Field(..., description="Owning tenant identifier (SEC-015)")
    job_id: str = Field(..., description="Associated sync job identifier")
    connector_id: str = Field(..., description="Target connector identifier")
    capability: ConnectorCapability = Field(..., description="Capability being paginated")
    continuation_token: str | None = Field(default=None, description="Opaque resumption token")
    page_number: int = Field(..., ge=1, description="Page number just completed")
    records_ingested: int = Field(
        default=0, ge=0, description="Total cumulative records ingested so far"
    )
    last_record_id: str | None = Field(
        default=None, description="Identifier of last processed record"
    )
    status: str = Field(default="IN_PROGRESS", description="Current status of the checkpointed job")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Creation timestamp"
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Last update timestamp"
    )


class HourlyQuotaDiagnostic(BaseModel):
    """Hourly API request consumption and headroom diagnostics (Prompt 14 Item 94)."""

    connector_id: str = Field(..., description="Connector identifier")
    tenant_id: str = Field(..., description="Owning tenant identifier")
    window_hour_utc: str = Field(
        ..., description="ISO 8601 hour bucket string (e.g. 2026-09-26T18:00:00Z)"
    )
    requests_made: int = Field(
        default=0, ge=0, description="Requests consumed in current hour window"
    )
    hourly_limit: int = Field(..., ge=1, description="Maximum requests permitted per hour")
    remaining_headroom: int = Field(
        ..., ge=0, description="Remaining requests available before throttling"
    )
    utilization_percentage: float = Field(
        ..., ge=0.0, description="Percentage of hourly quota consumed"
    )
    is_exhausted: bool = Field(
        default=False, description="Whether the quota has been fully exhausted"
    )
    resets_at: datetime = Field(..., description="Timestamp when quota window resets")


class RawLandingRecord(BaseModel):
    """Metadata record for raw immutable payloads landed in object storage (Prompt 14 Item 95)."""

    landing_id: str = Field(..., description="Unique landing record identifier")
    tenant_id: str = Field(..., description="Owning tenant identifier (SEC-015)")
    connector_id: str = Field(..., description="Originating connector identifier")
    run_id: str = Field(..., description="Sync or ingestion run identifier")
    capability: ConnectorCapability = Field(..., description="Ingested capability")
    schema_version: str = Field(..., description="Schema version identifier for landing payload")
    storage_path: str = Field(..., description="Object storage URI (prefixed under tenant path)")
    sha256_checksum: str = Field(..., description="Cryptographic SHA256 digest of raw payload")
    byte_size: int = Field(..., ge=0, description="Exact payload size in bytes")
    record_count: int = Field(..., ge=0, description="Count of raw records contained in landing")
    landed_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Landing timestamp"
    )


class HealthStatusResult(BaseModel):
    """Health check diagnostic result for connector endpoints."""

    healthy: bool = Field(..., description="Whether provider management endpoint is healthy")
    latency_ms: float = Field(..., ge=0.0, description="Endpoint roundtrip latency in milliseconds")
    status_code: int | None = Field(default=None, description="HTTP status code from probe")
    details: dict[str, Any] = Field(default_factory=dict, description="Diagnostic metadata")


class ProviderMetadataResult(BaseModel):
    """Metadata describing provider capabilities, regions, and supported versions."""

    provider: ProviderType = Field(..., description="Provider type identifier")
    api_version: str = Field(..., description="Provider API version in use")
    supported_regions: list[str] = Field(
        default_factory=list, description="Supported deployment regions"
    )
    capabilities_supported: list[ConnectorCapability] = Field(
        default_factory=list, description="Capabilities supported by this provider implementation"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional provider metadata"
    )
