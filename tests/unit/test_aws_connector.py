"""Comprehensive Unit and Contract Tests for Amazon Web Services (AWS) Connector (Prompt 17 / BBP Section 14.3 & 15.4).

Validates:
1. Authentication: Cross-account IAM role assumption with mandatory ExternalId as recommended path;
   OIDC web identity federation (EKS IRSA); audited access keys exception.
   Root credentials and user console passwords strictly prohibited.
2. Pre-flight Permission Verification: Satisfies all 17 capabilities against AWS_PERMISSIONS.
3. Hierarchy Discovery: Single-pass Organizations tree with nested OUs and Account billing boundary.
4. Resource Inventory: Hybrid Tagging + Config with non-uniform coverage caveat and Unclassified typing.
5. Cost Ingestion: Export-first via CUR 2.0 (BCM Data Exports) in S3 with Cost Explorer fallback.
   Negative credits/refunds supported; idempotency verified.
6. Sizing Envelope: FinOps capacity calculation surfaces 10x-100x volume expansion for resource IDs.
7. AWS Cost Categories: Modeled as distinct native concept, strictly separated from tags.
8. Pricing Precedence: Bulk offer files (aws_v1) vs negotiated EDP discounts with strict precedence.
9. Budgets: AWS Budgets read for comparison only (never authoritative).
10. Usage Metrics: Coarse CloudWatch metrics (hourly PT1H / daily P1D); sub-minute intervals strictly rejected.
11. Relationships: Structural topology (ENI, EBS, VPC) declared as PARTIAL.
12. Boundary Safety: Conformance kit verification and fast-fail on undeclared capabilities.
"""

from __future__ import annotations

import pytest

from connectors.aws.auth import AWSAuthService
from connectors.aws.connector import AWSConnector
from connectors.aws.metrics import AWSMetricIntervalForbiddenException
from connectors.aws.models import (
    AWSAuthenticationException,
    AWSAuthMethod,
    AWSCredentials,
    AWSCURConfiguration,
    CURCompression,
    CURTimeGranularity,
    is_valid_aws_account_id,
)
from domain.models.enums import ConnectorCapability, ProviderType
from domain.models.exceptions import UndeclaredCapabilityException


@pytest.fixture
def aws_connector() -> AWSConnector:
    """Provides a standard AWSConnector instance for unit testing."""
    return AWSConnector(
        connector_id="conn-aws-test-01",
        tenant_id="tenant-test-01",
        config={
            "management_account_id": "112233445566",
            "credentials": {
                "management_account_id": "112233445566",
                "role_arn": "arn:aws:iam::112233445566:role/CloudLensCrossAccountRole",
                "external_id": "cloudlens-ext-tenant-test-01",
                "auth_method": AWSAuthMethod.ASSUME_ROLE.value,
            },
            "has_edp_entitlement": True,
        },
    )


# ==============================================================================
# 1. Authentication & Security Baselines
# ==============================================================================


@pytest.mark.asyncio
async def test_aws_auth_assume_role_recommended(aws_connector: AWSConnector):
    """Cross-account role assumption with ExternalId produces valid AuthResult."""
    auth_res = await aws_connector.authenticate()
    assert auth_res.authenticated is True
    assert auth_res.provider == ProviderType.AWS.value
    assert "arn:aws:iam::112233445566:role/CloudLensCrossAccountRole" in auth_res.identity
    assert auth_res.attributes["auth_method"] == AWSAuthMethod.ASSUME_ROLE.value
    assert auth_res.attributes["external_id_configured"] is True
    assert auth_res.attributes["token_type"] == "AWS-SigV4-AssumedRole"


@pytest.mark.asyncio
async def test_aws_auth_oidc_and_access_keys():
    """OIDC web identity federation and audited access key fallback work correctly."""
    # 1. OIDC Web Identity Federation (EKS IRSA)
    oidc_svc = AWSAuthService(
        AWSCredentials(
            management_account_id="112233445566",
            role_arn="arn:aws:iam::112233445566:role/CloudLensEksPodRole",
            auth_method=AWSAuthMethod.OIDC_FEDERATION,
            web_identity_token_path="/var/run/secrets/eks.amazonaws.com/serviceaccount/token",
        )
    )
    res_oidc = await oidc_svc.authenticate()
    assert res_oidc.authenticated is True
    assert res_oidc.attributes["auth_method"] == AWSAuthMethod.OIDC_FEDERATION.value

    # 2. Audited Access Keys exception
    ak_svc = AWSAuthService(
        AWSCredentials(
            management_account_id="112233445566",
            auth_method=AWSAuthMethod.ACCESS_KEYS,
            access_key_id="AKIAIOSFODNN7EXAMPLE",
            secret_access_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        )
    )
    res_ak = await ak_svc.authenticate()
    assert res_ak.authenticated is True
    assert "AKIA" in res_ak.attributes["access_key_id"]
    assert res_ak.attributes["secret_access_key"] == "***REDACTED***"
    assert "90-day" in res_ak.attributes["rotation_notice"]


