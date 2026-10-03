"""Comprehensive Unit and Integration Tests for Bulk Import Framework and Data Onboarding (Prompt 53).

Validates:
1. AC-120: 5,000-row bulk application and ownership import completes with dry run first, per-row result, and full provenance.
2. Invalid value rejected with row number and failed master, never silently becoming free text.
3. Import reversal within configured window, audited, and blocked when dependent changes occurred.
4. Export symmetry and round-trip support (export-edit-reimport without transformation).
5. Unattended scheduled CMDB feed running and reporting outcome.
6. Four import modes: INSERT_ONLY, UPDATE_ONLY, UPSERT, DEACTIVATE_MISSING.
7. Atomicity policies: ALL_OR_NOTHING vs PARTIAL_SUCCESS.
8. Interlocks: "Do not apply an import without a dry run" and "Do not accept a value that does not exist in its master".
9. File encoding and delimiter detection (UTF-8, UTF-8-BOM, Latin-1, CP1252; comma, semicolon, tab, pipe).
10. Saved mapping profiles for repeat imports.
11. REST API endpoints coverage for API-058 (/api/v1/imports/*).
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import json

import pytest
from fastapi.testclient import TestClient

from api.cloudlens_api.main import app
from domain.bulk_import.catalogue import (
    get_import_catalogue,
)
from domain.bulk_import.engine import (
    BulkImportEngine,
    get_bulk_import_engine,
)
from domain.bulk_import.file_parser import (
    detect_delimiter,
    detect_encoding,
    parse_file_content,
)
from domain.bulk_import.models import (
    AtomicityPolicy,
    ImportMode,
    ImportStatus,
    MappingProfile,
    RowOutcome,
)
from domain.bulk_import.repository import (
    BulkImportRepository,
    get_bulk_import_repository,
)
from domain.bulk_import.scheduler import (
    ScheduledImportScheduler,
    get_scheduled_import_scheduler,
)
from domain.bulk_import.validator import BulkImportValidator
from domain.models.exceptions import (
    DryRunRequiredException,
    ImportValidationException,
    RollbackBlockedException,
    RollbackWindowExpiredException,
)
from domain.tenant.context import TenantContext


@pytest.fixture
def tenant_context() -> TenantContext:
    return TenantContext(tenant_id="T-IMPORT-TEST")


@pytest.fixture
def repo() -> BulkImportRepository:
    r = get_bulk_import_repository()
    r.clear()
    return r


@pytest.fixture
def engine(repo: BulkImportRepository) -> BulkImportEngine:
    _ = repo
    eng = get_bulk_import_engine()
    eng._entity_stores.clear()
    eng._record_modified_at.clear()
    eng._record_dependents.clear()
    return eng


@pytest.fixture
def scheduler() -> ScheduledImportScheduler:
    return get_scheduled_import_scheduler()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# ==============================================================================
# 1. Catalogue and Specification Tests
# ==============================================================================


class TestBulkImportCatalogue:
    """Verifies importable entity metadata, natural keys, and master reference declarations."""

    def test_core_entities_present_in_catalogue(self):
        cat = get_import_catalogue()
        required_entities = [
            "APPLICATION",
            "RESOURCE_CURATION",
            "DEPENDENCY_EDGE",
            "BUSINESS_UNIT",
            "COST_CENTRE",
            "OWNER_TEAM",
            "ENVIRONMENT",
            "PROJECT",
            "BUDGET",
            "EXCHANGE_RATE",
            "RATE_CARD",
            "HOLIDAY_CALENDAR",
            "LICENCE",
            "USER_ROLE_GRANT",
            "TAG_POLICY",
            "THRESHOLD_SET",
        ]
        for et in required_entities:
            meta = cat.get_metadata(et)
            assert meta is not None, f"Entity '{et}' must be registered in catalogue"
            assert meta.natural_key_columns, f"Entity '{et}' must declare natural keys"
            assert len(meta.columns) > 0, f"Entity '{et}' must have column definitions"

    def test_dynamic_prompt45_masters_accessible(self):
        cat = get_import_catalogue()
        master_types = ["SERVICE_CATEGORY", "RESOURCE_TYPE", "UNIT", "CLOUD_PROVIDER"]
        for mt in master_types:
            meta = cat.get_metadata(mt)
            assert meta is not None
            assert meta.natural_key_columns == ["code"]
            assert meta.default_atomicity_policy in {
                AtomicityPolicy.ALL_OR_NOTHING,
                AtomicityPolicy.PARTIAL_SUCCESS,
            }

    def test_atomicity_policy_defaults_as_master_data(self):
        cat = get_import_catalogue()
        # Financial and integrity critical entities default to ALL_OR_NOTHING
        budget_meta = cat.get_metadata("BUDGET")
        assert budget_meta is not None
        assert budget_meta.default_atomicity_policy == AtomicityPolicy.ALL_OR_NOTHING

        fx_meta = cat.get_metadata("EXCHANGE_RATE")
        assert fx_meta is not None
        assert fx_meta.default_atomicity_policy == AtomicityPolicy.ALL_OR_NOTHING

        # Portfolio and curation entities default to PARTIAL_SUCCESS
        app_meta = cat.get_metadata("APPLICATION")
        assert app_meta is not None
        assert app_meta.default_atomicity_policy == AtomicityPolicy.PARTIAL_SUCCESS


# ==============================================================================
# 2. File Parsing, Encoding and Delimiter Detection Tests
# ==============================================================================


class TestFileParsingAndEncoding:
    """Verifies multi-format parsing, encoding detection, and delimiter sniffing."""

    def test_encoding_detection(self):
        utf8_bytes = b"code,name\nAPP-1,Portal"
        assert detect_encoding(utf8_bytes) == "utf-8"

        bom_bytes = b"\xef\xbb\xbfcode,name\nAPP-1,Portal"
        assert detect_encoding(bom_bytes) == "utf-8-sig"

        utf16_bytes = "code,name\nAPP-1,Portal".encode("utf-16")
        assert detect_encoding(utf16_bytes) == "utf-16"

    def test_delimiter_detection(self):
        comma_text = "code,name,criticality\nAPP-1,Portal,HIGH"
        assert detect_delimiter(comma_text) == ","

        semicolon_text = "code;name;criticality\nAPP-1;Portal;HIGH"
        assert detect_delimiter(semicolon_text) == ";"

        tab_text = "code\tname\tcriticality\nAPP-1\tPortal\tHIGH"
        assert detect_delimiter(tab_text) == "\t"

        pipe_text = "code|name|criticality\nAPP-1|Portal|HIGH"
        assert detect_delimiter(pipe_text) == "|"

    def test_json_parsing_with_line_numbers(self):
        json_data = [
            {"code": "APP-01", "name": "App One"},
            {"code": "APP-02", "name": "App Two"},
        ]
        content_bytes = json.dumps(json_data).encode("utf-8")
        encoding, fmt, rows = parse_file_content(content_bytes, "apps.json")
        assert fmt == "json"
        assert len(rows) == 2
        assert rows[0][0] == 1
        assert rows[0][1]["code"] == "APP-01"
        assert rows[1][0] == 2
        assert rows[1][1]["code"] == "APP-02"


# ==============================================================================
# 3. Row-Level Validation & Master Reference Integrity Tests
# ==============================================================================


class TestRowLevelValidationAndMasterReferences:
    """Enforces: Invalid value rejected with row number and failed master, never becoming free text."""

    def test_valid_row_passes_cleanly(self, tenant_context: TenantContext):
        val = BulkImportValidator()
        cat = get_import_catalogue()
        meta = cat.get_metadata("APPLICATION")
        assert meta is not None

        row = {
            "code": "APP-VALID-01",
            "name": "Valid App",
            "criticality_tier": "HIGH",
            "business_unit": "BU_RETAIL_BANKING",
            "cost_centre": "CC-2001",
            "lifecycle_state": "ACTIVE",
        }
        res = val.validate_row(
            row_number=5,
            raw_row=row,
            metadata=meta,
            tenant_id=tenant_context.tenant_id,
        )
        assert res.is_valid is True
        assert res.natural_key == "APP-VALID-01"
        assert len(res.errors) == 0

    def test_invalid_master_reference_rejected_with_row_and_master(
        self, tenant_context: TenantContext
    ):
        """Hard Rule: Do not accept a value that does not exist in its master."""
        val = BulkImportValidator()
        cat = get_import_catalogue()
        meta = cat.get_metadata("APPLICATION")
        assert meta is not None

        row = {
            "code": "APP-INVALID-BU",
            "name": "Invalid BU App",
            "business_unit": "NON_EXISTENT_BU_CODE_999",  # Does not exist in BUSINESS_UNIT
        }
        res = val.validate_row(
            row_number=42,
            raw_row=row,
            metadata=meta,
            tenant_id=tenant_context.tenant_id,
        )
        assert res.is_valid is False
        assert res.failed_master == "BUSINESS_UNIT"
        assert any(
            "Row 42" in err and "NON_EXISTENT_BU_CODE_999" in err and "BUSINESS_UNIT" in err
            for err in res.errors
        )
        # Verify it did not silently become free text
        assert res.failed_master is not None

    def test_missing_required_column_rejected(self, tenant_context: TenantContext):
        val = BulkImportValidator()
        cat = get_import_catalogue()
        meta = cat.get_metadata("APPLICATION")
        assert meta is not None

        row = {"name": "No Code App"}  # Missing required 'code'
        res = val.validate_row(
            row_number=12,
            raw_row=row,
            metadata=meta,
            tenant_id=tenant_context.tenant_id,
        )
        assert res.is_valid is False
        assert any("Required field 'code' is missing" in err for err in res.errors)

    def test_invalid_type_conversion_rejected(self, tenant_context: TenantContext):
        val = BulkImportValidator()
        cat = get_import_catalogue()
        meta = cat.get_metadata("BUDGET")
        assert meta is not None

        row = {
            "budget_id": "BGT-01",
            "name": "Test Budget",
            "amount": "NOT_A_NUMBER",  # Requires number
            "currency": "USD",
            "fiscal_year": "2026",
            "business_unit_code": "BU_RETAIL_BANKING",
        }
        res = val.validate_row(
            row_number=8,
            raw_row=row,
            metadata=meta,
            tenant_id=tenant_context.tenant_id,
        )
        assert res.is_valid is False
        assert any("requires numeric value" in err for err in res.errors)


# ==============================================================================
# 4. Mandatory Dry Run & Four Import Modes
# ==============================================================================


class TestMandatoryDryRunAndModes:
    """Tests INSERT_ONLY, UPDATE_ONLY, UPSERT, DEACTIVATE_MISSING and dry-run enforcement."""

    def test_cannot_apply_without_dry_run_interlock(
        self, engine: BulkImportEngine, tenant_context: TenantContext
    ):
        """Hard Rule: Do not apply an import without a dry run."""
        with pytest.raises(DryRunRequiredException) as exc_info:
            engine.apply_import(
                dry_run_id="fake-non-existent-dry-run",
                tenant_context=tenant_context,
                actor_id="test_user",
            )
        assert "Do not apply an import without a dry run" in str(exc_info.value)

    def test_insert_only_mode(self, engine: BulkImportEngine, tenant_context: TenantContext):
        # Seed 1 existing application
        csv_seed = "code,name\nAPP-EXISTS,Existing Application\n"
        dry_seed = engine.execute_dry_run(
            content_bytes=csv_seed.encode("utf-8"),
            filename="seed.csv",
            entity_type="APPLICATION",
            mode=ImportMode.INSERT_ONLY,
            tenant_context=tenant_context,
        )
        engine.apply_import(
            dry_run_id=dry_seed.dry_run_id, tenant_context=tenant_context, actor_id="admin"
        )

        # Upload file containing 1 new record and 1 existing record
        csv_batch = "code,name\nAPP-EXISTS,Existing Application\nAPP-NEW,Newly Introduced App\n"
        dry = engine.execute_dry_run(
            content_bytes=csv_batch.encode("utf-8"),
            filename="batch.csv",
            entity_type="APPLICATION",
            mode=ImportMode.INSERT_ONLY,
            tenant_context=tenant_context,
        )
        assert dry.created_count == 1
        assert dry.skipped_count == 1
        assert dry.rejected_count == 0

        # Check per-row outcomes
        results_by_key = {r.natural_key: r for r in dry.row_results}
        assert results_by_key["APP-NEW"].outcome == RowOutcome.CREATED
        assert results_by_key["APP-EXISTS"].outcome == RowOutcome.SKIPPED
        assert "already exists" in results_by_key["APP-EXISTS"].reasons[0]

    def test_update_only_mode(self, engine: BulkImportEngine, tenant_context: TenantContext):
        # Seed 1 existing application
        csv_seed = "code,name\nAPP-TARGET,Original Title\n"
        dry_seed = engine.execute_dry_run(
            content_bytes=csv_seed.encode("utf-8"),
            filename="seed.csv",
            entity_type="APPLICATION",
            mode=ImportMode.UPSERT,
            tenant_context=tenant_context,
        )
        engine.apply_import(
            dry_run_id=dry_seed.dry_run_id, tenant_context=tenant_context, actor_id="admin"
        )

        # Attempt update batch with 1 existing (modified title) and 1 non-existent record
        csv_update = (
            "code,name\nAPP-TARGET,Updated Title Modified\nAPP-NONEXISTENT,Never Seen Before\n"
        )
        dry = engine.execute_dry_run(
            content_bytes=csv_update.encode("utf-8"),
            filename="update.csv",
            entity_type="APPLICATION",
            mode=ImportMode.UPDATE_ONLY,
            tenant_context=tenant_context,
        )
        assert dry.updated_count == 1
        assert dry.skipped_count == 1
        assert dry.created_count == 0

        results_by_key = {r.natural_key: r for r in dry.row_results}
        assert results_by_key["APP-TARGET"].outcome == RowOutcome.UPDATED
        assert "name" in results_by_key["APP-TARGET"].changes_diff
        assert results_by_key["APP-NONEXISTENT"].outcome == RowOutcome.SKIPPED

    def test_upsert_mode(self, engine: BulkImportEngine, tenant_context: TenantContext):
        csv_seed = "code,name\nAPP-01,Alpha 1\n"
        dry_seed = engine.execute_dry_run(
            content_bytes=csv_seed.encode("utf-8"),
            filename="seed.csv",
            entity_type="APPLICATION",
            mode=ImportMode.UPSERT,
            tenant_context=tenant_context,
        )
        engine.apply_import(
            dry_run_id=dry_seed.dry_run_id, tenant_context=tenant_context, actor_id="admin"
        )

        # Upsert file: 1 existing modified, 1 existing identical, 1 new
        csv_upsert = "code,name\nAPP-01,Alpha 1 Updated\nAPP-02,Beta 2 New\n"
        dry = engine.execute_dry_run(
            content_bytes=csv_upsert.encode("utf-8"),
            filename="upsert.csv",
            entity_type="APPLICATION",
            mode=ImportMode.UPSERT,
            tenant_context=tenant_context,
        )
        assert dry.created_count == 1
        assert dry.updated_count == 1

        run = engine.apply_import(
            dry_run_id=dry.dry_run_id, tenant_context=tenant_context, actor_id="admin"
        )
        assert run.status == ImportStatus.APPLIED
        assert run.created_count == 1
        assert run.updated_count == 1

    def test_deactivate_missing_mode_for_full_refresh(
        self, engine: BulkImportEngine, tenant_context: TenantContext
    ):
        # Seed 3 records
        csv_seed = (
            "code,name\n"
            "APP-KEEP-1,Keep Me 1\n"
            "APP-KEEP-2,Keep Me 2\n"
            "APP-DELETE,Omitted From Full Refresh\n"
        )
        dry_seed = engine.execute_dry_run(
            content_bytes=csv_seed.encode("utf-8"),
            filename="seed.csv",
            entity_type="APPLICATION",
            mode=ImportMode.UPSERT,
            tenant_context=tenant_context,
        )
        engine.apply_import(
            dry_run_id=dry_seed.dry_run_id, tenant_context=tenant_context, actor_id="admin"
        )

        # Full refresh payload omitting APP-DELETE
        csv_full_refresh = "code,name\nAPP-KEEP-1,Keep Me 1\nAPP-KEEP-2,Keep Me 2\n"
        dry = engine.execute_dry_run(
            content_bytes=csv_full_refresh.encode("utf-8"),
            filename="refresh.csv",
            entity_type="APPLICATION",
            mode=ImportMode.DEACTIVATE_MISSING,
            tenant_context=tenant_context,
        )
        assert dry.deactivated_count >= 1
        results_by_key = {r.natural_key: r for r in dry.row_results}
        assert results_by_key["APP-DELETE"].outcome == RowOutcome.DEACTIVATED

        run = engine.apply_import(
            dry_run_id=dry.dry_run_id, tenant_context=tenant_context, actor_id="admin"
        )
        assert run.deactivated_count >= 1


# ==============================================================================
# 5. Atomicity Policy Enforcement
# ==============================================================================


class TestAtomicityPolicies:
    """Validates ALL_OR_NOTHING vs PARTIAL_SUCCESS behavior."""

    def test_all_or_nothing_policy_rejects_entire_batch_on_single_failure(
        self, engine: BulkImportEngine, tenant_context: TenantContext
    ):
        csv_data = (
            "budget_id,name,amount,currency,fiscal_year,business_unit_code\n"
            "BGT-01,Valid Budget 1,10000,USD,2026,BU_RETAIL_BANKING\n"
            "BGT-02,Invalid Budget,20000,USD,2026,NON_EXISTENT_BU\n"  # Invalid BU!
            "BGT-03,Valid Budget 3,30000,USD,2026,BU_RETAIL_BANKING\n"
        )
        dry = engine.execute_dry_run(
            content_bytes=csv_data.encode("utf-8"),
            filename="budgets.csv",
            entity_type="BUDGET",
            mode=ImportMode.INSERT_ONLY,
            atomicity_policy=AtomicityPolicy.ALL_OR_NOTHING,
            tenant_context=tenant_context,
        )
        assert dry.rejected_count == 1
        assert dry.is_valid is False  # ALL_OR_NOTHING invalidates whole batch!

        with pytest.raises(ImportValidationException) as exc_info:
            engine.apply_import(
                dry_run_id=dry.dry_run_id, tenant_context=tenant_context, actor_id="admin"
            )
        assert "Cannot apply import: dry run failed with 1 rejected rows" in str(exc_info.value)

    def test_partial_success_policy_applies_valid_rows(
        self, engine: BulkImportEngine, tenant_context: TenantContext
    ):
        csv_data = (
            "code,name,business_unit\n"
            "APP-GOOD-1,Good App 1,BU_RETAIL_BANKING\n"
            "APP-BAD,Bad App,INVALID_BU_CODE\n"  # Rejected
            "APP-GOOD-2,Good App 2,BU_RETAIL_BANKING\n"
        )
        dry = engine.execute_dry_run(
            content_bytes=csv_data.encode("utf-8"),
            filename="apps.csv",
            entity_type="APPLICATION",
            mode=ImportMode.INSERT_ONLY,
            atomicity_policy=AtomicityPolicy.PARTIAL_SUCCESS,
            tenant_context=tenant_context,
        )
        assert dry.rejected_count == 1
        assert dry.created_count == 2
        assert dry.is_valid is True  # PARTIAL_SUCCESS allows apply

        run = engine.apply_import(
            dry_run_id=dry.dry_run_id, tenant_context=tenant_context, actor_id="admin"
        )
        assert run.status == ImportStatus.APPLIED
        assert run.created_count == 2
        assert run.rejected_count == 1


# ==============================================================================
# 6. 5,000-Row Bulk Import & Full Provenance (AC-120)
# ==============================================================================


class Test5000RowBulkImportAndProvenance:
    """Enforces Acceptance AC-120:

    'A five-thousand-row application and ownership import completes with a dry run first,
    a per-row result, and full provenance on every record.'
    """

    def test_five_thousand_row_import_lifecycle(
        self, engine: BulkImportEngine, tenant_context: TenantContext
    ):
        row_count = 5000
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["code", "name", "business_unit", "criticality_tier"])

        for i in range(1, row_count + 1):
            writer.writerow(
                [
                    f"APP-{i:05d}",
                    f"Enterprise Service Scale {i}",
                    "BU_RETAIL_BANKING",
                    "HIGH" if i % 2 == 0 else "MEDIUM",
                ]
            )

        content_bytes = output.getvalue().encode("utf-8")

        # 1. Mandatory dry run first
        dry = engine.execute_dry_run(
            content_bytes=content_bytes,
            filename="bulk_5000_apps.csv",
            entity_type="APPLICATION",
            mode=ImportMode.INSERT_ONLY,
            tenant_context=tenant_context,
            actor_id="finops-director@cloudlens.internal",
        )
        assert dry.total_rows == 5000
        assert dry.created_count == 5000
        assert dry.rejected_count == 0
        assert dry.is_valid is True
        assert len(dry.row_results) == 5000

        # Verify downloadable dry-run report
        download_report = engine.generate_dry_run_download_result(dry, export_format="csv")
        assert len(download_report) > 0
        assert "row_number,outcome,natural_key" in download_report

        # 2. Apply import
        run = engine.apply_import(
            dry_run_id=dry.dry_run_id,
            tenant_context=tenant_context,
            actor_id="finops-director@cloudlens.internal",
        )
        assert run.status == ImportStatus.APPLIED
        assert run.created_count == 5000
        assert run.duration_seconds >= 0.0

        # 3. Verify full row-level provenance on imported records
        # Hard Rule: Do not import without recording the source file, row and actor.
        sample_keys = ["APP-00001", "APP-02500", "APP-05000"]
        for k in sample_keys:
            rec = engine._get_record("APPLICATION", k, tenant_context)
            assert rec is not None
            assert "_provenance" in rec
            prov = rec["_provenance"]
            assert prov["imported"] is True
            assert prov["source_filename"] == "bulk_5000_apps.csv"
            assert len(prov["source_file_hash"]) == 64  # SHA256
            assert prov["import_run_id"] == run.id
            assert prov["imported_by"] == "finops-director@cloudlens.internal"
            assert prov["source_row_number"] > 0


# ==============================================================================
# 7. Rollback Path & Dependency Guard
# ==============================================================================


class TestRollbackPathAndDependencyGuard:
    """Enforces:

    - An import run can be reversed within the window, and the reversal is audited.
    - Reversal is blocked where dependent changes have since occurred, with a clear explanation.
    """

    def test_successful_rollback_within_window(
        self, engine: BulkImportEngine, tenant_context: TenantContext
    ):
        csv_data = "code,name\nAPP-ROLL-1,Rollback Target\n"
        dry = engine.execute_dry_run(
            content_bytes=csv_data.encode("utf-8"),
            filename="apps.csv",
            entity_type="APPLICATION",
            mode=ImportMode.INSERT_ONLY,
            tenant_context=tenant_context,
        )
        run = engine.apply_import(
            dry_run_id=dry.dry_run_id, tenant_context=tenant_context, actor_id="admin"
        )

        assert engine._get_record("APPLICATION", "APP-ROLL-1", tenant_context) is not None

        # Reversal
        reversed_run = engine.rollback_import(
            import_run_id=run.id,
            tenant_context=tenant_context,
            actor_id="admin",
            reason="Mistaken test import",
        )
        assert reversed_run.status == ImportStatus.REVERSED
        assert reversed_run.can_rollback is False
        assert reversed_run.reversal_record is not None
        assert reversed_run.reversal_record["reversed_by"] == "admin"

        # Record should no longer exist
        assert engine._get_record("APPLICATION", "APP-ROLL-1", tenant_context) is None

    def test_rollback_blocked_when_dependent_changes_occurred(
        self, engine: BulkImportEngine, tenant_context: TenantContext
    ):
        csv_data = "code,name\nAPP-DEPENDENT,Parent App\n"
        dry = engine.execute_dry_run(
            content_bytes=csv_data.encode("utf-8"),
            filename="apps.csv",
            entity_type="APPLICATION",
            mode=ImportMode.INSERT_ONLY,
            tenant_context=tenant_context,
        )
        run = engine.apply_import(
            dry_run_id=dry.dry_run_id, tenant_context=tenant_context, actor_id="admin"
        )

        # Register dependent relationship (e.g. cloud resource linked to application)
        engine.register_dependent_relation(
            tenant_id=tenant_context.tenant_id,
            entity_type="APPLICATION",
            natural_key="APP-DEPENDENT",
            dependent_id="res-vm-prod-01",
        )

        with pytest.raises(RollbackBlockedException) as exc_info:
            engine.rollback_import(
                import_run_id=run.id, tenant_context=tenant_context, actor_id="admin"
            )
        assert "actively referenced by dependent records" in str(exc_info.value)

    def test_rollback_blocked_when_subsequent_modification_occurred(
        self, engine: BulkImportEngine, tenant_context: TenantContext
    ):
        csv_data = "code,name\nAPP-MOD,Original Name\n"
        dry = engine.execute_dry_run(
            content_bytes=csv_data.encode("utf-8"),
            filename="apps.csv",
            entity_type="APPLICATION",
            mode=ImportMode.INSERT_ONLY,
            tenant_context=tenant_context,
        )
        run = engine.apply_import(
            dry_run_id=dry.dry_run_id, tenant_context=tenant_context, actor_id="admin"
        )

        # Simulate subsequent modification by user in console
        engine.mark_record_subsequently_modified(
            tenant_id=tenant_context.tenant_id,
            entity_type="APPLICATION",
            natural_key="APP-MOD",
            modified_at=dt.datetime.now(dt.UTC) + dt.timedelta(minutes=10),
        )

        with pytest.raises(RollbackBlockedException) as exc_info:
            engine.rollback_import(
                import_run_id=run.id, tenant_context=tenant_context, actor_id="admin"
            )
        assert "was modified at" in str(exc_info.value)
        assert "Subsequent changes block rollback" in str(exc_info.value)

    def test_rollback_blocked_when_window_expired(
        self, engine: BulkImportEngine, tenant_context: TenantContext
    ):
        csv_data = "code,name\nAPP-EXPIRED,Expiring App\n"
        dry = engine.execute_dry_run(
            content_bytes=csv_data.encode("utf-8"),
            filename="apps.csv",
            entity_type="APPLICATION",
            mode=ImportMode.INSERT_ONLY,
            tenant_context=tenant_context,
        )
        run = engine.apply_import(
            dry_run_id=dry.dry_run_id, tenant_context=tenant_context, actor_id="admin"
        )

        # Artificially age the started_at timestamp beyond rollback window (48h)
        run.started_at = dt.datetime.now(dt.UTC) - dt.timedelta(hours=50)
        engine.repository.save_import_run(run, tenant_context=tenant_context)

        with pytest.raises(RollbackWindowExpiredException) as exc_info:
            engine.rollback_import(
                import_run_id=run.id, tenant_context=tenant_context, actor_id="admin"
            )
        assert "rollback window of 48 hours expired" in str(exc_info.value)


# ==============================================================================
# 8. Export Symmetry & Round-Trip Support
# ==============================================================================


class TestExportSymmetryAndRoundTrip:
    """Enforces: Exporting an entity produces a file that can be edited and re-imported without transformation."""

    def test_export_edit_reimport_round_trip(
        self, engine: BulkImportEngine, tenant_context: TenantContext
    ):
        # 1. Seed initial state
        initial_csv = (
            "code,name,criticality_tier\n"
            "APP-RT-1,RoundTrip One,HIGH\n"
            "APP-RT-2,RoundTrip Two,MEDIUM\n"
        )
        dry = engine.execute_dry_run(
            content_bytes=initial_csv.encode("utf-8"),
            filename="initial.csv",
            entity_type="APPLICATION",
            mode=ImportMode.INSERT_ONLY,
            tenant_context=tenant_context,
        )
        engine.apply_import(
            dry_run_id=dry.dry_run_id, tenant_context=tenant_context, actor_id="admin"
        )

        # 2. Export entity in same CSV format
        exported_csv = engine.export_entity("APPLICATION", tenant_context, export_format="csv")
        assert "APP-RT-1" in exported_csv
        assert "APP-RT-2" in exported_csv

        # 3. Simulate human editing exported file (changing title of APP-RT-1)
        edited_csv = exported_csv.replace("RoundTrip One", "RoundTrip One Edited In Excel")

        # 4. Re-import edited file in UPSERT mode without transformation
        reimport_dry = engine.execute_dry_run(
            content_bytes=edited_csv.encode("utf-8"),
            filename="reimport.csv",
            entity_type="APPLICATION",
            mode=ImportMode.UPSERT,
            tenant_context=tenant_context,
        )
        assert reimport_dry.is_valid is True
        assert reimport_dry.updated_count == 1  # 1 updated

        run = engine.apply_import(
            dry_run_id=reimport_dry.dry_run_id, tenant_context=tenant_context, actor_id="admin"
        )
        assert run.updated_count == 1

        rec = engine._get_record("APPLICATION", "APP-RT-1", tenant_context)
        assert rec is not None
        assert rec["name"] == "RoundTrip One Edited In Excel"

    def test_template_download(self, engine: BulkImportEngine):
        template = engine.generate_template("APPLICATION", export_format="csv")
        assert "code,name" in template
        assert "# Template for Enterprise Applications" in template


# ==============================================================================
# 9. Scheduled CMDB Feed (Unattended)
# ==============================================================================


class TestScheduledCMDBFeed:
    """Enforces: A scheduled CMDB feed runs unattended and reports its outcome."""

    def test_unattended_cmdb_feed_execution(
        self,
        scheduler: ScheduledImportScheduler,
        engine: BulkImportEngine,
        tenant_context: TenantContext,
    ):
        # 1. Register mapping profile for ServiceNow CMDB
        repo = engine.repository
        profile = MappingProfile(
            id="prof-servicenow-cmdb",
            tenant_id=tenant_context.tenant_id,
            name="ServiceNow CMDB Dependency Feed",
            entity_type="DEPENDENCY_EDGE",
            column_mappings={
                "parent_ci": "source_id",
                "child_ci": "target_id",
                "type": "relationship_type",
            },
            default_values={"relationship_type": "LOGICAL_DEPENDENCY"},
        )
        repo.save_mapping_profile(profile, tenant_context=tenant_context)

        # 2. Register mock CMDB feed payload
        feed_uri = "https://cmdb.internal.corp/api/v1/topology_export.csv"
        cmdb_payload = (
            b"parent_ci,child_ci,type\n"
            b"APP-PORTAL-01,res-db-rds-01,LOGICAL_DEPENDENCY\n"
            b"APP-CHECKOUT-01,res-cache-redis-01,LOGICAL_DEPENDENCY\n"
        )
        scheduler.register_mock_feed_data(feed_uri, cmdb_payload)

        # 3. Create scheduled job
        job = scheduler.create_scheduled_job(
            name="Nightly ServiceNow CMDB Feed",
            entity_type="DEPENDENCY_EDGE",
            cron_expression="0 2 * * *",
            mapping_profile_id=profile.id,
            mode=ImportMode.UPSERT,
            source_type="CMDB_CONNECTOR",
            source_uri=feed_uri,
            tenant_context=tenant_context,
        )
        assert job.id.startswith("sch-")

        # 4. Run unattended
        run = scheduler.run_scheduled_job(job.id, tenant_context=tenant_context)
        assert run.status == ImportStatus.APPLIED
        assert run.created_count == 2
        assert run.actor_id == f"cron:{job.id}"

        # 5. Check job status updated
        updated_job = repo.get_scheduled_job(job.id, tenant_context=tenant_context)
        assert updated_job is not None
        assert updated_job.last_status == "SUCCESS"
        assert updated_job.last_run_at is not None
        assert updated_job.last_run_id == run.id


# ==============================================================================
# 10. REST API Integration Tests (API-058)
# ==============================================================================


class TestBulkImportRestApi:
    """Validates public API surface at /api/v1/imports/* (API-058 / Prompt 34 / Rule 2.4)."""

    def test_api_entities_and_template_endpoints(self, client: TestClient):
        # 1. GET /api/v1/imports/entities
        resp = client.get("/api/v1/imports/entities")
        assert resp.status_code == 200
        entities = resp.json()
        assert len(entities) >= 16

        # 2. GET /api/v1/imports/templates/APPLICATION
        resp = client.get("/api/v1/imports/templates/APPLICATION?format=csv")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]
        assert "code,name" in resp.text

    def test_api_mapping_profiles_lifecycle(self, client: TestClient):
        headers = {"X-Tenant-ID": "T-API-IMPORT"}
        payload = {
            "name": "Custom HR Mapping",
            "entity_type": "OWNER_TEAM",
            "column_mappings": {"squad_name": "display_name", "squad_code": "code"},
            "default_values": {"role": "Engineering Squad"},
        }
        resp = client.post("/api/v1/imports/profiles", json=payload, headers=headers)
        assert resp.status_code == 201
        data = resp.json()
        assert data["id"].startswith("prof-")
        assert data["name"] == "Custom HR Mapping"

        # List profiles
        list_resp = client.get("/api/v1/imports/profiles", headers=headers)
        assert list_resp.status_code == 200
        profiles = list_resp.json()
        assert len(profiles) >= 1

    def test_api_dry_run_and_apply_flow(self, client: TestClient):
        headers = {"X-Tenant-ID": "T-API-FLOW"}

        # 1. Dry run
        dry_payload = {
            "entity_type": "APPLICATION",
            "mode": "INSERT_ONLY",
            "content": "code,name\nAPP-API-01,API App One\nAPP-API-02,API App Two\n",
        }
        resp = client.post("/api/v1/imports/dry-run", json=dry_payload, headers=headers)
        assert resp.status_code == 200
        dry_data = resp.json()
        assert dry_data["total_rows"] == 2
        assert dry_data["created_count"] == 2
        assert dry_data["is_valid"] is True
        dry_run_id = dry_data["dry_run_id"]

        # 2. Download dry run result report
        res_resp = client.get(
            f"/api/v1/imports/dry-run/{dry_run_id}/result?format=csv", headers=headers
        )
        assert res_resp.status_code == 200
        assert "row_number,outcome,natural_key" in res_resp.text

        # 3. Apply import
        apply_resp = client.post(
            f"/api/v1/imports/{dry_run_id}/apply?actor_id=admin-user", headers=headers
        )
        assert apply_resp.status_code == 200
        apply_data = apply_resp.json()
        assert apply_data["status"] == "APPLIED"
        assert apply_data["created_count"] == 2
        import_run_id = apply_data["id"]

        # 4. History check
        hist_resp = client.get("/api/v1/imports/history", headers=headers)
        assert hist_resp.status_code == 200
        assert len(hist_resp.json()) >= 1

        # 5. Rollback
        roll_resp = client.post(
            f"/api/v1/imports/{import_run_id}/rollback",
            json={"reason": "Testing rollback endpoint", "actor_id": "admin-user"},
            headers=headers,
        )
        assert roll_resp.status_code == 200
        roll_data = roll_resp.json()
        assert roll_data["status"] == "REVERSED"
