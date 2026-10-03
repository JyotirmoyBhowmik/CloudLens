"""Bulk Data Import & Onboarding REST API Endpoints (API-058 / Prompt 53).

Exposes:
- GET /api/v1/imports/entities: List importable entities and metadata.
- GET /api/v1/imports/templates/{entity_type}: Template download with column definitions and valid values.
- GET /api/v1/imports/export/{entity_type}: Export entity data with round-trip symmetry.
- POST /api/v1/imports/profiles: Create saved mapping profile.
- GET /api/v1/imports/profiles: List mapping profiles for tenant.
- POST /api/v1/imports/dry-run: Execute mandatory dry-run validation.
- GET /api/v1/imports/dry-run/{dry_run_id}/result: Download dry-run result report file.
- POST /api/v1/imports/{dry_run_id}/apply: Apply validated import.
- POST /api/v1/imports/{import_run_id}/rollback: Reverse import within configured window.
- GET /api/v1/imports/history: List historical import runs.
- GET /api/v1/imports/history/{import_run_id}: Get detailed run report.
- POST /api/v1/imports/scheduled: Create recurring unattended feed schedule.
- GET /api/v1/imports/scheduled: List scheduled jobs.
- POST /api/v1/imports/scheduled/{job_id}/run: Execute scheduled unattended feed.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Response,
    status,
)
from pydantic import BaseModel, Field

from api.cloudlens_api.tenant_context import get_authenticated_tenant_context
from domain.bulk_import.catalogue import (
    get_import_catalogue,
)
from domain.bulk_import.engine import (
    get_bulk_import_engine,
)
from domain.bulk_import.models import (
    AtomicityPolicy,
    DryRunSummary,
    EntityImportMetadata,
    ImportMode,
    ImportRunRecord,
    MappingProfile,
    ScheduledImportJob,
)
from domain.bulk_import.repository import (
    get_bulk_import_repository,
)
from domain.bulk_import.scheduler import (
    get_scheduled_import_scheduler,
)
from domain.models.exceptions import (
    BulkImportException,
    DryRunRequiredException,
    ImportRunNotFoundException,
    ImportValidationException,
    RollbackBlockedException,
    RollbackWindowExpiredException,
    ScheduledImportJobNotFoundException,
)
from domain.tenant.context import TenantContext

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/imports", tags=["Bulk Import & Onboarding"])


# ==============================================================================
# Request DTOs
# ==============================================================================


class CreateMappingProfileRequest(BaseModel):
    name: str = Field(..., description="User-friendly name of mapping profile")
    entity_type: str = Field(..., description="Target importable entity type")
    column_mappings: dict[str, str] = Field(
        default_factory=dict, description="Source column name -> Target canonical field name"
    )
    default_values: dict[str, Any] = Field(
        default_factory=dict, description="Default fallback values for unmapped required fields"
    )


class DryRunJsonRequest(BaseModel):
    entity_type: str
    mode: ImportMode
    atomicity_policy: AtomicityPolicy | None = None
    mapping_profile_id: str | None = None
    filename: str = "import_payload.csv"
    content: str = Field(..., description="Raw text content in CSV, TSV, or JSON format")


class RollbackRequest(BaseModel):
    reason: str = Field(default="Manual user rollback", description="Reason for reversing import")
    actor_id: str = Field(default="api_user", description="Identity of requesting actor")


class CreateScheduledJobRequest(BaseModel):
    name: str
    entity_type: str
    cron_expression: str = "0 2 * * *"
    mapping_profile_id: str
    mode: ImportMode
    source_type: str = "CMDB_CONNECTOR"
    source_uri: str
    enabled: bool = True


# ==============================================================================
# 1. Entity Specifications & Template Downloads
# ==============================================================================


@router.get("/entities", response_model=list[EntityImportMetadata])
async def list_importable_entities() -> list[EntityImportMetadata]:
    """Lists all registered importable entities with schemas, columns, and atomicity policies."""
    catalogue = get_import_catalogue()
    return catalogue.list_all()


@router.get("/entities/{entity_type}", response_model=EntityImportMetadata)
async def get_entity_metadata(entity_type: str) -> EntityImportMetadata:
    """Retrieves import specification metadata for a specific entity type."""
    catalogue = get_import_catalogue()
    meta = catalogue.get_metadata(entity_type)
    if not meta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Entity type '{entity_type}' is not registered as importable.",
        )
    return meta


@router.get("/templates/{entity_type}")
async def download_template(
    entity_type: str,
    format: str = Query("csv", description="Template format: csv or json"),
) -> Response:
    """Downloads import template file with column definitions, descriptions, and sample values."""
    engine = get_bulk_import_engine()
    try:
        content = engine.generate_template(entity_type, export_format=format)
        media_type = "text/csv" if format.lower() == "csv" else "application/json"
        filename = f"{entity_type.lower()}_template.{format.lower()}"
        return Response(
            content=content,
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except BulkImportException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message) from e


@router.get("/export/{entity_type}")
async def export_entity_data(
    entity_type: str,
    format: str = Query("csv", description="Export format: csv or json"),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> Response:
    """Exports current entity records with export symmetry (round-trip edit-and-reimport)."""
    engine = get_bulk_import_engine()
    try:
        content = engine.export_entity(entity_type, tenant_context, export_format=format)
        media_type = "text/csv" if format.lower() == "csv" else "application/json"
        filename = f"{entity_type.lower()}_export.{format.lower()}"
        return Response(
            content=content,
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except BulkImportException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message) from e


# ==============================================================================
# 2. Mapping Profiles
# ==============================================================================


@router.post("/profiles", response_model=MappingProfile, status_code=status.HTTP_201_CREATED)
async def create_mapping_profile(
    payload: CreateMappingProfileRequest,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> MappingProfile:
    """Creates a saved mapping profile for repeated imports (Prompt 53)."""
    repo = get_bulk_import_repository()
    profile_id = f"prof-{uuid.uuid4().hex[:10]}"
    profile = MappingProfile(
        id=profile_id,
        tenant_id=tenant_context.tenant_id,
        name=payload.name,
        entity_type=payload.entity_type,
        column_mappings=payload.column_mappings,
        default_values=payload.default_values,
        created_by="api_user",
    )
    return repo.save_mapping_profile(profile, tenant_context=tenant_context)


@router.get("/profiles", response_model=list[MappingProfile])
async def list_mapping_profiles(
    entity_type: str | None = Query(None, description="Optional entity type filter"),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> list[MappingProfile]:
    """Lists saved mapping profiles for the authenticated tenant."""
    repo = get_bulk_import_repository()
    return repo.list_mapping_profiles(tenant_context=tenant_context, entity_type=entity_type)


# ==============================================================================
# 3. Dry-Run Validation (Mandatory Step)
# ==============================================================================


@router.post("/dry-run", response_model=DryRunSummary)
async def execute_dry_run_json(
    payload: DryRunJsonRequest,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> DryRunSummary:
    """Executes mandatory complete dry-run validation reporting created, updated, skipped, rejected rows."""
    engine = get_bulk_import_engine()
    try:
        content_bytes = payload.content.encode("utf-8")
        return engine.execute_dry_run(
            content_bytes=content_bytes,
            filename=payload.filename,
            entity_type=payload.entity_type,
            mode=payload.mode,
            atomicity_policy=payload.atomicity_policy,
            mapping_profile_id=payload.mapping_profile_id,
            tenant_context=tenant_context,
            actor_id="api_user",
        )
    except BulkImportException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message) from e


class UploadDryRunRequest(BaseModel):
    entity_type: str
    mode: ImportMode
    atomicity_policy: AtomicityPolicy | None = None
    mapping_profile_id: str | None = None
    filename: str = "uploaded_file.csv"
    content: str = Field(..., description="Uploaded raw file content in CSV, TSV, or JSON format")
    content_base64: str | None = Field(
        default=None, description="Optional Base64-encoded file content"
    )


@router.post("/upload/dry-run", response_model=DryRunSummary)
async def execute_dry_run_upload(
    payload: UploadDryRunRequest,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> DryRunSummary:
    """Executes mandatory complete dry-run validation from uploaded file payload."""
    engine = get_bulk_import_engine()
    try:
        if payload.content_base64:
            import base64

            content_bytes = base64.b64decode(payload.content_base64)
        else:
            content_bytes = payload.content.encode("utf-8")
        return engine.execute_dry_run(
            content_bytes=content_bytes,
            filename=payload.filename,
            entity_type=payload.entity_type,
            mode=payload.mode,
            atomicity_policy=payload.atomicity_policy,
            mapping_profile_id=payload.mapping_profile_id,
            tenant_context=tenant_context,
            actor_id="api_user",
        )
    except BulkImportException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message) from e


@router.get("/dry-run/{dry_run_id}/result")
async def download_dry_run_result(
    dry_run_id: str,
    format: str = Query("csv", description="Result report format: csv or json"),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> Response:
    """Downloads per-row dry-run validation result file before anything is written (Prompt 53)."""
    repo = get_bulk_import_repository()
    engine = get_bulk_import_engine()
    dry_run = repo.get_dry_run(dry_run_id, tenant_context=tenant_context)
    if not dry_run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dry run result '{dry_run_id}' not found.",
        )

    content = engine.generate_dry_run_download_result(dry_run, export_format=format)
    media_type = "text/csv" if format.lower() == "csv" else "application/json"
    filename = f"dry_run_{dry_run_id}_result.{format.lower()}"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ==============================================================================
# 4. Applying Import
# ==============================================================================


@router.post("/{dry_run_id}/apply", response_model=ImportRunRecord)
async def apply_import(
    dry_run_id: str,
    actor_id: str = Query("api_user", description="Executing actor identity"),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> ImportRunRecord:
    """Applies a previously validated dry run. Enforces: Do not apply an import without a dry run."""
    engine = get_bulk_import_engine()
    try:
        return engine.apply_import(
            dry_run_id=dry_run_id,
            tenant_context=tenant_context,
            actor_id=actor_id,
        )
    except DryRunRequiredException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message) from e
    except ImportValidationException as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=e.message
        ) from e
    except BulkImportException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message) from e


# ==============================================================================
# 5. Rollback Path
# ==============================================================================


@router.post("/{import_run_id}/rollback", response_model=ImportRunRecord)
async def rollback_import(
    import_run_id: str,
    payload: RollbackRequest,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> ImportRunRecord:
    """Reverses an applied import run within configured window with dependent change guard (Prompt 53)."""
    engine = get_bulk_import_engine()
    try:
        return engine.rollback_import(
            import_run_id=import_run_id,
            tenant_context=tenant_context,
            actor_id=payload.actor_id,
            reason=payload.reason,
        )
    except ImportRunNotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message) from e
    except RollbackWindowExpiredException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message) from e
    except RollbackBlockedException as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=e.message) from e
    except BulkImportException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message) from e


# ==============================================================================
# 6. Import History & Audit
# ==============================================================================


@router.get("/history", response_model=list[ImportRunRecord])
async def list_import_history(
    entity_type: str | None = Query(None, description="Optional entity type filter"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> list[ImportRunRecord]:
    """Retrieves import history runs with outcomes, duration, and status (Prompt 53)."""
    repo = get_bulk_import_repository()
    return repo.list_import_runs(
        tenant_context=tenant_context, entity_type=entity_type, limit=limit, offset=offset
    )


@router.get("/history/{import_run_id}", response_model=ImportRunRecord)
async def get_import_run_detail(
    import_run_id: str,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> ImportRunRecord:
    """Retrieves full execution details and audit report for an import run."""
    repo = get_bulk_import_repository()
    run = repo.get_import_run(import_run_id, tenant_context=tenant_context)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Import run '{import_run_id}' not found.",
        )
    return run


# ==============================================================================
# 7. Scheduled Import Feeds
# ==============================================================================


@router.post("/scheduled", response_model=ScheduledImportJob, status_code=status.HTTP_201_CREATED)
async def create_scheduled_import_job(
    payload: CreateScheduledJobRequest,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> ScheduledImportJob:
    """Registers a scheduled unattended import feed (Prompt 53)."""
    scheduler = get_scheduled_import_scheduler()
    return scheduler.create_scheduled_job(
        name=payload.name,
        entity_type=payload.entity_type,
        cron_expression=payload.cron_expression,
        mapping_profile_id=payload.mapping_profile_id,
        mode=payload.mode,
        source_type=payload.source_type,
        source_uri=payload.source_uri,
        enabled=payload.enabled,
        tenant_context=tenant_context,
    )


@router.get("/scheduled", response_model=list[ScheduledImportJob])
async def list_scheduled_jobs(
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> list[ScheduledImportJob]:
    """Lists scheduled import jobs for the authenticated tenant."""
    repo = get_bulk_import_repository()
    return repo.list_scheduled_jobs(tenant_context=tenant_context)


@router.post("/scheduled/{job_id}/run", response_model=ImportRunRecord)
async def run_scheduled_job_now(
    job_id: str,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> ImportRunRecord:
    """Manually triggers an unattended scheduled feed execution."""
    scheduler = get_scheduled_import_scheduler()
    try:
        return scheduler.run_scheduled_job(job_id, tenant_context=tenant_context)
    except ScheduledImportJobNotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message) from e
    except BulkImportException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message) from e
