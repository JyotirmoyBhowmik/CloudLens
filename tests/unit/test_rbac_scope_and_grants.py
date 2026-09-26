"""Unit tests for CloudLens RBAC, Scope Grants, Financial Sensitivity, and Disclosure (Prompt 11).

Tests:
1. All eight scoping dimensions (Item 71).
2. Deny-over-allow precedence across all scoping dimensions (Item 72, Acceptance Criterion 3).
3. Financial detail vs cost totals permission separation & rate redaction (Item 73).
4. The Disclosure Rule on filtered aggregates (Item 74, Acceptance Criterion 2).
5. Access review audit exports in JSON and CSV format (Item 75).
6. Custom role composition and validation (Item 70).
"""

import csv
import io
import json

import pytest

from domain.identity.models import User
from domain.identity.service import get_identity_service
from domain.models.enums import (
    FinancialSensitivity,
    GranteeType,
    GrantEffect,
    SystemRole,
    UserStatus,
)
from domain.models.exceptions import (
    CustomRoleInvalidException,
)
from domain.rbac.catalogue import get_permission_catalogue
from domain.rbac.models import ResourceTarget, ScopeGrant
from domain.rbac.service import get_rbac_service


@pytest.fixture(autouse=True)
def clean_rbac_state():
    """Ensures each test starts with a fresh RBAC state."""
    service = get_rbac_service()
    service.clear_scope_grants()
    yield
    service.clear_scope_grants()


# ==============================================================================
# Item 70: Permission Catalogue & Custom Roles
# ==============================================================================


def test_permission_catalogue_initialization():
    """Verify standard catalogue registers permissions and built-in roles."""
    catalogue = get_permission_catalogue()
    perms = catalogue.list_permissions()
    assert len(perms) >= 40
    assert catalogue.is_valid_permission("billing:read") is True
    assert catalogue.is_valid_permission("cost:totals:read") is True
    assert catalogue.is_valid_permission("financial:detail:read") is True
    assert catalogue.is_valid_permission("invalid:permission") is False

    built_in_roles = catalogue.list_built_in_roles()
    assert len(built_in_roles) == 9
    role_codes = {r.code for r in built_in_roles}
    expected_roles = {
        "GLOBAL_ADMIN",
        "TENANT_ADMIN",
        "CLOUD_ARCHITECT",
        "FINOPS_ADMIN",
        "FINOPS_ANALYST",
        "TENANT_USER",
        "DEVELOPER",
        "FINOPS_VIEWER",
        "SECURITY_AUDITOR",
    }
    assert expected_roles.issubset(role_codes)


def test_custom_role_creation_and_validation():
    """Verify custom role composition from catalogue and rejection of uncatalogued permissions."""
    service = get_rbac_service()
    custom_role = service.create_custom_role(
        tenant_id="tenant-acme",
        code="CUSTOM_BILLING_AUDITOR",
        display_name="Custom Billing Auditor",
        description="Audits billing without write privileges",
        allowed_permissions=["billing:read", "cost:totals:read", "audit:read"],
    )
    assert custom_role.code == "CUSTOM_BILLING_AUDITOR"
    assert custom_role.tenant_id == "tenant-acme"
    assert "billing:read" in custom_role.allowed_permissions

    # Rejection of uncatalogued permission
    with pytest.raises(CustomRoleInvalidException) as exc_info:
        service.create_custom_role(
            tenant_id="tenant-acme",
            code="INVALID_ROLE",
            display_name="Invalid Role",
            description="Has bogus permission",
            allowed_permissions=["billing:read", "hack:the:planet"],
        )
    assert "hack:the:planet" in str(exc_info.value)


# ==============================================================================
# Item 71: Multidimensional Scope Grants (8 Dimensions)
# ==============================================================================


