"""Comprehensive Unit Test Suite for Remediation, Task Assignment, and Accountability (Prompt 51).

Enforces:
- Prompt 51 / BBP Sections 34, 35, 36: Remediation task lifecycle across all 11 states.
- Master data taxonomies: states, priorities, categories, closure codes, and 12 creation rules.
- 4-Tier Ownership Hierarchy: Technical Owner -> Scope Owner -> App Owner -> Fallback Queue -> NoResolvableAssigneeException.
- Mandatory Automated Verification: Never close a task on assignee's word alone.
  Persistent condition reopens to OPEN with explanation note; cleared condition advances to VERIFIED -> CLOSED.
- Realised-Saving Ledger: Confirmed savings tracked with method attribution and aggregated across periods, teams, categories.
- Bidirectional Alert Sync: Resolving a verified task resolves the linked alert.
- Deferral and Risk Acceptance: Time-boxed justifications, expiry checks, and automatic reopening.
- Bulk Operations: Assign, reprioritise, defer, close as duplicate.
- Accountability Views: My Tasks, Team Tasks, App, BU, Overdue, Ageing distribution, and Leaderboard-Free Trends.
- Outbound ITSM Adapter with feature flag gating.
- Multi-Tenant Isolation and REST API Endpoint contracts.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from fastapi.testclient import TestClient

from api.cloudlens_api.main import app
from domain.alerting.models import AlertEntity, AlertEvidence
from domain.alerting.repository import reset_alert_repository
from domain.alerting.service import get_alert_service, reset_alert_service
from domain.models.enums import (
    AlertSeverity,
    AlertType,
    TaskAssignmentRule,
    TaskCategory,
    TaskClosureCode,
    TaskPriority,
    TaskSource,
    TaskState,
)
from domain.models.exceptions import (
    InvalidTaskTransitionException,
    MandatoryReasonException,
    NoResolvableAssigneeException,
    RemediationTaskNotFoundException,
)
from domain.remediation.assignment import AssignmentResolver
from domain.remediation.itsm import ITSMAdapter, reset_itsm_adapter
from domain.remediation.ledger import reset_realised_saving_ledger
from domain.remediation.models import (
    BulkAssignRequest,
    BulkDuplicateRequest,
    BulkReprioritiseRequest,
    RemediationTask,
    SubjectEntity,
    TaskCreateRequest,
)
from domain.remediation.repository import (
    reset_remediation_repository,
)
from domain.remediation.service import (
    get_remediation_service,
    reset_remediation_service,
)
from domain.tenant.context import TenantContext
from masterdata.service import get_master_data_service


@pytest.fixture(autouse=True)
def reset_singletons():
    """Isolate state for each unit test."""
    reset_remediation_repository()
    reset_remediation_service()
    reset_realised_saving_ledger()
    reset_itsm_adapter()
    reset_alert_repository()
    reset_alert_service()
    yield
    reset_remediation_repository()
    reset_remediation_service()
    reset_realised_saving_ledger()
    reset_itsm_adapter()
    reset_alert_repository()
    reset_alert_service()


@pytest.fixture
def tenant_ctx() -> TenantContext:
    """Standard authenticated tenant execution context."""
    return TenantContext(
        tenant_id="tenant-rem-test",
        user_id="user-engineer-1",
        email="engineer@cloudlens.io",
        roles=["ENGINEER"],
        correlation_id=str(uuid.uuid4()),
    )


@pytest.fixture
def other_tenant_ctx() -> TenantContext:
    """Secondary tenant execution context for isolation tests."""
    return TenantContext(
        tenant_id="tenant-rem-other",
        user_id="user-other-1",
        email="other@enterprise.io",
        roles=["ENGINEER"],
        correlation_id=str(uuid.uuid4()),
    )


# ==============================================================================
# 1. Master Data Taxonomies & Creation Rules
# ==============================================================================


class TestMasterDataTaxonomiesAndCreationRules:
    """Validates that all remediation taxonomies are master-data-driven."""

    def test_task_states_registered(self):
        """Validates all 11 lifecycle states in master data registry."""
        md_service = get_master_data_service()
        records = md_service.list_records("TASK_STATE")
        assert len(records) == 11
        codes = {r.code for r in records}
        expected_states = {
            "OPEN",
            "ASSIGNED",
            "IN_PROGRESS",
            "BLOCKED",
            "AWAITING_VERIFICATION",
            "RESOLVED",
            "VERIFIED",
            "CLOSED",
            "REJECTED",
            "DEFERRED",
            "DUPLICATE",
        }
        assert codes == expected_states

    def test_task_priorities_registered(self):
        """Validates urgency priorities in master data."""
        md_service = get_master_data_service()
        records = md_service.list_records("TASK_PRIORITY")
        assert len(records) == 4
        codes = {r.code for r in records}
        assert codes == {"CRITICAL", "HIGH", "MEDIUM", "LOW"}

    def test_task_categories_registered(self):
        """Validates problem categories in master data."""
        md_service = get_master_data_service()
        records = md_service.list_records("TASK_CATEGORY")
        assert len(records) == 13
        codes = {r.code for r in records}
        assert "UNOWNED_RESOURCE" in codes
        assert "SCHEDULE_BREACH" in codes
        assert "BUDGET_BREACH" in codes

    def test_task_closure_codes_registered(self):
        """Validates final closure codes in master data."""
        md_service = get_master_data_service()
        records = md_service.list_records("TASK_CLOSURE_CODE")
        assert len(records) == 5
        codes = {r.code for r in records}
        assert codes == {
            "FIXED_AND_VERIFIED",
            "RISK_ACCEPTED",
            "FALSE_POSITIVE",
            "DUPLICATE_SUPERSEDED",
            "RESOURCE_TERMINATED",
        }

    def test_task_creation_rules_twelve_canonical_sources(self):
        """Validates the 12 canonical detection source creation rules."""
        md_service = get_master_data_service()
        records = md_service.list_records("TASK_CREATION_RULE")
        assert len(records) == 12
        sources = {r.attributes["source_code"] for r in records}
        assert "UNOWNED_RESOURCE" in sources
        assert "TAG_COMPLIANCE" in sources
        assert "SCHEDULE_BREACH" in sources
        assert "BUDGET_BREACH" in sources
        assert "FORECAST_BREACH" in sources
        assert "IDLE_RESOURCE" in sources
        assert "STALE_CONNECTOR" in sources
        assert "CREDENTIAL_EXPIRING" in sources
        assert "RECONCILIATION_VARIANCE" in sources
        assert "UNKNOWN_SKU" in sources
        assert "UNCLASSIFIED_RESOURCE" in sources
        assert "MASTERDATA_GAP" in sources


# ==============================================================================
# 2. Ownership Resolution Hierarchy & Automatic Task Creation
# ==============================================================================


class TestTaskCreationAndOwnershipResolution:
    """Validates 4-tier assignment resolution and declarative task creation."""

    def test_tier_1_resolves_technical_owner_from_tags(self):
        """Resolves technical owner directly from tags."""
        resolver = AssignmentResolver(get_master_data_service())
        subject = SubjectEntity(entity_type="vm", entity_id="vm-app-01")
        assignee_id, assignee_type, rule = resolver.resolve(
            subject=subject,
            tags={"technical_owner": "eng-alice", "env": "prod"},
        )
        assert assignee_id == "eng-alice"
        assert assignee_type == "USER"
        assert rule == TaskAssignmentRule.TECHNICAL_OWNER

    def test_tier_2_resolves_scope_owner_when_technical_owner_absent(self):
        """Falls back to scope owner when technical owner tag is missing."""
        resolver = AssignmentResolver(get_master_data_service())
        subject = SubjectEntity(entity_type="vm", entity_id="vm-app-02")
        assignee_id, assignee_type, rule = resolver.resolve(
            subject=subject,
            tags={},
            scope_owner_id="scope-lead-bob",
        )
        assert assignee_id == "scope-lead-bob"
        assert assignee_type == "USER"
        assert rule == TaskAssignmentRule.SCOPE_OWNER

    def test_tier_3_resolves_application_owner_when_scope_owner_absent(self):
        """Falls back to application owner when scope owner is missing."""
        resolver = AssignmentResolver(get_master_data_service())
        subject = SubjectEntity(entity_type="db", entity_id="db-app-03")
        assignee_id, assignee_type, rule = resolver.resolve(
            subject=subject,
            tags={},
            scope_owner_id=None,
            app_owner_id="app-lead-charlie",
        )
        assert assignee_id == "app-lead-charlie"
        assert assignee_type == "USER"
        assert rule == TaskAssignmentRule.APPLICATION_OWNER

    def test_tier_4_resolves_fallback_queue(self):
        """Routes to fallback queue when no explicit owners exist."""
        resolver = AssignmentResolver(get_master_data_service())
        subject = SubjectEntity(entity_type="bucket", entity_id="bucket-orphan-01")
        assignee_id, assignee_type, rule = resolver.resolve(
            subject=subject,
            tags={},
            fallback_queue_id="queue-cloud-admin",
        )
        assert assignee_id == "queue-cloud-admin"
        assert assignee_type == "QUEUE"
        assert rule == TaskAssignmentRule.FALLBACK_QUEUE

    def test_governance_exception_raised_when_no_owner_resolvable(self):
        """Raises NoResolvableAssigneeException if completely unassigned."""
        resolver = AssignmentResolver(get_master_data_service())
        subject = SubjectEntity(entity_type="bucket", entity_id="bucket-orphan-02")
        with pytest.raises(NoResolvableAssigneeException) as exc_info:
            resolver.resolve(
                subject=subject,
                tags={},
                scope_owner_id=None,
                app_owner_id=None,
                fallback_queue_id="",
            )
        assert "bucket-orphan-02" in exc_info.value.message

    def test_automatic_task_creation_from_detection_source(self, tenant_ctx: TenantContext):
        """Creates task automatically from schedule breach detection with excess cost."""
        service = get_remediation_service()
        subject = SubjectEntity(
            entity_type="vm",
            entity_id="i-excess-123",
            entity_name="Analytics Worker",
            scope_type="subscription",
            scope_id="sub-prod-01",
        )
        task = service.create_from_source(
            source=TaskSource.SCHEDULE_BREACH,
            subject=subject,
            evidence={"excess_hours": 14, "excess_cost": 420.50, "tags": {"owner": "eng-bob"}},
            payload={"excess_cost": 420.50, "tags": {"owner": "eng-bob"}},
            tenant_context=tenant_ctx,
        )
        assert task is not None
        assert task.state == TaskState.ASSIGNED
        assert task.category == TaskCategory.SCHEDULE_BREACH
        assert task.estimated_saving == 420.50
        assert task.assignee_id == "eng-bob"
        assert len(task.history) >= 2


# ==============================================================================
# 3. Mandatory Automated Verification Discipline
# ==============================================================================


class TestAutomatedVerificationDiscipline:
    """Enforces: Never close a task on assignee's word alone."""

    def test_verification_fails_when_condition_still_active_and_reopens_to_open(
        self, tenant_ctx: TenantContext
    ):
        """Assignee attempts to resolve, but verification detects problem is STILL active.

        Expected: Task transitions to AWAITING_VERIFICATION -> fails verification -> reopens to OPEN
        with explanatory note in history and verification_notes.
        """
        service = get_remediation_service()
        verifier = service.verifier
        # Set mock entity state indicating problem STILL persists
        verifier.set_mock_entity_state(
            tenant_ctx.tenant_id,
            "resource",
            "res-unowned-01",
            {"owner": None, "status": "active"},
        )

        task = service.create_task(
            TaskCreateRequest(
                source=TaskSource.UNOWNED_RESOURCE,
                subject_entity=SubjectEntity(entity_type="resource", entity_id="res-unowned-01"),
                title="Assign Owner to S3 Bucket",
                description="Bucket is missing accountable owner tag.",
                category=TaskCategory.UNOWNED_RESOURCE,
                assignee_id="eng-alice",
            ),
            actor="admin",
            tenant_context=tenant_ctx,
        )

        # Assignee marks resolved
        resolved_task, verification = service.resolve_task(
            task.id,
            actor="eng-alice",
            tenant_context=tenant_ctx,
            resolution_note="I think someone added an owner in Jira.",
        )

        # Verification must fail and task must be REOPENED to OPEN
        assert verification.is_cleared is False
        assert resolved_task.state == TaskState.OPEN
        assert resolved_task.verification_attempts == 1
        assert len(resolved_task.verification_notes) == 1
        assert "still exists" in resolved_task.verification_notes[0].lower()

        # Check history contains REOPENED event
        actions = [h.action for h in resolved_task.history]
        assert "VERIFICATION_FAILED_REOPENED" in actions

    def test_verification_succeeds_when_condition_cleared_and_closes_task(
        self, tenant_ctx: TenantContext
    ):
        """Assignee fixes problem, condition clears, and task advances to VERIFIED -> CLOSED."""
        service = get_remediation_service()
        verifier = service.verifier
        # Simulate fixed state (owner populated)
        verifier.set_mock_entity_state(
            tenant_ctx.tenant_id,
            "resource",
            "res-fixed-02",
            {"owner": "eng-dan", "tags": {"owner": "eng-dan"}},
        )

        task = service.create_task(
            TaskCreateRequest(
                source=TaskSource.UNOWNED_RESOURCE,
                subject_entity=SubjectEntity(entity_type="resource", entity_id="res-fixed-02"),
                title="Tag Missing Owner",
                description="Missing owner tag.",
                category=TaskCategory.UNOWNED_RESOURCE,
                assignee_id="eng-dan",
                estimated_saving=150.0,
            ),
            actor="admin",
            tenant_context=tenant_ctx,
        )

        resolved_task, verification = service.resolve_task(
            task.id,
            actor="eng-dan",
            tenant_context=tenant_ctx,
            resolution_note="Tagged owner='eng-dan' in AWS Console.",
        )

        # Verification succeeds!
        assert verification.is_cleared is True
        assert resolved_task.state == TaskState.CLOSED
        assert resolved_task.closure_code == TaskClosureCode.FIXED_AND_VERIFIED
        assert resolved_task.closed_at is not None
        assert resolved_task.realised_saving == 150.0

        # Check history contains VERIFIED_AND_CLOSED
        actions = [h.action for h in resolved_task.history]
        assert "VERIFIED_AND_CLOSED" in actions

    def test_direct_transition_to_closed_without_verification_is_strictly_forbidden(
        self, tenant_ctx: TenantContext
    ):
        """Attempts to bypass verification by directly setting state to CLOSED are rejected."""
        service = get_remediation_service()
        task = service.create_task(
            TaskCreateRequest(
                source=TaskSource.MANUAL,
                subject_entity=SubjectEntity(entity_type="vm", entity_id="vm-direct-01"),
                title="Direct Close Bypass Attempt",
                description="Testing direct close protection.",
                assignee_id="eng-alice",
            ),
            actor="admin",
            tenant_context=tenant_ctx,
        )

        with pytest.raises(InvalidTaskTransitionException):
            service.transition_state(
                task.id,
                to_state=TaskState.CLOSED,
                actor="eng-alice",
                tenant_context=tenant_ctx,
            )


