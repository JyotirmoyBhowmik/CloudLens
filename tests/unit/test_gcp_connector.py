"""Comprehensive Unit and Contract Tests for Google Cloud Platform (GCP) Connector (Prompt 18 / BBP Section 14.4 & 15.4).

Validates:
1. Authentication: Service Account with Workload Identity Federation (WIF) as recommended path;
   audited service account key JSON exception; API key for catalog.
   Interactive user passwords and personal gcloud auth tokens strictly prohibited.
2. Pre-flight Permission Verification: Satisfies all 17 capabilities against GCP_PERMISSIONS.
3. Hierarchy Discovery: Strict dual representation of resource hierarchy (org -> folders -> projects)
   and billing hierarchy (billingAccounts), preserving folder nesting in canonical scope paths.
   Billing accounts are never conflated as parents or children of folders.
4. Resource Inventory: Cloud Asset Inventory with normalization for camelCase/snake_case and
   handling of null values in frequently changing fields.
5. Cost Ingestion: BigQuery Cloud Billing export (Detailed, Standard, Pricing, FOCUS).
   Tracks and surfaces running BigQuery query cost ($5.00/TB on-demand, 10MB minimum).
   Negative line items (credits, SUDs, adjustments) supported.
6. Onboarding Wizard: Permanent warning that billing export history starts at enablement.
7. Pricing: Cloud Billing Catalog API public rates vs account-specific contract pricing with strict precedence.
8. Usage Metrics: Coarse Cloud Monitoring aggregates (hourly PT1H / daily P1D); sub-minute intervals strictly rejected.
9. Tags: Label collection with explicit source tier (LABEL_SOURCE_PROJECT vs LABEL_SOURCE_RESOURCE).
10. Relationships: Dynamic runtime probe of RELATIONSHIP content type, declared as PARTIAL.
11. Budgets: Non-authoritative Cloud Billing Budgets (is_authoritative = False); silent Pub/Sub creation prohibited.
12. Boundary Safety: Conformance kit verification and fast-fail on undeclared capabilities.
"""

from __future__ import annotations

import pytest

from connectors.gcp.auth import GCPAuthService
from connectors.gcp.budgets import GCPBudgetService
from connectors.gcp.connector import (
    GCPConnector,
)
from connectors.gcp.models import (
    GCPAuthenticationException,
    GCPAuthMethod,
    GCPBigQueryExportType,
    GCPBigQueryQueryCost,
    GCPCredentials,
    GCPMetricIntervalForbiddenException,
    GCPPubSubSilentCreationForbiddenException,
    is_valid_gcp_billing_account_id,
)
from connectors.gcp.pricing import GCPPricingService
from connectors.gcp.relationships import GCPRelationshipService
from connectors.wizard.service import OnboardingWizardService
from domain.models.enums import ConnectorCapability, ProviderType
from domain.models.exceptions import UndeclaredCapabilityException
from domain.tenant.context import TenantContext


@pytest.fixture
def gcp_connector() -> GCPConnector:
    """Provides a standard GCPConnector instance for unit testing."""
    return GCPConnector(
        connector_id="conn-gcp-test-01",
        tenant_id="tenant-test-01",
        config={
            "project_id": "proj-cloudlens-core",
            "organization_id": "1092837465",
            "billing_account_id": "01ABCD-2345EF-6789GH",
            "credentials": {
                "project_id": "proj-cloudlens-core",
                "auth_method": GCPAuthMethod.WORKLOAD_IDENTITY.value,
                "service_account_email": "cloudlens-sa@proj-cloudlens-core.iam.gserviceaccount.com",
                "workload_identity_pool": "projects/1092837465/locations/global/workloadIdentityPools/cloudlens-pool",
                "workload_identity_provider": "providers/cloudlens-k8s-provider",
            },
            "has_contract_entitlement": True,
        },
    )


# ==============================================================================
# 1. Authentication & Security Baselines
# ==============================================================================


@pytest.mark.asyncio
async def test_gcp_auth_workload_identity_recommended(gcp_connector: GCPConnector):
    """Workload Identity Federation produces valid AuthResult with keyless OIDC attributes."""
    auth_res = await gcp_connector.authenticate()
    assert auth_res.authenticated is True
    assert auth_res.provider == ProviderType.GCP.value
    assert "cloudlens-sa@proj-cloudlens-core.iam.gserviceaccount.com" in auth_res.identity
    assert auth_res.attributes["auth_method"] == GCPAuthMethod.WORKLOAD_IDENTITY.value
    assert "workloadIdentityPools/cloudlens-pool" in auth_res.attributes["workload_identity_pool"]
    assert auth_res.attributes["token_type"] == "Bearer"


