"""Credential Lifecycle and Secret Management REST API Endpoints (Prompt 12).

Enforces:
- POST /api/v1/credentials/profiles: Provision profile with pre-flight validation and reference storage (Item 77, 78).
- GET  /api/v1/credentials/profiles: List profiles for tenant (reference-only, no secrets).
- GET  /api/v1/credentials/profiles/{profile_id}: Retrieve profile metadata and state.
- POST /api/v1/credentials/profiles/{profile_id}/rotate: Zero-downtime rotation (Item 78).
- POST /api/v1/credentials/profiles/{profile_id}/complete-rotation: Finalize rotation and retire old version.
- POST /api/v1/credentials/profiles/{profile_id}/retire: Retire credential profile.
- POST /api/v1/credentials/profiles/{profile_id}/revoke: Emergency revocation and secret purge.
- POST /api/v1/credentials/profiles/{profile_id}/bind: Bind connector within tenant (Item 80).
- POST /api/v1/credentials/profiles/{profile_id}/unbind: Unbind connector.
- POST /api/v1/credentials/check-expiries: Trigger expiry tracking and alert emission (Item 79).
- GET  /api/v1/credentials/permissions/{provider}: Least-privilege permission reference (Item 81).
- GET  /api/v1/credentials/export: Safe export guaranteeing negative controls (Item 82).
"""

import logging
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from domain.credentials.models import (
    CredentialCreateRequest,
    CredentialProfileResponse,
    CredentialRotateRequest,
    ExpiryAlert,
)
from domain.credentials.permissions import (
    PermissionReferenceService,
    ProviderPermissionReference,
)
from domain.credentials.service import get_credential_service
from domain.models.enums import ProviderType
from domain.models.exceptions import (
    CredentialNotFoundException,
    CredentialRevokedException,
    CredentialValidationException,
    CrossTenantCredentialAccessException,
)

logger = logging.getLogger("cloudlens.api.credentials")

router = APIRouter(prefix="/api/v1/credentials", tags=["Credentials & Secrets"])


class ConnectorBindRequest(BaseModel):
    """Payload to bind a connector to a credential profile."""

    connector_id: str = Field(..., min_length=2, max_length=128, description="Connector ID")


def _to_response_dto(profile: Any) -> CredentialProfileResponse:
    return CredentialProfileResponse(
        id=profile.id,
        tenant_id=profile.tenant_id,
        name=profile.name,
        provider=profile.provider,
        credential_type=profile.credential_type,
        secret_ref=profile.secret_ref,
        fingerprint=profile.fingerprint,
        version=profile.version,
        rotation_state=profile.rotation_state,
        expires_at=profile.expires_at,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
        last_validated_at=profile.last_validated_at,
        last_rotated_at=profile.last_rotated_at,
        connectors_bound=list(profile.connectors_bound),
        metadata=dict(profile.metadata),
    )


@router.post(
    "/profiles",
    response_model=CredentialProfileResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Provision a new credential profile with pre-flight validation",
)
def create_credential_profile(
    request_data: CredentialCreateRequest,
    request: Request,
    x_tenant_id: str = Header(default="default-tenant", alias="X-Tenant-ID"),
    x_actor_id: str = Header(default="admin", alias="X-Actor-ID"),
) -> CredentialProfileResponse:
    """Provisions a credential profile.

    Validates credential material before persisting anywhere.
    Writes secret material directly to SecretStore and stores only an opaque reference.
    """
    correlation_id = getattr(request.state, "correlation_id", None)
    service = get_credential_service()

    try:
        profile = service.create_profile(
            tenant_id=x_tenant_id,
            name=request_data.name,
            provider=request_data.provider,
            credential_type=request_data.credential_type,
            secret_payload=request_data.secret_payload,
            metadata=request_data.metadata,
            expires_at=request_data.expires_at,
            actor_id=x_actor_id,
            correlation_id=correlation_id,
        )
        return _to_response_dto(profile)
    except CredentialValidationException as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        ) from e


