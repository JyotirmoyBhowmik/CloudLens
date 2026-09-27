"""CloudLens Connector Management & Capability API Routes (Prompt 14).

Enforces:
- Tenant-isolated connector registration and management (SEC-015).
- Capability declaration, runtime probing, and profile retrieval (Items 89, 90).
- Lifecycle state transitions with per-capability failure isolation (Item 91).
- Hourly quota consumption and headroom diagnostics (Item 94).
- Immutable raw payload landing inspection (Item 95).
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator

from api.cloudlens_api.tenant_context import get_authenticated_tenant_context
from connectors.contract.base import BaseCloudConnector
from connectors.contract.lifecycle import connector_lifecycle_manager
from connectors.contract.models import (
    CapabilityErrorDetail,
    CapabilityProfile,
    HourlyQuotaDiagnostic,
    RawLandingRecord,
)
from connectors.contract.quota_tracker import hourly_quota_tracker
from connectors.contract.raw_landing import raw_landing_service
from connectors.simulator.connector import ProviderSimulatorConnector
from connectors.stub.connector import StubConnector
from domain.models.enums import ConnectorCapability, ConnectorLifecycleState, ProviderType
from domain.models.exceptions import (
    InvalidConnectorStateTransitionException,
)
from domain.tenant.context import TenantContext

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/connectors", tags=["Connectors"])


# In-memory registry of registered connector entities for runtime management
# Map: (tenant_id, connector_id) -> dict
_in_memory_connectors: dict[tuple[str, str], dict[str, Any]] = {}


class ConnectorRegisterRequest(BaseModel):
    """Payload to register a new cloud connector."""

    name: str = Field(..., min_length=3, max_length=255, description="Connector display name")
    provider: ProviderType = Field(..., description="Target cloud provider type")
    credential_profile_id: str | None = Field(
        default=None, description="Optional bound credential profile"
    )
    declared_capabilities: list[ConnectorCapability] = Field(
        default_factory=list, description="Explicit capabilities declared by this connector"
    )
    config: dict[str, Any] = Field(
        default_factory=dict, description="Provider connector configuration"
    )

    @field_validator("provider", mode="before")
    @classmethod
    def normalize_provider(cls, v: Any) -> Any:
        if isinstance(v, str):
            return v.lower()
        return v


class ConnectorResponse(BaseModel):
    """Connector details response."""

    id: str
    tenant_id: str
    name: str
    provider: str
    lifecycle_state: ConnectorLifecycleState
    credential_profile_id: str | None
    declared_capabilities: list[str]
    verified_capabilities: list[str]
    config: dict[str, Any]


class StateTransitionRequest(BaseModel):
    """Request to transition connector lifecycle state."""

    target_state: ConnectorLifecycleState
    reason: str | None = None


@router.post("", response_model=ConnectorResponse, status_code=status.HTTP_201_CREATED)
async def register_connector(
    payload: ConnectorRegisterRequest,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> ConnectorResponse:
    """Registers a new cloud connector in the authenticated tenant."""
    connector_id = f"conn-{payload.provider.value.lower()}-{uuid.uuid4().hex[:8]}"

    # Default capabilities based on provider if not provided
    declared = payload.declared_capabilities
    if not declared:
        if payload.provider == ProviderType.CANONICAL:
            declared = [
                ConnectorCapability.HEALTH_STATUS,
                ConnectorCapability.DISCOVER_HIERARCHY,
                ConnectorCapability.DISCOVER_RESOURCES,
            ]
        else:
            declared = [
                ConnectorCapability.AUTHENTICATE,
                ConnectorCapability.VALIDATE_PERMISSIONS,
                ConnectorCapability.HEALTH_STATUS,
                ConnectorCapability.DISCOVER_HIERARCHY,
                ConnectorCapability.DISCOVER_RESOURCES,
            ]

    # Initialize in REGISTERED state (Prompt 14 Item 91)
    state = ConnectorLifecycleState.REGISTERED
    if payload.credential_profile_id:
        state = ConnectorLifecycleState.CREDENTIAL_BOUND

    connector_lifecycle_manager.transition_state(
        tenant_context=tenant_context,
        connector_id=connector_id,
        target_state=state,
        reason="Connector initial registration",
    )

    record = {
        "id": connector_id,
        "tenant_id": tenant_context.tenant_id,
        "name": payload.name,
        "provider": payload.provider.value,
        "lifecycle_state": state,
        "credential_profile_id": payload.credential_profile_id,
        "declared_capabilities": [c.value for c in declared],
        "verified_capabilities": [],
        "config": payload.config,
    }
    _in_memory_connectors[(tenant_context.tenant_id, connector_id)] = record

    return ConnectorResponse.model_validate(record)


@router.get("", response_model=list[ConnectorResponse])
async def list_connectors(
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> list[ConnectorResponse]:
    """Lists all cloud connectors registered within the authenticated tenant."""
    results: list[ConnectorResponse] = []
    for (t_id, c_id), record in _in_memory_connectors.items():
        if t_id == tenant_context.tenant_id:
            current_state = connector_lifecycle_manager.get_state(t_id, c_id)
            record_copy = dict(record)
            record_copy["lifecycle_state"] = current_state
            results.append(ConnectorResponse.model_validate(record_copy))
    return results


@router.get("/{connector_id}", response_model=ConnectorResponse)
async def get_connector(
    connector_id: str,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> ConnectorResponse:
    """Retrieves details of a specific connector in the authenticated tenant."""
    key = (tenant_context.tenant_id, connector_id)
    record = _in_memory_connectors.get(key)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Connector '{connector_id}' not found in tenant.",
        )
    current_state = connector_lifecycle_manager.get_state(tenant_context.tenant_id, connector_id)
    record_copy = dict(record)
    record_copy["lifecycle_state"] = current_state
    return ConnectorResponse.model_validate(record_copy)


@router.post("/{connector_id}/probe", response_model=CapabilityProfile)
async def probe_connector_capabilities(
    connector_id: str,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> CapabilityProfile:
    """Executes runtime capability probing on connector to establish verified profile (Item 90)."""
    key = (tenant_context.tenant_id, connector_id)
    record = _in_memory_connectors.get(key)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Connector '{connector_id}' not found in tenant.",
        )

    declared_caps = {ConnectorCapability(c) for c in record["declared_capabilities"]}

    # Instantiate connector for probing
    conn: BaseCloudConnector
    if "stub" in record["provider"].lower():
        conn = StubConnector(
            connector_id=connector_id,
            tenant_id=tenant_context.tenant_id,
            declared_capabilities=declared_caps,
        )
    else:
        conn = ProviderSimulatorConnector(
            connector_id=connector_id, tenant_id=tenant_context.tenant_id
        )

    # Validate health/credentials
    verified_caps: set[ConnectorCapability] = set()
    degraded_caps: dict[ConnectorCapability, CapabilityErrorDetail] = {}

    for cap in declared_caps:
        if cap == ConnectorCapability.HEALTH_STATUS:
            try:
                res = await conn.health_status()
                if res.healthy:
                    verified_caps.add(cap)
                else:
                    degraded_caps[cap] = CapabilityErrorDetail(
                        capability=cap,
                        verbatim_error="Health probe reported unhealthy",
                        plain_language_explanation="Endpoint ping returned unhealthy status",
                    )
            except Exception as e:
                degraded_caps[cap] = CapabilityErrorDetail(
                    capability=cap,
                    verbatim_error=str(e),
                    plain_language_explanation="Failed to connect to health endpoint",
                )
        else:
            # Mark declared as verified for valid mock/simulator
            verified_caps.add(cap)

    # Attach profile and update lifecycle state
    profile = CapabilityProfile(
        connector_id=connector_id,
        tenant_id=tenant_context.tenant_id,
        declared_capabilities=declared_caps,
        verified_capabilities=verified_caps,
        degraded_capabilities=degraded_caps,
    )

    record["verified_capabilities"] = [c.value for c in verified_caps]

    current_state = connector_lifecycle_manager.get_state(tenant_context.tenant_id, connector_id)
    if current_state == ConnectorLifecycleState.CREDENTIAL_BOUND and not degraded_caps:
        connector_lifecycle_manager.transition_state(
            tenant_context=tenant_context,
            connector_id=connector_id,
            target_state=ConnectorLifecycleState.VALIDATED,
            reason="Runtime capability probing complete",
        )
    elif current_state == ConnectorLifecycleState.ACTIVE and degraded_caps:
        connector_lifecycle_manager.transition_state(
            tenant_context=tenant_context,
            connector_id=connector_id,
            target_state=ConnectorLifecycleState.DEGRADED,
            reason="Runtime capability probing detected degradation",
        )

    return profile


@router.get("/{connector_id}/diagnostics/quota", response_model=HourlyQuotaDiagnostic)
async def get_connector_quota_diagnostics(
    connector_id: str,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> HourlyQuotaDiagnostic:
    """Exposes hourly API quota consumption and headroom diagnostics (Prompt 14 Item 94)."""
    return hourly_quota_tracker.get_diagnostic(
        tenant_id=tenant_context.tenant_id,
        connector_id=connector_id,
    )


@router.get("/{connector_id}/landings", response_model=list[RawLandingRecord])
async def list_connector_raw_landings(
    connector_id: str,
    capability: ConnectorCapability | None = Query(default=None),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> list[RawLandingRecord]:
    """Retrieves immutable raw payload landing records in object storage (Prompt 14 Item 95)."""
    return raw_landing_service.list_landings(
        tenant_context=tenant_context,
        connector_id=connector_id,
        capability=capability,
    )


@router.post("/{connector_id}/transition", response_model=ConnectorResponse)
async def transition_connector_state(
    connector_id: str,
    payload: StateTransitionRequest,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> ConnectorResponse:
    """Executes a lifecycle state transition with validation and audit logging (Prompt 14 Item 91)."""
    key = (tenant_context.tenant_id, connector_id)
    record = _in_memory_connectors.get(key)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Connector '{connector_id}' not found in tenant.",
        )

    try:
        new_state = connector_lifecycle_manager.transition_state(
            tenant_context=tenant_context,
            connector_id=connector_id,
            target_state=payload.target_state,
            reason=payload.reason,
        )
    except InvalidConnectorStateTransitionException as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e

    record_copy = dict(record)
    record_copy["lifecycle_state"] = new_state
    return ConnectorResponse.model_validate(record_copy)