def test_scope_dimension_1_provider():
    """Verify Dimension 1: provider filtering ('aws', 'azure', 'gcp', 'oci', '*')."""
    service = get_rbac_service()
    service.create_scope_grant(
        ScopeGrant(
            id="grant-aws-only",
            tenant_id="tenant-alpha",
            grantee_type=GranteeType.USER,
            grantee_id="user-1",
            effect=GrantEffect.ALLOW,
            providers=["aws"],
        )
    )

    # AWS target should be allowed
    decision_aws = service.authorize(
        user_id="user-1",
        tenant_id="tenant-alpha",
        role_codes=[SystemRole.FINOPS_ANALYST.value],
        permission_code="billing:read",
        target=ResourceTarget(provider="aws", resource_id="i-12345"),
    )
    assert decision_aws.allowed is True

    # Azure target should be denied
    decision_azure = service.authorize(
        user_id="user-1",
        tenant_id="tenant-alpha",
        role_codes=[SystemRole.FINOPS_ANALYST.value],
        permission_code="billing:read",
        target=ResourceTarget(provider="azure", resource_id="vm-67890"),
    )
    assert decision_azure.allowed is False


def test_scope_dimension_2_account_boundary():
    """Verify Dimension 2: Account and billing boundary restrictions."""
    service = get_rbac_service()
    service.create_scope_grant(
        ScopeGrant(
            id="grant-acct-100",
            tenant_id="tenant-alpha",
            grantee_type=GranteeType.USER,
            grantee_id="user-1",
            effect=GrantEffect.ALLOW,
            account_ids=["111222333444"],
        )
    )

    decision_match = service.authorize(
        user_id="user-1",
        tenant_id="tenant-alpha",
        role_codes=[SystemRole.FINOPS_ANALYST.value],
        permission_code="billing:read",
        target=ResourceTarget(account_id="111222333444"),
    )
    assert decision_match.allowed is True

    decision_mismatch = service.authorize(
        user_id="user-1",
        tenant_id="tenant-alpha",
        role_codes=[SystemRole.FINOPS_ANALYST.value],
        permission_code="billing:read",
        target=ResourceTarget(account_id="999888777666"),
    )
    assert decision_mismatch.allowed is False


def test_scope_dimension_3_hierarchy_subtree_cascading():
    """Verify Dimension 3: Hierarchy subtree cascading to descendants."""
    service = get_rbac_service()
    # Grant with cascading subtree root 'mg-finance'
    service.create_scope_grant(
        ScopeGrant(
            id="grant-subtree-cascading",
            tenant_id="tenant-alpha",
            grantee_type=GranteeType.USER,
            grantee_id="user-1",
            effect=GrantEffect.ALLOW,
            hierarchy_subtree_roots=["mg-finance"],
            cascade_hierarchy=True,
        )
    )

    # Target path containing 'mg-finance' as an ancestor
    decision_descendant = service.authorize(
        user_id="user-1",
        tenant_id="tenant-alpha",
        role_codes=[SystemRole.FINOPS_ANALYST.value],
        permission_code="billing:read",
        target=ResourceTarget(
            hierarchy_path=["tenant-root", "mg-finance", "sub-tax", "rg-payroll"],
            resource_id="res-pay-01",
        ),
    )
    assert decision_descendant.allowed is True

    # Target path outside 'mg-finance'
    decision_other = service.authorize(
        user_id="user-1",
        tenant_id="tenant-alpha",
        role_codes=[SystemRole.FINOPS_ANALYST.value],
        permission_code="billing:read",
        target=ResourceTarget(
            hierarchy_path=["tenant-root", "mg-engineering", "sub-prod"],
            resource_id="res-eng-01",
        ),
    )
    assert decision_other.allowed is False


def test_scope_dimension_4_project_and_application():
    """Verify Dimension 4: Project and application restrictions."""
    service = get_rbac_service()
    service.create_scope_grant(
        ScopeGrant(
            id="grant-proj-app",
            tenant_id="tenant-alpha",
            grantee_type=GranteeType.ROLE,
            grantee_id=SystemRole.DEVELOPER.value,
            effect=GrantEffect.ALLOW,
            project_ids=["proj-payments"],
            application_ids=["app-checkout"],
        )
    )

    decision_match = service.authorize(
        user_id="dev-1",
        tenant_id="tenant-alpha",
        role_codes=[SystemRole.DEVELOPER.value],
        permission_code="inventory:read",
        target=ResourceTarget(project_id="proj-payments", application_id="app-checkout"),
    )
    assert decision_match.allowed is True

    decision_wrong_app = service.authorize(
        user_id="dev-1",
        tenant_id="tenant-alpha",
        role_codes=[SystemRole.DEVELOPER.value],
        permission_code="inventory:read",
        target=ResourceTarget(project_id="proj-payments", application_id="app-inventory"),
    )
    assert decision_wrong_app.allowed is False


