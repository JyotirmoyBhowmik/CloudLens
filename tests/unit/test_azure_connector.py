"""Comprehensive Unit and Contract Tests for Microsoft Azure Connector (Prompt 16 / BBP Section 14.2 & 15.4).

Validates:
1. Authentication: Entra ID Service Principal with certificate credential (recommended),
   Workload Identity Federation (OIDC keyless), and Managed Identity (IMDS).
   Interactive user passwords (ROPC) strictly prohibited.
2. Hierarchy Discovery: Single-pass canonical scope tree from Management Group hierarchy
   and subscription ancestry, preserving native identifiers and types.
3. Resource Inventory: Azure Resource Graph as primary source; verifies eventual consistency
   freshness indicator with indexing latency caveat explicitly surfaced.
4. Agreement Detection & Scope-Form Matrix: Automatic detection of EA, MCA, MPA, DIRECT;
   explicit diagnostic errors on agreement/scope mismatches.
5. Cost Ingestion: Export-first bulk ingestion with Query API fallback; unsupported subscription
   types (Free Trial, Sponsored) handled as declared capability gaps, not connector errors.
6. Pricing Precedence: Public Retail Prices API (USD, is_retail=True) vs Price Sheet API
   (is_negotiated=True) with strict precedence: retail is never presented as actuals when price sheet exists.
7. Budgets: Cost Management budgets read for comparison only (never authoritative).
8. Usage Metrics: Coarse Azure Monitor metrics (hourly PT1H / daily P1D); sub-minute intervals strictly rejected.
9. Tags: Multi-tier tag collection across subscription, resource group, and resource levels (no fake inheritance).
10. Relationships: Structural dependencies derived from Resource Graph; declared as PARTIAL.
11. Boundary Safety: Conformance kit verification and fast-fail on undeclared capabilities.
"""

from __future__ import annotations

from typing import Any

import pytest

from connectors.azure.auth import AzureAuthService
from connectors.azure.connector import AzureConnector
from connectors.azure.metrics import AzureMetricIntervalForbiddenException
from connectors.azure.models import (
    AzureAgreementType,
    AzureAuthenticationException,
    AzureAuthMethod,
    AzureCredentials,
    AzureScopeMismatchException,
    AzureSubscriptionOffer,
    AzureTagLevel,
    detect_agreement_type,
    is_unsupported_cost_offer,
    validate_scope_for_agreement,
)
from domain.models.enums import ConnectorCapability, ProviderType
from domain.models.exceptions import UndeclaredCapabilityException


@pytest.fixture
def azure_connector() -> AzureConnector:
    """Provides a standard AzureConnector instance for unit testing."""
    return AzureConnector(
        connector_id="conn-azure-test-01",
        tenant_id="00000000-0000-0000-0000-000000000001",
        config={
            "credentials": {
                "tenant_id": "00000000-0000-0000-0000-000000000001",
                "client_id": "11111111-1111-1111-1111-111111111111",
                "auth_method": AzureAuthMethod.CERTIFICATE.value,
                "certificate_thumbprint": "ABCDEF1234567890ABCDEF1234567890ABCDEF12",
                "subscription_id": "sub-prod-0001",
                "management_group_id": "mg-root-00000000-0000-0000-0000-000000000001",
            },
            "has_negotiated_entitlement": True,
        },
    )


# ==============================================================================
# 1. Authentication & Security Baselines
# ==============================================================================


@pytest.mark.asyncio
async def test_azure_auth_certificate_recommended(azure_connector: AzureConnector):
    """Certificate credential authentication produces valid AuthResult with assertion type."""
    auth_res = await azure_connector.authenticate()
    assert auth_res.authenticated is True
    assert auth_res.provider == ProviderType.AZURE.value
    assert "spn:11111111-1111-1111-1111-111111111111" in auth_res.identity
    assert auth_res.attributes["auth_method"] == AzureAuthMethod.CERTIFICATE.value
    assert "assertion_type" in auth_res.attributes