@pytest.mark.asyncio
async def test_gcp_auth_service_account_key_and_api_key():
    """Service account key JSON exception and API key catalog lookups work correctly."""
    # 1. Audited Service Account Key JSON
    sa_key_svc = GCPAuthService(
        GCPCredentials(
            project_id="proj-cloudlens-core",
            auth_method=GCPAuthMethod.SERVICE_ACCOUNT_KEY,
            service_account_email="cloudlens-key@proj-cloudlens-core.iam.gserviceaccount.com",
            service_account_key_json='{"type": "service_account", "project_id": "proj-cloudlens-core"}',
        )
    )
    res_key = await sa_key_svc.authenticate()
    assert res_key.authenticated is True
    assert res_key.attributes["key_type"] == "SERVICE_ACCOUNT_KEY_JSON"
    assert "90-day" in res_key.attributes["rotation_notice"]

    # 2. Public Catalog API Key
    api_key_svc = GCPAuthService(
        GCPCredentials(
            project_id="proj-cloudlens-core",
            auth_method=GCPAuthMethod.API_KEY,
            api_key="AIzaSyD-TEST-GCP-CATALOG-KEY",
        )
    )
    res_api_key = await api_key_svc.authenticate()
    assert res_api_key.authenticated is True
    assert (
        res_api_key.attributes["scope_restriction"] == "Cloud Billing Catalog API public rates only"
    )


def test_gcp_auth_prohibits_passwords_and_personal_tokens():
    """Enterprise security invariant: User console passwords and personal gcloud auth tokens raise error."""
    # 1. Prohibit user console password
    with pytest.raises(GCPAuthenticationException) as exc_pwd:
        GCPCredentials(
            project_id="proj-cloudlens-core",
            user_password="MasterAdminPassword123!",
        ).validate_security_invariants()
    assert exc_pwd.value.error_code == "FORBIDDEN_USER_CREDENTIALS"

    # 2. Prohibit personal gcloud auth oauth token
    with pytest.raises(GCPAuthenticationException) as exc_token:
        GCPCredentials(
            project_id="proj-cloudlens-core",
            user_oauth_token="ya29.a0AfH6SMA-test-personal-token",
        ).validate_security_invariants()
    assert exc_token.value.error_code == "FORBIDDEN_USER_CREDENTIALS"


@pytest.mark.asyncio
async def test_gcp_permission_preflight_validation(gcp_connector: GCPConnector):
    """Pre-flight permission verification satisfies all 17 capabilities against GCP_PERMISSIONS."""
    perm_res = await gcp_connector.validate_permissions()
    assert perm_res.valid is True
    assert perm_res.provider == ProviderType.GCP.value
    assert len(perm_res.capabilities) >= 17
    assert len(perm_res.missing_permissions) == 0


# ==============================================================================
# 2. Dual Hierarchy Discovery (Resource vs Billing Separation & Folder Nesting)
# ==============================================================================


@pytest.mark.asyncio
async def test_gcp_hierarchy_dual_representation_and_folder_nesting(gcp_connector: GCPConnector):
    """Preserves folder nesting in resource hierarchy and models billing accounts as distinct linked scopes."""
    hierarchy = await gcp_connector.discover_hierarchy()
    assert len(hierarchy) >= 8

    # 1. Verify Organization Root
    org_node = next(n for n in hierarchy if n["native_type"] == "organization")
    assert org_node["scope_role"] == "ROOT_GROUP"
    assert org_node["hierarchy_type"] == "RESOURCE"
    assert org_node["parent_id"] is None

    # 2. Verify Nested Folder: workloads -> retail-banking
    folder_retail = next(
        n
        for n in hierarchy
        if n.get("native_type") == "folder" and n["scope_id"] == "folders/9876543210"
    )
    assert folder_retail["scope_role"] == "GROUP"
    assert folder_retail["parent_id"] == "folders/4444555566"
    assert len(folder_retail["ancestor_chain"]) >= 2  # Organization -> workloads -> retail-banking

    # 3. Verify Project: preserves folder nesting in scope path
    proj_retail = next(
        n
        for n in hierarchy
        if n.get("native_type") == "project" and "proj-retail-banking-prod" in n["scope_id"]
    )
    assert proj_retail["scope_role"] == "BILLING_BOUNDARY"
    assert "folders/4444555566" in proj_retail["scope_path"]
    assert "folders/9876543210" in proj_retail["scope_path"]
    assert proj_retail["linked_billing_account_id"] == "billingAccounts/01ABCD-2345EF-6789GH"

    # 4. STRICT ARCHITECTURAL INVARIANT: Billing Account is a distinct linked root scope, NOT a child of folders
    billing_node = next(n for n in hierarchy if n.get("native_type") == "billingAccount")
    assert billing_node["scope_role"] == "BILLING_ACCOUNT"
    assert billing_node["hierarchy_type"] == "BILLING"
    assert billing_node["parent_id"] is None  # Never parented by folders or organizations
    assert "proj-retail-banking-prod" in str(billing_node["linked_projects"])


