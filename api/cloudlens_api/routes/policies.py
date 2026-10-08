"""Governance Policy Engine API Endpoints (Prompt 30, BBP Section 34, FR-740 to FR-746).

Enforces:
- FR-740: Governance policies must be declarative, versioned, and definable without code modification or deployment.
- FR-741: Policies must support simulate and enforce modes, with simulation producing findings without alerting.
- FR-742: A policy condition that cannot be evaluated for an entity must produce 'Not Evaluable', never False / violation.
- FR-743: Policy exemptions must be time-boxed, justified, approved, and reported while active.
- FR-744: Policy violation findings must be deduplicated against open findings for the same entity and condition.
- FR-745: Governance exception counts and resolution times must be trended over time and reportable.
- FR-746: Default policies (POL-01 to POL-16), disabled by default except connector health.
"""

from __future__ import annotations

import datetime as dt
import logging

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import BaseModel

from api.cloudlens_api.tenant_context import get_authenticated_tenant_context
from domain.models.enums import (
    FindingLifecycleStatus,
    PolicyCategory,
    PolicyMode,
    PolicySeverity,
)
from domain.policy.catalogue import get_default_policy_definitions
from domain.policy.models import (
    GovernanceTrendReport,
    PolicyCreateDTO,
    PolicyDefinition,
    PolicyEnableToggleDTO,
    PolicyEvaluationBatchRequest,
    PolicyEvaluationBatchResponse,
    PolicyExemption,
    PolicyExemptionCreateDTO,
    PolicyFinding,
    PolicySimulationRequest,
    PolicySimulationResponse,
    PolicyUpdateDTO,
)
from domain.policy.service import PolicyService, get_policy_service
from domain.tenant.context import TenantContext

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/policies", tags=["Governance Policy Engine"])


# ==============================================================================
# Response Wrapper Models
# ==============================================================================


class PolicyListResponse(BaseModel):
    """Response envelope for policy definitions."""

    items: list[PolicyDefinition]
    total: int


class FindingListResponse(BaseModel):
    """Response envelope for policy findings."""

    items: list[PolicyFinding]
    total: int


class ExemptionListResponse(BaseModel):
    """Response envelope for policy exemptions."""

    items: list[PolicyExemption]
    total: int


# ==============================================================================
# 1. Static Collection Endpoints
# ==============================================================================


@router.get("", response_model=PolicyListResponse)
async def list_policies(
    enabled_only: bool = Query(default=False, description="Filter for enabled policies only"),
    category: PolicyCategory | None = Query(default=None, description="Optional category filter"),
    service: PolicyService = Depends(get_policy_service),
    tenant_ctx: TenantContext = Depends(get_authenticated_tenant_context),
) -> PolicyListResponse:
    """Lists policies for the authenticated tenant, seeding defaults if empty."""
    policies = service.list_policies(
        tenant_context=tenant_ctx,
        enabled_only=enabled_only,
        category=category,
    )
    return PolicyListResponse(items=policies, total=len(policies))


@router.get("/catalogue", response_model=PolicyListResponse)
async def get_catalogue() -> PolicyListResponse:
    """Returns the authoritative default policy catalogue (POL-01 to POL-18)."""
    defaults = get_default_policy_definitions()
    return PolicyListResponse(items=defaults, total=len(defaults))


@router.post("", response_model=PolicyDefinition, status_code=status.HTTP_201_CREATED)
async def create_policy(
    dto: PolicyCreateDTO,
    service: PolicyService = Depends(get_policy_service),
    tenant_ctx: TenantContext = Depends(get_authenticated_tenant_context),
) -> PolicyDefinition:
    """Creates a new declarative policy dynamically without code deployment (FR-740)."""
    return service.create_policy(dto, tenant_context=tenant_ctx)


# ==============================================================================
# 2. Simulation & Live Evaluation Endpoints
# ==============================================================================


@router.post("/simulate", response_model=PolicySimulationResponse)
async def simulate_policy(
    request: PolicySimulationRequest,
    service: PolicyService = Depends(get_policy_service),
    tenant_ctx: TenantContext = Depends(get_authenticated_tenant_context),
) -> PolicySimulationResponse:
    """Simulates a policy against test entity records, producing findings with ZERO alerts (FR-741)."""
    return service.simulate_policy(
        tenant_context=tenant_ctx,
        policy_id=request.policy_id,
        inline_policy=request.inline_policy,
        entities=request.entities,
    )


@router.post("/evaluate", response_model=PolicyEvaluationBatchResponse)
async def evaluate_batch(
    request: PolicyEvaluationBatchRequest,
    service: PolicyService = Depends(get_policy_service),
    tenant_ctx: TenantContext = Depends(get_authenticated_tenant_context),
) -> PolicyEvaluationBatchResponse:
    """Evaluates entity batch against enabled policies with deduplication & clearing (FR-742, FR-744)."""
    return service.evaluate_batch(
        entities=request.entities,
        tenant_context=tenant_ctx,
        policy_ids=request.policy_ids,
    )


# ==============================================================================
# 3. Finding Endpoints
# ==============================================================================


