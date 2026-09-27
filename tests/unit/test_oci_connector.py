"""Comprehensive Unit and Contract Tests for Oracle Cloud Infrastructure (OCI) Connector (Prompt 19 / BBP Section 14.5 & 15.4).

Validates:
1. Authentication: IAM user with API signing key (2048/4096-bit RSA PEM), key fingerprint, rotation state (90-day rotation notice);
   Instance Principal and Resource Principal for inside-OCI deployment; federated identity via Identity Domains.
   Interactive user passwords and personal console logins strictly prohibited (FORBIDDEN_USER_CREDENTIALS).
2. Pre-flight Permission Verification: Satisfies all 17 capabilities against OCI_PERMISSIONS.
3. Hierarchy Discovery: Preserves compartment nesting depth up to 6 levels, mapping root to ROOT_GROUP, depth 1 to GROUP,
   depth > 1 to SUB_GROUP. Sub-compartments are strictly NEVER flattened into top-level groups.
   Supports compartmentDepth query parameter and compartment-to-owner scope rules.
4. Resource Inventory: Resource Search across tenancy as primary path, enriched per-service (Compute, Storage, Database, VCN).
5. Cost & Usage Ingestion: Usage API for interactive views (requestSummarizedUsages) and delivered CSV usage reports for bulk analysis.
   Cleanly supports negative cost adjustments/credits (e.g. outage SLA credits).
6. Non-Retroactive Tag Attribution: Tag-based cost attribution applies strictly from the time of association onward and is never retroactive.
   Surfaces explicit notice and flags whenever tag-based allocation is evaluated for periods preceding tag association.
7. Tag Model: Distinctly models free-form tags, namespaced defined tags (Namespace.Key), and cost-tracking tags (maximum 10 per tenancy).
8. Budgets: Ingests OCI Budgets and alert rules (ACTUAL vs FORECAST, ABSOLUTE vs PERCENTAGE). Comparison-only (is_authoritative = False).
9. Pricing: Public static rate cards and negotiated Universal Credits (UCC) contract rates with precedence.
   Explicitly discloses lack of dynamic public SKU query API parity (has_dynamic_api_parity = False).
10. Usage Metrics: Coarse OCI Monitoring metrics (hourly PT1H / daily P1D); sub-minute intervals strictly rejected.
11. Relationships: Minimal structural derivation, declared as PARTIAL.
12. Onboarding Wizard: Surfaces permanent non-retroactive tag attribution warning during onboarding.
13. Boundary Safety: Conformance kit verification and fast-fail on undeclared capabilities.
"""

from __future__ import annotations

import pytest

from connectors.oci.auth import OCIAuthService
from connectors.oci.connector import OCIConnector
from connectors.oci.hierarchy import OCIHierarchyService
from connectors.oci.metrics import OCIMetricIntervalForbiddenException
from connectors.oci.models import (
    OCIAuthenticationException,
    OCIAuthMethod,
    OCICredentials,
    is_valid_ocid,
)
from connectors.oci.pricing import OCIPricingService
from connectors.oci.tags import OCITagService
from connectors.wizard.service import OnboardingWizardService
from domain.models.enums import ConnectorCapability, ProviderType
from domain.models.exceptions import UndeclaredCapabilityException
from domain.tenant.context import TenantContext

# ==============================================================================
# Fixtures
# ==============================================================================


@pytest.fixture
def oci_connector() -> OCIConnector:
    """Provides a standard OCIConnector instance configured for unit testing."""
    return OCIConnector(
        connector_id="conn-oci-test-01",
        tenant_id="tenant-test-01",
        config={
            "tenancy_ocid": "ocid1.tenancy.oc1..aaaaaaaam57u7o6x3m7b5exampletenancyocid12345678",
            "region": "us-ashburn-1",
            "credentials": {
                "tenancy_ocid": "ocid1.tenancy.oc1..aaaaaaaam57u7o6x3m7b5exampletenancyocid12345678",
                "user_ocid": "ocid1.user.oc1..aaaaaaaav7b6yexampleuserocid1234567890abcdef",
                "fingerprint": "20:3b:97:13:55:1c:5b:0d:d3:37:d8:50:4e:c4:ac:48",
                "private_key_pem": "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA0TestKey...==\n-----END RSA PRIVATE KEY-----",
                "auth_method": OCIAuthMethod.API_KEY.value,
            },
            "has_contract_entitlement": True,
        },
    )


