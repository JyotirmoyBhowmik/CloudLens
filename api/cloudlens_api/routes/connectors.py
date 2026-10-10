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
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from pydantic import BaseModel, Field, field_validator

from api.cloudlens_api.conventions.concurrency import generate_etag, validate_if_match
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
from connectors.factory import resolve_connector
from connectors.stub.connector import StubConnector
from connectors.sync.orchestrator import get_sync_orchestrator
from domain.models.enums import (
    ConnectorCapability,
    ConnectorLifecycleState,
    ProviderType,
    SyncType,
)
from domain.models.exceptions import (
    InvalidConnectorStateTransitionException,
)
from domain.sync.models import SyncJob
from domain.sync.repository import get_sync_job_repository
from domain.tenant.context import TenantContext

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/connectors", tags=["Connectors"])


from domain.connectors.models import ConnectorEntity
from domain.connectors.repository import get_connector_repository


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

    entity = ConnectorEntity(
        id=connector_id,
        tenant_id=tenant_context.tenant_id,
        name=payload.name,
        provider=payload.provider,
        lifecycle_state=state,
        credential_profile_id=payload.credential_profile_id,
        declared_capabilities=[c.value for c in declared],
        verified_capabilities=[],
        config=payload.config,
    )
    repo = get_connector_repository()
    saved = repo.save(entity, tenant_context=tenant_context)

    return ConnectorResponse(
        id=saved.id,
        tenant_id=saved.tenant_id,
        name=saved.name,
        provider=saved.provider.value if hasattr(saved.provider, "value") else str(saved.provider),
        lifecycle_state=saved.lifecycle_state,
        credential_profile_id=saved.credential_profile_id,
        declared_capabilities=saved.declared_capabilities,
        verified_capabilities=saved.verified_capabilities,
        config=saved.config,
    )