@pytest.mark.asyncio
async def test_gcp_discover_organizations_and_accounts(gcp_connector: GCPConnector):
    """discover_organizations returns organization and billing accounts; discover_accounts returns projects."""
    orgs = await gcp_connector.discover_organizations()
    assert len(orgs) >= 2
    roles = [o["scope_role"] for o in orgs]
    assert "ROOT_GROUP" in roles
    assert "BILLING_ACCOUNT" in roles

    accounts = await gcp_connector.discover_accounts()
    assert len(accounts) >= 4
    for acc in accounts:
        assert acc["scope_role"] in ("BILLING_BOUNDARY", "BILLING_ACCOUNT")

    # Filter by parent folder
    retail_accounts = await gcp_connector.discover_accounts(parent_id="folders/9876543210")
    assert len(retail_accounts) >= 1
    assert "proj-retail-banking-prod" in retail_accounts[0]["scope_id"]


def test_gcp_billing_account_id_validation():
    """Validates 18-character hex GCP billing account ID format."""
    assert is_valid_gcp_billing_account_id("01ABCD-2345EF-6789GH") is True
    assert is_valid_gcp_billing_account_id("123456-7890AB-CDEF01") is True
    assert is_valid_gcp_billing_account_id("invalid-format") is False
    assert is_valid_gcp_billing_account_id("01ABCD2345EF6789GH") is False
    assert is_valid_gcp_billing_account_id("") is False


# ==============================================================================
# 3. Resource Inventory & Cloud Asset Inventory Normalization
# ==============================================================================


@pytest.mark.asyncio
async def test_gcp_inventory_casing_and_null_field_handling(gcp_connector: GCPConnector):
    """Handles Cloud Asset Inventory constraints: camelCase normalized, null fields acknowledged."""
    caveat = gcp_connector.inventory_coverage_caveat
    assert "exports only to Google Cloud Storage (GCS) or BigQuery" in caveat
    assert "Frequently changing fields" in caveat

    resources = await gcp_connector.discover_resources()
    assert len(resources) >= 5

    # 1. Compute VM instance
    vm = next(r for r in resources if r["asset_type"] == "compute.googleapis.com/Instance")
    assert vm["service_category"] == "COMPUTE"
    assert vm["runtime_status"] == "RUNNING"
    assert vm["has_null_frequently_changing_fields"] is True
    assert vm["properties"]["last_start_timestamp"] is None  # Handled null field
    assert vm["properties"]["machine_type"] == "n2-standard-4"  # Normalized property

    # 2. Cloud Storage Bucket
    bucket = next(r for r in resources if r["asset_type"] == "storage.googleapis.com/Bucket")
    assert bucket["service_category"] == "STORAGE"

    # 3. BigQuery Table
    bq = next(r for r in resources if r["asset_type"] == "bigquery.googleapis.com/Table")
    assert bq["service_category"] == "DATABASE"


@pytest.mark.asyncio
async def test_gcp_discover_services(gcp_connector: GCPConnector):
    """discover_services enumerates enabled GCP APIs via Service Usage."""
    services = await gcp_connector.discover_services()
    assert len(services) >= 5
    svc_names = [s["service_name"] for s in services]
    assert "compute.googleapis.com" in svc_names
    assert "storage.googleapis.com" in svc_names
    assert "bigquery.googleapis.com" in svc_names


# ==============================================================================
# 4. BigQuery Export Cost Ingestion & Query Cost Accounting
# ==============================================================================


