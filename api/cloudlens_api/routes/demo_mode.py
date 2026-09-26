"""CloudLens Demo Mode and Scenarios REST API Endpoints (Prompt 47 Items 30-32).

Endpoints:
- POST /api/v1/system/demo/mode/enable: Enables Demo Mode with safety interlock checks.
- POST /api/v1/system/demo/mode/disable: Disables Demo Mode and purges simulated data with audit log.
- GET  /api/v1/system/demo/mode/status: Retrieves Demo Mode status, banner text, and safety posture.
- POST /api/v1/system/demo/reset: Executes one-command purge, reseed, and reload.
- GET  /api/v1/system/demo/scenarios: Lists all seven named demonstration scenarios.
- POST /api/v1/system/demo/scenarios/load: Loads a named scenario in a single action.
"""

from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

from domain.demo import (
    EXPORT_WATERMARK,
    DemoModeStatus,
    DemoResetResult,
    DemoScenario,
    DemoScenarioInfo,
    get_demo_mode_service,
)
from domain.models.exceptions import DemoModeSafetyException

router = APIRouter(prefix="/api/v1/system/demo", tags=["Demo Mode & Scenarios"])


class LoadScenarioRequest(BaseModel):
    """Payload to load a named demo scenario."""

    scenario: DemoScenario = Field(..., description="Target demonstration scenario")
    tenant_id: str = Field(default="T-DEMO", description="Target tenant ID")


class EnableDemoModeRequest(BaseModel):
    """Payload to enable Demo Mode."""

    tenant_id: str = Field(default="T-DEMO", description="Target tenant ID")
    scenario: DemoScenario = Field(
        default=DemoScenario.MONTH_END_REVIEW, description="Initial scenario"
    )


@router.get("/mode/status", response_model=DemoModeStatus)
def get_demo_mode_status_endpoint(
    tenant_id: str = Query(default="T-DEMO", description="Target tenant ID"),
) -> DemoModeStatus:
    """Returns Demo Mode status, persistent banner message, and safety interlocks."""
    service = get_demo_mode_service()
    return service.get_status(tenant_id)


@router.post("/mode/enable", response_model=DemoModeStatus)
def enable_demo_mode_endpoint(
    payload: EnableDemoModeRequest,
    x_actor_id: str = Header(default="admin@cloudlens.internal", alias="X-Actor-ID"),
) -> DemoModeStatus:
    """Enables Demo Mode on a tenant, enforcing Safety Interlock 1.

    Refuses activation if tenant has active live cloud connectors.
    """
    service = get_demo_mode_service()
    try:
        return service.enable_demo_mode(
            tenant_id=payload.tenant_id,
            scenario=payload.scenario,
            actor_id=x_actor_id,
        )
    except DemoModeSafetyException as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error_code": exc.error_code, "message": exc.message},
        ) from exc


@router.post("/mode/disable", response_model=DemoModeStatus)
def disable_demo_mode_endpoint(
    tenant_id: str = Query(default="T-DEMO", description="Target tenant ID"),
    confirm_purge: bool = Query(
        default=False,
        description="Explicit confirmation to purge simulated estate data (required by Safety Interlock 3)",
    ),
    x_actor_id: str = Header(default="admin@cloudlens.internal", alias="X-Actor-ID"),
) -> DemoModeStatus:
    """Disables Demo Mode and purges simulated data, enforcing Safety Interlock 3."""
    service = get_demo_mode_service()
    try:
        return service.disable_demo_mode(
            tenant_id=tenant_id,
            confirm_purge=confirm_purge,
            actor_id=x_actor_id,
        )
    except DemoModeSafetyException as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error_code": exc.error_code, "message": exc.message},
        ) from exc


@router.post("/reset", response_model=DemoResetResult)
def reset_demo_endpoint(
    tenant_id: str = Query(default="T-DEMO", description="Target tenant ID"),
    scenario: DemoScenario = Query(
        default=DemoScenario.MONTH_END_REVIEW,
        description="Target demonstration scenario to configure after reset",
    ),
    seed: int = Query(default=42, description="Deterministic pseudorandom seed"),
) -> DemoResetResult:
    """One-command demo reset: purges, reseeds, and reloads in a single action (Prompt 47 Item 31)."""
    service = get_demo_mode_service()
    return service.reset_demo(tenant_id=tenant_id, scenario=scenario, seed=seed)