@pytest.mark.asyncio
async def test_azure_auth_workload_and_managed_identity():
    """Workload identity federation and managed identity authentication methods work correctly."""
    # Workload identity
    wi_svc = AzureAuthService(
        AzureCredentials(
            tenant_id="00000000-0000-0000-0000-000000000001",
            client_id="22222222-2222-2222-2222-222222222222",
            auth_method=AzureAuthMethod.WORKLOAD_IDENTITY,
            federated_token_path="/var/run/secrets/azure/tokens/azure-identity-token",
        )
    )
    res_wi = await wi_svc.authenticate()
    assert res_wi.authenticated is True
    assert res_wi.attributes["auth_method"] == AzureAuthMethod.WORKLOAD_IDENTITY.value

    # Managed identity
    mi_svc = AzureAuthService(
        AzureCredentials(
            tenant_id="00000000-0000-0000-0000-000000000001",
            client_id="33333333-3333-3333-3333-333333333333",
            auth_method=AzureAuthMethod.MANAGED_IDENTITY,
        )
    )
    res_mi = await mi_svc.authenticate()
    assert res_mi.authenticated is True
    assert "169.254.169.254" in res_mi.attributes["endpoint"]


def test_azure_auth_prohibits_interactive_passwords():
    """Enterprise security invariant: interactive user passwords strictly raise error."""
    with pytest.raises(AzureAuthenticationException) as exc_info:
        AzureCredentials(
            tenant_id="00000000-0000-0000-0000-000000000001",
            client_id="11111111-1111-1111-1111-111111111111",
            user_password="SuperSecretPassword123!",
        ).validate_security_invariants()
    assert exc_info.value.error_code == "FORBIDDEN_USER_PASSWORD"


@pytest.mark.asyncio
async def test_azure_permission_preflight_validation(azure_connector: AzureConnector):
    """Pre-flight permission verification satisfies all 17 capabilities."""
    perm_res = await azure_connector.validate_permissions()
    assert perm_res.valid is True
    assert perm_res.provider == ProviderType.AZURE.value
    assert len(perm_res.capabilities) >= 17
    assert len(perm_res.missing_permissions) == 0


# ==============================================================================
# 2. Hierarchy Discovery (Single-Pass Ancestor Chain)
# ==============================================================================


@pytest.mark.asyncio
async def test_azure_hierarchy_single_pass_ancestors(azure_connector: AzureConnector):
    """Constructs canonical scope tree with single-pass ancestor chains preserving native types."""
    hierarchy = await azure_connector.discover_hierarchy()
    assert len(hierarchy) >= 5

    # Verify Root Management Group
    root_node = next(n for n in hierarchy if n["parent_id"] is None)
    assert root_node["native_type"] == "managementGroup"
    assert root_node["ancestor_chain"] == []
    assert root_node["scope_path"] == f"/{azure_connector.tenant_id}"

    # Verify Production Subscription node has complete ancestor path
    sub_node = next(
        n
        for n in hierarchy
        if n.get("native_type") == "subscription" and "sub-prod-0001" in n["scope_id"]
    )
    assert sub_node["scope_role"] == "BILLING_ACCOUNT"
    assert len(sub_node["ancestor_chain"]) >= 2
    assert "sub-prod-0001" in sub_node["scope_path"]


@pytest.mark.asyncio
async def test_azure_discover_organizations_and_accounts(azure_connector: AzureConnector):
    """discover_organizations returns tenant root, discover_accounts returns subscriptions."""
    orgs = await azure_connector.discover_organizations()
    assert len(orgs) >= 1
    assert orgs[0]["native_type"] == "managementGroup"

    accounts = await azure_connector.discover_accounts()
    assert len(accounts) >= 2
    assert all(a["native_type"] == "subscription" for a in accounts)