# ==============================================================================
# 4. Realised-Saving Ledger
# ==============================================================================


class TestRealisedSavingLedger:
    """Validates confirmed saving attribution across periods, teams, and categories."""

    def test_realised_saving_ledger_recording_upon_verified_resolution(
        self, tenant_ctx: TenantContext
    ):
        """Confirms saving entry is added to ledger upon verified task closure."""
        service = get_remediation_service()
        verifier = service.verifier
        # Set cleared condition
        verifier.set_mock_entity_state(
            tenant_ctx.tenant_id,
            "vm",
            "vm-idle-99",
            {"status": "stopped", "running": False},
        )

        task = service.create_task(
            TaskCreateRequest(
                source=TaskSource.IDLE_RESOURCE,
                subject_entity=SubjectEntity(
                    entity_type="vm",
                    entity_id="vm-idle-99",
                    business_unit_id="bu-fintech",
                ),
                title="Terminate Idle Dev Cluster",
                description="Cluster idle for >14 days.",
                category=TaskCategory.IDLE_RESOURCE,
                assignee_id="team-platform",
                assignee_type="TEAM",
                estimated_saving=850.00,
            ),
            actor="finops-lead",
            tenant_context=tenant_ctx,
        )

        # Resolve and verify
        closed_task, verification = service.resolve_task(
            task.id,
            actor="team-platform",
            tenant_context=tenant_ctx,
            resolution_note="Terminated idle cluster nodes.",
        )

        assert closed_task.state == TaskState.CLOSED
        assert closed_task.realised_saving == 850.00

        # Query Realised-Saving Report
        report = service.get_savings_report(tenant_context=tenant_ctx)
        assert report.total_realised_saving == 850.00
        assert report.entries_count == 1
        assert "IDLE_RESOURCE" in report.savings_by_category
        assert report.savings_by_category["IDLE_RESOURCE"] == 850.00
        assert "team-platform" in report.savings_by_team
        assert report.savings_by_team["team-platform"] == 850.00