def test_aws_auth_prohibits_root_and_passwords():
    """Enterprise security invariant: Root credentials and console passwords strictly raise error."""
    # 1. Prohibit root email credentials
    with pytest.raises(AWSAuthenticationException) as exc_root:
        AWSCredentials(
            management_account_id="112233445566",
            root_email="root@company.com",
        ).validate_security_invariants()
    assert exc_root.value.error_code == "FORBIDDEN_ROOT_CREDENTIALS"

    # 2. Prohibit user console password
    with pytest.raises(AWSAuthenticationException) as exc_pwd:
        AWSCredentials(
            management_account_id="112233445566",
            user_password="MasterAdminPassword123!",
        ).validate_security_invariants()
    assert exc_pwd.value.error_code == "FORBIDDEN_USER_PASSWORD"

    # 3. Missing ExternalId on AssumeRole fails
    with pytest.raises(AWSAuthenticationException) as exc_ext:
        AWSCredentials(
            management_account_id="112233445566",
            role_arn="arn:aws:iam::112233445566:role/SomeRole",
            auth_method=AWSAuthMethod.ASSUME_ROLE,
            external_id=None,
        ).validate_security_invariants()
    assert exc_ext.value.error_code == "MISSING_EXTERNAL_ID"


@pytest.mark.asyncio
async def test_aws_permission_preflight_validation(aws_connector: AWSConnector):
    """Pre-flight permission verification satisfies all 17 capabilities against AWS_PERMISSIONS."""
    perm_res = await aws_connector.validate_permissions()
    assert perm_res.valid is True
    assert perm_res.provider == ProviderType.AWS.value
    assert len(perm_res.capabilities) >= 17
    assert len(perm_res.missing_permissions) == 0


# ==============================================================================
# 2. Hierarchy Discovery (Single-Pass & OU Nesting)
# ==============================================================================


@pytest.mark.asyncio
async def test_aws_hierarchy_ou_nesting_and_billing_boundary(aws_connector: AWSConnector):
    """Constructs canonical scope tree preserving OU nesting; accounts serve as billing boundary."""
    hierarchy = await aws_connector.discover_hierarchy()
    assert len(hierarchy) >= 6

    # Verify Organization Root
    root_node = next(n for n in hierarchy if n["parent_id"] is None)
    assert root_node["native_type"] == "organizationRoot"
    assert root_node["scope_role"] == "ROOT_GROUP"
    assert root_node["ancestor_chain"] == []

    # Verify Nested Production OU
    ou_prod = next(n for n in hierarchy if n.get("native_details", {}).get("name") == "Production")
    assert ou_prod["native_type"] == "organizationalUnit"
    assert ou_prod["scope_role"] == "GROUP"
    assert len(ou_prod["ancestor_chain"]) >= 2  # Root -> Workloads -> Production

    # Verify Production Account node preserves OU nesting in scope path
    acc_prod = next(
        n
        for n in hierarchy
        if n.get("native_type") == "account" and n["scope_id"] == "223344556677"
    )
    assert acc_prod["scope_role"] == "BILLING_ACCOUNT"  # Account is the billing boundary
    assert "Production" in acc_prod["scope_path"]
    assert "Workloads" in acc_prod["scope_path"]
    assert acc_prod["parent_id"] == ou_prod["scope_id"]


@pytest.mark.asyncio
async def test_aws_discover_organizations_and_accounts(aws_connector: AWSConnector):
    """discover_organizations returns root, discover_accounts returns member accounts."""
    orgs = await aws_connector.discover_organizations()
    assert len(orgs) >= 1
    assert orgs[0]["native_type"] == "organizationRoot"

    accounts = await aws_connector.discover_accounts()
    assert len(accounts) >= 3
    assert all(a["native_type"] == "account" for a in accounts)
    assert all(a["scope_role"] == "BILLING_ACCOUNT" for a in accounts)

    # Filter accounts by parent
    ou_prod = next(
        n
        for n in await aws_connector.discover_hierarchy()
        if n.get("native_details", {}).get("name") == "Production"
    )
    prod_accounts = await aws_connector.discover_accounts(parent_id=ou_prod["scope_id"])
    assert len(prod_accounts) >= 2


