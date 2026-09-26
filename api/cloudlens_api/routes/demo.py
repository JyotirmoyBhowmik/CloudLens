"""CloudLens Demonstration Tenant REST API Endpoints (Prompt 09 Item 63).

Enforces:
- POST /api/v1/system/demo/seed: Seeds the demonstration tenant and returns the verification summary.
- GET /api/v1/system/demo/status: Retrieves current demonstration tenant state.
- GET /api/v1/system/demo/anomalies: Discovers injected deliberate anomalies with optional type filter.
- GET /api/v1/system/demo/anomalies/cost-spikes: Detailed cost spike anomaly inspection.
- GET /api/v1/system/demo/anomalies/restatements: Prior billing period retroactive adjustments.
- GET /api/v1/system/demo/anomalies/stale-connectors: Connector sync freshness SLA violations.
- GET /api/v1/system/demo/anomalies/unowned-clusters: Unowned resource cluster governance exceptions.
"""

from typing import Any

from fastapi import APIRouter, Header, Query
from pydantic import BaseModel, Field

from domain.models.facts import CostFact
from domain.models.governance import SyncJob
from domain.synthetic.demo_tenant import (
    DEMO_TENANT_ID,
    DemoTenantSeedResult,
    get_demo_tenant_service,
)
from domain.synthetic.estate_generator import SyntheticAnomaly, SyntheticAnomalyType

router = APIRouter(prefix="/api/v1/system/demo", tags=["Demonstration Estate"])


class DemoStatusResponse(BaseModel):
    """Status summary of demonstration tenant."""

    is_seeded: bool = Field(description="True if demonstration tenant is loaded in memory/storage")
    tenant_id: str = Field(default=DEMO_TENANT_ID, description="Demonstration tenant ID")
    scopes_count: int = Field(default=0, description="Total hierarchy scopes populated")
    resources_count: int = Field(default=0, description="Total cloud resources populated")
    cost_facts_count: int = Field(default=0, description="Total cost facts recorded")
    anomalies_count: int = Field(default=0, description="Total discoverable anomalies count")


@router.post("/seed", response_model=DemoTenantSeedResult)
def seed_demo_tenant_endpoint(
    sample_size: int = Query(
        default=50,
        ge=10,
        le=5000,
        description="Base count of cloud resources generated per provider",
    ),
    force_reseed: bool = Query(
        default=False,
        description="Force regeneration and replacement of any existing demonstration estate",
    ),
    dry_run: bool = Query(
        default=False,
        description="Generate synthetic estate in-memory without persisting to state store",
    ),
    _x_correlation_id: str | None = Header(default=None, alias="X-Correlation-ID"),
) -> DemoTenantSeedResult:
    """Populates the complete demonstration tenant with multi-level hierarchies and anomalies.

    Executes in under two minutes, bringing a clean deployment to a fully demonstratable state.
    """
    service = get_demo_tenant_service()
    return service.seed_demo_tenant(
        tenant_id=DEMO_TENANT_ID,
        sample_size=sample_size,
        force_reseed=force_reseed,
        dry_run=dry_run,
    )


@router.get("/status", response_model=DemoStatusResponse)
def get_demo_status_endpoint() -> DemoStatusResponse:
    """Retrieves current population and anomaly readiness status of the demonstration tenant."""
    service = get_demo_tenant_service()
    is_seeded = service.is_seeded(DEMO_TENANT_ID)
    if not is_seeded:
        return DemoStatusResponse(
            is_seeded=False,
            tenant_id=DEMO_TENANT_ID,
            scopes_count=0,
            resources_count=0,
            cost_facts_count=0,
            anomalies_count=0,
        )

    estate = service.get_estate(DEMO_TENANT_ID)
    if not estate:
        return DemoStatusResponse(
            is_seeded=False,
            tenant_id=DEMO_TENANT_ID,
            scopes_count=0,
            resources_count=0,
            cost_facts_count=0,
            anomalies_count=0,
        )

    return DemoStatusResponse(
        is_seeded=True,
        tenant_id=DEMO_TENANT_ID,
        scopes_count=len(estate.scopes),
        resources_count=len(estate.resources),
        cost_facts_count=len(estate.cost_facts),
        anomalies_count=len(estate.anomalies),
    )


@router.get("/anomalies", response_model=list[SyntheticAnomaly])
def get_demo_anomalies_endpoint(
    anomaly_type: SyntheticAnomalyType | None = Query(
        default=None,
        description="Optional filter by anomaly type (COST_SPIKE, RESTATEMENT, STALE_CONNECTOR, UNOWNED_CLUSTER)",
    ),
) -> list[SyntheticAnomaly]:
    """Discovers deliberate anomalies injected into the demonstration tenant."""
    service = get_demo_tenant_service()
    return service.find_anomalies(tenant_id=DEMO_TENANT_ID, anomaly_type=anomaly_type)


@router.get("/anomalies/cost-spikes")
def get_cost_spikes_endpoint() -> list[dict[str, Any]]:
    """Inspects sudden day-over-day spend spike anomalies."""
    service = get_demo_tenant_service()
    return service.find_cost_spikes(tenant_id=DEMO_TENANT_ID)


@router.get("/anomalies/restatements", response_model=list[CostFact])
def get_restatements_endpoint() -> list[CostFact]:
    """Inspects retroactive adjustment credits from prior billing periods."""
    service = get_demo_tenant_service()
    return service.find_restatements(tenant_id=DEMO_TENANT_ID)


@router.get("/anomalies/stale-connectors", response_model=list[SyncJob])
def get_stale_connectors_endpoint(
    max_freshness_hours: int = Query(default=72, ge=1, le=720),
) -> list[SyncJob]:
    """Inspects connector ingestion jobs exceeding SLA freshness limits."""
    service = get_demo_tenant_service()
    return service.find_stale_connectors(
        tenant_id=DEMO_TENANT_ID,
        max_freshness_hours=max_freshness_hours,
    )


@router.get("/anomalies/unowned-clusters")
def get_unowned_clusters_endpoint() -> list[dict[str, Any]]:
    """Inspects unowned resource clusters evaluated by the OwnershipResolutionService."""
    service = get_demo_tenant_service()
    return service.find_unowned_clusters(tenant_id=DEMO_TENANT_ID)