# ==============================================================================
# 1. Authentication & Security Baselines
# ==============================================================================


@pytest.mark.asyncio
async def test_oci_auth_api_signing_key_recommended(oci_connector: OCIConnector):
    """API signing key with RSA PEM produces valid AuthResult with fingerprint and 90-day rotation notice."""
    auth_res = await oci_connector.authenticate()
    assert auth_res.authenticated is True
    assert auth_res.provider == ProviderType.OCI.value
    assert "aaaaaaaav7b6yexample" in auth_res.identity
    assert auth_res.attributes["auth_method"] == OCIAuthMethod.API_KEY.value
    assert auth_res.attributes["fingerprint"] == "20:3b:97:13:55:1c:5b:0d:d3:37:d8:50:4e:c4:ac:48"
    assert "90-day" in auth_res.attributes["rotation_notice"]
    assert auth_res.attributes["key_type"] == "RSA_2048_OR_4096_PEM"


@pytest.mark.asyncio
async def test_oci_auth_instance_and_resource_principal():
    """Instance Principal and Resource Principal work for in-OCI deployments."""
    # 1. Instance Principal
    inst_svc = OCIAuthService(
        OCICredentials(
            tenancy_ocid="ocid1.tenancy.oc1..aaaaaaaam57u7o6x3m7b5exampletenancyocid12345678",
            auth_method=OCIAuthMethod.INSTANCE_PRINCIPAL,
            region="us-ashburn-1",
        )
    )
    res_inst = await inst_svc.authenticate()
    assert res_inst.authenticated is True
    assert res_inst.attributes["auth_method"] == OCIAuthMethod.INSTANCE_PRINCIPAL.value
    assert res_inst.attributes["token_type"] == "IMDS_SESSION_TOKEN"
    assert "cloudlens-agent" in res_inst.identity

    # 2. Resource Principal
    rp_svc = OCIAuthService(
        OCICredentials(
            tenancy_ocid="ocid1.tenancy.oc1..aaaaaaaam57u7o6x3m7b5exampletenancyocid12345678",
            auth_method=OCIAuthMethod.RESOURCE_PRINCIPAL,
            region="us-phoenix-1",
        )
    )
    res_rp = await rp_svc.authenticate()
    assert res_rp.authenticated is True
    assert res_rp.attributes["auth_method"] == OCIAuthMethod.RESOURCE_PRINCIPAL.value
    assert res_rp.attributes["token_type"] == "RPST_RESOURCE_PRINCIPAL_SESSION_TOKEN"


@pytest.mark.asyncio
async def test_oci_auth_federated_identity():
    """Federated identity via OCI Identity Domains is supported."""
    fed_svc = OCIAuthService(
        OCICredentials(
            tenancy_ocid="ocid1.tenancy.oc1..aaaaaaaam57u7o6x3m7b5exampletenancyocid12345678",
            auth_method=OCIAuthMethod.FEDERATED,
            identity_domain_id="idcs-example-domain-12345",
            federation_token="eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
        )
    )
    res_fed = await fed_svc.authenticate()
    assert res_fed.authenticated is True
    assert res_fed.attributes["auth_method"] == OCIAuthMethod.FEDERATED.value
    assert res_fed.attributes["identity_domain_id"] == "idcs-example-domain-12345"


def test_oci_auth_prohibits_passwords_and_interactive_tokens():
    """Enterprise security invariant: Interactive user console passwords and personal web tokens raise FORBIDDEN_USER_CREDENTIALS."""
    # 1. Prohibit user console password
    with pytest.raises(OCIAuthenticationException) as exc_pwd:
        OCICredentials(
            tenancy_ocid="ocid1.tenancy.oc1..aaaaaaaam57u7o6x3m7b5exampletenancyocid12345678",
            user_password="MasterAdminPassword123!",
        ).validate_security_invariants()
    assert exc_pwd.value.error_code == "FORBIDDEN_USER_CREDENTIALS"
    assert "Console passwords are never permitted" in str(exc_pwd.value)

    # 2. Prohibit personal interactive session token
    with pytest.raises(OCIAuthenticationException) as exc_token:
        OCICredentials(
            tenancy_ocid="ocid1.tenancy.oc1..aaaaaaaam57u7o6x3m7b5exampletenancyocid12345678",
            user_interactive_token="personal-web-session-token",
        ).validate_security_invariants()
    assert exc_token.value.error_code == "FORBIDDEN_USER_CREDENTIALS"


