"""Deterministic Governance-Layer Mock Estate Generator (Prompt 47B).

Enforces:
- Deterministic generation of governance and control datasets:
  1. Quotas across all headroom states (Healthy, Warning, Breach Imminent, Exhausted, Not Supported, Manual).
  2. Provisioning requests in all eight workflow states with linked approved-to-actual tracking and unapproved deployment.
  3. Remediation tasks in all eleven states, including a false-resolved task that reopens on verification.
  4. Showback statements for at least 3 business units over 2 periods with dispute, acceptance, unallocated, and restatement.
  5. Approver inbox requests of every workflow type, with escalation and delegation.
  6. Commitments (over-committed, under-committed, renewal window).
  7. Budget planning (open cycle, top-down target, partial submissions, visible gap).
  8. Master-data gap items, import history, and analytical extract run history.
- Direct seeding into domain repositories for Demo Mode.
- 100% deterministic output: identical seed yields identical objects and metrics.
"""

from __future__ import annotations

import datetime as dt
import logging
import random
from decimal import Decimal

from domain.models.enums import (
    ApprovalChainMode,
    CloudProvider,
    DecisionOutcome,
    QuotaHeadroomState,
    QuotaScopeType,
    QuotaServiceAffectingType,
    RealisedSavingMethod,
    TaskCategory,
    TaskClosureCode,
    TaskPriority,
    TaskSource,
    TaskState,
    WorkflowRequestType,
    WorkflowState,
)
from domain.provisioning.models import (
    ADVISORY_GATE_NOTICE,
    BudgetImpactAssessment,
    BudgetImpactTier,
    BypassRecord,
    DependencyComponentCost,
    DependencyPreCheckResult,
    EstimateAccuracyClassification,
    EstimateVsActualTracking,
    GateTriggerAction,
    ProvisioningRequest,
    ProvisioningRequestStatus,
    QuotaPreCheckResult,
    ResourcePeriodActual,
    SavedEstimate,
    UnapprovedDeploymentFinding,
)
from domain.provisioning.repository import get_provisioning_repository
from domain.quotas.models import (
    QuotaDataPoint,
    QuotaEntity,
    QuotaRemediationTask,
)
from domain.quotas.repository import get_quota_repository
from domain.remediation.models import (
    RemediationHistoryEntry,
    RemediationTask,
    SubjectEntity,
)
from domain.remediation.repository import get_remediation_repository
from domain.rules.monetary import round_currency
from domain.statements.models import (
    AdjustmentLine,
    ApplicationBreakdownItem,
    BudgetVarianceStatus,
    CategoryBreakdownItem,
    CostMovementItem,
    DiscountBenefitItem,
    DisputeStatus,
    EnvironmentBreakdownItem,
    MovementDirection,
    ProviderBreakdownItem,
    RecipientScopeType,
    SharedServiceApportionmentItem,
    ShowbackStatement,
    StatementAdjustment,
    StatementDispute,
    StatementLifecycleStatus,
    StatementMode,
    UnallocatedCostItem,
)
from domain.statements.repository import get_statement_repository
from domain.synthetic.governance_models import (
    AnalyticalExtractRun,
    AnalyticalExtractRunStatus,
    BudgetPlanningCycle,
    BudgetPlanningSubmission,
    BulkImportJobSummary,
    CommitmentPortfolioItem,
    CommitmentStatus,
    CommitmentType,
    GovernanceMockEstateResult,
    MasterDataGapItem,
)
from domain.tenant.context import TenantContext
from domain.workflows.models import (
    RequesterInfo,
    WorkflowDecision,
    WorkflowHistoryEntry,
    WorkflowRequest,
    WorkflowStage,
)
from domain.workflows.models import (
    SubjectEntity as WorkflowSubjectEntity,
)
from domain.workflows.repository import get_workflow_repository

logger = logging.getLogger(__name__)


