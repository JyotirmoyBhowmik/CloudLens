"""Comprehensive Unit and Integration Tests for Analytics Export, BI Feed & Semantic Layer (Prompt 56).

Enforces:
1. Star-schema semantic layer with FactCostAndUsage at the center and 16 conformed dimensions.
2. 100% business-friendly naming across all dimension columns and fact measures.
3. Pre-computed derived measures (billed, effective, list, contracted, realised discount,
   budget, variance, utilisation, forecast, unallocated, allocated, estimated, reconciliation variance).
4. Four-state null discipline (ZERO/NO_COST, NO_DATA, NOT_APPLICABLE, NOT_SUPPORTED) without flattening.
5. Scheduled FOCUS-format partitioned extracts with versioned schemas (Parquet & CSV).
6. Incremental extract with watermark and unambiguous restatement supersession.
7. Scope-bound extract identity with verifiable cryptographic manifest.
8. Rate-limited read-only analytical access path strictly isolated from transactional OLTP.
9. Observability alerting for late or empty extracts.
10. Reference monthly cost pack and FOCUS mapping table.
11. REST API endpoints integration.
"""

from __future__ import annotations

import datetime as dt
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq
import pytest
from fastapi.testclient import TestClient

from api.cloudlens_api.main import app
from domain.analytics.data_dictionary import get_semantic_data_dictionary
from domain.analytics.extract_engine import AnalyticsExtractEngine
from domain.analytics.models import (
    AnalyticalQueryRequest,
    FactCostAndUsageRecord,
    SemanticDataQualityNullState,
)
from domain.analytics.query_engine import AnalyticsQueryEngine
from domain.analytics.semantic_layer import SemanticLayerEngine
from domain.analytics.service import (
    AnalyticsService,
    get_analytics_service,
    reset_analytics_service,
)
from domain.audit.models import AuditEventFilter
from domain.audit.service import get_audit_service
from domain.models.enums import AuditEventType
from domain.models.exceptions import (
    AnalyticsRateLimitExceededException,
    LateExtractException,
    TransactionalPathAccessForbiddenException,
)
from domain.tenant.context import TenantContext


@pytest.fixture(autouse=True)
def clean_singletons():
    """Resets service singletons before each test."""
    reset_analytics_service()


@pytest.fixture
def temp_export_dir():
    """Provides a temporary filesystem location for extract artifacts."""
    tmp = tempfile.mkdtemp(prefix="cloudlens_analytics_")
    yield Path(tmp)
    shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture
def tenant_admin_context() -> TenantContext:
    return TenantContext(
        tenant_id="tenant-corp",
        user_id="usr-cfo-01",
        email="cfo@tenantcorp.com",
        roles=["GLOBAL_ADMIN"],
        correlation_id="corr-analytics-01",
        is_superuser=True,
    )


@pytest.fixture
def scope_restricted_context() -> TenantContext:
    return TenantContext(
        tenant_id="tenant-corp",
        user_id="usr-retail-lead",
        email="retail-lead@tenantcorp.com",
        roles=["SCOPE:scp-retail-prod"],
        correlation_id="corr-analytics-02",
        is_superuser=False,
    )


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# ==============================================================================
# 1. Conformed Star Schema & Business-Friendly Naming
# ==============================================================================


def test_semantic_layer_generates_all_16_conformed_dimensions(tenant_admin_context: TenantContext):
    """Verify SemanticLayerEngine generates all 16 conformed dimensions with business-friendly naming."""
    engine = SemanticLayerEngine()
    facts, dimensions, filtered, disclosure = engine.generate_star_schema_dataset(
        raw_rows=[],
        tenant_context=tenant_admin_context,
        period="2026-09",
    )
    _ = (facts, filtered, disclosure)

    expected_dimensions = [
        "DimDate",
        "DimScope",
        "DimProvider",
        "DimService",
        "DimResource",
        "DimApplication",
        "DimEnvironment",
        "DimOwner",
        "DimCostCentre",
        "DimBusinessUnit",
        "DimProject",
        "DimRegion",
        "DimTag",
        "DimPricing",
        "DimCommitment",
        "DimChargeCategory",
    ]

    for dim in expected_dimensions:
        assert dim in dimensions, f"Missing required conformed dimension: {dim}"
        assert len(dimensions[dim]) > 0, f"Dimension {dim} should contain records."

    # Validate business-friendly naming on DimDate
    date_rec = dimensions["DimDate"][0]
    assert hasattr(date_rec, "FiscalPeriod")
    assert hasattr(date_rec, "FiscalYear")
    assert hasattr(date_rec, "IsWorkingDay")

    # Validate business-friendly naming on DimBusinessUnit
    bu_rec = dimensions["DimBusinessUnit"][0]
    assert hasattr(bu_rec, "BusinessUnitName")
    assert hasattr(bu_rec, "DivisionName")


