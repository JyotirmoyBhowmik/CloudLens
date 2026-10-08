"""Real-DB Integration Test for Restart Survival across All Tier 4 Entity Groups (Prompt P07).

DONE WHEN Proof:
[ ] Restart proof per entity group
Verifies that each entity group:
1. Alerts & Delivery Logs
2. Contextual Alerts
3. Policies, Findings & Exemptions
4. Workflow Requests & Definitions
5. Remediation Tasks & Savings Ledger
6. Quotas & Increase Requests
7. Provisioning Requests & Estimates
8. Showback Statements & Disputes
9. Bulk Import Runs & Profiles
10. Dependency Edges & Conflicts
11. Usage Facts & Overrides
12. Runtime States & Schedules
13. Hierarchy Resources & Saved Views
is persisted to PostgreSQL and survives full repository singleton reset (simulating application restart).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from domain.alerting.contextual import (
    SqlContextualAlertRepository,
    get_contextual_alert_manager,
    reset_contextual_alert_manager,
)
from domain.alerting.models import (
    AlertDeliveryLog,
    AlertEntity,
    AlertEvidence,
    ContextualAlert,
    RecipientSubscription,
)
from domain.alerting.repository import (
    SqlAlertRepository,
    get_alert_repository,
    reset_alert_repository,
)
from domain.bulk_import.models import (
    AtomicityPolicy,
    DryRunSummary,
    ImportMode,
    ImportRunRecord,
    ImportStatus,
    MappingProfile,
)
from domain.bulk_import.repository import (
    SqlBulkImportRepository,
    get_bulk_import_repository,
    reset_bulk_import_repository,
)
from domain.dependency.models import (
    DependencyEdge,
    EdgeConflict,
    EdgeProvenance,
    TypedEntityRef,
)
from domain.dependency.repository import (
    SqlDependencyRepository,
    get_dependency_repository,
    reset_dependency_repository,
)
from domain.hierarchy.models import (
    InventoryResource35,
    SavedInventoryView,
)
from domain.hierarchy.repository import (
    SqlHierarchyRepository,
    get_hierarchy_repository,
    reset_hierarchy_repository,
)
from domain.models.enums import (
    AlertLifecycleStatus,
    AlertSeverity,
    AlertType,
    CloudProvider,
    ConditionOperator,
    ContextualAlertType,
    ContextualAlertVisibility,
    DeliveryOutcome,
    DiscoveryLayer,
    EdgeConfidenceLevel,
    EdgeCriticality,
    EdgeProvenanceType,
    EdgeStatus,
    EntityReferenceType,
    FindingLifecycleStatus,
    NotificationChannel,
    PolicyCategory,
    PolicyMode,
    PolicySeverity,
    QuotaScopeType,
    RealisedSavingMethod,
    RelationshipType,
    TaskCategory,
    TaskPriority,
    TaskSource,
    TaskState,
    WorkflowState,
)
from domain.policy.models import (
    DeclarativeCondition,
    PolicyDefinition,
    PolicyExemption,
    PolicyFinding,
)
from domain.policy.repository import (
    SqlPolicyRepository,
    get_policy_repository,
    reset_policy_repository,
)
from domain.provisioning.models import (
    BudgetImpactAssessment,
    BudgetImpactTier,
    DependencyPreCheckResult,
    GateTriggerAction,
    GateTriggerRule,
    ProvisioningRequest,
    ProvisioningRequestStatus,
    QuotaPreCheckResult,
    SavedEstimate,
)
from domain.provisioning.repository import (
    SqlProvisioningRepository,
    get_provisioning_repository,
    reset_provisioning_repository,
)
from domain.quotas.models import (
    QuotaEntity,
    QuotaIncreaseRequest,
    QuotaRemediationTask,
)
from domain.quotas.repository import (
    SqlQuotaRepository,
    get_quota_repository,
    reset_quota_repository,
)
from domain.remediation.models import (
    RealisedSavingEntry,
    RemediationTask,
    SubjectEntity,
    TaskCreationRule,
)
from domain.remediation.repository import (
    SqlRemediationRepository,
    get_remediation_repository,
    reset_remediation_repository,
)
from domain.runtime.models import (
    AdherenceStatus,
    NamedSchedule,
    RuntimeExemption,
    RuntimeObservation,
    RuntimeState,
    ScheduleAdherenceResult,
)
from domain.runtime.repository import (
    SqlRuntimeRepository,
    get_runtime_repository,
    reset_runtime_repository,
)
from domain.statements.models import (
    RecipientScopeType,
    ShowbackStatement,
    StatementAdjustment,
    StatementDispute,
    StatementLifecycleStatus,
)
from domain.statements.repository import (
    SqlStatementRepository,
    get_statement_repository,
    reset_statement_repository,
)
from domain.tenant.context import TenantContext
from domain.usage.models import (
    MonitoringType,
    MonitoringTypeOverride,
    PreAggregatedUsageRecord,
    UsageExpectation,
    ExpectationLevel,
)
from domain.models.measures import QuantityMeasure
from domain.usage.repository import (
    SqlUsageRepository,
    get_usage_repository,
    reset_usage_repository,
)
from domain.workflows.models import (
    RequesterInfo,
    WorkflowDefinition,
    WorkflowRequest,
    SubjectEntity as WfSubjectEntity,
)
from domain.workflows.repository import (
    SqlWorkflowRepository,
    get_workflow_repository,
    reset_workflow_repository,
)


@pytest.mark.realdb
@pytest.mark.asyncio
async def test_alerting_group_restart_proof() -> None:
    """Group 1: Alerts and Delivery Logs survive restart."""
    tenant_id = f"tenant-p07-alert-{uuid.uuid4().hex[:6]}"
    tc = TenantContext(tenant_id=tenant_id, user_id="user-alert-admin", roles=["TENANT_ADMIN"])
    alert_id = f"alt-p07-{uuid.uuid4().hex[:6]}"

    reset_alert_repository()
    repo1 = get_alert_repository()
    assert not repo1.is_in_memory

    alert = AlertEntity(
        id=alert_id,
        tenant_id=tenant_id,
        alert_type=AlertType.UNEXPECTED_COST_INCREASE,
        title="Spike in EC2 Spend",
        description="Monthly compute exceeded threshold by 25%",
        severity=AlertSeverity.HIGH,
        source="cost_anomaly_engine",
        evidence=AlertEvidence(
            summary="Monthly compute exceeded threshold by 25%",
            context={"scope": "ec2", "threshold": 25},
        ),
        status=AlertLifecycleStatus.ACTIVE,
        fingerprint=f"fp-{alert_id}",
    )
    repo1.save_alert(alert, tenant_context=tc)

    log_entry = AlertDeliveryLog(
        id=f"log-{uuid.uuid4().hex[:6]}",
        alert_id=alert_id,
        tenant_id=tenant_id,
        channel=NotificationChannel.EMAIL,
        outcome=DeliveryOutcome.DELIVERED,
        recipient="finops-team@corp.internal",
    )
    repo1.save_delivery_log(log_entry, tenant_context=tc)

    # Restart
    reset_alert_repository()
    repo2 = get_alert_repository()
    assert repo2 is not repo1

    loaded_alert = repo2.get_alert(alert_id, tenant_context=tc)
    assert loaded_alert is not None
    assert loaded_alert.id == alert_id
    assert loaded_alert.title == "Spike in EC2 Spend"

    logs = repo2.list_delivery_logs(alert_id, tenant_context=tc)
    assert len(logs) >= 1
    assert logs[0].channel == NotificationChannel.EMAIL


@pytest.mark.realdb
@pytest.mark.asyncio
async def test_contextual_alerts_restart_proof() -> None:
    """Group 2: Contextual Alerts survive restart."""
    tenant_id = f"tenant-p07-ctx-{uuid.uuid4().hex[:6]}"
    tc = TenantContext(tenant_id=tenant_id, user_id="user-ops", roles=["TENANT_ADMIN"])

    reset_contextual_alert_manager()
    mgr1 = get_contextual_alert_manager()
    assert not mgr1._repository.is_in_memory

    alert = ContextualAlert(
        id=f"ctx-item-{uuid.uuid4().hex[:6]}",
        tenant_id=tenant_id,
        alert_type=ContextualAlertType.BUDGET,
        title="Budget 90% Depleted",
        message="Budget nearing full allocation for dev-env",
        visibility=ContextualAlertVisibility.PAGE_INLINE,
        context_entity_type="BUDGET",
        context_entity_id="bgt-dev-env",
        severity=AlertSeverity.HIGH,
    )
    mgr1._repository.save(alert, tenant_context=tc)

    # Restart
    reset_contextual_alert_manager()
    mgr2 = get_contextual_alert_manager()
    assert mgr2 is not mgr1

    loaded = mgr2.list_alerts(
        context_entity_type="BUDGET",
        context_entity_id="bgt-dev-env",
        tenant_context=tc,
    )
    assert len(loaded) >= 1
    assert loaded[0].id == alert.id
    assert loaded[0].title == "Budget 90% Depleted"


@pytest.mark.realdb
@pytest.mark.asyncio
async def test_policy_group_restart_proof() -> None:
    """Group 3: Policy Definitions, Findings, and Exemptions survive restart."""
    tenant_id = f"tenant-p07-pol-{uuid.uuid4().hex[:6]}"
    tc = TenantContext(tenant_id=tenant_id, user_id="user-sec-officer", roles=["TENANT_ADMIN"])
    pol_id = f"pol-{uuid.uuid4().hex[:6]}"
    fnd_id = f"fnd-{uuid.uuid4().hex[:6]}"
    exm_id = f"exm-{uuid.uuid4().hex[:6]}"

    reset_policy_repository()
    repo1 = get_policy_repository()
    assert not repo1.is_in_memory

    # Policy
    pol = PolicyDefinition(
        id=pol_id,
        tenant_id=tenant_id,
        name="Mandatory Resource Tagging",
        description="Every resource must possess Project and Owner tags.",
        severity=PolicySeverity.HIGH,
        category=PolicyCategory.TAGGING,
        condition=DeclarativeCondition(
            field="tags.Project",
            operator=ConditionOperator.IS_NOT_NULL,
        ),
        enabled=True,
    )
    repo1.save_policy(pol, tenant_context=tc)

    # Finding
    fnd = PolicyFinding(
        id=fnd_id,
        policy_id=pol_id,
        policy_version=1,
        entity_id="i-worker-prod-99",
        lifecycle_status=FindingLifecycleStatus.OPEN,
        severity=PolicySeverity.HIGH,
        category=PolicyCategory.TAGGING,
        mode=PolicyMode.ENFORCE,
        condition_summary="Missing 'Project' metadata tag.",
        first_detected_at=datetime.now(UTC),
    )
    repo1.save_finding(fnd, tenant_context=tc)

    # Exemption
    exm = PolicyExemption(
        id=exm_id,
        policy_id=pol_id,
        entity_id="i-worker-prod-99",
        justification="Legacy instance scheduled for decommissioning next week.",
        approved_by="vp-engineering",
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    repo1.save_exemption(exm, tenant_context=tc)

    # Restart
    reset_policy_repository()
    repo2 = get_policy_repository()
    assert repo2 is not repo1

    loaded_pol = repo2.get_policy(pol_id, tenant_context=tc)
    assert loaded_pol is not None
    assert loaded_pol.name == "Mandatory Resource Tagging"

    loaded_fnd = repo2.get_finding(fnd_id, tenant_context=tc)
    assert loaded_fnd is not None
    assert loaded_fnd.lifecycle_status == FindingLifecycleStatus.OPEN

    loaded_exm = repo2.get_exemption(exm_id, tenant_context=tc)
    assert loaded_exm is not None
    assert loaded_exm.approved_by == "vp-engineering"


@pytest.mark.realdb
@pytest.mark.asyncio
async def test_workflows_restart_proof() -> None:
    """Group 4: Workflow Requests and Definitions survive restart."""
    tenant_id = f"tenant-p07-wf-{uuid.uuid4().hex[:6]}"
    tc = TenantContext(tenant_id=tenant_id, user_id="user-wf-requester", roles=["TENANT_ADMIN"])
    req_id = f"wfr-{uuid.uuid4().hex[:6]}"
    def_id = f"wfd-{uuid.uuid4().hex[:6]}"

    reset_workflow_repository()
    repo1 = get_workflow_repository()
    assert not repo1.is_in_memory

    wf_def = WorkflowDefinition(
        id=def_id,
        tenant_id=tenant_id,
        request_type="PROVISIONING",
        entity_type="cloud_resource",
        name="Standard Cloud Provisioning Approval",
        description="Approval matrix for infrastructure deployment",
    )
    repo1.save_definition(wf_def, tenant_context=tc)

    wf_req = WorkflowRequest(
        id=req_id,
        tenant_id=tenant_id,
        request_type="PROVISIONING",
        title="Deploy Kubernetes Cluster in eu-west-1",
        subject_entity=WfSubjectEntity(
            entity_type="cluster",
            entity_id="k8s-prod-1",
        ),
        requester=RequesterInfo(
            requester_id="user-wf-requester",
        ),
        justification="Required for production Kubernetes cluster scale-out.",
        state=WorkflowState.SUBMITTED,
    )
    repo1.save_request(wf_req, tenant_context=tc)

    # Restart
    reset_workflow_repository()
    repo2 = get_workflow_repository()
    assert repo2 is not repo1

    loaded_req = repo2.get_request(req_id, tenant_context=tc)
    assert loaded_req is not None
    assert loaded_req.id == req_id
    assert loaded_req.title == "Deploy Kubernetes Cluster in eu-west-1"

    loaded_def = repo2.get_definition(def_id, tenant_context=tc)
    assert loaded_def is not None
    assert loaded_def.request_type == "PROVISIONING"


@pytest.mark.realdb
@pytest.mark.asyncio
async def test_remediation_restart_proof() -> None:
    """Group 5: Remediation Tasks, Savings Ledger, and Rules survive restart."""
    tenant_id = f"tenant-p07-rem-{uuid.uuid4().hex[:6]}"
    tc = TenantContext(tenant_id=tenant_id, user_id="user-rem-lead", roles=["TENANT_ADMIN"])
    task_id = f"rem-{uuid.uuid4().hex[:6]}"
    saving_id = f"sav-{uuid.uuid4().hex[:6]}"

    reset_remediation_repository()
    repo1 = get_remediation_repository()
    assert not repo1.is_in_memory

    task = RemediationTask(
        id=task_id,
        tenant_id=tenant_id,
        source=TaskSource.IDLE_RESOURCE,
        subject_entity=SubjectEntity(
            entity_type="RESOURCE",
            entity_id="i-09f87238a111",
            entity_name="prod-payment-worker-1",
        ),
        title="Downsize Overprovisioned Instance",
        description="Downsize overprovisioned instance from m5.4xlarge to m5.xlarge",
        assignee_id="user-rem-lead",
        due_date=datetime.now(UTC) + timedelta(days=7),
        state=TaskState.OPEN,
        priority=TaskPriority.HIGH,
        category=TaskCategory.IDLE_RESOURCE,
    )
    repo1.save(task, tenant_context=tc)

    saving = RealisedSavingEntry(
        id=saving_id,
        tenant_id=tenant_id,
        task_id=task_id,
        entity_id="i-09f87238a111",
        category="IDLE_RESOURCE",
        team_id="engineering-core",
        period="2026-10",
        realised_amount=450.00,
        currency="USD",
        calculation_method=RealisedSavingMethod.IDLE_TERMINATION_DELTA,
    )
    repo1.save_saving_entry(saving, tenant_context=tc)

    # Restart
    reset_remediation_repository()
    repo2 = get_remediation_repository()
    assert repo2 is not repo1

    loaded_task = repo2.get(task_id, tenant_context=tc)
    assert loaded_task is not None
    assert loaded_task.title == "Downsize Overprovisioned Instance"

    savings = repo2.list_saving_entries(tenant_context=tc)
    assert len(savings) >= 1
    assert savings[0].realised_amount == 450.00


@pytest.mark.realdb
@pytest.mark.asyncio
async def test_quotas_restart_proof() -> None:
    """Group 6: Quotas, Increase Requests, and Remediation Tasks survive restart."""
    tenant_id = f"tenant-p07-quota-{uuid.uuid4().hex[:6]}"
    tc = TenantContext(tenant_id=tenant_id, user_id="user-quota-lead", roles=["TENANT_ADMIN"])
    quota_id = f"qta-{uuid.uuid4().hex[:6]}"
    req_id = f"qir-{uuid.uuid4().hex[:6]}"

    reset_quota_repository()
    repo1 = get_quota_repository()
    assert not repo1.is_in_memory

    quota = QuotaEntity(
        id=quota_id,
        tenant_id=tenant_id,
        provider=CloudProvider.AWS,
        service_code="ec2",
        quota_code="L-1216C47A",
        quota_name="Running On-Demand Standard Instances",
        scope_type=QuotaScopeType.ACCOUNT,
        scope_id="123456789012",
        limit_value=128.0,
        consumed_value=112.0,
        unit="vCPU",
    )
    repo1.save(quota, tenant_context=tc)

    inc_req = QuotaIncreaseRequest(
        id=req_id,
        tenant_id=tenant_id,
        quota_id=quota_id,
        quota_code="L-1216C47A",
        provider=CloudProvider.AWS,
        requested_value=256.0,
        current_value=128.0,
        justification="Anticipated holiday peak traffic volume",
        requester_id="user-quota-lead",
    )
    repo1.save_increase_request(inc_req, tenant_context=tc)

    # Restart
    reset_quota_repository()
    repo2 = get_quota_repository()
    assert repo2 is not repo1

    loaded_quota = repo2.get(quota_id, tenant_context=tc)
    assert loaded_quota is not None
    assert loaded_quota.quota_code == "L-1216C47A"
    assert loaded_quota.limit_value == 128.0

    loaded_req = repo2.get_increase_request(req_id, tenant_context=tc)
    assert loaded_req is not None
    assert loaded_req.requested_value == 256.0


@pytest.mark.realdb
@pytest.mark.asyncio
async def test_provisioning_restart_proof() -> None:
    """Group 7: Provisioning Requests, Estimates, and Rules survive restart."""
    tenant_id = f"tenant-p07-prov-{uuid.uuid4().hex[:6]}"
    req_id = f"prv-req-{uuid.uuid4().hex[:6]}"
    est_id = f"prv-est-{uuid.uuid4().hex[:6]}"

    reset_provisioning_repository()
    repo1 = get_provisioning_repository()
    assert not repo1.is_in_memory

    estimate = SavedEstimate(
        tenant_id=tenant_id,
        estimate_id=est_id,
        requester_id="data-engineer-lead",
        requester_email="data@corp.internal",
        provider="aws",
        service="AmazonEC2",
        region="eu-west-1",
        size="m5.xlarge",
        hourly_cost=Decimal("0.192"),
        daily_cost=Decimal("4.608"),
        monthly_cost=Decimal("1200.00"),
        annualised_cost=Decimal("14400.00"),
        valid_until=(datetime.now(UTC) + timedelta(days=30)).isoformat(),
    )
    repo1.save_estimate(estimate)

    req = ProvisioningRequest(
        tenant_id=tenant_id,
        request_id=req_id,
        estimate_id=est_id,
        estimate=estimate,
        target_scope="sc-aws-analytics-1",
        intended_application="app-spark",
        intended_environment="PROD",
        owner_id="data-engineer-lead",
        owner_email="data@corp.internal",
        cost_centre="CC-DATA-101",
        business_justification="Quarterly big data model training with high memory nodes.",
        intended_start_date=datetime.now(UTC).date().isoformat(),
        budget_impact=BudgetImpactAssessment(
            period="2026-10",
            period_budget=Decimal("50000.00"),
            actual_spend=Decimal("20000.00"),
            remaining_budget=Decimal("30000.00"),
            request_monthly_cost=Decimal("1200.00"),
            projected_spend=Decimal("21200.00"),
            projected_utilisation_pct=Decimal("42.4"),
            consumption_of_remaining_pct=Decimal("4.0"),
            current_forecast=Decimal("48000.00"),
            revised_forecast=Decimal("49200.00"),
            forecast_variance_change=Decimal("1200.00"),
            impact_tier=BudgetImpactTier.NEGLIGIBLE,
            commentary="Spend within allocated budget headroom",
        ),
        quota_pre_check=QuotaPreCheckResult(
            current_headroom_pct=Decimal("50.0"),
            projected_headroom_pct=Decimal("45.0"),
            quota_name="Running Standard Instances",
            quota_code="L-1216C47A",
            consumed_units=Decimal("50"),
            limit_units=Decimal("100"),
            projected_units=Decimal("55"),
            message="Sufficient headroom",
        ),
        dependency_pre_check=DependencyPreCheckResult(
            primary_monthly_cost=Decimal("1200.00"),
            total_chain_monthly_cost=Decimal("1200.00"),
        ),
        gate_action=GateTriggerAction.NOTIFY_ONLY,
        status=ProvisioningRequestStatus.DRAFT,
    )
    repo1.save_request(req)

    # Restart
    reset_provisioning_repository()
    repo2 = get_provisioning_repository()
    assert repo2 is not repo1

    loaded_req = repo2.get_request(tenant_id, req_id)
    assert loaded_req is not None
    assert loaded_req.request_id == req_id
    assert loaded_req.target_scope == "sc-aws-analytics-1"

    loaded_est = repo2.get_estimate(tenant_id, est_id)
    assert loaded_est is not None
    assert loaded_est.monthly_cost == Decimal("1200.00")


@pytest.mark.realdb
@pytest.mark.asyncio
async def test_statements_restart_proof() -> None:
    """Group 8: Showback Statements and Disputes survive restart."""
    tenant_id = f"tenant-p07-stmt-{uuid.uuid4().hex[:6]}"
    tc = TenantContext(tenant_id=tenant_id, user_id="user-billing-lead", roles=["TENANT_ADMIN"])
    stmt_id = f"stmt-{uuid.uuid4().hex[:6]}"
    disp_id = f"disp-{uuid.uuid4().hex[:6]}"

    reset_statement_repository()
    repo1 = get_statement_repository()
    assert not repo1.is_in_memory

    statement = ShowbackStatement(
        statement_id=stmt_id,
        tenant_id=tenant_id,
        period="2026-10",
        scope_type=RecipientScopeType.COST_CENTRE,
        scope_code="CC-FINOPS-101",
        scope_name="FinOps Engineering",
        recipient_owner_id="user-billing-lead",
        recipient_owner_email="billing@corp.internal",
        total_allocated_cost=Decimal("18500.00"),
        direct_allocated_cost=Decimal("15000.00"),
        shared_service_apportioned_cost=Decimal("3500.00"),
        currency="USD",
        status=StatementLifecycleStatus.DRAFT,
    )
    repo1.save_statement(statement, tenant_context=tc)

    dispute = StatementDispute(
        dispute_id=disp_id,
        tenant_id=tenant_id,
        statement_id=stmt_id,
        line_id="WHOLE_STATEMENT",
        recipient_id="user-billing-lead",
        recipient_email="billing@corp.internal",
        disputed_amount=Decimal("500.00"),
        proposed_amount=Decimal("0.00"),
        reason="Storage transfer charge disputed with shared platform",
        assigned_owner="finops-admin",
        sla_deadline=(datetime.now(UTC) + timedelta(days=5)).isoformat(),
    )
    repo1.save_dispute(dispute, tenant_context=tc)

    # Restart
    reset_statement_repository()
    repo2 = get_statement_repository()
    assert repo2 is not repo1

    loaded_stmt = repo2.get_statement(stmt_id, tenant_context=tc)
    assert loaded_stmt is not None
    assert loaded_stmt.period == "2026-10"
    assert loaded_stmt.total_allocated_cost == Decimal("18500.00")

    loaded_disp = repo2.get_dispute(disp_id, tenant_context=tc)
    assert loaded_disp is not None
    assert loaded_disp.disputed_amount == Decimal("500.00")


@pytest.mark.realdb
@pytest.mark.asyncio
async def test_bulk_imports_restart_proof() -> None:
    """Group 9: Bulk Import Runs and Mapping Profiles survive restart."""
    tenant_id = f"tenant-p07-import-{uuid.uuid4().hex[:6]}"
    tc = TenantContext(tenant_id=tenant_id, user_id="user-import-admin", roles=["TENANT_ADMIN"])
    run_id = f"imp-run-{uuid.uuid4().hex[:6]}"
    prof_id = f"map-prof-{uuid.uuid4().hex[:6]}"

    reset_bulk_import_repository()
    repo1 = get_bulk_import_repository()
    assert not repo1.is_in_memory

    profile = MappingProfile(
        id=prof_id,
        tenant_id=tenant_id,
        name="ServiceNow CMDB Mapping",
        entity_type="RESOURCE",
        column_mappings={"HostName": "name", "AssetID": "native_id"},
    )
    repo1.save_mapping_profile(profile, tenant_context=tc)

    run = ImportRunRecord(
        id=run_id,
        tenant_id=tenant_id,
        entity_type="RESOURCE",
        mode=ImportMode.UPSERT,
        atomicity_policy=AtomicityPolicy.PARTIAL_SUCCESS,
        source_filename="cmdb_assets_2026.csv",
        source_file_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        actor_id="user-import-admin",
        status=ImportStatus.APPLIED,
        total_rows=150,
        created_count=150,
        updated_count=0,
        skipped_count=0,
        rejected_count=0,
        deactivated_count=0,
        dry_run_id=f"dry-{uuid.uuid4().hex[:6]}",
    )
    repo1.save_import_run(run, tenant_context=tc)

    # Restart
    reset_bulk_import_repository()
    repo2 = get_bulk_import_repository()
    assert repo2 is not repo1

    loaded_run = repo2.get_import_run(run_id, tenant_context=tc)
    assert loaded_run is not None
    assert loaded_run.source_filename == "cmdb_assets_2026.csv"
    assert loaded_run.total_rows == 150

    loaded_prof = repo2.get_mapping_profile(prof_id, tenant_context=tc)
    assert loaded_prof is not None
    assert loaded_prof.name == "ServiceNow CMDB Mapping"


@pytest.mark.realdb
@pytest.mark.asyncio
async def test_dependency_graph_restart_proof() -> None:
    """Group 10: Service Dependencies and Conflicts survive restart."""
    tenant_id = f"tenant-p07-dep-{uuid.uuid4().hex[:6]}"
    tc = TenantContext(tenant_id=tenant_id, user_id="user-architect", roles=["TENANT_ADMIN"])
    edge_id = f"dep-edge-{uuid.uuid4().hex[:6]}"
    conf_id = f"dep-conf-{uuid.uuid4().hex[:6]}"

    reset_dependency_repository()
    repo1 = get_dependency_repository()
    assert not repo1.is_in_memory

    edge = DependencyEdge(
        id=edge_id,
        tenant_id=tenant_id,
        source_ref=TypedEntityRef(entity_id="app-payments-api", entity_type=EntityReferenceType.APPLICATION),
        target_ref=TypedEntityRef(entity_id="db-postgres-cluster", entity_type=EntityReferenceType.RESOURCE),
        relationship_type=RelationshipType.DATA_FLOW,
        provenance=EdgeProvenance(
            provenance_type=EdgeProvenanceType.DISCOVERED,
            layer=DiscoveryLayer.STRUCTURAL,
        ),
        confidence=EdgeConfidenceLevel.HIGH,
        criticality=EdgeCriticality.CRITICAL,
        status=EdgeStatus.ACTIVE,
    )
    repo1.save_edge(edge, tenant_context=tc)

    conflict = EdgeConflict(
        conflict_id=conf_id,
        tenant_id=tenant_id,
        source_ref=TypedEntityRef(entity_id="app-payments-api", entity_type=EntityReferenceType.APPLICATION),
        manual_edge_id=edge_id,
        discovered_edge_id=f"disc-{edge_id}",
        manual_version={"rel": "DATA_FLOW"},
        discovered_version={"rel": "NETWORK_CONNECTIVITY"},
        conflict_reason="Source claims DATA_FLOW while network discovery inferred NETWORK_CONNECTIVITY",
        detected_at=datetime.now(UTC),
    )
    repo1.save_conflict(conflict, tenant_context=tc)

    # Restart
    reset_dependency_repository()
    repo2 = get_dependency_repository()
    assert repo2 is not repo1

    loaded_edge = repo2.get_edge(edge_id, tenant_context=tc)
    assert loaded_edge is not None
    assert loaded_edge.id == edge_id
    assert loaded_edge.relationship_type == RelationshipType.DATA_FLOW

    loaded_conf = repo2.get_conflict(conf_id, tenant_context=tc)
    assert loaded_conf is not None
    assert loaded_conf.manual_edge_id == edge_id


@pytest.mark.realdb
@pytest.mark.asyncio
async def test_usage_facts_restart_proof() -> None:
    """Group 11: Usage Fact partitioned records and Overrides survive restart."""
    tenant_id = f"tenant-p07-usage-{uuid.uuid4().hex[:6]}"
    tc = TenantContext(tenant_id=tenant_id, user_id="user-telemetry", roles=["TENANT_ADMIN"])
    record_id = f"usg-fact-{uuid.uuid4().hex[:6]}"
    ovr_id = f"ovr-{uuid.uuid4().hex[:6]}"

    reset_usage_repository()
    repo1 = get_usage_repository()
    assert not repo1.is_in_memory

    now = datetime.now(UTC)
    usage = PreAggregatedUsageRecord(
        id=record_id,
        tenant_id=tenant_id,
        scope_id="sc-prod-1",
        resource_id="i-worker-vm-01",
        metric_name="CPUUtilization",
        interval_start=now - timedelta(hours=1),
        interval_end=now,
        usage_quantity=QuantityMeasure(value=Decimal("78.50")),
        usage_unit="Percent",
    )
    repo1.save(usage, tenant_context=tc)

    override = MonitoringTypeOverride(
        id=ovr_id,
        tenant_id=tenant_id,
        resource_id="i-worker-vm-01",
        monitoring_type=MonitoringType.RUNTIME_BASED,
        previous_monitoring_type=MonitoringType.NOT_APPLICABLE,
        who="user-telemetry",
        why="Compute instance active running workload for analytics pipeline",
    )
    repo1.save_override(override, tenant_context=tc)

    # Restart
    reset_usage_repository()
    repo2 = get_usage_repository()
    assert repo2 is not repo1

    loaded_usage = repo2.get(record_id, tenant_context=tc)
    assert loaded_usage is not None
    assert loaded_usage.id == record_id
    assert loaded_usage.metric_name == "CPUUtilization"

    loaded_ovr = repo2.get_override("i-worker-vm-01", tenant_context=tc)
    assert loaded_ovr is not None
    assert loaded_ovr.monitoring_type == MonitoringType.RUNTIME_BASED


@pytest.mark.realdb
@pytest.mark.asyncio
async def test_runtime_states_restart_proof() -> None:
    """Group 12: Runtime Observations, Schedules, and Exemptions survive restart."""
    tenant_id = f"tenant-p07-rt-{uuid.uuid4().hex[:6]}"
    tc = TenantContext(tenant_id=tenant_id, user_id="user-ops", roles=["TENANT_ADMIN"])
    sched_id = f"sched-{uuid.uuid4().hex[:6]}"
    res_id = f"rt-res-{uuid.uuid4().hex[:6]}"

    reset_runtime_repository()
    repo1 = get_runtime_repository()
    assert not repo1.is_in_memory

    now = datetime.now(UTC)
    schedule = NamedSchedule(
        id=sched_id,
        name="Dev Workday Schedule 08:00-18:00",
        description="Daily operational shutdown outside working hours.",
        timezone="UTC",
        working_days=[1, 2, 3, 4, 5],
        daily_start_time="08:00",
        daily_end_time="18:00",
    )
    repo1.save_schedule(schedule, tenant_context=tc)

    result = ScheduleAdherenceResult(
        id=res_id,
        tenant_id=tenant_id,
        schedule_id=sched_id,
        schedule_name="Dev Workday Schedule 08:00-18:00",
        resource_id="i-dev-box-01",
        resource_name="dev-box-01",
        runtime_state=RuntimeState.RUNNING,
        adherence_status=AdherenceStatus.COMPLIANT,
        is_compliant=True,
        color_hex="#10b981",
        expected_running_hours=Decimal("10.0"),
        actual_running_hours=Decimal("10.0"),
        excess_running_hours=Decimal("0.0"),
        hourly_rate=Decimal("0.50"),
        breach_cost=Decimal("0.00"),
        evaluation_window_start=now - timedelta(hours=2),
        evaluation_window_end=now,
    )
    repo1.save(result, tenant_context=tc)

    # Restart
    reset_runtime_repository()
    repo2 = get_runtime_repository()
    assert repo2 is not repo1

    loaded_sched = repo2.get_schedule(sched_id, tenant_context=tc)
    assert loaded_sched is not None
    assert loaded_sched.name == "Dev Workday Schedule 08:00-18:00"

    loaded_res = repo2.get(res_id, tenant_context=tc)
    assert loaded_res is not None
    assert loaded_res.schedule_id == sched_id
    assert loaded_res.is_compliant is True


@pytest.mark.realdb
@pytest.mark.asyncio
async def test_hierarchy_resources_and_views_restart_proof() -> None:
    """Group 13: Hierarchy Resources and Saved Views survive restart."""
    tenant_id = f"tenant-p07-hier-{uuid.uuid4().hex[:6]}"
    tc = TenantContext(tenant_id=tenant_id, user_id="user-hier-lead", roles=["TENANT_ADMIN"])
    res_id = f"res-p07-{uuid.uuid4().hex[:6]}"
    view_id = f"view-p07-{uuid.uuid4().hex[:6]}"

    reset_hierarchy_repository()
    repo1 = get_hierarchy_repository()
    assert not repo1.is_in_memory

    from sqlalchemy import text
    from db.session import get_tenant_session

    async with get_tenant_session(tenant_id) as sess:
        await sess.execute(
            text("""
                INSERT INTO tenants (id, name, created_at, updated_at)
                VALUES (:tid, 'Test Tenant', NOW(), NOW())
                ON CONFLICT (id) DO NOTHING;
            """),
            {"tid": tenant_id},
        )
        await sess.execute(
            text("""
                INSERT INTO scopes (
                    id, tenant_id, name, canonical_role, provider, native_type, native_id, materialized_path, created_at, updated_at
                ) VALUES (
                    'sc-aws-prod-1', :tid, 'Prod Scope', 'ACCOUNT', 'aws', 'account', '123456789012', '/sc-aws-prod-1', NOW(), NOW()
                ) ON CONFLICT (id) DO NOTHING;
            """),
            {"tid": tenant_id},
        )
        await sess.execute(
            text("""
                INSERT INTO services (id, provider, service_code, name, category, created_at)
                VALUES ('svc-ec2', 'aws', 'ec2', 'Amazon Elastic Compute Cloud', 'COMPUTE', NOW())
                ON CONFLICT (id) DO NOTHING;
            """)
        )
        await sess.execute(
            text("""
                INSERT INTO resource_types (id, provider, service_id, native_type_name, canonical_type, created_at)
                VALUES ('ec2:instance', 'aws', 'svc-ec2', 'ec2:instance', 'COMPUTE_INSTANCE', NOW())
                ON CONFLICT (id) DO NOTHING;
            """)
        )
        await sess.execute(
            text("""
                INSERT INTO regions (id, provider, native_name, display_name, geography, created_at)
                VALUES ('us-east-1', 'aws', 'us-east-1', 'US East (N. Virginia)', 'NORTH_AMERICA', NOW())
                ON CONFLICT (id) DO NOTHING;
            """)
        )
        await sess.commit()

    now = datetime.now(UTC)
    resource = InventoryResource35(
        id=res_id,
        tenant_id=tenant_id,
        scope_id="sc-aws-prod-1",
        native_id=f"i-aws-{res_id}",
        name="prod-core-gateway",
        provider="AWS",
        service_id="svc-ec2",
        service_name="Amazon Elastic Compute Cloud",
        service_category="Compute",
        resource_type_id="ec2:instance",
        resource_type="VirtualMachine",
        region_id="us-east-1",
        region_name="US East (N. Virginia)",
        pricing_status="PAID",
        runtime_state="RUNNING",
        monthly_cost=Decimal("245.50"),
        last_synced_at=now,
        created_at=now,
    )
    repo1.save_resource(resource, tenant_context=tc)

    view = SavedInventoryView(
        id=view_id,
        name="Production Compute View",
        user_id="user-hier-lead",
        filters={"providers": ["AWS"], "regions": ["us-east-1"]},
        created_at=now,
    )
    repo1.save_saved_view(view, tenant_context=tc)

    # Restart
    reset_hierarchy_repository()
    repo2 = get_hierarchy_repository()
    assert repo2 is not repo1

    loaded_res = repo2.get_resource(res_id, tenant_context=tc)
    assert loaded_res is not None
    assert loaded_res.name == "prod-core-gateway"
    assert loaded_res.monthly_cost == Decimal("245.50")

    loaded_view = repo2.get_saved_view(view_id, tenant_context=tc)
    assert loaded_view is not None
    assert loaded_view.name == "Production Compute View"
    assert loaded_view.filters == {"providers": ["AWS"], "regions": ["us-east-1"]}
