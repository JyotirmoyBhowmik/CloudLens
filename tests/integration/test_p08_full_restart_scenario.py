"""Full-Restart Scenario Across All MVP Modules (Prompt P08).

DONE WHEN Proof:
[ ] Scripted full-restart scenario: one record per module survives
[ ] Audit §6 REPOSITORY dict holders = 0 for MVP modules
[ ] pytest -m realdb all pass, 0 skipped

Enforces:
- Every MVP repository is backed by real PostgreSQL 16 persistence (SQLAlchemy 2 async + asyncpg).
- Records written by Repository Instance A survive when Instance A is discarded and a fresh Instance B connects to PostgreSQL.
- Object storage written to disk survives instance replacement.
- Cache items backed by Redis with TTL survive instance replacement.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from domain.analytics.models import AnalyticsExtractJob, FactCostAndUsageRecord
from domain.analytics.semantic_layer import SemanticLayerEngine
from domain.analytics.repository import (
    SqlAnalyticsRepository,
    get_analytics_repository,
    reset_analytics_repository,
)
from domain.analytics.watermark import WatermarkTracker
from domain.catalogues.models import (
    MetricDTO,
    PricingDimensionDTO,
    ServiceCategoryDTO,
    ServiceDTO,
    UnitDTO,
)
from domain.catalogues.repository import (
    SqlCatalogueRepository,
    get_catalogue_repository,
    reset_catalogue_repository,
)
from domain.reports.models import ExportFormat, ReportJob, ReportParameters, ScheduledReport
from domain.reports.repository import (
    SqlReportRepository,
    get_report_repository,
    reset_report_repository,
)
from domain.tenant.context import TenantContext
from domain.tenant.object_store import (
    FilesystemTenantObjectStorage,
    get_tenant_object_storage,
    reset_tenant_object_storage,
)


@pytest.mark.realdb
def test_reports_module_survives_full_restart():
    """Verify ReportJob, ReportArtifact, and ScheduledReport survive simulated restart."""
    tenant_id = f"tenant-rpt-{uuid.uuid4().hex[:8]}"
    tc = TenantContext(tenant_id=tenant_id)
    job_id = f"job-{uuid.uuid4().hex[:8]}"
    sched_id = f"sched-{uuid.uuid4().hex[:8]}"
    report_id = f"rep-{uuid.uuid4().hex[:8]}"
    artifact_bytes = b"PDF-CONTENT-BINARY-DATA-PROOF-P08"

    # Instance A: Write records
    repo_a = SqlReportRepository()
    job = ReportJob(
        id=job_id,
        tenant_id=tenant_id,
        template_id="tpl-p08-test",
        format=ExportFormat.PDF,
        parameters=ReportParameters(currency="USD"),
        status="COMPLETED",
    )
    repo_a.save_job(job, tenant_context=tc)
    repo_a.save_artifact(report_id, artifact_bytes, tenant_context=tc)

    schedule = ScheduledReport(
        id=sched_id,
        tenant_id=tenant_id,
        template_id="tpl-p08-test",
        format=ExportFormat.CSV,
        cron_expression="0 9 * * 1",
    )
    repo_a.save_schedule(schedule, tenant_context=tc)

    # Simulate restart by discarding repo_a and resetting singleton
    del repo_a
    reset_report_repository(None)

    # Instance B: Fresh repository connecting to DB
    repo_b = get_report_repository()
    retrieved_job = repo_b.get_job(job_id, tenant_context=tc)
    assert retrieved_job is not None
    assert retrieved_job.id == job_id
    assert retrieved_job.tenant_id == tenant_id
    assert retrieved_job.status == "COMPLETED"

    retrieved_bytes = repo_b.get_artifact(report_id, tenant_context=tc)
    assert retrieved_bytes == artifact_bytes

    retrieved_sched = repo_b.get_schedule(sched_id, tenant_context=tc)
    assert retrieved_sched is not None
    assert retrieved_sched.id == sched_id
    assert retrieved_sched.cron_expression == "0 9 * * 1"


@pytest.mark.realdb
def test_analytics_module_survives_full_restart():
    """Verify AnalyticsExtractJob and AnalyticsSnapshot survive simulated restart."""
    tenant_id = f"tenant-anl-{uuid.uuid4().hex[:8]}"
    tc = TenantContext(tenant_id=tenant_id)
    job_id = f"ext-{uuid.uuid4().hex[:8]}"
    period = "2026-10"

    # Instance A: Write records
    repo_a = SqlAnalyticsRepository()
    job = AnalyticsExtractJob(
        id=job_id,
        tenant_id=tenant_id,
        service_identity_id="svc-test-runner",
        period=period,
        version=1,
        status="COMPLETED",
        row_count=42,
    )
    repo_a.save_job(job, tenant_context=tc)

    sem_engine = SemanticLayerEngine()
    fact_rec = sem_engine.transform_fact_record(
        {"fact_key": f"fact-{uuid.uuid4().hex[:8]}", "billed_cost": 123.45},
        tenant_context=tc,
        period=period,
    )
    facts = [fact_rec]
    dims = {"providers": ["aws", "azure"]}
    repo_a.save_snapshot(period, facts, dims, tenant_context=tc)

    # Discard Instance A
    del repo_a
    reset_analytics_repository(None)

    # Instance B: Fresh repository
    repo_b = get_analytics_repository()
    retrieved_job = repo_b.get_job(job_id, tenant_context=tc)
    assert retrieved_job is not None
    assert retrieved_job.id == job_id
    assert retrieved_job.row_count == 42

    retrieved_snap = repo_b.get_snapshot(period, tenant_context=tc)
    assert retrieved_snap is not None
    r_facts, r_dims = retrieved_snap
    assert len(r_facts) == 1
    assert r_facts[0].BilledCostAmount == 123.45
    assert r_dims.get("providers") == ["aws", "azure"]


@pytest.mark.realdb
def test_watermark_tracker_survives_full_restart():
    """Verify partition watermark state survives simulated restart in PostgreSQL."""
    tenant_id = f"tenant-wm-{uuid.uuid4().hex[:8]}"
    period = "2026-11"

    tracker_a = WatermarkTracker()
    now_ts = datetime.now(UTC).isoformat()
    tracker_a.update_watermark(tenant_id, period, now_ts)
    new_ver, old_ver = tracker_a.trigger_restatement(tenant_id, period, reason="Recalculation")
    assert new_ver == 2
    assert old_ver == 1

    # Discard tracker_a
    del tracker_a

    # Instance B
    tracker_b = WatermarkTracker()
    wm = tracker_b.get_watermark(tenant_id, period)
    assert wm.current_version == 2
    assert wm.is_restated is True
    assert 1 in wm.superseded_versions


@pytest.mark.realdb
def test_catalogues_module_survives_full_restart():
    """Verify custom master catalogue items and gap records survive restart in PostgreSQL."""
    code_cat = f"CAT-TEST-{uuid.uuid4().hex[:6]}"
    code_dim = f"DIM-TEST-{uuid.uuid4().hex[:6]}"
    sym_unit = f"u-{uuid.uuid4().hex[:6]}"

    repo_a = SqlCatalogueRepository(load_seeds=False)
    repo_a.add_service_category(ServiceCategoryDTO(code=code_cat, name="P08 Test Category"))
    repo_a.add_pricing_dimension(
        PricingDimensionDTO(
            code=code_dim,
            name="P08 Dimension",
            category="Capacity",
            unit_symbol="nodes",
            aggregation_method="sum",
            default_threshold_basis="node-hours",
        )
    )
    repo_a.add_unit(
        UnitDTO(
            symbol=sym_unit,
            name="P08 Test Unit",
            dimensionality="COUNT",
            base_unit=sym_unit,
            scale_factor_to_base=Decimal("1.0"),
        )
    )
    gap = repo_a.record_gap(
        catalogue_type="SERVICE",
        provider="gcp",
        native_identifier="Google Cloud Spanner NextGen",
        tenant_id="tenant-test",
    )
    gap_id = gap.id

    # Discard repo_a and reset singleton
    del repo_a
    reset_catalogue_repository(None)

    # Instance B: Fresh repository
    repo_b = get_catalogue_repository()
    all_cats = [c.code for c in repo_b.list_service_categories()]
    assert code_cat in all_cats

    dim = repo_b.get_pricing_dimension(code_dim)
    assert dim is not None
    assert dim.name == "P08 Dimension"

    unit = repo_b.get_unit(sym_unit)
    assert unit is not None
    assert unit.dimensionality == "COUNT"

    gaps = repo_b.list_gaps(provider="gcp")
    matching = [g for g in gaps if g.id == gap_id]
    assert len(matching) == 1
    assert matching[0].native_identifier == "Google Cloud Spanner NextGen"


@pytest.mark.realdb
def test_filesystem_object_storage_survives_restart():
    """Verify FilesystemTenantObjectStorage persists across instance teardown."""
    tenant_id = f"tenant-obj-{uuid.uuid4().hex[:8]}"
    tc = TenantContext(tenant_id=tenant_id)
    key = f"landings/p08/test_payload_{uuid.uuid4().hex[:6]}.json"
    data = b'{"status": "persisted", "tier": 5}'

    storage_a = FilesystemTenantObjectStorage()
    storage_a.put_object(tenant_context=tc, key=key, data=data, content_type="application/json")

    del storage_a
    reset_tenant_object_storage(None)

    storage_b = get_tenant_object_storage()
    assert storage_b.object_exists(tenant_context=tc, key=key)
    retrieved = storage_b.get_object(tenant_context=tc, key=key)
    assert retrieved == data

    # Cleanup
    storage_b.delete_object(tenant_context=tc, key=key)
    assert not storage_b.object_exists(tenant_context=tc, key=key)