# ==============================================================================
# 2. Pre-Computed Derived Measures Verification
# ==============================================================================


def test_all_13_derived_measures_precomputed_once(tenant_admin_context: TenantContext):
    """Verify that all 13 derived measures are computed in the semantic layer without BI recalculation."""
    engine = SemanticLayerEngine()
    raw_fact = {
        "fact_key": "fct-test-01",
        "scope_key": "scp-retail-prod",
        "provider_key": "AWS",
        "service_key": "srv-ec2",
        "billed_cost": 1000.00,
        "effective_cost": 850.00,
        "list_cost": 1200.00,
        "contracted_cost": 1100.00,
        "budget_amount": 900.00,
        "forecast_amount": 1050.00,
        "estimated_cost": 980.00,
        "reconciliation_variance": 0.00,
        "usage_quantity": 720.0,
    }

    fact = engine.transform_fact_record(raw_fact, tenant_admin_context, period="2026-09")

    # 1. Billed
    assert fact.BilledCostAmount == 1000.00
    # 2. Effective
    assert fact.EffectiveCostAmount == 850.00
    # 3. List
    assert fact.ListCostAmount == 1200.00
    # 4. Contracted
    assert fact.ContractedCostAmount == 1100.00
    # 5. Realised Discount = List - Effective
    assert fact.RealisedDiscountAmount == 350.00
    # 6. Budget
    assert fact.BudgetAmount == 900.00
    # 7. Variance = Billed - Budget
    assert fact.BudgetVarianceAmount == 100.00
    # 8. Utilisation = (Billed / Budget) * 100
    assert fact.BudgetUtilisationPercentage == 111.11
    # 9. Spend Forecast
    assert fact.SpendForecastAmount == 1050.00
    # 10 & 11. Allocated & Unallocated
    assert fact.AllocatedCostAmount == 1000.00
    assert fact.UnallocatedCostAmount == 0.00
    # 12. Estimated
    assert fact.EstimatedCostAmount == 980.00
    # 13. Reconciliation Variance
    assert fact.ReconciliationVarianceAmount == 0.00
    assert fact.UsageQuantity == 720.0


# ==============================================================================
# 3. Four-State Null Discipline Preservation
# ==============================================================================


def test_four_state_null_discipline_preserved_without_flattening(
    tenant_admin_context: TenantContext,
):
    """Verify four null states (ZERO, NO_DATA, NOT_APPLICABLE, NOT_SUPPORTED) remain distinguishable from 0."""
    engine = SemanticLayerEngine()

    # Case A: Genuine Verified Zero
    fact_zero = engine.transform_fact_record(
        {"billed_cost": 0.00, "is_zero_cost": True, "billed_null_state": "ZERO"},
        tenant_admin_context,
        period="2026-09",
    )
    assert fact_zero.BilledCostAmount == 0.00
    assert fact_zero.BilledCostNullState == SemanticDataQualityNullState.ZERO

    # Case B: Missing Ingestion (NO_DATA)
    fact_nodata = engine.transform_fact_record(
        {"billed_cost": None, "billed_null_state": "NO_DATA"},
        tenant_admin_context,
        period="2026-09",
    )
    assert fact_nodata.BilledCostNullState == SemanticDataQualityNullState.NO_DATA

    # Case C: Inapplicable Metric (NOT_APPLICABLE)
    fact_na = engine.transform_fact_record(
        {"billed_cost": 50.0, "billed_null_state": "NOT_APPLICABLE"},
        tenant_admin_context,
        period="2026-09",
    )
    assert fact_na.BilledCostNullState == SemanticDataQualityNullState.NOT_APPLICABLE

    # Case D: Provider Unsupported (NOT_SUPPORTED)
    fact_ns = engine.transform_fact_record(
        {"billed_cost": 100.0, "billed_null_state": "NOT_SUPPORTED"},
        tenant_admin_context,
        period="2026-09",
    )
    assert fact_ns.BilledCostNullState == SemanticDataQualityNullState.NOT_SUPPORTED

    # Ensure ZERO is strictly distinct from NO_DATA
    assert fact_zero.BilledCostNullState != fact_nodata.BilledCostNullState