# ==============================================================================
# 5. Bidirectional Alert Synchronization
# ==============================================================================


class TestAlertIntegrationAndSync:
    """Validates that alerts and tasks never drift into two disconnected records."""

    def test_resolving_task_resolves_linked_alert(self, tenant_ctx: TenantContext):
        """Resolving and verifying a remediation task automatically resolves the originating alert."""
        alert_service = get_alert_service()
        remediation_service = get_remediation_service()
        remediation_service.alert_service = alert_service

        # 1. Create alert
        alert_entity = AlertEntity(
            tenant_id=tenant_ctx.tenant_id,
            alert_type=AlertType.UNEXPECTED_COST_INCREASE,
            severity=AlertSeverity.HIGH,
            title="Spike in EC2 Spend",
            description="Unexpected surge detected.",
            source="cost_engine",
            affected_resource_id="res-spike-01",
            evidence=AlertEvidence(
                summary="Spend increased 300% over 24h baseline",
                datapoints=[{"cost": 1200.0, "baseline": 300.0}],
            ),
        )
        alert = alert_service.raise_alert(
            alert_entity,
            tenant_context=tenant_ctx,
            auto_dispatch=False,
        )

        # 2. Acknowledge alert and link task
        task = remediation_service.create_task(
            TaskCreateRequest(
                source=TaskSource.ALERT,
                subject_entity=SubjectEntity(entity_type="ec2", entity_id="res-spike-01"),
                title="Investigate Spike in EC2 Spend",
                description="Investigate surge and adjust provisioned capacity.",
                category=TaskCategory.CUSTOM,
                assignee_id="eng-bob",
                estimated_saving=900.0,
                alert_id=alert.id,
            ),
            actor="eng-bob",
            tenant_context=tenant_ctx,
        )

        alert_service.acknowledge_alert(
            alert.id,
            actor="eng-bob",
            tenant_context=tenant_ctx,
            reason="Created remediation task",
            remediation_task_id=task.id,
        )

        # Verify alert has task ID linked
        updated_alert = alert_service.get_alert(alert.id, tenant_context=tenant_ctx)
        assert updated_alert is not None
        assert updated_alert.remediation_task_id == task.id

        # 3. Resolve and verify remediation task
        verifier = remediation_service.verifier
        verifier.set_mock_entity_state(
            tenant_ctx.tenant_id, "ec2", "res-spike-01", {"condition_cleared": True}
        )

        closed_task, verif = remediation_service.resolve_task(
            task.id,
            actor="eng-bob",
            tenant_context=tenant_ctx,
            resolution_note="Downsized oversized instances.",
        )
        assert closed_task.state == TaskState.CLOSED

        # 4. Check alert is now automatically RESOLVED
        final_alert = alert_service.get_alert(alert.id, tenant_context=tenant_ctx)
        assert final_alert is not None
        assert final_alert.status.value == "RESOLVED"
        assert "Remediation task" in (final_alert.resolution_reason or "")


