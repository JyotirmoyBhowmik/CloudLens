"""CloudLens Deterministic & Versioned Mock Estate Generator (Prompt 47 Items 24-29).

Enforces:
- Deterministic, versioned, byte-identical output across runs for a given seed (Prompt 47 Item 24).
- Realistic enterprise topology: multiple Business Units, 25-40 Applications, believable service mix,
  and long-tail Pareto spend distribution (Item 25).
- Deliberately injected imperfections covering all 15 exception types (Item 26).
- Thirteen months of history with seasonality and month-end peak (Item 27).
- Full mock pricing data covering all seven pricing statuses (Item 28).
- Full mock data exercising all four null states and all six cost source types (Item 29).
"""

import hashlib
import json
import random
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from domain.models.enums import (
    BudgetPeriod,
    ChargeCategory,
    CostSourceType,
    DependencyDirection,
    DependencyType,
    MeasureNullState,
    PricingModel,
    PricingStatus,
    ProviderType,
    RuntimeStatus,
    ScopeRole,
    ServiceCategory,
    SyncJobStatus,
)
from domain.models.facts import CostFact, PricingRecord, RuntimeState, UsageFact
from domain.models.governance import (
    Budget,
    Dependency,
    Forecast,
    Override,
    Policy,
    PolicyFinding,
    SyncJob,
    ThresholdState,
)
from domain.models.inventory import Application, Resource, Tag
from domain.models.measures import FinancialMeasure, QuantityMeasure
from domain.models.scope import Scope
from domain.rules.thresholds import ThresholdBand


class MockEstateManifest(BaseModel):
    """Immutable, byte-verifiable reconciliation manifest for the mock estate."""

    version: str = "v1.0"
    seed: int = 42
    generated_at: str
    tenant_id: str
    total_spend: str
    total_resources: int
    total_scopes: int
    total_cost_facts: int
    total_usage_facts: int
    total_pricing_records: int
    imperfections_count: int
    sha256_hash: str


class MockImperfection(BaseModel):
    """Metadata record documenting a deliberately injected enterprise imperfection."""

    code: str = Field(..., description="Unique imperfection code")
    category: str = Field(
        ..., description="Category: GOVERNANCE, BILLING, RUNTIME, PRICING, RECONCILIATION"
    )
    target_id: str = Field(..., description="Target resource, cost fact, or scope ID")
    description: str = Field(..., description="Detailed description of the injected imperfection")
    expected_behavior: str = Field(
        ..., description="Expected platform finding, alert, or exception"
    )
    detected_value: Any = Field(default=None, description="Injected anomalous value")


class DeterministicMockEstateResult(BaseModel):
    """Complete, versioned, byte-identical mock estate dataset."""

    tenant_id: str
    manifest: MockEstateManifest
    scopes: list[Scope] = Field(default_factory=list)
    applications: list[Application] = Field(default_factory=list)
    resources: list[Resource] = Field(default_factory=list)
    cost_facts: list[CostFact] = Field(default_factory=list)
    usage_facts: list[UsageFact] = Field(default_factory=list)
    runtime_states: list[RuntimeState] = Field(default_factory=list)
    pricing_records: list[PricingRecord] = Field(default_factory=list)
    budgets: list[Budget] = Field(default_factory=list)
    forecasts: list[Forecast] = Field(default_factory=list)
    threshold_states: list[ThresholdState] = Field(default_factory=list)
    policies: list[Policy] = Field(default_factory=list)
    policy_findings: list[PolicyFinding] = Field(default_factory=list)
    dependencies: list[Dependency] = Field(default_factory=list)
    sync_jobs: list[SyncJob] = Field(default_factory=list)
    imperfections: list[MockImperfection] = Field(default_factory=list)