def test_azure_hierarchy_live_sandbox_and_custom_recorded_fixtures(
    azure_connector: AzureConnector,
):
    """Verifies that recorded fixtures and live sandbox both produce correct canonical scope tree with ancestry."""
    # 1. Live sandbox default estate
    sandbox_tree = azure_connector.hierarchy_service.build_canonical_scope_tree()
    assert len(sandbox_tree) >= 5
    assert all("scope_path" in node and "ancestor_chain" in node for node in sandbox_tree)

    # 2. Recorded custom ARM fixtures
    recorded_fixtures: list[dict[str, Any]] = [
        {
            "id": "/providers/Microsoft.Management/managementGroups/mg-tenant-root",
            "name": "mg-tenant-root",
            "type": "Microsoft.Management/managementGroups",
            "properties": {"displayName": "Recorded Root", "details": {"parent": None}},
        },
        {
            "id": "/providers/Microsoft.Management/managementGroups/mg-custom-bu",
            "name": "mg-custom-bu",
            "type": "Microsoft.Management/managementGroups",
            "properties": {
                "displayName": "Recorded BU",
                "details": {
                    "parent": {
                        "id": "/providers/Microsoft.Management/managementGroups/mg-tenant-root"
                    }
                },
            },
        },
        {
            "id": "/subscriptions/sub-rec-001",
            "subscriptionId": "sub-rec-001",
            "displayName": "Recorded Subscription",
            "parent_id": "/providers/Microsoft.Management/managementGroups/mg-custom-bu",
            "type": "Microsoft.Resources/subscriptions",
        },
    ]
    custom_tree = azure_connector.hierarchy_service.build_canonical_scope_tree(
        raw_items=recorded_fixtures
    )
    assert len(custom_tree) == 3

    sub_rec = next(n for n in custom_tree if n["scope_id"] == "/subscriptions/sub-rec-001")
    assert sub_rec["native_type"] == "subscription"
    assert sub_rec["ancestor_chain"] == [
        "/providers/Microsoft.Management/managementGroups/mg-tenant-root",
        "/providers/Microsoft.Management/managementGroups/mg-custom-bu",
    ]
    assert sub_rec["scope_path"] == "/mg-tenant-root/mg-custom-bu/sub-rec-001"


# ==============================================================================
# 3. Resource Inventory & Latency Caveat
# ==============================================================================


@pytest.mark.asyncio
async def test_azure_inventory_latency_caveat_surfaced(azure_connector: AzureConnector):
    """Resource Graph inventory surfaces eventual consistency and latency caveat."""
    freshness = azure_connector.freshness_report
    assert freshness.is_strongly_consistent is False
    assert freshness.indexing_latency_caveat is True
    assert "indexed asynchronously via ARM events" in freshness.caveat_message

    resources = await azure_connector.discover_resources()
    assert len(resources) >= 4

    # Check VM resource
    vm = next(r for r in resources if r["type"] == "Microsoft.Compute/virtualMachines")
    assert vm["name"] == "vm-payment-gw-01"
    assert vm["service_category"] == "COMPUTE"
    assert vm["runtime_status"] == "RUNNING"
    assert "_freshness" in vm
    assert vm["_freshness"]["is_strongly_consistent"] is False


@pytest.mark.asyncio
async def test_azure_discover_services(azure_connector: AzureConnector):
    """discover_services groups active providers in estate."""
    services = await azure_connector.discover_services()
    assert len(services) >= 3
    service_codes = [s["service_code"] for s in services]
    assert "Microsoft.Compute" in service_codes
    assert "Microsoft.Sql" in service_codes
    assert "Microsoft.Storage" in service_codes


# ==============================================================================
# 4. Agreement Detection & Scope-Form Matrix
# ==============================================================================


def test_azure_agreement_detection():
    """Detects agreement types from scope URI or billing account format."""
    # EA: numeric billing account or department / enrollmentAccount
    assert (
        detect_agreement_type(scope_uri="/providers/Microsoft.Billing/billingAccounts/1234567")
        == AzureAgreementType.EA
    )
    assert (
        detect_agreement_type(
            scope_uri="/providers/Microsoft.Billing/billingAccounts/1234567/enrollmentAccounts/987"
        )
        == AzureAgreementType.EA
    )

    # MCA: billingProfiles, invoiceSections, or colon/hyphen account ID
    assert (
        detect_agreement_type(
            scope_uri="/providers/Microsoft.Billing/billingAccounts/ba-guid:0001/billingProfiles/bp-01"
        )
        == AzureAgreementType.MCA
    )

    # MPA: customers
    assert (
        detect_agreement_type(
            scope_uri="/providers/Microsoft.Billing/billingAccounts/ba-01/customers/cust-01"
        )
        == AzureAgreementType.MPA
    )

    # DIRECT: standard subscription
    assert (
        detect_agreement_type(scope_uri="/subscriptions/sub-prod-0001") == AzureAgreementType.DIRECT
    )


