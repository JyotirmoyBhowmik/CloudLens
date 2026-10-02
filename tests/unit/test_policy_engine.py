"""Comprehensive Unit and Integration Tests for Governance Policy Engine (Prompt 30).

Enforces:
- FR-740: Governance policies must be declarative, versioned, and definable without code modification or deployment.
- FR-741: Policies must support simulate and enforce modes, with simulation producing findings without alerting.
- FR-742: A policy condition that cannot be evaluated for an entity must produce 'Not Evaluable', never False / violation.
- FR-743: Policy exemptions must be time-boxed, justified, approved, and reported while active.
- FR-744: Policy violation findings must be deduplicated against open findings for the same entity and condition.
- FR-745: Governance exception counts and resolution times must be trended over time and reportable.
- FR-746: Sixteen default policies (POL-01 to POL-16), disabled by default except connector health.
- Negative constraint: Do NOT enable policies by default (only connector health is enabled).
- Negative constraint: Do NOT let a missing field produce a violation.
- Negative constraint: Do NOT allow an exemption without justification and expiry.
- Prompt 13 Item 84: 100% TenantContext validation and tenant isolation across all repository methods.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from starlette.testclient import TestClient

from api.cloudlens_api.main import app
from domain.models.enums import (
    ConditionOperator,
    EvaluationOutcome,
    FindingLifecycleStatus,
    PolicyCategory,
    PolicyEffect,
    PolicyMode,
    PolicySeverity,
)
from domain.models.exceptions import (
    InvalidExemptionException,
    MissingTenantContextException,
)
from domain.policy.evaluator import PolicyEvaluator
from domain.policy.models import (
    DeclarativeCondition,
    PolicyCreateDTO,
    PolicyDefinition,
    PolicyExemptionCreateDTO,
    PolicyFinding,
    PolicyUpdateDTO,
    TargetSelector,
)
from domain.policy.repository import (
    get_policy_repository,
    reset_policy_repository,
)
from domain.policy.service import (
    PolicyService,
    reset_policy_service,
)
from domain.tenant.context import TenantContext

# ==============================================================================
# Fixtures
# ==============================================================================


@pytest.fixture(autouse=True)
def cleanup_policy_state():
    """Ensures clean repository and service instances between tests."""
    reset_policy_repository()
    reset_policy_service()
    yield
    reset_policy_repository()
    reset_policy_service()


@pytest.fixture
def tenant_ctx() -> TenantContext:
    """Standard authenticated tenant context."""
    return TenantContext(
        tenant_id="tenant-acme-corp",
        user_id="user-compliance-lead",
        correlation_id=str(uuid.uuid4()),
    )


@pytest.fixture
def other_tenant_ctx() -> TenantContext:
    """Secondary tenant context for isolation testing."""
    return TenantContext(
        tenant_id="tenant-beta-inc",
        user_id="user-beta-admin",
        correlation_id=str(uuid.uuid4()),
    )


@pytest.fixture
def policy_service() -> PolicyService:
    """Instantiates clean PolicyService instance."""
    return PolicyService()


# ==============================================================================
# 1. Sixteen Default Policies & Connector Health Exception (FR-746)
# ==============================================================================


class TestDefaultPoliciesAndSeeding:
    """Tests for canonical default policies catalogue and default enablement rules."""

    def test_default_sixteen_policies_seeded_and_only_connector_health_enabled(
        self, policy_service: PolicyService, tenant_ctx: TenantContext
    ):
        """FR-746: Default policies (POL-01 to POL-16+) must be present.

        Strict constraint: All policies must be disabled by default EXCEPT POL-08 (Connector Health).
        """
        policies = policy_service.list_policies(tenant_context=tenant_ctx)
        policy_ids = [p.id for p in policies]

        # Verify key mandatory categories from prompt
        assert "POL-01" in policy_ids  # Budget
        assert "POL-02" in policy_ids  # Runtime
        assert "POL-03" in policy_ids  # Usage
        assert "POL-04" in policy_ids  # Cost threshold
        assert "POL-05" in policy_ids  # Tagging
        assert "POL-06" in policy_ids  # Naming
        assert "POL-07" in policy_ids  # Ownership
        assert "POL-08" in policy_ids  # Connector health
        assert "POL-09" in policy_ids  # Data retention
        assert "POL-10" in policy_ids  # Access
        assert "POL-11" in policy_ids  # Zero-usage cost
        assert "POL-12" in policy_ids  # Region compliance

        # Check total default count >= 16
        assert len(policies) >= 16

        # Check enablement status
        for p in policies:
            if p.id == "POL-08":
                assert p.enabled is True, f"POL-08 must be enabled by default, got {p.enabled}"
                assert p.category == PolicyCategory.CONNECTOR_HEALTH
                assert p.mode == PolicyMode.ENFORCE
            else:
                assert p.enabled is False, (
                    f"Policy '{p.id}' ({p.name}) MUST be disabled by default to prevent platform shouting"
                )


# ==============================================================================
# 2. Dynamic Authoring, Versioning & Enabling (FR-740)
# ==============================================================================


class TestPolicyAuthoringAndVersioning:
    """Tests declarative creation, immutable version increments, and dynamic toggles."""

    def test_create_custom_policy_without_deployment(
        self, policy_service: PolicyService, tenant_ctx: TenantContext
    ):
        """A policy can be created dynamically with version 1 without code deployment."""
        dto = PolicyCreateDTO(
            id="POL-CUSTOM-TAGS",
            name="Strict FinOps CostCenter Tagging",
            description="Requires CostCenter tag on all compute resources",
            category=PolicyCategory.TAGGING,
            target_selector=TargetSelector(resource_types=["COMPUTE_INSTANCE"]),
            condition=DeclarativeCondition(
                operator=ConditionOperator.ALL_PRESENT,
                field="tags",
                value=["CostCenter", "Environment"],
            ),
            effect=PolicyEffect.AUDIT_FINDING,
            severity=PolicySeverity.HIGH,
            mode=PolicyMode.SIMULATE,
            enabled=False,
        )

        policy = policy_service.create_policy(dto, tenant_context=tenant_ctx)
        assert policy.id == "POL-CUSTOM-TAGS"
        assert policy.version == 1
        assert policy.enabled is False
        assert policy.updated_by == "user-compliance-lead"

    def test_update_policy_increments_version_and_preserves_history(
        self, policy_service: PolicyService, tenant_ctx: TenantContext
    ):
        """Updating a policy increments version (1 -> 2) and preserves historical snapshot."""
        # 1. Create v1
        dto = PolicyCreateDTO(
            id="POL-STORAGE-LIMIT",
            name="Max Disk Size Guardrail",
            description="Prevents disks > 1000GB",
            category=PolicyCategory.USAGE,
            condition=DeclarativeCondition(
                operator=ConditionOperator.LESS_THAN_OR_EQUAL,
                field="disk_gb",
                value=1000,
            ),
            severity=PolicySeverity.MEDIUM,
        )
        p1 = policy_service.create_policy(dto, tenant_context=tenant_ctx)
        assert p1.version == 1

        # 2. Update to v2 with relaxed limit
        update_dto = PolicyUpdateDTO(
            description="Relaxed to 2000GB for analytics workloads",
            condition=DeclarativeCondition(
                operator=ConditionOperator.LESS_THAN_OR_EQUAL,
                field="disk_gb",
                value=2000,
            ),
            severity=PolicySeverity.HIGH,
        )
        p2 = policy_service.update_policy(
            "POL-STORAGE-LIMIT", update_dto, tenant_context=tenant_ctx
        )
        assert p2.version == 2
        assert p2.severity == PolicySeverity.HIGH
        assert p2.condition.value == 2000

        # 3. Retrieve historical v1 snapshot
        v1_hist = policy_service.get_policy_version(
            "POL-STORAGE-LIMIT", 1, tenant_context=tenant_ctx
        )
        assert v1_hist.version == 1
        assert v1_hist.condition.value == 1000
        assert v1_hist.severity == PolicySeverity.MEDIUM

    def test_enable_and_disable_policy_dynamically(
        self, policy_service: PolicyService, tenant_ctx: TenantContext
    ):
        """Policy can be enabled/disabled at runtime without changing version."""
        p = policy_service.get_policy("POL-01", tenant_context=tenant_ctx)
        assert p.enabled is False

        # Enable
        enabled_p = policy_service.set_policy_enabled("POL-01", True, tenant_context=tenant_ctx)
        assert enabled_p.enabled is True
        assert enabled_p.version == 1

        # Disable
        disabled_p = policy_service.set_policy_enabled("POL-01", False, tenant_context=tenant_ctx)
        assert disabled_p.enabled is False
        assert disabled_p.version == 1


# ==============================================================================
# 3. Not Evaluable Outcome (FR-742)
# ==============================================================================


class TestNotEvaluableHandling:
    """Tests the mandatory Not Evaluable outcome when fields are not supplied."""

    def test_missing_field_produces_not_evaluable_never_violation(self):
        """FR-742: Where a policy references a field that a provider does not supply,
        the result is Not Evaluable, never a violation.
        """
        policy = PolicyDefinition(
            id="POL-METRICS-CPU",
            version=1,
            name="CPU Idle Check",
            description="Flags instances with CPU < 5%",
            category=PolicyCategory.IDLE_RESOURCE,
            condition=DeclarativeCondition(
                operator=ConditionOperator.GREATER_THAN_OR_EQUAL,
                field="metrics.cpu_utilization",
                value=5.0,
            ),
            mode=PolicyMode.SIMULATE,
            enabled=True,
        )

        # Entity completely lacks metrics.cpu_utilization
        entity_missing_metrics = {
            "id": "res-storage-volume-001",
            "name": "backup-volume-01",
            "resource_type": "BLOCK_VOLUME",
            "provider": "AWS",
            # No 'metrics' dict or 'metrics.cpu_utilization' supplied
        }

        result, finding = PolicyEvaluator.evaluate_policy_against_entity(
            policy, entity_missing_metrics
        )

        assert result.outcome == EvaluationOutcome.NOT_EVALUABLE
        assert "not supplied" in result.reason.lower()
        assert "metrics.cpu_utilization" in result.missing_fields
        # Negative constraint: Zero findings created for NOT_EVALUABLE
        assert finding is None

    def test_explicit_unsupported_field_produces_not_evaluable(self):
        """Entity declaring unsupported_fields yields Not Evaluable."""
        policy = PolicyDefinition(
            id="POL-DISK-IOPS",
            version=1,
            name="Disk IOPS Policy",
            description="Checks disk IOPS capability",
            category=PolicyCategory.USAGE,
            condition=DeclarativeCondition(
                operator=ConditionOperator.LESS_THAN_OR_EQUAL,
                field="iops_provisioned",
                value=10000,
            ),
        )

        entity_with_declared_gap = {
            "id": "res-db-001",
            "iops_provisioned": 50000,
            "unsupported_fields": ["iops_provisioned"],  # Provider declares this metric unsupplied
        }

        result, finding = PolicyEvaluator.evaluate_policy_against_entity(
            policy, entity_with_declared_gap
        )
        assert result.outcome == EvaluationOutcome.NOT_EVALUABLE
        assert finding is None


# ==============================================================================
# 4. Simulation vs Enforce Modes (FR-741)
# ==============================================================================


class TestSimulateAndEnforceModes:
    """Tests simulation produces findings without raising alerts."""

    def test_simulation_produces_findings_and_zero_alerts(
        self, policy_service: PolicyService, tenant_ctx: TenantContext
    ):
        """FR-741: Simulation records findings without raising alerts."""
        test_entities = [
            {
                "id": "vm-prod-01",
                "name": "vm-prod-01",
                "resource_type": "COMPUTE_INSTANCE",
                "tags": {"CostCenter": "Finance"},  # Missing 'Owner' and 'Environment'
            },
            {
                "id": "vm-prod-02",
                "name": "vm-prod-02",
                "resource_type": "COMPUTE_INSTANCE",
                "tags": {
                    "CostCenter": "Finance",
                    "Owner": "finops@acme.com",
                    "Environment": "PROD",
                },  # Fully compliant
            },
        ]

        # Simulate POL-05 (Tagging compliance)
        sim_resp = policy_service.simulate_policy(
            policy_id="POL-05",
            entities=test_entities,
            tenant_context=tenant_ctx,
        )

        assert sim_resp.total_evaluated == 2
        assert sim_resp.violations_count == 1
        assert sim_resp.compliant_count == 1
        assert sim_resp.alerts_raised == 0  # STRICT: ZERO ALERTS IN SIMULATION

        # Verify finding attributes
        assert len(sim_resp.findings) == 1
        fnd = sim_resp.findings[0]
        assert fnd.entity_id == "vm-prod-01"
        assert fnd.policy_id == "POL-05"
        assert fnd.mode == PolicyMode.SIMULATE
        assert fnd.is_alertable is False
        assert fnd.alerts_suppressed is True

    def test_enforce_mode_enables_alertable_flag(
        self, policy_service: PolicyService, tenant_ctx: TenantContext
    ):
        """Enforce mode marks findings as alertable."""
        # Enable POL-05 and set to ENFORCE mode
        p5 = policy_service.get_policy("POL-05", tenant_context=tenant_ctx)
        p5.enabled = True
        p5.mode = PolicyMode.ENFORCE
        policy_service.repo.save_policy(p5, tenant_context=tenant_ctx)

        entities = [
            {
                "id": "vm-non-compliant",
                "name": "vm-bad",
                "tags": {},  # Violates tagging policy
            }
        ]

        batch_resp = policy_service.evaluate_batch(
            entities, tenant_context=tenant_ctx, policy_ids=["POL-05"]
        )

        assert batch_resp.violations_detected == 1
        assert batch_resp.alerts_generated == 1
        assert len(batch_resp.findings) == 1
        fnd = batch_resp.findings[0]
        assert fnd.mode == PolicyMode.ENFORCE
        assert fnd.is_alertable is True
        assert fnd.alerts_suppressed is False


# ==============================================================================
# 5. Finding Deduplication and Clearing (FR-744)
# ==============================================================================


class TestFindingDeduplicationAndClearing:
    """Tests deduplication against open findings and clearing upon condition resolution."""

    def test_deduplication_against_open_finding(
        self, policy_service: PolicyService, tenant_ctx: TenantContext
    ):
        """FR-744: Repeated violation evaluations update existing open finding rather than duplicating."""
        # Enable POL-08 (Connector Health)
        violating_connector = [
            {
                "id": "conn-aws-prod",
                "name": "AWS Production Connector",
                "resource_type": "CONNECTOR",
                "hours_since_last_sync": 36.0,  # Violates <= 24h SLA
            }
        ]

        # Cycle 1: creates finding
        res1 = policy_service.evaluate_batch(
            violating_connector, tenant_context=tenant_ctx, policy_ids=["POL-08"]
        )
        assert res1.new_findings_created == 1
        assert res1.existing_findings_updated == 0

        findings = policy_service.list_findings(tenant_context=tenant_ctx)
        assert len(findings) == 1
        assert findings[0].consecutive_occurrences == 1

        # Cycle 2: evaluates again while still violating
        violating_connector[0]["hours_since_last_sync"] = 38.0
        res2 = policy_service.evaluate_batch(
            violating_connector, tenant_context=tenant_ctx, policy_ids=["POL-08"]
        )
        assert res2.new_findings_created == 0
        assert res2.existing_findings_updated == 1

        # Verify only 1 finding exists in repository with updated counter
        findings_after = policy_service.list_findings(tenant_context=tenant_ctx)
        assert len(findings_after) == 1
        assert findings_after[0].id == findings[0].id
        assert findings_after[0].consecutive_occurrences == 2
        assert findings_after[0].observed_value == 38.0

    def test_finding_clears_when_condition_clears(
        self, policy_service: PolicyService, tenant_ctx: TenantContext
    ):
        """FR-744: Finding status transitions to CLEARED when entity returns to compliance."""
        connector = {
            "id": "conn-azure-corp",
            "name": "Azure Primary Connector",
            "resource_type": "CONNECTOR",
            "hours_since_last_sync": 48.0,  # Violation
        }

        # Cycle 1: Violation
        policy_service.evaluate_batch([connector], tenant_context=tenant_ctx, policy_ids=["POL-08"])
        open_findings = policy_service.list_findings(
            tenant_context=tenant_ctx, status=FindingLifecycleStatus.OPEN
        )
        assert len(open_findings) == 1
        assert open_findings[0].cleared_at is None

        # Cycle 2: Connector is resynced and compliant
        connector["hours_since_last_sync"] = 2.0  # Compliant!
        res2 = policy_service.evaluate_batch(
            [connector], tenant_context=tenant_ctx, policy_ids=["POL-08"]
        )
        assert res2.findings_cleared == 1

        # Check repository state
        cleared_findings = policy_service.list_findings(
            tenant_context=tenant_ctx, status=FindingLifecycleStatus.CLEARED
        )
        assert len(cleared_findings) == 1
        assert cleared_findings[0].id == open_findings[0].id
        assert cleared_findings[0].cleared_at is not None


# ==============================================================================
# 6. Time-Boxed, Justified Exemptions (FR-743)
# ==============================================================================


class TestPolicyExemptions:
    """Tests time-boxed, justified policy exemptions."""

    def test_exemption_negative_constraints_missing_justification_or_past_expiry(
        self, policy_service: PolicyService, tenant_ctx: TenantContext
    ):
        """Negative constraints: Reject exemptions without justification or with invalid expiry."""
        future_time = dt.datetime.now(dt.UTC) + dt.timedelta(days=30)
        past_time = dt.datetime.now(dt.UTC) - dt.timedelta(days=1)

        # 1. Empty justification
        with pytest.raises(InvalidExemptionException, match="justification is mandatory"):
            policy_service.create_exemption(
                PolicyExemptionCreateDTO(
                    policy_id="POL-01",
                    entity_id="res-001",
                    justification="   ",
                    expires_at=future_time,
                ),
                tenant_context=tenant_ctx,
            )

        # 2. Past expiry
        with pytest.raises(InvalidExemptionException, match="must be strictly in the future"):
            policy_service.create_exemption(
                PolicyExemptionCreateDTO(
                    policy_id="POL-01",
                    entity_id="res-001",
                    justification="Migration test exemption",
                    expires_at=past_time,
                ),
                tenant_context=tenant_ctx,
            )

    def test_active_exemption_suppresses_violation_and_reverts_upon_expiry(
        self, policy_service: PolicyService, tenant_ctx: TenantContext
    ):
        """Active exemption produces EXEMPTED outcome, which reverts when expired."""
        entity = {
            "id": "vm-legacy-monolith",
            "name": "Legacy Core VM",
            "resource_type": "COMPUTE_INSTANCE",
            "tags": {},  # Violates POL-05
        }

        # Enable POL-05
        p5 = policy_service.get_policy("POL-05", tenant_context=tenant_ctx)
        p5.enabled = True
        policy_service.repo.save_policy(p5, tenant_context=tenant_ctx)

        # 1. Create 7-day exemption
        expiry = dt.datetime.now(dt.UTC) + dt.timedelta(days=7)
        exm = policy_service.create_exemption(
            PolicyExemptionCreateDTO(
                policy_id="POL-05",
                entity_id="vm-legacy-monolith",
                justification="Exempted during Q3 cloud migration sprint approved by Architecture Board",
                expires_at=expiry,
            ),
            tenant_context=tenant_ctx,
        )
        assert exm.is_active() is True

        # 2. Evaluate with active exemption
        batch_res = policy_service.evaluate_batch(
            [entity], tenant_context=tenant_ctx, policy_ids=["POL-05"]
        )
        assert batch_res.exempted_count == 1
        assert batch_res.violations_detected == 0

        # 3. Test after expiry (8 days later)
        eval_time_future = dt.datetime.now(dt.UTC) + dt.timedelta(days=8)
        assert exm.is_active(eval_time_future) is False

        # Evaluator directly with future timestamp
        res_future, finding_future = PolicyEvaluator.evaluate_policy_against_entity(
            p5, entity, active_exemptions=[exm], as_of=eval_time_future
        )
        assert res_future.outcome == EvaluationOutcome.VIOLATION
        assert finding_future is not None


# ==============================================================================
# 7. Governance Exception Trending Over Time (FR-745)
# ==============================================================================


class TestGovernanceExceptionTrending:
    """Tests governance exception counting and trend tracking over time."""

    def test_governance_exception_trend_report(
        self, policy_service: PolicyService, tenant_ctx: TenantContext
    ):
        """FR-745: Governance exception counts and resolution times trended over time."""
        now = dt.datetime(2026, 6, 15, 12, 0, 0, tzinfo=dt.UTC)
        t_day1 = now - dt.timedelta(days=4)
        t_day2 = now - dt.timedelta(days=2)

        # Seed findings manually into repository
        f1 = PolicyFinding(
            policy_id="POL-05",
            policy_version=1,
            entity_id="res-01",
            severity=PolicySeverity.HIGH,
            category=PolicyCategory.TAGGING,
            mode=PolicyMode.ENFORCE,
            lifecycle_status=FindingLifecycleStatus.CLEARED,
            first_detected_at=t_day1,
            last_evaluated_at=t_day2,
            cleared_at=t_day2,  # Resolved after 48 hours
        )
        f2 = PolicyFinding(
            policy_id="POL-01",
            policy_version=1,
            entity_id="res-02",
            severity=PolicySeverity.CRITICAL,
            category=PolicyCategory.BUDGET,
            mode=PolicyMode.ENFORCE,
            lifecycle_status=FindingLifecycleStatus.OPEN,
            first_detected_at=t_day2,
            last_evaluated_at=now,
        )

        policy_service.repo.save_finding(f1, tenant_context=tenant_ctx)
        policy_service.repo.save_finding(f2, tenant_context=tenant_ctx)

        start_date = (now - dt.timedelta(days=5)).date()
        end_date = now.date()

        report = policy_service.get_governance_trend(
            start_date=start_date, end_date=end_date, tenant_context=tenant_ctx
        )

        assert report.current_open_count == 1
        assert report.total_detected_in_period == 2
        assert report.total_cleared_in_period == 1
        assert report.mttr_hours == 48.0
        assert report.resolution_rate_pct == 50.0
        assert len(report.points) == (end_date - start_date).days + 1


# ==============================================================================
# 8. Tenant Isolation & Context Enforcement (Prompt 13 Item 84)
# ==============================================================================


class TestMultiTenantIsolation:
    """Verifies strict tenant isolation and context validation."""

    def test_repository_enforces_tenant_context_100_percent(self):
        """Passing None tenant_context raises MissingTenantContextException."""
        repo = get_policy_repository()
        with pytest.raises(MissingTenantContextException):
            repo.list_policies(tenant_context=None)  # type: ignore

    def test_tenant_data_isolation(
        self,
        policy_service: PolicyService,
        tenant_ctx: TenantContext,
        other_tenant_ctx: TenantContext,
    ):
        """Data created in Tenant A is invisible and isolated from Tenant B."""
        # Tenant A creates custom policy
        dto = PolicyCreateDTO(
            id="POL-TENANT-A",
            name="Tenant A Policy",
            description="Tenant A private policy",
            category=PolicyCategory.NAMING,
            condition=DeclarativeCondition(
                operator=ConditionOperator.IS_NOT_NULL, field="name", value=None
            ),
        )
        policy_service.create_policy(dto, tenant_context=tenant_ctx)

        # Tenant A sees it
        assert policy_service.repo.get_policy("POL-TENANT-A", tenant_context=tenant_ctx) is not None

        # Tenant B does NOT see it
        assert (
            policy_service.repo.get_policy("POL-TENANT-A", tenant_context=other_tenant_ctx) is None
        )


# ==============================================================================
# 9. REST API Contract Tests
# ==============================================================================


class TestPolicyAPIContracts:
    """Tests FastAPI endpoint contracts."""

    @pytest.fixture
    def client(self) -> TestClient:
        return TestClient(app)

    def test_api_list_policies_and_catalogue(self, client: TestClient):
        """GET /api/v1/policies and /catalogue return default catalogue."""
        res_cat = client.get("/api/v1/policies/catalogue")
        assert res_cat.status_code == 200
        cat_data = res_cat.json()
        assert cat_data["total"] >= 16

        res_list = client.get(
            "/api/v1/policies",
            headers={"X-Tenant-ID": "tenant-api-test", "X-User-ID": "user-test"},
        )
        assert res_list.status_code == 200
        assert res_list.json()["total"] >= 16

    def test_api_simulate_policy(self, client: TestClient):
        """POST /api/v1/policies/simulate returns findings with 0 alerts raised."""
        payload = {
            "policy_id": "POL-05",
            "entities": [
                {
                    "id": "server-001",
                    "tags": {"CostCenter": "Ops"},  # Missing Owner and Environment
                }
            ],
        }
        res = client.post(
            "/api/v1/policies/simulate",
            json=payload,
            headers={"X-Tenant-ID": "tenant-api-test", "X-User-ID": "user-test"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["mode"] == "SIMULATE"
        assert data["violations_count"] == 1
        assert data["alerts_raised"] == 0
        assert len(data["findings"]) == 1

    def test_api_create_exemption_and_governance_trend(self, client: TestClient):
        """POST /api/v1/policies/exemptions and GET /api/v1/policies/trend contracts."""
        future_iso = (dt.datetime.now(dt.UTC) + dt.timedelta(days=14)).isoformat()
        exm_payload = {
            "policy_id": "POL-05",
            "entity_id": "server-001",
            "justification": "API test authorized temporary exemption",
            "expires_at": future_iso,
        }
        res_exm = client.post(
            "/api/v1/policies/exemptions",
            json=exm_payload,
            headers={"X-Tenant-ID": "tenant-api-test", "X-User-ID": "user-test"},
        )
        assert res_exm.status_code == 201
        assert res_exm.json()["is_approved"] is True

        # Trend endpoint
        start = dt.date(2026, 6, 1).isoformat()
        end = dt.date(2026, 6, 15).isoformat()
        res_trend = client.get(
            f"/api/v1/policies/trend?start_date={start}&end_date={end}",
            headers={"X-Tenant-ID": "tenant-api-test", "X-User-ID": "user-test"},
        )
        assert res_trend.status_code == 200
        trend_data = res_trend.json()
        assert "points" in trend_data
        assert "mttr_hours" in trend_data