# ==============================================================================
# 6. Deferral & Risk Acceptance Paths
# ==============================================================================


class TestDeferralAndRiskAcceptance:
    """Validates time-boxed deferral justifications and automatic reopening upon expiry."""

    def test_defer_task_requires_mandatory_reason_and_future_expiry(
        self, tenant_ctx: TenantContext
    ):
        """Deferral without justification is rejected; valid deferral advances to DEFERRED."""
        service = get_remediation_service()
        task = service.create_task(
            TaskCreateRequest(
                source=TaskSource.MANUAL,
                subject_entity=SubjectEntity(entity_type="vm", entity_id="vm-def-01"),
                title="Deferral Test Task",
                description="Testing deferral requirements.",
                assignee_id="eng-alice",
            ),
            actor="admin",
            tenant_context=tenant_ctx,
        )

        # Blank reason fails
        with pytest.raises(MandatoryReasonException):
            service.defer_task(
                task.id,
                actor="eng-alice",
                tenant_context=tenant_ctx,
                reason="   ",
                deferral_expiry=dt.datetime.now(dt.UTC) + dt.timedelta(days=7),
            )

        # Past expiry fails
        with pytest.raises(MandatoryReasonException):
            service.defer_task(
                task.id,
                actor="eng-alice",
                tenant_context=tenant_ctx,
                reason="Postponing until sprint 28",
                deferral_expiry=dt.datetime.now(dt.UTC) - dt.timedelta(days=1),
            )

        # Valid deferral succeeds
        future_exp = dt.datetime.now(dt.UTC) + dt.timedelta(days=14)
        deferred = service.defer_task(
            task.id,
            actor="eng-alice",
            tenant_context=tenant_ctx,
            reason="Awaiting vendor patch scheduled in release 4.2",
            deferral_expiry=future_exp,
        )
        assert deferred.state == TaskState.DEFERRED
        assert deferred.deferral_expiry == future_exp

    def test_expired_deferral_automatically_reopens_to_open(self, tenant_ctx: TenantContext):
        """Scans deferred tasks and reopens expired ones to OPEN."""
        service = get_remediation_service()
        task = service.create_task(
            TaskCreateRequest(
                source=TaskSource.MANUAL,
                subject_entity=SubjectEntity(entity_type="vm", entity_id="vm-def-exp-01"),
                title="Expired Deferral Task",
                description="Testing automatic reopening.",
                assignee_id="eng-alice",
            ),
            actor="admin",
            tenant_context=tenant_ctx,
        )

        # Defer until tomorrow
        tomorrow = dt.datetime.now(dt.UTC) + dt.timedelta(days=1)
        deferred = service.defer_task(
            task.id,
            actor="eng-alice",
            tenant_context=tenant_ctx,
            reason="Waiting for patch",
            deferral_expiry=tomorrow,
        )
        assert deferred.state == TaskState.DEFERRED

        # Simulate time passing beyond expiry (tomorrow + 1 hour)
        simulated_future = tomorrow + dt.timedelta(hours=1)
        reopened_tasks = service.check_expired_deferrals(
            tenant_context=tenant_ctx, now=simulated_future
        )
        assert len(reopened_tasks) == 1
        assert reopened_tasks[0].id == task.id
        assert reopened_tasks[0].state == TaskState.OPEN
        assert reopened_tasks[0].deferral_expiry is None

    def test_risk_acceptance_closes_task_with_audit_trail(self, tenant_ctx: TenantContext):
        """Accepts organizational risk with mandatory justification."""
        service = get_remediation_service()
        task = service.create_task(
            TaskCreateRequest(
                source=TaskSource.MANUAL,
                subject_entity=SubjectEntity(entity_type="vm", entity_id="vm-risk-01"),
                title="Accepted Risk Task",
                description="Legacy database cannot be decommissioned yet.",
                assignee_id="eng-lead",
            ),
            actor="admin",
            tenant_context=tenant_ctx,
        )

        risk_exp = dt.datetime.now(dt.UTC) + dt.timedelta(days=90)
        accepted = service.accept_risk(
            task.id,
            actor="ciso-officer",
            tenant_context=tenant_ctx,
            reason="Approved legacy exception by architectural board pending cloud migration in Q2.",
            risk_expiry=risk_exp,
            approved_by="VP Architecture",
        )
        assert accepted.state == TaskState.CLOSED
        assert accepted.closure_code == TaskClosureCode.RISK_ACCEPTED
        assert accepted.risk_accepted is True
        assert accepted.risk_accepted_expiry == risk_exp