def test_aws_account_id_validation():
    """Validates 12-digit AWS account ID regex."""
    assert is_valid_aws_account_id("112233445566") is True
    assert is_valid_aws_account_id("223344556677") is True
    assert is_valid_aws_account_id("12345") is False
    assert is_valid_aws_account_id("11223344556a") is False
    assert is_valid_aws_account_id("") is False


# ==============================================================================
# 3. Resource Inventory & Non-Uniform Coverage Caveat
# ==============================================================================


@pytest.mark.asyncio
async def test_aws_inventory_non_uniform_coverage_caveat(aws_connector: AWSConnector):
    """Resource inventory surfaces non-uniform coverage caveat; unsupported types marked Unclassified."""
    caveat = aws_connector.inventory_coverage_caveat
    assert "non-uniform service coverage" in caveat
    assert "is_unclassified=True" in caveat

    resources = await aws_connector.discover_resources()
    assert len(resources) >= 6

    # 1. Check supported EC2 instance
    ec2 = next(r for r in resources if r["native_type"] == "AWS::EC2::Instance")
    assert ec2["service_category"] == "COMPUTE"
    assert ec2["runtime_status"] == "RUNNING"
    assert ec2["is_unclassified"] is False

    # 2. Check unsupported AppSync GraphQL API (explicitly marked Unclassified)
    appsync = next(r for r in resources if r["native_type"] == "AWS::AppSync::GraphQLApi")
    assert appsync["is_unclassified"] is True
    assert appsync["native_type"] == "AWS::AppSync::GraphQLApi"  # Native type preserved
    assert "non-uniform coverage" in appsync["classification_reason"]


@pytest.mark.asyncio
async def test_aws_discover_services(aws_connector: AWSConnector):
    """discover_services groups active services and indicates uniform vs partial coverage."""
    services = await aws_connector.discover_services()
    assert len(services) >= 4
    svc_codes = [s["service_code"] for s in services]
    assert "ec2" in svc_codes
    assert "s3" in svc_codes
    assert "rds" in svc_codes
    assert "appsync" in svc_codes

    # AppSync is flagged with non-uniform coverage
    appsync_svc = next(s for s in services if s["service_code"] == "appsync")
    assert appsync_svc["is_uniform_coverage"] is False
    assert appsync_svc["coverage_caveat"] is not None


# ==============================================================================
# 4. Cost Ingestion & Sizing Envelope
# ==============================================================================


@pytest.mark.asyncio
async def test_aws_cost_bulk_cur_2_0_ingestion(aws_connector: AWSConnector):
    """Bulk ingestion parses CUR 2.0 export fixture with credit and usage records."""
    cost_records = await aws_connector.collect_cost_bulk()
    assert len(cost_records) >= 4

    # Standard usage record
    rec_ec2 = next(
        r for r in cost_records if r["product_code"] == "AmazonEC2" and r["unblended_cost"] > 0
    )
    assert rec_ec2["currency"] == "USD"
    assert rec_ec2["unblended_cost"] == 0.1664
    assert rec_ec2["is_estimated"] is False
    assert "Environment" in rec_ec2["tags"]

    # Credit/Refund record (negative unblended cost)
    rec_credit = next(r for r in cost_records if r["line_item_id"] == "aws-cur-line-0004")
    assert rec_credit["unblended_cost"] == -50.0
    assert rec_credit["usage_type"] == "Credit:Promotional"


@pytest.mark.asyncio
async def test_aws_cost_query_fallback(aws_connector: AWSConnector):
    """Cost Explorer query fallback returns interactive records marked is_estimated=True."""
    cost_records = await aws_connector.collect_cost_query()
    assert len(cost_records) >= 4
    for r in cost_records:
        assert r["is_estimated"] is True


@pytest.mark.asyncio
async def test_aws_cost_ingestion_idempotency(aws_connector: AWSConnector):
    """Cost ingestion is strictly idempotent across repeated runs."""
    run_1 = await aws_connector.collect_cost_bulk()
    run_2 = await aws_connector.collect_cost_bulk()
    assert len(run_1) == len(run_2)
    assert run_1 == run_2