class DeterministicGovernanceMockGenerator:
    """Generates byte-identical governance and control estates for demonstration."""

    def __init__(self, seed: int = 42) -> None:
        self.seed = seed

    def generate(
        self,
        tenant_id: str = "T-DEMO",
        as_of_date: dt.datetime | None = None,
    ) -> GovernanceMockEstateResult:
        """Generates all governance datasets deterministically."""
        # Use an isolated RNG initialized from seed + 777 to maintain separate reproducibility
        _rng = random.Random(self.seed + 777)
        now = as_of_date or dt.datetime(2026, 9, 26, 0, 0, 0, tzinfo=dt.UTC)
        now_iso = now.isoformat()

        # ----------------------------------------------------------------------
        # 1. Quotas (Prompt 54) - All Headroom States Across 4 Profiles
        # ----------------------------------------------------------------------
        quotas: list[QuotaEntity] = []
        quota_tasks: list[QuotaRemediationTask] = []

        # 1a. AWS Compute vCPU (us-east-1): WARNING (< 20% headroom: 56/64 = 12.5% headroom)
        q_aws_vcpu = QuotaEntity(
            id="quota-aws-vcpu-01",
            tenant_id=tenant_id,
            provider=CloudProvider.AWS,
            scope_type=QuotaScopeType.REGION,
            scope_id="us-east-1",
            service_code="ec2",
            quota_code="L-1216C47A",
            quota_name="Running On-Demand Standard (A, C, D, I, M, R, T, Z) vCPUs",
            description="Active capacity growth across web tier instances.",
            limit_value=64.0,
            consumed_value=56.0,
            unit="vCPU",
            is_adjustable=True,
            is_manual=False,
            category="COMPUTE",
            exhaustion_impact=QuotaServiceAffectingType.SERVICE_AFFECTING,
            lead_time_days=7,
            status=QuotaHeadroomState.WARNING,
            predicted_exhaustion_date=(now + dt.timedelta(days=12)),
            history=[
                QuotaDataPoint(
                    timestamp=(now - dt.timedelta(days=10)),
                    consumed_value=44.0,
                    limit_value=64.0,
                    headroom_value=20.0,
                    headroom_pct=31.25,
                ),
                QuotaDataPoint(
                    timestamp=(now - dt.timedelta(days=5)),
                    consumed_value=50.0,
                    limit_value=64.0,
                    headroom_value=14.0,
                    headroom_pct=21.88,
                ),
                QuotaDataPoint(
                    timestamp=now,
                    consumed_value=56.0,
                    limit_value=64.0,
                    headroom_value=8.0,
                    headroom_pct=12.50,
                ),
            ],
        )
        quotas.append(q_aws_vcpu)

        # 1b. AWS EBS Storage (us-east-1): HEALTHY (Ample headroom: 6144/20480 = 70% headroom)
        q_aws_ebs = QuotaEntity(
            id="quota-aws-ebs-02",
            tenant_id=tenant_id,
            provider=CloudProvider.AWS,
            scope_type=QuotaScopeType.REGION,
            scope_id="us-east-1",
            service_code="ec2",
            quota_code="L-D18FCDEB",
            quota_name="Storage for General Purpose SSD (gp3) volumes",
            description="Comfortably within safe capacity limits (70% headroom).",
            limit_value=20480.0,
            consumed_value=6144.0,
            unit="GiB",
            is_adjustable=True,
            is_manual=False,
            category="STORAGE",
            exhaustion_impact=QuotaServiceAffectingType.SERVICE_AFFECTING,
            lead_time_days=3,
            status=QuotaHeadroomState.NORMAL,
            history=[
                QuotaDataPoint(
                    timestamp=now,
                    consumed_value=6144.0,
                    limit_value=20480.0,
                    headroom_value=14336.0,
                    headroom_pct=70.0,
                ),
            ],
        )
        quotas.append(q_aws_ebs)

        # 1c. GCP Custom AI Accelerator (us-central1): NOT_SUPPORTED (Provider does not expose limit)
        q_gcp_not_sup = QuotaEntity(
            id="quota-gcp-ai-03",
            tenant_id=tenant_id,
            provider=CloudProvider.GCP,
            scope_type=QuotaScopeType.REGION,
            scope_id="us-central1",
            service_code="vertexai",
            quota_code="L-GCP-TPU-BETA",
            quota_name="Custom Specialized TPU v5e Pod Slice Allowance",
            description="Cloud provider does not expose programmatically via Quotas API; renders as Not Supported.",
            limit_value=None,
            consumed_value=12.0,
            unit="count",
            is_adjustable=True,
            is_manual=False,
            category="AI_ML",
            exhaustion_impact=QuotaServiceAffectingType.SERVICE_AFFECTING,
            status=QuotaHeadroomState.NOT_SUPPORTED,
        )
        quotas.append(q_gcp_not_sup)

        # 1d. Azure Compute Core Limit (eastus): CRITICAL / BREACH_IMMINENT (Predicted exhaustion inside lead time)
        q_az_breach = QuotaEntity(
            id="quota-az-core-04",
            tenant_id=tenant_id,
            provider=CloudProvider.AZURE,
            scope_type=QuotaScopeType.REGION,
            scope_id="eastus",
            service_code="compute",
            quota_code="L-AZ-DV4-FAMILY",
            quota_name="Total Regional Standard Dv4 vCPUs",
            description="Predicted exhaustion date (in 9 days) is inside standard vendor lead time (14 days).",
            limit_value=100.0,
            consumed_value=92.0,
            unit="vCPU",
            is_adjustable=True,
            is_manual=False,
            category="COMPUTE",
            exhaustion_impact=QuotaServiceAffectingType.SERVICE_AFFECTING,
            lead_time_days=14,
            status=QuotaHeadroomState.CRITICAL,
            predicted_exhaustion_date=(now + dt.timedelta(days=9)),
            history=[
                QuotaDataPoint(
                    timestamp=(now - dt.timedelta(days=15)),
                    consumed_value=60.0,
                    limit_value=100.0,
                    headroom_value=40.0,
                    headroom_pct=40.0,
                ),
                QuotaDataPoint(
                    timestamp=(now - dt.timedelta(days=7)),
                    consumed_value=80.0,
                    limit_value=100.0,
                    headroom_value=20.0,
                    headroom_pct=20.0,
                ),
                QuotaDataPoint(
                    timestamp=now,
                    consumed_value=92.0,
                    limit_value=100.0,
                    headroom_value=8.0,
                    headroom_pct=8.0,
                ),
            ],
        )
        quotas.append(q_az_breach)

        # Linked remediation task for Azure breach
        q_rem_task = QuotaRemediationTask(
            id="qtask-az-core-01",
            tenant_id=tenant_id,
            quota_id=q_az_breach.id,
            quota_code=q_az_breach.quota_code,
            title="Request Regional Quota Increase for Azure Dv4 vCPUs",
            description="Predicted exhaustion in 9 days with 14-day vendor lead time requires immediate increase request.",
            due_date=(now + dt.timedelta(days=9)),
            assigned_owner_id="cloudops-azure@cloudlens.internal",
            status="OPEN",
            created_at=now,
        )
        quota_tasks.append(q_rem_task)

        # 1e. OCI Block Storage (us-ashburn-1): MANUAL_SOURCE (Enterprise contract limit)
        q_oci_manual = QuotaEntity(
            id="quota-oci-block-05",
            tenant_id=tenant_id,
            provider=CloudProvider.OCI,
            scope_type=QuotaScopeType.REGION,
            scope_id="us-ashburn-1",
            service_code="blockstorage",
            quota_code="L-OCI-BLOCK-TB",
            quota_name="Total Account Block Storage Capacity (TB)",
            description="Custom contractual ceiling manually recorded per BBP Section 27.",
            limit_value=50000.0,
            consumed_value=42000.0,
            unit="TB",
            is_adjustable=True,
            is_manual=True,
            manual_source_note="Enterprise negotiated master contract amendment OCI-2026-Q1 signed by Procurement.",
            category="STORAGE",
            exhaustion_impact=QuotaServiceAffectingType.SERVICE_AFFECTING,
            lead_time_days=10,
            status=QuotaHeadroomState.WARNING,
            history=[
                QuotaDataPoint(
                    timestamp=now,
                    consumed_value=42000.0,
                    limit_value=50000.0,
                    headroom_value=8000.0,
                    headroom_pct=16.0,
                ),
            ],
        )
        quotas.append(q_oci_manual)

        # 1f. GCP Cloud SQL RAM (us-central1): HEALTHY (25% consumed, 75% headroom)
        q_gcp_sql = QuotaEntity(
            id="quota-gcp-sql-06",
            tenant_id=tenant_id,
            provider=CloudProvider.GCP,
            scope_type=QuotaScopeType.REGION,
            scope_id="us-central1",
            service_code="cloudsql",
            quota_code="L-GCP-SQL-RAM-GB",
            quota_name="Total Cloud SQL Instance RAM (GB)",
            description="Comfortably within safe database allocation envelope (75% headroom).",
            limit_value=512.0,
            consumed_value=128.0,
            unit="GB",
            is_adjustable=True,
            is_manual=False,
            category="DATABASE",
            exhaustion_impact=QuotaServiceAffectingType.SERVICE_AFFECTING,
            lead_time_days=2,
            status=QuotaHeadroomState.NORMAL,
            history=[
                QuotaDataPoint(
                    timestamp=now,
                    consumed_value=128.0,
                    limit_value=512.0,
                    headroom_value=384.0,
                    headroom_pct=75.0,
                ),
            ],
        )
        quotas.append(q_gcp_sql)

        # 1g. Azure App Service Plans (eastus): WARNING (<20% headroom: 17/20 = 15% headroom)
        q_az_app = QuotaEntity(
            id="quota-az-app-07",
            tenant_id=tenant_id,
            provider=CloudProvider.AZURE,
            scope_type=QuotaScopeType.REGION,
            scope_id="eastus",
            service_code="web",
            quota_code="L-AZ-APP-PLANS",
            quota_name="Total Standard App Service Plans",
            description="Approaching capacity threshold (<20% headroom).",
            limit_value=20.0,
            consumed_value=17.0,
            unit="count",
            is_adjustable=True,
            is_manual=False,
            category="COMPUTE",
            exhaustion_impact=QuotaServiceAffectingType.SERVICE_AFFECTING,
            lead_time_days=5,
            status=QuotaHeadroomState.WARNING,
            history=[
                QuotaDataPoint(
                    timestamp=now,
                    consumed_value=17.0,
                    limit_value=20.0,
                    headroom_value=3.0,
                    headroom_pct=15.0,
                ),
            ],
        )
        quotas.append(q_az_app)

        # 1h. OCI Compute OCPUs (us-ashburn-1): HEALTHY (80/160 = 50% headroom)
        q_oci_compute = QuotaEntity(
            id="quota-oci-ocpu-08",
            tenant_id=tenant_id,
            provider=CloudProvider.OCI,
            scope_type=QuotaScopeType.REGION,
            scope_id="us-ashburn-1",
            service_code="compute",
            quota_code="L-OCI-VM-STANDARD-E4",
            quota_name="Total VM.Standard.E4 OCPU Allowance",
            description="Operational headroom within normal operating ranges (50% headroom).",
            limit_value=160.0,
            consumed_value=80.0,
            unit="OCPU",
            is_adjustable=True,
            is_manual=False,
            category="COMPUTE",
            exhaustion_impact=QuotaServiceAffectingType.SERVICE_AFFECTING,
            lead_time_days=7,
            status=QuotaHeadroomState.NORMAL,
            history=[
                QuotaDataPoint(
                    timestamp=now,
                    consumed_value=80.0,
                    limit_value=160.0,
                    headroom_value=80.0,
                    headroom_pct=50.0,
                ),
            ],
        )
        quotas.append(q_oci_compute)

        # ----------------------------------------------------------------------
        # 2. Provisioning Requests (Prompt 55) - All 8 States & Reconciliation
        # ----------------------------------------------------------------------
        saved_estimates: list[SavedEstimate] = []
        provisioning_requests: list[ProvisioningRequest] = []
        trackings: list[EstimateVsActualTracking] = []
        unapproved_findings: list[UnapprovedDeploymentFinding] = []

        # Helper to build consistent estimates
        def make_estimate(
            est_id: str,
            svc: str,
            size: str,
            monthly: Decimal,
            valid_days: int = 14,
        ) -> SavedEstimate:
            hourly = round_currency(monthly / Decimal("730.0"))
            daily = round_currency(hourly * Decimal("24.0"))
            annual = round_currency(monthly * Decimal("12.0"))
            return SavedEstimate(
                estimate_id=est_id,
                tenant_id=tenant_id,
                requester_id="user-eng-lead",
                requester_email="eng-lead@cloudlens.internal",
                provider="aws",
                service=svc,
                region="us-east-1",
                size=size,
                options={"storage_gb": 150},
                hourly_cost=hourly,
                daily_cost=daily,
                monthly_cost=monthly,
                annualised_cost=annual,
                valid_until=(now + dt.timedelta(days=valid_days)).isoformat(),
                created_at=(now - dt.timedelta(days=2)).isoformat(),
            )

        est_1 = make_estimate("est-demo-01", "AmazonEC2", "c5.2xlarge", Decimal("248.20"))
        est_2 = make_estimate("est-demo-02", "AmazonRDS", "db.r5.xlarge", Decimal("730.00"))
        est_3 = make_estimate("est-demo-03", "AmazonS3", "Standard", Decimal("85.00"))
        est_4 = make_estimate(
            "est-demo-04", "Virtual Machines", "Standard_D8s_v4", Decimal("380.00")
        )
        est_expired = make_estimate(
            "est-demo-expired", "AmazonEC2", "m5.large", Decimal("70.08"), valid_days=-3
        )
        saved_estimates.extend([est_1, est_2, est_3, est_4, est_expired])

        # Budget impact helper
        def make_impact(monthly: Decimal, tier: BudgetImpactTier) -> BudgetImpactAssessment:
            return BudgetImpactAssessment(
                period="2026-09",
                period_budget=Decimal("50000.00"),
                actual_spend=Decimal("32000.00"),
                remaining_budget=Decimal("18000.00"),
                request_monthly_cost=monthly,
                projected_spend=Decimal("32000.00") + monthly,
                projected_utilisation_pct=Decimal("65.50"),
                consumption_of_remaining_pct=round_currency(
                    (monthly / Decimal("18000.00")) * Decimal("100.00")
                ),
                current_forecast=Decimal("48000.00"),
                revised_forecast=Decimal("48000.00") + monthly,
                forecast_variance_change=monthly,
                impact_tier=tier,
                commentary=f"Simulated {tier.value} budget impact for demonstration.",
            )

        def make_precheck(monthly: Decimal) -> tuple[QuotaPreCheckResult, DependencyPreCheckResult]:
            q_res = QuotaPreCheckResult(
                is_blocked=False,
                headroom_warning=False,
                current_headroom_pct=Decimal("65.00"),
                projected_headroom_pct=Decimal("62.50"),
                quota_name="Standard vCPU Allowance",
                quota_code="L-1216C47A",
                consumed_units=Decimal("44.0"),
                limit_units=Decimal("64.0"),
                projected_units=Decimal("46.0"),
                message="Quota headroom is healthy.",
            )
            d_res = DependencyPreCheckResult(
                primary_monthly_cost=monthly,
                inferred_dependencies=[
                    DependencyComponentCost(
                        service_name="Attached Block Storage (150 GB gp3)",
                        category="Storage",
                        estimated_monthly_cost=Decimal("12.00"),
                        basis="Root boot volume",
                    ),
                    DependencyComponentCost(
                        service_name="Application Load Balancer",
                        category="Network",
                        estimated_monthly_cost=Decimal("22.50"),
                        basis="Ingress traffic controller",
                    ),
                ],
                total_chain_monthly_cost=monthly + Decimal("34.50") + Decimal("15.00"),
                shared_service_apportionment=Decimal("15.00"),
                chain_multiplier=Decimal("1.25"),
            )
            return q_res, d_res

        # All Workflow States for Provisioning Requests
        states = [
            (
                ProvisioningRequestStatus.DRAFT,
                "prv-demo-draft",
                "BU-DEV",
                "DEV",
                est_1,
                BudgetImpactTier.NEGLIGIBLE,
                "DRAFT",
            ),
            (
                ProvisioningRequestStatus.SUBMITTED,
                "prv-demo-submitted",
                "BU-RETAIL",
                "STAGING",
                est_1,
                BudgetImpactTier.MODERATE,
                "SUBMITTED",
            ),
            (
                ProvisioningRequestStatus.IN_REVIEW,
                "prv-demo-in-review",
                "BU-RETAIL",
                "PROD",
                est_2,
                BudgetImpactTier.SUBSTANTIAL,
                "IN_REVIEW",
            ),
            (
                ProvisioningRequestStatus.APPROVED,
                "prv-demo-approved",
                "BU-COMMERCIAL",
                "PROD",
                est_4,
                BudgetImpactTier.MODERATE,
                "APPROVED",
            ),
            (
                ProvisioningRequestStatus.REJECTED,
                "prv-demo-rejected",
                "BU-MARKETING",
                "DEV",
                est_2,
                BudgetImpactTier.CRITICAL,
                "REJECTED",
            ),
            (
                ProvisioningRequestStatus.DRAFT,
                "prv-demo-withdrawn",
                "BU-DIGITAL",
                "STAGING",
                est_3,
                BudgetImpactTier.NEGLIGIBLE,
                "WITHDRAWN",
            ),
            (
                ProvisioningRequestStatus.DRAFT,
                "prv-demo-expired",
                "BU-DIGITAL",
                "DEV",
                est_expired,
                BudgetImpactTier.NEGLIGIBLE,
                "EXPIRED",
            ),
            (
                ProvisioningRequestStatus.APPROVED,
                "prv-demo-applied",
                "BU-CORE",
                "PROD",
                est_1,
                BudgetImpactTier.MODERATE,
                "APPLIED",
            ),
            (
                ProvisioningRequestStatus.BYPASSED,
                "prv-demo-bypassed",
                "BU-CORE",
                "PROD",
                est_2,
                BudgetImpactTier.SUBSTANTIAL,
                "APPROVED",
            ),
        ]

        for st, req_id, scope, env, est, tier, wf_state in states:
            q_res, d_res = make_precheck(est.monthly_cost)
            bypass = None
            if st == ProvisioningRequestStatus.BYPASSED:
                bypass = BypassRecord(
                    bypass_id=f"byp-{req_id}",
                    request_id=req_id,
                    bypassed_by="user-admin@cloudlens.internal",
                    justification="Emergency disaster recovery provisioning bypass authorized by CTO.",
                    governance_exception_id="exc-bypass-dr-01",
                )

            pr = ProvisioningRequest(
                request_id=req_id,
                tenant_id=tenant_id,
                estimate_id=est.estimate_id,
                estimate=est,
                target_scope=scope,
                scope_type="BUSINESS_UNIT",
                intended_application="CoreBankingService",
                intended_environment=env,
                owner_id="user-eng-lead",
                owner_email="eng-lead@cloudlens.internal",
                cost_centre="CC-ENG-100",
                business_justification=f"Simulated pre-deployment request in workflow state {wf_state}.",
                intended_start_date=(now + dt.timedelta(days=7)).strftime("%Y-%m-%d"),
                budget_impact=make_impact(est.monthly_cost, tier),
                quota_pre_check=q_res,
                dependency_pre_check=d_res,
                gate_action=GateTriggerAction.APPROVAL_REQUIRED
                if env == "PROD"
                else GateTriggerAction.NOTIFY_ONLY,
                status=st,
                workflow_request_id=f"wf-{req_id}",
                bypass_details=bypass,
                created_at=(now - dt.timedelta(days=3)).isoformat(),
                advisory_notice=ADVISORY_GATE_NOTICE,
            )
            provisioning_requests.append(pr)

        # 2b. Approved Request Linked to Resource with 3 Periods of Actuals
        req_linked = ProvisioningRequest(
            request_id="prv-demo-linked-reconciled",
            tenant_id=tenant_id,
            estimate_id=est_1.estimate_id,
            estimate=est_1,
            target_scope="BU-RETAIL",
            scope_type="BUSINESS_UNIT",
            intended_application="StorefrontGateway",
            intended_environment="PROD",
            owner_id="user-eng-lead",
            owner_email="eng-lead@cloudlens.internal",
            cost_centre="CC-RETAIL-01",
            business_justification="Production storefront gateway capacity scaling.",
            intended_start_date=(now - dt.timedelta(days=90)).strftime("%Y-%m-%d"),
            budget_impact=make_impact(est_1.monthly_cost, BudgetImpactTier.MODERATE),
            quota_pre_check=make_precheck(est_1.monthly_cost)[0],
            dependency_pre_check=make_precheck(est_1.monthly_cost)[1],
            gate_action=GateTriggerAction.APPROVAL_REQUIRED,
            status=ProvisioningRequestStatus.LINKED_TO_RESOURCE,
            linked_resource_id="i-0987654321fedcba0",
            linked_at=(now - dt.timedelta(days=85)).isoformat(),
            created_at=(now - dt.timedelta(days=95)).isoformat(),
            advisory_notice=ADVISORY_GATE_NOTICE,
        )
        provisioning_requests.append(req_linked)

        tracking_3p = EstimateVsActualTracking(
            tracking_id="track-demo-3period-01",
            request_id=req_linked.request_id,
            resource_id="i-0987654321fedcba0",
            requester_id="user-eng-lead",
            approver_role="FINOPS_ADMIN",
            service=est_1.service,
            approved_monthly_estimate=est_1.monthly_cost,
            periods_tracked=[
                ResourcePeriodActual(period="2026-07", billed_amount=Decimal("245.00")),
                ResourcePeriodActual(period="2026-08", billed_amount=Decimal("252.00")),
                ResourcePeriodActual(period="2026-09", billed_amount=Decimal("249.50")),
            ],
            latest_variance_amount=Decimal("1.30"),
            latest_variance_pct=Decimal("0.52"),
            classification=EstimateAccuracyClassification.WITHIN_ACCURACY_BAND,
            is_three_periods_complete=True,
        )
        trackings.append(tracking_3p)

        # 2c. Unapproved Deployment in Gated Scope
        unapp_finding = UnapprovedDeploymentFinding(
            finding_id="unapp-demo-shadow-01",
            resource_id="i-rogue-shadow-99",
            resource_name="shadow-ml-cluster-node",
            provider="AWS",
            service="AmazonEC2",
            scope_code="BU-RETAIL",
            detected_at=(now - dt.timedelta(days=1)).isoformat(),
            estimated_monthly_cost=Decimal("450.00"),
            governance_exception_id="govex-demo-shadow-01",
            remediation_task_id="rem-demo-shadow-01",
            advisory_disclaimer=ADVISORY_GATE_NOTICE,
        )
        unapproved_findings.append(unapp_finding)

        # 2d. Emergency Bypassed Request
        req_bypassed = ProvisioningRequest(
            request_id="prv-demo-bypassed-sev1",
            tenant_id=tenant_id,
            estimate_id=est_2.estimate_id,
            estimate=est_2,
            target_scope="BU-CORE",
            scope_type="BUSINESS_UNIT",
            intended_application="IncidentMitigationDB",
            intended_environment="PROD",
            owner_id="user-commander",
            owner_email="commander@cloudlens.internal",
            cost_centre="CC-ENG-100",
            business_justification="SEV1 Outage hotfix database cluster.",
            intended_start_date=now.strftime("%Y-%m-%d"),
            budget_impact=make_impact(est_2.monthly_cost, BudgetImpactTier.SUBSTANTIAL),
            quota_pre_check=make_precheck(est_2.monthly_cost)[0],
            dependency_pre_check=make_precheck(est_2.monthly_cost)[1],
            gate_action=GateTriggerAction.APPROVAL_REQUIRED,
            status=ProvisioningRequestStatus.BYPASSED,
            bypass_details=BypassRecord(
                bypass_id="byp-demo-01",
                request_id="prv-demo-bypassed-sev1",
                bypassed_by="incident-commander-john",
                justification="Emergency production outage mitigation per Runbook INC-992.",
                governance_exception_id="govex-demo-bypass-01",
            ),
            created_at=now.isoformat(),
            advisory_notice=ADVISORY_GATE_NOTICE,
        )
        provisioning_requests.append(req_bypassed)

        # ----------------------------------------------------------------------
        # 3. Remediation Tasks (Prompt 51) - All 11 States & False-Resolved Case
        # ----------------------------------------------------------------------
        remediation_tasks: list[RemediationTask] = []

        all_states = [
            (
                TaskState.OPEN,
                "task-demo-open-01",
                "Unowned Disused Volume",
                45.0,
                TaskSource.POLICY_FINDING,
            ),
            (
                TaskState.ASSIGNED,
                "task-demo-assigned-02",
                "Rightsizing Memory on Database",
                180.0,
                TaskSource.ALERT,
            ),
            (
                TaskState.IN_PROGRESS,
                "task-demo-in-progress-03",
                "Decommissioning Dev Cluster",
                350.0,
                TaskSource.BUDGET_BREACH,
            ),
            (
                TaskState.BLOCKED,
                "task-demo-blocked-04",
                "Storage Tiering Awaiting Migration",
                120.0,
                TaskSource.MANUAL,
            ),
            (
                TaskState.AWAITING_VERIFICATION,
                "task-demo-awaiting-05",
                "Idle Instance Termination",
                95.0,
                TaskSource.POLICY_FINDING,
            ),
            (
                TaskState.RESOLVED,
                "task-demo-resolved-06",
                "Snapshot Retention Trim",
                60.0,
                TaskSource.POLICY_FINDING,
            ),
            (
                TaskState.VERIFIED,
                "task-demo-verified-07",
                "Orphaned NAT Gateway Deletion",
                32.4,
                TaskSource.POLICY_FINDING,
            ),
            (
                TaskState.CLOSED,
                "task-demo-closed-08",
                "Cold Archive Policy Execution",
                210.0,
                TaskSource.POLICY_FINDING,
            ),
            (
                TaskState.REJECTED,
                "task-demo-rejected-09",
                "Dismissed Alert (Planned DR Drill)",
                0.0,
                TaskSource.MANUAL,
            ),
            (
                TaskState.DEFERRED,
                "task-demo-deferred-10",
                "Scheduled OS Patch Window",
                75.0,
                TaskSource.POLICY_FINDING,
            ),
            (
                TaskState.DUPLICATE,
                "task-demo-duplicate-11",
                "Merged Finding with Primary Incident",
                0.0,
                TaskSource.ALERT,
            ),
        ]

        for task_st, t_id, title, saving, src in all_states:
            task = RemediationTask(
                id=t_id,
                tenant_id=tenant_id,
                title=title,
                description=f"Automated governance remediation task: {title}.",
                subject_entity=SubjectEntity(
                    entity_type="resource",
                    entity_id=f"res-{t_id[:12]}",
                    entity_name=title,
                    scope_type="subscription",
                    scope_id="sub-prod-01",
                    provider="AWS",
                ),
                assignee_id="cloud-engineer-alice@cloudlens.internal",
                source=src,
                priority=TaskPriority.HIGH if saving > 100 else TaskPriority.MEDIUM,
                created_at=(now - dt.timedelta(days=4)),
                due_date=(now + dt.timedelta(days=3)),
                sla_working_hours=48.0,
                estimated_saving=saving,
                state=task_st,
                category=TaskCategory.IDLE_RESOURCE
                if "Rightsizing" in title
                else TaskCategory.UNOWNED_RESOURCE,
                realised_saving=saving
                if task_st in {TaskState.VERIFIED, TaskState.CLOSED}
                else None,
                realised_saving_method=RealisedSavingMethod.IDLE_TERMINATION_DELTA
                if task_st in {TaskState.VERIFIED, TaskState.CLOSED}
                else None,
                closure_code=TaskClosureCode.FIXED_AND_VERIFIED
                if task_st == TaskState.CLOSED
                else None,
                history=[
                    RemediationHistoryEntry(
                        actor_id="system-audit",
                        action="STATE_TRANSITION",
                        from_state=TaskState.OPEN.value if task_st != TaskState.OPEN else None,
                        to_state=task_st.value,
                        note=f"Transitioned to {task_st.value} for demonstration.",
                    )
                ],
            )
            remediation_tasks.append(task)

        # 3b. False-Resolved Task (condition persists, reopens on automated verification)
        false_resolved_task = RemediationTask(
            id="task-demo-false-resolved",
            tenant_id=tenant_id,
            title="Orphaned 2TB Volume Deletion (Falsely Marked Resolved)",
            description="Orphaned volume deletion was claimed resolved by operator, but volume vol-0123456789orphaned remains active in cloud inventory.",
            subject_entity=SubjectEntity(
                entity_type="resource",
                entity_id="vol-0123456789orphaned",
                entity_name="unattached-backup-volume-2tb",
                scope_type="account",
                scope_id="acc-aws-prod",
                provider="AWS",
            ),
            assignee_id="devops-contractor@cloudlens.internal",
            source=TaskSource.POLICY_FINDING,
            priority=TaskPriority.CRITICAL,
            created_at=(now - dt.timedelta(days=5)),
            due_date=(now + dt.timedelta(days=2)),
            sla_working_hours=24.0,
            estimated_saving=160.0,
            state=TaskState.RESOLVED,
            category=TaskCategory.UNOWNED_RESOURCE,
            reason_code="MANUAL_DELETION_CLAIMED",
            verification_notes=[
                "Operator marked task resolved. Live volume presence will fail automated verification and reopen task."
            ],
            history=[
                RemediationHistoryEntry(
                    actor_id="devops-contractor@cloudlens.internal",
                    action="RESOLVE",
                    from_state=TaskState.IN_PROGRESS.value,
                    to_state=TaskState.RESOLVED.value,
                    note="Claimed volume was deleted.",
                )
            ],
        )
        remediation_tasks.append(false_resolved_task)

        # ----------------------------------------------------------------------
        # 4. Showback Statements (Prompt 52) - 3 BUs across 2 Periods
        # ----------------------------------------------------------------------
        showback_statements: list[ShowbackStatement] = []

        def make_statement(
            stmt_id: str,
            scope_code: str,
            scope_name: str,
            period: str,
            direct_cost: Decimal,
            shared_cost: Decimal,
            status_enum: StatementLifecycleStatus,
            has_unallocated: bool = False,
            is_adjustment: bool = False,
            supersedes_id: str | None = None,
        ) -> ShowbackStatement:
            total_allocated = direct_cost + shared_cost
            unalloc_amt = Decimal("6500.00") if has_unallocated else Decimal("0.00")

            stmt = ShowbackStatement(
                statement_id=stmt_id,
                tenant_id=tenant_id,
                period=period,
                version=2 if is_adjustment else 1,
                supersedes_statement_id=supersedes_id,
                scope_type=RecipientScopeType.BUSINESS_UNIT,
                scope_code=scope_code,
                scope_name=scope_name,
                recipient_owner_id=f"owner-{scope_code.lower()}@cloudlens.internal",
                recipient_owner_email=f"owner-{scope_code.lower()}@cloudlens.internal",
                status=status_enum,
                mode=StatementMode.SHOWBACK,
                total_allocated_cost=total_allocated,
                direct_allocated_cost=direct_cost,
                shared_service_apportioned_cost=shared_cost,
                unallocated_cost=unalloc_amt,
                cost_basis="BILLED",
                currency="USD",
                budget_amount=round_currency(total_allocated * Decimal("1.08")),
                budget_variance_amount=round_currency(total_allocated * Decimal("-0.08")),
                budget_variance_pct=Decimal("-7.41"),
                budget_status=BudgetVarianceStatus.ON_TRACK,
                budget_commentary=f"Spend is within allocated budget for {scope_name}.",
                prior_period="2026-08" if period == "2026-09" else "2026-07",
                prior_period_cost=round_currency(total_allocated * Decimal("0.95")),
                period_movement_amount=round_currency(total_allocated * Decimal("0.05")),
                period_movement_pct=Decimal("5.26"),
                movement_direction=MovementDirection.UP,
                movement_commentary="Moderate organic usage expansion.",
                provider_breakdown=[
                    ProviderBreakdownItem(
                        provider="AWS",
                        allocated_amount=round_currency(total_allocated * Decimal("0.70")),
                        share_percentage=Decimal("70.00"),
                    ),
                    ProviderBreakdownItem(
                        provider="AZURE",
                        allocated_amount=round_currency(total_allocated * Decimal("0.30")),
                        share_percentage=Decimal("30.00"),
                    ),
                ],
                category_breakdown=[
                    CategoryBreakdownItem(
                        service_category="Compute",
                        allocated_amount=round_currency(total_allocated * Decimal("0.60")),
                        share_percentage=Decimal("60.00"),
                    ),
                    CategoryBreakdownItem(
                        service_category="Storage",
                        allocated_amount=round_currency(total_allocated * Decimal("0.40")),
                        share_percentage=Decimal("40.00"),
                    ),
                ],
                application_breakdown=[
                    ApplicationBreakdownItem(
                        application_code="APP-CORE",
                        application_name="Core Services",
                        allocated_amount=total_allocated,
                        share_percentage=Decimal("100.00"),
                    )
                ],
                environment_breakdown=[
                    EnvironmentBreakdownItem(
                        environment="PROD",
                        allocated_amount=round_currency(total_allocated * Decimal("0.85")),
                        share_percentage=Decimal("85.00"),
                    ),
                    EnvironmentBreakdownItem(
                        environment="NON-PROD",
                        allocated_amount=round_currency(total_allocated * Decimal("0.15")),
                        share_percentage=Decimal("15.00"),
                    ),
                ],
                largest_movements=[
                    CostMovementItem(
                        item_name="Compute Instances",
                        prior_amount=round_currency(total_allocated * Decimal("0.55")),
                        current_amount=round_currency(total_allocated * Decimal("0.60")),
                        delta_amount=round_currency(total_allocated * Decimal("0.05")),
                        delta_pct=Decimal("9.1"),
                        movement_direction=MovementDirection.UP,
                        narrative_explanation="Expanded auto-scaling pool for end-of-quarter volume.",
                    )
                ],
                shared_service_apportionments=[
                    SharedServiceApportionmentItem(
                        shared_service_id="svc-shared-k8s",
                        shared_service_name="Shared Kubernetes Cluster Ingress",
                        provider="AWS",
                        source_total_cost=Decimal("45000.00"),
                        apportioned_amount=shared_cost,
                        apportionment_percentage=Decimal("8.50"),
                        allocation_rule_id="RULE-SPLIT-K8S-01",
                        allocation_rule_name="K8s CPU Core Request Pro-Rata Split",
                        apportionment_basis="Pro-rata share of measured CPU core requests (8.50% allocation)",
                    )
                ],
                unallocated_cost_details=UnallocatedCostItem(
                    unallocated_amount=unalloc_amt,
                    unallocated_percentage=Decimal("4.20"),
                    reasons=[
                        {
                            "code": "MISSING_TAG",
                            "description": "Lacks CostCentre tag on legacy storage",
                        }
                    ],
                )
                if has_unallocated
                else None,
                discount_benefit=DiscountBenefitItem(
                    list_cost=round_currency(total_allocated * Decimal("1.18")),
                    contracted_cost=round_currency(total_allocated * Decimal("1.08")),
                    effective_cost=total_allocated,
                    realised_discount_amount=round_currency(total_allocated * Decimal("0.18")),
                    realised_discount_percentage=Decimal("15.25"),
                ),
            )
            return stmt

        # Period 2026-08 (Historical baseline)
        s_ret_08 = make_statement(
            "stmt-retail-2026-08",
            "BU-RETAIL",
            "Retail Banking",
            "2026-08",
            Decimal("80900.00"),
            Decimal("7500.00"),
            StatementLifecycleStatus.FINALISED,
        )
        # Period 2026-08 Restatement version 2 showing visible retroactive discount adjustment
        s_ret_08_restated = make_statement(
            "stmt-retail-2026-08-v2",
            "BU-RETAIL",
            "Retail Banking",
            "2026-08",
            Decimal("79650.00"),
            Decimal("7500.00"),
            StatementLifecycleStatus.ADJUSTED,
            is_adjustment=True,
            supersedes_id="stmt-retail-2026-08",
        )
        s_com_08 = make_statement(
            "stmt-comm-2026-08",
            "BU-COMMERCIAL",
            "Commercial Lending",
            "2026-08",
            Decimal("56800.00"),
            Decimal("5200.00"),
            StatementLifecycleStatus.ACCEPTED,
        )
        s_dig_08 = make_statement(
            "stmt-dig-2026-08",
            "BU-DIGITAL",
            "Digital Channels",
            "2026-08",
            Decimal("49200.00"),
            Decimal("4800.00"),
            StatementLifecycleStatus.FINALISED,
        )

        # Period 2026-09 (Current closing period)
        # Retail Banking: DISPUTED with disputed line ($14,200.00 storage)
        s_ret_09 = make_statement(
            "stmt-retail-2026-09",
            "BU-RETAIL",
            "Retail Banking",
            "2026-09",
            Decimal("86100.00"),
            Decimal("8100.00"),
            StatementLifecycleStatus.DISPUTED,
        )
        # Commercial Lending: ACCEPTED
        s_com_09 = make_statement(
            "stmt-comm-2026-09",
            "BU-COMMERCIAL",
            "Commercial Lending",
            "2026-09",
            Decimal("59800.00"),
            Decimal("5600.00"),
            StatementLifecycleStatus.ACCEPTED,
        )
        # Digital Channels: Material unallocated cost ($6,500.00)
        s_dig_09 = make_statement(
            "stmt-dig-2026-09",
            "BU-DIGITAL",
            "Digital Channels",
            "2026-09",
            Decimal("53800.00"),
            Decimal("5100.00"),
            StatementLifecycleStatus.IN_REVIEW,
            has_unallocated=True,
        )

        showback_statements.extend(
            [s_ret_08, s_ret_08_restated, s_com_08, s_dig_08, s_ret_09, s_com_09, s_dig_09]
        )

        # Disputed line on stmt-retail-2026-09 ($14,200.00)
        statement_disputes: list[StatementDispute] = [
            StatementDispute(
                dispute_id="disp-retail-01",
                tenant_id=tenant_id,
                statement_id="stmt-retail-2026-09",
                line_id="line-storage-archive",
                line_description="Amazon S3 Glacier Deep Archive storage fee",
                recipient_id="owner-bu-retail@cloudlens.internal",
                recipient_email="owner-bu-retail@cloudlens.internal",
                disputed_amount=Decimal("14200.00"),
                proposed_amount=Decimal("4200.00"),
                reason="Storage archival charges are pending vendor audit of partner data retention SLA.",
                status=DisputeStatus.IN_REVIEW,
                assigned_owner="finops-analyst@company.com",
                sla_deadline=(now + dt.timedelta(days=7)).isoformat(),
            )
        ]

        # Adjustment record for stmt-retail-2026-08-v2
        statement_adjustments: list[StatementAdjustment] = [
            StatementAdjustment(
                adjustment_id="adj-retail-2026-08-v2",
                tenant_id=tenant_id,
                original_statement_id="stmt-retail-2026-08",
                adjusted_statement_id="stmt-retail-2026-08-v2",
                version=2,
                original_total=Decimal("88400.00"),
                adjustment_total=Decimal("-1250.00"),
                adjusted_total=Decimal("87150.00"),
                restatement_reason="Retroactive AWS Enterprise Discount Program credit reconciliation.",
                adjusted_by="finance-lead@cloudlens.internal",
                lines=[
                    AdjustmentLine(
                        line_id="line-edp-rebate",
                        description="Retroactive EDP tier rebate applied to Compute",
                        original_amount=Decimal("53000.00"),
                        adjustment_delta=Decimal("-1250.00"),
                        adjusted_amount=Decimal("51750.00"),
                        reason="Vendor revised billing ledger applied post-month close.",
                    )
                ],
            )
        ]

        # ----------------------------------------------------------------------
        # 5. Workflow Engine & Approver Inbox (Prompt 50)
        # ----------------------------------------------------------------------
        workflow_requests: list[WorkflowRequest] = []

        wf_types = [
            (
                WorkflowRequestType.BUDGET_APPROVAL.value,
                "wf-req-budget-01",
                "FY27 Digital Channels Budget Ceiling Increase ($125k)",
                125000.0,
                False,
                False,
            ),
            (
                WorkflowRequestType.OVERRIDE_APPROVAL.value,
                "wf-req-override-02",
                "Weekend Shutdown Policy Exemption for DR Rehearsal",
                2500.0,
                False,
                False,
            ),
            (
                WorkflowRequestType.POLICY_EXEMPTION.value,
                "wf-req-exemption-03",
                "Third-Party SaaS Appliance Tagging Exemption",
                0.0,
                False,
                False,
            ),
            (
                WorkflowRequestType.CUSTOM_ROLE_CREATION.value,
                "wf-req-role-04",
                "External Auditor Restricted Financial Viewer Role",
                0.0,
                False,
                False,
            ),
            (
                WorkflowRequestType.MASTER_DATA_CHANGE.value,
                "wf-req-mdm-05",
                "Creation of Wealth Management BU & Cost Centre CC-WM-400",
                0.0,
                False,
                False,
            ),
            (
                WorkflowRequestType.TENANT_LIFECYCLE.value,
                "wf-req-tenant-06",
                "Staging Environment Tier 2 Scale-Up",
                4500.0,
                False,
                False,
            ),
            (
                WorkflowRequestType.PROVISIONING_REQUEST.value,
                "wf-req-prov-07",
                "High-Throughput Analytics Cluster Provisioning ($850/mo)",
                850.0,
                False,
                False,
            ),
            # Escalated for inaction
            (
                WorkflowRequestType.BUDGET_APPROVAL.value,
                "wf-req-escalated-08",
                "Emergency Core Banking Budget Buffer (Escalated)",
                75000.0,
                True,
                False,
            ),
            # Handled by a delegate
            (
                WorkflowRequestType.POLICY_EXEMPTION.value,
                "wf-req-delegated-09",
                "Temporary Legacy Firewall Rule Retention (Delegated)",
                1200.0,
                False,
                True,
            ),
        ]

        for req_type, req_id, title, impact, is_esc, is_del in wf_types:
            decisions = []
            if is_del:
                decisions.append(
                    WorkflowDecision(
                        decision_id=f"dec-{req_id}",
                        stage_id="stage-review",
                        decided_by="user-delegate-jane@cloudlens.internal",
                        decision=DecisionOutcome.APPROVE,
                        comment="Approved on behalf of primary approver (Out of Office delegation).",
                        on_behalf_of="user-finops-admin@cloudlens.internal",
                        timestamp=(now - dt.timedelta(hours=4)),
                    )
                )

            wf = WorkflowRequest(
                id=req_id,
                tenant_id=tenant_id,
                request_type=req_type,
                title=title,
                requester=RequesterInfo(
                    requester_id="user-eng-lead@cloudlens.internal",
                    requester_name="Alex River (Lead FinOps Engineer)",
                    requester_email="eng-lead@cloudlens.internal",
                ),
                subject_entity=WorkflowSubjectEntity(
                    entity_type="governance_request",
                    entity_id=f"ent-{req_id}",
                    scope_type="BUSINESS_UNIT",
                    scope_id="BU-RETAIL",
                ),
                justification=f"Formal business justification for {title}.",
                payload={"financial_impact": impact, "requested_type": req_type},
                financial_impact=impact,
                state=WorkflowState.IN_REVIEW if not is_del else WorkflowState.APPROVED,
                current_stage_index=0,
                stages=[
                    WorkflowStage(
                        stage_id="stage-review",
                        name="FinOps & Scope Owner Evaluation Stage",
                        sequence_order=1,
                        mode=ApprovalChainMode.SERIAL,
                        quorum=1,
                        assigned_approvers=[
                            "user-finops-admin@cloudlens.internal"
                            if not is_del
                            else "user-delegate-jane@cloudlens.internal"
                        ],
                        status="IN_REVIEW" if not is_del else "APPROVED",
                        decisions=decisions,
                    )
                ],
                is_escalated=is_esc,
                history=[
                    WorkflowHistoryEntry(
                        actor_id="system",
                        action="SUBMITTED",
                        new_state=WorkflowState.SUBMITTED,
                    )
                ],
            )
            if is_esc:
                wf.add_history(
                    actor_id="system-sla-engine",
                    action="ESCALATE",
                    new_state=WorkflowState.IN_REVIEW,
                    details={
                        "escalated_to": "FINANCE_DIRECTOR",
                        "reason": "SLA working-hours threshold elapsed without review",
                    },
                )
            workflow_requests.append(wf)

        # ----------------------------------------------------------------------
        # 6. Forward Demo Estates: Commitments, Planning, Extracts, Gaps, Imports
        # ----------------------------------------------------------------------
        commitments = [
            # 6a. Over-committed (Low utilisation)
            CommitmentPortfolioItem(
                commitment_id="comm-aws-sp-over-01",
                provider="AWS",
                name="3-Year Compute Savings Plan (Analytics)",
                commitment_type=CommitmentType.SAVINGS_PLAN,
                term_months=36,
                hourly_committed_rate=Decimal("120.00"),
                monthly_commitment=Decimal("87600.00"),
                current_coverage_pct=Decimal("94.5"),
                current_utilisation_pct=Decimal("52.3"),  # 52% utilisation -> Wasted spend
                start_date="2024-01-01",
                end_date="2027-01-01",
                days_to_expiry=462,
                status=CommitmentStatus.ACTIVE,
                is_over_committed=True,
                notes="Over-committed: compute spend scaled down leaving 47.7% unused hourly commitment.",
            ),
            # 6b. Under-committed (Low coverage)
            CommitmentPortfolioItem(
                commitment_id="comm-gcp-cud-under-02",
                provider="GCP",
                name="1-Year Committed Use Discount (Database)",
                commitment_type=CommitmentType.COMMITTED_USE_DISCOUNT,
                term_months=12,
                hourly_committed_rate=Decimal("35.00"),
                monthly_commitment=Decimal("25550.00"),
                current_coverage_pct=Decimal("35.0"),  # Only 35% covered -> Opportunity for savings
                current_utilisation_pct=Decimal("99.4"),
                start_date="2026-03-01",
                end_date="2027-03-01",
                days_to_expiry=156,
                status=CommitmentStatus.ACTIVE,
                is_under_committed=True,
                notes="Under-committed: 65% of database workload running on expensive on-demand rates.",
            ),
            # 6c. Renewal Window Item 1 (Expiring in 18 days)
            CommitmentPortfolioItem(
                commitment_id="comm-aws-ri-renewal-03",
                provider="AWS",
                name="3-Year Standard Reserved Instances (Core Web)",
                commitment_type=CommitmentType.RESERVED_INSTANCE,
                term_months=36,
                hourly_committed_rate=Decimal("50.00"),
                monthly_commitment=Decimal("36500.00"),
                current_coverage_pct=Decimal("88.0"),
                current_utilisation_pct=Decimal("96.5"),
                start_date="2023-10-15",
                end_date=(now + dt.timedelta(days=18)).strftime("%Y-%m-%d"),
                days_to_expiry=18,
                status=CommitmentStatus.EXPIRING_SOON,
                in_renewal_window=True,
                notes="Expiring in 18 days. Urgent renewal decision required to avoid rate doubling.",
            ),
            # 6d. Renewal Window Item 2 (Expiring in 27 days)
            CommitmentPortfolioItem(
                commitment_id="comm-az-sp-renewal-04",
                provider="AZURE",
                name="1-Year Azure Compute Savings Plan",
                commitment_type=CommitmentType.SAVINGS_PLAN,
                term_months=12,
                hourly_committed_rate=Decimal("42.00"),
                monthly_commitment=Decimal("30660.00"),
                current_coverage_pct=Decimal("78.2"),
                current_utilisation_pct=Decimal("94.1"),
                start_date="2025-10-23",
                end_date=(now + dt.timedelta(days=27)).strftime("%Y-%m-%d"),
                days_to_expiry=27,
                status=CommitmentStatus.EXPIRING_SOON,
                in_renewal_window=True,
                notes="Expiring in 27 days. Renewal evaluation in progress with Finance.",
            ),
        ]

        # 6e. Budget Planning Cycle (Prompt 57)
        budget_planning = BudgetPlanningCycle(
            cycle_id="plan-fy2027-cycle",
            cycle_name="FY2027 Annual Enterprise Cloud Budget Plan",
            fiscal_year="2027",
            status="OPEN",
            top_down_target=Decimal("5000000.00"),
            total_submitted=Decimal("4200000.00"),
            planning_gap=Decimal("800000.00"),  # $800k gap
            submissions=[
                BudgetPlanningSubmission(
                    business_unit_id="BU-RETAIL",
                    business_unit_name="Retail Banking",
                    submitted_amount=Decimal("1850000.00"),
                    submitted_by="cfo-retail@cloudlens.internal",
                    submitted_at=(now - dt.timedelta(days=10)).isoformat(),
                ),
                BudgetPlanningSubmission(
                    business_unit_id="BU-COMMERCIAL",
                    business_unit_name="Commercial Lending",
                    submitted_amount=Decimal("1200000.00"),
                    submitted_by="cfo-commercial@cloudlens.internal",
                    submitted_at=(now - dt.timedelta(days=6)).isoformat(),
                ),
                BudgetPlanningSubmission(
                    business_unit_id="BU-DIGITAL",
                    business_unit_name="Digital Channels",
                    submitted_amount=Decimal("1150000.00"),
                    submitted_by="cfo-digital@cloudlens.internal",
                    submitted_at=(now - dt.timedelta(days=2)).isoformat(),
                ),
            ],
            notes="Open planning cycle: 3 of 4 business units submitted, visible $800k variance gap.",
        )

        # 6f. Analytical Extract Run History (Prompt 56)
        analytical_extracts = [
            AnalyticalExtractRun(
                run_id="extract-run-2026-09-24",
                period="2026-09",
                format="PARQUET",
                destination_uri="s3://cloudlens-analytics-feed-prod/focus/2026-09/data.parquet",
                status=AnalyticalExtractRunStatus.COMPLETED,
                row_count=142500,
                file_size_mb=Decimal("48.2"),
                started_at=(now - dt.timedelta(days=2, hours=1)).isoformat(),
                completed_at=(now - dt.timedelta(days=2)).isoformat(),
            ),
            AnalyticalExtractRun(
                run_id="extract-run-2026-09-25",
                period="2026-09",
                format="PARQUET",
                destination_uri="s3://cloudlens-analytics-feed-prod/focus/2026-09/data-v2.parquet",
                status=AnalyticalExtractRunStatus.DELAYED,
                row_count=0,
                file_size_mb=Decimal("0.0"),
                started_at=(now - dt.timedelta(days=1, hours=3)).isoformat(),
                delay_reason="Upstream billing provider restatement file pending verification.",
            ),
            AnalyticalExtractRun(
                run_id="extract-run-2026-09-26-empty",
                period="2026-09",
                format="PARQUET",
                destination_uri="s3://cloudlens-analytics-feed-prod/focus/2026-09/empty-test.parquet",
                status=AnalyticalExtractRunStatus.EMPTY,
                row_count=0,
                file_size_mb=Decimal("0.0"),
                started_at=(now - dt.timedelta(hours=2)).isoformat(),
                completed_at=(now - dt.timedelta(hours=1)).isoformat(),
                delay_reason="Zero metered records found for target partition.",
            ),
            AnalyticalExtractRun(
                run_id="extract-run-2026-08-31",
                period="2026-08",
                format="PARQUET",
                destination_uri="s3://cloudlens-analytics-feed-prod/focus/2026-08/data.parquet",
                status=AnalyticalExtractRunStatus.COMPLETED,
                row_count=138000,
                file_size_mb=Decimal("46.5"),
                started_at=(now - dt.timedelta(days=26)).isoformat(),
                completed_at=(now - dt.timedelta(days=26, hours=-1)).isoformat(),
                delay_reason=None,
            ),
        ]

        # 6g. Master Data Gap Items (Prompt 45/46)
        master_data_gaps = [
            MasterDataGapItem(
                gap_id="gap-tag-01",
                entity_type="RESOURCE_TAG",
                key_identifier="CostCenter",
                gap_type="UNMAPPED_TAG",
                severity="HIGH",
                suggested_action="Map tag value 'CC-FIN-99' to financial Cost Centre CC-FINANCE-CORP.",
                detected_at=(now - dt.timedelta(days=3)).isoformat(),
            ),
            MasterDataGapItem(
                gap_id="gap-cc-02",
                entity_type="APPLICATION",
                key_identifier="APP-PORTAL-V1",
                gap_type="MISSING_COST_CENTRE",
                severity="MEDIUM",
                suggested_action="Assign responsible Cost Centre code to application record.",
                detected_at=(now - dt.timedelta(days=5)).isoformat(),
            ),
            MasterDataGapItem(
                gap_id="gap-sku-03",
                entity_type="PRICING_CATALOGUE",
                key_identifier="SKU-OCI-CUSTOM-IOPS",
                gap_type="UNCLASSIFIED_SKU",
                severity="LOW",
                suggested_action="Classify uncatalogued rate card SKU under Storage category.",
                detected_at=(now - dt.timedelta(days=7)).isoformat(),
            ),
        ]

        # 6h. Bulk Import Job Summaries (Prompt 53)
        import_jobs = [
            BulkImportJobSummary(
                job_id="job-imp-01-applied",
                source_filename="enterprise-tag-overrides-202609.csv",
                is_dry_run=False,
                total_rows=1500,
                successful_rows=1498,
                error_rows=2,
                executed_at=(now - dt.timedelta(days=4)).isoformat(),
                executed_by="admin@cloudlens.internal",
                status="APPLIED",
            ),
            BulkImportJobSummary(
                job_id="job-imp-02-dryrun",
                source_filename="org-hierarchy-restructure-draft.csv",
                is_dry_run=True,
                total_rows=450,
                successful_rows=445,
                error_rows=5,
                executed_at=(now - dt.timedelta(days=1)).isoformat(),
                executed_by="admin@cloudlens.internal",
                status="DRY_RUN_VALIDATED",
            ),
        ]

        return GovernanceMockEstateResult(
            tenant_id=tenant_id,
            seed=self.seed,
            generated_at=now_iso,
            quotas=[q.model_dump() for q in quotas],
            quota_remediation_tasks=[t.model_dump() for t in quota_tasks],
            saved_estimates=[e.model_dump() for e in saved_estimates],
            provisioning_requests=[r.model_dump() for r in provisioning_requests],
            estimate_actual_trackings=[t.model_dump() for t in trackings],
            unapproved_findings=[f.model_dump() for f in unapproved_findings],
            remediation_tasks=[t.model_dump() for t in remediation_tasks],
            false_resolved_task_id="task-demo-false-resolved",
            showback_statements=[s.model_dump(mode="json") for s in showback_statements],
            statement_adjustments=[a.model_dump(mode="json") for a in statement_adjustments],
            statement_disputes=[d.model_dump(mode="json") for d in statement_disputes],
            disputed_line_statement_id="stmt-retail-2026-09",
            restated_statement_id="stmt-retail-2026-08-v2",
            workflow_requests=[w.model_dump() for w in workflow_requests],
            escalated_request_id="wf-req-escalated-08",
            delegated_request_id="wf-req-delegated-09",
            commitments=commitments,
            budget_planning=budget_planning,
            analytical_extract_runs=analytical_extracts,
            master_data_gaps=master_data_gaps,
            import_jobs=import_jobs,
        )

    def seed_repositories(
        self,
        tenant_id: str,
        gov_estate: GovernanceMockEstateResult,
    ) -> None:
        """Injects generated governance mock data directly into active domain repositories."""
        tc = TenantContext(tenant_id=tenant_id, user_id="system-demo-seed", roles=["SUPER_ADMIN"])

        # 1. Quotas Repository
        q_repo = get_quota_repository()
        for q_dict in gov_estate.quotas:
            q_ent = QuotaEntity(**q_dict)
            q_repo.save(q_ent, tenant_context=tc)

        for qt_dict in gov_estate.quota_remediation_tasks:
            qt_ent = QuotaRemediationTask(**qt_dict)
            q_repo.save_remediation_task(qt_ent, tenant_context=tc)

        # 2. Provisioning Repository
        pr_repo = get_provisioning_repository()
        for est_dict in gov_estate.saved_estimates:
            est = SavedEstimate(**est_dict)
            pr_repo.save_estimate(est)

        for pr_dict in gov_estate.provisioning_requests:
            pr = ProvisioningRequest(**pr_dict)
            pr_repo.save_request(pr)

        for tr_dict in gov_estate.estimate_actual_trackings:
            tr = EstimateVsActualTracking(**tr_dict)
            pr_repo.save_tracking(tenant_id, tr)

        for f_dict in gov_estate.unapproved_findings:
            f = UnapprovedDeploymentFinding(**f_dict)
            pr_repo.save_finding(tenant_id, f)

        # 3. Remediation Repository
        rem_repo = get_remediation_repository()
        for rem_dict in gov_estate.remediation_tasks:
            rem = RemediationTask(**rem_dict)
            rem_repo.save(rem, tenant_context=tc)

        # 4. Statements Repository
        stmt_repo = get_statement_repository()
        for s_dict in gov_estate.showback_statements:
            s = ShowbackStatement(**s_dict)
            stmt_repo.save_statement(s, tenant_context=tc)

        for a_dict in gov_estate.statement_adjustments:
            a = StatementAdjustment(**a_dict)
            stmt_repo.save_adjustment(a, tenant_context=tc)

        for d_dict in gov_estate.statement_disputes:
            d = StatementDispute(**d_dict)
            stmt_repo.save_dispute(d, tenant_context=tc)

        # 5. Workflows Repository
        wf_repo = get_workflow_repository()
        for wf_dict in gov_estate.workflow_requests:
            wf = WorkflowRequest(**wf_dict)
            wf_repo.save(wf, tenant_context=tc)

        logger.info(
            "Seeded governance mock estate into repositories for tenant '%s': "
            "%d quotas, %d provisioning requests, %d tasks, %d statements, %d workflows.",
            tenant_id,
            len(gov_estate.quotas),
            len(gov_estate.provisioning_requests),
            len(gov_estate.remediation_tasks),
            len(gov_estate.showback_statements),
            len(gov_estate.workflow_requests),
        )
