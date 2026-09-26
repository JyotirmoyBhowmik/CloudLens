"""Master Data Management API Routes.

Exposes endpoints for the Master Data Console:
- Registry manifest introspection.
- Point-in-time record resolution.
- Versioned mutations and approval lifecycle.
- Reference-integrity guarded deactivation/deletion.
- Lineage, where-used, import/export, and health reports.
"""

import json
from datetime import date, datetime
from decimal import Decimal
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
    BudgetAllocation,
    BudgetAllocationService,
    ContractRateEngine,
    CurrencyConversionResult,
    CurrencyConverterEngine,
    DryRunValidationResult,
    EffectiveRateResult,
    FinancialCalendarEngine,
    FiscalPeriod,
    GeographyComplianceEngine,
    GeographyComplianceResult,
    MasterDataHealthReport,
    MasterDataLineage,
    MasterDataRecord,
    MasterDataService,
    MasterRegistryEntry,
    RuntimeScheduleAdherenceEngine,
    ScheduleAdherenceResult,
    StringCatalogueService,
    TagComplianceReport,
    TagPolicyEngine,
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


class ValidateBudgetRequest(BaseModel):
    tenant_id: str
    name: str
    amount: Decimal
    currency: str = "USD"
    fiscal_year: int
    cost_centre_code: str
    business_unit_code: str


class ScheduleAdherenceEvaluateRequest(BaseModel):
    resource_id: str
    environment_code: str
    current_status: str
    check_date: date
    location_code: str = "LOC_US_EAST_VA"


class CurrencyConvertRequest(BaseModel):
    amount: Decimal
    from_currency: str
    presentation_context: str = "actual_cost"
    tenant_id: str | None = None
    as_of_date: str | None = None


class TagPolicyEvaluateRequest(BaseModel):
    tags: dict[str, str]
    policy_code: str = "TAG_POL_ENTERPRISE_MANDATORY"


# ------------------------------------------------------------------------------
# Business Master Data Domain Endpoints (Prompt 46)
# ------------------------------------------------------------------------------


@router.post("/budgets/validate", response_model=BudgetAllocation)
async def validate_and_create_budget(payload: ValidateBudgetRequest) -> BudgetAllocation:
    """Validates budget creation against registered Cost Centre and Business Unit masters."""
    try:
        service = BudgetAllocationService(get_master_service())
        return service.create_budget_allocation(
            tenant_id=payload.tenant_id,
            name=payload.name,
            amount=payload.amount,
            currency=payload.currency,
            fiscal_year=payload.fiscal_year,
            cost_centre_code=payload.cost_centre_code,
            business_unit_code=payload.business_unit_code,
            created_by="api_user",
        )
    except MasterDataException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message) from e


@router.get("/calendar/fiscal-periods", response_model=list[FiscalPeriod])
async def get_fiscal_periods(
    calendar_code: str = Query("FC_STANDARD_JAN", description="Fiscal calendar code"),
    fiscal_year: int = Query(2026, description="Fiscal year"),
) -> list[FiscalPeriod]:
    """Calculates all 12 period boundaries dynamically from master data."""
    try:
        engine = FinancialCalendarEngine(get_master_service())
        return engine.get_fiscal_periods(calendar_code, fiscal_year)
    except MasterDataException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message) from e


@router.post("/schedule-adherence/evaluate", response_model=ScheduleAdherenceResult)
async def evaluate_schedule_adherence(
    payload: ScheduleAdherenceEvaluateRequest,
) -> ScheduleAdherenceResult:
    """Evaluates schedule adherence, suppressing exceptions on holidays."""
    try:
        engine = RuntimeScheduleAdherenceEngine(get_master_service())
        return engine.evaluate_schedule_adherence(
            resource_id=payload.resource_id,
            environment_code=payload.environment_code,
            current_status=payload.current_status,
            check_date=payload.check_date,
            location_code=payload.location_code,
        )
    except MasterDataException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message) from e


@router.post("/currency/convert", response_model=CurrencyConversionResult)
async def convert_currency_cost(payload: CurrencyConvertRequest) -> CurrencyConversionResult:
    """Converts a cost to reporting currency using the tenant FX presentation policy."""
    try:
        engine = CurrencyConverterEngine(get_master_service())
        return engine.convert_cost(
            amount=payload.amount,
            from_currency=payload.from_currency,
            presentation_context=payload.presentation_context,
            tenant_id=payload.tenant_id,
            as_of_date=payload.as_of_date,
        )
    except MasterDataException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message) from e


