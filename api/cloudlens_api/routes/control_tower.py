"""API Router for Platform Control Tower (Prompt R-CT).

Exposes:
1. Telemetry and Overview Endpoints (all require platform.observe):
   - GET /overview (14 panel statuses)
   - GET /health, /release, /tenants, /connectors, /jobs, /queues, /pipeline,
     /security, /audit/tail, /alerts-pipeline, /collection-cost, /capacity,
     /backups, /expiries, /value
   - GET /stream (Server-Sent Events: live status updates every 10s)
2. Administrative Actions (require platform.operate + step-up MFA + reason >= 20 chars):
   - POST /actions/{action_name}
   - Supported actions: retry-job, pause-connector, resume-connector, force-sync,
     drain-queue, requeue-quarantine, maintenance-mode, revoke-user-sessions,
     trigger-backup, trigger-reconciliation
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse

from api.cloudlens_api.tenant_context import get_authenticated_tenant_context
from domain.audit.service import get_audit_service
from domain.control_tower.models import (
    BlastRadius,
    ControlTowerActionRequest,
    ControlTowerActionResult,
    ControlTowerOverview,
    ControlTowerPanel,
)
from domain.control_tower.service import get_control_tower_service
from domain.models.enums import SystemRole
from domain.tenant.context import TenantContext

logger = logging.getLogger("cloudlens.api.control_tower")

router = APIRouter(prefix="/api/v1/control-tower", tags=["Platform Control Tower"])

# Roles with observe and operate capabilities
OBSERVE_ROLES = {
    SystemRole.SUPER_ADMIN.value,
    SystemRole.PLATFORM_ADMIN.value,
    SystemRole.AUDITOR.value,
    "SUPER_ADMIN",
    "PLATFORM_ADMIN",
    "AUDITOR",
}

OPERATE_ROLES = {
    SystemRole.SUPER_ADMIN.value,
    SystemRole.PLATFORM_ADMIN.value,
    "SUPER_ADMIN",
    "PLATFORM_ADMIN",
}


def _check_observe_permission(tc: TenantContext) -> None:
    """Verifies caller holds platform.observe capability."""
    if tc.is_superuser:
        return
    caller_roles = set(tc.roles)
    if caller_roles & OBSERVE_ROLES or "platform.observe" in getattr(tc, "scope_grants", []):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Control Tower Access Denied: 'platform.observe' capability required.",
    )


def _check_operate_permission(tc: TenantContext) -> None:
    """Verifies caller holds platform.operate capability (AUDITOR blocked)."""
    if tc.is_superuser:
        return
    caller_roles = set(tc.roles)
    if caller_roles & OPERATE_ROLES or "platform.operate" in getattr(tc, "scope_grants", []):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Control Tower Action Forbidden: 'platform.operate' capability required. Read-only observers cannot execute actions.",
    )


# ==============================================================================
# Overview and 14 Monitoring Panel Endpoints
# ==============================================================================


@router.get("/overview", response_model=ControlTowerOverview, status_code=status.HTTP_200_OK)
def get_control_tower_overview(
    tc: TenantContext = Depends(get_authenticated_tenant_context),
) -> ControlTowerOverview:
    """Returns the unified Control Tower overview with all 14 monitoring panels."""
    _check_observe_permission(tc)
    svc = get_control_tower_service()
    return svc.get_overview()


@router.get("/health", response_model=ControlTowerPanel, status_code=status.HTTP_200_OK)
def get_health_panel(
    tc: TenantContext = Depends(get_authenticated_tenant_context),
) -> ControlTowerPanel:
    _check_observe_permission(tc)
    return get_control_tower_service().get_health_panel()


@router.get("/release", response_model=ControlTowerPanel, status_code=status.HTTP_200_OK)
def get_release_panel(
    tc: TenantContext = Depends(get_authenticated_tenant_context),
) -> ControlTowerPanel:
    _check_observe_permission(tc)
    return get_control_tower_service().get_release_panel()


@router.get("/tenants", response_model=ControlTowerPanel, status_code=status.HTTP_200_OK)
def get_tenants_panel(
    tc: TenantContext = Depends(get_authenticated_tenant_context),
) -> ControlTowerPanel:
    _check_observe_permission(tc)
    return get_control_tower_service().get_tenants_panel()


@router.get("/connectors", response_model=ControlTowerPanel, status_code=status.HTTP_200_OK)
def get_connectors_panel(
    tc: TenantContext = Depends(get_authenticated_tenant_context),
) -> ControlTowerPanel:
    _check_observe_permission(tc)
    return get_control_tower_service().get_connectors_panel()


@router.get("/jobs", response_model=ControlTowerPanel, status_code=status.HTTP_200_OK)
def get_jobs_panel(
    tc: TenantContext = Depends(get_authenticated_tenant_context),
) -> ControlTowerPanel:
    _check_observe_permission(tc)
    return get_control_tower_service().get_jobs_panel()


@router.get("/queues", response_model=ControlTowerPanel, status_code=status.HTTP_200_OK)
def get_queues_panel(
    tc: TenantContext = Depends(get_authenticated_tenant_context),
) -> ControlTowerPanel:
    _check_observe_permission(tc)
    return get_control_tower_service().get_queues_panel()


@router.get("/pipeline", response_model=ControlTowerPanel, status_code=status.HTTP_200_OK)
def get_pipeline_panel(
    tc: TenantContext = Depends(get_authenticated_tenant_context),
) -> ControlTowerPanel:
    _check_observe_permission(tc)
    return get_control_tower_service().get_pipeline_panel()


@router.get("/security", response_model=ControlTowerPanel, status_code=status.HTTP_200_OK)
def get_security_panel(
    tc: TenantContext = Depends(get_authenticated_tenant_context),
) -> ControlTowerPanel:
    _check_observe_permission(tc)
    return get_control_tower_service().get_security_panel()


@router.get("/alerts-pipeline", response_model=ControlTowerPanel, status_code=status.HTTP_200_OK)
def get_alerts_pipeline_panel(
    tc: TenantContext = Depends(get_authenticated_tenant_context),
) -> ControlTowerPanel:
    _check_observe_permission(tc)
    return get_control_tower_service().get_alerts_pipeline_panel()


@router.get("/collection-cost", response_model=ControlTowerPanel, status_code=status.HTTP_200_OK)
def get_collection_cost_panel(
    tc: TenantContext = Depends(get_authenticated_tenant_context),
) -> ControlTowerPanel:
    _check_observe_permission(tc)
    return get_control_tower_service().get_collection_cost_panel()


@router.get("/capacity", response_model=ControlTowerPanel, status_code=status.HTTP_200_OK)
def get_capacity_panel(
    tc: TenantContext = Depends(get_authenticated_tenant_context),
) -> ControlTowerPanel:
    _check_observe_permission(tc)
    return get_control_tower_service().get_capacity_panel()


@router.get("/backups", response_model=ControlTowerPanel, status_code=status.HTTP_200_OK)
def get_backups_panel(
    tc: TenantContext = Depends(get_authenticated_tenant_context),
) -> ControlTowerPanel:
    _check_observe_permission(tc)
    return get_control_tower_service().get_backups_panel()


@router.get("/expiries", response_model=ControlTowerPanel, status_code=status.HTTP_200_OK)
def get_expiries_panel(
    tc: TenantContext = Depends(get_authenticated_tenant_context),
) -> ControlTowerPanel:
    _check_observe_permission(tc)
    return get_control_tower_service().get_expiries_panel()


@router.get("/value", response_model=ControlTowerPanel, status_code=status.HTTP_200_OK)
def get_value_panel(
    tc: TenantContext = Depends(get_authenticated_tenant_context),
) -> ControlTowerPanel:
    _check_observe_permission(tc)
    return get_control_tower_service().get_value_panel()


@router.get("/audit/tail", status_code=status.HTTP_200_OK)
def get_audit_tail(
    limit: int = Query(default=200, ge=1, le=500),
    tc: TenantContext = Depends(get_authenticated_tenant_context),
) -> dict[str, Any]:
    """Returns the live audit tail up to 200 events for Control Tower inspection."""
    _check_observe_permission(tc)
    audit_svc = get_audit_service()
    events = audit_svc.list_events(tenant_context=tc, limit=limit)
    # Sanitize: ensure no personal user emails or raw tenant data are exposed
    sanitized_events = [
        {
            "id": getattr(e, "id", ""),
            "event_type": getattr(e, "event_type", ""),
            "action": getattr(e, "action", ""),
            "resource_type": getattr(e, "resource_type", ""),
            "actor_roles": getattr(e, "actor_roles", []),
            "timestamp": getattr(e, "timestamp", "").isoformat() if hasattr(getattr(e, "timestamp", None), "isoformat") else str(getattr(e, "timestamp", "")),
        }
        for e in events
    ]
    return {
        "limit": limit,
        "returned_count": len(sanitized_events),
        "events": sanitized_events,
    }


# ==============================================================================
# Server-Sent Events (SSE) Stream
# ==============================================================================


@router.get("/stream")
async def control_tower_stream(
    request: Request,
    tc: TenantContext = Depends(get_authenticated_tenant_context),
) -> StreamingResponse:
    """Streams live Control Tower status changes as Server-Sent Events (SSE) every 10s."""
    _check_observe_permission(tc)
    svc = get_control_tower_service()

    async def event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                overview = svc.get_overview()
                payload = {
                    "overall_status": overview.overall_status.value,
                    "overall_label": overview.overall_label,
                    "maintenance_mode": overview.maintenance_mode,
                    "timestamp": overview.timestamp,
                    "panels_count": len(overview.panels),
                }
                yield f"event: status_update\ndata: {json.dumps(payload)}\n\n"
                await asyncio.sleep(10)
        except asyncio.CancelledError:
            pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ==============================================================================
# Audited Operational Actions (require platform.operate + step-up MFA + reason)
# ==============================================================================


VALID_ACTIONS = {
    "retry-job",
    "pause-connector",
    "resume-connector",
    "force-sync",
    "drain-queue",
    "requeue-quarantine",
    "maintenance-mode",
    "revoke-user-sessions",
    "trigger-backup",
    "run-restore-test",
    "trigger-restore-test",
    "trigger-reconciliation",
}


@router.get("/abuse", status_code=status.HTTP_200_OK, summary="Rate-Limit and Abuse Dashboard (IMP-07)")
def get_abuse_dashboard(
    tc: TenantContext = Depends(get_authenticated_tenant_context),
) -> dict[str, Any]:
    """Returns real-time rate limiting, 429 counts, top callers, and lockout status (IMP-07)."""
    _check_observe_permission(tc)
    from domain.abuse.tracker import get_abuse_tracker
    return get_abuse_tracker().get_abuse_summary()



@router.post("/actions/{action_name}", status_code=status.HTTP_200_OK)
def handle_control_tower_action(
    action_name: str,
    req: ControlTowerActionRequest,
    x_step_up_token: str | None = Header(default=None, alias="X-Step-Up-Token"),
    tc: TenantContext = Depends(get_authenticated_tenant_context),
) -> dict[str, Any]:
    """Executes a confirmed Control Tower operational action or returns its blast radius."""
    action_clean = action_name.strip().lower()
    if action_clean not in VALID_ACTIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown operational action '{action_name}'. Valid actions: {', '.join(sorted(VALID_ACTIONS))}",
        )

    # 1. Require platform.operate capability (Auditor strictly blocked)
    _check_operate_permission(tc)

    svc = get_control_tower_service()

    # 2. Stage / Blast Radius Assessment (Confirmation Step)
    if not req.confirm:
        blast_radius = svc.compute_blast_radius(action_clean, req.params)
        return {
            "status": "staged",
            "action": action_clean,
            "blast_radius": blast_radius.model_dump(),
            "requires_confirmation": True,
            "message": "Blast radius computed. To execute, submit with confirm=True, a valid step_up_token, and operational reason (>= 20 chars).",
        }

    # 3. Require Step-Up MFA
    step_up_token = req.step_up_token or x_step_up_token
    if not step_up_token or step_up_token.strip() == "":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Step-up authentication verification required to execute operational actions.",
        )

    # 4. Require Operational Reason (>= 20 chars)
    if len(req.reason.strip()) < 20:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Operational reason must be at least 20 characters explaining justification.",
        )

    # 5. Execute action and record CT_ACTION audit event
    actor = tc.email or tc.user_id
    result = svc.execute_action(
        action=action_clean,
        params=req.params,
        actor_id=actor,
        reason=req.reason.strip(),
        tenant_context=tc,
    )
    return result
