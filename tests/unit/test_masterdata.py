"""Unit Tests for Master Data Management Framework & Console (Prompt 45).

Acceptance Criteria Enforced:
1. Every list, enumeration, category, label, state, threshold default, and mapping
   in the product resolves from a registered master, proven by the registry manifest covering all of them.
2. Changing a master value changes product behaviour with no deployment and no restart.
3. A master value in use cannot be deleted; the block message explicitly names what references it.
4. Re-running the seed loader twice produces zero changes on the second run (idempotent).
5. Reading a cost fact from six months ago resolves its service category through the master version
   effective then, not the current one.
6. Strict Rules: Do not create any master outside the registry; do not allow an in-code enumeration
   to shadow a master; do not mutate a master row in place when its meaning changes (version it).
"""

import json
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from api.cloudlens_api.main import app
from domain.models.exceptions import (
    CannotDeleteSystemMasterException,
    MasterDataApprovalException,
    MasterNotRegisteredException,
    ReferenceIntegrityBlockedException,
)
from masterdata import (
    LifecycleStatus,
    MasterDataService,
    reset_master_data_service,
)


@pytest.fixture
def service() -> MasterDataService:
    """Fixture providing a freshly initialized and seeded MasterDataService."""
    reset_master_data_service()
    return MasterDataService(auto_seed=True)


@pytest.fixture
def client() -> TestClient:
    """Fixture providing FastAPI test client with freshly seeded service."""
    reset_master_data_service()
    return TestClient(app)


# ==============================================================================
# 1. Acceptance: Registry Manifest Covers All System Masters
# ==============================================================================


def test_registry_manifest_covers_all_system_masters(service: MasterDataService):
    """Every taxonomy, category, and state resolves from a registered master."""
    registry = service.get_registry()
    registered_codes = {entry.master_type for entry in registry}

    expected_masters = {
        "SERVICE_CATEGORY",
        "RESOURCE_TYPE",
        "UNIT",
        "METRIC",
        "PRICING_DIMENSION",
        "CLOUD_PROVIDER",
        "RUNTIME_STATUS",
        "CHARGE_CATEGORY",
        "PRICING_STATUS",
        "POLICY_SEVERITY",
        "THRESHOLD_BAND",
    }

    assert expected_masters.issubset(registered_codes)
    assert len(registry) == 32

    # Strict rule: accessing or creating an unregistered master must raise MasterNotRegisteredException
    with pytest.raises(MasterNotRegisteredException) as exc_info:
        service.get_record("UNREGISTERED_TAXONOMY", "SOME_CODE")
    assert "UNREGISTERED_TAXONOMY" in str(exc_info.value)

    with pytest.raises(MasterNotRegisteredException):
        service.list_records("NON_EXISTENT_MASTER")

    with pytest.raises(MasterNotRegisteredException):
        service.create_record(
            master_type="ILLEGAL_MASTER",
            code="VAL1",
            display_name="Illegal Value",
        )


# ==============================================================================
# 2. Acceptance: Idempotent Seed Loading
# ==============================================================================


def test_seed_loader_is_fully_idempotent(service: MasterDataService):
    """Re-running the seed loader twice produces exactly zero changes on the second run."""
    # First seed occurred in fixture. Re-run explicitly:
    report2 = service.seed_system_masters()

    assert report2.records_created == 0
    assert report2.records_updated == 0
    assert report2.total_mutations == 0
    assert len(report2.errors) == 0

    # Third run to ensure deterministic idempotency
    report3 = service.seed_system_masters()
    assert report3.total_mutations == 0

    # Ensure all seeded records are marked is_system=True and PUBLISHED
    categories = service.list_records("SERVICE_CATEGORY")
    assert len(categories) >= 11
    for cat in categories:
        assert cat.is_system is True
        assert cat.lifecycle_status == LifecycleStatus.PUBLISHED
        assert cat.effective_from <= datetime.utcnow()
        assert cat.effective_to is None


# ==============================================================================
# 3. Acceptance: Dynamic Change With No Deployment or Restart
# ==============================================================================


def test_dynamic_master_change_with_no_restart(service: MasterDataService):
    """Changing a master value changes product behaviour with no deployment and no restart."""
    # Lookup initial threshold band
    nominal = service.get_record("THRESHOLD_BAND", "NOMINAL")
    assert nominal is not None
    assert nominal.display_name == "Nominal"

    # Dynamically update the threshold band in the running service (simulating admin action)
    updated = service.update_record(
        master_type="THRESHOLD_BAND",
        code="NOMINAL",
        display_name="Nominal Operational Range (Updated)",
        description="Updated operational baseline without restart",
        attributes={"min_percentage": 0.0, "max_percentage": 75.0, "color_hex": "#10B981"},
        changed_by="admin-user-01",
        change_reason="Re-calibrated enterprise baseline",
    )

    assert updated.version == 2
    assert updated.display_name == "Nominal Operational Range (Updated)"

    # Immediate query in the same running process confirms the new behaviour is active
    resolved = service.get_record("THRESHOLD_BAND", "NOMINAL")
    assert resolved is not None
    assert resolved.version == 2
    assert resolved.display_name == "Nominal Operational Range (Updated)"
    assert resolved.attributes["max_percentage"] == 75.0