@router.get("/findings", response_model=FindingListResponse)
async def list_findings(
    status: FindingLifecycleStatus | None = Query(default=None),
    severity: PolicySeverity | None = Query(default=None),
    category: PolicyCategory | None = Query(default=None),
    mode: PolicyMode | None = Query(default=None),
    policy_id: str | None = Query(default=None),
    entity_id: str | None = Query(default=None),
    service: PolicyService = Depends(get_policy_service),
    tenant_ctx: TenantContext = Depends(get_authenticated_tenant_context),
) -> FindingListResponse:
    """Lists findings with optional lifecycle status and category filters."""
    findings = service.list_findings(
        tenant_context=tenant_ctx,
        status=status,
        severity=severity,
        category=category,
        mode=mode,
        policy_id=policy_id,
        entity_id=entity_id,
    )
    total_count = service.count_findings(tenant_context=tenant_ctx, status=status)
    return FindingListResponse(items=findings, total=total_count)


# ==============================================================================
# 4. Exemption Endpoints
# ==============================================================================


@router.post("/exemptions", response_model=PolicyExemption, status_code=status.HTTP_201_CREATED)
async def create_exemption(
    dto: PolicyExemptionCreateDTO,
    service: PolicyService = Depends(get_policy_service),
    tenant_ctx: TenantContext = Depends(get_authenticated_tenant_context),
) -> PolicyExemption:
    """Creates a time-boxed justified governance exemption (FR-743)."""
    return service.create_exemption(dto, tenant_context=tenant_ctx)


@router.get("/exemptions", response_model=ExemptionListResponse)
async def list_exemptions(
    policy_id: str | None = Query(default=None),
    entity_id: str | None = Query(default=None),
    active_only: bool = Query(default=False),
    service: PolicyService = Depends(get_policy_service),
    tenant_ctx: TenantContext = Depends(get_authenticated_tenant_context),
) -> ExemptionListResponse:
    """Lists governance exemptions."""
    exemptions = service.list_exemptions(
        tenant_context=tenant_ctx,
        policy_id=policy_id,
        entity_id=entity_id,
        active_only=active_only,
    )
    return ExemptionListResponse(items=exemptions, total=len(exemptions))


@router.delete("/exemptions/{exemption_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_exemption(
    exemption_id: str,
    service: PolicyService = Depends(get_policy_service),
    tenant_ctx: TenantContext = Depends(get_authenticated_tenant_context),
) -> Response:
    """Deletes an exemption by ID."""
    service.delete_exemption(exemption_id, tenant_context=tenant_ctx)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ==============================================================================
# 5. Governance Trend Endpoint (FR-745)
# ==============================================================================


@router.get("/trend", response_model=GovernanceTrendReport)
async def get_governance_trend(
    start_date: dt.date = Query(..., description="Report start date YYYY-MM-DD"),
    end_date: dt.date = Query(..., description="Report end date YYYY-MM-DD"),
    service: PolicyService = Depends(get_policy_service),
    tenant_ctx: TenantContext = Depends(get_authenticated_tenant_context),
) -> GovernanceTrendReport:
    """Calculates governance exception counts and resolution time trends over time (FR-745)."""
    return service.get_governance_trend(
        start_date=start_date,
        end_date=end_date,
        tenant_context=tenant_ctx,
    )


# ==============================================================================
# 6. Parameterized Policy ID Endpoints (MUST follow literal endpoints)
# ==============================================================================


@router.get("/{policy_id}", response_model=PolicyDefinition)
async def get_policy(
    policy_id: str,
    service: PolicyService = Depends(get_policy_service),
    tenant_ctx: TenantContext = Depends(get_authenticated_tenant_context),
) -> PolicyDefinition:
    """Retrieves current active version of a policy."""
    return service.get_policy(policy_id, tenant_context=tenant_ctx)


@router.get("/{policy_id}/versions/{version}", response_model=PolicyDefinition)
async def get_policy_version(
    policy_id: str,
    version: int,
    service: PolicyService = Depends(get_policy_service),
    tenant_ctx: TenantContext = Depends(get_authenticated_tenant_context),
) -> PolicyDefinition:
    """Retrieves a specific historical version of a policy."""
    return service.get_policy_version(policy_id, version, tenant_context=tenant_ctx)


@router.put("/{policy_id}", response_model=PolicyDefinition)
async def update_policy(
    policy_id: str,
    dto: PolicyUpdateDTO,
    service: PolicyService = Depends(get_policy_service),
    tenant_ctx: TenantContext = Depends(get_authenticated_tenant_context),
) -> PolicyDefinition:
    """Updates a policy and increments its version without code deployment (FR-740)."""
    return service.update_policy(policy_id, dto, tenant_context=tenant_ctx)


@router.patch("/{policy_id}/enable", response_model=PolicyDefinition)
async def toggle_policy_enabled(
    policy_id: str,
    dto: PolicyEnableToggleDTO,
    service: PolicyService = Depends(get_policy_service),
    tenant_ctx: TenantContext = Depends(get_authenticated_tenant_context),
) -> PolicyDefinition:
    """Toggles policy enabled state without deployment."""
    return service.set_policy_enabled(policy_id, dto.enabled, tenant_context=tenant_ctx)