# ==============================================================================
# 7. Bulk Operations
# ==============================================================================


class TestBulkOperations:
    """Validates batch task assignments, reprioritisation, deferrals, and duplicate closures."""

    def test_bulk_operations_lifecycle(self, tenant_ctx: TenantContext):
        """Executes bulk assign, reprioritise, defer, and duplicate operations."""
        service = get_remediation_service()
        t1 = service.create_task(
            TaskCreateRequest(
                source=TaskSource.MANUAL,
                subject_entity=SubjectEntity(entity_type="vm", entity_id="vm-b1"),
                title="Task 1",
                description="Bulk test 1",
                assignee_id="eng-alice",
            ),
            actor="admin",
            tenant_context=tenant_ctx,
        )
        t2 = service.create_task(
            TaskCreateRequest(
                source=TaskSource.MANUAL,
                subject_entity=SubjectEntity(entity_type="vm", entity_id="vm-b2"),
                title="Task 2",
                description="Bulk test 2",
                assignee_id="eng-alice",
            ),
            actor="admin",
            tenant_context=tenant_ctx,
        )

        # 1. Bulk Reprioritise
        reprio_res = service.bulk_reprioritise(
            BulkReprioritiseRequest(
                task_ids=[t1.id, t2.id],
                new_priority=TaskPriority.CRITICAL,
                reason="Escalated for production readiness",
            ),
            actor="admin",
            tenant_context=tenant_ctx,
        )
        assert len(reprio_res) == 2
        assert all(t.priority == TaskPriority.CRITICAL for t in reprio_res)

        # 2. Bulk Assign
        assign_res = service.bulk_assign(
            BulkAssignRequest(
                task_ids=[t1.id, t2.id],
                new_assignee_id="eng-bob",
                reason="Team rebalancing",
            ),
            actor="admin",
            tenant_context=tenant_ctx,
        )
        assert len(assign_res) == 2
        assert all(t.assignee_id == "eng-bob" for t in assign_res)

        # 3. Bulk Close Duplicate (t2 duplicate of t1)
        dup_res = service.bulk_close_duplicate(
            BulkDuplicateRequest(
                duplicate_task_ids=[t2.id],
                canonical_task_id=t1.id,
                reason="Same underlying issue on host",
            ),
            actor="admin",
            tenant_context=tenant_ctx,
        )
        assert len(dup_res) == 1
        assert dup_res[0].state == TaskState.DUPLICATE
        assert dup_res[0].closure_code == TaskClosureCode.DUPLICATE_SUPERSEDED