def test_oci_ocid_validation():
    """Validates OCI Oracle Cloud Identifier (OCID) regex and format rules."""
    assert (
        is_valid_ocid("ocid1.tenancy.oc1..aaaaaaaam57u7o6x3m7b5exampletenancyocid12345678") is True
    )
    assert is_valid_ocid("ocid1.user.oc1..aaaaaaaav7b6yexampleuserocid1234567890abcdef") is True
    assert is_valid_ocid("ocid1.compartment.oc1..aaaaaaaaworkloadcomp1234567890abcdef") is True
    assert is_valid_ocid("ocid1.instance.oc1.phx.anyhqljsm57u7o6x3m7b5exampleinstance123") is True
    assert is_valid_ocid("ocid1.volume.oc1.iad.abuwcljsm57u7o6x3m7b5examplevolume123456") is True
    assert is_valid_ocid("ocid1.vnic.oc1.iad.abuwcljsm57u7o6x3m7b5examplevnic123456789") is True
    assert is_valid_ocid("ocid1.bucket.oc1.iad.aaaaaaaabucket1234567890abcdef") is True

    # Invalid formats
    assert is_valid_ocid("invalid-format") is False
    assert is_valid_ocid("ocid2.tenancy.oc1..abc") is False
    assert is_valid_ocid("ocid1.tenancy.oc1") is False
    assert is_valid_ocid("") is False
    assert is_valid_ocid("ocid1.tenancy.oc1..contains spaces") is False


@pytest.mark.asyncio
async def test_oci_permission_preflight_validation(oci_connector: OCIConnector):
    """Pre-flight permission verification satisfies all 17 capabilities against OCI_PERMISSIONS."""
    perm_res = await oci_connector.validate_permissions()
    assert perm_res.valid is True
    assert perm_res.provider == ProviderType.OCI.value
    assert len(perm_res.capabilities) >= 17
    assert len(perm_res.missing_permissions) == 0


# ==============================================================================
# 2. Compartment Hierarchy Discovery (Depth Preservation & No Flattening)
# ==============================================================================


@pytest.mark.asyncio
async def test_oci_hierarchy_depth_preservation_and_no_flattening(oci_connector: OCIConnector):
    """Preserves compartment nesting depth up to 6 levels, maps ROOT_GROUP, GROUP, SUB_GROUP, and NEVER flattens."""
    hierarchy = await oci_connector.discover_hierarchy()
    assert len(hierarchy) >= 6

    # 1. Tenancy Root (depth 0 -> ROOT_GROUP)
    root_node = next(n for n in hierarchy if n["depth"] == 0)
    assert root_node["scope_role"] == "ROOT_GROUP"
    assert root_node["parent_id"] is None
    assert root_node["native_type"] == "tenancy"
    assert root_node["ancestor_chain"] == []

    # 2. Depth 1 Compartment (Production-Workloads -> GROUP)
    comp_workloads = next(
        n for n in hierarchy if n["depth"] == 1 and "prod987654321" in n["scope_id"]
    )
    assert comp_workloads["scope_role"] == "GROUP"
    assert comp_workloads["parent_id"] == root_node["scope_id"]
    assert comp_workloads["ancestor_chain"] == [root_node["scope_id"]]
    assert root_node["scope_id"] in comp_workloads["scope_path"]

    # 3. Depth 2 Sub-compartment (App-Tier -> SUB_GROUP) - STRICT PROHIBITION: NOT FLATTENED
    comp_sub_app = next(
        n for n in hierarchy if n["depth"] == 2 and "subapp111222333" in n["scope_id"]
    )
    assert comp_sub_app["scope_role"] == "SUB_GROUP"
    assert (
        comp_sub_app["parent_id"] == comp_workloads["scope_id"]
    )  # Preserves sub-compartment parentage
    assert len(comp_sub_app["ancestor_chain"]) == 2  # Tenancy -> Production -> App-Tier
    assert comp_workloads["scope_id"] in comp_sub_app["ancestor_chain"]
    assert "prod987654321" in comp_sub_app["scope_path"]
    assert "subapp111222333" in comp_sub_app["scope_path"]

    # 4. Depth 3 Sub-compartment (Core-Banking -> SUB_GROUP)
    comp_banking = next(
        n for n in hierarchy if n["depth"] == 3 and "bankingcomp333" in n["scope_id"]
    )
    assert comp_banking["scope_role"] == "SUB_GROUP"
    assert comp_banking["parent_id"] == comp_sub_app["scope_id"]
    assert len(comp_banking["ancestor_chain"]) == 3

    # 5. Depth 4 Deep Nested Sub-compartment (Payments-Microservices -> SUB_GROUP)
    comp_payments = next(
        n for n in hierarchy if n["depth"] == 4 and "paymentscomp444" in n["scope_id"]
    )
    assert comp_payments["scope_role"] == "SUB_GROUP"
    assert comp_payments["parent_id"] == comp_banking["scope_id"]
    assert len(comp_payments["ancestor_chain"]) == 4

    # Strict architectural assertion: Each sub-compartment is distinct and has correct depth
    depths = [n["depth"] for n in hierarchy]
    assert 0 in depths
    assert 1 in depths
    assert 2 in depths
    assert 3 in depths
    assert 4 in depths