@router.get(
    "/profiles",
    response_model=list[CredentialProfileResponse],
    summary="List credential profiles for the requesting tenant",
)
def list_credential_profiles(
    provider: ProviderType | None = Query(default=None, description="Optional provider filter"),
    x_tenant_id: str = Header(default="default-tenant", alias="X-Tenant-ID"),
) -> list[CredentialProfileResponse]:
    """Lists credential profiles belonging strictly to the caller's tenant."""
    service = get_credential_service()
    profiles = service.list_profiles(tenant_id=x_tenant_id, provider=provider)
    return [_to_response_dto(p) for p in profiles]


@router.get(
    "/profiles/{profile_id}",
    response_model=CredentialProfileResponse,
    summary="Retrieve credential profile metadata and state",
)
def get_credential_profile(
    profile_id: str,
    x_tenant_id: str = Header(default="default-tenant", alias="X-Tenant-ID"),
) -> CredentialProfileResponse:
    """Retrieves a single credential profile enforcing tenant isolation."""
    service = get_credential_service()
    try:
        profile = service.get_profile(tenant_id=x_tenant_id, profile_id=profile_id)
        return _to_response_dto(profile)
    except CredentialNotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except CrossTenantCredentialAccessException as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e


@router.post(
    "/profiles/{profile_id}/rotate",
    response_model=CredentialProfileResponse,
    summary="Initiate zero-downtime credential rotation",
)
def rotate_credential_profile(
    profile_id: str,
    rotate_data: CredentialRotateRequest,
    request: Request,
    x_tenant_id: str = Header(default="default-tenant", alias="X-Tenant-ID"),
    x_actor_id: str = Header(default="admin", alias="X-Actor-ID"),
) -> CredentialProfileResponse:
    """Initiates zero-downtime rotation.

    Validates new credential material before retiring the old version.
    """
    correlation_id = getattr(request.state, "correlation_id", None)
    service = get_credential_service()
    try:
        profile = service.rotate_credential(
            tenant_id=x_tenant_id,
            profile_id=profile_id,
            new_secret_payload=rotate_data.new_secret_payload,
            new_metadata=rotate_data.new_metadata,
            new_expires_at=rotate_data.new_expires_at,
            actor_id=x_actor_id,
            correlation_id=correlation_id,
        )
        return _to_response_dto(profile)
    except CredentialNotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except CrossTenantCredentialAccessException as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e
    except (CredentialValidationException, CredentialRevokedException) as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from e


@router.post(
    "/profiles/{profile_id}/complete-rotation",
    response_model=CredentialProfileResponse,
    summary="Finalize credential rotation",
)
def complete_credential_rotation(
    profile_id: str,
    request: Request,
    purge_previous: bool = Query(
        default=False, description="Whether to purge previous secret from SecretStore"
    ),
    x_tenant_id: str = Header(default="default-tenant", alias="X-Tenant-ID"),
    x_actor_id: str = Header(default="admin", alias="X-Actor-ID"),
) -> CredentialProfileResponse:
    """Finalizes rotation and returns state to ACTIVE."""
    correlation_id = getattr(request.state, "correlation_id", None)
    service = get_credential_service()
    try:
        profile = service.complete_rotation(
            tenant_id=x_tenant_id,
            profile_id=profile_id,
            purge_previous=purge_previous,
            actor_id=x_actor_id,
            correlation_id=correlation_id,
        )
        return _to_response_dto(profile)
    except CredentialNotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except CrossTenantCredentialAccessException as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e


@router.post(
    "/profiles/{profile_id}/retire",
    response_model=CredentialProfileResponse,
    summary="Retire a credential profile",
)
def retire_credential_profile(
    profile_id: str,
    request: Request,
    x_tenant_id: str = Header(default="default-tenant", alias="X-Tenant-ID"),
    x_actor_id: str = Header(default="admin", alias="X-Actor-ID"),
) -> CredentialProfileResponse:
    """Retires a credential profile."""
    correlation_id = getattr(request.state, "correlation_id", None)
    service = get_credential_service()
    try:
        profile = service.retire_credential(
            tenant_id=x_tenant_id,
            profile_id=profile_id,
            actor_id=x_actor_id,
            correlation_id=correlation_id,
        )
        return _to_response_dto(profile)
    except CredentialNotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except CrossTenantCredentialAccessException as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e