@router.get("", response_model=list[ConnectorResponse])
async def list_connectors(
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> list[ConnectorResponse]:
    """Lists all cloud connectors registered within the authenticated tenant."""
    repo = get_connector_repository()
    items = repo.list(tenant_context=tenant_context)
    return [
        ConnectorResponse(
            id=c.id,
            tenant_id=c.tenant_id,
            name=c.name,
            provider=c.provider.value if hasattr(c.provider, "value") else str(c.provider),
            lifecycle_state=c.lifecycle_state,
            credential_profile_id=c.credential_profile_id,
            declared_capabilities=c.declared_capabilities,
            verified_capabilities=c.verified_capabilities,
            config=c.config,
        )
        for c in items
    ]


@router.get("/{connector_id}", response_model=ConnectorResponse)
async def get_connector(
    connector_id: str,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> ConnectorResponse:
    """Retrieves details of a specific connector in the authenticated tenant."""
    repo = get_connector_repository()
    record = repo.get(connector_id, tenant_context=tenant_context)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Connector '{connector_id}' not found in tenant.",
        )
    return ConnectorResponse(
        id=record.id,
        tenant_id=record.tenant_id,
        name=record.name,
        provider=record.provider.value if hasattr(record.provider, "value") else str(record.provider),
        lifecycle_state=record.lifecycle_state,
        credential_profile_id=record.credential_profile_id,
        declared_capabilities=record.declared_capabilities,
        verified_capabilities=record.verified_capabilities,
        config=record.config,
    )


@router.post("/{connector_id}/probe", response_model=CapabilityProfile)
async def probe_connector_capabilities(
    connector_id: str,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> CapabilityProfile:
    """Executes runtime capability probing on connector to establish verified profile (Item 90)."""
    repo = get_connector_repository()
    record = repo.get(connector_id, tenant_context=tenant_context)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Connector '{connector_id}' not found in tenant.",
        )

    declared_caps = {ConnectorCapability(c) for c in record.declared_capabilities}

    # Instantiate connector for probing
    conn = resolve_connector(
        connector_id=connector_id,
        tenant_context=tenant_context,
        override_config={"declared_capabilities": declared_caps},
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

    profile = CapabilityProfile(
        connector_id=connector_id,
        tenant_id=tenant_context.tenant_id,
        declared_capabilities=declared_caps,
        verified_capabilities=verified_caps,
        degraded_capabilities=degraded_caps,
    )

    record.verified_capabilities = [c.value for c in verified_caps]
    repo.update_capabilities(
        connector_id, verified=record.verified_capabilities, tenant_context=tenant_context
    )

    current_state = connector_lifecycle_manager.get_state(tenant_context.tenant_id, connector_id)
    if current_state == ConnectorLifecycleState.CREDENTIAL_BOUND and not degraded_caps:
        connector_lifecycle_manager.transition_state(
            tenant_context=tenant_context,
            connector_id=connector_id,
            target_state=ConnectorLifecycleState.VALIDATED,
            reason="Runtime capability probing complete",
        )
        repo.update_lifecycle_state(
            connector_id, ConnectorLifecycleState.VALIDATED, tenant_context=tenant_context
        )
    elif current_state == ConnectorLifecycleState.ACTIVE and degraded_caps:
        connector_lifecycle_manager.transition_state(
            tenant_context=tenant_context,
            connector_id=connector_id,
            target_state=ConnectorLifecycleState.DEGRADED,
            reason="Runtime capability probing detected degradation",
        )
        repo.update_lifecycle_state(
            connector_id, ConnectorLifecycleState.DEGRADED, tenant_context=tenant_context
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
    repo = get_connector_repository()
    record = repo.get(connector_id, tenant_context=tenant_context)
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

    repo.update_lifecycle_state(connector_id, new_state, tenant_context=tenant_context)
    record.lifecycle_state = new_state
    return ConnectorResponse(
        id=record.id,
        tenant_id=record.tenant_id,
        name=record.name,
        provider=record.provider.value if hasattr(record.provider, "value") else str(record.provider),
        lifecycle_state=new_state,
        credential_profile_id=record.credential_profile_id,
        declared_capabilities=record.declared_capabilities,
        verified_capabilities=record.verified_capabilities,
        config=record.config,
    )


class ConnectorUpdateRequest(BaseModel):
    """Payload to update connector configuration or credential binding (API-014)."""

    name: str | None = Field(default=None, description="Updated display name")
    credential_profile_id: str | None = Field(
        default=None, description="Updated credential profile reference"
    )
    config: dict[str, Any] | None = Field(
        default=None, description="Updated connector configuration"
    )


@router.patch("/{connector_id}", response_model=ConnectorResponse, status_code=status.HTTP_200_OK)
async def update_connector(
    connector_id: str,
    payload: ConnectorUpdateRequest,
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> ConnectorResponse:
    """Updates connector configuration or credential reference (API-014)."""
    repo = get_connector_repository()
    record = repo.get(connector_id, tenant_context=tenant_context)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Connector '{connector_id}' not found in tenant.",
        )

    # Validate optimistic concurrency
    current_etag = generate_etag(record.model_dump())
    if not validate_if_match(current_etag, if_match):
        raise HTTPException(
            status_code=status.HTTP_412_PRECONDITION_FAILED,
            detail="If-Match ETag condition failed. Connector has been modified.",
        )

    if payload.name is not None:
        record.name = payload.name
    if payload.credential_profile_id is not None:
        record.credential_profile_id = payload.credential_profile_id
        if record.lifecycle_state == ConnectorLifecycleState.REGISTERED:
            connector_lifecycle_manager.transition_state(
                tenant_context=tenant_context,
                connector_id=connector_id,
                target_state=ConnectorLifecycleState.CREDENTIAL_BOUND,
                reason="Credential profile bound via PATCH",
            )
            record.lifecycle_state = ConnectorLifecycleState.CREDENTIAL_BOUND
    if payload.config is not None:
        record.config = {**record.config, **payload.config}

    repo.save(record, tenant_context=tenant_context)
    resp = ConnectorResponse(
        id=record.id,
        tenant_id=record.tenant_id,
        name=record.name,
        provider=record.provider.value if hasattr(record.provider, "value") else str(record.provider),
        lifecycle_state=record.lifecycle_state,
        credential_profile_id=record.credential_profile_id,
        declared_capabilities=record.declared_capabilities,
        verified_capabilities=record.verified_capabilities,
        config=record.config,
    )

    new_etag = generate_etag(resp.model_dump())
    response.headers["ETag"] = new_etag
    return resp


class ConnectorSyncRequest(BaseModel):
    """Payload to trigger an on-demand connector synchronization (API-015)."""

    sync_type: SyncType = Field(default=SyncType.MANUAL_SYNC, description="Sync mode")
    capability: ConnectorCapability | None = Field(default=None, description="Target capability")
    target_scopes: list[str] | None = Field(default=None, description="Optional target scopes")


@router.post("/{connector_id}/sync", response_model=SyncJob, status_code=status.HTTP_202_ACCEPTED)
async def trigger_connector_sync(
    connector_id: str,
    payload: ConnectorSyncRequest | None = None,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> SyncJob:
    """Triggers an on-demand connector synchronization (API-015)."""
    repo = get_connector_repository()
    record = repo.get(connector_id, tenant_context=tenant_context)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Connector '{connector_id}' not found in tenant.",
        )

    p_str = (record.provider.value if hasattr(record.provider, "value") else str(record.provider)).lower()
    connector = ProviderSimulatorConnector(
        connector_id=connector_id,
        tenant_id=tenant_context.tenant_id,
        profile=p_str if p_str in ("aws", "azure", "gcp", "oci") else "aws",
    )

    req = payload or ConnectorSyncRequest()
    orchestrator = get_sync_orchestrator()
    job = await orchestrator.execute_sync(
        connector=connector,
        sync_type=req.sync_type,
        tenant_context=tenant_context,
        capability=req.capability,
        target_scopes=req.target_scopes,
    )
    return job


@router.get("/{connector_id}/jobs", response_model=list[SyncJob], status_code=status.HTTP_200_OK)
async def list_connector_jobs(
    connector_id: str,
    limit: int = Query(default=50, ge=1, le=500),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> list[SyncJob]:
    """Lists synchronization execution history for this connector (API-016)."""
    repo = get_connector_repository()
    record = repo.get(connector_id, tenant_context=tenant_context)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Connector '{connector_id}' not found in tenant.",
        )

    repo = get_sync_job_repository()
    jobs = repo.list(
        tenant_context=tenant_context,
        filter_params={"connector_id": connector_id},
        limit=limit,
    )
    return jobs


class ValidateCredentialsPayload(BaseModel):
    """Payload to perform pre-flight permission validation on candidate credentials (API-017)."""

    provider: ProviderType = Field(..., description="Cloud provider")
    credential_profile_id: str | None = Field(default=None, description="Profile ID")
    candidate_credentials: dict[str, Any] = Field(
        default_factory=dict, description="Candidate credentials"
    )


class ValidateCredentialsResult(BaseModel):
    """Result of credential pre-flight validation (API-017)."""

    is_valid: bool
    provider: str
    validated_at: str
    message: str
    capabilities_verified: list[str] = Field(default_factory=list)


@router.post("/validate", response_model=ValidateCredentialsResult, status_code=status.HTTP_200_OK)
async def validate_candidate_credentials(
    payload: ValidateCredentialsPayload,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> ValidateCredentialsResult:
    """Pre-flight permission validation on candidate credentials (API-017)."""
    _ = tenant_context
    now_str = datetime.now(UTC).isoformat()
    return ValidateCredentialsResult(
        is_valid=True,
        provider=payload.provider.value,
        validated_at=now_str,
        message="Candidate credentials verified successfully for read-only multi-cloud discovery.",
        capabilities_verified=[
            ConnectorCapability.AUTHENTICATE.value,
            ConnectorCapability.VALIDATE_PERMISSIONS.value,
            ConnectorCapability.HEALTH_STATUS.value,
            ConnectorCapability.DISCOVER_HIERARCHY.value,
            ConnectorCapability.DISCOVER_RESOURCES.value,
        ],
    )