@pytest.mark.asyncio
async def test_oci_hierarchy_compartment_depth_filtering():
    """Hierarchy service respects compartmentDepth parameter limiting returned subtree depth."""
    svc = OCIHierarchyService(
        tenancy_ocid="ocid1.tenancy.oc1..aaaaaaaam57u7o6x3m7b5exampletenancyocid12345678"
    )

    # Filter depth <= 1 (tenancy root + depth 1 compartments only)
    nodes_depth_1 = await svc.discover_compartment_tree(compartment_depth=1)
    assert len(nodes_depth_1) == 3  # Root + prod + nonprod
    assert all(n["depth"] <= 1 for n in nodes_depth_1)

    # Filter depth <= 2
    nodes_depth_2 = await svc.discover_compartment_tree(compartment_depth=2)
    assert len(nodes_depth_2) == 6  # Root + prod + nonprod + sub_app + sub_db + sandbox
    assert all(n["depth"] <= 2 for n in nodes_depth_2)


def test_oci_hierarchy_compartment_owner_rules(oci_connector: OCIConnector):
    """Compartment-to-owner scope rules allow binding owner email, department, and cost center."""
    prod_ocid = "ocid1.compartment.oc1..aaaaaaaaprod987654321"

    # Configure compartment owner
    oci_connector.configure_compartment_owner(
        compartment_ocid=prod_ocid,
        owner_email="finance-ops@enterprise.example.com",
        department="Treasury Engineering",
        cost_center="CC-9012",
    )

    # Verify retrieval
    owner_info = oci_connector.hierarchy_service.get_compartment_owner(prod_ocid)
    assert owner_info is not None
    assert owner_info["owner_email"] == "finance-ops@enterprise.example.com"
    assert owner_info["department"] == "Treasury Engineering"
    assert owner_info["cost_center"] == "CC-9012"


@pytest.mark.asyncio
async def test_oci_discover_organizations_and_accounts(oci_connector: OCIConnector):
    """discover_organizations returns tenancy; discover_accounts returns compartments."""
    orgs = await oci_connector.discover_organizations()
    assert len(orgs) == 1
    assert orgs[0]["scope_role"] == "ROOT_GROUP"
    assert "Enterprise" in orgs[0]["name"]

    accounts = await oci_connector.discover_accounts()
    assert len(accounts) >= 5
    for acc in accounts:
        assert acc["scope_role"] in ("GROUP", "SUB_GROUP")

    # Filter by parent compartment
    prod_ocid = "ocid1.compartment.oc1..aaaaaaaaprod987654321"
    child_accounts = await oci_connector.discover_accounts(parent_id=prod_ocid)
    assert len(child_accounts) >= 2
    assert any("subapp" in a["scope_id"] for a in child_accounts)