# ==============================================================================
# 4. Partitioned Parquet / Columnar Extract & Schema Versioning
# ==============================================================================


def test_scheduled_focus_format_partitioned_parquet_extract(
    tenant_admin_context: TenantContext, temp_export_dir: Path
):
    """Verify FOCUS-format partitioned extract writes valid Parquet files with stamped schema version."""
    engine = AnalyticsExtractEngine(base_storage_path=temp_export_dir)

    job, manifest = engine.generate_extract(
        period="2026-09",
        service_identity_id="svc-bi-tableau",
        service_identity_name="Tableau Enterprise Ingestion",
        scope_grants=["*"],
        tenant_context=tenant_admin_context,
    )

    assert job.status == "COMPLETED"
    assert job.row_count > 0
    assert manifest.schema_version == "1.0.0"
    assert manifest.period == "2026-09"
    assert manifest.version == 1

    dest_dir = Path(job.storage_destination)
    assert dest_dir.exists()

    # 1. Verify Parquet files exist
    fact_parquet = dest_dir / "fact_cost_and_usage.parquet"
    focus_parquet = dest_dir / "focus_cost_and_usage.parquet"
    assert fact_parquet.exists()
    assert focus_parquet.exists()

    # 2. Read and validate Parquet schema metadata
    table = pq.read_table(fact_parquet)
    assert b"schema_version" in table.schema.metadata
    assert table.schema.metadata[b"schema_version"] == b"1.0.0"
    assert len(table) == job.row_count

    # 3. Read and validate FOCUS dataset columns
    focus_table = pq.read_table(focus_parquet)
    cols = focus_table.column_names
    assert "BilledCost" in cols
    assert "EffectiveCost" in cols
    assert "ProviderName" in cols
    assert "ServiceName" in cols
    assert "ResourceId" in cols
    assert "ChargeCategory" in cols

    # 4. Verify Dimension CSVs exist
    assert (dest_dir / "dim_business_unit.csv").exists()
    assert (dest_dir / "dim_date.csv").exists()
    assert (dest_dir / "dim_provider.csv").exists()

    # 5. Verify Manifest
    manifest_file = dest_dir / "manifest.json"
    assert manifest_file.exists()
    saved_manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    assert saved_manifest["extract_id"] == manifest.extract_id
    assert "fact_cost_and_usage.parquet" in saved_manifest["file_checksums"]


# ==============================================================================
# 5. Incremental Watermark & Restatement Supersession
# ==============================================================================


def test_incremental_watermark_and_restatement_reemission(
    tenant_admin_context: TenantContext, temp_export_dir: Path
):
    """Verify restated period is re-emitted in full with version bump and unambiguous supersession."""
    engine = AnalyticsExtractEngine(base_storage_path=temp_export_dir)

    # 1. Initial Extract (Version 1)
    job_v1, manifest_v1 = engine.generate_extract(
        period="2026-09",
        service_identity_id="svc-finance",
        service_identity_name="Finance ETL",
        scope_grants=["*"],
        tenant_context=tenant_admin_context,
        is_restatement=False,
    )
    assert job_v1.version == 1
    assert manifest_v1.supersedes_version is None

    # 2. Restatement Trigger (Version 2 supersedes Version 1)
    job_v2, manifest_v2 = engine.generate_extract(
        period="2026-09",
        service_identity_id="svc-finance",
        service_identity_name="Finance ETL",
        scope_grants=["*"],
        tenant_context=tenant_admin_context,
        is_restatement=True,
    )
    assert job_v2.version == 2
    assert manifest_v2.version == 2
    assert manifest_v2.supersedes_version == 1
    assert manifest_v2.governance_context["is_restated"] is True
    assert (
        "Higher version number unconditionally supersedes earlier versions"
        in manifest_v2.supersession_policy
    )


# ==============================================================================
# 6. Scope-Bound Extract Identity & Manifest Verification
# ==============================================================================