def test_aws_cur_sizing_envelope_calculation():
    """FinOps sizing calculation surfaces 10x-100x row volume expansion when resource IDs are enabled."""
    cur_hourly_res = AWSCURConfiguration(
        time_granularity=CURTimeGranularity.HOURLY,
        include_resource_ids=True,
        compression=CURCompression.PARQUET_SNAPPY,
    )
    cur_daily_no_res = AWSCURConfiguration(
        time_granularity=CURTimeGranularity.DAILY,
        include_resource_ids=False,
        compression=CURCompression.PARQUET_SNAPPY,
    )

    resource_count = 500
    sizing_res = cur_hourly_res.estimate_sizing_envelope(resource_count)
    sizing_no_res = cur_daily_no_res.estimate_sizing_envelope(resource_count)

    # Hourly with resource IDs produces significantly higher volume (240x expansion factor)
    assert sizing_res["estimated_monthly_rows"] > sizing_no_res["estimated_monthly_rows"] * 50
    assert sizing_res["resource_ids_enabled"] is True
    assert sizing_res["recommended_ingestion_workers"] >= 1
    assert "Provision" in sizing_res["sizing_guidance"]


# ==============================================================================
# 5. AWS Cost Categories Distinction
# ==============================================================================


@pytest.mark.asyncio
async def test_aws_cost_categories_distinct_from_tags(aws_connector: AWSConnector):
    """AWS Cost Categories are modeled as distinct concepts and NEVER merged into tags."""
    # Check cost records have distinct cost_categories
    records = await aws_connector.collect_cost_bulk()
    for rec in records:
        assert isinstance(rec["cost_categories"], dict)
        assert len(rec["cost_categories"]) > 0
        # Cost categories must NOT be blended into resource tags
        for cat_key in rec["cost_categories"]:
            assert cat_key not in rec["tags"]

    # Check distinct cost categories collection endpoint
    categories = await aws_connector.collect_cost_categories()
    assert len(categories) >= 3
    cat_names = [c["category_name"] for c in categories]
    assert "BusinessUnit" in cat_names
    assert "EnvironmentTier" in cat_names


# ==============================================================================
# 6. Pricing Precedence (Bulk Offer vs EDP Discounts)
# ==============================================================================


@pytest.mark.asyncio
async def test_aws_pricing_bulk_and_edp_precedence(aws_connector: AWSConnector):
    """Public Price List bulk offer files vs negotiated EDP discounts with strict precedence."""
    sku_ec2 = "AWS-EC2-T3-XLARGE-US-EAST"

    # Public retail rate check
    public_rates = await aws_connector.collect_pricing_public()
    assert len(public_rates) >= 4
    ec2_public = next(r for r in public_rates if r["sku"] == sku_ec2)
    assert ec2_public["retail_price"] == 0.1664
    assert ec2_public["is_retail"] is True
    assert ec2_public["currency"] == "USD"

    # Negotiated EDP check
    negotiated_rates = await aws_connector.collect_pricing_negotiated()
    assert len(negotiated_rates) >= 4
    ec2_edp = next(r for r in negotiated_rates if r["sku"] == sku_ec2)
    assert ec2_edp["negotiated_price"] == 0.1331  # 20% EDP discount
    assert ec2_edp["is_negotiated"] is True

    # Precedence check: entitled connector resolves negotiated EDP rate as effective price
    quote = aws_connector.get_effective_pricing(sku_ec2)
    assert quote is not None
    assert quote.is_negotiated is True
    assert quote.is_retail is False
    assert quote.effective_price == 0.1331
    assert quote.pricing_source == "aws_edp_negotiated"

    # Non-entitled connector falls back to public retail rate
    non_entitled_connector = AWSConnector(
        connector_id="conn-aws-retail-only",
        tenant_id="tenant-test-02",
        config={"has_edp_entitlement": False},
    )
    quote_retail = non_entitled_connector.get_effective_pricing(sku_ec2)
    assert quote_retail is not None
    assert quote_retail.is_retail is True
    assert quote_retail.is_negotiated is False
    assert quote_retail.effective_price == 0.1664
    assert quote_retail.pricing_source == "aws_price_list_bulk"


# ==============================================================================
# 7. Budgets (Non-Authoritative Discipline)
# ==============================================================================


