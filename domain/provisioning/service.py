"""Provisioning Gate Service Facade (Prompt 55).

Enforces:
- Master brief Section 6 (pre-deployment estimation); Control Principle Section 2; Addendum A Prompt 50.
- Saved estimate object with 4 computed values, full derivation, pricing source, and validity window.
- Provisioning request as a Prompt 50 workflow request type (never a separate approval mechanism).
- Multi-dimensional budget impact computation (remaining budget, consumption %, projected utilisation, forecast effect).
- Master-data gate triggers per scope, environment, and value band, defaulting to NOTIFY_ONLY (opt-in control).
- Quota headroom pre-checks (Prompt 54) and dependency/shared-service chain cost pre-checks (Prompt 33).
- Approval authority routing via AM-12 master data (never named individuals in code).
- Reconciliation loop comparing actuals to approved estimates over the first 3 billing periods with accuracy reporting.
- Unapproved-deployment detection with governance exception, assigned remediation task, and prominent advisory notice.
- Recorded emergency bypass path with post-hoc justification.
- Scenario comparison view evaluating alternative configurations side by side.
"""

from __future__ import annotations

import datetime as dt
import logging
import uuid
from decimal import Decimal
from typing import Any

from domain.audit.models import AuditEventCreate
from domain.audit.service import AuditService, get_audit_service
from domain.models.enums import AuditEventType, WorkflowRequestType
from domain.models.exceptions import (
    EstimateExpiredException,
    EstimateNotFoundException,
    ProvisioningRequestInvalidStateException,
    ProvisioningRequestNotFoundException,
)
from domain.provisioning.authority import ApprovalAuthorityMaster
from domain.provisioning.budget_impact import BudgetImpactEngine
from domain.provisioning.models import (
    ADVISORY_GATE_NOTICE,
    AccuracyReport,
    ApprovalAuthorityRule,
    BypassRecord,
    EstimateVsActualTracking,
    GateTriggerAction,
    GateTriggerRule,
    ProvisioningRequest,
    ProvisioningRequestStatus,
    SavedEstimate,
    ScenarioComparisonView,
    ScenarioOption,
    UnapprovedDeploymentFinding,
)
from domain.provisioning.prechecks import DependencyPreCheckEngine, QuotaPreCheckEngine
from domain.provisioning.reconciliation import ProvisioningReconciliationEngine
from domain.provisioning.repository import (
    ProvisioningRepository,
    get_provisioning_repository,
)
from domain.provisioning.triggers import GateTriggerEngine
from domain.provisioning.unapproved import UnapprovedDeploymentDetector
from domain.rules.monetary import round_currency
from domain.tenant.context import TenantContext, require_tenant_context
from domain.workflows.models import SubjectEntity, WorkflowSubmitRequest
from domain.workflows.service import WorkflowService

logger = logging.getLogger(__name__)