def test_scope_bound_extract_identity_with_manifest(
    scope_restricted_context: TenantContext, temp_export_dir: Path
):
    """Verify that extract generated under scope-restricted identity carries proof in manifest."""
    engine = AnalyticsExtractEngine(base_storage_path=temp_export_dir)

    job, manifest = engine.generate_extract(
        period="2026-09",
        service_identity_id="svc-retail-app",
        service_identity_name="Retail Team Downstream BI",
        scope_grants=["SCOPE:scp-retail-prod"],
        tenant_context=scope_restricted_context,
    )

    assert job.status == "COMPLETED"
    assert manifest.access_filtering_occurred is True
    assert manifest.filtering_disclosure is not None
    assert (
        "Data filtered according to service identity scope grants" in manifest.filtering_disclosure
    )
    assert manifest.scope_grants == ["SCOPE:scp-retail-prod"]

    # Verify extracted fact records only contain authorized scope
    dest_dir = Path(job.storage_destination)
    table = pq.read_table(dest_dir / "fact_cost_and_usage.parquet")
    for row in table.to_pylist():
        assert row["ScopeKey"] == "scp-retail-prod"


# ==============================================================================
# 7. Isolated Read-Only Analytical Query Path & OLTP Prohibition
# ==============================================================================


def test_isolated_query_path_aggregates_without_oltp_database(
    tenant_admin_context: TenantContext,
):
    """Verify BI tool can query Cost-by-Business-Unit from the semantic layer without DB access."""
    service = get_analytics_service()

    req = AnalyticalQueryRequest(
        dimensions=["BusinessUnitName"],
        measures=["BilledCostAmount", "RealisedDiscountAmount", "BudgetAmount"],
        period="2026-09",
    )

    res = service.execute_query(req, tenant_context=tenant_admin_context)
    assert res.total_rows >= 0
    assert "BusinessUnitName" in res.columns
    assert "BilledCostAmount" in res.columns
    assert res.isolation_mode == "ISOLATED_ANALYTICAL_REPLICA"

    for r in res.rows:
        assert "BusinessUnitName" in r
        assert float(r["BilledCostAmount"]) >= 0.0


def test_analytical_query_raises_when_touching_transactional_path(
    tenant_admin_context: TenantContext,
):
    """Verify hard rule: Analytical queries strictly prohibited from using transactional connection."""
    service = get_analytics_service()
    req = AnalyticalQueryRequest(dimensions=["BusinessUnitName"])

    with pytest.raises(TransactionalPathAccessForbiddenException):
        service.execute_query(
            req,
            tenant_context=tenant_admin_context,
            oltp_connection={"fake_db_session": "active"},
        )


def test_analytical_query_rate_limiting(tenant_admin_context: TenantContext):
    """Verify analytical queries enforce per-tenant rate limiting."""
    engine = AnalyticsQueryEngine(max_queries_per_minute=2)
    req = AnalyticalQueryRequest()
    facts: list[FactCostAndUsageRecord] = []
    dims: dict[str, list[Any]] = {}

    # First 2 queries succeed
    engine.execute_query(req, facts=facts, dimensions=dims, tenant_context=tenant_admin_context)
    engine.execute_query(req, facts=facts, dimensions=dims, tenant_context=tenant_admin_context)

    # 3rd query exceeds rate limit
    with pytest.raises(AnalyticsRateLimitExceededException):
        engine.execute_query(req, facts=facts, dimensions=dims, tenant_context=tenant_admin_context)


# ==============================================================================
# 8. Observability: Lateness & Emptiness Alerting
# ==============================================================================


def test_empty_extract_raises_alert_and_records_audit(
    tenant_admin_context: TenantContext, temp_export_dir: Path
):
    """Verify an extract resulting in 0 records raises an alert and records an audit event."""
    service = AnalyticsService(
        extract_engine=AnalyticsExtractEngine(base_storage_path=temp_export_dir)
    )
    audit_svc = get_audit_service()

    job, manifest = service.run_extract(
        period="2026-09",
        service_identity_id="svc-empty-test",
        service_identity_name="Empty Extract Tester",
        scope_grants=["*"],
        tenant_context=tenant_admin_context,
        raw_facts=[],  # Empty facts
    )
    _ = (job, manifest)

    events = audit_svc.list_events(
        tenant_context=tenant_admin_context,
        filter_params=AuditEventFilter(
            event_type=AuditEventType.ANALYTICAL_EXTRACT_LATE_OR_EMPTY_ALERT_DISPATCHED
        ),
    )
    assert len(events) > 0
    assert events[0].details["reason"] == "EXTRACT_EMPTY"


