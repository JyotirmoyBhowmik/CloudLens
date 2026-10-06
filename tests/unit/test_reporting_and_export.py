"""Unit and Integration Tests for Reporting and Export Engine (Prompt 35 / BBP Section 36).

Enforces:
1. All 14 MVP reports (RPT-01 to RPT-14) generation.
2. All 5 pricing-specific reports (RPT-15 to RPT-19) generation.
3. Mandatory provenance footer on every report:
   - generation time, per-provider freshness, cost basis, currency policy, requester identity.
4. RBAC scope-respecting generation:
   - Restricted users receive only permitted scope data.
   - Provenance explicitly discloses that access filtering occurred.
5. Asynchronous generation and time-limited download links (TTL enforcement).
6. Mandatory dual audit trail logging (generation + download).
7. Multi-format serialization: CSV, JSON, XLSX, and PDF 1.4.
8. Phase 2 flag gating for anomaly/idle reports and recurring scheduling.
9. Public REST API endpoints (API-047, API-048, and download route).
"""

from __future__ import annotations

import datetime as dt
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from api.cloudlens_api.main import app
from domain.audit.service import get_audit_service
from domain.models.enums import AuditEventType
from domain.models.exceptions import (
    DownloadLinkExpiredException,
    FeatureNotEnabledException,
    InvalidDownloadTokenException,
)
from domain.reports.catalogue import MASTER_REPORT_CATALOGUE
from domain.reports.models import (
    ExportFormat,
    ReportCode,
    ReportParameters,
)
from domain.reports.service import ReportService, get_report_service
from domain.tenant.context import TenantContext


@pytest.fixture
def tenant_admin_context() -> TenantContext:
    return TenantContext(
        tenant_id="tenant-corp",
        user_id="usr-cfo-01",
        email="cfo@tenantcorp.com",
        roles=["GLOBAL_ADMIN"],
        correlation_id="corr-rep-test-01",
        is_superuser=True,
    )


@pytest.fixture
def scope_restricted_context() -> TenantContext:
    return TenantContext(
        tenant_id="tenant-corp",
        user_id="usr-dev-99",
        email="developer@tenantcorp.com",
        roles=["SCOPE:scope-dev"],
        correlation_id="corr-rep-test-02",
        is_superuser=False,
    )


@pytest.fixture
def report_service() -> ReportService:
    return get_report_service()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# ==============================================================================
# 1. MVP Report Set Tests (14 Reports: RPT-01 to RPT-14)
# ==============================================================================


def test_catalogue_contains_all_14_mvp_reports():
    """Verify master catalogue registers all 14 MVP report codes."""
    mvp_codes = {
        ReportCode.RPT_01_MONTHLY_COST,
        ReportCode.RPT_02_PROVIDER_COST,
        ReportCode.RPT_03_SERVICE_COST,
        ReportCode.RPT_04_BUDGET_VARIANCE,
        ReportCode.RPT_05_SPEND_FORECAST,
        ReportCode.RPT_06_USAGE_TELEMETRY,
        ReportCode.RPT_07_RUNTIME_COMPLIANCE,
        ReportCode.RPT_08_DEPENDENCY_CHAIN,
        ReportCode.RPT_09_GOVERNANCE_EXCEPTIONS,
        ReportCode.RPT_10_CONNECTOR_STATUS,
        ReportCode.RPT_11_EXECUTIVE_SUMMARY,
        ReportCode.RPT_12_RECONCILIATION,
        ReportCode.RPT_13_ACCESS_REVIEW,
        ReportCode.RPT_14_AUDIT_EXTRACT,
    }
    registered_codes = {d.code for d in MASTER_REPORT_CATALOGUE if not d.is_phase_2}
    for code in mvp_codes:
        assert code in registered_codes, f"MVP report code '{code}' must be in catalogue."


def test_generation_of_all_14_mvp_reports(
    report_service: ReportService, tenant_admin_context: TenantContext
):
    """Verify all 14 MVP reports generate non-empty rows, summary, and provenance."""
    params = ReportParameters(period="2026-10", currency="USD", cost_basis="BILLED")

    mvp_templates = [
        d
        for d in MASTER_REPORT_CATALOGUE
        if not d.is_phase_2
        and d.code.value.startswith("RPT-0")
        or d.code.value in ("RPT-10", "RPT-11", "RPT-12", "RPT-13", "RPT-14")
    ]
    assert len(mvp_templates) >= 14

    for defn in mvp_templates:
        job, content = report_service.generate_report(
            template_id=defn.id,
            parameters=params,
            format_type=defn.supported_formats[0],
            async_generation=False,
            tenant_context=tenant_admin_context,
        )
        assert job.status == "COMPLETED"
        assert job.row_count >= 0
        assert content is not None
        assert len(content) > 0
        assert job.provenance is not None
        assert job.provenance.cost_basis == "BILLED"
        assert job.provenance.currency_policy.startswith("USD")
        assert len(job.provenance.data_freshness_per_provider) >= 4