@router.post(
    "/profiles/{profile_id}/revoke",
    response_model=CredentialProfileResponse,
    summary="Emergency revocation and secret purge",
)
def revoke_credential_profile(
    profile_id: str,
    request: Request,
    reason: str = Query(default="Emergency security revocation"),
    x_tenant_id: str = Header(default="default-tenant", alias="X-Tenant-ID"),
    x_actor_id: str = Header(default="admin", alias="X-Actor-ID"),
) -> CredentialProfileResponse:
    """Permanently revokes a credential profile and purges secret from store."""
    correlation_id = getattr(request.state, "correlation_id", None)
    service = get_credential_service()
    try:
        profile = service.revoke_credential(
            tenant_id=x_tenant_id,
            profile_id=profile_id,
            actor_id=x_actor_id,
            reason=reason,
            correlation_id=correlation_id,
        )
        return _to_response_dto(profile)
    except CredentialNotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except CrossTenantCredentialAccessException as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e


@router.post(
    "/profiles/{profile_id}/bind",
    response_model=CredentialProfileResponse,
    summary="Bind a connector to a credential profile",
)
def bind_connector(
    profile_id: str,
    bind_data: ConnectorBindRequest,
    request: Request,
    x_tenant_id: str = Header(default="default-tenant", alias="X-Tenant-ID"),
    x_actor_id: str = Header(default="admin", alias="X-Actor-ID"),
) -> CredentialProfileResponse:
    """Binds a connector to an existing credential profile within the tenant."""
    correlation_id = getattr(request.state, "correlation_id", None)
    service = get_credential_service()
    try:
        profile = service.bind_connector(
            tenant_id=x_tenant_id,
            profile_id=profile_id,
            connector_id=bind_data.connector_id,
            actor_id=x_actor_id,
            correlation_id=correlation_id,
        )
        return _to_response_dto(profile)
    except CredentialNotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except CrossTenantCredentialAccessException as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e


@router.post(
    "/profiles/{profile_id}/unbind",
    response_model=CredentialProfileResponse,
    summary="Unbind a connector from a credential profile",
)
def unbind_connector(
    profile_id: str,
    bind_data: ConnectorBindRequest,
    request: Request,
    x_tenant_id: str = Header(default="default-tenant", alias="X-Tenant-ID"),
    x_actor_id: str = Header(default="admin", alias="X-Actor-ID"),
) -> CredentialProfileResponse:
    """Unbinds a connector from a credential profile."""
    correlation_id = getattr(request.state, "correlation_id", None)
    service = get_credential_service()
    try:
        profile = service.unbind_connector(
            tenant_id=x_tenant_id,
            profile_id=profile_id,
            connector_id=bind_data.connector_id,
            actor_id=x_actor_id,
            correlation_id=correlation_id,
        )
        return _to_response_dto(profile)
    except CredentialNotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except CrossTenantCredentialAccessException as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e


@router.post(
    "/check-expiries",
    response_model=list[ExpiryAlert],
    summary="Scan credential expiries and fire milestone alerts",
)
def check_credential_expiries(
    x_tenant_id: str = Header(default="default-tenant", alias="X-Tenant-ID"),
) -> list[ExpiryAlert]:
    """Scans credential profiles and emits alerts at 30, 14, 3 days and expiration."""
    service = get_credential_service()
    return service.check_expiries(tenant_id=x_tenant_id)


@router.get(
    "/permissions/{provider}",
    response_model=ProviderPermissionReference,
    summary="Authoritative least-privilege permission reference for onboarding wizard",
)
def get_provider_permissions_reference(
    provider: ProviderType,
) -> ProviderPermissionReference:
    """Returns the documented least-privilege permission reference for a cloud provider (Prompt 12 Item 81)."""
    try:
        return PermissionReferenceService.get_reference(provider)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.get(
    "/export",
    response_model=list[CredentialProfileResponse],
    summary="Export sanitized credential profiles for compliance",
)
def export_credential_profiles(
    x_tenant_id: str = Header(default="default-tenant", alias="X-Tenant-ID"),
) -> list[CredentialProfileResponse]:
    """Exports sanitized credential profiles containing strictly zero credential material."""
    service = get_credential_service()
    return service.export_profiles(x_tenant_id)