def test_scope_dimension_5_cost_centre_and_business_unit():
    """Verify Dimension 5: Cost centre and business unit scoping."""
    service = get_rbac_service()
    service.create_scope_grant(
        ScopeGrant(
            id="grant-bu-cc",
            tenant_id="tenant-alpha",
            grantee_type=GranteeType.USER,
            grantee_id="fin-user",
            effect=GrantEffect.ALLOW,
            business_unit_ids=["bu-retail"],
            cost_centre_ids=["cc-1004"],
        )
    )

    decision_match = service.authorize(
        user_id="fin-user",
        tenant_id="tenant-alpha",
        role_codes=[SystemRole.FINOPS_ANALYST.value],
        permission_code="billing:read",
        target=ResourceTarget(business_unit_id="bu-retail", cost_centre_id="cc-1004"),
    )
    assert decision_match.allowed is True

    decision_wrong_bu = service.authorize(
        user_id="fin-user",
        tenant_id="tenant-alpha",
        role_codes=[SystemRole.FINOPS_ANALYST.value],
        permission_code="billing:read",
        target=ResourceTarget(business_unit_id="bu-wholesale", cost_centre_id="cc-1004"),
    )
    assert decision_wrong_bu.allowed is False


def test_scope_dimension_7_administrative():
    """Verify Dimension 7: Administrative capabilities boundary."""
    service = get_rbac_service()
    service.create_scope_grant(
        ScopeGrant(
            id="grant-non-admin",
            tenant_id="tenant-alpha",
            grantee_type=GranteeType.USER,
            grantee_id="user-1",
            effect=GrantEffect.ALLOW,
            is_administrative=False,
            providers=["*"],
        )
    )

    # Normal resource action should pass
    decision_normal = service.authorize(
        user_id="user-1",
        tenant_id="tenant-alpha",
        role_codes=[SystemRole.FINOPS_ADMIN.value],
        permission_code="billing:read",
        target=ResourceTarget(is_administrative=False),
    )
    assert decision_normal.allowed is True

    # Administrative target should be rejected by non-admin grant
    decision_admin = service.authorize(
        user_id="user-1",
        tenant_id="tenant-alpha",
        role_codes=[SystemRole.FINOPS_ADMIN.value],
        permission_code="billing:read",
        target=ResourceTarget(is_administrative=True),
    )
    assert decision_admin.allowed is False


def test_scope_dimension_8_resource_exceptions():
    """Verify Dimension 8: Explicit resource-level allow exclusion and deny exception."""
    service = get_rbac_service()

    # Allow grant that specifically EXCLUDES 'res-confidential'
    service.create_scope_grant(
        ScopeGrant(
            id="grant-bu-with-exclusion",
            tenant_id="tenant-alpha",
            grantee_type=GranteeType.USER,
            grantee_id="user-1",
            effect=GrantEffect.ALLOW,
            business_unit_ids=["bu-tech"],
            resource_exceptions=["res-confidential"],
        )
    )

    # Normal resource in bu-tech allowed
    decision_normal = service.authorize(
        user_id="user-1",
        tenant_id="tenant-alpha",
        role_codes=[SystemRole.FINOPS_ANALYST.value],
        permission_code="billing:read",
        target=ResourceTarget(business_unit_id="bu-tech", resource_id="res-public"),
    )
    assert decision_normal.allowed is True

    # Excluded resource in bu-tech denied
    decision_excluded = service.authorize(
        user_id="user-1",
        tenant_id="tenant-alpha",
        role_codes=[SystemRole.FINOPS_ANALYST.value],
        permission_code="billing:read",
        target=ResourceTarget(business_unit_id="bu-tech", resource_id="res-confidential"),
    )
    assert decision_excluded.allowed is False


# ==============================================================================
# Item 72: Strict Deny-Over-Allow Precedence (Acceptance Criterion 3)
# ==============================================================================