@router.get("/rate-cards/effective-rate", response_model=EffectiveRateResult)
async def get_effective_rate_card(
    provider_code: str = Query(..., description="Cloud provider code"),
    service_code: str = Query(..., description="Service code"),
    sku_id: str = Query(..., description="SKU identifier"),
) -> EffectiveRateResult:
    """Resolves effective rate with contracted precedence and visible manual source label."""
    try:
        engine = ContractRateEngine(get_master_service())
        return engine.resolve_effective_rate(provider_code, service_code, sku_id)
    except MasterDataException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message) from e


@router.post("/tag-policy/evaluate", response_model=TagComplianceReport)
async def evaluate_tag_policy(payload: TagPolicyEvaluateRequest) -> TagComplianceReport:
    """Evaluates resource tags against corporate tag policy."""
    try:
        engine = TagPolicyEngine(get_master_service())
        return engine.evaluate_tags(payload.tags, payload.policy_code)
    except MasterDataException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message) from e


@router.get("/geography/compliance", response_model=GeographyComplianceResult)
async def evaluate_geography_compliance(
    provider_code: str = Query(..., description="Cloud provider code"),
    region_name: str = Query(..., description="Region name"),
) -> GeographyComplianceResult:
    """Verifies region deployment compliance and sovereign data residency."""
    engine = GeographyComplianceEngine(get_master_service())
    return engine.evaluate_region(provider_code, region_name)


class ResolveStringRequest(BaseModel):
    key: str
    locale: str = "en_US"
    params: dict[str, Any] = Field(default_factory=dict)
    tenant_id: str | None = None


@router.post("/strings/resolve")
async def resolve_externalised_string(payload: ResolveStringRequest) -> dict[str, Any]:
    """Resolves an externalised display string or template from STRING_CATALOGUE master."""
    try:
        service = StringCatalogueService(get_master_service())
        resolved = service.resolve_string(
            key=payload.key,
            locale=payload.locale,
            params=payload.params,
            tenant_id=payload.tenant_id,
        )
        return {
            "key": payload.key,
            "locale": payload.locale,
            "resolved_text": resolved,
        }
    except MasterDataException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message) from e


@router.get("/strings/resolve")
async def resolve_externalised_string_get(
    key: str = Query(..., description="String catalogue key code"),
    locale: str = Query("en_US", description="Locale code"),
    tenant_id: str | None = Query(None, description="Optional tenant scope"),
) -> dict[str, Any]:
    """Resolves a static label from STRING_CATALOGUE master."""
    try:
        service = StringCatalogueService(get_master_service())
        resolved = service.resolve_string(key=key, locale=locale, tenant_id=tenant_id)
        return {
            "key": key,
            "locale": locale,
            "resolved_text": resolved,
        }
    except MasterDataException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message) from e


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
    x_tenant_id: str = Header(default="global", alias="X-Tenant-ID"),
) -> Response:
    """Exports master data records as JSON or CSV with mandatory Demo Mode watermark if active."""
    try:
        content = get_master_service().export_data(master_type, export_format=format)
        from domain.config.tenant_settings import tenant_settings_store
        from domain.demo.models import EXPORT_WATERMARK

        settings = tenant_settings_store.get(x_tenant_id)
        resp_headers: dict[str, str] = {}

        if settings.is_demo_mode:
            resp_headers["X-CloudLens-Demo-Mode"] = "true"
            resp_headers["X-CloudLens-Watermark"] = EXPORT_WATERMARK
            if format.lower() == "csv":
                content = f"# WATERMARK: {EXPORT_WATERMARK}\n" + content
            elif format.lower() == "json":
                try:
                    data = json.loads(content)
                    if isinstance(data, list):
                        content = json.dumps(
                            [{"_watermark": EXPORT_WATERMARK, "_demo_mode": True}] + data,
                            indent=2,
                        )
                except Exception:
                    pass

        media_type = "text/csv" if format.lower() == "csv" else "application/json"
        return Response(content=content, media_type=media_type, headers=resp_headers)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
