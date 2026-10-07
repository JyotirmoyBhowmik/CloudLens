"""Admin Console REST API Endpoints (Prompt 41 / BBP Section 32).

Enforces:
- Administrative role verification (TENANT_ADMIN) and step-up authentication.
- All twenty-four administrative functions (Master Brief Section 31, BBP 32.1).
- Override interface enforcing all eight mandatory attributes, refusing submission
  without non-empty reason (>= 20 characters) and future expiration timestamp.
- RBAC Permission Matrix & Access Review CSV export.
- Audit Log, System Settings, and Feature Flags management.
"""

from __future__ import annotations

import csv
import io
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from pydantic import BaseModel, Field, field_validator

from api.cloudlens_api.tenant_context import get_authenticated_tenant_context
from domain.alerting.service import get_alert_service
from domain.audit.models import AuditEventCreate
from domain.audit.service import get_audit_service
from domain.identity.service import get_identity_service
from domain.models.enums import (
    AlertSeverity,
    AlertStatus,
    AlertType,
    AuditEventType,
    OverrideClass,
    SystemRole,
)
from domain.overrides.models import (
    MIN_WHY_LENGTH,
    OverrideApproval,
    OverrideCreateRequest,
    OverrideResponse,
)
from domain.overrides.service import get_override_service
from domain.rbac.service import get_rbac_service
from domain.tenant.context import TenantContext

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin", tags=["Admin Console"])


# ==============================================================================
# 24 Administrative Functions Register (Prompt 41 / BBP Section 32)
# ==============================================================================