@pytest.mark.asyncio
async def test_gcp_cost_bulk_ingestion_and_query_cost_accounting(gcp_connector: GCPConnector):
    """Ingests BigQuery billing export, handles credits/adjustments, and tracks query cost ($5/TB)."""
    cost_res = await gcp_connector.collect_cost_bulk(
        start_date="2026-09-01",
        end_date="2026-09-27",
    )
    assert len(cost_res) >= 4

    # Verify Compute Engine row with Sustained Usage Discount (SUD) credit
    vm_cost = next(r for r in cost_res if r["service_description"] == "Compute Engine")
    assert vm_cost["cost"] > 0
    assert len(vm_cost["credits"]) >= 1
    assert vm_cost["credits"][0]["type"] == "SUSTAINED_USAGE_DISCOUNT"
    assert vm_cost["credits"][0]["amount"] < 0  # Negative credit

    # Verify query cost was tracked explicitly
    query_costs = gcp_connector.bigquery_query_costs
    assert len(query_costs) >= 1
    latest_q = query_costs[-1]
    assert latest_q.bytes_scanned >= 50 * 1024 * 1024
    assert latest_q.bytes_billed >= 10 * 1024 * 1024  # 10 MB minimum billed
    assert latest_q.query_cost_usd > 0.0
    assert latest_q.export_table_type == GCPBigQueryExportType.DETAILED_RESOURCE

    total_query_cost = gcp_connector.total_bigquery_query_cost_usd
    assert total_query_cost > 0.0


@pytest.mark.asyncio
async def test_gcp_cost_query_targeted(gcp_connector: GCPConnector):
    """Targeted query scans fewer bytes and updates running query cost total."""
    cost_res = await gcp_connector.collect_cost_query(query={"service": "BigQuery"})
    assert len(cost_res) >= 1
    assert all("BigQuery" in r["service_description"] for r in cost_res)

    query_costs = gcp_connector.bigquery_query_costs
    assert len(query_costs) >= 1


def test_bigquery_query_cost_model_calculation():
    """Validates BigQuery on-demand rate calculation ($5.00/TB with 10MB minimum)."""
    # Case 1: Query scans 1 MB (below 10MB minimum) -> billed at 10 MB
    cost_sub_min = GCPBigQueryQueryCost.calculate_cost(bytes_scanned=1024 * 1024, latency_ms=50.0)
    assert cost_sub_min.bytes_scanned == 1024 * 1024
    assert cost_sub_min.bytes_billed == 10 * 1024 * 1024  # 10 MiB minimum
    assert cost_sub_min.query_cost_usd > 0.0

    # Case 2: Query scans 1 TiB (1024^4 bytes) -> billed at exactly $5.00
    one_tib = 1024**4
    cost_one_tib = GCPBigQueryQueryCost.calculate_cost(bytes_scanned=one_tib, latency_ms=500.0)
    assert cost_one_tib.bytes_billed == one_tib
    assert cost_one_tib.query_cost_usd == 5.0


# ==============================================================================
# 5. Pricing Catalog & Contract Precedence
# ==============================================================================


@pytest.mark.asyncio
async def test_gcp_pricing_public_and_contract_precedence(gcp_connector: GCPConnector):
    """Account-specific custom contract pricing takes strict precedence over public catalog rates."""
    # 1. Public Catalog API list prices
    public_res = await gcp_connector.collect_pricing_public()
    assert len(public_res) >= 4
    vm_public = next(r for r in public_res if r["sku_id"] == "D982-F0A1-332B")
    assert vm_public["list_price"] == 0.031611
    assert vm_public["effective_price"] == 0.031611
    assert vm_public["is_contract_rate"] is False

    # 2. Negotiated Contract pricing (with entitlement enabled on connector)
    negotiated_res = await gcp_connector.collect_pricing_negotiated()
    assert len(negotiated_res) >= 4
    vm_contract = next(r for r in negotiated_res if r["sku_id"] == "D982-F0A1-332B")
    assert vm_contract["list_price"] == 0.031611
    assert vm_contract["contract_price"] == 0.025288  # 20% discount
    assert vm_contract["effective_price"] == 0.025288  # Precedence
    assert vm_contract["is_contract_rate"] is True

    # 3. Helper method resolves quote with precedence
    quote = gcp_connector.get_effective_pricing("D982-F0A1-332B")
    assert quote is not None
    assert quote.effective_price == 0.025288
    assert quote.is_contract_rate is True

    # 4. Without contract entitlement, falls back to list price
    svc_no_contract = GCPPricingService(has_contract_entitlement=False)
    fallback_quote = svc_no_contract.get_effective_quote("D982-F0A1-332B")
    assert fallback_quote is not None
    assert fallback_quote.effective_price == 0.031611
    assert fallback_quote.is_contract_rate is False