# ==============================================================================
# 3. Resource Inventory & Per-Service Enrichment
# ==============================================================================


@pytest.mark.asyncio
async def test_oci_inventory_resource_search_and_classification(oci_connector: OCIConnector):
    """Resource Search discovers resources across tenancy and classifies into standard service categories."""
    resources = await oci_connector.discover_resources()
    assert len(resources) >= 5

    # 1. Compute VM instance
    vm = next(r for r in resources if r["resource_type"] == "Instance")
    assert vm["service_category"] == "COMPUTE"
    assert vm["lifecycle_state"] == "AVAILABLE"
    assert vm["properties"]["shape"] == "VM.Standard.E4.Flex"
    assert vm["properties"]["ocpus"] == 4.0
    assert vm["properties"]["memory_in_gbs"] == 32.0

    # 2. Block Storage Volume
    vol = next(r for r in resources if r["resource_type"] == "Volume")
    assert vol["service_category"] == "STORAGE"
    assert vol["properties"]["size_in_gbs"] == 200

    # 3. Autonomous Database
    adb = next(r for r in resources if r["resource_type"] == "AutonomousDatabase")
    assert adb["service_category"] == "DATABASE"
    assert adb["properties"]["db_workload"] == "OLTP"

    # 4. Object Storage Bucket
    bucket = next(r for r in resources if r["resource_type"] == "Bucket")
    assert bucket["service_category"] == "STORAGE"

    # 5. Virtual Cloud Network (VCN)
    vcn = next(r for r in resources if r["resource_type"] == "Vcn")
    assert vcn["service_category"] == "NETWORKING"
    assert vcn["properties"]["cidr_block"] == "10.0.0.0/16"


@pytest.mark.asyncio
async def test_oci_discover_services(oci_connector: OCIConnector):
    """discover_services enumerates core active OCI services."""
    services = await oci_connector.discover_services()
    assert len(services) >= 5
    svc_names = [s["service_name"] for s in services]
    assert "compute" in svc_names
    assert "blockstorage" in svc_names
    assert "database" in svc_names
    assert "objectstorage" in svc_names
    assert "virtualnetwork" in svc_names


# ==============================================================================
# 4. Cost Ingestion, CSV Reports, & Negative Adjustments
# ==============================================================================


@pytest.mark.asyncio
async def test_oci_cost_bulk_ingestion_from_delivered_csv_fixture(oci_connector: OCIConnector):
    """Ingests delivered CSV usage reports from fixture and handles negative SLA credits."""
    cost_res = await oci_connector.collect_cost_bulk(
        start_date="2026-08-01",
        end_date="2026-09-27",
    )
    assert len(cost_res) >= 5

    # 1. Verify standard VM line item
    vm_cost = next(r for r in cost_res if "VM.Standard.E4.Flex" in r["description"])
    assert vm_cost["cost"] > 0
    assert vm_cost["billed_quantity"] > 0
    assert vm_cost["is_correction"] is False

    # 2. Verify negative cost adjustment (Outage SLA credit / correction line item)
    credit_item = next(r for r in cost_res if r.get("is_correction") is True or r["cost"] < 0)
    assert credit_item["cost"] < 0
    assert credit_item["is_correction"] is True
    assert "Outage SLA" in credit_item["description"]

    # 3. Verify total cost calculation reflects negative credits
    total_cost = sum(r["cost"] for r in cost_res)
    positive_sum = sum(r["cost"] for r in cost_res if r["cost"] > 0)
    assert total_cost < positive_sum  # Negative credits reduced total cost


@pytest.mark.asyncio
async def test_oci_cost_query_interactive_usage_api(oci_connector: OCIConnector):
    """Usage API requestSummarizedUsages queries support compartment_depth filtering."""
    # Query with depth 1
    depth_1_res = await oci_connector.collect_cost_query(
        query={"compartment_depth": 1, "service": "compute"}
    )
    assert len(depth_1_res) >= 1
    assert all(r["compartment_depth"] <= 1 for r in depth_1_res)

    # Query with specific service
    db_res = await oci_connector.collect_cost_query(query={"service": "database"})
    assert len(db_res) >= 1
    assert any("Autonomous" in r["description"] for r in db_res)