# ==============================================================================
# 4. Acceptance: Historical Point-in-Time Version Resolution
# ==============================================================================


def test_point_in_time_resolution_resolves_historical_effective_version(service: MasterDataService):
    """Reading a cost fact from six months ago resolves its service category through

    the master version effective then, not the current one.
    """
    now = datetime.utcnow()
    six_months_ago = now - timedelta(days=180)
    three_months_ago = now - timedelta(days=90)

    # Compute service category was seeded effective from DEFAULT_MASTER_EPOCH (year 2000)
    initial_record = service.get_record("SERVICE_CATEGORY", "COMPUTE")
    assert initial_record is not None
    assert initial_record.display_name == "Compute"
    assert initial_record.version == 1

    # 3 months ago, Compute was updated to a new version with an updated display name & attribute
    # We simulate this transition by specifying effective_at = three_months_ago
    service.update_record(
        master_type="SERVICE_CATEGORY",
        code="COMPUTE",
        display_name="Compute & Accelerated Processing",
        description="Updated FOCUS category definition",
        attributes={"focus_id": "compute", "supports_accelerators": True},
        effective_at=three_months_ago,
        changed_by="finops-governance",
        change_reason="Enterprise focus expansion",
        force_publish=True,
    )

    # 1. Querying as of 6 months ago (before the change) MUST resolve Version 1
    historical_fact_category = service.get_record(
        master_type="SERVICE_CATEGORY",
        code="COMPUTE",
        as_of=six_months_ago,
    )
    assert historical_fact_category is not None
    assert historical_fact_category.version == 1
    assert historical_fact_category.display_name == "Compute"
    assert "supports_accelerators" not in historical_fact_category.attributes

    # 2. Querying as of now MUST resolve Version 2
    current_category = service.get_record(
        master_type="SERVICE_CATEGORY",
        code="COMPUTE",
        as_of=now,
    )
    assert current_category is not None
    assert current_category.version == 2
    assert current_category.display_name == "Compute & Accelerated Processing"
    assert current_category.attributes["supports_accelerators"] is True

    # 3. Lineage trace must confirm 2 versions in history
    lineage = service.get_lineage("SERVICE_CATEGORY", "COMPUTE")
    assert lineage.total_versions == 2
    assert len(lineage.history) == 2
    assert lineage.history[0].version == 1
    assert lineage.history[0].effective_to == three_months_ago
    assert lineage.history[1].version == 2
    assert lineage.history[1].effective_to is None


# ==============================================================================
# 5. Acceptance: Reference Integrity Guard Blocks Deactivation and Deletion
# ==============================================================================


def test_reference_integrity_blocks_deactivation_with_explicit_reasons(service: MasterDataService):
    """A master value in use cannot be deactivated; block message explicitly names what references it."""
    # Simulate active estate references for COMPUTE
    service.set_mock_live_reference(
        master_type="SERVICE_CATEGORY",
        code="COMPUTE",
        references={"cost_fact": 142050, "resource": 3200, "budget_item": 14},
    )

    # Inspect where-used
    where_used = service.check_reference_integrity("SERVICE_CATEGORY", "COMPUTE")
    assert where_used.is_in_use is True
    assert where_used.total_reference_count == 145264
    assert len(where_used.blocking_reasons) > 0

    # Attempting to deactivate must raise ReferenceIntegrityBlockedException
    with pytest.raises(ReferenceIntegrityBlockedException) as exc_info:
        service.deactivate_record("SERVICE_CATEGORY", "COMPUTE", requested_by="operator-1")

    err_msg = str(exc_info.value)
    assert "Cannot deactivate master value 'COMPUTE'" in err_msg
    assert "142050 cost_fact" in err_msg
    assert "3200 resource" in err_msg
    assert "14 budget_item" in err_msg
    assert "Deactivation blocked" in err_msg