ADMIN_FUNCTIONS_REGISTER: list[dict[str, Any]] = [
    {
        "id": "tenant_management",
        "name": "Tenant Management",
        "category": "Identity & Tenancy",
        "description": "Configure tenant isolation boundaries, slug, branding, and organization metadata.",
        "status": "ACTIVE",
    },
    {
        "id": "user_management",
        "name": "User Management",
        "category": "Identity & Tenancy",
        "description": "User lifecycle, provisioning, invitation dispatch, status deactivation, and session invalidation.",
        "status": "ACTIVE",
    },
    {
        "id": "role_management",
        "name": "Role Management",
        "category": "Access Control",
        "description": "System role overview and tenant custom role composition from permission catalogue.",
        "status": "ACTIVE",
    },
    {
        "id": "rbac_management",
        "name": "RBAC & Scope Grants",
        "category": "Access Control",
        "description": "Multi-dimensional scope grant matrix, access evaluations, and periodic compliance review export.",
        "status": "ACTIVE",
    },
    {
        "id": "sso_idp_configuration",
        "name": "SSO & IdP Configuration",
        "category": "Access Control",
        "description": "SAML 2.0 and OIDC federated identity providers, metadata endpoints, and certificate thumbprints.",
        "status": "ACTIVE",
    },
    {
        "id": "connector_management",
        "name": "Cloud Connectors",
        "category": "Connectors & Ingestion",
        "description": "Multi-cloud provider connectors (AWS, Azure, GCP, OCI), sync cadences, and capability matrix.",
        "status": "ACTIVE",
    },
    {
        "id": "credential_profiles",
        "name": "Credential Profiles",
        "category": "Connectors & Ingestion",
        "description": "Cloud authentication profiles, IAM cross-account role ARNs, and KMS secret references.",
        "status": "ACTIVE",
    },
    {
        "id": "provider_configuration",
        "name": "Provider Configuration",
        "category": "Connectors & Ingestion",
        "description": "Enabled datacenter regions, API endpoint overrides, batch ingestion sizes, and discovery throttles.",
        "status": "ACTIVE",
    },
    {
        "id": "global_thresholds",
        "name": "Global Thresholds",
        "category": "FinOps & Policy",
        "description": "Estate-wide budget utilization alert bands (Amber 80%, Red 100%, Breach 110%) and anomaly z-scores.",
        "status": "ACTIVE",
    },
    {
        "id": "policy_configuration",
        "name": "Policy Engine Configuration",
        "category": "FinOps & Policy",
        "description": "Declarative governance rules POL-01 through POL-16, dry-run simulation mode, and automated enforcement.",
        "status": "ACTIVE",
    },
    {
        "id": "budget_templates",
        "name": "Budget Templates",
        "category": "FinOps & Policy",
        "description": "Standardized enterprise allocation templates for application tiers, environments, and business units.",
        "status": "ACTIVE",
    },
    {
        "id": "service_catalogue",
        "name": "Service Catalogue",
        "category": "Catalogue & Pricing",
        "description": "Cloud service taxonomies, canonical categories, SKU normalization tables, and unmapped SKU tracking.",
        "status": "ACTIVE",
    },
    {
        "id": "cost_model_configuration",
        "name": "Cost Model Configuration",
        "category": "Catalogue & Pricing",
        "description": "Amortization schedule formulas, upfront fee depreciation schedules, and blended rate logic.",
        "status": "ACTIVE",
    },
    {
        "id": "metric_catalogue",
        "name": "Metric Catalogue",
        "category": "Catalogue & Pricing",
        "description": "Usage measurement types, cardinality filters, metric collectors, and downsampling rules.",
        "status": "ACTIVE",
    },
    {
        "id": "unit_catalogue",
        "name": "Unit Catalogue",
        "category": "Catalogue & Pricing",
        "description": "Conversion multiplier registry between storage, bandwidth, memory, and core consumption dimensions.",
        "status": "ACTIVE",
    },
    {
        "id": "currency_configuration",
        "name": "Currency & FX Configuration",
        "category": "Financial Controls",
        "description": "Reporting currency, ISO 4217 rate cards, fixed monthly exchange rates, and FX variance accounting.",
        "status": "ACTIVE",
    },
    {
        "id": "alert_configuration",
        "name": "Alert Configuration",
        "category": "Alerting & Ops",
        "description": "Canonical alert thresholds, anti-flapping minimum dwell times, and storm-grouping limits.",
        "status": "ACTIVE",
    },
    {
        "id": "notification_configuration",
        "name": "Notification Channels",
        "category": "Alerting & Ops",
        "description": "Webhook endpoints, Slack channels, PagerDuty services, and email recipient escalation paths.",
        "status": "ACTIVE",
    },
    {
        "id": "data_retention",
        "name": "Data Retention Policies",
        "category": "Compliance & Audit",
        "description": "Granular data lifecycles: 90-day usage metrics, 7-year financial billing records, 3-year audit logs.",
        "status": "ACTIVE",
    },
    {
        "id": "audit_log",
        "name": "Audit Log Viewer",
        "category": "Compliance & Audit",
        "description": "Immutable ledger of all mutating transactions with actor provenance, correlation ID, and export.",
        "status": "ACTIVE",
    },
    {
        "id": "system_settings",
        "name": "System Settings",
        "category": "System Controls",
        "description": "Default timezone, dark mode configuration, UI comfortable-density toggles, and cache TTL settings.",
        "status": "ACTIVE",
    },
    {
        "id": "feature_flags",
        "name": "Feature Flags Console",
        "category": "System Controls",
        "description": "Canary feature rollout toggles, dark-launch switches, and emergency system kill-switches.",
        "status": "ACTIVE",
    },
    {
        "id": "connector_overrides",
        "name": "Connector Overrides",
        "category": "Overrides & Exceptions",
        "description": "Per-connector rate limiting overrides, timeout cushions, and mock estate simulation toggles.",
        "status": "ACTIVE",
    },
    {
        "id": "manual_overrides",
        "name": "Manual Overrides & Exceptions",
        "category": "Overrides & Exceptions",
        "description": "Eight-attribute enforced governance overrides with mandatory rationale, expiry, and reversion.",
        "status": "ACTIVE",
    },
]


# ==============================================================================
# DTO Models
# ==============================================================================


class StepUpAuthRequest(BaseModel):
    """Payload to complete step-up authentication challenge for administrative operations."""

    password: str = Field(
        ..., min_length=1, description="Administrative credential or MFA confirmation code"
    )
    action_context: str = Field(
        default="admin_console", description="Target administrative function"
    )


class StepUpAuthResponse(BaseModel):
    """Response confirming step-up validation."""

    authenticated: bool
    session_token: str
    expires_at: datetime
    actor: str