@router.get("/scenarios", response_model=list[DemoScenarioInfo])
def list_demo_scenarios_endpoint() -> list[DemoScenarioInfo]:
    """Lists all seven named demonstration scenarios (Prompt 47 Item 32)."""
    service = get_demo_mode_service()
    return service.get_scenarios()


@router.post("/scenarios/load", response_model=DemoScenarioInfo)
def load_demo_scenario_endpoint(payload: LoadScenarioRequest) -> DemoScenarioInfo:
    """Loads a named demo scenario in a single action (Prompt 47 Item 32)."""
    service = get_demo_mode_service()
    try:
        return service.load_scenario(tenant_id=payload.tenant_id, scenario=payload.scenario)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.get("/export")
def export_demo_data_endpoint(
    tenant_id: str = Query(default="T-DEMO", description="Target tenant ID"),
    format: str = Query(default="json", description="Export format: json or csv"),
    entity: str = Query(
        default="costs", description="Entity to export: costs, resources, or summary"
    ),
) -> Response:
    """Exports simulated estate data with mandatory demonstration watermark (Prompt 47 Item 30)."""
    service = get_demo_mode_service()
    status_info = service.get_status(tenant_id)
    if not status_info.is_demo_mode:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tenant '{tenant_id}' is not in Demo Mode. Use standard operational export endpoints.",
        )

    estate = service.get_estate(tenant_id)
    if not estate:
        # If no estate initialized yet, trigger reset to generate one
        service.reset_demo(tenant_id=tenant_id)
        estate = service.get_estate(tenant_id)

    if not estate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No simulated estate data found for tenant.",
        )

    headers = {
        "X-CloudLens-Demo-Mode": "true",
        "X-CloudLens-Watermark": EXPORT_WATERMARK,
    }

    if entity == "resources":
        records: list[dict[str, Any]] = [
            {
                "resource_id": r.id,
                "name": r.name,
                "type": r.resource_type_id,
                "service": r.service_id,
                "provider": r.provider.value if hasattr(r.provider, "value") else str(r.provider),
                "scope_id": r.scope_id,
                "pricing_status": r.pricing_status.value,
                "tags": {t.key: t.value for t in r.tags},
            }
            for r in estate.resources
        ]
    elif entity == "summary":
        records = [
            {
                "manifest_seed": estate.manifest.seed,
                "manifest_hash": estate.manifest.sha256_hash,
                "total_resources": len(estate.resources),
                "total_cost_facts": len(estate.cost_facts),
                "injected_imperfections_count": len(estate.imperfections),
            }
        ]
    else:  # "costs" default
        records = [
            {
                "cost_fact_id": cf.id,
                "resource_id": cf.resource_id,
                "scope_id": cf.scope_id,
                "charge_period_start": cf.charge_period_start.isoformat(),
                "billed_cost": str(cf.billed_cost.value) if cf.billed_cost.is_present else None,
                "effective_cost": str(cf.effective_cost.value)
                if cf.effective_cost.is_present
                else None,
                "cost_source": cf.cost_source.value,
                "charge_category": cf.charge_category.value,
                "null_state": cf.billed_cost.null_state.value
                if cf.billed_cost.null_state
                else "PRESENT",
            }
            for cf in estate.cost_facts
        ]

    if format.lower() == "csv":
        import csv
        import io

        output = io.StringIO()
        if records:
            writer = csv.DictWriter(output, fieldnames=list(records[0].keys()))
            writer.writeheader()
            for rec in records:
                writer.writerow(rec)
        raw_csv = output.getvalue()
        content = f"# WATERMARK: {EXPORT_WATERMARK}\n" + raw_csv
        return Response(content=content, media_type="text/csv", headers=headers)
    else:
        import json

        watermarked_records = [{"_watermark": EXPORT_WATERMARK, "_demo_mode": True}] + records
        content = json.dumps(watermarked_records, indent=2)
        return Response(content=content, media_type="application/json", headers=headers)