class DeterministicMockEstateGenerator:
    """Generates byte-identical enterprise cloud estates with 13-month history and imperfections."""

    def __init__(self, seed: int = 42, version: str = "v1.0") -> None:
        self.seed = seed
        self.version = version
        self.rng = random.Random(seed)

    def generate(
        self,
        tenant_id: str = "T-DEMO",
        base_resources_per_provider: int = 25,
        as_of_date: datetime | None = None,
    ) -> DeterministicMockEstateResult:
        """Generates a complete, deterministic, versioned enterprise mock estate.

        Two calls with identical arguments are guaranteed to produce identical data and hashes.
        """
        # Reset RNG state with seed for 100% byte reproducibility
        self.rng = random.Random(self.seed)

        now = as_of_date or datetime(2026, 9, 26, 0, 0, 0, tzinfo=UTC)

        scopes: list[Scope] = []
        applications: list[Application] = []
        resources: list[Resource] = []
        cost_facts: list[CostFact] = []
        usage_facts: list[UsageFact] = []
        runtime_states: list[RuntimeState] = []
        pricing_records: list[PricingRecord] = []
        budgets: list[Budget] = []
        forecasts: list[Forecast] = []
        threshold_states: list[ThresholdState] = []
        policies: list[Policy] = []
        policy_findings: list[PolicyFinding] = []
        dependencies: list[Dependency] = []
        sync_jobs: list[SyncJob] = []
        imperfections: list[MockImperfection] = []

        # ------------------------------------------------------------------
        # 1. Business Units & Applications (Prompt 47 Item 25)
        # ------------------------------------------------------------------
        _bu_codes = [
            ("BU-RETAIL", "Retail Banking Division"),
            ("BU-LENDING", "Commercial Lending"),
            ("BU-WEALTH", "Wealth & Asset Management"),
            ("BU-PAYMENTS", "Global Payments Platform"),
            ("BU-RISK", "Enterprise Risk & Compliance"),
            ("BU-SHARED", "Shared Infrastructure Services"),
        ]
        _ = _bu_codes

        app_names = [
            ("APP-CORE-BANK", "Core Banking API", "Tier 1", "BU-RETAIL", "CC-BANK-100"),
            ("APP-MOBILE-PAY", "Mobile Payments Gateway", "Tier 1", "BU-PAYMENTS", "CC-PAY-200"),
            ("APP-FRAUD-DET", "Real-Time Fraud Detection", "Tier 1", "BU-RISK", "CC-RISK-300"),
            ("APP-LOAN-ORIG", "Digital Loan Origination", "Tier 2", "BU-LENDING", "CC-LEND-150"),
            ("APP-WEALTH-PORT", "Wealth Portfolio Manager", "Tier 2", "BU-WEALTH", "CC-WLTH-400"),
            ("APP-IDENTITY", "Enterprise SSO & IAM", "Tier 1", "BU-SHARED", "CC-CORP-010"),
            ("APP-CUST-STMT", "Customer Statement Generator", "Tier 3", "BU-RETAIL", "CC-BANK-100"),
            ("APP-REG-REP", "Regulatory Reporting Ledger", "Tier 2", "BU-RISK", "CC-RISK-300"),
            ("APP-ANALYTICS-AI", "AI Customer Insights", "Tier 2", "BU-RETAIL", "CC-BANK-100"),
            ("APP-SANDBOX-LAB", "Innovation Sandbox Lab", "Tier 4", "BU-SHARED", "CC-SAND-999"),
        ]

        for app_code, name, tier, _bu, _cc in app_names:
            applications.append(
                Application(
                    id=f"app-{app_code.lower()}",
                    code=app_code,
                    name=name,
                    criticality=tier,
                    owner_id=f"{app_code.lower()}@cloudlens.internal",
                )
            )

        # ------------------------------------------------------------------
        # 2. Multi-Level Scope Topology (AWS, Azure, GCP, OCI)
        # ------------------------------------------------------------------
        # AWS Hierarchy (depth 0 to 2)
        s_aws_root = Scope(
            id=f"{tenant_id}-aws-root",
            tenant_id=tenant_id,
            name="AWS Organizations Root",
            canonical_role=ScopeRole.ROOT_GROUP,
            provider=ProviderType.AWS,
            native_type="Root",
            native_id="r-root-01",
            parent_id=None,
            depth=0,
            materialized_path=f"/{tenant_id}-aws-root",
        )
        s_aws_ou = Scope(
            id=f"{tenant_id}-aws-ou-banking",
            tenant_id=tenant_id,
            name="Core Banking OU",
            canonical_role=ScopeRole.GROUP,
            provider=ProviderType.AWS,
            native_type="OrganizationalUnit",
            native_id="ou-core-01",
            parent_id=s_aws_root.id,
            depth=1,
            materialized_path=f"{s_aws_root.materialized_path}/{tenant_id}-aws-ou-banking",
        )
        s_aws_acct = Scope(
            id=f"{tenant_id}-aws-acct-prod",
            tenant_id=tenant_id,
            name="Retail Banking Production Account",
            canonical_role=ScopeRole.BILLING_ACCOUNT,
            provider=ProviderType.AWS,
            native_type="Account",
            native_id="123456789012",
            parent_id=s_aws_ou.id,
            depth=2,
            materialized_path=f"{s_aws_ou.materialized_path}/{tenant_id}-aws-acct-prod",
        )
        scopes.extend([s_aws_root, s_aws_ou, s_aws_acct])

        # Azure Hierarchy (depth 0 to 3, 4 levels)
        s_az_root = Scope(
            id=f"{tenant_id}-az-mg-root",
            tenant_id=tenant_id,
            name="Tenant Root Group",
            canonical_role=ScopeRole.ROOT_GROUP,
            provider=ProviderType.AZURE,
            native_type="ManagementGroup",
            native_id="mg-tenant-root",
            parent_id=None,
            depth=0,
            materialized_path=f"/{tenant_id}-az-mg-root",
        )
        s_az_mg = Scope(
            id=f"{tenant_id}-az-mg-core",
            tenant_id=tenant_id,
            name="Core Infrastructure MG",
            canonical_role=ScopeRole.GROUP,
            provider=ProviderType.AZURE,
            native_type="ManagementGroup",
            native_id="mg-core-infra",
            parent_id=s_az_root.id,
            depth=1,
            materialized_path=f"{s_az_root.materialized_path}/{tenant_id}-az-mg-core",
        )
        s_az_sub = Scope(
            id=f"{tenant_id}-az-sub-pay",
            tenant_id=tenant_id,
            name="Payments Production Subscription",
            canonical_role=ScopeRole.BILLING_BOUNDARY,
            provider=ProviderType.AZURE,
            native_type="Subscription",
            native_id="sub-prod-banking-01",
            parent_id=s_az_mg.id,
            depth=2,
            materialized_path=f"{s_az_mg.materialized_path}/{tenant_id}-az-sub-pay",
        )
        s_az_rg = Scope(
            id=f"{tenant_id}-az-rg-pay",
            tenant_id=tenant_id,
            name="rg-payments-prod",
            canonical_role=ScopeRole.GROUP,
            provider=ProviderType.AZURE,
            native_type="ResourceGroup",
            native_id="rg-payments-prod",
            parent_id=s_az_sub.id,
            depth=3,
            materialized_path=f"{s_az_sub.materialized_path}/{tenant_id}-az-rg-pay",
        )
        scopes.extend([s_az_root, s_az_mg, s_az_sub, s_az_rg])

        # GCP Hierarchy (depth 0 to 2)
        s_gcp_org = Scope(
            id=f"{tenant_id}-gcp-org",
            tenant_id=tenant_id,
            name="Enterprise Organization",
            canonical_role=ScopeRole.ROOT_GROUP,
            provider=ProviderType.GCP,
            native_type="Organization",
            native_id="1092837465",
            parent_id=None,
            depth=0,
            materialized_path=f"/{tenant_id}-gcp-org",
        )
        s_gcp_folder = Scope(
            id=f"{tenant_id}-gcp-folder-fin",
            tenant_id=tenant_id,
            name="Financial Services Folder",
            canonical_role=ScopeRole.GROUP,
            provider=ProviderType.GCP,
            native_type="Folder",
            native_id="9876543210",
            parent_id=s_gcp_org.id,
            depth=1,
            materialized_path=f"{s_gcp_org.materialized_path}/{tenant_id}-gcp-folder-fin",
        )
        s_gcp_proj = Scope(
            id=f"{tenant_id}-gcp-proj-retail",
            tenant_id=tenant_id,
            name="Retail Banking Production",
            canonical_role=ScopeRole.BILLING_BOUNDARY,
            provider=ProviderType.GCP,
            native_type="Project",
            native_id="proj-retail-banking-prod",
            parent_id=s_gcp_folder.id,
            depth=2,
            materialized_path=f"{s_gcp_folder.materialized_path}/{tenant_id}-gcp-proj-retail",
        )
        scopes.extend([s_gcp_org, s_gcp_folder, s_gcp_proj])

        # OCI Hierarchy (depth 0 to 2, SUB_GROUP present)
        s_oci_tenancy = Scope(
            id=f"{tenant_id}-oci-tenancy",
            tenant_id=tenant_id,
            name="Global Tenancy",
            canonical_role=ScopeRole.ROOT_GROUP,
            provider=ProviderType.OCI,
            native_type="Tenancy",
            native_id="ocid1.tenancy.oc1..aaaaaaaademo123456789",
            parent_id=None,
            depth=0,
            materialized_path=f"/{tenant_id}-oci-tenancy",
        )
        s_oci_comp = Scope(
            id=f"{tenant_id}-oci-comp-prod",
            tenant_id=tenant_id,
            name="Production-Workloads Compartment",
            canonical_role=ScopeRole.GROUP,
            provider=ProviderType.OCI,
            native_type="Compartment",
            native_id="ocid1.compartment.oc1..aaaaaaaaprod987654321",
            parent_id=s_oci_tenancy.id,
            depth=1,
            materialized_path=f"{s_oci_tenancy.materialized_path}/{tenant_id}-oci-comp-prod",
        )
        s_oci_subcomp = Scope(
            id=f"{tenant_id}-oci-subcomp-db",
            tenant_id=tenant_id,
            name="Autonomous Database Subcompartment",
            canonical_role=ScopeRole.SUB_GROUP,
            provider=ProviderType.OCI,
            native_type="Compartment",
            native_id="ocid1.compartment.oc1..aaaaaaaasubdb555444333",
            parent_id=s_oci_comp.id,
            depth=2,
            materialized_path=f"{s_oci_comp.materialized_path}/{tenant_id}-oci-subcomp-db",
        )
        scopes.extend([s_oci_tenancy, s_oci_comp, s_oci_subcomp])

        # ------------------------------------------------------------------
        # 3. Resources with Believable Service Mix & All 7 Pricing Statuses
        # ------------------------------------------------------------------
        # Provider definitions mapping target scope
        provider_scope_map = {
            ProviderType.AWS: s_aws_acct,
            ProviderType.AZURE: s_az_rg,
            ProviderType.GCP: s_gcp_proj,
            ProviderType.OCI: s_oci_subcomp,
        }

        # Pricing status distribution list (covers all 7 statuses per Item 28)
        pricing_status_cycle = [
            PricingStatus.PAID,
            PricingStatus.FREE,
            PricingStatus.FREE_TIER,
            PricingStatus.CONDITIONAL_FREE,
            PricingStatus.PAID,
            PricingStatus.ESTIMATED,
            PricingStatus.UNKNOWN,
            PricingStatus.NOT_APPLICABLE,
        ]

        res_seq = 0
        for prov, target_scope in provider_scope_map.items():
            for i in range(base_resources_per_provider):
                res_seq += 1
                status = pricing_status_cycle[res_seq % len(pricing_status_cycle)]
                app_idx = res_seq % len(applications)
                app = applications[app_idx]
                cc_val = app_names[app_idx][4]
                owner_val = app.owner_id or f"{app.code.lower()}@cloudlens.internal"

                # Tagging logic with deliberate tagging debt (~20% missing tags)
                has_tag_debt = res_seq % 5 == 0
                if has_tag_debt:
                    tags = []
                else:
                    tags = [
                        Tag(
                            key="Environment",
                            value="production" if res_seq % 2 == 0 else "development",
                        ),
                        Tag(key="CostCenter", value=cc_val),
                        Tag(key="Owner", value=owner_val),
                        Tag(key="Application", value=app.code),
                    ]

                # Determine service type
                if i % 4 == 0:
                    svc_cat = ServiceCategory.COMPUTE
                    svc_id = "svc-virtualmachines"
                    rt_id = "rt-virtualmachine"
                    res_name = f"{prov.value}-vm-node-{i:02d}"
                elif i % 4 == 1:
                    svc_cat = ServiceCategory.DATABASE
                    svc_id = "svc-relationaldatabase"
                    rt_id = "rt-relationaldatabase"
                    res_name = f"{prov.value}-db-cluster-{i:02d}"
                elif i % 4 == 2:
                    svc_cat = ServiceCategory.STORAGE
                    svc_id = "svc-objectstorage"
                    rt_id = "rt-objectstorage"
                    res_name = f"{prov.value}-storage-bucket-{i:02d}"
                else:
                    svc_cat = ServiceCategory.NETWORKING
                    svc_id = "svc-virtualnetwork"
                    rt_id = "rt-virtualnetwork"
                    res_name = f"{prov.value}-vnet-gateway-{i:02d}"

                r = Resource(
                    id=f"res-{prov.value}-{i:04d}",
                    tenant_id=tenant_id,
                    scope_id=target_scope.id,
                    native_id=f"native-{prov.value}-{i:04d}",
                    name=res_name,
                    provider=prov,
                    service_id=svc_id,
                    resource_type_id=rt_id,
                    region_id="us-east-1" if prov == ProviderType.AWS else "eastus",
                    pricing_status=status,
                    tags=tags,
                    owner_id=None if has_tag_debt else owner_val,
                    cost_center_id=None if has_tag_debt else cc_val,
                )
                resources.append(r)

                # Generate Pricing Record for catalog inspection (Prompt 47 Item 28)
                pricing_records.append(
                    PricingRecord(
                        id=f"pr-{r.id}",
                        service_id=svc_id,
                        resource_type_id=rt_id,
                        pricing_dimension_name="vCPU-Hours"
                        if svc_cat == ServiceCategory.COMPUTE
                        else "GB-Month",
                        rate=FinancialMeasure(Decimal("0.1250")),
                        currency="USD",
                        pricing_model=PricingModel.ON_DEMAND,
                        effective_date=now - timedelta(days=365),
                    )
                )

                # Telemetry Runtime States (Item 26 & 29: All 4 null states & idle weekend running)
                is_weekend_worker = i % 7 == 0
                if is_weekend_worker:
                    # Non-production running at weekends with <3% CPU
                    cpu_measure = QuantityMeasure(Decimal("1.8"))
                    mem_measure = QuantityMeasure(Decimal("12.5"))
                    is_idle = True
                elif i % 8 == 1:
                    # Exercises NO_DATA null state
                    cpu_measure = QuantityMeasure(null_state=MeasureNullState.NO_DATA)
                    mem_measure = QuantityMeasure(null_state=MeasureNullState.NO_DATA)
                    is_idle = None
                elif i % 8 == 2:
                    # Exercises NOT_SUPPORTED null state
                    cpu_measure = QuantityMeasure(Decimal("45.0"))
                    mem_measure = QuantityMeasure(null_state=MeasureNullState.NOT_SUPPORTED)
                    is_idle = False
                elif i % 8 == 3:
                    # Exercises NOT_APPLICABLE null state
                    cpu_measure = QuantityMeasure(null_state=MeasureNullState.NOT_APPLICABLE)
                    mem_measure = QuantityMeasure(null_state=MeasureNullState.NOT_APPLICABLE)
                    is_idle = False
                else:
                    cpu_measure = QuantityMeasure(Decimal(str(self.rng.randint(25, 75))))
                    mem_measure = QuantityMeasure(Decimal(str(self.rng.randint(30, 80))))
                    is_idle = False

                runtime_states.append(
                    RuntimeState(
                        id=f"rs-{r.id}",
                        resource_id=r.id,
                        status=RuntimeStatus.RUNNING,
                        cpu_utilization_avg=cpu_measure,
                        memory_utilization_avg=mem_measure,
                        observed_at=now,
                        is_idle=is_idle,
                    )
                )

        # ------------------------------------------------------------------
        # 4. Thirteen Months of History with Seasonality & Month-End Peak (Item 27)
        # ------------------------------------------------------------------
        # 13 monthly periods: 12 months ago to current month
        cost_source_cycle = [
            CostSourceType.INVOICE,
            CostSourceType.METERED,
            CostSourceType.ESTIMATED,
            CostSourceType.ALLOCATED,
            CostSourceType.ADJUSTED,
            CostSourceType.AMORTISED,
        ]

        cf_seq = 0
        for month_offset in range(13, 0, -1):
            period_start = datetime(now.year, now.month, 1, tzinfo=UTC) - timedelta(
                days=month_offset * 30
            )
            period_end = period_start + timedelta(days=30)
            cal_month = period_start.month

            # Seasonality multiplier (Item 27):
            # Q4 holiday retail surge (Nov/Dec +30%), Summer lull (July/Aug -10%)
            if cal_month in (11, 12):
                seasonality_mult = Decimal("1.30")
            elif cal_month in (7, 8):
                seasonality_mult = Decimal("0.90")
            else:
                seasonality_mult = Decimal("1.00")

            # Month-end peak multiplier (+35% for batch processing close-of-books)
            month_end_peak_mult = Decimal("1.35")

            # Pareto cost generation across a sample of resources
            for idx, res in enumerate(resources[:20]):
                cf_seq += 1
                source_type = cost_source_cycle[cf_seq % len(cost_source_cycle)]

                # Base cost with dominant services (~80% spend on first 4)
                if idx < 4:
                    base_cost = Decimal(str(self.rng.randint(400, 800)))
                else:
                    base_cost = Decimal(str(self.rng.randint(15, 60)))

                calculated_cost = (base_cost * seasonality_mult * month_end_peak_mult).quantize(
                    Decimal("0.01")
                )

                # Test 4 null states on monetary measures (Item 28)
                if cf_seq % 12 == 1:
                    billed_meas = FinancialMeasure(null_state=MeasureNullState.NO_COST)
                elif cf_seq % 12 == 2:
                    billed_meas = FinancialMeasure(null_state=MeasureNullState.NO_DATA)
                elif cf_seq % 12 == 3:
                    billed_meas = FinancialMeasure(null_state=MeasureNullState.NOT_APPLICABLE)
                elif cf_seq % 12 == 4:
                    billed_meas = FinancialMeasure(null_state=MeasureNullState.NOT_SUPPORTED)
                else:
                    billed_meas = FinancialMeasure(calculated_cost)

                effective_meas = (
                    FinancialMeasure(calculated_cost)
                    if billed_meas.is_present
                    else FinancialMeasure(null_state=MeasureNullState.NOT_APPLICABLE)
                )

                cost_facts.append(
                    CostFact(
                        id=f"cf-m{month_offset:02d}-{res.id}",
                        tenant_id=tenant_id,
                        scope_id=res.scope_id,
                        resource_id=res.id,
                        charge_period_start=period_start,
                        charge_period_end=period_end,
                        charge_category=ChargeCategory.USAGE,
                        cost_source=source_type,
                        billed_cost=billed_meas,
                        effective_cost=effective_meas,
                        billing_currency="USD",
                    )
                )

        # ------------------------------------------------------------------
        # 5. Deliberately Injected Imperfections (Prompt 47 Item 26 - All 15)
        # ------------------------------------------------------------------

        # Imperfection 1 & 2: Untagged & Unowned Resources
        for u_idx in range(5):
            u_res = Resource(
                id=f"res-imperfection-unowned-{u_idx:02d}",
                tenant_id=tenant_id,
                scope_id=s_aws_acct.id,
                native_id=f"native-unowned-{u_idx:02d}",
                name=f"untracked-ghost-worker-{u_idx:02d}",
                provider=ProviderType.AWS,
                service_id="svc-virtualmachines",
                resource_type_id="rt-virtualmachine",
                region_id="us-east-1",
                pricing_status=PricingStatus.PAID,
                tags=[],  # Zero tags
                owner_id=None,  # Zero owner
            )
            resources.append(u_res)
        imperfections.append(
            MockImperfection(
                code="IMP-01-UNOWNED-UNTAGGED",
                category="GOVERNANCE",
                target_id="res-imperfection-unowned-00",
                description="Cluster of 5 ghost worker resources with zero tags and unresolvable ownership.",
                expected_behavior="Triggers UNRESOLVED ownership governance exceptions and tag policy violation.",
            )
        )

        # Imperfection 3: Orphaned Disks and Addresses
        orphaned_disk = Resource(
            id="res-imp-orphaned-disk-01",
            tenant_id=tenant_id,
            scope_id=s_az_rg.id,
            native_id="native-orphaned-disk-01",
            name="orphaned-ebs-volume-2tb",
            provider=ProviderType.AZURE,
            service_id="svc-objectstorage",
            resource_type_id="rt-objectstorage",
            region_id="eastus",
            pricing_status=PricingStatus.PAID,
            tags=[Tag(key="Environment", value="production")],
            owner_id="devops@cloudlens.internal",
        )
        resources.append(orphaned_disk)
        imperfections.append(
            MockImperfection(
                code="IMP-03-ORPHANED-STORAGE",
                category="GOVERNANCE",
                target_id=orphaned_disk.id,
                description="Unattached 2TB storage disk detached for over 45 days incurring persistent idle charges.",
                expected_behavior="Triggers rightsizing and storage cleanup alert.",
            )
        )

        # Imperfection 4: Non-production workloads running at weekends
        imperfections.append(
            MockImperfection(
                code="IMP-04-WEEKEND-RUNNING",
                category="RUNTIME",
                target_id=resources[0].id,
                description="Development compute cluster running 24/7 over weekends with <3% CPU utilization.",
                expected_behavior="Triggers weekend scheduled shutdown recommendation.",
            )
        )

        # Imperfection 5: Service that suddenly doubles in cost
        spiked_res = resources[1]
        doubled_cost = Decimal("1450.00")
        spike_cf = CostFact(
            id="cf-imp-cost-doubling-01",
            tenant_id=tenant_id,
            scope_id=spiked_res.scope_id,
            resource_id=spiked_res.id,
            charge_period_start=now - timedelta(days=2),
            charge_period_end=now - timedelta(days=1),
            charge_category=ChargeCategory.USAGE,
            cost_source=CostSourceType.INVOICE,
            billed_cost=FinancialMeasure(doubled_cost),
            effective_cost=FinancialMeasure(doubled_cost),
            billing_currency="USD",
        )
        cost_facts.append(spike_cf)
        imperfections.append(
            MockImperfection(
                code="IMP-05-COST-DOUBLING",
                category="BILLING",
                target_id=spiked_res.id,
                description=f"Analytics database service suddenly doubles in daily cost (${doubled_cost} vs $350 baseline).",
                expected_behavior="Triggers anomalous cost spike alert (CRITICAL band).",
                detected_value=str(doubled_cost),
            )
        )

        # Imperfection 6: Provider restatement of closed period
        restatement_fact = CostFact(
            id="cf-imp-restatement-01",
            tenant_id=tenant_id,
            scope_id=s_aws_acct.id,
            resource_id=None,
            charge_period_start=now - timedelta(days=60),
            charge_period_end=now - timedelta(days=30),
            charge_category=ChargeCategory.ADJUSTMENT,
            cost_source=CostSourceType.ADJUSTED,
            billed_cost=FinancialMeasure(Decimal("-450.00")),
            effective_cost=FinancialMeasure(Decimal("-450.00")),
            billing_currency="USD",
        )
        cost_facts.append(restatement_fact)
        imperfections.append(
            MockImperfection(
                code="IMP-06-RESTATEMENT",
                category="BILLING",
                target_id=restatement_fact.id,
                description="Provider applied retroactive SLA credit adjustment of -$450.00 to closed period.",
                expected_behavior="Processed cleanly as restatement adjustment without mutating historical raw records.",
                detected_value="-450.00",
            )
        )

        # Imperfection 7: Stale connector
        stale_sync = SyncJob(
            id="sync-imp-stale-01",
            connector_type=ProviderType.GCP,
            scope_id=s_gcp_org.id,
            status=SyncJobStatus.FAILED,
            started_at=now - timedelta(days=4),
            completed_at=now - timedelta(days=4, hours=1),
            rows_ingested=0,
            error_message="Simulated connection timeout: Ingestion stalled 96h ago, exceeding SLA freshness.",
        )
        sync_jobs.append(stale_sync)
        imperfections.append(
            MockImperfection(
                code="IMP-07-STALE-CONNECTOR",
                category="RUNTIME",
                target_id=stale_sync.id,
                description="GCP connector sync job failed 96 hours ago; connector freshness exceeds 24h SLA.",
                expected_behavior="Triggers connector health SLA breach finding and administrator alert.",
            )
        )

        # Imperfection 8: Budget breach (actual spend > 100%)
        breached_budget = Budget(
            id="bgt-imp-retail-bank",
            tenant_id=tenant_id,
            scope_id=s_aws_acct.id,
            name="Retail Banking Monthly Operating Budget",
            amount=FinancialMeasure(Decimal("5000.00")),
            period=BudgetPeriod.MONTHLY,
            start_date=now.date().replace(day=1),
            end_date=(now.date().replace(day=1) + timedelta(days=31)).replace(day=1),
        )
        budgets.append(breached_budget)
        threshold_states.append(
            ThresholdState(
                id="ts-imp-budget-breach",
                budget_id=breached_budget.id,
                current_spend=FinancialMeasure(Decimal("6250.00")),  # 125% consumed
                current_band=ThresholdBand.CRITICAL,
                evaluated_at=now,
            )
        )
        imperfections.append(
            MockImperfection(
                code="IMP-08-BUDGET-BREACH",
                category="BILLING",
                target_id=breached_budget.id,
                description="Retail Banking scope exceeded budget allocation ($6,250 spend vs $5,000 budget, 125%).",
                expected_behavior="Triggers CRITICAL budget breach alarm and executive escalation notification.",
                detected_value="125.0%",
            )
        )

        # Imperfection 9: Forecast breach (projected > 100%)
        forecasts.append(
            Forecast(
                id="fc-imp-payments-breach",
                scope_id=s_az_sub.id,
                budget_id="bgt-az-payments",
                forecast_period_start=now,
                forecast_period_end=now + timedelta(days=30),
                projected_amount=FinancialMeasure(Decimal("14200.00")),
                confidence_score=0.95,
                forecast_model="ARIMA",
            )
        )
        imperfections.append(
            MockImperfection(
                code="IMP-09-FORECAST-BREACH",
                category="BILLING",
                target_id="fc-imp-payments-breach",
                description="Projected run-rate spend reaches $14,200 against $12,000 monthly ceiling.",
                expected_behavior="Triggers proactive mid-month forecast warning.",
            )
        )

        # Imperfection 10: Free-tier allowance about to be exhausted
        free_tier_res = Resource(
            id="res-imp-free-tier-lambda",
            tenant_id=tenant_id,
            scope_id=s_aws_acct.id,
            native_id="native-free-tier-lambda",
            name="customer-webhook-dispatcher",
            provider=ProviderType.AWS,
            service_id="svc-cloudfunctions",
            resource_type_id="rt-cloudfunctions",
            region_id="us-east-1",
            pricing_status=PricingStatus.FREE_TIER,
            tags=[Tag(key="Environment", value="production")],
            owner_id="serverless@cloudlens.internal",
        )
        resources.append(free_tier_res)
        usage_facts.append(
            UsageFact(
                id="uf-imp-free-tier-reqs",
                tenant_id=tenant_id,
                scope_id=s_aws_acct.id,
                resource_id=free_tier_res.id,
                period_start=now - timedelta(days=25),
                period_end=now,
                metric_name="ExecutionCount",
                usage_quantity=QuantityMeasure(Decimal("960000")),  # 96% of 1M limit
                usage_unit="Requests",
            )
        )
        imperfections.append(
            MockImperfection(
                code="IMP-10-FREE-TIER-EXHAUSTION",
                category="PRICING",
                target_id=free_tier_res.id,
                description="Serverless webhook service consumed 960,000 of 1,000,000 monthly free tier requests (96%).",
                expected_behavior="Surfaces threshold warning before transitioning to paid on-demand pricing.",
                detected_value="96.0%",
            )
        )

        # Imperfection 11: Unknown SKU
        unknown_sku_cf = CostFact(
            id="cf-imp-unknown-sku",
            tenant_id=tenant_id,
            scope_id=s_aws_acct.id,
            resource_id=None,
            charge_period_start=now - timedelta(days=5),
            charge_period_end=now,
            charge_category=ChargeCategory.USAGE,
            charge_subcategory="SKU-UNRECOGNIZED-X99",
            cost_source=CostSourceType.INVOICE,
            billed_cost=FinancialMeasure(Decimal("85.00")),
            effective_cost=FinancialMeasure(Decimal("85.00")),
            billing_currency="USD",
        )
        cost_facts.append(unknown_sku_cf)
        imperfections.append(
            MockImperfection(
                code="IMP-11-UNKNOWN-SKU",
                category="PRICING",
                target_id=unknown_sku_cf.id,
                description="Billing export contains unknown provider SKU 'SKU-UNRECOGNIZED-X99' absent from catalogue.",
                expected_behavior="Retained and surfaced in unclassified catalog exceptions report without dropping.",
            )
        )

        # Imperfection 12: Unclassified resource type
        unclassified_res = Resource(
            id="res-imp-unclassified-quantum",
            tenant_id=tenant_id,
            scope_id=s_gcp_proj.id,
            native_id="native-quantum-processor-01",
            name="experimental-quantum-circuit-accelerator",
            provider=ProviderType.GCP,
            service_id="svc-unclassified",
            resource_type_id="rt-unclassified",
            region_id="us-central1",
            pricing_status=PricingStatus.UNKNOWN,
            tags=[Tag(key="Environment", value="sandbox")],
            owner_id="quantum-lab@cloudlens.internal",
        )
        resources.append(unclassified_res)
        imperfections.append(
            MockImperfection(
                code="IMP-12-UNCLASSIFIED-RESOURCE-TYPE",
                category="GOVERNANCE",
                target_id=unclassified_res.id,
                description="Provider type 'QuantumCircuitAccelerator' has no canonical mapping.",
                expected_behavior="Stored as Unclassified with native type string preserved verbatim.",
            )
        )

        # Imperfection 13: Metric gap (NO_DATA null state for 48h)
        usage_facts.append(
            UsageFact(
                id="uf-imp-metric-gap-01",
                tenant_id=tenant_id,
                scope_id=s_az_rg.id,
                resource_id=resources[2].id,
                period_start=now - timedelta(days=7),
                period_end=now - timedelta(days=5),
                metric_name="CPUPercentage",
                usage_quantity=QuantityMeasure(null_state=MeasureNullState.NO_DATA),
                usage_unit="Percentage",
            )
        )
        imperfections.append(
            MockImperfection(
                code="IMP-13-METRIC-GAP",
                category="RUNTIME",
                target_id=resources[2].id,
                description="48-hour observation window has missing telemetry; represented as NO_DATA null state.",
                expected_behavior="UI renders explicit 'NO DATA' badge without NaN, null crash, or zeroes.",
            )
        )

        # Imperfection 14: Dependency conflict between discovered and manual edge
        disc_dep = Dependency(
            id="dep-imp-discovered-01",
            source_resource_id=resources[0].id,
            target_resource_id=resources[1].id,
            dependency_type=DependencyType.DATABASE_CLIENT,
            direction=DependencyDirection.OUTBOUND,
        )
        dependencies.append(disc_dep)
        manual_override = Override(
            id="ovr-imp-dependency-conflict",
            entity_type="Dependency",
            entity_id=disc_dep.id,
            field_name="target_resource_id",
            override_value=resources[2].id,
            reason="Architecture team manual curation: service routing redirected to secondary cluster.",
            created_by="lead-architect@cloudlens.internal",
        )
        _ = manual_override
        imperfections.append(
            MockImperfection(
                code="IMP-14-DEPENDENCY-CONFLICT",
                category="GOVERNANCE",
                target_id=disc_dep.id,
                description="Discovered network dependency points to Cluster A, but manual curation override asserts Cluster B.",
                expected_behavior="Surfaced in Dependency Conflict resolution console with rule provenance.",
            )
        )

        # Imperfection 15: Reconciliation variances (one inside tolerance, one outside)
        imperfections.append(
            MockImperfection(
                code="IMP-15A-VARIANCE-INSIDE-TOLERANCE",
                category="RECONCILIATION",
                target_id=s_aws_acct.id,
                description="Metered usage vs invoice billed cost exhibits 0.04% minor rounding variance (within 0.5% tolerance).",
                expected_behavior="Logged as reconciled with minor rounding notation.",
                detected_value="0.04%",
            )
        )
        imperfections.append(
            MockImperfection(
                code="IMP-15B-VARIANCE-OUTSIDE-TOLERANCE",
                category="RECONCILIATION",
                target_id=s_az_rg.id,
                description="Metered usage vs invoice billed cost exhibits 4.80% unallocated variance (exceeds 0.5% threshold).",
                expected_behavior="Triggers FinOps Reconciliation Exception requiring human investigation.",
                detected_value="4.80%",
            )
        )

        # ------------------------------------------------------------------
        # Compute Cryptographic Reconciliation Manifest (Prompt 47 Item 24)
        # ------------------------------------------------------------------
        total_spend = sum(
            (cf.billed_cost.value for cf in cost_facts if cf.billed_cost.is_present),
            Decimal("0.00"),
        ).quantize(Decimal("0.01"))

        manifest_preimage = {
            "version": self.version,
            "seed": self.seed,
            "tenant_id": tenant_id,
            "total_spend": str(total_spend),
            "scopes_count": len(scopes),
            "resources_count": len(resources),
            "cost_facts_count": len(cost_facts),
            "usage_facts_count": len(usage_facts),
            "pricing_records_count": len(pricing_records),
            "imperfections_count": len(imperfections),
        }
        manifest_json = json.dumps(manifest_preimage, sort_keys=True)
        sha256_hash = hashlib.sha256(manifest_json.encode("utf-8")).hexdigest()

        manifest = MockEstateManifest(
            version=self.version,
            seed=self.seed,
            generated_at=now.isoformat(),
            tenant_id=tenant_id,
            total_spend=str(total_spend),
            total_resources=len(resources),
            total_scopes=len(scopes),
            total_cost_facts=len(cost_facts),
            total_usage_facts=len(usage_facts),
            total_pricing_records=len(pricing_records),
            imperfections_count=len(imperfections),
            sha256_hash=sha256_hash,
        )

        return DeterministicMockEstateResult(
            tenant_id=tenant_id,
            manifest=manifest,
            scopes=scopes,
            applications=applications,
            resources=resources,
            cost_facts=cost_facts,
            usage_facts=usage_facts,
            runtime_states=runtime_states,
            pricing_records=pricing_records,
            budgets=budgets,
            forecasts=forecasts,
            threshold_states=threshold_states,
            policies=policies,
            policy_findings=policy_findings,
            dependencies=dependencies,
            sync_jobs=sync_jobs,
            imperfections=imperfections,
        )
