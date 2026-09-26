"""Audit Domain Models & Append-Only Event Definitions (Prompt 13 Item 86).

Enforces:
- Full canonical audit event taxonomy covering authentication, denied authorization,
  configuration, overrides, exports, credentials, roles/grants, budgets/thresholds,
  manual dependency edits, and report generation/downloads.
- Cryptographically chained event hashes for append-only tamper evidence.
- Mechanical immutability across all principal roles.
"""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from domain.models.base import CanonicalEntity
from domain.models.enums import AuditEventType


class AuditEvent(CanonicalEntity):
    """Canonical append-only audit event record (Prompt 13 Item 86, BBP Section 41)."""

    tenant_id: str = Field(..., description="Organization tenant identifier")
    event_type: AuditEventType = Field(..., description="Canonical taxonomy classification")
    actor_id: str = Field(
        ..., description="Accountable principal (user email, system, or machine client)"
    )
    actor_roles: list[str] = Field(
        default_factory=list, description="Roles held by actor at time of event"
    )
    action: str = Field(..., description="Action performed or attempted")
    resource_type: str = Field(..., description="Target entity or system component type")
    resource_id: str = Field(..., description="Target entity identifier")
    details: dict[str, Any] = Field(default_factory=dict, description="Contextual payload or diff")
    correlation_id: str | None = Field(default=None, description="Request trace correlation ID")
    ip_address: str | None = Field(default=None, description="Originating client IP address")
    user_agent: str | None = Field(default=None, description="Originating client User-Agent")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Immutable UTC timestamp when event occurred",
    )
    previous_event_hash: str | None = Field(
        default=None, description="Cryptographic SHA-256 hash of previous tenant event"
    )
    event_hash: str = Field(
        ..., description="SHA-256 hash chaining event payload to previous event"
    )


class AuditEventCreate(BaseModel):
    """Payload to record a new audit event in the append-only stream."""

    event_type: AuditEventType
    actor_id: str
    actor_roles: list[str] = Field(default_factory=list)
    action: str
    resource_type: str
    resource_id: str
    details: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None


class AuditEventFilter(BaseModel):
    """Query filters for audit stream inspection."""

    event_type: AuditEventType | None = None
    actor_id: str | None = None
    resource_type: str | None = None
    resource_id: str | None = None
    correlation_id: str | None = None
    since: datetime | None = None
    until: datetime | None = None


class AuditEventResponse(BaseModel):
    """Sanitized public DTO for audit event inspection."""

    id: str
    tenant_id: str
    event_type: AuditEventType
    actor_id: str
    actor_roles: list[str]
    action: str
    resource_type: str
    resource_id: str
    details: dict[str, Any]
    correlation_id: str | None
    ip_address: str | None
    user_agent: str | None
    timestamp: datetime
    previous_event_hash: str | None
    event_hash: str