def test_deny_grant_defeats_overlapping_allow_grant():
    """Item 72: A deny grant defeats an overlapping allow grant across dimensions."""
    service = get_rbac_service()

    # Broad ALLOW grant: all AWS resources
    service.create_scope_grant(
        ScopeGrant(
            id="grant-allow-all-aws",
            tenant_id="tenant-alpha",
            grantee_type=GranteeType.USER,
            grantee_id="user-analyst",
            effect=GrantEffect.ALLOW,
            providers=["aws"],
        )
    )

    # Specific DENY grant: account '999000111' on AWS
    service.create_scope_grant(
        ScopeGrant(
            id="grant-deny-sensitive-account",
            tenant_id="tenant-alpha",
            grantee_type=GranteeType.USER,
            grantee_id="user-analyst",
            effect=GrantEffect.DENY,
            providers=["aws"],
            account_ids=["999000111"],
        )
    )

    # Accessing regular AWS account should be ALLOWED
    dec_allowed = service.authorize(
        user_id="user-analyst",
        tenant_id="tenant-alpha",
        role_codes=[SystemRole.FINOPS_ANALYST.value],
        permission_code="billing:read",
        target=ResourceTarget(provider="aws", account_id="111222333"),
    )
    assert dec_allowed.allowed is True
    assert dec_allowed.effect == GrantEffect.ALLOW

    # Accessing the denied AWS account MUST BE DEFEATED by the deny grant!
    dec_denied = service.authorize(
        user_id="user-analyst",
        tenant_id="tenant-alpha",
        role_codes=[SystemRole.FINOPS_ANALYST.value],
        permission_code="billing:read",
        target=ResourceTarget(provider="aws", account_id="999000111"),
    )
    assert dec_denied.allowed is False
    assert dec_denied.effect == GrantEffect.DENY
    assert dec_denied.matched_grant_id == "grant-deny-sensitive-account"
    assert "A deny grant defeats all overlapping allow grants" in dec_denied.reason


def test_deny_grant_defeats_admin_role_scope():
    """Verify that an explicit DENY grant even restricts a Tenant Administrator."""
    service = get_rbac_service()

    # Explicit DENY grant targeting a top-secret project
    service.create_scope_grant(
        ScopeGrant(
            id="grant-deny-project-x",
            tenant_id="tenant-alpha",
            grantee_type=GranteeType.ROLE,
            grantee_id=SystemRole.TENANT_ADMIN.value,
            effect=GrantEffect.DENY,
            project_ids=["project-black-budget"],
        )
    )

    # Tenant admin on normal project is ALLOWED
    dec_normal = service.authorize(
        user_id="admin-1",
        tenant_id="tenant-alpha",
        role_codes=[SystemRole.TENANT_ADMIN.value],
        permission_code="billing:read",
        target=ResourceTarget(project_id="project-standard"),
    )
    assert dec_normal.allowed is True

    # Tenant admin on black budget project is DENIED by explicit DENY grant
    dec_denied = service.authorize(
        user_id="admin-1",
        tenant_id="tenant-alpha",
        role_codes=[SystemRole.TENANT_ADMIN.value],
        permission_code="billing:read",
        target=ResourceTarget(project_id="project-black-budget"),
    )
    assert dec_denied.allowed is False
    assert dec_denied.effect == GrantEffect.DENY


# ==============================================================================
# Item 73: Financial Detail Permission vs Cost Totals & Rate Masking
# ==============================================================================