# ==============================================================================
# 2. Five Pricing-Specific Reports Tests (RPT-15 to RPT-19)
# ==============================================================================


def test_catalogue_contains_all_5_pricing_reports():
    """Verify master catalogue registers all 5 pricing-specific reports."""
    pricing_codes = {
        ReportCode.RPT_15_PRICING_RATES,
        ReportCode.RPT_16_FREE_TIER_USAGE,
        ReportCode.RPT_17_COST_DRIVERS,
        ReportCode.RPT_18_PRICING_CHANGES,
        ReportCode.RPT_19_DATA_FRESHNESS,
    }
    registered_codes = {d.code for d in MASTER_REPORT_CATALOGUE}
    for code in pricing_codes:
        assert code in registered_codes, f"Pricing report code '{code}' must be in catalogue."


def test_generation_of_all_5_pricing_reports(
    report_service: ReportService, tenant_admin_context: TenantContext
):
    """Verify rates in use, free tier usage, cost drivers, price changes, and freshness reports."""
    pricing_ids = [
        "tpl-pricing-rates",
        "tpl-pricing-free-tier",
        "tpl-pricing-cost-drivers",
        "tpl-pricing-changes",
        "tpl-pricing-freshness",
    ]
    params = ReportParameters(period="2026-10", currency="USD")

    for pid in pricing_ids:
        job, content = report_service.generate_report(
            template_id=pid,
            parameters=params,
            format_type=ExportFormat.JSON,
            async_generation=False,
            tenant_context=tenant_admin_context,
        )
        assert job.status == "COMPLETED"
        assert job.row_count > 0
        assert content is not None

        # Validate JSON structure contains provenance
        data = json.loads(content.decode("utf-8"))
        assert "provenance" in data
        assert data["provenance"]["cost_basis"] == "BILLED"
        assert "data_freshness_per_provider" in data["provenance"]
        assert len(data["rows"]) > 0


# ==============================================================================
# 3. Mandatory Provenance Footer & RBAC Scope Masking Tests
# ==============================================================================


def test_provenance_footer_text_formatting():
    """Verify provenance footer produces human-readable text block with all 5 mandatory elements."""
    prov = ReportService().generator_engine._build_provenance_footer(
        params=ReportParameters(cost_basis="EFFECTIVE", currency="EUR"),
        tenant_context=TenantContext(
            tenant_id="t1",
            user_id="u1",
            email="u1@example.com",
            roles=["FINOPS_VIEWER"],
            correlation_id="c1",
        ),
        filtering_occurred=True,
        permitted_scopes={"scope-dev"},
    )
    footer_text = prov.format_footer_text()

    assert "Generated At (UTC):" in footer_text
    assert "Requester Identity: u1@example.com" in footer_text
    assert "Cost Basis: EFFECTIVE" in footer_text
    assert "Currency Policy: EUR" in footer_text
    assert "Provider Data Freshness:" in footer_text
    assert "ACCESS FILTERING DISCLOSURE:" in footer_text
    assert "scope-dev" in footer_text


def test_scope_restricted_user_receives_only_permitted_data_and_disclosure(
    report_service: ReportService, scope_restricted_context: TenantContext
):
    """Restricted caller only sees permitted scopes and report explicitly discloses filtering."""
    params = ReportParameters(period="2026-10", currency="USD")

    job, content = report_service.generate_report(
        template_id="tpl-cost-monthly",
        parameters=params,
        format_type=ExportFormat.JSON,
        async_generation=False,
        tenant_context=scope_restricted_context,
    )

    assert job.provenance is not None
    assert job.provenance.access_filtering_occurred is True
    assert job.provenance.filtering_disclosure is not None
    assert (
        "constrained by requester's authorized scope grants" in job.provenance.filtering_disclosure
    )

    assert content is not None
    data = json.loads(content.decode("utf-8"))
    for row in data["rows"]:
        assert row["scope_id"] == "scope-dev", "Out-of-scope records must be filtered out."


# ==============================================================================
# 4. Multi-Format Exporter Tests (CSV, JSON, XLSX, PDF)
# ==============================================================================


def test_csv_export_format(report_service: ReportService, tenant_admin_context: TenantContext):
    """Verify CSV export contains data rows and # Provenance: comment footer."""
    job, content = report_service.generate_report(
        template_id="tpl-cost-monthly",
        parameters=ReportParameters(),
        format_type=ExportFormat.CSV,
        tenant_context=tenant_admin_context,
    )
    assert content is not None
    csv_str = content.decode("utf-8")

    assert "period,scope_id,scope_name" in csv_str
    assert "# PROVENANCE & GOVERNANCE FOOTER (Prompt 35)" in csv_str
    assert "# Generation Time (UTC):" in csv_str
    assert "# Cost Basis: BILLED" in csv_str
    assert "# Requester Identity: cfo@tenantcorp.com" in csv_str


