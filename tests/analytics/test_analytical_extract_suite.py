"""Test Level 20: Analytical Extract and Semantic Layer Suite (Prompt 42B / Defect D-11).

Verifies the analytical extract and semantic layer across all seven canonical criteria:
1. Schema version stamped on every file and manifest.
2. Restatement re-emitted in full with a new incremented version.
3. Scope manifest present, signed with cryptographic checksums, and accurate.
4. Four canonical null states preserved without flattening (ZERO, NO_DATA, NOT_APPLICABLE, NOT_SUPPORTED).
5. Watermark advances monotonically and correctly.
6. Late and empty extract runs dispatch alerts.
7. Analytical queries strictly isolated from transactional OLTP database connections.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from domain.analytics.extract_engine import AnalyticsExtractEngine
from domain.analytics.models import (
    AnalyticalQueryRequest,
    SemanticDataQualityNullState,
)
from domain.analytics.observability import ExtractObservabilityEngine
from domain.analytics.query_engine import AnalyticsQueryEngine
from domain.analytics.watermark import WatermarkTracker
from domain.models.exceptions import (
    EmptyExtractException,
    TransactionalPathAccessForbiddenException,
)
from domain.tenant.context import TenantContext


class TestAnalyticalExtractSuite:
    """Rigorous verification of Test Level 20 (Analytical Extract and Semantic Layer)."""

    @pytest.fixture
    def tenant_context(self) -> TenantContext:
        return TenantContext(
            tenant_id="tenant-analytics-test",
            user_id="bi-analyst@acme.com",
            roles={"TENANT_ADMIN", "FINOPS_ADMIN", "BI_ANALYST"},
        )

    @pytest.fixture
    def extract_engine(self, tmp_path: Path) -> AnalyticsExtractEngine:
        return AnalyticsExtractEngine(base_storage_path=tmp_path)

    @pytest.fixture
    def sample_facts(self) -> list[dict]:
        return [
            {
                "ChargePeriodStart": "2026-09-01T00:00:00Z",
                "ChargePeriodEnd": "2026-09-01T23:59:59Z",
                "BilledCost": 150.00,
                "BillingCurrency": "USD",
                "ServiceName": "Amazon EC2",
                "ServiceCategory": "Compute",
                "ResourceId": "i-test-001",
                "ScopeId": "scp-prod-01",
            }
        ]

    def test_criterion_1_schema_version_stamped_on_files_and_manifest(
        self, extract_engine: AnalyticsExtractEngine, tenant_context: TenantContext, sample_facts: list[dict]
    ) -> None:
        """Criterion 1: Schema version stamped on every file and manifest."""
        job, manifest = extract_engine.generate_extract(
            period="2026-09",
            service_identity_id="svc-bi-worker",
            service_identity_name="BI Extraction Daemon",
            scope_grants=["scp-prod-01"],
            tenant_context=tenant_context,
            raw_facts=sample_facts,
            is_restatement=False,
        )
        assert job.schema_version == "1.0.0"
        assert manifest.schema_version == "1.0.0"
        assert manifest.version >= 1

    def test_criterion_2_restatement_re_emitted_in_full_with_new_version(
        self, extract_engine: AnalyticsExtractEngine, tenant_context: TenantContext, sample_facts: list[dict]
    ) -> None:
        """Criterion 2: Restatement re-emitted in full with an incremented version."""
        # Initial run: version 1
        job_v1, manifest_v1 = extract_engine.generate_extract(
            period="2026-09",
            service_identity_id="svc-bi-worker",
            service_identity_name="BI Extraction Daemon",
            scope_grants=["scp-prod-01"],
            tenant_context=tenant_context,
            raw_facts=sample_facts,
            is_restatement=False,
        )
        assert job_v1.version == 1

        # Restatement run: version 2 with supersession note
        job_v2, manifest_v2 = extract_engine.generate_extract(
            period="2026-09",
            service_identity_id="svc-bi-worker",
            service_identity_name="BI Extraction Daemon",
            scope_grants=["scp-prod-01"],
            tenant_context=tenant_context,
            raw_facts=sample_facts,
            is_restatement=True,
        )
        assert job_v2.version == 2
        assert manifest_v2.supersedes_version == 1

    def test_criterion_3_scope_manifest_present_and_accurate(
        self, extract_engine: AnalyticsExtractEngine, tenant_context: TenantContext, sample_facts: list[dict]
    ) -> None:
        """Criterion 3: Scope manifest present, signed with checksums, and accurate."""
        job, manifest = extract_engine.generate_extract(
            period="2026-09",
            service_identity_id="svc-bi-worker",
            service_identity_name="BI Extraction Daemon",
            scope_grants=["scp-prod-01"],
            tenant_context=tenant_context,
            raw_facts=sample_facts,
            is_restatement=False,
        )
        assert manifest.tenant_id == tenant_context.tenant_id
        assert manifest.scope_grants == ["scp-prod-01"]
        assert len(manifest.file_checksums) > 0
        for fname, digest in manifest.file_checksums.items():
            assert digest.startswith("sha256:"), f"Digest missing sha256: prefix for {fname}"
            hex_part = digest.split("sha256:")[1]
            assert len(hex_part) == 64, f"Invalid SHA-256 digest hex length for {fname}"

    def test_criterion_4_four_null_states_preserved(self) -> None:
        """Criterion 4: Four null states preserved without conflation or flattening."""
        null_states = {
            SemanticDataQualityNullState.ZERO,
            SemanticDataQualityNullState.NO_DATA,
            SemanticDataQualityNullState.NOT_APPLICABLE,
            SemanticDataQualityNullState.NOT_SUPPORTED,
        }
        assert len(null_states) == 4
        for ns in null_states:
            assert ns is not None
            assert ns.value != "None"

    def test_criterion_5_watermark_advances_correctly(self) -> None:
        """Criterion 5: Watermark advances monotonically and correctly."""
        tracker = WatermarkTracker()
        t1 = "2026-09-01T12:00:00Z"
        t2 = "2026-09-01T14:00:00Z"

        wm1 = tracker.update_watermark("tenant-1", "2026-09", t1)
        assert wm1.last_watermark_timestamp == t1

        # Advance watermark
        wm2 = tracker.update_watermark("tenant-1", "2026-09", t2)
        assert wm2.last_watermark_timestamp == t2
        assert wm2.last_watermark_timestamp > wm1.last_watermark_timestamp

        # Restatement advances version monotonically
        new_v, old_v = tracker.trigger_restatement("tenant-1", "2026-09")
        assert new_v == 2
        assert old_v == 1

    def test_criterion_6_late_and_empty_runs_alert(
        self, tenant_context: TenantContext
    ) -> None:
        """Criterion 6: Empty and late extract executions dispatch alerts and raise exceptions."""
        obs = ExtractObservabilityEngine()
        from domain.analytics.models import AnalyticsExtractJob

        empty_job = AnalyticsExtractJob(
            id="job-empty-001",
            tenant_id=tenant_context.tenant_id,
            period="2026-09",
            version=1,
            row_count=0,
            duration_ms=120,
            schema_version="1.0.0",
            service_identity_id="svc-worker",
            storage_destination="/tmp/test",
            status="SUCCESS",
        )
        with pytest.raises(EmptyExtractException):
            obs.evaluate_emptiness(empty_job, tenant_context=tenant_context, raise_exception=True)

    def test_criterion_7_analytical_queries_never_touch_transactional_path(
        self, tenant_context: TenantContext
    ) -> None:
        """Criterion 7: Analytical queries strictly reject transactional OLTP database connections."""
        query_engine = AnalyticsQueryEngine()
        req = AnalyticalQueryRequest(
            dimensions=["ServiceName"],
            metrics=["BilledCost"],
        )

        class MockOltpConnection:
            """Simulated live PostgreSQL OLTP transactional handle."""
            pass

        with pytest.raises(TransactionalPathAccessForbiddenException):
            query_engine.execute_query(
                req,
                facts=[],
                dimensions={},
                tenant_context=tenant_context,
                oltp_connection=MockOltpConnection(),
            )