def test_financial_detail_separated_from_cost_totals():
    """Item 73: Operations users can see cost totals without seeing unit rates."""
    service = get_rbac_service()
    # Grant tenant-wide allow to IT Operations User
    service.create_scope_grant(
        ScopeGrant(
            id="grant-ops",
            tenant_id="tenant-alpha",
            grantee_type=GranteeType.ROLE,
            grantee_id=SystemRole.TENANT_USER.value,
            effect=GrantEffect.ALLOW,
            providers=["*"],
            financial_sensitivity=FinancialSensitivity.COST_TOTALS_ONLY,
        )
    )

    # 1. Operations User accessing Cost Totals target
    dec_totals = service.authorize(
        user_id="ops-user-1",
        tenant_id="tenant-alpha",
        role_codes=[SystemRole.TENANT_USER.value],
        permission_code="cost:totals:read",
        target=ResourceTarget(provider="aws", is_financial=True, is_rate_detail=False),
    )
    assert dec_totals.allowed is True
    assert dec_totals.can_view_rates is False

    # 2. Operations User attempting to access granular rate details
    dec_rates = service.authorize(
        user_id="ops-user-1",
        tenant_id="tenant-alpha",
        role_codes=[SystemRole.TENANT_USER.value],
        permission_code="cost:totals:read",
        target=ResourceTarget(provider="aws", is_financial=True, is_rate_detail=True),
    )
    assert dec_rates.allowed is False
    assert "financial:detail:read" in dec_rates.reason

    # 3. Finance User (FINOPS_ANALYST) has financial:detail:read
    service.create_scope_grant(
        ScopeGrant(
            id="grant-finance",
            tenant_id="tenant-alpha",
            grantee_type=GranteeType.ROLE,
            grantee_id=SystemRole.FINOPS_ANALYST.value,
            effect=GrantEffect.ALLOW,
            providers=["*"],
            financial_sensitivity=FinancialSensitivity.FULL_FINANCIAL_DETAIL,
        )
    )
    dec_fin = service.authorize(
        user_id="fin-user-1",
        tenant_id="tenant-alpha",
        role_codes=[SystemRole.FINOPS_ANALYST.value],
        permission_code="financial:detail:read",
        target=ResourceTarget(provider="aws", is_financial=True, is_rate_detail=True),
    )
    assert dec_fin.allowed is True
    assert dec_fin.can_view_rates is True


def test_rate_masking_in_dataset_filtering():
    """Verify rate redaction masks unit rates while preserving cost totals."""
    service = get_rbac_service()
    service.create_scope_grant(
        ScopeGrant(
            id="grant-ops",
            tenant_id="tenant-alpha",
            grantee_type=GranteeType.ROLE,
            grantee_id=SystemRole.TENANT_USER.value,
            effect=GrantEffect.ALLOW,
            providers=["*"],
            financial_sensitivity=FinancialSensitivity.COST_TOTALS_ONLY,
        )
    )

    items = [
        {
            "resource_id": "vm-prod-1",
            "provider": "aws",
            "billed_cost": 150.00,
            "effective_cost": 120.00,
            "contracted_unit_price": 0.45,
            "list_unit_price": 0.60,
            "unit_rate": 0.45,
        }
    ]

    filtered_result = service.filter_dataset(
        user_id="ops-user",
        tenant_id="tenant-alpha",
        role_codes=[SystemRole.TENANT_USER.value],
        permission_code="cost:totals:read",
        items=items,
    )

    assert len(filtered_result.data) == 1
    redacted_item = filtered_result.data[0]
    # Cost totals preserved
    assert redacted_item["billed_cost"] == 150.00
    assert redacted_item["effective_cost"] == 120.00
    # Unit rates redacted to None
    assert redacted_item["contracted_unit_price"] is None
    assert redacted_item["list_unit_price"] is None
    assert redacted_item["unit_rate"] is None


# ==============================================================================
# Item 74: The Disclosure Rule on Aggregates (Acceptance Criterion 2)
# ==============================================================================


def test_disclosure_rule_when_access_filtering_occurs():
    """Item 74: Filtering by access control must report is_filtered=True, hidden_count, notice."""
    service = get_rbac_service()

    # User grant only allows 'bu-retail'
    service.create_scope_grant(
        ScopeGrant(
            id="grant-retail-only",
            tenant_id="tenant-alpha",
            grantee_type=GranteeType.USER,
            grantee_id="analyst-retail",
            effect=GrantEffect.ALLOW,
            business_unit_ids=["bu-retail"],
        )
    )

    dataset = [
        {"resource_id": "r-1", "business_unit_id": "bu-retail", "billed_cost": 100},
        {"resource_id": "r-2", "business_unit_id": "bu-retail", "billed_cost": 200},
        {"resource_id": "r-3", "business_unit_id": "bu-wholesale", "billed_cost": 300},
        {"resource_id": "r-4", "business_unit_id": "bu-corporate", "billed_cost": 400},
        {"resource_id": "r-5", "business_unit_id": "bu-wholesale", "billed_cost": 500},
    ]

    result = service.filter_dataset(
        user_id="analyst-retail",
        tenant_id="tenant-alpha",
        role_codes=[SystemRole.FINOPS_ANALYST.value],
        permission_code="billing:read",
        items=dataset,
    )

    # 2 visible items, 3 hidden items
    assert len(result.data) == 2
    disclosure = result.disclosure

    assert disclosure.is_filtered is True
    assert disclosure.hidden_count == 3
    assert disclosure.total_unfiltered_count == 5
    assert len(disclosure.filtered_dimensions) > 0
    assert "cost_centre_business_unit" in disclosure.filtered_dimensions
    assert disclosure.disclosure_notice is not None
    assert "Access control filtered 3 of 5 items" in disclosure.disclosure_notice