class ProvisioningGateService:
    """Unified service orchestrating cost-aware pre-deployment provisioning gates."""

    def __init__(
        self,
        repository: ProvisioningRepository | None = None,
        trigger_engine: GateTriggerEngine | None = None,
        authority_master: ApprovalAuthorityMaster | None = None,
        budget_impact_engine: BudgetImpactEngine | None = None,
        quota_engine: QuotaPreCheckEngine | None = None,
        dependency_engine: DependencyPreCheckEngine | None = None,
        reconciliation_engine: ProvisioningReconciliationEngine | None = None,
        unapproved_detector: UnapprovedDeploymentDetector | None = None,
        workflow_service: WorkflowService | None = None,
        audit_service: AuditService | None = None,
    ) -> None:
        self.repository = repository or get_provisioning_repository()
        self.trigger_engine = trigger_engine or GateTriggerEngine()
        self.authority_master = authority_master or ApprovalAuthorityMaster()
        self.budget_impact_engine = budget_impact_engine or BudgetImpactEngine()
        self.quota_engine = quota_engine or QuotaPreCheckEngine()
        self.dependency_engine = dependency_engine or DependencyPreCheckEngine()
        self.reconciliation_engine = reconciliation_engine or ProvisioningReconciliationEngine()
        self.unapproved_detector = unapproved_detector or UnapprovedDeploymentDetector()
        self._workflow_service = workflow_service
        self.audit_service = audit_service or get_audit_service()

    @property
    def workflow_service(self) -> WorkflowService:
        if self._workflow_service is None:
            from domain.workflows.service import WorkflowService as WS

            self._workflow_service = WS()
        return self._workflow_service

    # ==========================================================================
    # 1. Saved Estimates
    # ==========================================================================

    def save_estimate(
        self,
        *,
        tenant_context: TenantContext,
        estimate_id: str | None = None,
        provider: str,
        service: str,
        region: str,
        size: str,
        hourly_cost: Decimal,
        daily_cost: Decimal,
        monthly_cost: Decimal,
        annualised_cost: Decimal,
        options: dict[str, Any] | None = None,
        currency: str = "USD",
        derivation: dict[str, Any] | None = None,
        pricing_source: str = "cloudlens_catalog",
        pricing_effective_date: str | None = None,
        validity_days: int = 7,
    ) -> SavedEstimate:
        """Saves a priced pre-deployment configuration with TTL validity window."""
        tc = require_tenant_context(tenant_context)
        now = dt.datetime.now(dt.UTC)
        valid_until_dt = now + dt.timedelta(days=validity_days)

        e_id = estimate_id or f"est-{uuid.uuid4().hex[:8]}"

        estimate = SavedEstimate(
            estimate_id=e_id,
            tenant_id=tc.tenant_id,
            requester_id=tc.user_id,
            requester_email=tc.email or f"{tc.user_id}@cloudlens.internal",
            provider=provider.lower(),
            service=service,
            region=region,
            size=size,
            options=options or {},
            hourly_cost=round_currency(hourly_cost),
            daily_cost=round_currency(daily_cost),
            monthly_cost=round_currency(monthly_cost),
            annualised_cost=round_currency(annualised_cost),
            currency=currency,
            derivation=derivation or {"formula": "hourly * hours_per_period"},
            pricing_source=pricing_source,
            pricing_effective_date=pricing_effective_date or dt.date.today().isoformat(),
            valid_until=valid_until_dt.isoformat(),
            created_at=now.isoformat(),
        )

        saved = self.repository.save_estimate(estimate)

        self._record_audit(
            tc,
            AuditEventType.PROVISIONING_ESTIMATE_SAVED,
            "SavedEstimate",
            saved.estimate_id,
            {
                "provider": saved.provider,
                "service": saved.service,
                "monthly_cost": str(saved.monthly_cost),
                "valid_until": saved.valid_until,
            },
        )
        return saved

    def get_estimate(self, *, tenant_context: TenantContext, estimate_id: str) -> SavedEstimate:
        """Retrieves a saved estimate, raising EstimateNotFoundException if missing."""
        tc = require_tenant_context(tenant_context)
        est = self.repository.get_estimate(tc.tenant_id, estimate_id)
        if not est:
            raise EstimateNotFoundException(f"Saved estimate '{estimate_id}' not found.")
        return est

    # ==========================================================================
    # 2. Gate Trigger & AM-12 Configuration
    # ==========================================================================

    def configure_gate_trigger(
        self,
        *,
        tenant_context: TenantContext,
        rule: GateTriggerRule,
    ) -> GateTriggerRule:
        """Registers a master-data gate trigger rule for the tenant."""
        tc = require_tenant_context(tenant_context)
        saved = self.repository.save_gate_rule(tc.tenant_id, rule)
        self.trigger_engine.register_rule(saved)
        return saved

    def configure_authority_rule(
        self,
        *,
        tenant_context: TenantContext,
        rule: ApprovalAuthorityRule,
    ) -> ApprovalAuthorityRule:
        """Registers an AM-12 approval authority rule for the tenant."""
        tc = require_tenant_context(tenant_context)
        saved = self.repository.save_authority_rule(tc.tenant_id, rule)
        self.authority_master.register_rule(saved)
        return saved

    # ==========================================================================
    # 3. Provisioning Request Creation & Routing
    # ==========================================================================

    def submit_provisioning_request(
        self,
        *,
        tenant_context: TenantContext,
        estimate_id: str,
        target_scope: str,
        scope_type: str = "BUSINESS_UNIT",
        intended_application: str,
        intended_environment: str,
        owner_id: str,
        owner_email: str,
        cost_centre: str,
        business_justification: str,
        intended_start_date: str,
        period: str | None = None,
        period_budget: Decimal | None = None,
        actual_spend: Decimal | None = None,
        current_forecast: Decimal | None = None,
    ) -> ProvisioningRequest:
        """Submits a provisioning request evaluated against pre-checks, budget impact, and master gate triggers."""
        tc = require_tenant_context(tenant_context)
        estimate = self.get_estimate(tenant_context=tc, estimate_id=estimate_id)

        # Enforce estimate validity window
        if estimate.is_expired():
            raise EstimateExpiredException(
                estimate_id=estimate_id,
                valid_until=estimate.valid_until,
            )

        now = dt.datetime.now(dt.UTC)
        p_str = period or now.strftime("%Y-%m")
        budget_val = period_budget if period_budget is not None else Decimal("50000.00")
        actual_val = actual_spend if actual_spend is not None else Decimal("30000.00")

        # 1. Budget Impact Computation
        budget_impact = self.budget_impact_engine.evaluate_impact(
            period=p_str,
            period_budget=budget_val,
            actual_spend=actual_val,
            request_monthly_cost=estimate.monthly_cost,
            current_forecast=current_forecast,
        )

        # 2. Quota Headroom Pre-Check (Prompt 54)
        quota_pre_check = self.quota_engine.evaluate_quota(
            provider=estimate.provider,
            service=estimate.service,
            region=estimate.region,
        )

        # 3. Dependency & Shared-Service Pre-Check (Prompt 33)
        dependency_pre_check = self.dependency_engine.evaluate_dependencies(
            provider=estimate.provider,
            service=estimate.service,
            primary_monthly_cost=estimate.monthly_cost,
            options=estimate.options,
        )

        # 4. Gate Trigger Evaluation (Master Data driven, defaults to NOTIFY_ONLY)
        gate_action, specific_chain_id = self.trigger_engine.evaluate_trigger(
            scope_code=target_scope,
            environment=intended_environment,
            monthly_cost=estimate.monthly_cost,
        )

        req_id = f"prv-{uuid.uuid4().hex[:8]}"
        wf_req_id: str | None = None

        # 5. Routing through Prompt 50 Workflow Engine if approval is required
        if gate_action in {
            GateTriggerAction.APPROVAL_REQUIRED,
            GateTriggerAction.APPROVAL_REQUIRED_SPECIFIC_CHAIN,
        }:
            authority = self.authority_master.resolve_authority(
                scope_type=scope_type,
                scope_code=target_scope,
                monthly_amount=estimate.monthly_cost,
            )

            wf_submit = WorkflowSubmitRequest(
                request_type=WorkflowRequestType.PROVISIONING_REQUEST.value,
                title=f"Provisioning Approval: {estimate.service} in {target_scope} (${estimate.monthly_cost:,.2f}/mo)",
                subject_entity=SubjectEntity(
                    entity_type="provisioning_request",
                    entity_id=req_id,
                    scope_type=scope_type,
                    scope_id=target_scope,
                    metadata={
                        "owner_id": owner_id,
                        "monthly_cost": float(estimate.monthly_cost),
                        "environment": intended_environment,
                        "approver_role": authority.approver_role,
                    },
                ),
                justification=business_justification,
                payload={
                    "request_id": req_id,
                    "estimate_id": estimate_id,
                    "provider": estimate.provider,
                    "service": estimate.service,
                    "monthly_cost": float(estimate.monthly_cost),
                    "target_scope": target_scope,
                    "environment": intended_environment,
                    "budget_impact_tier": budget_impact.impact_tier.value,
                    "chain_monthly_cost": float(dependency_pre_check.total_chain_monthly_cost),
                    "quota_warning": quota_pre_check.headroom_warning,
                },
                financial_impact=float(estimate.monthly_cost),
            )

            try:
                wf_res = self.workflow_service.submit_request(wf_submit, tenant_context=tc)
                wf_req_id = wf_res.id
                status = ProvisioningRequestStatus.IN_REVIEW
            except Exception as e:
                logger.error("Failed to submit provisioning workflow request: %s", e)
                status = ProvisioningRequestStatus.SUBMITTED
        else:
            # NO_GATE or NOTIFY_ONLY: Auto-approved at advisory gate
            status = ProvisioningRequestStatus.APPROVED

        prov_req = ProvisioningRequest(
            request_id=req_id,
            tenant_id=tc.tenant_id,
            estimate_id=estimate_id,
            estimate=estimate,
            target_scope=target_scope,
            scope_type=scope_type,
            intended_application=intended_application,
            intended_environment=intended_environment,
            owner_id=owner_id,
            owner_email=owner_email,
            cost_centre=cost_centre,
            business_justification=business_justification,
            intended_start_date=intended_start_date,
            budget_impact=budget_impact,
            quota_pre_check=quota_pre_check,
            dependency_pre_check=dependency_pre_check,
            gate_action=gate_action,
            status=status,
            workflow_request_id=wf_req_id,
            created_at=now.isoformat(),
            advisory_notice=ADVISORY_GATE_NOTICE,
        )

        saved_req = self.repository.save_request(prov_req)

        self._record_audit(
            tc,
            AuditEventType.PROVISIONING_REQUEST_CREATED,
            "ProvisioningRequest",
            saved_req.request_id,
            {
                "target_scope": saved_req.target_scope,
                "environment": saved_req.intended_environment,
                "monthly_cost": str(saved_req.estimate.monthly_cost),
                "gate_action": saved_req.gate_action.value,
                "status": saved_req.status.value,
            },
        )

        self._record_audit(
            tc,
            AuditEventType.PROVISIONING_GATE_TRIGGERED,
            "ProvisioningRequest",
            saved_req.request_id,
            {
                "gate_action": saved_req.gate_action.value,
                "impact_tier": saved_req.budget_impact.impact_tier.value,
                "quota_warning": saved_req.quota_pre_check.headroom_warning,
            },
        )

        return saved_req

    def get_provisioning_request(
        self,
        *,
        tenant_context: TenantContext,
        request_id: str,
    ) -> ProvisioningRequest:
        """Retrieves a provisioning request by ID."""
        tc = require_tenant_context(tenant_context)
        req = self.repository.get_request(tc.tenant_id, request_id)
        if not req:
            raise ProvisioningRequestNotFoundException(
                f"Provisioning request '{request_id}' not found."
            )
        return req

    def list_provisioning_requests(
        self,
        *,
        tenant_context: TenantContext,
        status: str | None = None,
        scope_code: str | None = None,
    ) -> list[ProvisioningRequest]:
        """Lists provisioning requests with optional filtering."""
        tc = require_tenant_context(tenant_context)
        return self.repository.list_requests(tc.tenant_id, status=status, scope_code=scope_code)

    # ==========================================================================
    # 4. Emergency Bypass Path
    # ==========================================================================

    def bypass_provisioning_request(
        self,
        *,
        tenant_context: TenantContext,
        request_id: str,
        bypassed_by: str,
        justification: str,
    ) -> ProvisioningRequest:
        """Executes emergency bypass for urgent deployment with mandatory post-hoc rationale."""
        tc = require_tenant_context(tenant_context)
        req = self.get_provisioning_request(tenant_context=tc, request_id=request_id)

        if req.status in {
            ProvisioningRequestStatus.APPROVED,
            ProvisioningRequestStatus.REJECTED,
            ProvisioningRequestStatus.BYPASSED,
        }:
            raise ProvisioningRequestInvalidStateException(
                request_id=request_id,
                current_status=req.status.value,
                action="bypass",
            )

        gov_exc_id = f"govex-{uuid.uuid4().hex[:8]}"
        bypass_rec = BypassRecord(
            bypass_id=f"byp-{uuid.uuid4().hex[:8]}",
            request_id=request_id,
            bypassed_by=bypassed_by,
            justification=justification,
            governance_exception_id=gov_exc_id,
        )

        req.status = ProvisioningRequestStatus.BYPASSED
        req.bypass_details = bypass_rec
        self.repository.save_request(req)
        self.repository.save_bypass(tc.tenant_id, bypass_rec)

        self._record_audit(
            tc,
            AuditEventType.PROVISIONING_GATE_BYPASSED,
            "ProvisioningRequest",
            req.request_id,
            {
                "bypassed_by": bypassed_by,
                "justification": justification,
                "governance_exception_id": gov_exc_id,
            },
        )
        return req

    # ==========================================================================
    # 5. Resource Linking & Reconciliation Loop (First 3 Billing Periods)
    # ==========================================================================

    def link_resource_to_request(
        self,
        *,
        tenant_context: TenantContext,
        request_id: str,
        resource_id: str,
        approver_role: str | None = None,
    ) -> tuple[ProvisioningRequest, EstimateVsActualTracking]:
        """Links a discovered cloud inventory resource to an approved/bypassed request and starts tracking."""
        tc = require_tenant_context(tenant_context)
        req = self.get_provisioning_request(tenant_context=tc, request_id=request_id)

        if req.status not in {
            ProvisioningRequestStatus.APPROVED,
            ProvisioningRequestStatus.BYPASSED,
        }:
            raise ProvisioningRequestInvalidStateException(
                request_id=request_id,
                current_status=req.status.value,
                action="link_resource",
            )

        now = dt.datetime.now(dt.UTC)
        req.linked_resource_id = resource_id
        req.linked_at = now.isoformat()
        req.status = ProvisioningRequestStatus.LINKED_TO_RESOURCE
        self.repository.save_request(req)

        tracking = self.reconciliation_engine.initialize_tracking(
            request=req,
            resource_id=resource_id,
            approver_role=approver_role,
        )
        saved_tracking = self.repository.save_tracking(tc.tenant_id, tracking)

        self._record_audit(
            tc,
            AuditEventType.PROVISIONING_RESOURCE_LINKED,
            "ProvisioningRequest",
            req.request_id,
            {"resource_id": resource_id, "tracking_id": saved_tracking.tracking_id},
        )
        return req, saved_tracking

    def record_period_actual(
        self,
        *,
        tenant_context: TenantContext,
        request_id: str,
        period: str,
        billed_amount: Decimal,
    ) -> EstimateVsActualTracking:
        """Records actual billed spend for a period and evaluates estimate vs actual accuracy."""
        tc = require_tenant_context(tenant_context)
        tracking = self.repository.get_tracking_by_request_id(tc.tenant_id, request_id)
        if not tracking:
            raise ProvisioningRequestNotFoundException(
                f"No tracking record found for provisioning request '{request_id}'."
            )

        updated_tracking = self.reconciliation_engine.record_period_actual(
            tracking=tracking,
            period=period,
            billed_amount=billed_amount,
        )
        saved = self.repository.save_tracking(tc.tenant_id, updated_tracking)

        self._record_audit(
            tc,
            AuditEventType.PROVISIONING_ACCURACY_EVALUATED,
            "EstimateVsActualTracking",
            saved.tracking_id,
            {
                "request_id": request_id,
                "period": period,
                "billed_amount": str(billed_amount),
                "variance_pct": str(saved.latest_variance_pct),
                "classification": saved.classification.value if saved.classification else None,
                "is_three_periods_complete": saved.is_three_periods_complete,
            },
        )
        return saved

    def generate_accuracy_report(self, *, tenant_context: TenantContext) -> AccuracyReport:
        """Generates cross-sectional accuracy metrics across requesters, services, and approvers."""
        tc = require_tenant_context(tenant_context)
        trackings = self.repository.list_trackings(tc.tenant_id)
        return self.reconciliation_engine.generate_accuracy_report(tc.tenant_id, trackings)

    # ==========================================================================
    # 6. Unapproved Deployment Detection
    # ==========================================================================

    def detect_unapproved_deployments(
        self,
        *,
        tenant_context: TenantContext,
        inventoried_resources: list[dict[str, Any]],
        gated_scopes: set[str],
    ) -> list[UnapprovedDeploymentFinding]:
        """Scans inventory for resources deployed in gated scopes without approved requests."""
        tc = require_tenant_context(tenant_context)
        active_requests = self.repository.list_requests(tc.tenant_id)

        findings = self.unapproved_detector.detect_unapproved(
            tenant_id=tc.tenant_id,
            inventoried_resources=inventoried_resources,
            active_requests=active_requests,
            gated_scopes=gated_scopes,
        )

        for f in findings:
            self.repository.save_finding(tc.tenant_id, f)
            self._record_audit(
                tc,
                AuditEventType.UNAPPROVED_DEPLOYMENT_DETECTED,
                "CloudResource",
                f.resource_id,
                {
                    "scope_code": f.scope_code,
                    "estimated_monthly_cost": str(f.estimated_monthly_cost),
                    "governance_exception_id": f.governance_exception_id,
                    "remediation_task_id": f.remediation_task_id,
                },
            )
        return findings

    # ==========================================================================
    # 7. Scenario Comparison View (Decision Aid)
    # ==========================================================================

    def compare_scenarios(
        self,
        *,
        tenant_context: TenantContext,
        target_scope: str,
        period: str,
        baseline_estimate: SavedEstimate,
        alternative_estimates: list[SavedEstimate],
        period_budget: Decimal = Decimal("50000.00"),
        actual_spend: Decimal = Decimal("30000.00"),
        recommendation_notes: str = "",
    ) -> ScenarioComparisonView:
        """Compares 2 to 4 architecture configurations side by side against budget impact and cost drivers."""
        require_tenant_context(tenant_context)
        all_estimates = [baseline_estimate] + alternative_estimates
        if len(all_estimates) < 2 or len(all_estimates) > 4:
            raise ValueError("Scenario comparison requires between 2 and 4 configurations.")

        baseline_monthly = baseline_estimate.monthly_cost
        scenario_options: list[ScenarioOption] = []

        for idx, est in enumerate(all_estimates):
            is_base = idx == 0
            b_impact = self.budget_impact_engine.evaluate_impact(
                period=period,
                period_budget=period_budget,
                actual_spend=actual_spend,
                request_monthly_cost=est.monthly_cost,
            )
            q_check = self.quota_engine.evaluate_quota(
                provider=est.provider,
                service=est.service,
                region=est.region,
            )
            d_check = self.dependency_engine.evaluate_dependencies(
                provider=est.provider,
                service=est.service,
                primary_monthly_cost=est.monthly_cost,
                options=est.options,
            )

            delta_monthly = round_currency(est.monthly_cost - baseline_monthly)
            if baseline_monthly > Decimal("0.00"):
                delta_pct = round_currency((delta_monthly / baseline_monthly) * Decimal("100.00"))
            else:
                delta_pct = Decimal("0.00")

            opt = ScenarioOption(
                scenario_id=f"OPTION_{chr(65 + idx)}" if not is_base else "BASELINE",
                name=f"Config {chr(65 + idx)}: {est.size} ({est.provider.upper()})",
                description=f"{est.service} in {est.region}",
                estimate=est,
                budget_impact=b_impact,
                quota_pre_check=q_check,
                dependency_pre_check=d_check,
                monthly_cost=est.monthly_cost,
                annualised_cost=est.annualised_cost,
                delta_from_baseline_monthly=delta_monthly,
                delta_from_baseline_pct=delta_pct,
            )
            scenario_options.append(opt)

        return ScenarioComparisonView(
            comparison_id=f"scen-{uuid.uuid4().hex[:8]}",
            baseline_scenario_id="BASELINE",
            target_scope=target_scope,
            period=period,
            scenarios=scenario_options,
            recommendation_notes=recommendation_notes
            or "Evaluated configurations side by side to assist cost-aware deployment decision.",
        )

    # --------------------------------------------------------------------------
    # Audit Logging Helper
    # --------------------------------------------------------------------------
    def _record_audit(
        self,
        tc: TenantContext,
        event_type: AuditEventType,
        resource_type: str,
        resource_id: str,
        details: dict[str, Any],
    ) -> None:
        try:
            evt = AuditEventCreate(
                event_type=event_type,
                actor_id=tc.user_id,
                actor_roles=tc.roles,
                action=event_type.value,
                resource_type=resource_type,
                resource_id=resource_id,
                details=details,
            )
            self.audit_service.append_event(tenant_context=tc, event_in=evt)
        except Exception as e:
            logger.warning("Failed to record audit event %s: %s", event_type, e)


_GLOBAL_PROVISIONING_SERVICE: ProvisioningGateService | None = None


def get_provisioning_gate_service() -> ProvisioningGateService:
    """Singleton accessor for ProvisioningGateService."""
    global _GLOBAL_PROVISIONING_SERVICE
    if _GLOBAL_PROVISIONING_SERVICE is None:
        _GLOBAL_PROVISIONING_SERVICE = ProvisioningGateService()
    return _GLOBAL_PROVISIONING_SERVICE


def reset_provisioning_gate_service() -> None:
    """Resets the singleton instance."""
    global _GLOBAL_PROVISIONING_SERVICE
    _GLOBAL_PROVISIONING_SERVICE = None
