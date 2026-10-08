"""Domain models for cloud connectors and capability profiles (Prompt P05)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from domain.models.base import CanonicalEntity
from domain.models.enums import ConnectorLifecycleState, ProviderType


class ConnectorEntity(CanonicalEntity):
    """Registered cloud provider connector record."""

    tenant_id: str = Field(..., description="Owning tenant identifier")
    name: str = Field(..., description="Connector display name")
    provider: ProviderType = Field(..., description="Cloud provider type")
    lifecycle_state: ConnectorLifecycleState = Field(
        default=ConnectorLifecycleState.REGISTERED, description="Current lifecycle state"
    )
    credential_profile_id: str | None = Field(
        default=None, description="Optional associated credential profile ID"
    )
    declared_capabilities: list[str] = Field(
        default_factory=list, description="Capabilities declared by the connector"
    )
    verified_capabilities: list[str] = Field(
        default_factory=list, description="Capabilities verified by probing"
    )
    config: dict[str, Any] = Field(
        default_factory=dict, description="Provider-specific configuration"
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


__all__ = ["ConnectorEntity"]
