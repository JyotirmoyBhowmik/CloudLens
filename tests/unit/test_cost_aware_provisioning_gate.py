"""Unit and Integration Tests for Cost-Aware Provisioning Gate (Prompt 55 / API-051).

Enforces:
- Saved estimate object with 4 computed values, full derivation, pricing source, and validity window TTL.
- Estimate expiration enforcement (EstimateExpiredException).
- Multi-dimensional budget impact computation distinguishing visual materiality (3% vs 80%).
- Master-data gate triggers defaulting to NOTIFY_ONLY (opt-in control).
- Quota headroom pre-check (Prompt 54) flagging headroom < 20% or limit breach.
- Dependency & shared-service chain cost pre-check (Prompt 33) calculating complete application chain cost.
- AM-12 approval authority routing by master data role (never named individuals in code).
- Emergency bypass path with mandatory post-hoc rationale and governance exception.
- Three-period reconciliation loop, variance calculation, accuracy classification, and report generation.
- Unapproved-deployment detection with governance exception, remediation task, and prominent advisory notice.
- Scenario comparison view evaluating 2-4 architecture configurations side by side.
- Full REST API (API-051) endpoints via FastAPI TestClient.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from api.cloudlens_api.main import app
from domain.models.enums import ApprovalChainMode, ApproverResolutionType
from domain.models.exceptions import (
    EstimateExpiredException,
    EstimateNotFoundException,
    ProvisioningRequestInvalidStateException,
)
from domain.provisioning.authority import ApprovalAuthorityMaster
from domain.provisioning.budget_impact import BudgetImpactEngine
from domain.provisioning.models import (
    ADVISORY_GATE_NOTICE,
    ApprovalAuthorityRule,
    BudgetImpactTier,
    EstimateAccuracyClassification,
    GateTriggerAction,
    GateTriggerRule,
    ProvisioningRequestStatus,
    SavedEstimate,
)
from domain.provisioning.prechecks import DependencyPreCheckEngine, QuotaPreCheckEngine
from domain.provisioning.repository import (
    reset_provisioning_repository,
)
from domain.provisioning.service import (
    ProvisioningGateService,
    get_provisioning_gate_service,
    reset_provisioning_gate_service,
)
from domain.provisioning.triggers import GateTriggerEngine
from domain.tenant.context import TenantContext


@pytest.fixture(autouse=True)
def clean_environment():
    """Resets repository and service singletons before and after each test."""
    reset_provisioning_repository()
    reset_provisioning_gate_service()
    yield
    reset_provisioning_repository()
    reset_provisioning_gate_service()


@pytest.fixture
def tenant_ctx() -> TenantContext:
    return TenantContext(
        tenant_id="tenant-finops-123",
        user_id="user-engineer-1",
        email="engineer1@cloudlens.internal",
        roles=["CLOUD_ENGINEER"],
    )


@pytest.fixture
def service() -> ProvisioningGateService:
    return get_provisioning_gate_service()


# ==============================================================================
# 1. Saved Estimate Object Tests
# ==============================================================================


class TestSavedEstimate:
    def test_save_and_retrieve_estimate(
        self, service: ProvisioningGateService, tenant_ctx: TenantContext
    ):
        est = service.save_estimate(
            tenant_context=tenant_ctx,
            provider="aws",
            service="AmazonEC2",
            region="us-east-1",
            size="m5.large",
            hourly_cost=Decimal("0.096"),
            daily_cost=Decimal("2.304"),
            monthly_cost=Decimal("70.08"),
            annualised_cost=Decimal("840.96"),
            options={"os": "Linux", "storage_gb": 100},
            validity_days=7,
        )

        assert est.estimate_id.startswith("est-")
        assert est.tenant_id == "tenant-finops-123"
        assert est.requester_id == "user-engineer-1"
        assert est.hourly_cost == Decimal("0.10")
        assert est.monthly_cost == Decimal("70.08")
        assert est.annualised_cost == Decimal("840.96")
        assert not est.is_expired()

        retrieved = service.get_estimate(tenant_context=tenant_ctx, estimate_id=est.estimate_id)
        assert retrieved.estimate_id == est.estimate_id
        assert retrieved.service == "AmazonEC2"

    def test_estimate_expiration_detection(self):
        now = dt.datetime.now(dt.UTC)
        past = now - dt.timedelta(days=2)
        future = now + dt.timedelta(days=5)

        active = SavedEstimate(
            estimate_id="est-active",
            tenant_id="t1",
            requester_id="u1",
            requester_email="u1@test.com",
            provider="aws",
            service="EC2",
            region="us-east-1",
            size="t3.medium",
            hourly_cost=Decimal("0.0416"),
            daily_cost=Decimal("1.00"),
            monthly_cost=Decimal("30.37"),
            annualised_cost=Decimal("364.42"),
            valid_until=future.isoformat(),
        )
        assert not active.is_expired()

        expired = SavedEstimate(
            estimate_id="est-expired",
            tenant_id="t1",
            requester_id="u1",
            requester_email="u1@test.com",
            provider="aws",
            service="EC2",
            region="us-east-1",
            size="t3.medium",
            hourly_cost=Decimal("0.0416"),
            daily_cost=Decimal("1.00"),
            monthly_cost=Decimal("30.37"),
            annualised_cost=Decimal("364.42"),
            valid_until=past.isoformat(),
        )
        assert expired.is_expired()

    def test_submit_request_with_expired_estimate_fails(
        self, service: ProvisioningGateService, tenant_ctx: TenantContext
    ):
        est = service.save_estimate(
            tenant_context=tenant_ctx,
            provider="aws",
            service="EC2",
            region="us-east-1",
            size="t3.medium",
            hourly_cost=Decimal("0.05"),
            daily_cost=Decimal("1.20"),
            monthly_cost=Decimal("36.50"),
            annualised_cost=Decimal("438.00"),
            validity_days=-1,  # Expired yesterday
        )

        with pytest.raises(EstimateExpiredException) as exc:
            service.submit_provisioning_request(
                tenant_context=tenant_ctx,
                estimate_id=est.estimate_id,
                target_scope="BU-RETAIL",
                intended_application="Storefront",
                intended_environment="PROD",
                owner_id="u1",
                owner_email="u1@test.com",
                cost_centre="CC-ENG",
                business_justification="Scaling web tier for marketing campaign",
                intended_start_date="2026-10-15",
            )
        assert "expired" in str(exc.value).lower()

    def test_nonexistent_estimate_raises_not_found(
        self, service: ProvisioningGateService, tenant_ctx: TenantContext
    ):
        with pytest.raises(EstimateNotFoundException):
            service.get_estimate(tenant_context=tenant_ctx, estimate_id="est-nonexistent")


# ==============================================================================
# 2. Budget Impact Computation & Materiality Tiers Tests
# ==============================================================================


class TestBudgetImpactComputation:
    def test_distinguishes_negligible_vs_critical_materiality(self):
        engine = BudgetImpactEngine()
        period_budget = Decimal("100000.00")
        actual_spend = Decimal("50000.00")
        # Remaining budget = $50,000.00

        # Scenario A: Small deployment ($1,500/mo -> 3% of remaining $50,000)
        res_small = engine.evaluate_impact(
            period="2026-10",
            period_budget=period_budget,
            actual_spend=actual_spend,
            request_monthly_cost=Decimal("1500.00"),
            current_forecast=Decimal("80000.00"),
        )
        assert res_small.impact_tier == BudgetImpactTier.NEGLIGIBLE
        assert res_small.consumption_of_remaining_pct == Decimal("3.00")
        assert res_small.projected_utilisation_pct == Decimal("51.50")
        assert "NEGLIGIBLE" in res_small.commentary

        # Scenario B: Large deployment ($40,000/mo -> 80% of remaining $50,000)
        res_large = engine.evaluate_impact(
            period="2026-10",
            period_budget=period_budget,
            actual_spend=actual_spend,
            request_monthly_cost=Decimal("40000.00"),
            current_forecast=Decimal("80000.00"),
        )
        assert res_large.impact_tier == BudgetImpactTier.CRITICAL
        assert res_large.consumption_of_remaining_pct == Decimal("80.00")
        assert res_large.projected_utilisation_pct == Decimal("90.00")
        assert "CRITICAL" in res_large.commentary

    def test_moderate_and_substantial_tiers(self):
        engine = BudgetImpactEngine()
        period_budget = Decimal("10000.00")
        actual_spend = Decimal("2000.00")
        # Remaining budget = $8,000.00

        # $800 is 10% of $8,000 -> MODERATE (5% - 25%)
        mod = engine.evaluate_impact(
            period="2026-10",
            period_budget=period_budget,
            actual_spend=actual_spend,
            request_monthly_cost=Decimal("800.00"),
        )
        assert mod.impact_tier == BudgetImpactTier.MODERATE

        # $2,400 is 30% of $8,000 -> SUBSTANTIAL (25% - 50%)
        sub = engine.evaluate_impact(
            period="2026-10",
            period_budget=period_budget,
            actual_spend=actual_spend,
            request_monthly_cost=Decimal("2400.00"),
        )
        assert sub.impact_tier == BudgetImpactTier.SUBSTANTIAL

    def test_over_budget_condition_is_critical(self):
        engine = BudgetImpactEngine()
        res = engine.evaluate_impact(
            period="2026-10",
            period_budget=Decimal("10000.00"),
            actual_spend=Decimal("12000.00"),  # Already over budget
            request_monthly_cost=Decimal("500.00"),
        )
        assert res.remaining_budget == Decimal("-2000.00")
        assert res.impact_tier == BudgetImpactTier.CRITICAL


# ==============================================================================
# 3. Master Data Gate Triggers & Approval Routing Tests
# ==============================================================================


class TestGateTriggersAndRouting:
    def test_hard_rule_default_every_trigger_to_notify_only(self):
        engine = GateTriggerEngine([])  # No rules configured
        action, chain_id = engine.evaluate_trigger(
            scope_code="BU-ANALYTICS",
            environment="PROD",
            monthly_cost=Decimal("5000.00"),
        )
        # HARD RULE: Must default to NOTIFY_ONLY
        assert action == GateTriggerAction.NOTIFY_ONLY
        assert chain_id is None

    def test_opt_in_gate_triggers(self):
        engine = GateTriggerEngine(
            [
                # Dev environments are always NO_GATE
                GateTriggerRule(
                    rule_id="RULE-DEV",
                    scope_code="*",
                    environment="DEV",
                    min_monthly_amount=Decimal("0.00"),
                    action=GateTriggerAction.NO_GATE,
                ),
                # Production > $500 requires approval
                GateTriggerRule(
                    rule_id="RULE-PROD-HIGH",
                    scope_code="*",
                    environment="PROD",
                    min_monthly_amount=Decimal("500.00"),
                    action=GateTriggerAction.APPROVAL_REQUIRED,
                ),
                # Specific critical scope > $5,000 requires specific approval chain
                GateTriggerRule(
                    rule_id="RULE-PAYMENTS-CRITICAL",
                    scope_code="BU-PAYMENTS",
                    environment="PROD",
                    min_monthly_amount=Decimal("5000.00"),
                    action=GateTriggerAction.APPROVAL_REQUIRED_SPECIFIC_CHAIN,
                    approver_chain_id="CHAIN-FINOPS-EXEC",
                ),
            ]
        )

        act_dev, _ = engine.evaluate_trigger("BU-MARKETING", "DEV", Decimal("1000.00"))
        assert act_dev == GateTriggerAction.NO_GATE

        act_prod_low, _ = engine.evaluate_trigger("BU-MARKETING", "PROD", Decimal("200.00"))
        assert (
            act_prod_low == GateTriggerAction.NOTIFY_ONLY
        )  # Default fallback for unconfigured band

        act_prod_high, _ = engine.evaluate_trigger("BU-MARKETING", "PROD", Decimal("800.00"))
        assert act_prod_high == GateTriggerAction.APPROVAL_REQUIRED

        act_pay, chain = engine.evaluate_trigger("BU-PAYMENTS", "PROD", Decimal("6000.00"))
        assert act_pay == GateTriggerAction.APPROVAL_REQUIRED_SPECIFIC_CHAIN
        assert chain == "CHAIN-FINOPS-EXEC"

    def test_am12_approval_authority_resolves_roles_never_named_individuals(self):
        authority = ApprovalAuthorityMaster(
            [
                ApprovalAuthorityRule(
                    rule_id="AM12-TIER1",
                    scope_type="BUSINESS_UNIT",
                    scope_code="*",
                    min_monthly_amount=Decimal("0.00"),
                    max_monthly_amount=Decimal("1000.00"),
                    approver_role="TEAM_LEAD",
                    approver_resolution=ApproverResolutionType.ROLE,
                    sla_working_hours=12,
                ),
                ApprovalAuthorityRule(
                    rule_id="AM12-TIER2",
                    scope_type="BUSINESS_UNIT",
                    scope_code="*",
                    min_monthly_amount=Decimal("1000.01"),
                    max_monthly_amount=Decimal("10000.00"),
                    approver_role="BU_OWNER",
                    approver_resolution=ApproverResolutionType.BUSINESS_UNIT_OWNER,
                    sla_working_hours=24,
                ),
                ApprovalAuthorityRule(
                    rule_id="AM12-TIER3",
                    scope_type="BUSINESS_UNIT",
                    scope_code="*",
                    min_monthly_amount=Decimal("10000.01"),
                    max_monthly_amount=None,
                    approver_role="FINOPS_STEERING_COMMITTEE",
                    approver_resolution=ApproverResolutionType.ROLE,
                    chain_mode=ApprovalChainMode.PARALLEL,
                    sla_working_hours=48,
                ),
            ]
        )

        res_low = authority.resolve_authority("BUSINESS_UNIT", "BU-ENG", Decimal("500.00"))
        assert res_low.approver_role == "TEAM_LEAD"

        res_mid = authority.resolve_authority("BUSINESS_UNIT", "BU-ENG", Decimal("2500.00"))
        assert res_mid.approver_role == "BU_OWNER"
        assert res_mid.approver_resolution == ApproverResolutionType.BUSINESS_UNIT_OWNER

        res_high = authority.resolve_authority("BUSINESS_UNIT", "BU-ENG", Decimal("25000.00"))
        assert res_high.approver_role == "FINOPS_STEERING_COMMITTEE"
        assert res_high.chain_mode == ApprovalChainMode.PARALLEL


# ==============================================================================
# 4. Pre-Checks: Quota Headroom & Dependency Chain Cost Tests
# ==============================================================================


class TestPreChecks:
    def test_quota_pre_check_headroom_and_breach(self):
        engine = QuotaPreCheckEngine()

        # Healthy headroom: 20 consumed of 100 limit, adding 5 -> 75% headroom
        res_ok = engine.evaluate_quota(
            provider="aws",
            service="ec2",
            region="us-east-1",
            requested_units=Decimal("5.0"),
            current_consumed=Decimal("20.0"),
            limit_units=Decimal("100.0"),
        )
        assert not res_ok.is_blocked
        assert not res_ok.headroom_warning
        assert res_ok.projected_headroom_pct == Decimal("75.00")

        # Headroom warning: 80 consumed of 100 limit, adding 5 -> 15% headroom (< 20%)
        res_warn = engine.evaluate_quota(
            provider="aws",
            service="ec2",
            region="us-east-1",
            requested_units=Decimal("5.0"),
            current_consumed=Decimal("80.0"),
            limit_units=Decimal("100.0"),
        )
        assert not res_warn.is_blocked
        assert res_warn.headroom_warning
        assert res_warn.projected_headroom_pct == Decimal("15.00")
        assert "WARNING" in res_warn.message

        # Hard limit breach: 95 consumed of 100 limit, adding 10 -> 105 units (> 100)
        res_blocked = engine.evaluate_quota(
            provider="aws",
            service="ec2",
            region="us-east-1",
            requested_units=Decimal("10.0"),
            current_consumed=Decimal("95.0"),
            limit_units=Decimal("100.0"),
        )
        assert res_blocked.is_blocked
        assert res_blocked.headroom_warning
        assert "BREACH" in res_blocked.message

    def test_dependency_chain_cost_and_multiplier(self):
        engine = DependencyPreCheckEngine()
        primary_cost = Decimal("120.00")

        res = engine.evaluate_dependencies(
            provider="aws",
            service="AmazonEC2",
            primary_monthly_cost=primary_cost,
            options={"storage_gb": 200, "include_load_balancer": True, "include_nat_gateway": True},
        )

        assert res.primary_monthly_cost == Decimal("120.00")
        assert len(res.inferred_dependencies) >= 3
        # Check ALB, NAT Gateway, Backup, Storage
        dep_names = [d.service_name for d in res.inferred_dependencies]
        assert any("Load Balancer" in n for n in dep_names)
        assert any("NAT Gateway" in n for n in dep_names)
        assert any("Block Storage" in n for n in dep_names)

        assert res.shared_service_apportionment > Decimal("0.00")
        assert res.total_chain_monthly_cost > primary_cost
        assert res.chain_multiplier > Decimal("1.00")


# ==============================================================================
# 5. Provisioning Request Lifecycle & Workflow Routing Tests
# ==============================================================================


class TestProvisioningRequestLifecycle:
    def test_request_submission_with_default_notify_only_auto_approves(
        self, service: ProvisioningGateService, tenant_ctx: TenantContext
    ):
        est = service.save_estimate(
            tenant_context=tenant_ctx,
            provider="aws",
            service="AmazonEC2",
            region="us-east-1",
            size="t3.large",
            hourly_cost=Decimal("0.08"),
            daily_cost=Decimal("1.92"),
            monthly_cost=Decimal("58.40"),
            annualised_cost=Decimal("700.80"),
        )

        req = service.submit_provisioning_request(
            tenant_context=tenant_ctx,
            estimate_id=est.estimate_id,
            target_scope="BU-MARKETING",
            intended_application="CampaignApp",
            intended_environment="DEV",
            owner_id="u1",
            owner_email="u1@test.com",
            cost_centre="CC-MKT",
            business_justification="Ad-hoc campaign test server",
            intended_start_date="2026-10-10",
        )

        # Defaults to NOTIFY_ONLY -> Auto-approved advisory status
        assert req.status == ProvisioningRequestStatus.APPROVED
        assert req.gate_action == GateTriggerAction.NOTIFY_ONLY
        assert req.advisory_notice == ADVISORY_GATE_NOTICE

    def test_request_submission_with_approval_gate_routes_to_workflow_engine(
        self, service: ProvisioningGateService, tenant_ctx: TenantContext
    ):
        # Configure rule requiring approval for PROD > $500
        service.configure_gate_trigger(
            tenant_context=tenant_ctx,
            rule=GateTriggerRule(
                rule_id="RULE-PROD",
                scope_code="*",
                environment="PROD",
                min_monthly_amount=Decimal("500.00"),
                action=GateTriggerAction.APPROVAL_REQUIRED,
            ),
        )

        est = service.save_estimate(
            tenant_context=tenant_ctx,
            provider="aws",
            service="AmazonEC2",
            region="us-east-1",
            size="r5.2xlarge",
            hourly_cost=Decimal("1.00"),
            daily_cost=Decimal("24.00"),
            monthly_cost=Decimal("730.00"),
            annualised_cost=Decimal("8760.00"),
        )

        req = service.submit_provisioning_request(
            tenant_context=tenant_ctx,
            estimate_id=est.estimate_id,
            target_scope="BU-CORE",
            intended_application="PaymentProcessor",
            intended_environment="PROD",
            owner_id="u1",
            owner_email="u1@test.com",
            cost_centre="CC-ENG",
            business_justification="High memory worker instance for payments queue",
            intended_start_date="2026-10-10",
        )

        assert req.gate_action == GateTriggerAction.APPROVAL_REQUIRED
        assert req.status in {
            ProvisioningRequestStatus.IN_REVIEW,
            ProvisioningRequestStatus.SUBMITTED,
        }
        assert req.workflow_request_id is not None


# ==============================================================================
# 6. Emergency Bypass Path Tests
# ==============================================================================


class TestEmergencyBypass:
    def test_urgent_deployment_bypass(
        self, service: ProvisioningGateService, tenant_ctx: TenantContext
    ):
        service.configure_gate_trigger(
            tenant_context=tenant_ctx,
            rule=GateTriggerRule(
                rule_id="RULE-PROD-CRIT",
                scope_code="*",
                environment="PROD",
                min_monthly_amount=Decimal("100.00"),
                action=GateTriggerAction.APPROVAL_REQUIRED,
            ),
        )
        est = service.save_estimate(
            tenant_context=tenant_ctx,
            provider="aws",
            service="AmazonEC2",
            region="us-east-1",
            size="c5.xlarge",
            hourly_cost=Decimal("0.34"),
            daily_cost=Decimal("8.16"),
            monthly_cost=Decimal("248.20"),
            annualised_cost=Decimal("2978.40"),
        )
        req = service.submit_provisioning_request(
            tenant_context=tenant_ctx,
            estimate_id=est.estimate_id,
            target_scope="BU-CORE",
            intended_application="IncidentMitigation",
            intended_environment="PROD",
            owner_id="u1",
            owner_email="u1@test.com",
            cost_centre="CC-ENG",
            business_justification="Production outage hotfix scaling",
            intended_start_date="2026-10-04",
        )
        assert req.status in {
            ProvisioningRequestStatus.IN_REVIEW,
            ProvisioningRequestStatus.SUBMITTED,
        }

        # Execute emergency bypass
        bypassed = service.bypass_provisioning_request(
            tenant_context=tenant_ctx,
            request_id=req.request_id,
            bypassed_by="incident-commander-1",
            justification="SEV1 Outage mitigation in progress: immediate capacity needed per Runbook INC-882",
        )

        assert bypassed.status == ProvisioningRequestStatus.BYPASSED
        assert bypassed.bypass_details is not None
        assert bypassed.bypass_details.bypassed_by == "incident-commander-1"
        assert bypassed.bypass_details.governance_exception_id.startswith("govex-")

    def test_bypass_on_already_finalized_request_fails(
        self, service: ProvisioningGateService, tenant_ctx: TenantContext
    ):
        est = service.save_estimate(
            tenant_context=tenant_ctx,
            provider="aws",
            service="EC2",
            region="us-east-1",
            size="t3.nano",
            hourly_cost=Decimal("0.01"),
            daily_cost=Decimal("0.24"),
            monthly_cost=Decimal("7.30"),
            annualised_cost=Decimal("87.60"),
        )
        req = service.submit_provisioning_request(
            tenant_context=tenant_ctx,
            estimate_id=est.estimate_id,
            target_scope="BU-TEST",
            intended_application="TestApp",
            intended_environment="DEV",
            owner_id="u1",
            owner_email="u1@test.com",
            cost_centre="CC-TEST",
            business_justification="Routine test setup",
            intended_start_date="2026-10-05",
        )
        # In DEV, auto-approves
        assert req.status == ProvisioningRequestStatus.APPROVED

        with pytest.raises(ProvisioningRequestInvalidStateException):
            service.bypass_provisioning_request(
                tenant_context=tenant_ctx,
                request_id=req.request_id,
                bypassed_by="u1",
                justification="Testing bypass failure on approved request",
            )


# ==============================================================================
# 7. Reconciliation Loop (First 3 Billing Periods) & Accuracy Report Tests
# ==============================================================================


class TestReconciliationLoop:
    def test_three_period_tracking_and_classification(
        self, service: ProvisioningGateService, tenant_ctx: TenantContext
    ):
        est = service.save_estimate(
            tenant_context=tenant_ctx,
            provider="aws",
            service="AmazonEC2",
            region="us-east-1",
            size="m5.xlarge",
            hourly_cost=Decimal("0.192"),
            daily_cost=Decimal("4.608"),
            monthly_cost=Decimal("140.16"),
            annualised_cost=Decimal("1681.92"),
        )
        req = service.submit_provisioning_request(
            tenant_context=tenant_ctx,
            estimate_id=est.estimate_id,
            target_scope="BU-RETAIL",
            intended_application="Storefront",
            intended_environment="DEV",
            owner_id="u1",
            owner_email="u1@test.com",
            cost_centre="CC-ENG",
            business_justification="Capacity for catalog service",
            intended_start_date="2026-10-01",
        )

        # 1. Link newly inventoried resource
        linked_req, tracking = service.link_resource_to_request(
            tenant_context=tenant_ctx,
            request_id=req.request_id,
            resource_id="i-0123456789abcdef0",
            approver_role="FINOPS_ADMIN",
        )
        assert linked_req.status == ProvisioningRequestStatus.LINKED_TO_RESOURCE
        assert tracking.resource_id == "i-0123456789abcdef0"
        assert tracking.approved_monthly_estimate == Decimal("140.16")
        assert not tracking.is_three_periods_complete

        # 2. Record Period 1 Actual: $142.00 (within +/- 10%)
        t1 = service.record_period_actual(
            tenant_context=tenant_ctx,
            request_id=req.request_id,
            period="2026-10",
            billed_amount=Decimal("142.00"),
        )
        assert t1.classification == EstimateAccuracyClassification.WITHIN_ACCURACY_BAND
        assert not t1.is_three_periods_complete

        # 3. Record Period 2 Actual: $175.00 (> +10% -> UNDER_ESTIMATED)
        t2 = service.record_period_actual(
            tenant_context=tenant_ctx,
            request_id=req.request_id,
            period="2026-11",
            billed_amount=Decimal("175.00"),
        )
        assert t2.classification == EstimateAccuracyClassification.UNDER_ESTIMATED
        assert not t2.is_three_periods_complete

        # 4. Record Period 3 Actual: $138.00 (within band)
        t3 = service.record_period_actual(
            tenant_context=tenant_ctx,
            request_id=req.request_id,
            period="2026-12",
            billed_amount=Decimal("138.00"),
        )
        assert t3.is_three_periods_complete
        assert len(t3.periods_tracked) == 3

        # 5. Generate Accuracy Report
        report = service.generate_accuracy_report(tenant_context=tenant_ctx)
        assert report.total_tracked == 1
        assert report.three_period_completed_count == 1
        assert len(report.by_service) == 1
        assert report.by_service[0]["key"] == "AmazonEC2"


# ==============================================================================
# 8. Unapproved-Deployment Detection Tests
# ==============================================================================


class TestUnapprovedDeploymentDetection:
    def test_detects_unapproved_resources_with_advisory_notice(
        self, service: ProvisioningGateService, tenant_ctx: TenantContext
    ):
        inventoried = [
            {
                "resource_id": "i-legit-approved-1",
                "name": "approved-instance",
                "scope_code": "BU-GATED",
                "monthly_cost": "200.00",
                "provider": "aws",
                "service": "AmazonEC2",
            },
            {
                "resource_id": "i-rogue-unapproved-2",
                "name": "unapproved-instance",
                "scope_code": "BU-GATED",
                "monthly_cost": "350.00",
                "provider": "aws",
                "service": "AmazonEC2",
            },
            {
                "resource_id": "i-open-scope-3",
                "name": "ungated-instance",
                "scope_code": "BU-SANDBOX",
                "monthly_cost": "50.00",
                "provider": "aws",
                "service": "AmazonEC2",
            },
        ]

        # First instance has an approved request linked
        est = service.save_estimate(
            tenant_context=tenant_ctx,
            provider="aws",
            service="AmazonEC2",
            region="us-east-1",
            size="m5.large",
            hourly_cost=Decimal("0.10"),
            daily_cost=Decimal("2.40"),
            monthly_cost=Decimal("73.00"),
            annualised_cost=Decimal("876.00"),
        )
        req = service.submit_provisioning_request(
            tenant_context=tenant_ctx,
            estimate_id=est.estimate_id,
            target_scope="BU-GATED",
            intended_application="Storefront",
            intended_environment="DEV",
            owner_id="u1",
            owner_email="u1@test.com",
            cost_centre="CC-ENG",
            business_justification="Legitimate test instance",
            intended_start_date="2026-10-01",
        )
        service.link_resource_to_request(
            tenant_context=tenant_ctx,
            request_id=req.request_id,
            resource_id="i-legit-approved-1",
        )

        findings = service.detect_unapproved_deployments(
            tenant_context=tenant_ctx,
            inventoried_resources=inventoried,
            gated_scopes={"BU-GATED"},
        )

        assert len(findings) == 1
        finding = findings[0]
        assert finding.resource_id == "i-rogue-unapproved-2"
        assert finding.scope_code == "BU-GATED"
        assert finding.estimated_monthly_cost == Decimal("350.00")
        assert finding.governance_exception_id.startswith("govex-")
        assert finding.remediation_task_id.startswith("rem-")
        assert finding.advisory_disclaimer == ADVISORY_GATE_NOTICE


# ==============================================================================
# 9. Scenario Comparison View Tests
# ==============================================================================


class TestScenarioComparison:
    def test_compares_multiple_architecture_configurations(
        self, service: ProvisioningGateService, tenant_ctx: TenantContext
    ):
        base_est = service.save_estimate(
            tenant_context=tenant_ctx,
            provider="aws",
            service="AmazonEC2",
            region="us-east-1",
            size="m5.large",
            hourly_cost=Decimal("0.096"),
            daily_cost=Decimal("2.304"),
            monthly_cost=Decimal("70.08"),
            annualised_cost=Decimal("840.96"),
        )
        alt1_est = service.save_estimate(
            tenant_context=tenant_ctx,
            provider="aws",
            service="AmazonEC2",
            region="us-east-1",
            size="m5.xlarge",
            hourly_cost=Decimal("0.192"),
            daily_cost=Decimal("4.608"),
            monthly_cost=Decimal("140.16"),
            annualised_cost=Decimal("1681.92"),
        )
        alt2_est = service.save_estimate(
            tenant_context=tenant_ctx,
            provider="aws",
            service="AmazonEC2",
            region="us-east-1",
            size="t3.large",
            hourly_cost=Decimal("0.0832"),
            daily_cost=Decimal("1.9968"),
            monthly_cost=Decimal("60.74"),
            annualised_cost=Decimal("728.88"),
        )

        comparison = service.compare_scenarios(
            tenant_context=tenant_ctx,
            target_scope="BU-RETAIL",
            period="2026-10",
            baseline_estimate=base_est,
            alternative_estimates=[alt1_est, alt2_est],
            period_budget=Decimal("50000.00"),
            actual_spend=Decimal("20000.00"),
        )

        assert comparison.baseline_scenario_id == "BASELINE"
        assert len(comparison.scenarios) == 3
        assert comparison.scenarios[0].monthly_cost == Decimal("70.08")
        assert comparison.scenarios[1].monthly_cost == Decimal("140.16")
        assert comparison.scenarios[1].delta_from_baseline_monthly > Decimal("0.00")
        assert comparison.scenarios[2].monthly_cost == Decimal("60.74")
        assert comparison.scenarios[2].delta_from_baseline_monthly < Decimal("0.00")


# ==============================================================================
# 10. Public REST API (API-051) End-to-End Tests
# ==============================================================================


class TestProvisioningRESTAPI:
    def test_full_api_workflow_via_testclient(self):
        client = TestClient(app)
        headers = {
            "X-Tenant-ID": "tenant-corp-1",
            "X-User-ID": "admin-1",
            "X-User-Roles": "FINOPS_ADMIN",
        }

        # 1. Create Saved Estimate
        res_est = client.post(
            "/api/v1/provisioning-requests/estimates",
            headers=headers,
            json={
                "provider": "aws",
                "service": "AmazonEC2",
                "region": "us-east-1",
                "size": "c5.large",
                "hourly_cost": "0.085",
                "daily_cost": "2.04",
                "monthly_cost": "62.05",
                "annualised_cost": "744.60",
                "options": {"storage_gb": 100},
                "validity_days": 14,
            },
        )
        assert res_est.status_code == 201
        est_data = res_est.json()
        est_id = est_data["estimate_id"]

        # 2. Get Saved Estimate
        res_get_est = client.get(
            f"/api/v1/provisioning-requests/estimates/{est_id}", headers=headers
        )
        assert res_get_est.status_code == 200
        assert res_get_est.json()["service"] == "AmazonEC2"

        # 3. Submit Provisioning Request
        res_req = client.post(
            "/api/v1/provisioning-requests",
            headers=headers,
            json={
                "estimate_id": est_id,
                "target_scope": "BU-ENG",
                "intended_application": "CI-Worker",
                "intended_environment": "DEV",
                "owner_id": "eng-lead-1",
                "owner_email": "eng1@corp.internal",
                "cost_centre": "CC-ENG",
                "business_justification": "Dedicated CI pipeline runner",
                "intended_start_date": "2026-10-15",
            },
        )
        assert res_req.status_code == 201
        req_data = res_req.json()
        req_id = req_data["request_id"]
        assert req_data["status"] == "APPROVED"
        assert req_data["advisory_notice"] == ADVISORY_GATE_NOTICE

        # 4. List Provisioning Requests
        res_list = client.get("/api/v1/provisioning-requests", headers=headers)
        assert res_list.status_code == 200
        assert any(r["request_id"] == req_id for r in res_list.json())

        # 5. Link Resource
        res_link = client.post(
            f"/api/v1/provisioning-requests/{req_id}/link-resource",
            headers=headers,
            json={"resource_id": "i-0987654321fedcba0", "approver_role": "FINOPS_ADMIN"},
        )
        assert res_link.status_code == 200
        assert res_link.json()["status"] == "LINKED_TO_RESOURCE"

        # 6. Record Period Actual
        res_actual = client.post(
            f"/api/v1/provisioning-requests/{req_id}/actuals",
            headers=headers,
            json={"period": "2026-10", "billed_amount": "61.50"},
        )
        assert res_actual.status_code == 200
        assert res_actual.json()["classification"] == "WITHIN_ACCURACY_BAND"

        # 7. Get Accuracy Report
        res_report = client.get("/api/v1/provisioning-requests/accuracy/report", headers=headers)
        assert res_report.status_code == 200
        assert res_report.json()["total_tracked"] == 1

        # 8. Unapproved Deployment Detection
        res_unapproved = client.post(
            "/api/v1/provisioning-requests/unapproved/detect",
            headers=headers,
            json={
                "inventoried_resources": [
                    {
                        "resource_id": "i-untracked-999",
                        "resource_name": "shadow-it-instance",
                        "provider": "aws",
                        "service": "AmazonEC2",
                        "scope_code": "BU-FINANCE",
                        "monthly_cost": "450.00",
                    }
                ],
                "gated_scopes": ["BU-FINANCE"],
            },
        )
        assert res_unapproved.status_code == 200
        findings = res_unapproved.json()
        assert len(findings) == 1
        assert findings[0]["resource_id"] == "i-untracked-999"
        assert findings[0]["advisory_disclaimer"] == ADVISORY_GATE_NOTICE