# ==============================================================================
# 6. Usage Metrics & Coarse Interval Enforcement
# ==============================================================================


@pytest.mark.asyncio
async def test_gcp_metrics_coarse_intervals_succeed(gcp_connector: GCPConnector):
    """Hourly (PT1H) and daily (P1D) intervals succeed with coarse aggregates."""
    res_hourly = await gcp_connector.collect_usage(interval="PT1H")
    assert len(res_hourly) >= 5
    assert res_hourly[0]["aggregation"]["alignment_period"] == "3600s"

    res_daily = await gcp_connector.collect_usage(interval="P1D")
    assert len(res_daily) >= 5
    assert res_daily[0]["aggregation"]["alignment_period"] == "86400s"


@pytest.mark.asyncio
async def test_gcp_metrics_sub_minute_intervals_forbidden(gcp_connector: GCPConnector):
    """Sub-minute intervals are strictly forbidden and raise GCPMetricIntervalForbiddenException."""
    for bad_interval in ["PT30S", "30s", "PT1M", "10s", "1m"]:
        with pytest.raises(GCPMetricIntervalForbiddenException) as exc:
            await gcp_connector.collect_usage(interval=bad_interval)
        assert exc.value.error_code == "GCP_METRIC_INTERVAL_FORBIDDEN"
        assert "CloudLens enforces coarse aggregates only" in str(exc.value)


# ==============================================================================
# 7. Labels with Source Tier Attribution
# ==============================================================================


@pytest.mark.asyncio
async def test_gcp_labels_source_tier_attribution(gcp_connector: GCPConnector):
    """Label collection records source tier (LABEL_SOURCE_PROJECT vs LABEL_SOURCE_RESOURCE)."""
    tags_res = await gcp_connector.collect_tags()
    assert len(tags_res) >= 6

    # Verify project-level label
    proj_label = next(t for t in tags_res if t["source_tier"] == "LABEL_SOURCE_PROJECT")
    assert "projects/" in proj_label["scope_id"]
    assert proj_label["key"] in ("business_unit", "env", "data-classification")

    # Verify resource-level label
    res_label = next(t for t in tags_res if t["source_tier"] == "LABEL_SOURCE_RESOURCE")
    assert (
        "//compute.googleapis.com" in res_label["scope_id"] or "//storage" in res_label["scope_id"]
    )
    assert res_label["key"] in ("app", "cost_centre", "owner", "project-lead")


# ==============================================================================
# 8. Relationships & Dynamic Runtime Probe
# ==============================================================================


@pytest.mark.asyncio
async def test_gcp_relationships_probe_and_partial_declaration(gcp_connector: GCPConnector):
    """Dynamic probe verifies RELATIONSHIP content type; declared as PARTIAL."""
    # 1. Successful probe
    probe = gcp_connector.relationship_probe_result
    assert probe.is_available is True
    assert probe.probe_status == "AVAILABLE"
    assert probe.is_partial is True
    assert gcp_connector.relationships_is_partial is True

    # 2. Extract structural relationships
    rels = await gcp_connector.discover_relationships()
    assert len(rels) >= 4
    rel_types = [r["relationship_type"] for r in rels]
    assert "NETWORK_SUBNET" in rel_types
    assert "STORAGE_VOLUME" in rel_types
    assert "IDENTITY_ATTACHMENT" in rel_types
    assert all(r["is_structural_only"] is True for r in rels)

    # 3. Simulated tier-restricted estate probe
    restricted_svc = GCPRelationshipService(
        primary_project_id="proj-cloudlens-core",
        config={"force_relationship_unsupported": True},
    )
    restricted_probe = restricted_svc.probe_relationship_support()
    assert restricted_probe.is_available is False
    assert restricted_probe.probe_status == "TIER_RESTRICTED"


# ==============================================================================
# 9. Budgets & Prohibition of Silent Pub/Sub Creation
# ==============================================================================