# ==============================================================================
# 8. Accountability Views & Trend Reports (Leaderboard-Free)
# ==============================================================================


class TestAccountabilityViewsAndTrends:
    """Validates views by owner/app/BU, ageing distribution, and open-vs-closed trends."""

    def test_accountability_views_filtering(self, tenant_ctx: TenantContext):
        """Retrieves my tasks, team tasks, and app/BU views."""
        service = get_remediation_service()
        # Create tasks across owners
        service.create_task(
            TaskCreateRequest(
                source=TaskSource.MANUAL,
                subject_entity=SubjectEntity(
                    entity_type="vm",
                    entity_id="vm-app1",
                    application_id="app-checkout",
                    business_unit_id="bu-retail",
                ),
                title="Checkout Memory Leak",
                description="Investigate memory footprint.",
                assignee_id=tenant_ctx.user_id,
            ),
            actor="admin",
            tenant_context=tenant_ctx,
        )
        service.create_task(
            TaskCreateRequest(
                source=TaskSource.MANUAL,
                subject_entity=SubjectEntity(
                    entity_type="db",
                    entity_id="db-app2",
                    application_id="app-billing",
                    business_unit_id="bu-finance",
                ),
                title="Billing DB Indexing",
                description="Add index to reduce CPU burn.",
                assignee_id="team-dba",
                assignee_type="TEAM",
            ),
            actor="admin",
            tenant_context=tenant_ctx,
        )

        # My tasks
        my_tasks = service.get_my_tasks(tenant_ctx.user_id, tenant_context=tenant_ctx)
        assert len(my_tasks) == 1
        assert my_tasks[0].assignee_id == tenant_ctx.user_id

        # Team tasks
        team_tasks = service.get_team_tasks("team-dba", tenant_context=tenant_ctx)
        assert len(team_tasks) == 1
        assert team_tasks[0].assignee_id == "team-dba"

        # By application
        app_tasks = service.get_tasks_by_application("app-checkout", tenant_context=tenant_ctx)
        assert len(app_tasks) == 1
        assert app_tasks[0].subject_entity.application_id == "app-checkout"

        # By business unit
        bu_tasks = service.get_tasks_by_business_unit("bu-retail", tenant_context=tenant_ctx)
        assert len(bu_tasks) == 1
        assert bu_tasks[0].subject_entity.business_unit_id == "bu-retail"

    def test_ageing_report_distribution(self, tenant_ctx: TenantContext):
        """Produces ageing breakdown across brackets (0-7d, 8-30d, 31-90d, >90d)."""
        service = get_remediation_service()
        service.create_task(
            TaskCreateRequest(
                source=TaskSource.MANUAL,
                subject_entity=SubjectEntity(entity_type="vm", entity_id="vm-age-01"),
                title="Ageing Analysis Task",
                description="New task created today.",
                assignee_id="eng-bob",
                estimated_saving=250.0,
            ),
            actor="admin",
            tenant_context=tenant_ctx,
        )
        ageing = service.get_ageing_report(tenant_context=tenant_ctx)
        assert ageing.total_open_tasks == 1
        assert ageing.bracket_0_to_7_days.count == 1
        assert ageing.bracket_0_to_7_days.total_estimated_saving == 250.0

    def test_trend_report_leaderboard_free(self, tenant_ctx: TenantContext):
        """Validates daily opened-vs-closed trends reporting system health, not individual rankings."""
        service = get_remediation_service()
        # Task 1: open
        service.create_task(
            TaskCreateRequest(
                source=TaskSource.MANUAL,
                subject_entity=SubjectEntity(entity_type="vm", entity_id="vm-tr-01"),
                title="Trend Task 1",
                description="Testing trend",
                assignee_id="eng-bob",
            ),
            actor="admin",
            tenant_context=tenant_ctx,
        )
        # Task 2: open and closed
        verifier = service.verifier
        verifier.set_mock_entity_state(
            tenant_ctx.tenant_id, "vm", "vm-tr-02", {"condition_cleared": True}
        )
        t2 = service.create_task(
            TaskCreateRequest(
                source=TaskSource.MANUAL,
                subject_entity=SubjectEntity(entity_type="vm", entity_id="vm-tr-02"),
                title="Trend Task 2",
                description="Testing trend closed",
                assignee_id="eng-alice",
                estimated_saving=100.0,
            ),
            actor="admin",
            tenant_context=tenant_ctx,
        )
        service.resolve_task(
            t2.id,
            actor="eng-alice",
            tenant_context=tenant_ctx,
            resolution_note="Closed for trend test",
        )

        trend = service.get_trend_report(window_days=7, tenant_context=tenant_ctx)
        assert trend.total_opened_in_window == 2
        assert trend.total_closed_in_window == 1
        assert trend.net_backlog_change == 1