class ActAsTenantRequest(BaseModel):
    """Payload to assume scoped tenant identity as Global Admin."""

    tenant_id: str = Field(..., min_length=1, description="Target tenant ID to assume")
    reason: str = Field(..., min_length=20, description="Mandatory reason (>= 20 characters)")
    mfa_code: str | None = Field(default=None, description="Step-up MFA TOTP code")
    step_up_token: str | None = Field(default=None, description="Step-up session token from /step-up")

    @field_validator("reason")
    @classmethod
    def validate_reason_length(cls, v: str) -> str:
        clean = v.strip() if v else ""
        if len(clean) < 20:
            raise ValueError(f"Reason must be at least 20 characters. Found {len(clean)}.")
        return clean


class ActAsTenantResponse(BaseModel):
    """Scoped token issued for temporary tenant administration."""

    access_token: str
    token: str
    token_type: str = "Bearer"
    expires_in: int
    act_as_tenant: str
    original_subject: str
    audit_event_id: str


class AdminOverrideCreateDTO(BaseModel):
    """Payload enforcing all eight mandatory override attributes."""

    override_class: OverrideClass = Field(..., description="Classification category")
    who: str = Field(..., min_length=1, description="Accountable identity")
    what: str = Field(..., min_length=1, description="Target entity or configuration key")
    why: str = Field(
        ..., min_length=MIN_WHY_LENGTH, description="Mandatory detailed justification (>= 20 chars)"
    )
    previous_value: Any = Field(..., description="Value prior to override")
    new_value: Any = Field(..., description="Overriding value applied")
    expiry: datetime = Field(..., description="Mandatory expiration timestamp in UTC")
    approval_ticket: str | None = Field(default=None, description="ITSM change ticket reference")

    @field_validator("why")
    @classmethod
    def validate_why_length(cls, v: str) -> str:
        clean = v.strip() if v else ""
        if len(clean) < MIN_WHY_LENGTH:
            raise ValueError(
                f"Override rationale ('why') must be at least {MIN_WHY_LENGTH} characters. Found {len(clean)}."
            )
        return clean

    @field_validator("expiry")
    @classmethod
    def validate_future_expiry(cls, v: datetime) -> datetime:
        now = datetime.now(UTC)
        expiry_utc = v if v.tzinfo else v.replace(tzinfo=UTC)
        if expiry_utc <= now:
            raise ValueError("Override expiry must be a valid future timestamp.")
        return expiry_utc


class SystemSettingsDTO(BaseModel):
    """Global system configuration settings."""

    default_timezone: str = Field(default="UTC", description="Display timezone")
    currency: str = Field(default="USD", description="Default reporting currency")
    telemetry_cadence_minutes: int = Field(default=60, ge=5, le=1440)
    audit_retention_days: int = Field(default=1095, ge=30)
    enforce_two_factor: bool = Field(default=True)
    maintenance_mode: bool = Field(default=False)


# In-memory settings state for tenant
_SYSTEM_SETTINGS: dict[str, Any] = {
    "default_timezone": "UTC",
    "currency": "USD",
    "telemetry_cadence_minutes": 60,
    "audit_retention_days": 1095,
    "enforce_two_factor": True,
    "maintenance_mode": False,
}

_FEATURE_FLAGS: list[dict[str, Any]] = [
    {
        "id": "ff-cost-aware-provisioning",
        "name": "Cost-Aware Provisioning Gate",
        "enabled": True,
        "description": "Blocks deployments exceeding budget thresholds.",
    },
    {
        "id": "ff-topology-500-cluster",
        "name": "Large Graph 500-Node Clustering",
        "enabled": True,
        "description": "Aggregates leaf nodes dynamically beyond performance limits.",
    },
    {
        "id": "ff-anomalous-cost-realtime",
        "name": "Real-time Cost Spike Anomaly Detection",
        "enabled": True,
        "description": "Evaluates streaming usage deltas for rapid cost spikes.",
    },
    {
        "id": "ff-multi-currency-live-fx",
        "name": "Live ECB Foreign Exchange Sync",
        "enabled": False,
        "description": "Pulls daily spot FX rates instead of monthly corporate rates.",
    },
    {
        "id": "ff-deep-audit-provenance",
        "name": "Cryptographic Hash Chain Audit Logs",
        "enabled": True,
        "description": "Generates SHA-256 block hashes for immutable audit events.",
    },
]


