"""Master Data Management API Routes.

Exposes endpoints for the Master Data Console:
- Registry manifest introspection.
- Point-in-time record resolution.
- Versioned mutations and approval lifecycle.
- Reference-integrity guarded deactivation/deletion.
- Lineage, where-used, import/export, and health reports.
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

from domain.models.exceptions import (
    CannotDeleteSystemMasterException,
    MasterDataApprovalException,
    MasterDataException,
    MasterNotRegisteredException,
    ReferenceIntegrityBlockedException,
)
from masterdata import (
    DryRunValidationResult,
    MasterDataHealthReport,
    MasterDataLineage,
    MasterDataRecord,
    MasterDataService,
    MasterRegistryEntry,
    WhereUsedReport,
    get_master_data_service,
)

router = APIRouter(prefix="/api/v1/masterdata", tags=["masterdata"])


def get_master_service() -> MasterDataService:
    return get_master_data_service()


class CreateRecordRequest(BaseModel):
    code: str
    display_name: str
    description: str | None = None
    sort_order: int = 0
    parent_code: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class UpdateRecordRequest(BaseModel):
    display_name: str
    description: str | None = None
    sort_order: int | None = None
    parent_code: str | None = None
    attributes: dict[str, Any] | None = None
    change_reason: str = "Console update"


class ImportPayload(BaseModel):
    format: str = "json"
    content: str


class StandaloneDryRunRequest(BaseModel):
    master_type: str
    records: list[dict[str, Any]] | None = None
    content: str | None = None
    format: str = "json"


@router.post("/dry-run", response_model=DryRunValidationResult)
async def dry_run_standalone(payload: StandaloneDryRunRequest) -> DryRunValidationResult:
    """Executes dry-run validation for master records."""
    try:
        if payload.records is not None:
            return get_master_service().dry_run_import(payload.master_type, payload.records)
        return get_master_service().validate_import(
            payload.master_type, payload.content or "", payload.format
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("/registry", response_model=list[MasterRegistryEntry])
async def list_registry_manifest() -> list[MasterRegistryEntry]:
    """Lists all registered master types declared in the platform manifest."""
    return get_master_service().get_registry()


@router.get("/health", response_model=MasterDataHealthReport)
async def get_master_data_health() -> MasterDataHealthReport:
    """Returns platform-wide master data health and hygiene inspection."""
    return get_master_service().get_health_report()


@router.get("/records/{master_type}", response_model=list[MasterDataRecord])
@router.get("/{master_type}", response_model=list[MasterDataRecord])
async def list_master_records(
    master_type: str,
    as_of: datetime | None = Query(None, description="Point-in-time timestamp"),
    include_inactive: bool = Query(False, description="Include deactivated versions"),
    x_tenant_id: str | None = Header(None, alias="X-Tenant-ID"),
) -> list[MasterDataRecord]:
    """Lists effective master records for a registered master type."""
    try:
        return get_master_service().list_records(
            master_type=master_type,
            as_of=as_of,
            tenant_id=x_tenant_id,
            include_inactive=include_inactive,
        )
    except MasterNotRegisteredException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message) from e


@router.get("/records/{master_type}/{code}", response_model=MasterDataRecord)
@router.get("/{master_type}/{code}", response_model=MasterDataRecord)
async def get_master_record(
    master_type: str,
    code: str,
    as_of: datetime | None = Query(None, description="Point-in-time timestamp"),
    x_tenant_id: str | None = Header(None, alias="X-Tenant-ID"),
) -> MasterDataRecord:
    """Retrieves a specific master record by code and effective date."""
    try:
        record = get_master_service().get_record(
            master_type=master_type,
            code=code,
            as_of=as_of,
            tenant_id=x_tenant_id,
            include_inactive=True,
        )
        if not record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Record '{code}' not found in master '{master_type}'.",
            )
        return record
    except MasterNotRegisteredException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message) from e


@router.post("/{master_type}", response_model=MasterDataRecord, status_code=status.HTTP_201_CREATED)
async def create_master_record(
    master_type: str,
    payload: CreateRecordRequest,
    x_tenant_id: str | None = Header(None, alias="X-Tenant-ID"),
) -> MasterDataRecord:
    """Creates a new master data record."""
    try:
        return get_master_service().create_record(
            master_type=master_type,
            code=payload.code,
            display_name=payload.display_name,
            description=payload.description,
            sort_order=payload.sort_order,
            parent_code=payload.parent_code,
            attributes=payload.attributes,
            tenant_id=x_tenant_id,
            created_by="api_user",
        )
    except MasterDataException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message) from e


@router.put("/{master_type}/{code}", response_model=MasterDataRecord)
async def update_master_record(
    master_type: str,
    code: str,
    payload: UpdateRecordRequest,
    x_tenant_id: str | None = Header(None, alias="X-Tenant-ID"),
) -> MasterDataRecord:
    """Updates a master record via effective-dated versioning."""
    try:
        return get_master_service().update_record(
            master_type=master_type,
            code=code,
            display_name=payload.display_name,
            description=payload.description,
            sort_order=payload.sort_order,
            parent_code=payload.parent_code,
            attributes=payload.attributes,
            changed_by="api_user",
            change_reason=payload.change_reason,
            tenant_id=x_tenant_id,
        )
    except MasterDataException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message) from e


@router.post("/{master_type}/{code}/review", response_model=MasterDataRecord)
async def submit_record_for_review(master_type: str, code: str) -> MasterDataRecord:
    """Submits a draft record for review."""
    try:
        return get_master_service().submit_for_review(master_type, code, user_id="api_user")
    except MasterDataApprovalException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message) from e


@router.post("/{master_type}/{code}/approve", response_model=MasterDataRecord)
async def approve_record(master_type: str, code: str) -> MasterDataRecord:
    """Approves a review record."""
    try:
        return get_master_service().approve(master_type, code, approver_id="admin_approver")
    except MasterDataApprovalException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message) from e


@router.post("/{master_type}/{code}/publish", response_model=MasterDataRecord)
async def publish_record(master_type: str, code: str) -> MasterDataRecord:
    """Publishes an approved record, activating it and closing previous versions."""
    try:
        return get_master_service().publish(master_type, code, publisher_id="admin_approver")
    except MasterDataApprovalException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message) from e


@router.post("/{master_type}/{code}/deactivate", response_model=MasterDataRecord)
async def deactivate_master_record(master_type: str, code: str) -> MasterDataRecord:
    """Deactivates a master record, blocked if referenced by live records."""
    try:
        return get_master_service().deactivate_record(master_type, code, requested_by="api_user")
    except ReferenceIntegrityBlockedException as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=e.message) from e
    except MasterDataException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message) from e


@router.delete("/{master_type}/{code}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_master_record(master_type: str, code: str) -> Response:
    """Deletes a master record, blocked if system record or referenced."""
    try:
        get_master_service().delete_record(master_type, code, requested_by="api_user")
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except CannotDeleteSystemMasterException as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=e.message) from e
    except ReferenceIntegrityBlockedException as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=e.message) from e
    except MasterDataException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message) from e


@router.get("/{master_type}/{code}/lineage", response_model=MasterDataLineage)
async def get_record_lineage(master_type: str, code: str) -> MasterDataLineage:
    """Retrieves full version lineage and audit change log."""
    return get_master_service().get_lineage(master_type, code)


@router.get("/where-used/{master_type}/{code}", response_model=WhereUsedReport)
@router.get("/{master_type}/{code}/where-used", response_model=WhereUsedReport)
async def get_record_where_used(master_type: str, code: str) -> WhereUsedReport:
    """Retrieves where-used reference analysis for a master value."""
    return get_master_service().get_where_used(master_type, code)


@router.post("/{master_type}/import/validate", response_model=DryRunValidationResult)
async def validate_master_import(
    master_type: str, payload: ImportPayload
) -> DryRunValidationResult:
    """Dry-run validation reporting what would change before executing import."""
    try:
        return get_master_service().validate_import(
            master_type=master_type,
            content=payload.content,
            import_format=payload.format,
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/{master_type}/import")
async def execute_master_import(master_type: str, payload: ImportPayload) -> dict[str, int]:
    """Executes validated import of master records."""
    try:
        added, updated = get_master_service().import_data(
            master_type=master_type,
            content=payload.content,
            import_format=payload.format,
            imported_by="api_user",
        )
        return {"added": added, "updated": updated}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("/{master_type}/export")
async def export_master_records(
    master_type: str,
    format: str = Query("json", description="Export format: json or csv"),
) -> Response:
    """Exports master data records as JSON or CSV."""
    try:
        content = get_master_service().export_data(master_type, export_format=format)
        media_type = "text/csv" if format.lower() == "csv" else "application/json"
        return Response(content=content, media_type=media_type)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