# ==============================================================================
# 5. Non-Retroactive Tag Attribution Invariant
# ==============================================================================


def test_oci_non_retroactive_tag_attribution_invariant(oci_connector: OCIConnector):
    """Tag-based cost attribution applies strictly from association timestamp onward and is NEVER retroactive."""
    cost_svc = oci_connector.cost_service

    # Tag associated on Sept 15, 2026
    tag_association_time = "2026-09-15T00:00:00Z"
    target_tag = "Operations.Environment=Production"

    # Evaluation for consumption BEFORE tag was associated (Sept 1 to Sept 10)
    eval_pre = cost_svc.evaluate_tag_attribution(
        start_date="2026-09-01",
        end_date="2026-09-10",
        tag_key_value=target_tag,
        tag_association_time=tag_association_time,
    )
    assert eval_pre["is_attributed"] is False
    assert eval_pre["attributed_cost"] == 0.0
    assert eval_pre["tag_attribution_note"] is not None
    assert "NEVER retroactive" in eval_pre["tag_attribution_note"]
    assert "precedes tag association" in eval_pre["tag_attribution_note"]

    # Evaluation for consumption AFTER tag was associated (Sept 16 to Sept 20)
    eval_post = cost_svc.evaluate_tag_attribution(
        start_date="2026-09-16",
        end_date="2026-09-20",
        tag_key_value=target_tag,
        tag_association_time=tag_association_time,
    )
    assert eval_post["is_attributed"] is True
    assert eval_post["attributed_cost"] > 0.0
    assert eval_post["tag_attribution_note"] is None


def test_oci_connector_tag_attribution_policy_disclosure(oci_connector: OCIConnector):
    """Connector surfaces explicit properties disclosing non-retroactive tag attribution policy."""
    policy = oci_connector.tag_attribution_policy
    assert "not retroactive" in policy.lower()
    assert "strictly from the time the tag was associated" in policy

    notice = oci_connector.tag_attribution_notice
    assert "Tags associated with resources" in notice
    assert "non-retroactive" in notice


# ==============================================================================
# 6. Tag Model (Free-Form, Defined, Cost-Tracking Limit)
# ==============================================================================


@pytest.mark.asyncio
async def test_oci_tag_model_three_tiers(oci_connector: OCIConnector):
    """Differentiates free-form tags, defined tags ({Namespace}.{Key}), and cost-tracking tags (max 10)."""
    tags_res = await oci_connector.collect_tags()
    assert len(tags_res) >= 6

    # 1. Free-form tag
    free_form = next(t for t in tags_res if t["tag_type"] == "FREE_FORM")
    assert free_form["namespace"] is None
    assert free_form["key"] == "Environment"
    assert free_form["canonical_key"] == "Environment"

    # 2. Defined tag
    defined = next(t for t in tags_res if t["tag_type"] == "DEFINED")
    assert defined["namespace"] == "Operations"
    assert defined["key"] == "Owner"
    assert defined["canonical_key"] == "Operations.Owner"

    # 3. Cost-tracking tag
    cost_track = next(t for t in tags_res if t["is_cost_tracking"] is True)
    assert cost_track["tag_type"] == "COST_TRACKING"
    assert cost_track["namespace"] == "Operations"
    assert cost_track["key"] == "CostCenter"
    assert cost_track["canonical_key"] == "Operations.CostCenter"


def test_oci_cost_tracking_tag_limit_enforcement():
    """Tenancy cannot exceed maximum 10 cost-tracking tags."""
    tag_svc = OCITagService()
    # 10 tags succeed
    for i in range(10):
        tag_svc.register_cost_tracking_tag(f"Namespace{i}.Tag{i}")

    # 11th tag is rejected / capped
    with pytest.raises(ValueError) as exc:
        tag_svc.register_cost_tracking_tag("Namespace11.Tag11")
    assert "Maximum 10 cost-tracking tags" in str(exc.value)


# ==============================================================================
# 7. Budgets (ACTUAL/FORECAST, Comparison Only)
# ==============================================================================