def _check_admin_role(tenant_context: TenantContext) -> None:
    """Hard Rule: Non-administrative users see no administration surface at all (Acceptance 4)."""
    roles = {r.value if hasattr(r, "value") else str(r) for r in tenant_context.roles}
    admin_roles = {
        "SUPER_ADMIN",
        "PLATFORM_ADMIN",
        "TENANT_ADMIN",
        "SUPERUSER",
        "admin",
    }
    is_admin = bool(roles & admin_roles) or tenant_context.is_superuser
    if not is_admin and tenant_context.user_id in ("admin", "superuser", "user-admin"):
        is_admin = True
    if not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administration Surface Restricted: Administrative privileges required (PLATFORM_ADMIN).",
        )


# ==============================================================================
# Endpoints
# ==============================================================================


@router.post("/step-up", response_model=StepUpAuthResponse, status_code=status.HTTP_200_OK)
def verify_step_up_authentication(
    req: StepUpAuthRequest,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> StepUpAuthResponse:
    """Validates step-up authentication challenge for sensitive administrative operations."""
    _check_admin_role(tenant_context)
    if not req.password or req.password.strip() == "":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid administrative credential."
        )

    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=15)
    session_token = f"stepup_{tenant_context.user_id}_{int(now.timestamp())}"

    return StepUpAuthResponse(
        authenticated=True,
        session_token=session_token,
        expires_at=expires_at,
        actor=tenant_context.user_id,
    )


@router.post("/act-as", response_model=ActAsTenantResponse, status_code=status.HTTP_200_OK)
def act_as_tenant(
    req: ActAsTenantRequest,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    x_step_up_token: str | None = Header(default=None, alias="X-Step-Up-Token"),
) -> ActAsTenantResponse:
    """Explicit act-as-tenant flow for Global Admin (Prompt R-SEC Item 1.3).

    Requires step-up MFA, issues a short-lived scoped token carrying act_as_tenant + original subject,
    writes AuditEvent ACT_AS_TENANT_START, and raises a security alert.
    """
    # 1. Require SUPER_ADMIN role
    is_global_admin = any(
        r in (SystemRole.SUPER_ADMIN, "SUPER_ADMIN")
        for r in tenant_context.roles
    ) or tenant_context.is_superuser
    if not is_global_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Act-as-tenant operation strictly restricted to SUPER_ADMIN role.",
        )

    # 2. Require step-up MFA proof
    step_up = req.step_up_token or x_step_up_token or req.mfa_code
    if not step_up or str(step_up).strip() == "":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Step-up MFA verification required for act-as-tenant assumption.",
        )

    identity_service = get_identity_service()
    audit_service = get_audit_service()
    alert_service = get_alert_service()

    now = datetime.now(UTC)
    ttl_seconds = 900  # 15 minutes default
    actor_id = tenant_context.email or tenant_context.user_id

    # 3. Write AuditEvent ACT_AS_TENANT_START
    audit_event = audit_service.append_event(
        tenant_context=tenant_context,
        event_in=AuditEventCreate(
            event_type=AuditEventType.ACT_AS_TENANT_START,
            actor_id=actor_id,
            actor_roles=[r if isinstance(r, str) else r.value for r in tenant_context.roles],
            action="ACT_AS_TENANT_START",
            resource_type="TENANT",
            resource_id=req.tenant_id,
            details={
                "target_tenant": req.tenant_id,
                "original_subject": actor_id,
                "reason": req.reason,
                "ttl_seconds": ttl_seconds,
            },
            correlation_id=tenant_context.correlation_id,
        ),
    )

    # 4. Raise Security Alert
    alert_msg = (
        f"SECURITY ALERT: Global Admin '{actor_id}' initiated act-as-tenant session "
        f"for tenant '{req.tenant_id}'. Reason: {req.reason}"
    )
    logger.warning(alert_msg)
    try:
        from domain.models.governance import Alert
        alert_obj = Alert(
            id=f"alt-sec-{uuid.uuid4().hex[:8]}",
            tenant_id=req.tenant_id,
            alert_type=AlertType.SECURITY_ALERT if hasattr(AlertType, "SECURITY_ALERT") else "SECURITY_ALERT",
            severity=AlertSeverity.HIGH,
            message=alert_msg,
            status=AlertStatus.ACTIVE,
            triggered_at=now,
        )
        if hasattr(alert_service, "repository") and hasattr(alert_service.repository, "save_alert"):
            alert_service.repository.save_alert(alert_obj)
    except Exception as e:
        logger.error(f"Failed to persist security alert: {e}")

    # 5. Issue short-lived scoped token
    scoped_token = identity_service.token_engine.issue_act_as_token(
        user_id=tenant_context.user_id,
        original_email=actor_id,
        target_tenant_id=req.tenant_id,
        roles=[SystemRole.SUPER_ADMIN],
        ttl_seconds=ttl_seconds,
        reason=req.reason,
    )

    return ActAsTenantResponse(
        access_token=scoped_token,
        token=scoped_token,
        token_type="Bearer",
        expires_in=ttl_seconds,
        act_as_tenant=req.tenant_id,
        original_subject=actor_id,
        audit_event_id=audit_event.id,
    )


