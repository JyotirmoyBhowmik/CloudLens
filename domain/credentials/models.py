"""Credential Lifecycle & Secret Reference Domain Models (Prompt 12).

Enforces:
- SEC-008 & SEC-009: Reference-only storage in application database. Zero raw or encrypted
  secret material stored in application entity models or database records.
- SEC-010 & SEC-011: Credential lifecycle states and zero-downtime rotation metadata.
- SEC-013: Expiry tracking metadata and alerting thresholds (30, 14, 3 days).
- SEC-014 & SEC-015: Tenant-bounded credential profiles shareable across connectors.
- SEC-017: Negative controls - zero credential material exposed in responses or models.
"""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from domain.models.base import CanonicalEntity
from domain.models.enums import AlertSeverity, CredentialType, ProviderType, RotationState
from domain.observability.redaction import SENSITIVE_KEY_SUBSTRINGS


class CredentialProfile(CanonicalEntity):
    """Authoritative platform credential profile holding opaque secret reference and safe metadata.

    Strict Architectural Invariant (Item 77 / SEC-008):
    Provider credential material is written directly to the dedicated secret store;
    this entity holds ONLY an opaque reference URI and non-sensitive metadata.
    Raw or encrypted secrets are strictly prohibited from appearing in any attribute.
    """

    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(..., description="Owning tenant identifier (SEC-014)")
    name: str = Field(..., description="Human-readable credential profile display name")
    provider: ProviderType = Field(..., description="Target hyperscale cloud provider")
    credential_type: CredentialType = Field(
        ..., description="Authentication mechanism classification"
    )
    secret_ref: str = Field(
        ...,
        description="Opaque secret store reference URI (e.g. vault://secret/data/tenants/{tid}/...)",
    )
    previous_secret_ref: str | None = Field(
        default=None,
        description="Retiring opaque reference maintained during zero-downtime rotation",
    )
    fingerprint: str = Field(
        ...,
        description="SHA-256 cryptographic fingerprint of credential material or certificate",
    )
    version: int = Field(default=1, ge=1, description="Active credential material revision number")
    rotation_state: RotationState = Field(
        default=RotationState.ACTIVE,
        description="Lifecycle rotation and validity status",
    )
    expires_at: datetime | None = Field(
        default=None,
        description="Explicit credential expiry timestamp in UTC",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Profile creation timestamp in UTC",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Profile last updated timestamp in UTC",
    )
    last_validated_at: datetime | None = Field(
        default=None,
        description="Timestamp of most recent successful pre-flight validation",
    )
    last_rotated_at: datetime | None = Field(
        default=None,
        description="Timestamp of most recent zero-downtime rotation",
    )
    connectors_bound: list[str] = Field(
        default_factory=list,
        description="IDs of cloud connectors within the tenant bound to this profile",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Safe, non-sensitive configuration metadata (e.g. role ARNs, client IDs, OCIDs)",
    )

    @field_validator("metadata")
    @classmethod
    def validate_no_secrets_in_metadata(cls, v: dict[str, Any]) -> dict[str, Any]:
        """Defense against bad data: Rejects metadata containing sensitive secret keys."""
        for key in v:
            k_lower = str(key).lower()
            if any(sub in k_lower for sub in SENSITIVE_KEY_SUBSTRINGS):
                raise ValueError(
                    f"Metadata key '{key}' matches sensitive credential keyword. "
                    "Credential material must be stored in the dedicated SecretStore, not in profile metadata."
                )
        return v


class CredentialProfileResponse(BaseModel):
    """Sanitized public-facing API response representation.

    Guarantees that no credential material is ever reachable or exposed.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., description="Unique credential profile ID")
    tenant_id: str = Field(..., description="Owning tenant identifier")
    name: str = Field(..., description="Display name")
    provider: ProviderType = Field(..., description="Target cloud provider")
    credential_type: CredentialType = Field(..., description="Authentication classification")
    secret_ref: str = Field(..., description="Opaque reference URI")
    fingerprint: str = Field(..., description="Non-reversible SHA-256 fingerprint")
    version: int = Field(..., description="Active version number")
    rotation_state: RotationState = Field(..., description="Active rotation state")
    expires_at: datetime | None = Field(default=None, description="Expiry timestamp in UTC")
    created_at: datetime = Field(..., description="Creation timestamp in UTC")
    updated_at: datetime = Field(..., description="Last update timestamp in UTC")
    last_validated_at: datetime | None = Field(
        default=None, description="Last validation timestamp"
    )
    last_rotated_at: datetime | None = Field(default=None, description="Last rotation timestamp")
    connectors_bound: list[str] = Field(default_factory=list, description="Bound connector IDs")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Non-sensitive metadata")


class CredentialCreateRequest(BaseModel):
    """Inbound request payload for provisioning a new credential profile."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=2, max_length=128, description="Profile name")
    provider: ProviderType = Field(..., description="Cloud provider identifier")
    credential_type: CredentialType = Field(..., description="Credential type")
    secret_payload: dict[str, Any] = Field(
        ...,
        description="Raw credential material passed directly to SecretStore after pre-flight validation",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional safe metadata (e.g. role ARN, tenant ID, client ID)",
    )
    expires_at: datetime | None = Field(
        default=None,
        description="Optional explicit credential expiration timestamp in UTC",
    )


class CredentialRotateRequest(BaseModel):
    """Inbound request payload for executing a zero-downtime credential rotation."""

    model_config = ConfigDict(extra="forbid")

    new_secret_payload: dict[str, Any] = Field(
        ...,
        description="New raw credential material to validate and store prior to retiring current",
    )
    new_metadata: dict[str, Any] | None = Field(
        default=None,
        description="Optional updated non-sensitive metadata",
    )
    new_expires_at: datetime | None = Field(
        default=None,
        description="Optional updated expiration timestamp in UTC",
    )


class ExpiryAlert(BaseModel):
    """Governance alert for approaching or passed credential expiry."""

    model_config = ConfigDict(extra="forbid")

    profile_id: str
    tenant_id: str
    profile_name: str
    provider: ProviderType
    days_remaining: int
    threshold_days: int
    severity: AlertSeverity
    message: str
    triggered_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