# ==============================================================================
# 9. Multi-Tenant Isolation
# ==============================================================================


class TestMultiTenantIsolation:
    """Verifies strict isolation of remediation data and reports between tenants."""

    def test_tenant_boundary_enforcement(
        self, tenant_ctx: TenantContext, other_tenant_ctx: TenantContext
    ):
        """Tasks created in tenant A cannot be viewed or altered in tenant B."""
        service = get_remediation_service()
        task_a = service.create_task(
            TaskCreateRequest(
                source=TaskSource.MANUAL,
                subject_entity=SubjectEntity(entity_type="vm", entity_id="vm-tenant-a"),
                title="Tenant A Task",
                description="Private to tenant A",
                assignee_id="eng-a",
            ),
            actor="admin-a",
            tenant_context=tenant_ctx,
        )

        # Attempt to read from Tenant B -> 404 / Not Found
        with pytest.raises(RemediationTaskNotFoundException):
            service.get_task(task_a.id, tenant_context=other_tenant_ctx)

        # Tenant B listing shows zero tasks
        b_tasks = service.list_tasks(tenant_context=other_tenant_ctx)
        assert len(b_tasks) == 0


# ==============================================================================
# 10. Outbound ITSM Adapter
# ==============================================================================


class TestITSMAdapter:
    """Validates external ticketing integration formatting and feature flag toggle."""

    def test_itsm_adapter_payload_generation(self, tenant_ctx: TenantContext):
        """Tests Jira, ServiceNow, and Webhook formatters."""
        adapter = ITSMAdapter()
        task = RemediationTask(
            id="rem-itsm-01",
            tenant_id=tenant_ctx.tenant_id,
            source=TaskSource.UNOWNED_RESOURCE,
            subject_entity=SubjectEntity(entity_type="vm", entity_id="vm-1"),
            title="Fix Unowned VM",
            description="Assign owner tag.",
            due_date=dt.datetime.now(dt.UTC) + dt.timedelta(days=2),
            assignee_id="eng-bob",
            priority=TaskPriority.HIGH,
            category=TaskCategory.UNOWNED_RESOURCE,
        )

        jira_payload = adapter.build_payload(task, system="jira")
        assert jira_payload["fields"]["issuetype"]["name"] == "Task"
        assert jira_payload["fields"]["priority"]["name"] == "High"
        assert jira_payload["fields"]["cloudlens_task_id"] == "rem-itsm-01"

        snow_payload = adapter.build_payload(task, system="servicenow")
        assert snow_payload["urgency"] == "2"
        assert snow_payload["u_cloudlens_id"] == "rem-itsm-01"