def test_azure_scope_form_mismatches_raise_explicit_diagnostics():
    """Scope-form mismatch raises AzureScopeMismatchException with explanatory reason."""
    # 1. EA using MCA billingProfiles
    with pytest.raises(AzureScopeMismatchException) as exc_ea:
        validate_scope_for_agreement(
            AzureAgreementType.EA,
            "/providers/Microsoft.Billing/billingAccounts/12345/billingProfiles/bp-01",
        )
    assert "valid only for Microsoft Customer Agreements (MCA)" in exc_ea.value.reason

    # 2. MCA using EA enrollmentAccounts
    with pytest.raises(AzureScopeMismatchException) as exc_mca:
        validate_scope_for_agreement(
            AzureAgreementType.MCA,
            "/providers/Microsoft.Billing/billingAccounts/ba-guid/enrollmentAccounts/123",
        )
    assert "valid only for Enterprise Agreements (EA)" in exc_mca.value.reason

    # 3. DIRECT using enterprise billingAccounts
    with pytest.raises(AzureScopeMismatchException) as exc_direct:
        validate_scope_for_agreement(
            AzureAgreementType.DIRECT,
            "/providers/Microsoft.Billing/billingAccounts/12345",
        )
    assert (
        "Direct Pay-As-You-Go agreements do not expose enterprise billingAccount scopes"
        in exc_direct.value.reason
    )


# ==============================================================================
# 5. Cost Ingestion: Bulk Exports First with Query Fallback & Capability Gaps
# ==============================================================================


@pytest.mark.asyncio
async def test_azure_cost_bulk_export_ingestion(azure_connector: AzureConnector):
    """Bulk ingestion parses Cost Management Scheduled Exports fixture."""
    cost_records = await azure_connector.collect_cost_bulk(
        scope_uri="/subscriptions/sub-prod-0001",
    )
    assert len(cost_records) >= 3
    rec = cost_records[0]
    assert rec["billing_currency"] == "USD"
    assert rec["cost_in_billing_currency"] > 0
    assert rec["is_estimated"] is False


@pytest.mark.asyncio
async def test_azure_cost_query_fallback(azure_connector: AzureConnector):
    """Query API fallback returns interactive records marked is_estimated=True."""
    cost_records = await azure_connector.collect_cost_query(
        scope_uri="/subscriptions/sub-prod-0001",
    )
    assert len(cost_records) >= 3
    rec = cost_records[0]
    assert rec["is_estimated"] is True


@pytest.mark.asyncio
async def test_azure_cost_ingestion_both_agreement_types_and_idempotency(
    azure_connector: AzureConnector,
):
    """Cost ingestion works for both agreement types (EA and MCA) and is idempotent across re-runs."""
    ea_scope = "/providers/Microsoft.Billing/billingAccounts/1234567/enrollmentAccounts/987"
    mca_scope = "/providers/Microsoft.Billing/billingAccounts/ba-guid:0001/billingProfiles/bp-01"

    # 1. EA scope ingestion run 1 and run 2
    ea_records_1 = await azure_connector.collect_cost_bulk(scope_uri=ea_scope)
    ea_records_2 = await azure_connector.collect_cost_bulk(scope_uri=ea_scope)

    assert len(ea_records_1) >= 3
    assert len(ea_records_1) == len(ea_records_2)
    assert ea_records_1 == ea_records_2  # Idempotent across re-runs

    # 2. MCA scope ingestion run 1 and run 2
    mca_records_1 = await azure_connector.collect_cost_bulk(scope_uri=mca_scope)
    mca_records_2 = await azure_connector.collect_cost_bulk(scope_uri=mca_scope)

    assert len(mca_records_1) >= 3
    assert len(mca_records_1) == len(mca_records_2)
    assert mca_records_1 == mca_records_2  # Idempotent across re-runs


