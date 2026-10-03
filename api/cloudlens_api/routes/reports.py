"""Reporting and Asynchronous Export API Routes (API-047 & API-048 / Prompt 34 / Prompt 35).

Enforces:
- API-047: GET /api/v1/reports - List generated reports and available report templates.
- API-048: POST /api/v1/reports/export - Trigger asynchronous report export generation.
- GET /api/v1/reports/downloads/{report_id} - Time-limited download endpoint with audit logging.
- GET /api/v1/reports/jobs/{job_id} - Job polling endpoint.
- Response metadata envelope, cursor pagination, and standard error handling.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field

from api.cloudlens_api.conventions.filtering import decode_cursor, encode_cursor
from api.cloudlens_api.conventions.models import ResponseMetadata
from api.cloudlens_api.tenant_context import get_authenticated_tenant_context
from domain.models.exceptions import (
    DownloadLinkExpiredException,
    FeatureNotEnabledException,
    InvalidDownloadTokenException,
    ReportJobNotFoundException,
    ReportTemplateNotFoundException,
    UnsupportedReportFormatException,
)
from domain.reports.catalogue import MASTER_REPORT_CATALOGUE
from domain.reports.models import ExportFormat, ReportParameters
from domain.reports.service import ReportService, get_report_service
from domain.tenant.context import TenantContext

router = APIRouter(prefix="/api/v1/reports", tags=["Reporting & Exports"])


class ReportTemplate(BaseModel):
    """Available system or custom report template."""

    id: str
    name: str
    description: str
    category: str
    supported_formats: list[str] = Field(default_factory=lambda: ["CSV", "JSON", "PDF", "PARQUET"])


class GeneratedReport(BaseModel):
    """Metadata record for a generated report."""

    id: str
    tenant_id: str
    template_id: str
    name: str
    format: str
    status: str
    created_at: str
    download_url: str | None = None
    row_count: int = 0
    file_size_bytes: int = 0


class ReportExportRequest(BaseModel):
    """Payload to trigger asynchronous report export generation (API-048)."""

    template_id: str = Field(..., description="Target report template ID")
    format: str = Field(default="CSV", description="Export format: CSV, JSON, PDF, PARQUET")
    parameters: dict[str, Any] = Field(
        default_factory=dict, description="Filter parameters for report"
    )


class ReportExportResponse(BaseModel):
    """Response returned upon triggering an asynchronous report export (API-048)."""

    model_config = ConfigDict(populate_by_name=True)

    job_id: str
    report_id: str
    status: str
    template_id: str
    format: str
    created_at: str
    estimated_completion_seconds: int = 5
    metadata: ResponseMetadata = Field(default_factory=ResponseMetadata, alias="_metadata")


class ReportListResponse(BaseModel):
    """List of generated reports and available templates (API-047)."""

    model_config = ConfigDict(populate_by_name=True)

    templates: list[ReportTemplate]
    reports: list[GeneratedReport]
    total_reports: int
    next_cursor: str | None = None
    limit: int = 50
    metadata: ResponseMetadata = Field(default_factory=ResponseMetadata, alias="_metadata")


class ScheduleCreateRequest(BaseModel):
    """Payload to create a recurring report schedule (Phase 2)."""

    template_id: str = Field(..., description="Target report template ID")
    cron_expression: str = Field(..., description="Cron expression (e.g. '0 8 1 * *')")
    format: str = Field(default="PDF", description="Export format")
    recipients: list[str] = Field(default_factory=list, description="Target email recipients")
    storage_destination: str | None = Field(default=None, description="Object storage URI")
    parameters: dict[str, Any] = Field(default_factory=dict, description="Filter parameters")


class ScheduleResponse(BaseModel):
    """Scheduled report response (Phase 2)."""

    id: str
    template_id: str
    cron_expression: str
    format: str
    recipients: list[str]
    storage_destination: str | None
    is_active: bool
    created_at: str
    next_run_at: str | None


# Canonical Master Templates populated from domain catalogue
MASTER_TEMPLATES: list[ReportTemplate] = [
    ReportTemplate(
        id=d.id,
        name=d.name,
        description=d.description,
        category=d.category.value,
        supported_formats=[f.value for f in d.supported_formats],
    )
    for d in MASTER_REPORT_CATALOGUE
]


@router.get("", response_model=ReportListResponse, status_code=status.HTTP_200_OK)
async def list_reports_and_templates(
    category: str | None = Query(default=None, description="Filter templates by category"),
    limit: int = Query(default=50, ge=1, le=500, description="Page limit for generated reports"),
    cursor: str | None = Query(default=None, description="Pagination cursor"),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: ReportService = Depends(get_report_service),
) -> ReportListResponse:
    """Lists generated reports and available report templates (API-047)."""
    offset = decode_cursor(cursor)

    matched_templates = [
        tpl for tpl in MASTER_TEMPLATES if not category or tpl.category.lower() == category.lower()
    ]

    jobs = service.list_report_jobs(tenant_context=tenant_context, limit=limit, offset=offset)
    total_reps = len(service.list_report_jobs(tenant_context=tenant_context, limit=500, offset=0))

    converted_reports = [
        GeneratedReport(
            id=j.download_url.split("/downloads/")[1].split("?")[0]
            if j.download_url and "/downloads/" in j.download_url
            else j.id,
            tenant_id=j.tenant_id,
            template_id=j.template_id,
            name=f"{j.template_id} - {j.created_at.strftime('%Y-%m-%d')}",
            format=j.format.value,
            status=j.status,
            created_at=j.created_at.isoformat(),
            download_url=j.download_url,
            row_count=j.row_count,
            file_size_bytes=j.file_size_bytes,
        )
        for j in jobs
    ]

    next_cursor = encode_cursor(offset + limit) if (offset + limit) < total_reps else None

    return ReportListResponse(
        templates=matched_templates,
        reports=converted_reports,
        total_reports=total_reps,
        next_cursor=next_cursor,
        limit=limit,
        _metadata=ResponseMetadata(),
    )


@router.post("/export", response_model=ReportExportResponse, status_code=status.HTTP_202_ACCEPTED)
async def trigger_report_export(
    payload: ReportExportRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: ReportService = Depends(get_report_service),
) -> ReportExportResponse:
    """Triggers asynchronous report export generation with provenance footer (API-048)."""
    _ = idempotency_key

    # Format parsing
    fmt_str = payload.format.upper()
    try:
        req_format = ExportFormat(fmt_str)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Format '{payload.format}' is not supported. Supported: {[f.value for f in ExportFormat]}",
        ) from err

    # Parameter parsing
    params = ReportParameters(
        period=payload.parameters.get("period"),
        scope_id=payload.parameters.get("scope_id"),
        provider=payload.parameters.get("provider"),
        grouping=payload.parameters.get("grouping"),
        currency=payload.parameters.get("currency", "USD"),
        cost_basis=payload.parameters.get("cost_basis", "BILLED"),
        include_unallocated=payload.parameters.get("include_unallocated", False),
        custom_filters=payload.parameters,
    )

    try:
        job, _ = service.generate_report(
            template_id=payload.template_id,
            parameters=params,
            format_type=req_format,
            async_generation=True,
            tenant_context=tenant_context,
        )
    except ReportTemplateNotFoundException as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except UnsupportedReportFormatException as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except FeatureNotEnabledException as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    report_id = (
        job.download_url.split("/downloads/")[1].split("?")[0]
        if job.download_url and "/downloads/" in job.download_url
        else job.id
    )

    return ReportExportResponse(
        job_id=job.id,
        report_id=report_id,
        status="ACCEPTED",
        template_id=job.template_id,
        format=job.format.value,
        created_at=job.created_at.isoformat(),
        estimated_completion_seconds=3,
        _metadata=ResponseMetadata(),
    )


@router.get("/downloads/{report_id}", status_code=status.HTTP_200_OK)
async def download_report_artifact(
    report_id: str,
    token: str = Query(..., description="Time-limited secure download token"),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: ReportService = Depends(get_report_service),
) -> Response:
    """Downloads generated report artifact with token validation and audit tracking."""
    try:
        content_bytes, job = service.download_report(
            report_id=report_id,
            token=token,
            tenant_context=tenant_context,
        )
    except ReportJobNotFoundException as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except InvalidDownloadTokenException as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except DownloadLinkExpiredException as exc:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail=str(exc)) from exc

    media_map = {
        ExportFormat.CSV: "text/csv; charset=utf-8",
        ExportFormat.JSON: "application/json",
        ExportFormat.XLSX: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ExportFormat.PDF: "application/pdf",
        ExportFormat.PARQUET: "application/octet-stream",
    }
    media_type = media_map.get(job.format, "application/octet-stream")

    return Response(
        content=content_bytes,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{job.output_filename}"',
            "X-Report-Template": job.template_id,
            "X-Report-Format": job.format.value,
        },
    )


@router.post("/schedules", response_model=ScheduleResponse, status_code=status.HTTP_201_CREATED)
async def create_recurring_schedule(
    payload: ScheduleCreateRequest,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: ReportService = Depends(get_report_service),
) -> ScheduleResponse:
    """Creates a recurring report delivery schedule (Phase 2 feature flag gated)."""
    try:
        fmt = ExportFormat(payload.format.upper())
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported format '{payload.format}'",
        ) from err

    params = ReportParameters(custom_filters=payload.parameters)
    try:
        sched = service.create_schedule(
            template_id=payload.template_id,
            parameters=params,
            format_type=fmt,
            cron_expression=payload.cron_expression,
            recipients=payload.recipients,
            storage_destination=payload.storage_destination,
            tenant_context=tenant_context,
        )
    except FeatureNotEnabledException as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ReportTemplateNotFoundException as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return ScheduleResponse(
        id=sched.id,
        template_id=sched.template_id,
        cron_expression=sched.cron_expression,
        format=sched.format.value,
        recipients=sched.recipients,
        storage_destination=sched.storage_destination,
        is_active=sched.is_active,
        created_at=sched.created_at.isoformat(),
        next_run_at=sched.next_run_at.isoformat() if sched.next_run_at else None,
    )


@router.get("/schedules", response_model=list[ScheduleResponse], status_code=status.HTTP_200_OK)
async def list_recurring_schedules(
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: ReportService = Depends(get_report_service),
) -> list[ScheduleResponse]:
    """Lists recurring report delivery schedules (Phase 2 feature flag gated)."""
    try:
        schedules = service.list_schedules(tenant_context=tenant_context)
    except FeatureNotEnabledException as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    return [
        ScheduleResponse(
            id=s.id,
            template_id=s.template_id,
            cron_expression=s.cron_expression,
            format=s.format.value,
            recipients=s.recipients,
            storage_destination=s.storage_destination,
            is_active=s.is_active,
            created_at=s.created_at.isoformat(),
            next_run_at=s.next_run_at.isoformat() if s.next_run_at else None,
        )
        for s in schedules
    ]