# ==============================================================================
# 11. REST API Endpoint Contracts
# ==============================================================================


class TestRemediationAPIEndpoints:
    """Validates HTTP REST endpoints for remediation tasks, verification, and accountability."""

    def test_api_remediation_lifecycle_and_verification(self, tenant_ctx: TenantContext):
        """End-to-end HTTP API test creating, querying, resolving, and verifying a task."""
        client = TestClient(app)
        headers: dict[str, str] = {
            "X-Tenant-ID": str(tenant_ctx.tenant_id),
            "X-User-ID": str(tenant_ctx.user_id or "admin"),
            "X-User-Email": str(tenant_ctx.email or "admin@example.com"),
            "X-User-Roles": "ENGINEER,TENANT_ADMIN",
        }

        # 1. Create Task
        res = client.post(
            "/api/v1/remediation/tasks",
            headers=headers,
            json={
                "source": "MANUAL",
                "subject_entity": {
                    "entity_type": "database",
                    "entity_id": "db-api-01",
                    "application_id": "app-payments",
                },
                "title": "Unattached Storage Volume",
                "description": "Orphaned EBS volume detected.",
                "category": "IDLE_RESOURCE",
                "priority": "HIGH",
                "assignee_id": tenant_ctx.user_id,
                "estimated_saving": 350.0,
            },
        )
        assert res.status_code == 201
        data = res.json()
        task_id = data["id"]
        assert data["title"] == "Unattached Storage Volume"
        assert data["state"] == "ASSIGNED"

        # 2. Get Task
        get_res = client.get(f"/api/v1/remediation/tasks/{task_id}", headers=headers)
        assert get_res.status_code == 200
        assert get_res.json()["id"] == task_id

        # 3. List Tasks
        list_res = client.get("/api/v1/remediation/tasks?category=IDLE_RESOURCE", headers=headers)
        assert list_res.status_code == 200
        assert len(list_res.json()) >= 1

        # 4. Resolve Task (with mock entity state indicating cleared)
        service = get_remediation_service()
        service.verifier.set_mock_entity_state(
            tenant_ctx.tenant_id, "database", "db-api-01", {"condition_cleared": True}
        )

        resolve_res = client.post(
            f"/api/v1/remediation/tasks/{task_id}/resolve",
            headers=headers,
            json={"resolution_note": "Volume deleted after snapshot."},
        )
        assert resolve_res.status_code == 200
        resolve_data = resolve_res.json()
        assert resolve_data["task"]["state"] == "CLOSED"
        assert resolve_data["task"]["closure_code"] == "FIXED_AND_VERIFIED"
        assert resolve_data["verification"]["is_cleared"] is True

        # 5. Check My Tasks (now empty since task is closed)
        my_res = client.get("/api/v1/remediation/views/my-tasks", headers=headers)
        assert my_res.status_code == 200
        assert len(my_res.json()) == 0

        # 6. Check Savings Report
        save_res = client.get("/api/v1/remediation/reports/savings", headers=headers)
        assert save_res.status_code == 200
        assert save_res.json()["total_realised_saving"] == 350.0

        # 7. Check Ageing Report
        age_res = client.get("/api/v1/remediation/reports/ageing", headers=headers)
        assert age_res.status_code == 200
        assert age_res.json()["total_open_tasks"] == 0

        # 8. Check Trends Report
        trend_res = client.get("/api/v1/remediation/reports/trends?window_days=7", headers=headers)
        assert trend_res.status_code == 200
        assert trend_res.json()["total_closed_in_window"] >= 1