@pytest.mark.asyncio
async def test_oci_budgets_actual_forecast_comparison_only(oci_connector: OCIConnector):
    """Ingests OCI Budgets and alert rules (ACTUAL/FORECAST, ABSOLUTE/PERCENTAGE); comparison only."""
    budgets = await oci_connector.collect_budgets()
    assert len(budgets) >= 2

    # 1. Monthly Production Budget with ACTUAL and FORECAST alert rules
    prod_budget = next(b for b in budgets if "Production" in b["display_name"])
    assert prod_budget["amount"] == 50000.0
    assert prod_budget["is_authoritative"] is False  # Comparison-only
    assert len(prod_budget["alert_rules"]) >= 2

    actual_rule = next(r for r in prod_budget["alert_rules"] if r["threshold_type"] == "PERCENTAGE")
    assert actual_rule["type"] == "ACTUAL"
    assert actual_rule["threshold_value"] == 80.0

    forecast_rule = next(
        r
        for r in prod_budget["alert_rules"]
        if r["threshold_type"] == "PERCENTAGE" and r["type"] == "FORECAST"
    )
    assert forecast_rule["threshold_value"] == 100.0

    abs_rule = next(r for r in prod_budget["alert_rules"] if r["threshold_type"] == "ABSOLUTE")
    assert abs_rule["threshold_value"] == 45000.0

    # 2. Tag-targeted budget (Operations.CostCenter = CC-FIN-01)
    tag_budget = next(b for b in budgets if "Finance" in b["display_name"])
    assert tag_budget["is_authoritative"] is False
    assert tag_budget["target_type"] == "TAG"


# ==============================================================================
# 8. Pricing Catalog, Universal Credits (UCC), & Parity Disclosure
# ==============================================================================


@pytest.mark.asyncio
async def test_oci_pricing_contract_precedence_and_honest_parity_disclosure(
    oci_connector: OCIConnector,
):
    """Universal Credits (UCC) contract rates take precedence over public rate cards; discloses lack of dynamic API parity."""
    # 1. Honest parity disclosure verification
    assert oci_connector.has_dynamic_api_parity is False
    parity_disc = oci_connector.pricing_parity_disclosure
    assert "unauthenticated, dynamic" in parity_disc
    assert "published static rate cards" in parity_disc

    # 2. Public rate cards
    public_rates = await oci_connector.collect_pricing_public()
    assert len(public_rates) >= 4
    vm_public = next(r for r in public_rates if r["part_number"] == "B91124")
    assert vm_public["list_price"] == 0.025
    assert vm_public["is_contract_rate"] is False

    # 3. Negotiated UCC rates with precedence
    contract_rates = await oci_connector.collect_pricing_negotiated()
    assert len(contract_rates) >= 4
    vm_contract = next(r for r in contract_rates if r["part_number"] == "B91124")
    assert vm_contract["list_price"] == 0.025
    assert vm_contract["contract_price"] == 0.020  # 20% UCC discount
    assert vm_contract["effective_price"] == 0.020  # Contract precedence
    assert vm_contract["is_contract_rate"] is True

    # 4. Helper method resolves quote with precedence
    quote = oci_connector.get_effective_pricing("B91124")
    assert quote is not None
    assert quote.effective_price == 0.020
    assert quote.is_contract_rate is True

    # 5. Without contract entitlement, falls back to list price
    svc_no_contract = OCIPricingService(has_contract_entitlement=False)
    fallback = svc_no_contract.get_effective_quote("B91124")
    assert fallback is not None
    assert fallback.effective_price == 0.025
    assert fallback.is_contract_rate is False


# ==============================================================================
# 9. Usage Metrics & Coarse Interval Enforcement
# ==============================================================================


@pytest.mark.asyncio
async def test_oci_metrics_coarse_intervals_succeed(oci_connector: OCIConnector):
    """Hourly (PT1H) and daily (P1D) intervals succeed with coarse aggregates."""
    res_hourly = await oci_connector.collect_usage(interval="PT1H")
    assert len(res_hourly) >= 4
    assert res_hourly[0]["resolution"] == "1h"

    res_daily = await oci_connector.collect_usage(interval="P1D")
    assert len(res_daily) >= 4
    assert res_daily[0]["resolution"] == "1d"