@pytest.mark.asyncio
async def test_azure_unsupported_offers_capability_gaps(azure_connector: AzureConnector):
    """Unsupported subscription offer types (Free Trial, Sponsored, MSDN) handled as capability gaps."""
    assert is_unsupported_cost_offer(AzureSubscriptionOffer.FREE_TRIAL.value) is True
    assert is_unsupported_cost_offer(AzureSubscriptionOffer.SPONSORED.value) is True
    assert is_unsupported_cost_offer(AzureSubscriptionOffer.MSDN_DEV_TEST.value) is True
    assert is_unsupported_cost_offer(AzureSubscriptionOffer.ENTERPRISE.value) is False

    # Calling bulk cost on Free Trial does NOT fail with an error; returns empty result
    result = await azure_connector.collect_cost_bulk(
        scope_uri="/subscriptions/sub-free-001",
        offer_id=AzureSubscriptionOffer.FREE_TRIAL.value,
    )
    assert len(result) == 0
    assert result.total_records == 0


# ==============================================================================
# 6. Pricing: Retail vs Price Sheet Precedence
# ==============================================================================


@pytest.mark.asyncio
async def test_azure_pricing_retail_and_negotiated_precedence(azure_connector: AzureConnector):
    """Retail prices are public in USD; negotiated Price Sheet takes strict precedence when entitled."""
    meter_vm = "00000000-1111-2222-3333-444444444444"

    # Public retail rate check
    public_rates = await azure_connector.collect_pricing_public()
    assert len(public_rates) >= 4
    vm_public = next(r for r in public_rates if r["meter_id"] == meter_vm)
    assert vm_public["retail_price"] == 0.192
    assert vm_public["is_retail"] is True
    assert vm_public["retail_currency"] == "USD"

    # Negotiated Price Sheet check
    negotiated_rates = await azure_connector.collect_pricing_negotiated()
    assert len(negotiated_rates) >= 3
    vm_neg = next(r for r in negotiated_rates if r["meter_id"] == meter_vm)
    assert vm_neg["negotiated_price"] == 0.1536
    assert vm_neg["is_negotiated"] is True

    # Precedence check: entitled connector resolves negotiated price as effective price
    quote = azure_connector.get_effective_pricing(meter_vm)
    assert quote is not None
    assert quote.is_negotiated is True
    assert quote.is_retail is False
    assert quote.effective_price == 0.1536
    assert quote.pricing_source == "price_sheet"

    # Non-entitled connector falls back to retail rate
    non_entitled_connector = AzureConnector(
        connector_id="conn-azure-retail-only",
        tenant_id="00000000-0000-0000-0000-000000000002",
        config={"has_negotiated_entitlement": False},
    )
    quote_retail = non_entitled_connector.get_effective_pricing(meter_vm)
    assert quote_retail is not None
    assert quote_retail.is_retail is True
    assert quote_retail.is_negotiated is False
    assert quote_retail.effective_price == 0.192
    assert quote_retail.pricing_source == "retail_prices"


@pytest.mark.asyncio
async def test_azure_pricing_prohibits_usd_retail_as_local_currency_actuals(
    azure_connector: AzureConnector,
):
    """Enforces Do Not rule: USD retail rates must never be presented as local-currency actuals."""
    public_quotes = await azure_connector.collect_pricing_public()
    for q in public_quotes:
        # Must be strictly USD reference rate
        assert q["retail_currency"] == "USD"
        # Must be unambiguously labeled as retail
        assert q["is_retail"] is True
        assert q["is_negotiated"] is False
        assert q["pricing_source"] == "retail_prices"

    # When Price Sheet is present, retail rate is NOT effective price
    meter_vm = "00000000-1111-2222-3333-444444444444"
    entitled_quote = azure_connector.get_effective_pricing(meter_vm)
    assert entitled_quote is not None
    assert entitled_quote.is_retail is False
    assert entitled_quote.is_negotiated is True
    assert entitled_quote.effective_price < entitled_quote.retail_price


# ==============================================================================
# 7. Budgets (Non-Authoritative Discipline)
# ==============================================================================