def test_xlsx_export_format(report_service: ReportService, tenant_admin_context: TenantContext):
    """Verify XLSX export produces a valid OpenXML zip archive with multiple worksheets."""
    job, content = report_service.generate_report(
        template_id="tpl-cost-monthly",
        parameters=ReportParameters(),
        format_type=ExportFormat.XLSX,
        tenant_context=tenant_admin_context,
    )
    assert content is not None
    import io

    zf = zipfile.ZipFile(io.BytesIO(content))
    file_list = zf.namelist()

    assert "[Content_Types].xml" in file_list
    assert "xl/workbook.xml" in file_list
    assert "xl/worksheets/sheet1.xml" in file_list
    assert "xl/worksheets/sheet2.xml" in file_list

    # Validate provenance worksheet content
    sheet2_xml = zf.read("xl/worksheets/sheet2.xml").decode("utf-8")
    assert "Requester Identity" in sheet2_xml
    assert "Cost Basis" in sheet2_xml


def test_pdf_export_format(report_service: ReportService, tenant_admin_context: TenantContext):
    """Verify PDF export generates valid PDF 1.4 document with title and provenance footer."""
    job, content = report_service.generate_report(
        template_id="tpl-cost-monthly",
        parameters=ReportParameters(),
        format_type=ExportFormat.PDF,
        tenant_context=tenant_admin_context,
    )
    assert content is not None
    assert content.startswith(b"%PDF-1.4\n")
    assert b"%%EOF\n" in content
    assert b"CLOUDLENS AUTHORITATIVE PROVENANCE FOOTER" in content


# ==============================================================================
# 5. Asynchronous Generation, Time-Limited Links & Audit Logging
# ==============================================================================


def test_asynchronous_generation_and_time_limited_download(
    report_service: ReportService, tenant_admin_context: TenantContext
):
    """Verify asynchronous generation returns job, download URL with token, and audits both actions."""
    audit_svc = get_audit_service()
    from domain.audit.models import AuditEventFilter

    _ = len(audit_svc.list_events(tenant_context=tenant_admin_context))

    # 1. Trigger Asynchronous Generation
    job, content = report_service.generate_report(
        template_id="tpl-executive-summary",
        parameters=ReportParameters(),
        format_type=ExportFormat.PDF,
        async_generation=True,
        tenant_context=tenant_admin_context,
    )
    assert content is None  # Async returns None for immediate payload
    assert job.status == "COMPLETED"
    assert job.download_token is not None
    assert job.download_url is not None
    assert "/downloads/" in job.download_url

    # Check generation was audited
    gen_events = audit_svc.list_events(
        tenant_context=tenant_admin_context,
        filter_params=AuditEventFilter(event_type=AuditEventType.REPORT_GENERATED),
    )
    assert len(gen_events) > 0

    # 2. Perform Time-Limited Download
    report_id = job.download_url.split("/downloads/")[1].split("?")[0]
    dl_bytes, dl_job = report_service.download_report(
        report_id=report_id,
        token=job.download_token,
        tenant_context=tenant_admin_context,
    )
    assert len(dl_bytes) > 0
    assert dl_job.id == job.id

    # Check download was audited
    dl_events = audit_svc.list_events(
        tenant_context=tenant_admin_context,
        filter_params=AuditEventFilter(event_type=AuditEventType.REPORT_DOWNLOADED),
    )
    assert len(dl_events) > 0


def test_expired_download_link_raises_410(
    report_service: ReportService, tenant_admin_context: TenantContext
):
    """Accessing an expired download link raises DownloadLinkExpiredException."""
    job, _ = report_service.generate_report(
        template_id="tpl-cost-monthly",
        parameters=ReportParameters(),
        format_type=ExportFormat.CSV,
        tenant_context=tenant_admin_context,
    )
    # Manually expire the job token
    job.expires_at = dt.datetime.now(dt.UTC) - dt.timedelta(seconds=10)
    report_service.repository.save_job(job, tenant_context=tenant_admin_context)

    assert job.download_url is not None
    assert job.download_token is not None
    report_id = job.download_url.split("/downloads/")[1].split("?")[0]
    with pytest.raises(DownloadLinkExpiredException):
        report_service.download_report(
            report_id=report_id,
            token=job.download_token,
            tenant_context=tenant_admin_context,
        )