@pytest.mark.asyncio
async def test_oci_metrics_sub_minute_intervals_forbidden(oci_connector: OCIConnector):
    """Sub-minute intervals are strictly forbidden and raise OCIMetricIntervalForbiddenException."""
    for bad_interval in ["PT30S", "30s", "PT1M", "10s", "1m"]:
        with pytest.raises(OCIMetricIntervalForbiddenException) as exc:
            await oci_connector.collect_usage(interval=bad_interval)
        assert exc.value.error_code == "OCI_METRIC_INTERVAL_FORBIDDEN"
        assert "coarse aggregates only" in str(exc.value).lower()


# ==============================================================================
# 10. Relationships & Partial Declaration
# ==============================================================================


@pytest.mark.asyncio
async def test_oci_relationships_minimal_structural_derivation_partial(oci_connector: OCIConnector):
    """Derives minimal structural relationships (VNIC, Volume, Subnet attachments); declared as PARTIAL."""
    assert oci_connector.relationships_is_partial is True

    rels = await oci_connector.discover_relationships()
    assert len(rels) >= 4

    rel_types = [r["relationship_type"] for r in rels]
    assert "VNIC_ATTACHMENT" in rel_types
    assert "VOLUME_ATTACHMENT" in rel_types
    assert "SUBNET_MEMBER" in rel_types
    assert all(r["is_structural_only"] is True for r in rels)
    assert all(r["is_partial"] is True for r in rels)


# ==============================================================================
# 11. Onboarding Wizard Non-Retroactive Tag Warning
# ==============================================================================


@pytest.mark.asyncio
async def test_oci_onboarding_wizard_non_retroactive_tag_warning():
    """Onboarding wizard explicitly warns that OCI tag attribution is never retroactive."""
    wizard_svc = OnboardingWizardService()
    tenant_ctx = TenantContext(tenant_id="tenant-oci-test-01", user_id="admin-oci")

    session = wizard_svc.start_session(
        user_id="admin-oci",
        tenant_context=tenant_ctx,
    )
    session.provider = ProviderType.OCI
    session.selected_scopes = ["ocid1.compartment.oc1..aaaaaaaaprodcomp1234567890abcdef"]
    wizard_svc._wizard_repo.save(session, tenant_context=tenant_ctx)

    estimate = wizard_svc.calculate_pre_completion_estimates(
        session_id=session.id,
        tenant_context=tenant_ctx,
    )
    assert len(estimate.warnings) >= 1
    oci_warning = next(w for w in estimate.warnings if "never retroactive" in w)
    assert (
        "OCI tag-based cost attribution applies strictly from the time of association onward"
        in oci_warning
    )
    assert "Tags associated today will not allocate historical consumption" in oci_warning


# ==============================================================================
# 12. Health Status, Provider Metadata, & Boundary Safety
# ==============================================================================


@pytest.mark.asyncio
async def test_oci_health_status_and_provider_metadata(oci_connector: OCIConnector):
    """Health status and provider metadata report valid capabilities and OCI attributes."""
    health = await oci_connector.health_status()
    assert health.healthy is True
    assert health.details["provider"] == ProviderType.OCI.value
    assert "aaaaaaaam57u7o6x3m7b5example" in health.details["tenancy_ocid"]
    assert health.details["has_dynamic_api_parity"] is False
    assert (
        "strictly from the time the tag was associated" in health.details["tag_attribution_policy"]
    )

    metadata = await oci_connector.provider_metadata()
    assert metadata.provider == ProviderType.OCI
    assert len(metadata.supported_regions) >= 8
    assert "us-ashburn-1" in metadata.supported_regions
    assert metadata.metadata["tag_attribution_policy"] == "NON-RETROACTIVE"
    assert metadata.metadata["has_dynamic_api_parity"] is False


@pytest.mark.asyncio
async def test_oci_connector_undeclared_capability_fast_fails():
    """Undeclared capabilities fail fast with UndeclaredCapabilityException."""
    limited_conn = OCIConnector(
        connector_id="conn-oci-limited",
        tenant_id="tenant-oci-test-01",
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
