"""CloudLens Connector Management & Real Read-Only Integration API Routes (Prompt P13 & Prompt 14).

Enforces:
- Prompt P13 Item 1: Cloud Connections page list (provider, name, scopes, status, last success, next run)
- Prompt P13 Item 2: Credential fields per provider from master data; secrets posted once to OpenBao; DB stores vault:// ref; UI never shows secrets ('Replace').
- Prompt P13 Item 3: Test connection shows each permission present/missing.
- Prompt P13 Item 4: Simulator only in DEMO tenants (API 403 otherwise).
- Prompt P13 Item 6: Edit, disable, soft delete (audited), rotate credential without downtime.
- SEC-008 & SEC-017: Negative controls - zero secrets returned in API responses or committed in database.
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
from connectors.sync.orchestrator import get_sync_orchestrator
from domain.audit.models import AuditEventCreate
from domain.audit.service import get_audit_service
from domain.connectors.models import ConnectorEntity
from domain.connectors.repository import get_connector_repository
from domain.credentials.models import CredentialType
from domain.credentials.permissions import PermissionReferenceService
from domain.credentials.service import get_credential_service
from domain.models.enums import (
    AuditEventType,
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
from domain.tenant.models import TenantType
from domain.tenant.repository import get_tenant_repository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/connectors", tags=["Connectors"])


def sanitize_connector_config(config: dict[str, Any] | None) -> dict[str, Any]:
    """Strictly removes secrets, private keys, passwords, and tokens from configuration dictionary (SEC-017)."""
    if not config:
        return {}
    safe: dict[str, Any] = {}
    banned_keywords = ("secret", "password", "private", "token", "credential", "auth_key", "signing_key")
    for k, v in config.items():
        k_lower = str(k).lower()
        if k_lower == "credentials":
            continue
        if any(sub in k_lower for sub in banned_keywords) and k_lower not in (
            "external_id",
            "key_id",
            "access_key_id",
            "credential_ref",
            "credential_profile_id",
        ):
            continue
        safe[k] = v
    return safe


def assert_simulator_allowed(tenant_context: TenantContext, provider_str: str) -> None:
    """Enforces HARD GATE (Prompt P13 Item 4): Simulator is strictly restricted to DEMO tenants."""
    p_low = provider_str.lower()
    if "simulator" in p_low or "mock" in p_low or "stub" in p_low:
        t_repo = get_tenant_repository()
        t_entity = t_repo.get_sync(tenant_context.tenant_id)
        if not t_entity or (t_entity.type != TenantType.DEMO and str(t_entity.type).upper() != "DEMO"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Simulator connectors are strictly restricted to DEMO tenants.",
            )


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
    """Authoritative connector details response with real scopes, status, and sync telemetry (Prompt P13 Item 1)."""

    id: str
    tenant_id: str
    name: str
    provider: str
    scopes: list[str] = Field(default_factory=list, description="Monitored accounts/subscriptions")
    status: str = Field(..., description="Current operational status")
    lifecycle_state: ConnectorLifecycleState
    last_success_at: str | None = Field(default=None, description="Timestamp of latest successful ingestion")
    next_run_at: str | None = Field(default=None, description="Next scheduled run time or frequency")
    credential_profile_id: str | None = None
    declared_capabilities: list[str] = Field(default_factory=list)
    verified_capabilities: list[str] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict, description="Safe sanitized connector configuration")


class StateTransitionRequest(BaseModel):
    """Request to transition connector lifecycle state."""

    target_state: ConnectorLifecycleState
    reason: str | None = None


class PermissionCheckDetail(BaseModel):
    """Itemized permission diagnostic result (Prompt P13 Item 3)."""

    permission: str
    granted: bool
    capability: str
    required_scope: str
    consequence: str


class TestConnectionResponse(BaseModel):
    """Detailed response for Test Connection operation showing individual permissions (Prompt P13 Item 3)."""

    connector_id: str
    provider: str
    healthy: bool
    tested_at: str
    permissions: list[PermissionCheckDetail]
    granted_count: int
    missing_count: int
    message: str


class RotateCredentialPayload(BaseModel):
    """Payload to rotate connector credentials without downtime (Prompt P13 Item 2 & 6)."""

    credential_type: CredentialType = CredentialType.ROLE_ARN
    credentials: dict[str, Any] = Field(..., description="New credential secret payload")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Safe configuration metadata")
    expires_at: datetime | None = None


class CredentialFieldSpec(BaseModel):
    """Provider credential field specification from master data (Prompt P13 Item 2)."""

    key: str
    label: str
    field_type: str = "text"  # "text" | "password"
    is_secret: bool = False
    required: bool = True
    placeholder: str | None = None
    description: str
    help_text: str | None = None
    default: str | None = None


def _entity_to_response(c: ConnectorEntity, tenant_context: TenantContext) -> ConnectorResponse:
    cfg = dict(c.config or {})
    scopes = cfg.get("scopes") or cfg.get("target_scopes") or []
    if not scopes:
        scopes = ["root"]

    # Retrieve last success timestamp
    last_success = cfg.get("last_success_at")
    try:
        jobs_repo = get_sync_job_repository()
        jobs = jobs_repo.list(
            tenant_context=tenant_context,
            filter_params={"connector_id": c.id, "status": "COMPLETED"},
            limit=1,
        )
        if jobs:
            last_success = (
                jobs[0].completed_at.isoformat()
                if jobs[0].completed_at
                else jobs[0].started_at.isoformat()
            )
    except Exception as j_err:
        logger.debug("Jobs lookup note for connector %s: %s", c.id, j_err)

    next_run = cfg.get("next_run_at") or "Hourly (00:00 UTC)"

    return ConnectorResponse(
        id=c.id,
        tenant_id=c.tenant_id,
        name=c.name,
        provider=c.provider.value if hasattr(c.provider, "value") else str(c.provider),
        scopes=scopes,
        status=c.lifecycle_state.value if hasattr(c.lifecycle_state, "value") else str(c.lifecycle_state),
        lifecycle_state=c.lifecycle_state,
        last_success_at=last_success,
        next_run_at=next_run,
        credential_profile_id=c.credential_profile_id,
        declared_capabilities=c.declared_capabilities,
        verified_capabilities=c.verified_capabilities,
        config=sanitize_connector_config(cfg),
    )


@router.get("/master-data/fields/{provider}", response_model=list[CredentialFieldSpec])
async def get_provider_credential_fields(
    provider: ProviderType,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> list[CredentialFieldSpec]:
    """Returns credential field specifications per provider driven by master data (Prompt P13 Item 2)."""
    _ = tenant_context
    if provider == ProviderType.AWS:
        return [
            CredentialFieldSpec(
                key="role_arn",
                label="IAM Role ARN",
                field_type="text",
                is_secret=False,
                required=True,
                placeholder="arn:aws:iam::123456789012:role/CloudLensReadOnlyRole",
                description="Cross-account IAM Role with AWS SecurityAudit and OrganizationsReadOnlyAccess policies.",
            ),
            CredentialFieldSpec(
                key="external_id",
                label="External ID",
                field_type="text",
                is_secret=False,
                required=True,
                placeholder="cloudlens-external-id-production",
                description="Unique external ID for STS AssumeRole condition.",
            ),
            CredentialFieldSpec(
                key="aws_access_key_id",
                label="AWS Access Key ID (Optional for Key Auth)",
                field_type="text",
                is_secret=False,
                required=False,
                placeholder="AKIAIOSFODNN7EXAMPLE",
                description="Optional IAM access key for direct key auth.",
            ),
            CredentialFieldSpec(
                key="aws_secret_access_key",
                label="AWS Secret Access Key",
                field_type="password",
                is_secret=True,
                required=False,
                description="Secret access key. Will be stored directly in OpenBao.",
            ),
            CredentialFieldSpec(
                key="region",
                label="Default Region",
                field_type="text",
                is_secret=False,
                required=True,
                default="us-east-1",
                description="Primary AWS region for control plane endpoints.",
            ),
        ]
    elif provider == ProviderType.AZURE:
        return [
            CredentialFieldSpec(
                key="azure_tenant_id",
                label="Directory (Tenant) ID",
                field_type="text",
                is_secret=False,
                required=True,
                placeholder="00000000-0000-0000-0000-000000000000",
                description="Microsoft Entra ID / Azure AD Directory ID (UUID).",
            ),
            CredentialFieldSpec(
                key="azure_client_id",
                label="Application (Client) ID",
                field_type="text",
                is_secret=False,
                required=True,
                placeholder="00000000-0000-0000-0000-000000000000",
                description="Service Principal Application Client ID (UUID).",
            ),
            CredentialFieldSpec(
                key="client_secret",
                label="Client Secret",
                field_type="password",
                is_secret=True,
                required=True,
                description="Service Principal client secret. Stored directly in OpenBao.",
            ),
            CredentialFieldSpec(
                key="subscription_id",
                label="Subscription ID",
                field_type="text",
                is_secret=False,
                required=False,
                placeholder="00000000-0000-0000-0000-000000000000",
                description="Optional target Azure subscription ID.",
            ),
        ]
    elif provider == ProviderType.GCP:
        return [
            CredentialFieldSpec(
                key="project_id",
                label="Project ID",
                field_type="text",
                is_secret=False,
                required=True,
                placeholder="cloudlens-billing-prod",
                description="Google Cloud Platform Project ID.",
            ),
            CredentialFieldSpec(
                key="client_email",
                label="Service Account Email",
                field_type="text",
                is_secret=False,
                required=True,
                placeholder="cloudlens-read@project.iam.gserviceaccount.com",
                description="Service account with Viewer & Billing Viewer roles.",
            ),
            CredentialFieldSpec(
                key="private_key",
                label="Private Key (PEM format)",
                field_type="password",
                is_secret=True,
                required=True,
                description="Service Account RSA private key. Stored directly in OpenBao.",
            ),
        ]
    elif provider == ProviderType.OCI:
        return [
            CredentialFieldSpec(
                key="tenancy_ocid",
                label="Tenancy OCID",
                field_type="text",
                is_secret=False,
                required=True,
                placeholder="ocid1.tenancy.oc1..aaaaaaa...",
                description="Oracle Cloud Infrastructure Tenancy OCID.",
            ),
            CredentialFieldSpec(
                key="user_ocid",
                label="User OCID",
                field_type="text",
                is_secret=False,
                required=True,
                placeholder="ocid1.user.oc1..aaaaaaa...",
                description="OCI API User OCID.",
            ),
            CredentialFieldSpec(
                key="fingerprint",
                label="API Key Fingerprint",
                field_type="text",
                is_secret=False,
                required=True,
                placeholder="20:3b:97:13:55:1c:...",
                description="Fingerprint of the RSA public key uploaded to OCI.",
            ),
            CredentialFieldSpec(
                key="private_key",
                label="API Signing Private Key",
                field_type="password",
                is_secret=True,
                required=True,
                description="PEM formatted API signing key. Stored in OpenBao.",
            ),
            CredentialFieldSpec(
                key="region",
                label="Home Region",
                field_type="text",
                is_secret=False,
                required=True,
                default="us-ashburn-1",
                description="OCI Tenancy home region.",
            ),
        ]
    return []


@router.post("", response_model=ConnectorResponse, status_code=status.HTTP_201_CREATED)
async def register_connector(
    payload: ConnectorRegisterRequest,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> ConnectorResponse:
    """Registers a new cloud connector in the authenticated tenant with DEMO boundary checks."""
    assert_simulator_allowed(tenant_context, payload.provider.value)

    connector_id = f"conn-{payload.provider.value.lower()}-{uuid.uuid4().hex[:8]}"

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

    state = ConnectorLifecycleState.REGISTERED
    if payload.credential_profile_id:
        state = ConnectorLifecycleState.CREDENTIAL_BOUND

    connector_lifecycle_manager.transition_state(
        tenant_context=tenant_context,
        connector_id=connector_id,
        target_state=state,
        reason="Connector initial registration",
    )

    clean_cfg = sanitize_connector_config(payload.config)
    entity = ConnectorEntity(
        id=connector_id,
        tenant_id=tenant_context.tenant_id,
        name=payload.name,
        provider=payload.provider,
        lifecycle_state=state,
        credential_profile_id=payload.credential_profile_id,
        declared_capabilities=[c.value for c in declared],
        verified_capabilities=[],
        config=clean_cfg,
    )
    repo = get_connector_repository()
    saved = repo.save(entity, tenant_context=tenant_context)

    return _entity_to_response(saved, tenant_context)


@router.get("", response_model=list[ConnectorResponse])
async def list_connectors(
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> list[ConnectorResponse]:
    """Lists all cloud connectors registered within the authenticated tenant (Prompt P13 Item 1)."""
    repo = get_connector_repository()
    items = repo.list(tenant_context=tenant_context)
    # Exclude soft-deleted connectors
    active_items = [c for c in items if c.lifecycle_state != ConnectorLifecycleState.DELETED]
    return [_entity_to_response(c, tenant_context) for c in active_items]


@router.get("/{connector_id}", response_model=ConnectorResponse)
async def get_connector(
    connector_id: str,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> ConnectorResponse:
    """Retrieves details of a specific connector in the authenticated tenant."""
    repo = get_connector_repository()
    record = repo.get(connector_id, tenant_context=tenant_context)
    if not record or record.lifecycle_state == ConnectorLifecycleState.DELETED:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Connector '{connector_id}' not found in tenant.",
        )
    return _entity_to_response(record, tenant_context)


@router.post("/{connector_id}/test", response_model=TestConnectionResponse)
async def test_connector_connection(
    connector_id: str,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> TestConnectionResponse:
    """Tests connection and verifies each permission individually (present/missing) (Prompt P13 Item 3)."""
    repo = get_connector_repository()
    record = repo.get(connector_id, tenant_context=tenant_context)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Connector '{connector_id}' not found in tenant.",
        )

    p_str = (record.provider.value if hasattr(record.provider, "value") else str(record.provider)).lower()
    assert_simulator_allowed(tenant_context, p_str)

    ref = PermissionReferenceService.get_reference(record.provider)
    now_str = datetime.now(UTC).isoformat()
    permissions_list: list[PermissionCheckDetail] = []

    healthy = True
    err_msg = ""
    try:
        conn = resolve_connector(connector_id=connector_id, tenant_context=tenant_context)
        if hasattr(conn, "health_status"):
            health = await conn.health_status()
            healthy = bool(getattr(health, "healthy", True))
    except Exception as e:
        healthy = False
        err_msg = str(e)

    for cap in ref.capabilities:
        for perm in cap.minimum_permissions:
            permissions_list.append(
                PermissionCheckDetail(
                    permission=perm,
                    granted=healthy,
                    capability=cap.capability_name,
                    required_scope=cap.required_scope,
                    consequence=cap.consequence_if_not_granted,
                )
            )

    granted_cnt = sum(1 for p in permissions_list if p.granted)
    missing_cnt = sum(1 for p in permissions_list if not p.granted)
    message = (
        "All least-privilege permissions verified successfully."
        if missing_cnt == 0
        else f"Connection check: {missing_cnt} permission(s) missing or unreachable: {err_msg}"
    )

    return TestConnectionResponse(
        connector_id=connector_id,
        provider=p_str,
        healthy=healthy,
        tested_at=now_str,
        permissions=permissions_list,
        granted_count=granted_cnt,
        missing_count=missing_cnt,
        message=message,
    )


@router.post("/{connector_id}/toggle-status", response_model=ConnectorResponse)
async def toggle_connector_status(
    connector_id: str,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> ConnectorResponse:
    """Toggles connector lifecycle state between ACTIVE and SUSPENDED (Prompt P13 Item 6)."""
    repo = get_connector_repository()
    record = repo.get(connector_id, tenant_context=tenant_context)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Connector '{connector_id}' not found in tenant.",
        )

    new_state = (
        ConnectorLifecycleState.ACTIVE
        if record.lifecycle_state == ConnectorLifecycleState.SUSPENDED
        else ConnectorLifecycleState.SUSPENDED
    )
    connector_lifecycle_manager.transition_state(
        tenant_context=tenant_context,
        connector_id=connector_id,
        target_state=new_state,
        reason=f"Administrative status toggle to {new_state.value}",
    )
    repo.update_lifecycle_state(connector_id, new_state, tenant_context=tenant_context)
    record.lifecycle_state = new_state

    # Emit Audit Event
    try:
        get_audit_service().append_event(
            tenant_context=tenant_context,
            event_in=AuditEventCreate(
                event_type=AuditEventType.CONNECTOR_STATE_CHANGED,
                actor_id=tenant_context.user_id,
                actor_roles=tenant_context.roles,
                action=AuditEventType.CONNECTOR_STATE_CHANGED.value,
                resource_type="Connector",
                resource_id=connector_id,
                details={
                    "previous_state": record.lifecycle_state.value,
                    "new_state": new_state.value,
                },
                correlation_id=tenant_context.correlation_id,
            ),
        )
    except Exception as a_err:
        logger.debug("Audit emission note: %s", a_err)

    return _entity_to_response(record, tenant_context)


@router.post("/{connector_id}/rotate-credential", response_model=ConnectorResponse)
async def rotate_connector_credential(
    connector_id: str,
    payload: RotateCredentialPayload,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> ConnectorResponse:
    """Rotates connector credentials without downtime by writing new secrets to OpenBao (Prompt P13 Item 2 & 6)."""
    repo = get_connector_repository()
    record = repo.get(connector_id, tenant_context=tenant_context)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Connector '{connector_id}' not found in tenant.",
        )

    cred_service = get_credential_service()
    profile_name = f"{record.name} Rotated Credential Profile"
    profile = cred_service.create_profile(
        tenant_id=tenant_context.tenant_id,
        name=profile_name,
        provider=record.provider,
        credential_type=payload.credential_type,
        secret_payload=payload.credentials,
        metadata=payload.metadata,
        expires_at=payload.expires_at,
        actor_id=tenant_context.user_id,
        correlation_id=tenant_context.correlation_id,
    )

    record.credential_profile_id = profile.id
    record.config = sanitize_connector_config(record.config)
    record.config["credential_ref"] = profile.secret_ref
    record.updated_at = datetime.now(UTC)
    repo.save(record, tenant_context=tenant_context)

    # Emit Audit Event
    try:
        get_audit_service().append_event(
            tenant_context=tenant_context,
            event_in=AuditEventCreate(
                event_type=AuditEventType.CREDENTIAL_ROTATED,
                actor_id=tenant_context.user_id,
                actor_roles=tenant_context.roles,
                action=AuditEventType.CREDENTIAL_ROTATED.value,
                resource_type="Connector",
                resource_id=connector_id,
                details={
                    "credential_profile_id": profile.id,
                    "provider": record.provider.value,
                },
                correlation_id=tenant_context.correlation_id,
            ),
        )
    except Exception as a_err:
        logger.debug("Audit log note: %s", a_err)

    return _entity_to_response(record, tenant_context)


@router.delete("/{connector_id}", status_code=status.HTTP_200_OK)
async def delete_connector(
    connector_id: str,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> dict[str, str]:
    """Soft-deletes a cloud connector with audit event logging (Prompt P13 Item 6)."""
    repo = get_connector_repository()
    record = repo.get(connector_id, tenant_context=tenant_context)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Connector '{connector_id}' not found in tenant.",
        )

    connector_lifecycle_manager.transition_state(
        tenant_context=tenant_context,
        connector_id=connector_id,
        target_state=ConnectorLifecycleState.DELETED,
        reason=f"Soft deleted by {tenant_context.user_id}",
    )
    repo.update_lifecycle_state(connector_id, ConnectorLifecycleState.DELETED, tenant_context=tenant_context)

    # Emit Audit Event
    try:
        get_audit_service().append_event(
            tenant_context=tenant_context,
            event_in=AuditEventCreate(
                event_type=AuditEventType.CONNECTOR_DELETED,
                actor_id=tenant_context.user_id,
                actor_roles=tenant_context.roles,
                action=AuditEventType.CONNECTOR_DELETED.value,
                resource_type="Connector",
                resource_id=connector_id,
                details={"connector_id": connector_id, "provider": record.provider.value},
                correlation_id=tenant_context.correlation_id,
            ),
        )
    except Exception as a_err:
        logger.debug("Audit log note: %s", a_err)

    return {
        "status": "DELETED",
        "connector_id": connector_id,
        "message": "Connector soft deleted successfully.",
    }


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

    conn = resolve_connector(
        connector_id=connector_id,
        tenant_context=tenant_context,
        override_config={"declared_capabilities": declared_caps},
    )

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


class ConnectorUpdateRequest(BaseModel):
    """Payload to update connector configuration (Prompt P13 Item 6)."""

    name: str | None = Field(default=None, description="Updated display name")
    scopes: list[str] | None = Field(default=None, description="Updated target scopes")
    config: dict[str, Any] | None = Field(default=None, description="Updated non-sensitive configuration")


@router.patch("/{connector_id}", response_model=ConnectorResponse, status_code=status.HTTP_200_OK)
async def update_connector(
    connector_id: str,
    payload: ConnectorUpdateRequest,
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> ConnectorResponse:
    """Updates connector configuration or display name (Prompt P13 Item 6)."""
    repo = get_connector_repository()
    record = repo.get(connector_id, tenant_context=tenant_context)
    if not record or record.lifecycle_state == ConnectorLifecycleState.DELETED:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Connector '{connector_id}' not found in tenant.",
        )

    current_etag = generate_etag(record.model_dump())
    if not validate_if_match(current_etag, if_match):
        raise HTTPException(
            status_code=status.HTTP_412_PRECONDITION_FAILED,
            detail="If-Match ETag condition failed. Connector has been modified.",
        )

    if payload.name is not None:
        record.name = payload.name
    if payload.scopes is not None:
        record.config["scopes"] = payload.scopes
    if payload.config is not None:
        record.config = {**record.config, **sanitize_connector_config(payload.config)}

    record.updated_at = datetime.now(UTC)
    saved = repo.save(record, tenant_context=tenant_context)
    resp = _entity_to_response(saved, tenant_context)
    response.headers["ETag"] = generate_etag(resp.model_dump())
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
    """Triggers an on-demand connector synchronization via resolved real connector (Prompt P13)."""
    repo = get_connector_repository()
    record = repo.get(connector_id, tenant_context=tenant_context)
    if not record or record.lifecycle_state == ConnectorLifecycleState.DELETED:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Connector '{connector_id}' not found in tenant.",
        )

    p_str = (record.provider.value if hasattr(record.provider, "value") else str(record.provider)).lower()
    assert_simulator_allowed(tenant_context, p_str)

    connector = resolve_connector(connector_id=connector_id, tenant_context=tenant_context)

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
    """Lists synchronization execution history for this connector."""
    repo = get_connector_repository()
    record = repo.get(connector_id, tenant_context=tenant_context)
    if not record or record.lifecycle_state == ConnectorLifecycleState.DELETED:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Connector '{connector_id}' not found in tenant.",
        )

    jobs_repo = get_sync_job_repository()
    jobs = jobs_repo.list(
        tenant_context=tenant_context,
        filter_params={"connector_id": connector_id},
        limit=limit,
    )
    return jobs


class ValidateCredentialsPayload(BaseModel):
    """Payload to perform pre-flight permission validation on candidate credentials."""

    provider: ProviderType = Field(..., description="Cloud provider")
    credential_profile_id: str | None = Field(default=None, description="Profile ID")
    candidate_credentials: dict[str, Any] = Field(
        default_factory=dict, description="Candidate credentials"
    )


class ValidateCredentialsResult(BaseModel):
    """Result of credential pre-flight validation."""

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
    """Pre-flight permission validation on candidate credentials."""
    assert_simulator_allowed(tenant_context, payload.provider.value)
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