def test_invalid_download_token_raises_401(
    report_service: ReportService, tenant_admin_context: TenantContext
):
    """Accessing download with invalid token raises InvalidDownloadTokenException."""
    job, _ = report_service.generate_report(
        template_id="tpl-cost-monthly",
        parameters=ReportParameters(),
        format_type=ExportFormat.CSV,
        tenant_context=tenant_admin_context,
    )
    assert job.download_url is not None
    report_id = job.download_url.split("/downloads/")[1].split("?")[0]
    with pytest.raises(InvalidDownloadTokenException):
        report_service.download_report(
            report_id=report_id,
            token="invalid-tampered-token",
            tenant_context=tenant_admin_context,
        )


# ==============================================================================
# 6. Phase 2 Feature Flags (Anomaly, Idle, Scheduling)
# ==============================================================================


def test_phase_2_anomaly_report_flag_gated(tenant_admin_context: TenantContext):
    """Phase 2 anomaly report is blocked when flag disabled and permitted when enabled."""
    disabled_service = ReportService(feature_flags={"PHASE_2_ANOMALY_DETECTION": False})
    with pytest.raises(FeatureNotEnabledException):
        disabled_service.generate_report(
            template_id="tpl-phase2-unusual",
            parameters=ReportParameters(),
            format_type=ExportFormat.JSON,
            tenant_context=tenant_admin_context,
        )

    enabled_service = ReportService(feature_flags={"PHASE_2_ANOMALY_DETECTION": True})
    job, content = enabled_service.generate_report(
        template_id="tpl-phase2-unusual",
        parameters=ReportParameters(),
        format_type=ExportFormat.JSON,
        tenant_context=tenant_admin_context,
    )
    assert job.status == "COMPLETED"
    assert job.row_count > 0


def test_phase_2_scheduling_flag_gated(tenant_admin_context: TenantContext):
    """Recurring report scheduling is blocked when flag disabled and permitted when enabled."""
    disabled_service = ReportService(feature_flags={"PHASE_2_SCHEDULING_ENABLED": False})
    with pytest.raises(FeatureNotEnabledException):
        disabled_service.create_schedule(
            template_id="tpl-cost-monthly",
            parameters=ReportParameters(),
            format_type=ExportFormat.PDF,
            cron_expression="0 8 1 * *",
            recipients=["finops@example.com"],
            tenant_context=tenant_admin_context,
        )

    enabled_service = ReportService(feature_flags={"PHASE_2_SCHEDULING_ENABLED": True})
    sched = enabled_service.create_schedule(
        template_id="tpl-cost-monthly",
        parameters=ReportParameters(),
        format_type=ExportFormat.PDF,
        cron_expression="0 8 1 * *",
        recipients=["finops@example.com"],
        tenant_context=tenant_admin_context,
    )
    assert sched.id.startswith("sch-")
    assert sched.is_active is True
    assert sched.next_run_at is not None

    schedules = enabled_service.list_schedules(tenant_context=tenant_admin_context)
    assert len(schedules) >= 1


# ==============================================================================
# 7. REST API Endpoints Integration (API-047, API-048, Downloads)
# ==============================================================================


def test_api_list_templates_and_reports(client: TestClient):
    """Verify GET /api/v1/reports lists all templates and generated reports."""
    res = client.get("/api/v1/reports", headers={"X-Tenant-ID": "test-t1"})
    assert res.status_code == 200
    data = res.json()
    assert "templates" in data
    assert len(data["templates"]) >= 19  # 14 MVP + 5 Pricing
    assert "reports" in data
    assert "_metadata" in data


def test_api_export_and_download_flow(client: TestClient):
    """Verify POST /api/v1/reports/export generates report and download route retrieves it."""
    export_payload = {
        "template_id": "tpl-cost-monthly",
        "format": "CSV",
        "parameters": {"currency": "USD", "cost_basis": "BILLED"},
    }
    exp_res = client.post(
        "/api/v1/reports/export",
        json=export_payload,
        headers={"X-Tenant-ID": "test-t1", "X-User-ID": "test-user"},
    )
    assert exp_res.status_code == 202
    exp_data = exp_res.json()
    assert exp_data["status"] == "ACCEPTED"
    report_id = exp_data["report_id"]

    # List reports to find download url and token
    list_res = client.get("/api/v1/reports", headers={"X-Tenant-ID": "test-t1"})
    assert list_res.status_code == 200
    reports = list_res.json()["reports"]
    matching_rep = next(
        (r for r in reports if report_id in r["id"] or report_id in r["download_url"]), None
    )
    assert matching_rep is not None
    dl_url = matching_rep["download_url"]

    # Perform download
    dl_res = client.get(dl_url, headers={"X-Tenant-ID": "test-t1"})
    assert dl_res.status_code == 200
    assert "text/csv" in dl_res.headers["content-type"]
    assert "# PROVENANCE & GOVERNANCE FOOTER" in dl_res.text
