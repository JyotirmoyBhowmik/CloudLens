"""CloudLens Demonstration Tenant Loader & Anomaly Discovery Service (Prompt 09 Item 63).

Enforces:
- Prompt 09 Items 60, 61, 63 & Acceptance Criteria.
- Populates the demonstration tenant (T-DEMO) with multi-level hierarchies across AWS, Azure, GCP, and OCI.
- Seeds all reference catalogues (service categories, canonical services, standard units, core metrics,
  29 pricing dimensions, default budget templates, default threshold templates, default policies)
  idempotently without duplication.
- Injects and surfaces the four deliberate anomalies:
  1. COST_SPIKE: Sudden 15x cost spike on an active resource.
  2. RESTATEMENT: Prior billing period retroactive adjustment credit (-$450.00).
  3. STALE_CONNECTOR: Ingestion connector job failed >72 hours ago (96h stale).
  4. UNOWNED_CLUSTER: Cluster of 8 unowned resources with zero tags, unmapped scope, producing UNRESOLVED exceptions.
- Completes in under two minutes (typically < 2 seconds).
"""

import logging
import time
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from domain.attribution.models import OwnershipResolutionRule
from domain.attribution.ownership import OwnershipResolutionService
from domain.bootstrap.pre_identity import (
    PreIdentityBootstrapService,
    get_pre_identity_bootstrap_service,
)
from domain.config.tenant_settings import (
    RetentionProfile,
    TenantSettingsStore,
    tenant_settings_store,
)
from domain.models.enums import ChargeCategory, SyncJobStatus
from domain.models.facts import CostFact
from domain.models.governance import SyncJob
from domain.synthetic.estate_generator import (
    CompleteEstateResult,
    SyntheticAnomaly,
    SyntheticAnomalyType,
    SyntheticEstateGenerator,
)

logger = logging.getLogger(__name__)

DEMO_TENANT_ID = "T-DEMO"
DEMO_TENANT_NAME = "CloudLens Global Demonstration Corp"


class DemoTenantSeedResult(BaseModel):
    """Structured report returned upon seeding the demonstration tenant."""

    tenant_id: str = Field(default=DEMO_TENANT_ID, description="Target demonstration tenant ID")
    tenant_name: str = Field(
        default=DEMO_TENANT_NAME, description="Target demonstration tenant name"
    )
    scopes_count: int = Field(default=0, description="Total hierarchy scopes populated")
    resources_count: int = Field(default=0, description="Total cloud resources populated")
    cost_facts_count: int = Field(default=0, description="Total cost facts recorded")
    usage_facts_count: int = Field(default=0, description="Total usage telemetry facts recorded")
    runtime_states_count: int = Field(
        default=0, description="Total runtime state records populated"
    )
    dependencies_count: int = Field(
        default=0, description="Total cross-resource dependencies populated"
    )
    sync_jobs_count: int = Field(
        default=0, description="Total connector synchronization jobs populated"
    )
    anomalies: list[SyntheticAnomaly] = Field(
        default_factory=list, description="Deliberate anomalies injected and discoverable"
    )
    catalogues_seeded: bool = Field(
        default=True, description="Indicates if master reference catalogues were seeded"
    )
    elapsed_seconds: float = Field(default=0.0, description="Total wall-clock duration of seeding")
    seeded_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Timestamp when seeding took place"
    )
    is_reseeded: bool = Field(
        default=False, description="True if forced reseed replaced an existing estate"
    )
    status: str = Field(default="COMPLETED", description="Status of seeding operation")