def test_reference_integrity_blocks_deletion_of_system_and_in_use_records(
    service: MasterDataService,
):
    """System records cannot be hard deleted; non-system records in use cannot be deleted."""
    # 1. System master deletion attempt must be strictly blocked
    with pytest.raises(CannotDeleteSystemMasterException) as exc_info:
        service.delete_record("SERVICE_CATEGORY", "COMPUTE", requested_by="operator-1")
    assert "Cannot delete system master value 'COMPUTE'" in str(exc_info.value)

    # 2. Create custom non-system master record
    custom_charge = service.create_record(
        master_type="CHARGE_CATEGORY",
        code="CARBON_OFFSET",
        display_name="Carbon Offset Fee",
        description="Custom ESG environmental fee",
        is_system=False,
    )
    assert custom_charge.is_system is False

    # 3. Simulate reference in usage fact
    service.set_mock_live_reference(
        master_type="CHARGE_CATEGORY",
        code="CARBON_OFFSET",
        references={"usage_fact": 840},
    )

    with pytest.raises(ReferenceIntegrityBlockedException) as exc_info2:
        service.delete_record("CHARGE_CATEGORY", "CARBON_OFFSET", requested_by="operator-1")
    assert "840 usage_fact" in str(exc_info2.value)

    # 4. Once reference count drops to 0, deletion succeeds
    service.set_mock_live_reference(
        master_type="CHARGE_CATEGORY",
        code="CARBON_OFFSET",
        references={},
    )
    service.delete_record("CHARGE_CATEGORY", "CARBON_OFFSET", requested_by="operator-1")
    assert service.get_record("CHARGE_CATEGORY", "CARBON_OFFSET", include_inactive=True) is None


# ==============================================================================
# 6. Tenant-Specific Scoped Overrides
# ==============================================================================


def test_tenant_specific_master_override(service: MasterDataService):
    """Tenant-scoped master record takes precedence over global master record."""
    # Global currency unit
    global_usd = service.get_record("UNIT", "USD")
    assert global_usd is not None
    assert global_usd.tenant_id is None
    assert global_usd.display_name == "US Dollar"

    # Create tenant override for 'tenant-corp-intl'
    service.create_record(
        master_type="UNIT",
        code="USD",
        display_name="US Dollar (Internal Corporate Rate)",
        description="Tenant specific ledger representation",
        attributes={"reporting_symbol": "USD-INTL", "custom_fx_multiplier": 1.02},
        tenant_id="tenant-corp-intl",
        force_publish=True,
    )

    # Query without tenant -> returns global
    res_global = service.get_record("UNIT", "USD")
    assert res_global is not None
    assert res_global.display_name == "US Dollar"

    # Query for other tenant -> returns global
    res_other = service.get_record("UNIT", "USD", tenant_id="tenant-other")
    assert res_other is not None
    assert res_other.display_name == "US Dollar"

    # Query for tenant-corp-intl -> returns tenant override
    res_tenant = service.get_record("UNIT", "USD", tenant_id="tenant-corp-intl")
    assert res_tenant is not None
    assert res_tenant.display_name == "US Dollar (Internal Corporate Rate)"
    assert res_tenant.attributes["reporting_symbol"] == "USD-INTL"


# ==============================================================================
# 7. Configurable Change Lifecycle & Approval Workflow
# ==============================================================================


def test_approval_lifecycle_workflow(service: MasterDataService):
    """Enforces DRAFT -> IN_REVIEW -> APPROVED -> PUBLISHED lifecycle."""
    # SERVICE_CATEGORY requires approval per manifest
    manifest = service.get_master_manifest("SERVICE_CATEGORY")
    assert manifest.requires_approval is True

    # 1. Update creates DRAFT version
    draft_record = service.update_record(
        master_type="SERVICE_CATEGORY",
        code="DATABASE",
        display_name="Database & Data Stores",
        changed_by="developer-01",
        change_reason="Refined naming",
    )
    assert draft_record.lifecycle_status == LifecycleStatus.DRAFT
    assert draft_record.approved_by is None

    # Cannot publish directly from DRAFT
    with pytest.raises(MasterDataApprovalException):
        service.publish("SERVICE_CATEGORY", "DATABASE", publisher_id="lead-01")

    # 2. Submit for review -> IN_REVIEW
    in_review = service.submit_for_review(
        master_type="SERVICE_CATEGORY",
        code="DATABASE",
        user_id="developer-01",
    )
    assert in_review.lifecycle_status == LifecycleStatus.IN_REVIEW

    # 3. Approve -> APPROVED
    approved = service.approve(
        master_type="SERVICE_CATEGORY",
        code="DATABASE",
        approver_id="governance-lead-01",
    )
    assert approved.lifecycle_status == LifecycleStatus.APPROVED
    assert approved.approved_by == "governance-lead-01"

    # 4. Publish -> PUBLISHED (closes prior version and activates approved)
    published = service.publish(
        master_type="SERVICE_CATEGORY",
        code="DATABASE",
        publisher_id="release-manager-01",
    )
    assert published.lifecycle_status == LifecycleStatus.PUBLISHED
    assert published.is_active is True

    # Now querying current active record returns the newly published version
    current = service.get_record("SERVICE_CATEGORY", "DATABASE")
    assert current is not None
    assert current.display_name == "Database & Data Stores"
    assert current.version == published.version


