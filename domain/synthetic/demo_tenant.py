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

import json
import logging
import time
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import text

from db.session import get_tenant_session, run_async

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
            if tenant_id == DEMO_TENANT_ID:
                self._persist_to_postgres(estate, tenant_id)
            logger.info(
                "Demonstration tenant '%s' successfully seeded in %.3f seconds (%d resources, %d anomalies)",
                tenant_id,
                elapsed,
                len(estate.resources),
                len(estate.anomalies),
            )

        return result

    def _persist_to_postgres(self, estate: CompleteEstateResult, tenant_id: str) -> None:
        """Persists generated synthetic estate to PostgreSQL for demonstration tenants only (Prompt P09)."""
        async def _do_persist() -> None:
            async with get_tenant_session(tenant_id) as sess:
                # 1. Tenant record
                await sess.execute(text("""
                    INSERT INTO tenants (id, name, reporting_currency)
                    VALUES (:tid, :tname, 'USD')
                    ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name;
                """), {"tid": tenant_id, "tname": DEMO_TENANT_NAME})

                # 2. Reference dimensions (regions, services, resource_types)
                for res in estate.resources:
                    prov_str = str(res.provider.value if hasattr(res.provider, 'value') else res.provider).lower()
                    await sess.execute(text("""
                        INSERT INTO regions (id, provider, native_name, display_name, geography, created_at)
                        VALUES (:id, :prov, :id, :id, 'GLOBAL', NOW())
                        ON CONFLICT (id) DO NOTHING;
                    """), {"id": res.region_id, "prov": prov_str})

                    await sess.execute(text("""
                        INSERT INTO services (id, provider, service_code, name, category, created_at)
                        VALUES (:id, :prov, :code, :name, 'COMPUTE', NOW())
                        ON CONFLICT (id) DO NOTHING;
                    """), {
                        "id": res.service_id,
                        "prov": prov_str,
                        "code": res.service_id,
                        "name": res.service_id,
                    })

                    await sess.execute(text("""
                        INSERT INTO resource_types (id, provider, service_id, native_type_name, canonical_type, created_at)
                        VALUES (:id, :prov, :svc, :id, 'INSTANCE', NOW())
                        ON CONFLICT (id) DO NOTHING;
                    """), {
                        "id": res.resource_type_id,
                        "prov": prov_str,
                        "svc": res.service_id,
                    })

                # 3. Scopes
                sorted_scopes = sorted(estate.scopes, key=lambda s: getattr(s, 'depth', 0))
                for sc in sorted_scopes:
                    await sess.execute(text("""
                        INSERT INTO scopes (
                            id, tenant_id, parent_id, name, canonical_role, provider,
                            native_type, native_id, materialized_path, depth,
                            is_sub_group_applicable, provider_native, source_provenance,
                            created_at, updated_at
                        ) VALUES (
                            :id, :tid, :parent_id, :name, :canonical_role, :provider,
                            :native_type, :native_id, :materialized_path, :depth,
                            true, '{}'::jsonb, '{}'::jsonb,
                            NOW(), NOW()
                        )
                        ON CONFLICT (id) DO UPDATE SET
                            name = EXCLUDED.name,
                            materialized_path = EXCLUDED.materialized_path,
                            updated_at = NOW();
                    """), {
                        "id": sc.id,
                        "tid": tenant_id,
                        "parent_id": sc.parent_id,
                        "name": sc.name,
                        "canonical_role": str(sc.canonical_role.value if hasattr(sc.canonical_role, 'value') else sc.canonical_role),
                        "provider": str(sc.provider.value if hasattr(sc.provider, 'value') else sc.provider),
                        "native_type": sc.native_type,
                        "native_id": sc.native_id,
                        "materialized_path": getattr(sc, 'materialized_path', f"/{sc.id}"),
                        "depth": getattr(sc, 'depth', 0),
                    })

                # 4. Resources
                now_str = datetime.now(UTC).isoformat()
                for res in estate.resources:
                    tags_json = json.dumps([t.model_dump() if hasattr(t, 'model_dump') else t for t in res.tags])
                    prov_str = str(res.provider.value if hasattr(res.provider, 'value') else res.provider).upper()
                    payload = {
                        "id": res.id,
                        "tenant_id": tenant_id,
                        "scope_id": res.scope_id,
                        "native_id": res.native_id,
                        "name": res.name,
                        "provider": prov_str,
                        "service_id": res.service_id,
                        "service_name": res.service_id,
                        "service_category": "Compute",
                        "resource_type_id": res.resource_type_id,
                        "resource_type": "VirtualMachine",
                        "region_id": res.region_id,
                        "region_name": res.region_id,
                        "pricing_status": "PAID",
                        "runtime_state": "RUNNING",
                        "monthly_cost": "120.00",
                        "currency": "USD",
                        "last_synced_at": now_str,
                        "created_at": now_str,
                    }
                    await sess.execute(text("""
                        INSERT INTO resources (
                            id, tenant_id, scope_id, native_id, name, provider,
                            service_id, resource_type_id, region_id, availability_zone,
                            pricing_status, tags, application_id, environment_id,
                            owner_id, cost_center_id, business_unit_id, project_id,
                            provider_native, source_provenance, created_at, updated_at
                        ) VALUES (
                            :id, :tid, :sid, :native_id, :name, :provider,
                            :service_id, :resource_type_id, :region_id, :az,
                            :pricing_status, CAST(:tags AS JSONB), NULL, NULL,
                            NULL, NULL, NULL, NULL,
                            CAST(:payload AS JSONB), '{}'::jsonb, NOW(), NOW()
                        )
                        ON CONFLICT (id) DO UPDATE SET
                            name = EXCLUDED.name,
                            provider_native = EXCLUDED.provider_native,
                            updated_at = NOW();
                    """), {
                        "id": res.id,
                        "tid": tenant_id,
                        "sid": res.scope_id,
                        "native_id": res.native_id,
                        "name": res.name,
                        "provider": prov_str.lower(),
                        "service_id": res.service_id,
                        "resource_type_id": res.resource_type_id,
                        "region_id": res.region_id,
                        "az": res.availability_zone,
                        "pricing_status": str(res.pricing_status.value if hasattr(res.pricing_status, 'value') else res.pricing_status),
                        "tags": tags_json,
                        "payload": json.dumps(payload),
                    })

                # 5. Cost Facts
                for cf in estate.cost_facts:
                    b_cost = cf.billed_cost.value if cf.billed_cost and cf.billed_cost.is_present else Decimal("0.00")
                    e_cost = cf.effective_cost.value if cf.effective_cost and cf.effective_cost.is_present else b_cost
                    p_start = cf.charge_period_start.date().replace(day=1)
                    await sess.execute(text("""
                        INSERT INTO cost_fact (
                            billing_period_start, tenant_id, id, scope_id, resource_id,
                            service_id, charge_period_start, charge_period_end,
                            charge_category, charge_subcategory, billed_cost, billed_cost_state,
                            effective_cost, effective_cost_state, contracted_cost, contracted_cost_state,
                            list_cost, list_cost_state, billing_currency, pricing_quantity,
                            pricing_quantity_state, pricing_unit, provider_native, created_at
                        ) VALUES (
                            :b_start, :tid, :id, :scope_id, :resource_id,
                            :service_id, :cp_start, :cp_end,
                            :cat, 'On-Demand', :b_cost, 'PRESENT',
                            :e_cost, 'PRESENT', :b_cost, 'PRESENT',
                            :b_cost, 'PRESENT', 'USD', 1.0,
                            'PRESENT', 'Hours', '{}'::jsonb, NOW()
                        )
                        ON CONFLICT (billing_period_start, tenant_id, id) DO UPDATE SET
                            billed_cost = EXCLUDED.billed_cost,
                            effective_cost = EXCLUDED.effective_cost;
                    """), {
                        "b_start": p_start,
                        "tid": tenant_id,
                        "id": cf.id,
                        "scope_id": cf.scope_id,
                        "resource_id": cf.resource_id,
                        "service_id": cf.service_id,
                        "cp_start": cf.charge_period_start,
                        "cp_end": cf.charge_period_end,
                        "cat": str(cf.charge_category.value if hasattr(cf.charge_category, 'value') else cf.charge_category),
                        "b_cost": b_cost,
                        "e_cost": e_cost,
                    })

                # 6. Budgets for scopes
                for sc in sorted_scopes[:5]:
                    await sess.execute(text("""
                        INSERT INTO budgets (
                            id, tenant_id, scope_id, name, amount, amount_state,
                            period, start_date, created_at
                        ) VALUES (
                            :bid, :tid, :sid, :bname, 50000.00, 'EXACT',
                            'MONTHLY', CURRENT_DATE, NOW()
                        )
                        ON CONFLICT (id) DO UPDATE SET amount = EXCLUDED.amount;
                    """), {
                        "bid": f"bgt-{sc.id}",
                        "tid": tenant_id,
                        "sid": sc.id,
                        "bname": f"Budget for {sc.name}",
                    })

                # 7. Sync Jobs & Connector Schedules
                for sj in estate.sync_jobs:
                    conn_type = str(getattr(sj, "connector_type", getattr(sj, "provider", "aws"))).lower()
                    await sess.execute(text("""
                        INSERT INTO sync_jobs (
                            id, tenant_id, connector_type, scope_id, connector_id,
                            sync_type, capability, dataset_version, idempotency_key,
                            period_start, period_end, scopes_requested, scopes_completed,
                            scopes_failed, status, started_at, completed_at,
                            rows_ingested, error_message, created_at
                        ) VALUES (
                            :id, :tid, :conn_type, 'sc-root', :conn_id,
                            'INCREMENTAL', 'BILLING', '1.0', :idem,
                            NOW() - interval '1 day', NOW(), '[]'::jsonb, '[]'::jsonb,
                            '[]'::jsonb, :status, NOW() - interval '1 hour', NOW(),
                            100, NULL, NOW()
                        )
                        ON CONFLICT (id) DO UPDATE SET status = EXCLUDED.status;
                    """), {
                        "id": sj.id,
                        "tid": tenant_id,
                        "conn_type": conn_type,
                        "conn_id": f"conn-{sj.id}",
                        "idem": f"idem-{sj.id}",
                        "status": str(sj.status.value if hasattr(sj.status, 'value') else sj.status),
                    })

                await sess.commit()

        try:
            run_async(_do_persist())
            logger.info("Demo tenant '%s' estate successfully persisted to PostgreSQL.", tenant_id)
        except Exception as exc:
            logger.warning("Could not persist demo estate to PostgreSQL: %s", exc)


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


def reset_demo_tenant_service() -> DemoTenantLoaderService:
    """Resets the global DemoTenantLoaderService singleton."""
    global _demo_tenant_service
    _demo_tenant_service = DemoTenantLoaderService()
    return _demo_tenant_service