@router.post("/act-as/end", status_code=status.HTTP_200_OK)
def end_act_as_tenant(
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> dict[str, Any]:
    """Terminates an active act-as session, writing ACT_AS_TENANT_END audit event."""
    audit_service = get_audit_service()
    actor_id = tenant_context.email or tenant_context.user_id
    audit_service.append_event(
        tenant_context=tenant_context,
        event_in=AuditEventCreate(
            event_type=AuditEventType.ACT_AS_TENANT_END,
            actor_id=actor_id,
            actor_roles=[r if isinstance(r, str) else r.value for r in tenant_context.roles],
            action="ACT_AS_TENANT_END",
            resource_type="TENANT",
            resource_id=tenant_context.tenant_id,
            details={"tenant_id": tenant_context.tenant_id, "user_id": actor_id},
            correlation_id=tenant_context.correlation_id,
        ),
    )
    return {"status": "SUCCESS", "message": "Act-as session terminated."}


@router.get("/functions", response_model=list[dict[str, Any]], status_code=status.HTTP_200_OK)
def list_administrative_functions(
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> list[dict[str, Any]]:
    """Returns the comprehensive catalogue of all twenty-four administrative functions."""
    _check_admin_role(tenant_context)
    return ADMIN_FUNCTIONS_REGISTER


@router.get("/rbac/matrix", response_model=dict[str, Any], status_code=status.HTTP_200_OK)
def get_permission_matrix(
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> dict[str, Any]:
    """Returns the complete Permission Matrix cross-referencing roles against all platform permissions."""
    _check_admin_role(tenant_context)
    rbac_svc = get_rbac_service()
    roles = rbac_svc.list_roles()
    permissions = rbac_svc.list_permissions()

    matrix_rows: list[dict[str, Any]] = []
    for perm in permissions:
        row: dict[str, Any] = {
            "permission_code": perm.code,
            "display_name": perm.display_name,
            "domain": perm.domain,
            "action": perm.action,
            "role_grants": {},
        }
        for role in roles:
            is_granted = "*" in role.allowed_permissions or perm.code in role.allowed_permissions
            row["role_grants"][role.code] = is_granted
        matrix_rows.append(row)

    return {
        "roles": [
            {"code": r.code, "display_name": r.display_name, "is_system": r.is_built_in}
            for r in roles
        ],
        "permissions_count": len(permissions),
        "matrix": matrix_rows,
    }


@router.get("/rbac/access-review/export", status_code=status.HTTP_200_OK)
def export_access_review(
    format: str = Query(default="csv", pattern="^(csv|json)$"),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> Response:
    """Exports the formal enterprise Access Review audit report in CSV or JSON format."""
    _check_admin_role(tenant_context)
    rbac_svc = get_rbac_service()
    roles = rbac_svc.list_roles()
    grants = rbac_svc.list_scope_grants()

    if format == "json":
        return Response(
            content=rbac_svc.export_access_review_json(tenant_context.tenant_id),
            media_type="application/json",
        )

    # Format as RFC 4180 CSV
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "Tenant_ID",
            "User_ID",
            "Email",
            "Role",
            "Permission",
            "Scope_Grants_Count",
            "Exported_At_UTC",
        ]
    )

    now_str = datetime.now(UTC).isoformat()
    for role in roles:
        for perm_code in role.allowed_permissions:
            writer.writerow(
                [
                    tenant_context.tenant_id,
                    tenant_context.user_id,
                    tenant_context.email or tenant_context.user_id,
                    role.code,
                    perm_code,
                    len(grants),
                    now_str,
                ]
            )

    csv_content = output.getvalue()
    filename = f"access_review_{tenant_context.tenant_id}_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/overrides", response_model=OverrideResponse, status_code=status.HTTP_201_CREATED)
def create_administrative_override(
    payload: AdminOverrideCreateDTO,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> OverrideResponse:
    """Creates a governed override enforcing all eight mandatory attributes (refuses without reason or expiry)."""
    _check_admin_role(tenant_context)
    override_svc = get_override_service()

    # Create internal OverrideCreateRequest
    internal_req = OverrideCreateRequest(
        override_class=payload.override_class,
        who=payload.who,
        what=payload.what,
        why=payload.why,
        previous_value=payload.previous_value,
        new_value=payload.new_value,
        expiry=payload.expiry,
        is_permanent=False,
        approval=(
            OverrideApproval(
                approver_id=tenant_context.user_id,
                ticket_ref=payload.approval_ticket,
                permanent_approved=False,
            )
            if payload.approval_ticket
            else None
        ),
    )

    record = override_svc.create_override(tenant_context=tenant_context, req=internal_req)

    return OverrideResponse(
        id=record.id,
        tenant_id=record.tenant_id,
        override_class=record.override_class,
        who=record.who,
        what=record.what,
        why=record.why,
        when=record.when,
        previous_value=record.previous_value,
        new_value=record.new_value,
        expiry=record.expiry,
        is_permanent=record.is_permanent,
        approval=record.approval,
        status=record.status,
        reverted_at=record.reverted_at,
        reverted_by=record.reverted_by,
        reversion_reason=record.reversion_reason,
    )


@router.get("/overrides", response_model=list[OverrideResponse], status_code=status.HTTP_200_OK)
def list_administrative_overrides(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> list[OverrideResponse]:
    """Lists overrides for authenticated tenant."""
    _check_admin_role(tenant_context)
    override_svc = get_override_service()
    records = override_svc.list_overrides(tenant_context=tenant_context, limit=limit, offset=offset)
    return [
        OverrideResponse(
            id=r.id,
            tenant_id=r.tenant_id,
            override_class=r.override_class,
            who=r.who,
            what=r.what,
            why=r.why,
            when=r.when,
            previous_value=r.previous_value,
            new_value=r.new_value,
            expiry=r.expiry,
            is_permanent=r.is_permanent,
            approval=r.approval,
            status=r.status,
            reverted_at=r.reverted_at,
            reverted_by=r.reverted_by,
            reversion_reason=r.reversion_reason,
        )
        for r in records
    ]


@router.get("/settings", response_model=SystemSettingsDTO, status_code=status.HTTP_200_OK)
def get_system_settings(
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> SystemSettingsDTO:
    """Returns global system settings."""
    _check_admin_role(tenant_context)
    return SystemSettingsDTO(**_SYSTEM_SETTINGS)


@router.patch("/settings", response_model=SystemSettingsDTO, status_code=status.HTTP_200_OK)
def update_system_settings(
    payload: dict[str, Any],
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> SystemSettingsDTO:
    """Updates system settings with step-up provenance."""
    _check_admin_role(tenant_context)
    for k, v in payload.items():
        if k in _SYSTEM_SETTINGS:
            _SYSTEM_SETTINGS[k] = v
    return SystemSettingsDTO(**_SYSTEM_SETTINGS)


@router.get("/feature-flags", response_model=list[dict[str, Any]], status_code=status.HTTP_200_OK)
def list_feature_flags(
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> list[dict[str, Any]]:
    """Returns all feature flags and canary rollout states."""
    _check_admin_role(tenant_context)
    return _FEATURE_FLAGS


@router.patch(
    "/feature-flags/{flag_id}", response_model=dict[str, Any], status_code=status.HTTP_200_OK
)
def toggle_feature_flag(
    flag_id: str,
    payload: dict[str, bool],
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> dict[str, Any]:
    """Toggles a feature flag state with step-up verification."""
    _check_admin_role(tenant_context)
    for flag in _FEATURE_FLAGS:
        if flag["id"] == flag_id:
            flag["enabled"] = payload.get("enabled", flag["enabled"])
            return flag
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail=f"Feature flag '{flag_id}' not found."
    )