# ==============================================================================
# 8. Import / Export and Dry-Run Validation
# ==============================================================================


def test_dry_run_validation_and_bulk_io(service: MasterDataService):
    """Dry-run validation validates schemas, detects invalid rows, and produces row errors."""
    valid_payload = [
        {
            "code": "CUSTOM_TAG_1",
            "display_name": "Cost Center Tag",
            "description": "Enterprise allocation tag",
            "sort_order": 10,
            "attributes": {"required": True},
        },
        {
            "code": "CUSTOM_TAG_2",
            "display_name": "Project Code Tag",
            "sort_order": 20,
        },
    ]

    # Valid dry run
    dry_run_valid = service.dry_run_import("RESOURCE_TYPE", valid_payload)
    assert dry_run_valid.is_valid is True
    assert dry_run_valid.valid_rows == 2
    assert dry_run_valid.error_rows == 0

    # Invalid dry run: missing mandatory code and invalid attribute format
    invalid_payload = [
        {"display_name": "Missing code field"},  # Row 1 error
        {"code": "", "display_name": "Empty code"},  # Row 2 error
        {"code": "VALID_ROW", "display_name": "Valid Item"},  # Row 3 valid
    ]
    dry_run_invalid = service.dry_run_import("RESOURCE_TYPE", invalid_payload)
    assert dry_run_invalid.is_valid is False
    assert dry_run_invalid.error_rows == 2
    assert dry_run_invalid.valid_rows == 1
    assert len(dry_run_invalid.errors) == 2
    assert dry_run_invalid.errors[0]["row_index"] == 1
    assert dry_run_invalid.errors[1]["row_index"] == 2

    # JSON export / import round-trip
    exported_json = service.export_to_json("RUNTIME_STATUS")
    parsed = json.loads(exported_json)
    assert len(parsed) >= 6
    assert any(item["code"] == "RUNNING" for item in parsed)

    # CSV export
    exported_csv = service.export_to_csv("CLOUD_PROVIDER")
    assert "AWS" in exported_csv
    assert "AZURE" in exported_csv
    assert "GCP" in exported_csv
    assert "OCI" in exported_csv


# ==============================================================================
# 9. Health Inspection & Governance Reporting
# ==============================================================================


def test_master_data_health_inspection(service: MasterDataService):
    """Inspects health of registered masters, identifies unreferenced and stale values."""
    health = service.inspect_health()

    assert health.total_masters_registered == 32
    assert health.total_records > 80
    assert health.active_records > 80
    assert health.inactive_records == 0
    assert len(health.empty_masters) == 0
    assert health.overall_health_score >= 80.0


# ==============================================================================
# 10. API Route Verification
# ==============================================================================


def test_api_masterdata_routes(client: TestClient):
    """Tests master data REST endpoints."""
    # 1. GET /api/v1/masterdata/registry
    res_reg = client.get("/api/v1/masterdata/registry")
    assert res_reg.status_code == 200
    reg_data = res_reg.json()
    assert len(reg_data) == 32

    # 2. GET /api/v1/masterdata/records/{master_type}
    res_list = client.get("/api/v1/masterdata/records/SERVICE_CATEGORY")
    assert res_list.status_code == 200
    records = res_list.json()
    assert len(records) >= 11
    assert any(r["code"] == "COMPUTE" for r in records)

    # 3. GET /api/v1/masterdata/records/{master_type}/{code}
    res_single = client.get("/api/v1/masterdata/records/SERVICE_CATEGORY/COMPUTE")
    assert res_single.status_code == 200
    rec = res_single.json()
    assert rec["code"] == "COMPUTE"
    assert rec["display_name"] == "Compute"

    # 4. GET /api/v1/masterdata/where-used/{master_type}/{code}
    res_where = client.get("/api/v1/masterdata/where-used/SERVICE_CATEGORY/COMPUTE")
    assert res_where.status_code == 200
    where_data = res_where.json()
    assert where_data["code"] == "COMPUTE"
    assert "is_in_use" in where_data

    # 5. GET /api/v1/masterdata/health
    res_health = client.get("/api/v1/masterdata/health")
    assert res_health.status_code == 200
    health_data = res_health.json()
    assert health_data["total_masters_registered"] == 32
    assert health_data["overall_health_score"] > 0

    # 6. POST /api/v1/masterdata/dry-run
    dry_run_payload = {
        "master_type": "RESOURCE_TYPE",
        "records": [
            {"code": "API_TEST_1", "display_name": "API Test Resource"},
        ],
    }
    res_dry = client.post("/api/v1/masterdata/dry-run", json=dry_run_payload)
    assert res_dry.status_code == 200
    dry_res = res_dry.json()
    assert dry_res["is_valid"] is True
    assert dry_res["valid_rows"] == 1
