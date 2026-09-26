"""Override Record Domain Models & Lifecycle Definitions (Prompt 13 Item 87).

Enforces:
- All eight mandatory attributes: who, what, why (min length >= 20 chars), when,
  previous value, new value, expiry, approval where required (BBP Section 32.3).
- Strict rejection of permanent overrides without explicit governance approval.
- Lifecycle tracking: ACTIVE, REVERTED, EXPIRED, CANCELLED.
"""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from domain.models.base import CanonicalEntity
from domain.models.enums import OverrideClass, OverrideStatus
from domain.models.exceptions import (
    OverrideValidationException,
)

MIN_WHY_LENGTH = 20


class OverrideApproval(BaseModel):
    """Governance approval record for sensitive or permanent overrides."""

    approver_id: str = Field(..., description="Identity of authorized approver")
    approved_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp of explicit sign-off in UTC",
    )
    ticket_ref: str = Field(..., description="Change control or ITSM ticket reference")
    permanent_approved: bool = Field(
        default=False, description="True only if permanent exemption was specifically granted"
    )


class OverrideRecord(CanonicalEntity):
    """Canonical override entity holding all eight mandatory attributes."""

    tenant_id: str = Field(..., description="Organization tenant identifier")
    override_class: OverrideClass = Field(..., description="Categorisation of override")
    who: str = Field(..., description="Principal identity who applied the override")
    what: str = Field(..., description="Target entity or configuration key overridden")
    why: str = Field(..., description="Mandatory free-text business rationale")
    when: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp when override took effect in UTC",
    )
    previous_value: Any = Field(..., description="Original value prior to override")
    new_value: Any = Field(..., description="Overriding value applied")
    expiry: datetime | None = Field(
        default=None, description="Expiration timestamp in UTC when override must revert"
    )
    is_permanent: bool = Field(
        default=False, description="True only for approved permanent overrides"
    )
    approval: OverrideApproval | None = Field(
        default=None, description="Approval details where required or permanent"
    )
    status: OverrideStatus = Field(default=OverrideStatus.ACTIVE, description="Lifecycle status")
    reverted_at: datetime | None = Field(default=None, description="Timestamp when reverted in UTC")
    reverted_by: str | None = Field(default=None, description="Identity or process that reverted")
    reversion_reason: str | None = Field(default=None, description="Explanation for reversion")
    correlation_id: str | None = Field(default=None, description="Request trace correlation ID")


class OverrideCreateRequest(BaseModel):
    """Request DTO enforcing the eight mandatory attributes."""

    override_class: OverrideClass = Field(..., description="Classification category")
    who: str = Field(..., description="Accountable identity")
    what: str = Field(..., description="Target property, rule, or configuration key")
    why: str = Field(..., description="Detailed justification (minimum 20 characters)")
    previous_value: Any = Field(..., description="Value prior to override")
    new_value: Any = Field(..., description="New overriding value")
    expiry: datetime | None = Field(default=None, description="Expiration timestamp in UTC")
    is_permanent: bool = Field(default=False, description="Whether this override is permanent")
    approval: OverrideApproval | None = Field(default=None, description="Approval where required")

    @field_validator("why")
    @classmethod
    def validate_why_length(cls, v: str) -> str:
        clean = v.strip() if v else ""
        if len(clean) < MIN_WHY_LENGTH:
            raise OverrideValidationException(
                f"Override reason ('why') must be at least {MIN_WHY_LENGTH} characters of free text "
                f"explaining the operational necessity. Found {len(clean)} characters."
            )
        return clean

    @field_validator("who", "what")
    @classmethod
    def validate_non_empty(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise OverrideValidationException(f"Attribute '{info.field_name}' cannot be empty.")
        return v.strip()


class OverrideResponse(BaseModel):
    """Sanitized public DTO for override representation."""

    id: str
    tenant_id: str
    override_class: OverrideClass
    who: str
    what: str
    why: str
    when: datetime
    previous_value: Any
    new_value: Any
    expiry: datetime | None
    is_permanent: bool
    approval: OverrideApproval | None
    status: OverrideStatus
    reverted_at: datetime | None
    reverted_by: str | None
    reversion_reason: str | None