def test_late_extract_raises_alert(tenant_admin_context: TenantContext):
    """Verify an extract missing its SLA window raises a late extract alert."""
    service = get_analytics_service()
    scheduled_time = dt.datetime.now(dt.UTC) - dt.timedelta(hours=3)

    is_late = service.check_extract_sla(
        schedule_id="sch-daily-0800",
        scheduled_for=scheduled_time,
        actual_completion=None,
        sla_window_minutes=60.0,
        tenant_context=tenant_admin_context,
    )
    assert is_late is True

    # If raise_on_violation=True, raises LateExtractException
    with pytest.raises(LateExtractException):
        service.check_extract_sla(
            schedule_id="sch-daily-0800",
            scheduled_for=scheduled_time,
            actual_completion=None,
            sla_window_minutes=60.0,
            tenant_context=tenant_admin_context,
            raise_on_violation=True,
        )


# ==============================================================================
# 9. Reference Artefacts & Data Dictionary
# ==============================================================================


def test_reference_monthly_cost_pack_generated(tenant_admin_context: TenantContext):
    """Verify reference monthly cost pack provides executive summary and BU breakdown."""
    service = get_analytics_service()
    pack = service.get_reference_monthly_cost_pack(tenant_context=tenant_admin_context)

    assert "executive_summary" in pack
    assert "spend_by_business_unit" in pack
    assert "spend_by_provider" in pack
    assert pack["executive_summary"]["total_billed_cost"] >= 0.0


def test_semantic_to_focus_mapping_table():
    """Verify mapping table covers all primary FOCUS columns."""
    service = get_analytics_service()
    mappings = service.get_semantic_to_focus_mapping()
    assert len(mappings) >= 10
    focus_cols = {m["FocusColumn"] for m in mappings}
    assert "BilledCost" in focus_cols
    assert "EffectiveCost" in focus_cols
    assert "ProviderName" in focus_cols


def test_published_data_dictionary():
    """Verify data dictionary registers tables, descriptions, and formulas."""
    entries = get_semantic_data_dictionary()
    assert len(entries) >= 20
    col_names = {e.ColumnName for e in entries}
    assert "BilledCostAmount" in col_names
    assert "EffectiveCostAmount" in col_names
    assert "RealisedDiscountAmount" in col_names


# ==============================================================================
# 10. REST API Endpoints Integration
# ==============================================================================


def test_api_analytics_extract_and_query_flow(client: TestClient):
    """Verify REST API endpoints for analytical extracts, manifests, and queries."""
    headers = {"X-Tenant-ID": "test-corp", "X-User-ID": "usr-admin"}

    # 1. Trigger Extract
    extract_payload = {
        "period": "2026-09",
        "service_identity_id": "svc-powerbi",
        "service_identity_name": "Corporate PowerBI Service",
        "scope_grants": ["*"],
    }
    post_res = client.post("/api/v1/analytics/extracts", json=extract_payload, headers=headers)
    assert post_res.status_code == 202
    job_data = post_res.json()
    extract_id = job_data["id"]

    # 2. Get Extract Manifest
    mani_res = client.get(f"/api/v1/analytics/extracts/{extract_id}/manifest", headers=headers)
    assert mani_res.status_code == 200
    manifest_data = mani_res.json()
    assert manifest_data["schema_version"] == "1.0.0"
    assert manifest_data["extract_id"] == extract_id

    # 3. Query Semantic Layer
    query_payload = {
        "dimensions": ["BusinessUnitName"],
        "measures": ["BilledCostAmount"],
        "period": "2026-09",
    }
    q_res = client.post("/api/v1/analytics/query", json=query_payload, headers=headers)
    assert q_res.status_code == 200
    q_data = q_res.json()
    assert "rows" in q_data
    assert q_data["isolation_mode"] == "ISOLATED_ANALYTICAL_REPLICA"

    # 4. Get Data Dictionary
    dict_res = client.get("/api/v1/analytics/dictionary", headers=headers)
    assert dict_res.status_code == 200
    assert len(dict_res.json()) >= 20

    # 5. Get Reference Cost Pack
    pack_res = client.get("/api/v1/analytics/reference/cost-pack", headers=headers)
    assert pack_res.status_code == 200
    assert "executive_summary" in pack_res.json()

    # 6. Get FOCUS Mapping
    focus_res = client.get("/api/v1/analytics/reference/focus-mapping", headers=headers)
    assert focus_res.status_code == 200
    assert len(focus_res.json()) >= 10
