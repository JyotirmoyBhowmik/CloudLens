"""Explanation Layer API Routes (Prompt 40).

Exposes:
- Resource explanation suite (all 11 standard panels + 17-field information model)
- Specific explanation panel retrieval
- Data freshness surface (Pricing, Billing, Usage, Inventory)
- Contextual alert acknowledgement
- Mechanical explanation attachment validator
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field

from api.cloudlens_api.tenant_context import get_authenticated_tenant_context
from domain.alerting.models import ContextualAlert
from domain.explanation.models import (
    FreshnessSurfaceOverview,
    ResourceExplanationSuite,
    StandardExplanationPanel,
    StandardExplanationPanelType,
)
from domain.explanation.service import ExplanationService, get_explanation_service
from domain.tenant.context import TenantContext

router = APIRouter(prefix="/api/v1/explanation", tags=["Explanation Layer"])


class AcknowledgeContextualAlertRequest(BaseModel):
    """Payload for acknowledging an inline contextual alert."""

    actor: str = Field(..., min_length=1, description="Actor username acknowledging the alert")
    note: str | None = Field(default=None, description="Optional explanation or rationale note")


class ValidateExplanationRequest(BaseModel):
    """Payload for mechanically validating an explanation payload."""

    payload: dict[str, Any] = Field(..., description="Cost explanation dictionary to validate")


class ValidateExplanationResponse(BaseModel):
    is_valid: bool = Field(..., description="Whether the payload satisfies explanation rules")
    message: str = Field(..., description="Status message or error detail")


@router.get(
    "/freshness-surface", response_model=FreshnessSurfaceOverview, status_code=status.HTTP_200_OK
)
async def get_freshness_surface(
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    explanation_service: ExplanationService = Depends(get_explanation_service),
) -> FreshnessSurfaceOverview:
    """Returns the data freshness surface across Pricing, Billing, Usage, and Inventory."""
    return explanation_service.get_freshness_surface(tenant_context=tenant_context)


@router.get(
    "/panel/{resource_or_sku}/{panel_type}",
    response_model=StandardExplanationPanel,
    status_code=status.HTTP_200_OK,
)
async def get_explanation_panel(
    resource_or_sku: str,
    panel_type: StandardExplanationPanelType,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    explanation_service: ExplanationService = Depends(get_explanation_service),
) -> StandardExplanationPanel:
    """Retrieves one of the eleven standard explanation panels for a resource or SKU."""
    return explanation_service.get_single_explanation_panel(
        resource_id_or_sku=resource_or_sku,
        panel_type=panel_type,
        tenant_context=tenant_context,
    )


@router.get(
    "/suite/{resource_or_sku}",
    response_model=ResourceExplanationSuite,
    status_code=status.HTTP_200_OK,
)
async def get_explanation_suite(
    resource_or_sku: str,
    provider: str = Query(default="aws", description="Cloud provider"),
    region: str = Query(default="us-east-1", description="Datacenter region"),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    explanation_service: ExplanationService = Depends(get_explanation_service),
) -> ResourceExplanationSuite:
    """Retrieves the full explanation suite (all 11 panels + 17-field info model) for a resource."""
    return explanation_service.get_resource_explanation_suite(
        resource_id_or_sku=resource_or_sku,
        tenant_context=tenant_context,
        provider=provider,
        region=region,
    )


@router.post(
    "/alerts/{alert_id}/acknowledge",
    response_model=ContextualAlert,
    status_code=status.HTTP_200_OK,
)
async def acknowledge_alert(
    alert_id: str,
    body: AcknowledgeContextualAlertRequest,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    explanation_service: ExplanationService = Depends(get_explanation_service),
) -> ContextualAlert:
    """Acknowledges an inline contextual alert with recorded actor and timestamp."""
    return explanation_service.acknowledge_alert(
        alert_id=alert_id,
        actor=body.actor,
        note=body.note,
        tenant_context=tenant_context,
    )


@router.post(
    "/validate-attachment",
    response_model=ValidateExplanationResponse,
    status_code=status.HTTP_200_OK,
)
async def validate_attachment(
    body: ValidateExplanationRequest,
    explanation_service: ExplanationService = Depends(get_explanation_service),
) -> ValidateExplanationResponse:
    """Mechanically checks that an explanation payload satisfies Mandate M2 requirements."""
    try:
        explanation_service.verify_explanation_attachment(body.payload)
        return ValidateExplanationResponse(
            is_valid=True,
            message="Payload satisfies explanation attachment requirements.",
        )
    except Exception as exc:
        return ValidateExplanationResponse(
            is_valid=False,
            message=str(exc),
        )
