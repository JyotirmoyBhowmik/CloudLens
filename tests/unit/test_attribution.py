"""Unit & Contract Tests for Attribution, Tag Normalisation, and Allocation (Prompt 08).

Acceptance Criteria:
1. A manually assigned owner survives three simulated re-discovery cycles unchanged.
2. Every allocated cost row can report which rule allocated it.
3. A split rule that does not sum to 100% is rejected at save time.
4. Unallocated cost appears explicitly in a test aggregation and is never hidden in 'Other'.
5. Do not infer ownership from a name pattern without an explicit configured rule.
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from api.cloudlens_api.main import app
from domain.attribution.aggregation import (
    AllocationAggregationService,
)
from domain.attribution.allocation import AllocationRuleEngine
from domain.attribution.curated import CuratedFieldProtectionService
from domain.attribution.models import (
    AllocatedCostRow,
    AllocationRule,
    AllocationRuleType,
    AllocationSplitTarget,
    AllocationSplitType,
    CuratedField,
    OwnershipResolutionRule,
)
from domain.attribution.ownership import OwnershipResolutionService
from domain.models.enums import PricingStatus, ProviderType, ServiceCategory
from domain.models.exceptions import (
    InvalidSplitRuleException,
    UnresolvedOwnershipException,
)
from domain.models.facts import CostFact
from domain.models.inventory import Application, Resource, Service
from domain.models.measures import FinancialMeasure
from normalisation.tags.models import (
    NormalizedTag,
    RawTagInput,
    TagCasePolicy,
    TagKeyConvention,
    TagSeparatorPolicy,
    TagSourceLevel,
)
from normalisation.tags.normaliser import TagNormalisationService

client = TestClient(app)


# ==============================================================================
# 1. Tag Normalisation Tests (Prompt 08 Item 54)
# ==============================================================================


def test_tag_normalisation_case_and_separator_conventions():
    """Validates configurable key convention (case and separator policy)."""
    service = TagNormalisationService()

    # Kebab-case (default)
    ns, key = service.normalise_key(
        "CostCenter_Code",
        convention=TagKeyConvention(
            case_policy=TagCasePolicy.KEBAB, separator_policy=TagSeparatorPolicy.HYPHEN
        ),
    )
    assert key == "cost-center-code"
    assert ns is None

    # Snake-case
    ns, key = service.normalise_key(
        "App.Environment-Name",
        convention=TagKeyConvention(
            case_policy=TagCasePolicy.SNAKE, separator_policy=TagSeparatorPolicy.UNDERSCORE
        ),
    )
    assert key == "app_environment_name"

    # CamelCase
    ns, key = service.normalise_key(
        "business_unit_lead",
        convention=TagKeyConvention(
            case_policy=TagCasePolicy.CAMEL, separator_policy=TagSeparatorPolicy.PRESERVE
        ),
    )
    assert key == "businessUnitLead"

    # UPPER with DOT
    ns, key = service.normalise_key(
        "service-tier",
        convention=TagKeyConvention(
            case_policy=TagCasePolicy.UPPER, separator_policy=TagSeparatorPolicy.DOT
        ),
    )
    assert key == "SERVICE.TIER"


def test_tag_normalisation_retains_original_key_and_source_level():
    """Validates original key retention and source hierarchy level tracking."""
    service = TagNormalisationService()

    raw = RawTagInput(
        key="Env_Name",
        value="Production",
        source_level=TagSourceLevel.SUBSCRIPTION,
        inherited=True,
    )
    norm = service.normalise_tag(raw)

    assert norm.original_key == "Env_Name"
    assert norm.normalized_key == "env-name"
    assert norm.value == "Production"
    assert norm.source_level == TagSourceLevel.SUBSCRIPTION
    assert norm.inherited is True
    assert norm.namespace is None


def test_oci_defined_tag_namespace_retained_separately():
    """Validates OCI defined-tag namespace is parsed and retained separately."""
    service = TagNormalisationService()

    # Dotted syntax representation
    raw1 = RawTagInput(
        key="Oracle-Tags.CostCenter",
        value="CC-4012",
        source_level=TagSourceLevel.COMPARTMENT,
    )
    norm1 = service.normalise_tag(raw1)
    assert norm1.original_key == "Oracle-Tags.CostCenter"
    assert norm1.normalized_key == "cost-center"
    assert norm1.namespace == "Oracle-Tags"
    assert norm1.source_level == TagSourceLevel.COMPARTMENT

    # Explicit namespace attribute
    raw2 = RawTagInput(
        key="CreatedBy",
        value="devops@corp.internal",
        namespace="Governance-Tags",
        source_level=TagSourceLevel.RESOURCE,
    )
    norm2 = service.normalise_tag(raw2)
    assert norm2.original_key == "CreatedBy"
    assert norm2.normalized_key == "created-by"
    assert norm2.namespace == "Governance-Tags"


# ==============================================================================
# 2. Ownership Resolution Precedence Chain Tests (Prompt 08 Items 55 & 56)
# ==============================================================================


@pytest.fixture
def base_resource() -> Resource:
    return Resource(
        id="res-vm-001",
        name="web-frontend-01",
        tenant_id="tenant-acme",
        scope_id="sub-12345",
        native_id="i-0123456789abcdef0",
        provider=ProviderType.AWS,
        service_id="srv-ec2",
        resource_type_id="rt-instance",
        region_id="reg-us-east-1",
        pricing_status=PricingStatus.PAID,
    )


def test_ownership_precedence_tier1_manual_assignment_wins(base_resource: Resource):
    """Tier 1: Manual assignment on the resource takes highest precedence."""
    service = OwnershipResolutionService()

    base_resource.owner_id = "curated-admin@company.com"
    curated_fields = {"owner_id"}

    tags = [
        NormalizedTag(
            original_key="owner",
            normalized_key="owner",
            value="tag-owner@company.com",
            source_level=TagSourceLevel.RESOURCE,
            inherited=False,
        )
    ]
    scope_map = {"sub-12345": "scope-owner@company.com"}
    app = Application(
        id="app-store",
        code="APM-01",
        name="WebStore",
        owner_id="app-owner@company.com",
    )
    base_resource.application_id = "app-store"

    result = service.resolve_ownership(
        resource=base_resource,
        tags=tags,
        scope_owner_map=scope_map,
        application=app,
        curated_fields=curated_fields,
    )

    assert result.winning_rule == OwnershipResolutionRule.MANUAL_ASSIGNMENT
    assert result.owner_id == "curated-admin@company.com"
    assert "Direct manual curation" in result.rule_description


def test_ownership_precedence_tier2_direct_tag_wins_over_inherited_and_scope(
    base_resource: Resource,
):
    """Tier 2: Ownership tag on the resource itself beats inherited tags and scope rules."""
    service = OwnershipResolutionService()

    tags = [
        NormalizedTag(
            original_key="owner",
            normalized_key="owner",
            value="direct-tag@company.com",
            source_level=TagSourceLevel.RESOURCE,
            inherited=False,
        ),
        NormalizedTag(
            original_key="owner",
            normalized_key="owner",
            value="inherited-tag@company.com",
            source_level=TagSourceLevel.SUBSCRIPTION,
            inherited=True,
        ),
    ]
    scope_map = {"sub-12345": "scope-owner@company.com"}

    result = service.resolve_ownership(
        resource=base_resource,
        tags=tags,
        scope_owner_map=scope_map,
    )

    assert result.winning_rule == OwnershipResolutionRule.OWNERSHIP_TAG
    assert result.owner_id == "direct-tag@company.com"


def test_ownership_precedence_tier3_inherited_tag_wins_over_scope_and_app(base_resource: Resource):
    """Tier 3: Inherited tag from scope hierarchy beats scope rule and application rule."""
    service = OwnershipResolutionService()

    tags = [
        NormalizedTag(
            original_key="owner",
            normalized_key="owner",
            value="inherited-tag@company.com",
            source_level=TagSourceLevel.SUBSCRIPTION,
            inherited=True,
        )
    ]
    scope_map = {"sub-12345": "scope-owner@company.com"}
    app = Application(
        id="app-store",
        code="APM-01",
        name="WebStore",
        owner_id="app-owner@company.com",
    )
    base_resource.application_id = "app-store"

    result = service.resolve_ownership(
        resource=base_resource,
        tags=tags,
        scope_owner_map=scope_map,
        application=app,
    )

    assert result.winning_rule == OwnershipResolutionRule.INHERITED_TAG
    assert result.owner_id == "inherited-tag@company.com"


def test_ownership_precedence_tier4_scope_rule_wins_over_app(base_resource: Resource):
    """Tier 4: Scope ownership rule beats application membership rule."""
    service = OwnershipResolutionService()

    scope_map = {"sub-12345": "scope-lead@company.com"}
    app = Application(
        id="app-store",
        code="APM-01",
        name="WebStore",
        owner_id="app-owner@company.com",
    )
    base_resource.application_id = "app-store"

    result = service.resolve_ownership(
        resource=base_resource,
        tags=[],
        scope_owner_map=scope_map,
        application=app,
    )

    assert result.winning_rule == OwnershipResolutionRule.SCOPE_RULE
    assert result.owner_id == "scope-lead@company.com"


def test_ownership_precedence_tier5_application_rule_wins_over_unresolved(base_resource: Resource):
    """Tier 5: Application membership rule resolves owner when prior rules do not match."""
    service = OwnershipResolutionService()

    app = Application(
        id="app-store",
        code="APM-01",
        name="WebStore",
        owner_id="app-lead@company.com",
    )
    base_resource.application_id = "app-store"

    result = service.resolve_ownership(
        resource=base_resource,
        tags=[],
        application=app,
    )

    assert result.winning_rule == OwnershipResolutionRule.APPLICATION_RULE
    assert result.owner_id == "app-lead@company.com"


def test_ownership_tier6_unresolved_raises_governance_exception(base_resource: Resource):
    """Tier 6: Unresolved produces explicit governance exception. Never silently assigned."""
    service = OwnershipResolutionService()

    # Silent fallback without raise returns UNRESOLVED with governance exception details
    res_silent = service.resolve_ownership(resource=base_resource, tags=[])
    assert res_silent.winning_rule == OwnershipResolutionRule.UNRESOLVED
    assert res_silent.owner_id is None
    assert res_silent.is_resolved is False
    assert "UNRESOLVED_OWNERSHIP" in str(res_silent.governance_exception)

    # When strict exception is requested, raises UnresolvedOwnershipException
    with pytest.raises(UnresolvedOwnershipException) as exc_info:
        service.resolve_ownership(resource=base_resource, tags=[], raise_on_unresolved=True)
    assert "failed all 5 ownership tiers" in str(exc_info.value)


def test_do_not_infer_ownership_from_name_pattern(base_resource: Resource):
    """Enforces: Do not infer ownership from a name pattern without an explicit configured rule."""
    service = OwnershipResolutionService()
    # Resource named 'john-doe-testing-box' must not be inferred as owned by 'john-doe'
    base_resource.name = "john-doe-testing-box"

    result = service.resolve_ownership(resource=base_resource, tags=[])
    assert result.winning_rule == OwnershipResolutionRule.UNRESOLVED
    assert result.owner_id is None


# ==============================================================================
# 3. Allocation Rule Engine Tests (Prompt 08 Items 57 & 58)
# ==============================================================================


@pytest.fixture
def sample_cost_fact() -> CostFact:
    return CostFact(
        id="fact-cost-001",
        tenant_id="tenant-acme",
        scope_id="sub-12345",
        resource_id="res-vm-001",
        charge_period_start=datetime(2026, 9, 1, 0, 0, tzinfo=UTC),
        charge_period_end=datetime(2026, 9, 2, 0, 0, tzinfo=UTC),
        billed_cost=FinancialMeasure(Decimal("100.00")),
        effective_cost=FinancialMeasure(Decimal("100.00")),
        billing_currency="USD",
    )


def test_split_rule_must_sum_to_100_percent_rejected_at_save_time():
    """Acceptance: A split rule that does not sum to 100% is rejected at save time."""
    engine = AllocationRuleEngine()

    # 1. Invalid split: sums to 90%
    with pytest.raises(InvalidSplitRuleException) as exc1:
        AllocationRule(
            name="Invalid Under-allocated Split",
            rule_type=AllocationRuleType.SPLIT_RULE,
            split_type=AllocationSplitType.PROPORTIONAL,
            split_targets=[
                AllocationSplitTarget(cost_center_code="CC-101", percentage=Decimal("40.0")),
                AllocationSplitTarget(cost_center_code="CC-102", percentage=Decimal("50.0")),
            ],
        )
    assert "expected exactly 100.0%" in str(exc1.value)

    # 2. Invalid split: sums to 105%
    with pytest.raises(InvalidSplitRuleException) as exc2:
        AllocationRule(
            name="Invalid Over-allocated Split",
            rule_type=AllocationRuleType.SPLIT_RULE,
            split_type=AllocationSplitType.FIXED,
            split_targets=[
                AllocationSplitTarget(cost_center_code="CC-101", percentage=Decimal("60.0")),
                AllocationSplitTarget(cost_center_code="CC-102", percentage=Decimal("45.0")),
            ],
        )
    assert "expected exactly 100.0%" in str(exc2.value)

    # 3. Valid split: exactly 100%
    valid_rule = AllocationRule(
        name="Valid 60/40 Split",
        rule_type=AllocationRuleType.SPLIT_RULE,
        split_type=AllocationSplitType.PROPORTIONAL,
        split_targets=[
            AllocationSplitTarget(cost_center_code="CC-101", percentage=Decimal("60.0")),
            AllocationSplitTarget(cost_center_code="CC-102", percentage=Decimal("40.0")),
        ],
    )
    engine.add_rule(valid_rule)
    assert len(engine.rules) == 1


def test_allocation_first_match_wins_precedence_and_explainability(
    sample_cost_fact: CostFact, base_resource: Resource
):
    """Acceptance: Every allocated cost row can report which rule allocated it. First-match-wins order."""
    engine = AllocationRuleEngine()

    # Rule 1: Direct Resource rule (highest tier)
    r_direct = AllocationRule(
        name="Direct Resource Rule for VM",
        rule_type=AllocationRuleType.DIRECT_RESOURCE,
        match_resource_id="res-vm-001",
        target_cost_center_code="CC-DIRECT-999",
    )
    # Rule 2: Tag rule
    r_tag = AllocationRule(
        name="Tag Rule for Env Prod",
        rule_type=AllocationRuleType.TAG_RULE,
        match_tag_key="env",
        match_tag_value="prod",
        target_cost_center_code="CC-TAG-888",
    )
    # Rule 3: Scope rule
    r_scope = AllocationRule(
        name="Scope Rule for Sub-12345",
        rule_type=AllocationRuleType.SCOPE_RULE,
        match_scope_id="sub-12345",
        target_cost_center_code="CC-SCOPE-777",
    )

    engine.add_rule(r_scope)
    engine.add_rule(r_tag)
    engine.add_rule(r_direct)

    tags = [
        NormalizedTag(
            original_key="env",
            normalized_key="env",
            value="prod",
            source_level=TagSourceLevel.RESOURCE,
        )
    ]

    # Evaluate: Direct rule must win despite tag and scope rules matching
    rows = engine.allocate_cost_fact(cost_fact=sample_cost_fact, resource=base_resource, tags=tags)
    assert len(rows) == 1
    row = rows[0]
    assert row.cost_center_code == "CC-DIRECT-999"
    assert row.winning_rule_type == AllocationRuleType.DIRECT_RESOURCE
    assert row.winning_rule_name == "Direct Resource Rule for VM"
    assert "Direct resource assignment matched" in row.rule_explanation


def test_split_rule_execution_reconciles_to_exact_penny(sample_cost_fact: CostFact):
    """Validates split rule allocation with 3 targets reconciling to exact total cost."""
    engine = AllocationRuleEngine()

    split_rule = AllocationRule(
        name="Three-Way Shared Split",
        rule_type=AllocationRuleType.SPLIT_RULE,
        split_type=AllocationSplitType.PROPORTIONAL,
        split_targets=[
            AllocationSplitTarget(cost_center_code="CC-A", percentage=Decimal("33.33")),
            AllocationSplitTarget(cost_center_code="CC-B", percentage=Decimal("33.33")),
            AllocationSplitTarget(cost_center_code="CC-C", percentage=Decimal("33.34")),
        ],
    )
    engine.add_rule(split_rule)

    rows = engine.allocate_cost_fact(cost_fact=sample_cost_fact)
    assert len(rows) == 3
    assert rows[0].allocated_amount == Decimal("33.33")
    assert rows[1].allocated_amount == Decimal("33.33")
    assert rows[2].allocated_amount == Decimal("33.34")

    # Exact penny sum check
    total_allocated = sum(r.allocated_amount for r in rows)
    assert total_allocated == Decimal("100.00")
    for r in rows:
        assert r.winning_rule_type == AllocationRuleType.SPLIT_RULE
        assert r.winning_rule_name == "Three-Way Shared Split"
        assert "Split rule" in r.rule_explanation


def test_unallocated_fallback_when_no_rules_match(sample_cost_fact: CostFact):
    """When no rules match, cost is attributed to UNALLOCATED fallback with audit explanation."""
    engine = AllocationRuleEngine()  # Empty engine
    rows = engine.allocate_cost_fact(cost_fact=sample_cost_fact)

    assert len(rows) == 1
    row = rows[0]
    assert row.cost_center_code == "UNALLOCATED"
    assert row.winning_rule_type == AllocationRuleType.UNALLOCATED
    assert row.winning_rule_id is None
    assert row.winning_rule_name == "Default Unallocated Fallback"
    assert "UNALLOCATED fallback" in row.rule_explanation


# ==============================================================================
# 4. Unallocated Cost Visibility & Aggregation Tests (Prompt 08 Item 58)
# ==============================================================================


def test_unallocated_cost_appears_explicitly_in_test_aggregation():
    """Acceptance: Unallocated cost appears explicitly in a test aggregation. Never absorbed in 'Other'."""
    agg_service = AllocationAggregationService()

    rows = [
        AllocatedCostRow(
            cost_fact_id="cf-1",
            scope_id="sub-1",
            total_cost=Decimal("500.00"),
            allocated_amount=Decimal("500.00"),
            cost_center_code="CC-PROD-01",
            winning_rule_type=AllocationRuleType.DIRECT_RESOURCE,
            winning_rule_name="Prod DB Rule",
            rule_explanation="Direct",
        ),
        AllocatedCostRow(
            cost_fact_id="cf-2",
            scope_id="sub-1",
            total_cost=Decimal("300.00"),
            allocated_amount=Decimal("300.00"),
            cost_center_code="CC-QA-02",
            winning_rule_type=AllocationRuleType.TAG_RULE,
            winning_rule_name="QA Tag Rule",
            rule_explanation="Tag",
        ),
        # Unallocated cost row
        AllocatedCostRow(
            cost_fact_id="cf-3",
            scope_id="sub-1",
            total_cost=Decimal("200.00"),
            allocated_amount=Decimal("200.00"),
            cost_center_code="UNALLOCATED",
            winning_rule_type=AllocationRuleType.UNALLOCATED,
            winning_rule_name="Default Unallocated Fallback",
            rule_explanation="Fallback",
        ),
    ]

    summary = agg_service.aggregate_by_cost_center(rows, other_threshold_percentage=Decimal("50.0"))

    assert summary.total_spend == Decimal("1000.00")
    assert summary.allocated_spend == Decimal("800.00")
    assert summary.unallocated_spend == Decimal("200.00")
    assert summary.allocated_percentage == Decimal("80.00")
    assert summary.unallocated_percentage == Decimal("20.00")

    # Verify UNALLOCATED is an explicit top-level bucket and was NOT absorbed into "OTHER"
    unalloc_bucket = next((b for b in summary.buckets if b.bucket_key == "UNALLOCATED"), None)
    assert unalloc_bucket is not None
    assert unalloc_bucket.is_unallocated is True
    assert unalloc_bucket.total_amount == Decimal("200.00")
    assert unalloc_bucket.percentage_of_total == Decimal("20.00")

    # Verify 'OTHER' bucket does not contain unallocated amount
    other_bucket = next((b for b in summary.buckets if b.bucket_key == "OTHER"), None)
    if other_bucket:
        assert other_bucket.total_amount != Decimal("200.00")


# ==============================================================================
# 5. Curated-Field Protection Tests (Prompt 08 Item 59)
# ==============================================================================


def test_manually_assigned_owner_survives_three_rediscovery_cycles_unchanged(
    base_resource: Resource,
):
    """Acceptance: A manually assigned owner survives three simulated re-discovery cycles unchanged."""
    curation_service = CuratedFieldProtectionService()

    # Step 1: Initial state
    base_resource.owner_id = "initial-discovered@corp.com"

    # Step 2: Administrator applies manual curation
    curation_service.protect_curation(
        resource=base_resource,
        field_name=CuratedField.OWNER,
        value="curated-architect@corp.com",
        actor="admin@corp.com",
        reason="Assigned to Cloud Architect as primary owner",
    )
    assert base_resource.owner_id == "curated-architect@corp.com"
    assert curation_service.is_curated(base_resource.id, CuratedField.OWNER)

    # Step 3: Run 3 simulated re-discovery cycles with conflicting discovered owners
    cycle_1 = base_resource.model_copy(deep=True)
    cycle_1.owner_id = "discovered-sync-cycle-1@corp.com"
    cycle_1.name = "web-frontend-01-renamed"

    cycle_2 = base_resource.model_copy(deep=True)
    cycle_2.owner_id = "discovered-sync-cycle-2@corp.com"
    cycle_2.name = "web-frontend-01-renamed"

    cycle_3 = base_resource.model_copy(deep=True)
    cycle_3.owner_id = None  # Telemetry returned empty owner tag
    cycle_3.name = "web-frontend-01-renamed"

    # Reconcile all 3 cycles
    reconciled = curation_service.simulate_rediscovery_cycles(
        resource=base_resource,
        cycles=[cycle_1, cycle_2, cycle_3],
        explicit_overwrite=False,
    )

    # Acceptance verified: Curated owner survived all 3 cycles completely unchanged!
    assert reconciled.owner_id == "curated-architect@corp.com"
    # While non-curated fields (e.g. name from cycle 1) were updated
    assert reconciled.name == "web-frontend-01-renamed"


def test_explicit_user_action_allows_curated_overwrite(base_resource: Resource):
    """Explicit user action permits intentional overwrite of curated fields."""
    curation_service = CuratedFieldProtectionService()

    curation_service.protect_curation(
        resource=base_resource,
        field_name=CuratedField.OWNER,
        value="curated-architect@corp.com",
        actor="admin@corp.com",
    )

    discovered = base_resource.model_copy(deep=True)
    discovered.owner_id = "new-authorized-owner@corp.com"

    # Explicit user action allowed
    updated = curation_service.reconcile_rediscovery(
        existing_resource=base_resource,
        discovered_resource=discovered,
        explicit_user_action=True,
        actor="admin@corp.com",
    )

    assert updated.owner_id == "new-authorized-owner@corp.com"
    assert not curation_service.is_curated(base_resource.id, CuratedField.OWNER)


# ==============================================================================
# 6. REST API Endpoint Tests
# ==============================================================================


def test_api_tag_normalise_endpoint():
    """POST /api/v1/attribution/tags/normalise."""
    payload = {
        "tags": [
            {
                "key": "Oracle-Tags.CostCenter",
                "value": "CC-901",
                "source_level": "COMPARTMENT",
            },
            {
                "key": "App_Environment",
                "value": "Staging",
                "source_level": "RESOURCE",
            },
        ]
    }
    resp = client.post("/api/v1/attribution/tags/normalise", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["normalized_key"] == "cost-center"
    assert data[0]["namespace"] == "Oracle-Tags"
    assert data[1]["normalized_key"] == "app-environment"


def test_api_allocation_rule_split_validation_endpoint():
    """POST /api/v1/attribution/allocation/rules validates 100% split."""
    # Invalid split: 70% + 20% = 90% -> 422 Unprocessable Entity
    invalid_payload = {
        "name": "Invalid Split Rule",
        "rule_type": "SPLIT_RULE",
        "split_type": "PROPORTIONAL",
        "split_targets": [
            {"cost_center_code": "CC-1", "percentage": "70.0"},
            {"cost_center_code": "CC-2", "percentage": "20.0"},
        ],
    }
    resp_fail = client.post("/api/v1/attribution/allocation/rules", json=invalid_payload)
    assert resp_fail.status_code == 422

    # Valid split: 50% + 50% = 100% -> 201 Created
    valid_payload = {
        "name": "Valid 50/50 Split",
        "rule_type": "SPLIT_RULE",
        "split_type": "PROPORTIONAL",
        "split_targets": [
            {"cost_center_code": "CC-1", "percentage": "50.0"},
            {"cost_center_code": "CC-2", "percentage": "50.0"},
        ],
    }
    resp_ok = client.post("/api/v1/attribution/allocation/rules", json=valid_payload)
    assert resp_ok.status_code == 201
    assert resp_ok.json()["name"] == "Valid 50/50 Split"


def test_service_rule_allocation_matching(sample_cost_fact: CostFact):
    """Tier 4: Service rule matches canonical service or FOCUS service category."""
    engine = AllocationRuleEngine()
    srv_rule = AllocationRule(
        name="All Storage Rule",
        rule_type=AllocationRuleType.SERVICE_RULE,
        match_service_category=ServiceCategory.STORAGE.value,
        target_cost_center_code="CC-SHARED-STORAGE",
    )
    engine.add_rule(srv_rule)

    storage_service = Service(
        id="srv-s3",
        provider=ProviderType.AWS,
        service_code="AmazonS3",
        name="Simple Storage Service",
        category=ServiceCategory.STORAGE,
    )

    rows = engine.allocate_cost_fact(cost_fact=sample_cost_fact, service=storage_service)
    assert len(rows) == 1
    assert rows[0].cost_center_code == "CC-SHARED-STORAGE"
    assert rows[0].winning_rule_type == AllocationRuleType.SERVICE_RULE
    assert "service category STORAGE" in rows[0].rule_explanation


def test_curated_protection_survives_for_all_protected_fields(base_resource: Resource):
    """Prompt 08 Item 59: owner, application, environment, cost centre survive re-discovery."""
    curation_service = CuratedFieldProtectionService()

    # Manually curate all fields
    curation_service.protect_curation(
        base_resource, CuratedField.OWNER, "lead@corp.com", actor="admin"
    )
    curation_service.protect_curation(
        base_resource, CuratedField.APPLICATION, "app-core-banking", actor="admin"
    )
    curation_service.protect_curation(
        base_resource, CuratedField.ENVIRONMENT, "env-prod-pci", actor="admin"
    )
    curation_service.protect_curation(
        base_resource, CuratedField.COST_CENTER, "CC-9999", actor="admin"
    )

    discovered = base_resource.model_copy(deep=True)
    discovered.owner_id = "alien-owner@corp.com"
    discovered.application_id = "app-other"
    discovered.environment_id = "env-dev"
    discovered.cost_center_id = "CC-0000"

    reconciled = curation_service.reconcile_rediscovery(
        existing_resource=base_resource,
        discovered_resource=discovered,
        explicit_user_action=False,
    )

    # All curated fields survive
    assert reconciled.owner_id == "lead@corp.com"
    assert reconciled.application_id == "app-core-banking"
    assert reconciled.environment_id == "env-prod-pci"
    assert reconciled.cost_center_id == "CC-9999"


def test_allocation_aggregation_by_business_unit_and_rule_type():
    """Validates multidimensional aggregations keeping UNALLOCATED visible."""
    agg_service = AllocationAggregationService()
    rows = [
        AllocatedCostRow(
            cost_fact_id="cf-1",
            scope_id="sub-1",
            total_cost=Decimal("150.00"),
            allocated_amount=Decimal("150.00"),
            cost_center_code="CC-1",
            business_unit_code="BU_RETAIL",
            winning_rule_type=AllocationRuleType.DIRECT_RESOURCE,
            winning_rule_name="Rule 1",
            rule_explanation="Direct",
        ),
        AllocatedCostRow(
            cost_fact_id="cf-2",
            scope_id="sub-1",
            total_cost=Decimal("50.00"),
            allocated_amount=Decimal("50.00"),
            cost_center_code="UNALLOCATED",
            business_unit_code=None,
            winning_rule_type=AllocationRuleType.UNALLOCATED,
            winning_rule_name="Default",
            rule_explanation="Fallback",
        ),
    ]

    # By BU
    summary_bu = agg_service.aggregate_by_business_unit(rows)
    assert summary_bu.total_spend == Decimal("200.00")
    assert summary_bu.unallocated_spend == Decimal("50.00")
    unalloc_bu = next(b for b in summary_bu.buckets if b.bucket_key == "UNALLOCATED")
    assert unalloc_bu.total_amount == Decimal("50.00")

    # By winning rule tier
    summary_rule = agg_service.aggregate_by_winning_rule_type(rows)
    assert len(summary_rule.buckets) == 2
    rule_types = {b.bucket_key for b in summary_rule.buckets}
    assert "DIRECT_RESOURCE" in rule_types
    assert "UNALLOCATED" in rule_types


def test_api_ownership_resolve_endpoint(base_resource: Resource):
    """POST /api/v1/attribution/ownership/resolve endpoint."""
    payload = {
        "resource": base_resource.model_dump(mode="json"),
        "tags": [
            {
                "original_key": "owner",
                "normalized_key": "owner",
                "value": "dev@corp.internal",
                "source_level": "RESOURCE",
                "inherited": False,
            }
        ],
        "raise_on_unresolved": False,
    }
    resp = client.post("/api/v1/attribution/ownership/resolve", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["winning_rule"] == "OWNERSHIP_TAG"
    assert data["owner_id"] == "dev@corp.internal"
    assert data["is_resolved"] is True