class DemoTenantLoaderService:
    """Enterprise Demonstration Tenant Loader & Discovery Engine."""

    def __init__(
        self,
        bootstrap_service: PreIdentityBootstrapService | None = None,
        tenant_store: TenantSettingsStore | None = None,
        ownership_service: OwnershipResolutionService | None = None,
    ) -> None:
        self._bootstrap = bootstrap_service or get_pre_identity_bootstrap_service()
        self._tenant_store = tenant_store or tenant_settings_store
        self._ownership_service = ownership_service or OwnershipResolutionService()
        self._estates: dict[str, CompleteEstateResult] = {}
        self._seed_reports: dict[str, DemoTenantSeedResult] = {}

    def is_seeded(self, tenant_id: str = DEMO_TENANT_ID) -> bool:
        """Checks if the demonstration estate is populated in memory/storage."""
        return tenant_id in self._estates

    def get_estate(self, tenant_id: str = DEMO_TENANT_ID) -> CompleteEstateResult | None:
        """Retrieves the populated estate for the given tenant ID."""
        return self._estates.get(tenant_id)

    def get_seed_report(self, tenant_id: str = DEMO_TENANT_ID) -> DemoTenantSeedResult | None:
        """Retrieves the seed execution summary report."""
        return self._seed_reports.get(tenant_id)

    def seed_demo_tenant(
        self,
        tenant_id: str = DEMO_TENANT_ID,
        sample_size: int = 50,
        force_reseed: bool = False,
        dry_run: bool = False,
    ) -> DemoTenantSeedResult:
        """Populates the complete demonstration tenant and reference catalogues idempotently.

        Args:
            tenant_id: ID of the demonstration tenant (default: 'T-DEMO').
            sample_size: Base number of cloud resources per provider (default: 50).
            force_reseed: If True, regenerates the estate even if already present.
            dry_run: If True, performs generation without persisting to storage.

        Returns:
            DemoTenantSeedResult with detailed counts and discovered anomalies.
        """
        start_time = time.perf_counter()
        logger.info(
            "Initiating demonstration tenant seeding for '%s' (sample_size=%d, force_reseed=%s, dry_run=%s)",
            tenant_id,
            sample_size,
            force_reseed,
            dry_run,
        )

        # Idempotence check: return existing report if already populated and not force_reseed
        if not force_reseed and not dry_run and self.is_seeded(tenant_id):
            logger.info(
                "Demo tenant '%s' is already populated. Returning existing state.", tenant_id
            )
            existing_report = self._seed_reports.get(tenant_id)
            if existing_report:
                return existing_report.model_copy(update={"is_reseeded": False})

        # Step 1: Idempotently seed master data reference catalogues
        # (FOCUS service categories, canonical services, standard units, core metrics,
        # 29 pricing dimensions, default budget templates, default threshold templates,
        # default policies with only connector health enabled)
        bootstrap_report = self._bootstrap.bootstrap(dry_run=dry_run)
        catalogues_ok = bootstrap_report.status in {"INITIALIZED", "ALREADY_INITIALISED"}

        # Step 2: Ensure demonstration tenant settings are registered
        if not dry_run:
            self._tenant_store.update(
                tenant_id,
                {
                    "tenant_id": tenant_id,
                    "reporting_currency": "USD",
                    "fiscal_calendar_start_month": 1,
                    "default_time_zone": "UTC",
                    "cost_basis_default": "billed",
                    "retention_profile": RetentionProfile(
                        raw_metrics_retention_days=90,
                        daily_aggregates_retention_days=730,
                        audit_log_retention_days=2555,  # 7 years
                    ).model_dump(),
                },
            )

        # Step 3: Generate the full synthetic multi-cloud estate
        generator = SyntheticEstateGenerator(seed=42)
        estate = generator.generate_complete_estate(tenant_id=tenant_id, sample_size=sample_size)

        elapsed = time.perf_counter() - start_time

        result = DemoTenantSeedResult(
            tenant_id=tenant_id,
            tenant_name=DEMO_TENANT_NAME,
            scopes_count=len(estate.scopes),
            resources_count=len(estate.resources),
            cost_facts_count=len(estate.cost_facts),
            usage_facts_count=len(estate.usage_facts),
            runtime_states_count=len(estate.runtime_states),
            dependencies_count=len(estate.dependencies),
            sync_jobs_count=len(estate.sync_jobs),
            anomalies=estate.anomalies,
            catalogues_seeded=catalogues_ok,
            elapsed_seconds=round(elapsed, 4),
            seeded_at=datetime.now(UTC),
            is_reseeded=force_reseed,
            status="DRY_RUN" if dry_run else "COMPLETED",
        )

        if not dry_run:
            self._estates[tenant_id] = estate
            self._seed_reports[tenant_id] = result
            logger.info(
                "Demonstration tenant '%s' successfully seeded in %.3f seconds (%d resources, %d anomalies)",
                tenant_id,
                elapsed,
                len(estate.resources),
                len(estate.anomalies),
            )

        return result

    # ----------------------------------------------------------------------
    # Anomaly Discovery Methods (Prompt 09 Item 63 & Acceptance)
    # ----------------------------------------------------------------------

    def find_anomalies(
        self,
        tenant_id: str = DEMO_TENANT_ID,
        anomaly_type: SyntheticAnomalyType | None = None,
    ) -> list[SyntheticAnomaly]:
        """Discovers all injected anomalies matching the optional type filter."""
        estate = self.get_estate(tenant_id)
        if not estate:
            # If not yet seeded, automatically seed to ensure immediate usability
            self.seed_demo_tenant(tenant_id=tenant_id)
            estate = self.get_estate(tenant_id)

        if not estate:
            return []

        if anomaly_type is None:
            return estate.anomalies

        return [a for a in estate.anomalies if a.anomaly_type == anomaly_type]

    def find_cost_spikes(self, tenant_id: str = DEMO_TENANT_ID) -> list[dict[str, Any]]:
        """Discovers the deliberate cost spike anomaly and returns resource & cost facts."""
        estate = self.get_estate(tenant_id)
        if not estate:
            self.seed_demo_tenant(tenant_id=tenant_id)
            estate = self.get_estate(tenant_id)

        if not estate:
            return []

        spike_anomalies = [
            a for a in estate.anomalies if a.anomaly_type == SyntheticAnomalyType.COST_SPIKE
        ]
        results: list[dict[str, Any]] = []

        for sa in spike_anomalies:
            target_res = next((r for r in estate.resources if r.id == sa.target_id), None)
            spiked_facts = [
                cf
                for cf in estate.cost_facts
                if cf.resource_id == sa.target_id and cf.billed_cost.value > Decimal("500.00")
            ]
            results.append(
                {
                    "anomaly": sa,
                    "resource": target_res,
                    "cost_facts": spiked_facts,
                    "spike_amount": sa.detected_value,
                    "baseline_amount": sa.expected_baseline,
                }
            )

        return results

    def find_restatements(self, tenant_id: str = DEMO_TENANT_ID) -> list[CostFact]:
        """Discovers restatements or retroactive adjustments (charge_category=ADJUSTMENT or negative cost)."""
        estate = self.get_estate(tenant_id)
        if not estate:
            self.seed_demo_tenant(tenant_id=tenant_id)
            estate = self.get_estate(tenant_id)

        if not estate:
            return []

        return [
            cf
            for cf in estate.cost_facts
            if cf.charge_category == ChargeCategory.ADJUSTMENT
            or (cf.billed_cost.is_present and cf.billed_cost.value < Decimal("0.00"))
        ]

    def find_stale_connectors(
        self,
        tenant_id: str = DEMO_TENANT_ID,
        max_freshness_hours: int = 72,
    ) -> list[SyncJob]:
        """Discovers sync jobs that have failed or exceeded the SLA freshness threshold."""
        estate = self.get_estate(tenant_id)
        if not estate:
            self.seed_demo_tenant(tenant_id=tenant_id)
            estate = self.get_estate(tenant_id)

        if not estate:
            return []

        now = datetime.now(UTC)
        stale_jobs: list[SyncJob] = []
        for job in estate.sync_jobs:
            is_failed = job.status == SyncJobStatus.FAILED
            age_hours = (now - job.started_at).total_seconds() / 3600.0
            is_exceeded = age_hours > max_freshness_hours
            if is_failed or is_exceeded:
                stale_jobs.append(job)

        return stale_jobs

    def find_unowned_clusters(self, tenant_id: str = DEMO_TENANT_ID) -> list[dict[str, Any]]:
        """Evaluates resources with OwnershipResolutionService to identify unowned clusters.

        Returns clusters of resources where ownership resolves to UNRESOLVED with zero tags.
        """
        estate = self.get_estate(tenant_id)
        if not estate:
            self.seed_demo_tenant(tenant_id=tenant_id)
            estate = self.get_estate(tenant_id)

        if not estate:
            return []

        unresolved_by_scope: dict[str, list[str]] = {}
        scope_map = {s.id: s for s in estate.scopes}

        for res in estate.resources:
            scope = scope_map.get(res.scope_id)
            resolution = self._ownership_service.resolve_ownership(
                resource=res,
                parent_scope=scope,
            )
            if resolution.winning_rule == OwnershipResolutionRule.UNRESOLVED and len(res.tags) == 0:
                unresolved_by_scope.setdefault(res.scope_id, []).append(res.id)

        clusters: list[dict[str, Any]] = []
        for scope_id, res_ids in unresolved_by_scope.items():
            if len(res_ids) >= 5:  # Cluster threshold
                scope_obj = scope_map.get(scope_id)
                clusters.append(
                    {
                        "scope_id": scope_id,
                        "scope_name": scope_obj.name if scope_obj else "Unknown",
                        "unowned_resource_count": len(res_ids),
                        "resource_ids": res_ids,
                        "resolution_rule": OwnershipResolutionRule.UNRESOLVED.value,
                    }
                )

        return clusters


# Singleton instance
_demo_tenant_service = DemoTenantLoaderService()


def get_demo_tenant_service() -> DemoTenantLoaderService:
    """Retrieves the global DemoTenantLoaderService singleton."""
    return _demo_tenant_service