@pytest.mark.asyncio
async def test_gcp_budgets_non_authoritative_comparison_only(gcp_connector: GCPConnector):
    """Cloud Billing Budgets are read for comparison only (is_authoritative = False)."""
    budgets = await gcp_connector.collect_budgets()
    assert len(budgets) >= 2
    for b in budgets:
        assert b["is_authoritative"] is False
        assert b["has_pubsub_rule"] is False


def test_gcp_budgets_silent_pubsub_forbidden():
    """Attempting to enable Pub/Sub silently raises GCPPubSubSilentCreationForbiddenException."""
    with pytest.raises(GCPPubSubSilentCreationForbiddenException) as exc:
        GCPBudgetService(
            billing_account_id="01ABCD-2345EF-6789GH",
            config={"enable_silent_pubsub": True},
        )
    assert exc.value.error_code == "GCP_PUBSUB_SILENT_CREATION_FORBIDDEN"
    assert (
        "Silent creation of Cloud Billing Budget Pub/Sub notification topics is strictly prohibited"
        in str(exc.value)
    )


# ==============================================================================
# 10. Onboarding Wizard Non-Retrospective Warning
# ==============================================================================


@pytest.mark.asyncio
async def test_gcp_onboarding_wizard_non_retrospective_warning():
    """Onboarding wizard explicitly warns that Cloud Billing export history starts at enablement."""
    wizard_svc = OnboardingWizardService()
    tenant_ctx = TenantContext(tenant_id="tenant-gcp-test-01", user_id="admin-gcp")

    # 1. Initialize session with GCP provider and selected scopes
    session = wizard_svc.start_session(
        user_id="admin-gcp",
        tenant_context=tenant_ctx,
    )
    session.provider = ProviderType.GCP
    session.selected_scopes = ["projects/proj-retail-banking-prod"]
    wizard_svc._wizard_repo.save(session, tenant_context=tenant_ctx)

    # 2. Check pre-completion estimate warning
    estimate = wizard_svc.calculate_pre_completion_estimates(
        session_id=session.id,
        tenant_context=tenant_ctx,
    )
    assert estimate.billing_export_history_warning is not None
    assert "Cloud Billing export is NOT retrospective" in estimate.billing_export_history_warning
    assert "history begins strictly at enablement" in estimate.billing_export_history_warning
    assert len(estimate.warnings) >= 1

    # 3. Also check connector property warning
    conn = GCPConnector("conn-test", "tenant-test-01")
    assert "NOT retrospective" in conn.billing_export_history_warning


# ==============================================================================
# 11. Health Status, Provider Metadata, & Boundary Safety
# ==============================================================================


@pytest.mark.asyncio
async def test_gcp_health_status_and_provider_metadata(gcp_connector: GCPConnector):
    """Health status and provider metadata report valid capabilities and GCP attributes."""
    health = await gcp_connector.health_status()
    assert health.healthy is True
    assert health.details["provider"] == ProviderType.GCP.value
    assert health.details["billing_account_id"] == "01ABCD-2345EF-6789GH"
    assert health.details["relationships_status"] == "AVAILABLE"

    metadata = await gcp_connector.provider_metadata()
    assert metadata.provider == ProviderType.GCP
    assert len(metadata.supported_regions) >= 8
    assert "us-central1" in metadata.supported_regions
    assert metadata.metadata["workload_identity_federation_recommended"] is True
    assert metadata.metadata["dual_hierarchy_separated"] is True
    assert metadata.metadata["query_rate_per_tb_usd"] == 5.00
    assert "NOT retrospective" in metadata.metadata["billing_export_history_warning"]


@pytest.mark.asyncio
async def test_gcp_connector_undeclared_capability_fast_fails():
    """Undeclared capabilities fail fast with UndeclaredCapabilityException."""
    limited_conn = GCPConnector(
        connector_id="conn-gcp-limited",
        tenant_id="tenant-gcp-test-01",
        declared_capabilities={
            ConnectorCapability.AUTHENTICATE,
            ConnectorCapability.HEALTH_STATUS,
        },
    )
    # Authenticate works
    auth_res = await limited_conn.authenticate()
    assert auth_res.authenticated is True

    # Undeclared hierarchy discovery fails fast
    with pytest.raises(UndeclaredCapabilityException):
        await limited_conn.discover_hierarchy()

    # Undeclared cost collection fails fast
    with pytest.raises(UndeclaredCapabilityException):
        await limited_conn.collect_cost_bulk()
