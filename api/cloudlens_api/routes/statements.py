"""Showback Statements, Chargeback & Cost Allocation Packs REST API Endpoints (Prompt 52).

Enforces:
- API-053: GET /api/v1/statements - Showback statements and variance analysis.
- Full TenantContext authentication on all routes.
- Period close cycle: generation, circulation, finalisation, non-destructive restatement adjustments.
- Line disputes routed to generic workflow engine with tracked SLA.
- Formal acceptance and executive outstanding-acceptance reporting.
- Allocation transparency drill-through with financial-detail permission enforcement.
- ResponseMetadata envelopes and standard enterprise HTTP error handling.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

from api.cloudlens_api.conventions.models import ResponseMetadata
from api.cloudlens_api.tenant_context import get_authenticated_tenant_context
from domain.models.exceptions import (
    FinalisedStatementModificationForbiddenException,
    MissingApportionmentBasisException,
    StatementAlreadyFinalisedException,
    StatementDisputeException,
    StatementNotFoundException,
)
from domain.statements.models import (
    AllocationTransparencyView,
    ExportFormat,
    OutstandingAcceptanceReport,
    RecipientScopeType,
    ShowbackStatement,
    StatementDispute,
    StatementLifecycleStatus,
    StatementTemplate,
)
from domain.statements.service import StatementService, get_statement_service
from domain.tenant.context import TenantContext

router = APIRouter(prefix="/api/v1/statements", tags=["Showback & Cost Allocation Statements"])


# ==============================================================================
# Request & Response Envelopes
# ==============================================================================


class GenerateStatementRequest(BaseModel):
    """Payload to generate a new showback statement."""

    period: str = Field(..., description="Target billing period partition, e.g. '2026-09'")
    scope_type: RecipientScopeType = Field(
        default=RecipientScopeType.BUSINESS_UNIT,
        description="Scope type (BUSINESS_UNIT, COST_CENTRE, APPLICATION, PROJECT, TEAM)",
    )
    scope_code: str = Field(default="BU-RETAIL", description="Scope code")
    scope_name: str = Field(default="Retail & E-Commerce Business Unit", description="Scope title")
    recipient_owner_id: str | None = Field(
        default=None, description="Recipient owner user ID (resolved from master data if omitted)"
    )
    recipient_owner_email: str | None = Field(
        default=None, description="Recipient email (resolved from master data if omitted)"
    )
    template_id: str | None = Field(default=None, description="Layout template ID")
    target_currency: str = Field(default="USD", description="Presentation currency code")
    custom_budget: float | None = Field(default=None, description="Optional custom budget override")
    enable_chargeback_phase2: bool = Field(
        default=False, description="Phase 2 toggle. Statements state they are showback when False."
    )


class CirculateStatementRequest(BaseModel):
    """Payload to circulate statement for review."""

    review_window_days: int = Field(
        default=5, ge=1, le=30, description="Review window duration in days"
    )


class FinalizeStatementRequest(BaseModel):
    """Payload to finalise statement."""

    notes: str | None = Field(default=None, description="Optional period close sign-off notes")


class RestatementAdjustmentRequest(BaseModel):
    """Payload to emit post-finalisation restatement adjustment."""

    restatement_reason: str = Field(
        ..., min_length=5, description="Business justification for restatement"
    )
    adjustment_deltas: list[dict[str, Any]] = Field(
        ..., min_length=1, description="Line-level deltas to apply"
    )


class RaiseDisputeRequest(BaseModel):
    """Payload to query/dispute a statement line."""

    line_id: str = Field(..., description="Target line ID (e.g. srv-k8s-platform, AmazonEC2)")
    line_description: str = Field(default="Statement Line Query", description="Line title")
    disputed_amount: float = Field(..., gt=0, description="Amount under dispute")
    proposed_amount: float = Field(default=0.0, ge=0, description="Expected amount")
    reason: str = Field(..., min_length=5, description="Dispute explanation and evidence")
    assigned_owner: str | None = Field(
        default=None, description="Assigned investigator (resolved from master data if omitted)"
    )


class ResolveDisputeRequest(BaseModel):
    """Payload to resolve an existing dispute."""

    decision: str = Field(..., description="APPROVED or REJECTED")
    resolution_notes: str = Field(..., min_length=3, description="Resolution rationale")
    target_reallocation_scope: str | None = Field(
        default=None, description="Scope code to debit if reallocation approved"
    )


class AcceptStatementRequest(BaseModel):
    """Payload for formal recipient statement acceptance."""

    notes: str | None = Field(default=None, description="Recipient sign-off comments")


class StatementListResponse(BaseModel):
    """List response envelope for statements."""

    statements: list[ShowbackStatement]
    total_count: int
    metadata: ResponseMetadata = Field(default_factory=ResponseMetadata, alias="_metadata")


# ==============================================================================
# Endpoints
# ==============================================================================


@router.post("/generate", response_model=ShowbackStatement, status_code=status.HTTP_201_CREATED)
def generate_statement(
    request: GenerateStatementRequest,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: StatementService = Depends(get_statement_service),
) -> ShowbackStatement:
    """Generates an authoritative showback statement and cost allocation pack."""
    try:
        return service.generate_statement(
            period=request.period,
            scope_type=request.scope_type,
            scope_code=request.scope_code,
            scope_name=request.scope_name,
            recipient_owner_id=request.recipient_owner_id,
            recipient_owner_email=request.recipient_owner_email,
            template_id=request.template_id,
            target_currency=request.target_currency,
            custom_budget=request.custom_budget,
            enable_chargeback_phase2=request.enable_chargeback_phase2,
            tenant_context=tenant_context,
        )
    except MissingApportionmentBasisException as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.get("", response_model=StatementListResponse)
def list_statements(
    period: str | None = Query(default=None, description="Billing period filter (e.g. 2026-09)"),
    scope_code: str | None = Query(default=None, description="Scope code filter (e.g. BU-RETAIL)"),
    status_filter: StatementLifecycleStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: StatementService = Depends(get_statement_service),
) -> StatementListResponse:
    """API-053: Lists showback statements and variance analysis for the tenant."""
    items = service.list_statements(
        tenant_context=tenant_context,
        period=period,
        scope_code=scope_code,
        status=status_filter,
        limit=limit,
        offset=offset,
    )
    total = len(
        service.list_statements(
            tenant_context=tenant_context,
            period=period,
            scope_code=scope_code,
            status=status_filter,
            limit=5000,
            offset=0,
        )
    )
    return StatementListResponse(
        statements=items,
        total_count=total,
        _metadata=ResponseMetadata(period=period),
    )


@router.get("/templates", response_model=list[StatementTemplate])
def list_statement_templates(
    service: StatementService = Depends(get_statement_service),
) -> list[StatementTemplate]:
    """Lists available master-data statement layout templates."""
    return service.list_templates()


@router.get("/reports/outstanding-acceptance", response_model=OutstandingAcceptanceReport)
def get_outstanding_acceptance_report(
    period: str = Query(default="2026-09", description="Billing period to audit"),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: StatementService = Depends(get_statement_service),
) -> OutstandingAcceptanceReport:
    """Generates an executive compliance report of unaccepted/overdue showback statements."""
    return service.get_outstanding_acceptance_report(period, tenant_context=tenant_context)


@router.get("/{statement_id}", response_model=ShowbackStatement)
def get_statement(
    statement_id: str,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: StatementService = Depends(get_statement_service),
) -> ShowbackStatement:
    """Retrieves a specific showback statement pack by identifier."""
    try:
        return service.get_statement(statement_id, tenant_context=tenant_context)
    except StatementNotFoundException as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/{statement_id}/circulate", response_model=ShowbackStatement)
def circulate_statement(
    statement_id: str,
    request: CirculateStatementRequest,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: StatementService = Depends(get_statement_service),
) -> ShowbackStatement:
    """Circulates a draft statement to recipients and opens the formal review window."""
    try:
        return service.circulate_statement(
            statement_id,
            review_window_days=request.review_window_days,
            tenant_context=tenant_context,
        )
    except StatementNotFoundException as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/{statement_id}/finalize", response_model=ShowbackStatement)
def finalize_statement(
    statement_id: str,
    request: FinalizeStatementRequest | None = None,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: StatementService = Depends(get_statement_service),
) -> ShowbackStatement:
    """Finalises the showback statement, locking it against any in-place modification."""
    _ = request
    try:
        return service.finalise_statement(statement_id, tenant_context=tenant_context)
    except StatementNotFoundException as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except StatementAlreadyFinalisedException as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/{statement_id}/accept", response_model=ShowbackStatement)
def accept_statement(
    statement_id: str,
    request: AcceptStatementRequest | None = None,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: StatementService = Depends(get_statement_service),
) -> ShowbackStatement:
    """Records formal recipient sign-off and acceptance of the statement."""
    notes = request.notes if request else None
    try:
        return service.accept_statement(statement_id, notes=notes, tenant_context=tenant_context)
    except StatementNotFoundException as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/{statement_id}/adjust", response_model=ShowbackStatement)
def adjust_finalised_statement(
    statement_id: str,
    request: RestatementAdjustmentRequest,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: StatementService = Depends(get_statement_service),
) -> ShowbackStatement:
    """Emits a new adjusted statement version following a post-finalisation restatement.

    Rule: Never alters a finalised statement in-place.
    """
    try:
        adj_stmt, _ = service.process_restatement_adjustment(
            statement_id,
            adjustment_deltas=request.adjustment_deltas,
            restatement_reason=request.restatement_reason,
            tenant_context=tenant_context,
        )
        return adj_stmt
    except StatementNotFoundException as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except FinalisedStatementModificationForbiddenException as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post(
    "/{statement_id}/disputes", response_model=StatementDispute, status_code=status.HTTP_201_CREATED
)
def raise_statement_dispute(
    statement_id: str,
    request: RaiseDisputeRequest,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: StatementService = Depends(get_statement_service),
) -> StatementDispute:
    """Queries/disputes a statement line item, creating a tracked dispute routed to the workflow engine."""
    try:
        return service.raise_dispute(
            statement_id,
            line_id=request.line_id,
            line_description=request.line_description,
            disputed_amount=request.disputed_amount,
            proposed_amount=request.proposed_amount,
            reason=request.reason,
            assigned_owner=request.assigned_owner,
            tenant_context=tenant_context,
        )
    except StatementNotFoundException as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except StatementDisputeException as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/{statement_id}/disputes", response_model=list[StatementDispute])
def list_statement_disputes(
    statement_id: str,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: StatementService = Depends(get_statement_service),
) -> list[StatementDispute]:
    """Lists all active and resolved disputes associated with a statement."""
    return service.list_disputes(statement_id, tenant_context=tenant_context)


@router.post("/{statement_id}/disputes/{dispute_id}/resolve", response_model=StatementDispute)
def resolve_statement_dispute(
    statement_id: str,
    dispute_id: str,
    request: ResolveDisputeRequest,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: StatementService = Depends(get_statement_service),
) -> StatementDispute:
    """Resolves a statement dispute: if approved, applies a documented reallocation with an audit trail."""
    _ = statement_id
    try:
        resolved, _ = service.resolve_dispute(
            dispute_id,
            decision=request.decision,
            resolution_notes=request.resolution_notes,
            target_reallocation_scope=request.target_reallocation_scope,
            tenant_context=tenant_context,
        )
        return resolved
    except StatementNotFoundException as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except StatementDisputeException as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get(
    "/{statement_id}/lines/{line_id}/transparency", response_model=AllocationTransparencyView
)
def get_allocation_transparency(
    statement_id: str,
    line_id: str,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: StatementService = Depends(get_statement_service),
) -> AllocationTransparencyView:
    """Provides line-level attribution provenance, rule tracing, and permissioned drill-through."""
    try:
        return service.get_allocation_transparency(
            statement_id, line_id=line_id, tenant_context=tenant_context
        )
    except StatementNotFoundException as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/{statement_id}/export")
def export_statement(
    statement_id: str,
    format: ExportFormat = Query(default=ExportFormat.MARKDOWN, description="Export format"),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: StatementService = Depends(get_statement_service),
) -> Response:
    """Exports the showback statement in the requested format (MARKDOWN, CSV, JSON, HTML)."""
    try:
        content = service.export_statement(
            statement_id, format=format, tenant_context=tenant_context
        )
        media_type = "text/markdown"
        if format == ExportFormat.CSV:
            media_type = "text/csv"
        elif format == ExportFormat.JSON:
            media_type = "application/json"
        elif format == ExportFormat.HTML:
            media_type = "text/html"
        return Response(content=content, media_type=media_type)
    except StatementNotFoundException as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/{statement_id}/distribute")
def distribute_statement(
    statement_id: str,
    channels: list[str] | None = None,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: StatementService = Depends(get_statement_service),
) -> dict[str, Any]:
    """Dispatches statement to object storage and simulated email delivery channels."""
    try:
        return service.distribute_statement(
            statement_id, channels=channels, tenant_context=tenant_context
        )
    except StatementNotFoundException as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
