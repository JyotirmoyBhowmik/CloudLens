"""CloudLens Thirteen-Step Onboarding Wizard API Routes (Prompt 15 Items 100-103).

Enforces:
- Prompt 15 Item 100: Thirteen-step onboarding flow with save-and-resume.
- Prompt 15 Item 101: Permission reference before credentials (Step 2).
- Prompt 15 Item 102: Permission pre-flight and degradation reporting (Step 5).
- Prompt 15 Item 103: Pre-completion estate sizing and cost impact estimates (Step 12).
- Security rule: If validation fails, credentials are NEVER persisted and error is shown verbatim.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from api.cloudlens_api.tenant_context import get_authenticated_tenant_context
from connectors.wizard.service import get_wizard_service
from domain.models.enums import ProviderType, WizardStep
from domain.models.exceptions import (
    CredentialValidationFailedException,
    InvalidWizardStepException,
    WizardSessionNotFoundException,
)
from domain.tenant.context import TenantContext
from domain.wizard.models import (
    PermissionConsequenceReport,
    PreCompletionEstimate,
    WizardSession,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/wizard", tags=["Onboarding Wizard"])


class StartSessionResponse(BaseModel):
    session: WizardSession
    is_resumed: bool


class SaveStepRequest(BaseModel):
    step_data: dict[str, Any] = Field(default_factory=dict, description="Step configuration data")


class ValidateCredentialsRequest(BaseModel):
    credentials: dict[str, Any] = Field(
        ..., description="Provider credential parameters to validate"
    )


class ValidatePermissionsRequest(BaseModel):
    simulate_missing_permissions: list[str] = Field(
        default_factory=list, description="Optional permissions to treat as ungranted for testing"
    )


class CompleteWizardResponse(BaseModel):
    status: str
    session_id: str
    connector_id: str
    credential_profile_id: str | None = None
    initial_sync_job_id: str
    sync_status: str
    rows_ingested: int


@router.post("/sessions", response_model=StartSessionResponse, status_code=status.HTTP_201_CREATED)
async def start_wizard_session(
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> StartSessionResponse:
    """Starts or resumes a thirteen-step onboarding wizard session (Item 100)."""
    service = get_wizard_service()
    session = service.start_session(user_id=tenant_context.user_id, tenant_context=tenant_context)
    is_resumed = len(session.completed_steps) > 0
    return StartSessionResponse(session=session, is_resumed=is_resumed)


@router.get("/sessions/current", response_model=WizardSession)
async def get_current_session(
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> WizardSession:
    """Retrieves the active in-progress wizard session for the authenticated user."""
    service = get_wizard_service()
    session = service._wizard_repo.get_active_for_user(
        user_id=tenant_context.user_id, tenant_context=tenant_context
    )
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active wizard session found for current user.",
        )
    return session


@router.get("/sessions/{session_id}", response_model=WizardSession)
async def get_session_by_id(
    session_id: str,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> WizardSession:
    """Retrieves a wizard session by identifier."""
    service = get_wizard_service()
    try:
        return service.get_session(session_id=session_id, tenant_context=tenant_context)
    except WizardSessionNotFoundException as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.message) from exc


@router.post("/sessions/{session_id}/step/{step}", response_model=WizardSession)
async def save_wizard_step(
    session_id: str,
    step: WizardStep,
    payload: SaveStepRequest,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> WizardSession:
    """Saves progress for a wizard step and advances to next step (Item 100)."""
    service = get_wizard_service()
    try:
        return await service.save_step(
            session_id=session_id,
            step=step,
            step_payload=payload.step_data,
            tenant_context=tenant_context,
        )
    except InvalidWizardStepException as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.message
        ) from exc
    except WizardSessionNotFoundException as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.message) from exc


@router.get("/permissions-reference/{provider}")
async def get_permissions_reference(
    provider: ProviderType,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> dict[str, Any]:
    """Returns least-privilege permission requirements before credentials are requested (Item 101)."""
    _ = tenant_context
    service = get_wizard_service()
    return service.get_permission_reference(provider)


@router.post("/sessions/{session_id}/validate-credentials")
async def validate_credentials(
    session_id: str,
    payload: ValidateCredentialsRequest,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> dict[str, Any]:
    """Pre-flight validates credentials. If invalid, credentials are NEVER persisted and error is returned verbatim (Item 100/101)."""
    service = get_wizard_service()
    try:
        return await service.validate_credentials_step(
            session_id=session_id,
            credentials_payload=payload.credentials,
            tenant_context=tenant_context,
        )
    except CredentialValidationFailedException as exc:
        # Surface provider error verbatim without persisting credentials
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error_code": "CREDENTIAL_VALIDATION_FAILED",
                "provider": exc.provider,
                "verbatim_error": exc.verbatim_error,
                "message": f"Credential validation failed for {exc.provider}: {exc.verbatim_error}",
            },
        ) from exc


@router.post(
    "/sessions/{session_id}/validate-permissions", response_model=list[PermissionConsequenceReport]
)
async def validate_permissions(
    session_id: str,
    payload: ValidatePermissionsRequest,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> list[PermissionConsequenceReport]:
    """Evaluates each permission individually and reports consequences of gaps (Item 102)."""
    service = get_wizard_service()
    return await service.validate_permissions_step(
        session_id=session_id,
        simulate_missing_permissions=payload.simulate_missing_permissions,
        tenant_context=tenant_context,
    )


@router.get("/sessions/{session_id}/discover-scopes")
async def discover_scopes(
    session_id: str,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> list[dict[str, Any]]:
    """Probes provider hierarchy to discover selectable accounts/subscriptions (Step 6)."""
    service = get_wizard_service()
    return await service.discover_scopes_step(session_id=session_id, tenant_context=tenant_context)


@router.get("/sessions/{session_id}/estimates", response_model=PreCompletionEstimate)
async def get_estimates(
    session_id: str,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> PreCompletionEstimate:
    """Calculates pre-completion estate sizing, duration, metric volume, and provider cost impact (Item 103)."""
    service = get_wizard_service()
    return service.calculate_pre_completion_estimates(
        session_id=session_id, tenant_context=tenant_context
    )


@router.post("/sessions/{session_id}/complete", response_model=CompleteWizardResponse)
async def complete_wizard(
    session_id: str,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> CompleteWizardResponse:
    """Finalizes wizard, registers connector, binds credentials, initializes schedules, and launches initial sync (Item 100)."""
    service = get_wizard_service()
    result = await service.complete_wizard(session_id=session_id, tenant_context=tenant_context)
    return CompleteWizardResponse(**result)