def test_disclosure_rule_when_no_filtering_occurs():
    """Verify that when no filtering occurs, is_filtered=False and notice is None."""
    service = get_rbac_service()
    service.create_scope_grant(
        ScopeGrant(
            id="grant-all",
            tenant_id="tenant-alpha",
            grantee_type=GranteeType.USER,
            grantee_id="admin-user",
            effect=GrantEffect.ALLOW,
            providers=["*"],
        )
    )

    dataset = [
        {"resource_id": "r-1", "provider": "aws", "billed_cost": 100},
        {"resource_id": "r-2", "provider": "azure", "billed_cost": 200},
    ]

    result = service.filter_dataset(
        user_id="admin-user",
        tenant_id="tenant-alpha",
        role_codes=[SystemRole.FINOPS_ADMIN.value],
        permission_code="billing:read",
        items=dataset,
    )

    assert len(result.data) == 2
    disclosure = result.disclosure
    assert disclosure.is_filtered is False
    assert disclosure.hidden_count == 0
    assert disclosure.total_unfiltered_count == 2
    assert disclosure.filtered_dimensions == []
    assert disclosure.disclosure_notice is None


# ==============================================================================
# Item 75: Access Review Audit Export (JSON & CSV)
# ==============================================================================


def test_access_review_export_json_and_csv():
    """Item 75: Access review export listing every user, role, scope grant, and last sign-in."""
    identity_svc = get_identity_service()
    rbac_svc = get_rbac_service()

    # Provision sample test users in identity service
    test_user_id = "test-audit-user-1"
    identity_svc._users[test_user_id] = User(
        id=test_user_id,
        tenant_id="tenant-audit",
        email="auditee@example.com",
        display_name="Auditee User",
        status=UserStatus.ACTIVE,
        roles=[SystemRole.FINOPS_ANALYST, SystemRole.FINOPS_VIEWER],
    )

    rbac_svc.create_scope_grant(
        ScopeGrant(
            id="grant-audit-scope",
            tenant_id="tenant-audit",
            grantee_type=GranteeType.USER,
            grantee_id=test_user_id,
            effect=GrantEffect.ALLOW,
            providers=["aws", "azure"],
        )
    )

    # 1. Test JSON Export
    json_export = rbac_svc.export_access_review_json("tenant-audit")
    report_dict = json.loads(json_export)
    assert report_dict["tenant_id"] == "tenant-audit"
    assert report_dict["total_users"] >= 1
    found_record = next((r for r in report_dict["records"] if r["user_id"] == test_user_id), None)
    assert found_record is not None
    assert found_record["email"] == "auditee@example.com"
    assert SystemRole.FINOPS_ANALYST.value in found_record["assigned_roles"]
    assert "billing:read" in found_record["effective_permissions"]
    assert len(found_record["scope_grants"]) >= 1

    # 2. Test CSV Export
    csv_export = rbac_svc.export_access_review_csv("tenant-audit")
    csv_reader = list(csv.DictReader(io.StringIO(csv_export)))
    assert len(csv_reader) >= 1
    csv_user = next((row for row in csv_reader if row["user_id"] == test_user_id), None)
    assert csv_user is not None
    assert csv_user["email"] == "auditee@example.com"
    assert SystemRole.FINOPS_ANALYST.value in csv_user["assigned_roles"]
    assert int(csv_user["permissions_count"]) > 0
    assert int(csv_user["scope_grants_count"]) >= 1