@pytest.mark.asyncio
async def test_aws_budgets_non_authoritative(aws_connector: AWSConnector):
    """AWS Budgets are ingested strictly for comparison; is_authoritative is False."""
    budgets = await aws_connector.collect_budgets()
    assert len(budgets) >= 2
    for b in budgets:
        assert b["is_authoritative"] is False
        assert b["budget_limit"] > 0
        assert b["time_unit"] == "MONTHLY"


# ==============================================================================
# 8. Usage Metrics & Sub-Minute Rejection
# ==============================================================================


@pytest.mark.asyncio
async def test_aws_metrics_coarse_intervals_and_subminute_rejection(aws_connector: AWSConnector):
    """Coarse intervals (PT1H / Period 3600, P1D / Period 86400) succeed; sub-minute rejected."""
    # Hourly succeeds
    metrics_hourly = await aws_connector.collect_usage(interval="PT1H")
    assert len(metrics_hourly) >= 1
    assert metrics_hourly[0]["period_seconds"] == 3600

    # Daily succeeds
    metrics_daily = await aws_connector.collect_usage(interval="P1D")
    assert len(metrics_daily) >= 1
    assert metrics_daily[0]["period_seconds"] == 86400

    # Sub-minute interval is strictly forbidden
    with pytest.raises(AWSMetricIntervalForbiddenException) as exc_subminute:
        await aws_connector.collect_usage(interval="PT1M")
    assert "AWS_METRIC_INTERVAL_FORBIDDEN" in str(exc_subminute.value.error_code)


# ==============================================================================
# 9. Multi-Tier Tags
# ==============================================================================


@pytest.mark.asyncio
async def test_aws_tags_collection(aws_connector: AWSConnector):
    """Tags are collected across AWS resources and indicate cost allocation tags."""
    tags = await aws_connector.collect_tags()
    assert len(tags) >= 5
    tag_keys = {t["key"] for t in tags}
    assert "Environment" in tag_keys
    assert "CostCenter" in tag_keys


# ==============================================================================
# 10. Structural Relationships (Declared Partial)
# ==============================================================================


@pytest.mark.asyncio
async def test_aws_relationships_structural_partial(aws_connector: AWSConnector):
    """Structural relationships derived (ENI, EBS, VPC) and capability declared partial."""
    rels = await aws_connector.discover_relationships()
    assert len(rels) >= 4
    rel_types = {r["relationship_type"] for r in rels}
    assert "NETWORK_INTERFACE" in rel_types
    assert "STORAGE_VOLUME" in rel_types
    assert "VPC_SUBNET" in rel_types
    assert "VPC_CONTAINMENT" in rel_types
    assert all(r["is_structural_only"] is True for r in rels)
    assert aws_connector.relationships_is_partial is True


# ==============================================================================
# 11. Boundary Safety & Undeclared Invocations
# ==============================================================================


def test_aws_undeclared_capability_fails_fast():
    """Connector with restricted capability set rejects undeclared invocations."""
    restricted_connector = AWSConnector(
        connector_id="conn-aws-restricted",
        tenant_id="tenant-test-01",
        declared_capabilities={ConnectorCapability.AUTHENTICATE, ConnectorCapability.HEALTH_STATUS},
    )

    assert restricted_connector.has_capability(ConnectorCapability.AUTHENTICATE) is True
    assert restricted_connector.has_capability(ConnectorCapability.COLLECT_COST_BULK) is False

    with pytest.raises(UndeclaredCapabilityException):
        restricted_connector._assert_declared(ConnectorCapability.COLLECT_COST_BULK)


@pytest.mark.asyncio
async def test_aws_provider_metadata_and_health(aws_connector: AWSConnector):
    """provider_metadata and health_status return correct AWS telemetry and metadata."""
    health = await aws_connector.health_status()
    assert health.healthy is True
    assert health.status_code == 200
    assert health.details["provider"] == ProviderType.AWS.value

    meta = await aws_connector.provider_metadata()
    assert meta.provider == ProviderType.AWS
    assert meta.api_version == "2023-11-26"
    assert "us-east-1" in meta.supported_regions
    assert meta.metadata["cur_2_0_supported"] is True
    assert meta.metadata["cost_categories_distinct"] is True
    assert meta.metadata["pricing_edp_precedence"] is True
    assert meta.metadata["relationships_partial"] is True
    assert meta.metadata["non_uniform_inventory_coverage"] is True
