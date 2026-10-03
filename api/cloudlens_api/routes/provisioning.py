"""Cost-Aware Provisioning Gate REST API Endpoints (API-051 / Prompt 55).

Enforces:
- POST /api/v1/provisioning-requests/estimates - Save priced estimate with validity TTL
- GET /api/v1/provisioning-requests/estimates/{id} - Get saved estimate
- POST /api/v1/provisioning-requests - Submit provisioning request evaluated against pre-checks & gates
- GET /api/v1/provisioning-requests - List provisioning requests
- GET /api/v1/provisioning-requests/{id} - Get single provisioning request
- POST /api/v1/provisioning-requests/{id}/bypass - Emergency bypass with post-hoc rationale
- POST /api/v1/provisioning-requests/{id}/link-resource - Link discovered resource & start 3-period tracking
- POST /api/v1/provisioning-requests/{id}/actuals - Record billed spend for period
- GET /api/v1/provisioning-requests/accuracy/report - Cross-sectional accuracy report
- POST /api/v1/provisioning-requests/unapproved/detect - Detect unapproved deployments in gated scopes
- POST /api/v1/provisioning-requests/scenarios/compare - Side-by-side scenario comparison view
- GET/POST /api/v1/provisioning-requests/gate-triggers - Master data gate triggers
- GET/POST /api/v1/provisioning-requests/authority-rules - AM-12 approval authority rules
- Prompt 13 Item 84: 100% TenantContext validation.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field

from api.cloudlens_api.tenant_context import get_authenticated_tenant_context
from domain.provisioning.models import (
    AccuracyReport,
    ApprovalAuthorityRule,
    EstimateVsActualTracking,
    GateTriggerRule,
    ProvisioningRequest,
    SavedEstimate,
    ScenarioComparisonView,
    UnapprovedDeploymentFinding,
)
from domain.provisioning.service import (
    ProvisioningGateService,
    get_provisioning_gate_service,
)
from domain.tenant.context import TenantContext

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/provisioning-requests", tags=["Cost-Aware Provisioning Gate"])


# ==============================================================================
# Request DTOs
# ==============================================================================


class CreateSavedEstimateRequest(BaseModel):
    provider: str = Field(..., description="Cloud provider (aws, azure, gcp, oci)")
    service: str = Field(..., description="Service code, e.g. AmazonEC2")
    region: str = Field(..., description="Datacenter region")
    size: str = Field(..., description="Instance type or SKU size")
    hourly_cost: Decimal = Field(..., description="Hourly cost")
    daily_cost: Decimal = Field(..., description="Daily cost (24h)")
    monthly_cost: Decimal = Field(..., description="Monthly cost (730h)")
    annualised_cost: Decimal = Field(..., description="Annualised cost (12m)")
    options: dict[str, Any] = Field(default_factory=dict)
    currency: str = Field(default="USD")
    pricing_source: str = Field(default="cloudlens_catalog")
    validity_days: int = Field(default=7, ge=1, le=90)


class SubmitProvisioningRequestDTO(BaseModel):
    estimate_id: str = Field(..., description="Source saved estimate ID")
    target_scope: str = Field(..., description="Target scope code")
    scope_type: str = Field(default="BUSINESS_UNIT")
    intended_application: str = Field(..., description="Workload application")
    intended_environment: str = Field(..., description="Target environment (PROD, STAGING, DEV)")
    owner_id: str = Field(..., description="Owner user ID")
    owner_email: str = Field(..., description="Owner email")
    cost_centre: str = Field(..., description="Cost centre code")
    business_justification: str = Field(..., min_length=10, description="Business rationale")
    intended_start_date: str = Field(..., description="Planned deployment start date")
    period: str | None = Field(default=None)
    period_budget: Decimal | None = Field(default=None)
    actual_spend: Decimal | None = Field(default=None)
    current_forecast: Decimal | None = Field(default=None)


class BypassRequestDTO(BaseModel):
    bypassed_by: str = Field(..., description="User ID performing emergency bypass")
    justification: str = Field(..., min_length=10, description="Mandatory post-hoc justification")


class LinkResourceDTO(BaseModel):
    resource_id: str = Field(..., description="Discovered cloud resource ID")
    approver_role: str | None = Field(default=None, description="Role that authorized the request")


class RecordPeriodActualDTO(BaseModel):
    period: str = Field(..., description="Billing period partition, e.g. '2026-10'")
    billed_amount: Decimal = Field(..., description="Actual billed spend in period")


class DetectUnapprovedDTO(BaseModel):
    inventoried_resources: list[dict[str, Any]] = Field(
        ..., description="Inventoried cloud resources"
    )
    gated_scopes: list[str] = Field(..., description="Gated scope codes")


class CompareScenariosDTO(BaseModel):
    target_scope: str = Field(..., description="Evaluation target scope")
    period: str = Field(..., description="Billing period")
    baseline_estimate_id: str = Field(..., description="Baseline estimate ID")
    alternative_estimate_ids: list[str] = Field(
        ..., min_length=1, max_length=3, description="1 to 3 alternative estimate IDs"
    )
    period_budget: Decimal = Field(default=Decimal("50000.00"))
    actual_spend: Decimal = Field(default=Decimal("30000.00"))
    recommendation_notes: str = Field(default="")


# ==============================================================================
# 1. Saved Estimates Endpoints
# ==============================================================================


@router.post(
    "/estimates",
    response_model=SavedEstimate,
    status_code=status.HTTP_201_CREATED,
    summary="Save a priced estimate with validity TTL",
)
def save_estimate(
    body: CreateSavedEstimateRequest,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: ProvisioningGateService = Depends(get_provisioning_gate_service),
) -> SavedEstimate:
    """Creates a saved estimate with 4 computed values, full derivation, and validity window."""
    return service.save_estimate(
        tenant_context=tenant_context,
        provider=body.provider,
        service=body.service,
        region=body.region,
        size=body.size,
        hourly_cost=body.hourly_cost,
        daily_cost=body.daily_cost,
        monthly_cost=body.monthly_cost,
        annualised_cost=body.annualised_cost,
        options=body.options,
        currency=body.currency,
        pricing_source=body.pricing_source,
        validity_days=body.validity_days,
    )


@router.get(
    "/estimates/{estimate_id}",
    response_model=SavedEstimate,
    status_code=status.HTTP_200_OK,
    summary="Get saved estimate by ID",
)
def get_estimate(
    estimate_id: str,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: ProvisioningGateService = Depends(get_provisioning_gate_service),
) -> SavedEstimate:
    """Retrieves a previously saved estimate."""
    return service.get_estimate(tenant_context=tenant_context, estimate_id=estimate_id)


# ==============================================================================
# 2. Provisioning Requests Lifecycle Endpoints
# ==============================================================================


@router.post(
    "",
    response_model=ProvisioningRequest,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a cost-aware provisioning request",
)
def submit_provisioning_request(
    body: SubmitProvisioningRequestDTO,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: ProvisioningGateService = Depends(get_provisioning_gate_service),
) -> ProvisioningRequest:
    """Submits a deployment proposal evaluated against pre-checks, budget impact, and gate triggers."""
    return service.submit_provisioning_request(
        tenant_context=tenant_context,
        estimate_id=body.estimate_id,
        target_scope=body.target_scope,
        scope_type=body.scope_type,
        intended_application=body.intended_application,
        intended_environment=body.intended_environment,
        owner_id=body.owner_id,
        owner_email=body.owner_email,
        cost_centre=body.cost_centre,
        business_justification=body.business_justification,
        intended_start_date=body.intended_start_date,
        period=body.period,
        period_budget=body.period_budget,
        actual_spend=body.actual_spend,
        current_forecast=body.current_forecast,
    )


@router.get(
    "",
    response_model=list[ProvisioningRequest],
    status_code=status.HTTP_200_OK,
    summary="List provisioning requests",
)
def list_provisioning_requests(
    status_filter: str | None = Query(None, alias="status"),
    scope_code: str | None = Query(None),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: ProvisioningGateService = Depends(get_provisioning_gate_service),
) -> list[ProvisioningRequest]:
    """Lists provisioning requests with optional status and scope filtering."""
    return service.list_provisioning_requests(
        tenant_context=tenant_context,
        status=status_filter,
        scope_code=scope_code,
    )


@router.get(
    "/accuracy/report",
    response_model=AccuracyReport,
    status_code=status.HTTP_200_OK,
    summary="Get 3-period estimate vs actual accuracy report",
)
def get_accuracy_report(
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: ProvisioningGateService = Depends(get_provisioning_gate_service),
) -> AccuracyReport:
    """Reports estimate accuracy across requesters, services, and approvers."""
    return service.generate_accuracy_report(tenant_context=tenant_context)


@router.get(
    "/gate-triggers",
    response_model=list[GateTriggerRule],
    status_code=status.HTTP_200_OK,
    summary="List master-data gate trigger rules",
)
def list_gate_triggers(
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: ProvisioningGateService = Depends(get_provisioning_gate_service),
) -> list[GateTriggerRule]:
    """Lists configured gate trigger rules for the tenant."""
    return service.repository.list_gate_rules(tenant_context.tenant_id)


@router.post(
    "/gate-triggers",
    response_model=GateTriggerRule,
    status_code=status.HTTP_201_CREATED,
    summary="Configure master-data gate trigger rule",
)
def configure_gate_trigger(
    rule: GateTriggerRule,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: ProvisioningGateService = Depends(get_provisioning_gate_service),
) -> GateTriggerRule:
    """Registers or updates a gate trigger rule."""
    return service.configure_gate_trigger(tenant_context=tenant_context, rule=rule)


@router.get(
    "/authority-rules",
    response_model=list[ApprovalAuthorityRule],
    status_code=status.HTTP_200_OK,
    summary="List AM-12 approval authority rules",
)
def list_authority_rules(
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: ProvisioningGateService = Depends(get_provisioning_gate_service),
) -> list[ApprovalAuthorityRule]:
    """Lists configured AM-12 approval authority rules for the tenant."""
    return service.repository.list_authority_rules(tenant_context.tenant_id)


@router.post(
    "/authority-rules",
    response_model=ApprovalAuthorityRule,
    status_code=status.HTTP_201_CREATED,
    summary="Configure AM-12 approval authority rule",
)
def configure_authority_rule(
    rule: ApprovalAuthorityRule,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: ProvisioningGateService = Depends(get_provisioning_gate_service),
) -> ApprovalAuthorityRule:
    """Registers an AM-12 approval authority rule."""
    return service.configure_authority_rule(tenant_context=tenant_context, rule=rule)


@router.post(
    "/unapproved/detect",
    response_model=list[UnapprovedDeploymentFinding],
    status_code=status.HTTP_200_OK,
    summary="Detect unapproved deployments in gated scopes",
)
def detect_unapproved_deployments(
    body: DetectUnapprovedDTO,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: ProvisioningGateService = Depends(get_provisioning_gate_service),
) -> list[UnapprovedDeploymentFinding]:
    """Scans inventory for untracked deployments in gated scopes with advisory notice."""
    return service.detect_unapproved_deployments(
        tenant_context=tenant_context,
        inventoried_resources=body.inventoried_resources,
        gated_scopes=set(body.gated_scopes),
    )


@router.post(
    "/scenarios/compare",
    response_model=ScenarioComparisonView,
    status_code=status.HTTP_200_OK,
    summary="Compare architecture scenarios side by side",
)
def compare_scenarios(
    body: CompareScenariosDTO,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: ProvisioningGateService = Depends(get_provisioning_gate_service),
) -> ScenarioComparisonView:
    """Compares 2-4 architecture configurations against budget impact and cost drivers."""
    baseline = service.get_estimate(
        tenant_context=tenant_context, estimate_id=body.baseline_estimate_id
    )
    alternatives = [
        service.get_estimate(tenant_context=tenant_context, estimate_id=alt_id)
        for alt_id in body.alternative_estimate_ids
    ]
    return service.compare_scenarios(
        tenant_context=tenant_context,
        target_scope=body.target_scope,
        period=body.period,
        baseline_estimate=baseline,
        alternative_estimates=alternatives,
        period_budget=body.period_budget,
        actual_spend=body.actual_spend,
        recommendation_notes=body.recommendation_notes,
    )


@router.get(
    "/{request_id}",
    response_model=ProvisioningRequest,
    status_code=status.HTTP_200_OK,
    summary="Get single provisioning request by ID",
)
def get_provisioning_request(
    request_id: str,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: ProvisioningGateService = Depends(get_provisioning_gate_service),
) -> ProvisioningRequest:
    """Retrieves full details of a provisioning request."""
    return service.get_provisioning_request(tenant_context=tenant_context, request_id=request_id)


@router.post(
    "/{request_id}/bypass",
    response_model=ProvisioningRequest,
    status_code=status.HTTP_200_OK,
    summary="Execute emergency bypass with post-hoc justification",
)
def bypass_provisioning_request(
    request_id: str,
    body: BypassRequestDTO,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: ProvisioningGateService = Depends(get_provisioning_gate_service),
) -> ProvisioningRequest:
    """Bypasses a pending gate with mandatory recorded justification."""
    return service.bypass_provisioning_request(
        tenant_context=tenant_context,
        request_id=request_id,
        bypassed_by=body.bypassed_by,
        justification=body.justification,
    )


@router.post(
    "/{request_id}/link-resource",
    response_model=dict[str, Any],
    status_code=status.HTTP_200_OK,
    summary="Link newly inventoried resource and begin 3-period tracking",
)
def link_resource(
    request_id: str,
    body: LinkResourceDTO,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: ProvisioningGateService = Depends(get_provisioning_gate_service),
) -> dict[str, Any]:
    """Links an approved request to a cloud resource ID to initiate 3-period reconciliation."""
    req, tracking = service.link_resource_to_request(
        tenant_context=tenant_context,
        request_id=request_id,
        resource_id=body.resource_id,
        approver_role=body.approver_role,
    )
    return {
        "request_id": req.request_id,
        "resource_id": req.linked_resource_id,
        "status": req.status.value,
        "tracking_id": tracking.tracking_id,
    }


@router.post(
    "/{request_id}/actuals",
    response_model=EstimateVsActualTracking,
    status_code=status.HTTP_200_OK,
    summary="Record period actual billed spend for 3-period reconciliation",
)
def record_period_actual(
    request_id: str,
    body: RecordPeriodActualDTO,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: ProvisioningGateService = Depends(get_provisioning_gate_service),
) -> EstimateVsActualTracking:
    """Records billed cost for a period and evaluates estimate accuracy."""
    return service.record_period_actual(
        tenant_context=tenant_context,
        request_id=request_id,
        period=body.period,
        billed_amount=body.billed_amount,
    )