@pytest.mark.asyncio
async def test_azure_budgets_non_authoritative(azure_connector: AzureConnector):
    """Cost Management budgets are ingested strictly for comparison; is_authoritative is False."""
    budgets = await azure_connector.collect_budgets()
    assert len(budgets) >= 2
    for b in budgets:
        assert b["is_authoritative"] is False
        assert b["amount"] > 0


# ==============================================================================
# 8. Usage Metrics & Sub-Minute Rejection
# ==============================================================================


@pytest.mark.asyncio
async def test_azure_metrics_coarse_intervals_and_subminute_rejection(
    azure_connector: AzureConnector,
):
    """Coarse intervals (PT1H, P1D) succeed; sub-minute intervals (PT1M, PT5M) are rejected."""
    # Hourly succeeds
    metrics_hourly = await azure_connector.collect_usage(interval="PT1H")
    assert len(metrics_hourly) >= 1
    assert metrics_hourly[0]["time_grain"] == "PT1H"

    # Daily succeeds
    metrics_daily = await azure_connector.collect_usage(interval="P1D")
    assert len(metrics_daily) >= 1
    assert metrics_daily[0]["time_grain"] == "P1D"

    # Sub-minute interval is forbidden
    with pytest.raises(AzureMetricIntervalForbiddenException) as exc_subminute:
        await azure_connector.collect_usage(interval="PT1M")
    assert "AZURE_METRIC_INTERVAL_FORBIDDEN" in str(exc_subminute.value.error_code)


# ==============================================================================
# 9. Multi-Tier Tags
# ==============================================================================


@pytest.mark.asyncio
async def test_azure_tags_multi_tier_recording(azure_connector: AzureConnector):
    """Tags are collected across subscription, resource group, and resource tiers without fake inheritance."""
    tags = await azure_connector.collect_tags()
    assert len(tags) >= 5

    tiers = {t["tag_level"] for t in tags}
    assert AzureTagLevel.SUBSCRIPTION.value in tiers
    assert AzureTagLevel.RESOURCE_GROUP.value in tiers
    assert AzureTagLevel.RESOURCE.value in tiers


# ==============================================================================
# 10. Structural Relationships (Declared Partial)
# ==============================================================================


@pytest.mark.asyncio
async def test_azure_relationships_structural_partial(azure_connector: AzureConnector):
    """Structural relationships derived (NIC, Disk, Parent-Child) and capability declared partial."""
    rels = await azure_connector.discover_relationships()
    assert len(rels) >= 3
    rel_types = {r["relationship_type"] for r in rels}
    assert "NETWORK_INTERFACE" in rel_types
    assert "OS_DISK" in rel_types
    assert "PARENT_CHILD" in rel_types
    assert all(r["is_structural_only"] is True for r in rels)
    assert azure_connector.relationship_service.is_partial is True


# ==============================================================================
# 11. Boundary Safety & Undeclared Invocations
# ==============================================================================


def test_azure_undeclared_capability_fails_fast():
    """Connector with restricted capability set rejects undeclared invocations."""
    restricted_connector = AzureConnector(
        connector_id="conn-azure-restricted",
        tenant_id="00000000-0000-0000-0000-000000000001",
        declared_capabilities={ConnectorCapability.AUTHENTICATE, ConnectorCapability.HEALTH_STATUS},
    )

    assert restricted_connector.has_capability(ConnectorCapability.AUTHENTICATE) is True
    assert restricted_connector.has_capability(ConnectorCapability.COLLECT_COST_BULK) is False

    with pytest.raises(UndeclaredCapabilityException):
        restricted_connector._assert_declared(ConnectorCapability.COLLECT_COST_BULK)


@pytest.mark.asyncio
async def test_azure_provider_metadata(azure_connector: AzureConnector):
    """provider_metadata returns correct provider identifier, API version, and supported regions."""
    meta = await azure_connector.provider_metadata()
    assert meta.provider == ProviderType.AZURE
    assert meta.api_version == "2023-03-01"
    assert "eastus" in meta.supported_regions
    assert meta.metadata["agreement_type_detection"] is True
    assert meta.metadata["export_first_cost"] is True
    assert meta.metadata["relationships_partial"] is True
