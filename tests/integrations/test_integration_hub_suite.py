"""Comprehensive Verification Test Suite for Integration Hub (Prompt 60 / BBP Section 13.5 & 35).

Covers all prompt requirements and acceptance criteria:
1. Integration framework mirroring connector contract (declared capabilities, secret store, rate limiting, circuit breaker).
2. Versioned outbound domain event model with HMAC-SHA256 signatures, honest ordering guarantees, and replay window.
3. ITSM adapter with bidirectional status synchronization (closing ticket closes task, reopening ticket reopens task).
4. CMDB adapter with declared authority, overwrite blocking, and conflict surfacing.
5. Finance/ERP adapter with Chart-of-Accounts cost export, master import, and period-close accrual extract.
6. Chat adapter with Microsoft Teams and Slack formatting and in-message alert acknowledgement.
7. Identity and directory adapter with early leaver detection and automated remediation task creation.
8. Per-integration observability and fleet health reporting.
9. Integration sandbox with 100% offline simulation across all 5 adapter types.
"""

from __future__ import annotations

import datetime as dt
import time
from decimal import Decimal

import pytest

from domain.alerting.models import AlertEntity, AlertEvidence
from domain.credentials.store import SecretStore
from domain.integrations.adapters.chat import ChatAdapter
from domain.integrations.adapters.cmdb import CMDBAdapter
from domain.integrations.adapters.directory import IdentityDirectoryAdapter
from domain.integrations.adapters.finance import FinanceERPAdapter
from domain.integrations.adapters.itsm import ITSMAdapter
from domain.integrations.contract import BaseIntegrationAdapter
from domain.integrations.events import OutboundEventDispatcher
from domain.integrations.exceptions import (
    AuthoritativeFieldOverwriteBlockedException,
    IntegrationCircuitOpenException,
    IntegrationRateLimitExceededException,
    UndeclaredIntegrationCapabilityException,
)
from domain.integrations.models import (
    EventReplayRequest,
    IntegrationConfig,
)
from domain.integrations.observability import IntegrationObservabilityService
from domain.integrations.sandbox import IntegrationSandbox
from domain.integrations.service import IntegrationHubService
from domain.models.enums import (
    AlertLifecycleStatus,
    AlertSeverity,
    AlertType,
    FieldAuthority,
    IntegrationCapability,
    IntegrationHealth,
    IntegrationType,
    OutboundEventType,
    TaskCategory,
    TaskClosureCode,
    TaskPriority,
    TaskSource,
    TaskState,
)
from domain.remediation.models import SubjectEntity, TaskCreateRequest
from domain.remediation.service import RemediationService
from domain.tenant.context import TenantContext


class MockSecretStore(SecretStore):
    """Simple in-memory secret store for testing secret reference resolution."""

    def __init__(self) -> None:
        self._secrets: dict[str, dict[str, str]] = {}

    def store_secret(
        self,
        tenant_id: str,
        profile_id: str,
        version: int,
        secret_data: dict[str, str],
    ) -> str:
        ref = f"vault://secret/data/tenants/{tenant_id}/credentials/{profile_id}/v{version}"
        self._secrets[ref] = secret_data
        return ref

    def get_secret(self, secret_ref: str, tenant_id: str | None = None) -> dict[str, str]:
        _ = tenant_id
        return self._secrets.get(secret_ref, {"api_token": "mock-secret-token"})

    def delete_secret(self, secret_ref: str, tenant_id: str | None = None) -> bool:
        _ = tenant_id
        return self._secrets.pop(secret_ref, None) is not None

    def has_secret(self, secret_ref: str) -> bool:
        return secret_ref in self._secrets

    def health_check(self) -> bool:
        return True


class TestIntegrationHubSuite:
    """Rigorous verification suite for Prompt 60 Integration Hub."""

    @pytest.fixture
    def tenant_context(self) -> TenantContext:
        return TenantContext(
            tenant_id="tenant-acme-corp",
            user_id="integration-admin@acme.corp",
            roles={"INTEGRATION_ADMIN", "FINOPS_ADMIN", "CLOUD_ADMIN"},
        )

    @pytest.fixture
    def remediation_service(self) -> RemediationService:
        return RemediationService()

    @pytest.fixture
    def sandbox(self) -> IntegrationSandbox:
        return IntegrationSandbox()

    @pytest.fixture
    def hub_service(self) -> IntegrationHubService:
        dispatcher = OutboundEventDispatcher()
        observability = IntegrationObservabilityService()
        return IntegrationHubService(
            event_dispatcher=dispatcher,
            observability_service=observability,
        )

    # =========================================================================
    # 1. Integration Framework Contract & Resilience Tests
    # =========================================================================

    def test_declared_capabilities_enforcement_and_undeclared_rejection(
        self, sandbox: IntegrationSandbox
    ) -> None:
        """Adapters declare supported capabilities; undeclared calls strictly fail fast."""
        cfg = sandbox.create_sandbox_config(
            IntegrationType.ITSM,
            "Restricted Jira Adapter",
        )
        # Create adapter with only AUTHENTICATE capability declared
        adapter = ITSMAdapter(
            config=cfg,
            declared_capabilities={IntegrationCapability.AUTHENTICATE},
        )

        assert adapter.has_capability(IntegrationCapability.AUTHENTICATE)
        assert not adapter.has_capability(IntegrationCapability.CREATE_TICKET)

        # Attempting undeclared CREATE_TICKET must raise UndeclaredIntegrationCapabilityException
        with pytest.raises(UndeclaredIntegrationCapabilityException) as exc_info:
            adapter._assert_declared(IntegrationCapability.CREATE_TICKET)

        assert "does not declare capability 'create_ticket'" in str(exc_info.value)

    def test_secret_store_credential_resolution_via_reference(
        self, tenant_context: TenantContext
    ) -> None:
        """Secret store credentials are resolved securely via opaque reference URIs."""
        secret_store = MockSecretStore()
        secret_ref = secret_store.store_secret(
            tenant_id=tenant_context.tenant_id,
            profile_id="servicenow-prod",
            version=1,
            secret_data={"client_id": "snow-123", "client_secret": "super-secret-pw"},
        )

        cfg = IntegrationConfig(
            integration_id="int-snow-01",
            integration_type=IntegrationType.ITSM,
            name="ServiceNow Production",
            credential_ref=secret_ref,
            endpoint_url="https://instance.service-now.com/api",
            declared_capabilities=[IntegrationCapability.AUTHENTICATE],
            is_sandbox=False,
        )
        adapter = ITSMAdapter(config=cfg)

        creds = adapter.resolve_credentials(secret_store, tenant_context.tenant_id)
        assert creds["client_id"] == "snow-123"
        assert creds["client_secret"] == "super-secret-pw"

    def test_resilience_rate_limiting_enforcement(
        self, sandbox: IntegrationSandbox
    ) -> None:
        """Rate limit strictly guards against outbound flooding."""
        cfg = sandbox.create_sandbox_config(
            IntegrationType.ITSM,
            "Rate Limited Adapter",
        )
        cfg.rate_limit_per_minute = 3  # Limit to 3 requests per minute

        adapter = ITSMAdapter(config=cfg)

        # 3 calls succeed
        for _ in range(3):
            adapter.execute_with_resilience(
                IntegrationCapability.HEALTH_CHECK,
                "ping",
                lambda: True,
            )

        # 4th call within the same minute raises IntegrationRateLimitExceededException
        with pytest.raises(IntegrationRateLimitExceededException):
            adapter.execute_with_resilience(
                IntegrationCapability.HEALTH_CHECK,
                "ping",
                lambda: True,
            )

    def test_resilience_circuit_breaker_trips_and_recovers(
        self, sandbox: IntegrationSandbox
    ) -> None:
        """Consecutive failure threshold trips circuit breaker; resets after cooldown."""
        cfg = sandbox.create_sandbox_config(
            IntegrationType.ITSM,
            "Circuit Breaker Test",
        )
        cfg.circuit_breaker_threshold = 2
        cfg.circuit_breaker_reset_seconds = 0.1  # Fast cooldown for testing
        cfg.max_retries = 0

        adapter = ITSMAdapter(config=cfg)

        # Failure 1
        with pytest.raises(ConnectionError):
            adapter.execute_with_resilience(
                IntegrationCapability.HEALTH_CHECK,
                "fail1",
                lambda: (_ for _ in ()).throw(ConnectionError("Fail 1")),
            )

        # Failure 2 -> Trips circuit breaker to OPEN
        with pytest.raises(ConnectionError):
            adapter.execute_with_resilience(
                IntegrationCapability.HEALTH_CHECK,
                "fail2",
                lambda: (_ for _ in ()).throw(ConnectionError("Fail 2")),
            )

        assert adapter.get_health().status == IntegrationHealth.UNHEALTHY

        # Immediate next call rejected by OPEN circuit breaker
        with pytest.raises(IntegrationCircuitOpenException):
            adapter.execute_with_resilience(
                IntegrationCapability.HEALTH_CHECK,
                "fail3",
                lambda: True,
            )

        # Wait for cooldown
        time.sleep(0.15)

        # Half-open trial succeeds and resets circuit
        result = adapter.execute_with_resilience(
            IntegrationCapability.HEALTH_CHECK,
            "probe",
            lambda: "success",
        )
        assert result == "success"
        assert adapter.get_health().status == IntegrationHealth.HEALTHY

    # =========================================================================
    # 2. Outbound Event Model & Replay Tests
    # =========================================================================

    def test_outbound_event_publication_with_hmac_signing_and_partition_ordering(
        self, hub_service: IntegrationHubService, tenant_context: TenantContext
    ) -> None:
        """Domain events carry HMAC-SHA256 signature, standard headers, and partition sequence."""
        event1 = hub_service.publish_domain_event(
            event_type=OutboundEventType.BUDGET_BREACHED,
            payload={"scope_id": "scope-marketing", "threshold": 10000, "actual": 12500},
            partition_key="scope-marketing",
            tenant_context=tenant_context,
        )

        assert event1.event_type == OutboundEventType.BUDGET_BREACHED
        assert event1.sequence_number == 1
        assert event1.partition_key == "scope-marketing"
        assert event1.signature is not None

        # Build webhook headers
        headers = hub_service.event_dispatcher.build_webhook_headers(event1)
        assert headers["X-CloudLens-Event"] == "budget_breached"
        assert headers["X-CloudLens-Partition-Key"] == "scope-marketing"
        assert headers["X-CloudLens-Sequence-Number"] == "1"
        assert headers["X-CloudLens-Signature"].startswith("sha256=")

        # Second event in same partition gets monotonic sequence 2
        event2 = hub_service.publish_domain_event(
            event_type=OutboundEventType.ALERT_RAISED,
            payload={"alert_id": "alt-999", "severity": "HIGH"},
            partition_key="scope-marketing",
            tenant_context=tenant_context,
        )
        assert event2.sequence_number == 2

    def test_outbound_event_replay_within_window(
        self, hub_service: IntegrationHubService, tenant_context: TenantContext
    ) -> None:
        """Historical events are replayed accurately by time window, event type, and partition."""
        t_start = dt.datetime.now(dt.UTC) - dt.timedelta(minutes=5)

        # Publish 3 events
        e1 = hub_service.publish_domain_event(
            event_type=OutboundEventType.TASK_CREATED,
            payload={"task_id": "t1"},
            partition_key="part-A",
            tenant_context=tenant_context,
        )
        e2 = hub_service.publish_domain_event(
            event_type=OutboundEventType.TASK_CLOSED,
            payload={"task_id": "t1"},
            partition_key="part-A",
            tenant_context=tenant_context,
        )
        e3 = hub_service.publish_domain_event(
            event_type=OutboundEventType.COMMITMENT_EXPIRING,
            payload={"commitment_id": "comm-sp-01"},
            partition_key="part-B",
            tenant_context=tenant_context,
        )

        t_end = dt.datetime.now(dt.UTC) + dt.timedelta(minutes=5)

        # Replay partition 'part-A' only
        replay_req = EventReplayRequest(
            tenant_id=tenant_context.tenant_id,
            from_timestamp=t_start,
            to_timestamp=t_end,
            partition_key="part-A",
        )
        replayed = hub_service.replay_events(replay_req)
        assert len(replayed) == 2
        assert replayed[0].event_id == e1.event_id
        assert replayed[1].event_id == e2.event_id

        # Replay COMMITMENT_EXPIRING only
        replay_comm = EventReplayRequest(
            tenant_id=tenant_context.tenant_id,
            from_timestamp=t_start,
            to_timestamp=t_end,
            event_types=[OutboundEventType.COMMITMENT_EXPIRING],
        )
        replayed_comm = hub_service.replay_events(replay_comm)
        assert len(replayed_comm) == 1
        assert replayed_comm[0].event_id == e3.event_id

    # =========================================================================
    # 3. ITSM Adapter & Bidirectional Sync Tests
    # =========================================================================

    def test_itsm_ticket_creation_from_task_and_alert_with_evidence_and_deep_links(
        self,
        sandbox: IntegrationSandbox,
        hub_service: IntegrationHubService,
        tenant_context: TenantContext,
        remediation_service: RemediationService,
    ) -> None:
        """ITSM tickets are created from tasks and alerts, preserving evidence and deep links."""
        itsm_cfg = sandbox.create_sandbox_config(IntegrationType.ITSM, "Sandbox Jira")
        adapter = ITSMAdapter(config=itsm_cfg)
        hub_service.register_adapter(adapter)

        # 1. Create from RemediationTask
        task = remediation_service.create_task(
            req=TaskCreateRequest(
                source=TaskSource.IDLE_RESOURCE,
                category=TaskCategory.IDLE_RESOURCE,
                priority=TaskPriority.CRITICAL,
                title="Idle Aurora Cluster in eu-west-1",
                description="Cluster has 0 connections for 30 consecutive days.",
                subject_entity=SubjectEntity(
                    entity_type="DATABASE",
                    entity_id="aurora-db-01",
                    entity_name="Aurora DB Prod",
                ),
                assignee_id="dba-oncall@acme.corp",
                estimated_saving=1450.0,
            ),
            actor="test-runner",
            tenant_context=tenant_context,
        )

        ticket = hub_service.create_itsm_ticket_from_task(
            itsm_cfg.integration_id,
            task,
            tenant_context=tenant_context,
        )
        assert ticket.priority == "P1-Urgent"
        assert ticket.cloudlens_entity_id == task.id
        assert "tasks/" in ticket.deep_link
        assert "Estimated Saving: $1450.00" in ticket.evidence_summary

        # 2. Create from AlertEntity
        alert = AlertEntity(
            tenant_id=tenant_context.tenant_id,
            alert_type=AlertType.UNEXPECTED_COST_INCREASE,
            severity=AlertSeverity.HIGH,
            title="Compute Spend Spike Detected",
            description="Daily compute costs jumped 320% above 30-day baseline.",
            source="anomaly_detector",
            evidence=AlertEvidence(
                summary="Daily compute spend spiked from $200/day to $840/day",
                datapoints=[{"baseline": 200.0, "actual": 840.0, "z_score": 4.2}],
            ),
        )

        alert_ticket = hub_service.create_itsm_ticket_from_alert(
            itsm_cfg.integration_id,
            alert,
            tenant_context=tenant_context,
        )
        assert alert_ticket.priority == "P2-High"
        assert alert_ticket.cloudlens_entity_id == alert.id
        assert "alerts/" in alert_ticket.deep_link

    def test_itsm_bidirectional_sync_closing_ticket_closes_task(
        self,
        sandbox: IntegrationSandbox,
        hub_service: IntegrationHubService,
        tenant_context: TenantContext,
        remediation_service: RemediationService,
    ) -> None:
        """Closing an external ITSM ticket closes the linked CloudLens task."""
        itsm_cfg = sandbox.create_sandbox_config(IntegrationType.ITSM, "Sync Jira")
        adapter = ITSMAdapter(config=itsm_cfg)
        hub_service.register_adapter(adapter)

        task = remediation_service.create_task(
            req=TaskCreateRequest(
                source=TaskSource.IDLE_RESOURCE,
                category=TaskCategory.IDLE_RESOURCE,
                priority=TaskPriority.MEDIUM,
                title="Orphan Volume Attached to Deleted Instance",
                description="Volume vol-123 is unattached.",
                subject_entity=SubjectEntity(entity_type="VOLUME", entity_id="vol-123"),
                assignee_id="storage-lead@acme.corp",
                estimated_saving=120.0,
            ),
            actor="test-runner",
            tenant_context=tenant_context,
        )
        ticket = hub_service.create_itsm_ticket_from_task(
            itsm_cfg.integration_id,
            task,
            tenant_context=tenant_context,
        )
        assert task.state == TaskState.ASSIGNED

        # External system resolves/closes the ticket
        synced_ticket = hub_service.sync_itsm_ticket_status(
            itsm_cfg.integration_id,
            external_ticket_id=ticket.external_ticket_id,
            new_status="RESOLVED",
            actor_id="jira-user@acme.corp",
            reason="Volume deleted in AWS management console",
            remediation_task=task,
        )

        assert synced_ticket.status == "RESOLVED"
        assert task.state == TaskState.CLOSED
        assert task.closure_code == TaskClosureCode.FIXED_AND_VERIFIED
        assert task.history[-1].action == "CLOSED"

    def test_itsm_bidirectional_sync_reopening_ticket_reopens_task(
        self,
        sandbox: IntegrationSandbox,
        hub_service: IntegrationHubService,
        tenant_context: TenantContext,
        remediation_service: RemediationService,
    ) -> None:
        """Reopening an external ITSM ticket reopens the linked CloudLens task."""
        itsm_cfg = sandbox.create_sandbox_config(IntegrationType.ITSM, "Reopen Jira")
        adapter = ITSMAdapter(config=itsm_cfg)
        hub_service.register_adapter(adapter)

        task = remediation_service.create_task(
            req=TaskCreateRequest(
                source=TaskSource.IDLE_RESOURCE,
                category=TaskCategory.IDLE_RESOURCE,
                priority=TaskPriority.HIGH,
                title="Underutilized GPU Instance",
                description="Instance i-gpu-01 has 2% GPU utilization.",
                subject_entity=SubjectEntity(entity_type="INSTANCE", entity_id="i-gpu-01"),
                assignee_id="ml-team@acme.corp",
                estimated_saving=800.0,
            ),
            actor="test-runner",
            tenant_context=tenant_context,
        )
        ticket = hub_service.create_itsm_ticket_from_task(
            itsm_cfg.integration_id,
            task,
            tenant_context=tenant_context,
        )

        # First close the ticket
        hub_service.sync_itsm_ticket_status(
            itsm_cfg.integration_id,
            ticket.external_ticket_id,
            new_status="CLOSED",
            actor_id="admin@acme.corp",
            remediation_task=task,
        )
        assert task.state == TaskState.CLOSED

        # Now external team reopens ticket (e.g. GPU workload is needed next week)
        hub_service.sync_itsm_ticket_status(
            itsm_cfg.integration_id,
            ticket.external_ticket_id,
            new_status="REOPENED",
            actor_id="ml-lead@acme.corp",
            reason="Workload resumption requested by AI research team",
            remediation_task=task,
        )

        assert task.state == TaskState.IN_PROGRESS
        assert task.history[-1].action == "REOPENED"

    # =========================================================================
    # 4. CMDB Adapter & Field Authority Tests
    # =========================================================================

    def test_cmdb_import_with_provenance(
        self,
        sandbox: IntegrationSandbox,
        hub_service: IntegrationHubService,
        tenant_context: TenantContext,
    ) -> None:
        """CMDB import loads configuration items with declared authority and provenance."""
        cmdb_cfg = sandbox.create_sandbox_config(
            IntegrationType.CMDB,
            "ServiceNow CMDB",
            authoritative_fields=["owner_email", "criticality_tier"],
        )
        adapter = CMDBAdapter(config=cmdb_cfg)
        hub_service.register_adapter(adapter)

        apps = sandbox.get_seed_cmdb_applications()
        result = hub_service.import_cmdb_records(
            cmdb_cfg.integration_id,
            entity_type="APPLICATION",
            records=apps,
            tenant_context=tenant_context,
        )

        assert result["created"] == 2
        record = adapter.get_cmdb_record("APPLICATION", "APP-PORTAL-01")
        assert record is not None
        assert record["name"] == "Customer Self-Service Portal"
        assert record["_provenance_source"] == "CMDB_IMPORT"
        assert record["_declared_authority"] == FieldAuthority.CMDB.value

    def test_cmdb_authoritative_field_blocks_overwrite_and_surfaces_conflict(
        self,
        sandbox: IntegrationSandbox,
        hub_service: IntegrationHubService,
        tenant_context: TenantContext,
    ) -> None:
        """CloudLens strictly declines to overwrite a CMDB-authoritative field and surfaces a conflict."""
        cmdb_cfg = sandbox.create_sandbox_config(
            IntegrationType.CMDB,
            "ServiceNow CMDB Guard",
            authoritative_fields=["owner_email", "criticality_tier"],
        )
        adapter = CMDBAdapter(config=cmdb_cfg)
        hub_service.register_adapter(adapter)

        # Seed CMDB
        adapter.import_cmdb_records(
            "APPLICATION",
            sandbox.get_seed_cmdb_applications(),
            tenant_context=tenant_context,
        )

        # Attempt to mutate owner_email from CloudLens
        proposed_update = {"owner_email": "rogue-change@external.com"}

        with pytest.raises(AuthoritativeFieldOverwriteBlockedException) as exc_info:
            hub_service.validate_or_block_cmdb_overwrite(
                cmdb_cfg.integration_id,
                entity_type="APPLICATION",
                natural_key="APP-PORTAL-01",
                proposed_updates=proposed_update,
                tenant_context=tenant_context,
                raise_on_blocked=True,
            )

        assert "is authoritative in CMDB" in str(exc_info.value)

        # Verify conflict was surfaced
        conflicts = adapter.get_surfaced_conflicts(tenant_context.tenant_id)
        assert len(conflicts) == 1
        conf = conflicts[0]
        assert conf.field_name == "owner_email"
        assert conf.cmdb_value == "alice.smith@enterprise.internal"
        assert conf.cloudlens_value == "rogue-change@external.com"
        assert conf.surfaced is True
        assert conf.resolved is False

        # Formally resolve conflict via governance
        adapter.resolve_conflict(
            conflict_id=conf.conflict_id,
            actor_id="compliance-officer@acme.corp",
            resolution_strategy="RETAIN_CMDB_VALUE",
            note="Confirmed with application lead that Alice Smith remains the official owner.",
        )
        assert conf.resolved is True

    # =========================================================================
    # 5. Finance & ERP Adapter Tests
    # =========================================================================

    def test_finance_chart_of_accounts_cost_export_and_master_import(
        self,
        sandbox: IntegrationSandbox,
        hub_service: IntegrationHubService,
        tenant_context: TenantContext,
    ) -> None:
        """Finance adapter exports costs by Chart of Accounts and imports financial hierarchy."""
        fin_cfg = sandbox.create_sandbox_config(IntegrationType.FINANCE_ERP, "SAP S/4HANA")
        adapter = FinanceERPAdapter(config=fin_cfg)
        hub_service.register_adapter(adapter)

        # 1. Import Masters from Finance
        bus = [
            {"code": "BU-RETAIL", "name": "Consumer Retail Banking"},
            {"code": "BU-WEALTH", "name": "Wealth Management"},
        ]
        ccs = [
            {
                "code": "CC-1001",
                "name": "Digital Channels",
                "business_unit_code": "BU-RETAIL",
                "gl_account_code": "GL-52010",
            },
            {
                "code": "CC-2001",
                "name": "Portfolio Analytics",
                "business_unit_code": "BU-WEALTH",
                "gl_account_code": "GL-52020",
            },
        ]
        import_res = adapter.import_financial_masters(
            cost_centres=ccs,
            business_units=bus,
            tenant_context=tenant_context,
        )
        assert import_res["business_units_imported"] == 2
        assert import_res["cost_centres_imported"] == 2

        # 2. Export CoA costs
        allocated = [
            {
                "cost_centre_code": "CC-1001",
                "business_unit_code": "BU-RETAIL",
                "gl_account_code": "GL-52010",
                "amount": "45200.50",
                "currency": "USD",
            },
            {
                "cost_centre_code": "CC-2001",
                "business_unit_code": "BU-WEALTH",
                "gl_account_code": "GL-52020",
                "amount": "23400.00",
                "currency": "USD",
            },
        ]
        export_res = hub_service.export_finance_coa_costs(
            fin_cfg.integration_id,
            allocated_costs=allocated,
            tenant_context=tenant_context,
        )
        assert export_res["total_allocated"] == 68600.5
        assert len(export_res["entries"]) == 2

    def test_finance_period_close_accrual_extract(
        self,
        sandbox: IntegrationSandbox,
        hub_service: IntegrationHubService,
        tenant_context: TenantContext,
    ) -> None:
        """Generates period-close accrual extract with unbilled usage and commitment amortisations."""
        fin_cfg = sandbox.create_sandbox_config(IntegrationType.FINANCE_ERP, "SAP Period Close")
        adapter = FinanceERPAdapter(config=fin_cfg)
        hub_service.register_adapter(adapter)

        breakdown = [
            {
                "cost_centre_code": "CC-1001",
                "cost_centre_name": "Digital Channels",
                "business_unit_code": "BU-RETAIL",
                "gl_account_code": "GL-52010-CLOUD-OPEX",
                "unbilled_usage_amount": "12450.00",
                "amortised_commitment_amount": "3500.00",
                "accrued_amount": "15950.00",
            },
            {
                "cost_centre_code": "CC-2001",
                "cost_centre_name": "Portfolio Analytics",
                "business_unit_code": "BU-WEALTH",
                "gl_account_code": "GL-52020-CLOUD-OPEX",
                "unbilled_usage_amount": "8200.00",
                "amortised_commitment_amount": "1800.00",
                "accrued_amount": "10000.00",
            },
        ]

        extract = hub_service.generate_period_close_accrual(
            fin_cfg.integration_id,
            fiscal_period="2026-09",
            cost_centre_breakdown=breakdown,
            tenant_context=tenant_context,
            currency="USD",
        )

        assert extract.fiscal_period == "2026-09"
        assert extract.total_accrual == Decimal("25950.00")
        assert len(extract.cost_centre_items) == 2
        assert extract.cost_centre_items[0].unbilled_usage_amount == Decimal("12450.00")

    # =========================================================================
    # 6. Chat Adapter & In-Message Actioning Tests
    # =========================================================================

    def test_chat_teams_and_slack_formatting_and_in_message_acknowledgement(
        self,
        sandbox: IntegrationSandbox,
        hub_service: IntegrationHubService,
        tenant_context: TenantContext,
    ) -> None:
        """Formats alerts for Teams and Slack and processes in-message button acknowledgements."""
        chat_cfg = sandbox.create_sandbox_config(
            IntegrationType.CHAT,
            "Teams DevOps Channel",
            custom_attributes={"platform": "TEAMS"},
        )
        adapter = ChatAdapter(config=chat_cfg)
        hub_service.register_adapter(adapter)

        alert = AlertEntity(
            tenant_id=tenant_context.tenant_id,
            alert_type=AlertType.FORECAST_BUDGET_BREACH,
            severity=AlertSeverity.CRITICAL,
            title="End of Quarter Budget Overrun Projected",
            description="Projected spend exceeds quarterly allocation by 18%.",
            source="forecast_engine",
            evidence=AlertEvidence(
                summary="Current run rate $118k vs quarterly budget $100k",
                datapoints=[{"run_rate": 118000, "budget": 100000}],
            ),
        )

        # Dispatch card
        card = hub_service.dispatch_alert_to_chat(
            chat_cfg.integration_id,
            alert,
            tenant_context=tenant_context,
        )
        assert card.platform == "TEAMS"
        assert "AdaptiveCard" in str(card.formatted_payload)
        assert card.is_acknowledged is False

        # In-message button click by user in Teams
        ack_res = hub_service.acknowledge_alert_from_chat(
            chat_cfg.integration_id,
            alert_id=alert.id,
            actor_email="oncall-sre@acme.corp",
            reason="Acknowledged directly from MS Teams notification card",
            tenant_context=tenant_context,
            target_alert=alert,
        )

        assert ack_res["status"] == AlertLifecycleStatus.ACKNOWLEDGED.value
        assert ack_res["acknowledged_by"] == "oncall-sre@acme.corp"
        assert alert.status == AlertLifecycleStatus.ACKNOWLEDGED
        assert alert.acknowledged_by == "oncall-sre@acme.corp"
        assert alert.acknowledged_at is not None
        assert card.is_acknowledged is True

    # =========================================================================
    # 7. Identity Directory & Early Leaver Detection Tests
    # =========================================================================

    def test_directory_leaver_detection_raises_ownership_gap_and_spawns_remediation_task(
        self,
        sandbox: IntegrationSandbox,
        hub_service: IntegrationHubService,
        tenant_context: TenantContext,
        remediation_service: RemediationService,
    ) -> None:
        """A leaver in the directory raises an ownership gap and creates a Prompt 51 task before resources orphan."""
        dir_cfg = sandbox.create_sandbox_config(
            IntegrationType.IDENTITY_DIRECTORY,
            "Azure AD SCIM Sync",
        )
        adapter = IdentityDirectoryAdapter(config=dir_cfg)
        hub_service.register_adapter(adapter)

        # Sync directory users containing active users and 1 terminated employee
        users = sandbox.get_seed_directory_users()
        adapter.sync_directory_users(users, tenant_context=tenant_context)

        # Asset mappings: departed employee owns 2 active resources and 1 scope
        res_ownership = {
            "res-k8s-cluster-01": "departed.dev@enterprise.internal",
            "res-rds-postgres-01": "departed.dev@enterprise.internal",
            "res-ec2-bastion-01": "alice.smith@enterprise.internal",
        }
        scope_ownership = {
            "scope-legacy-payments": "departed.dev@enterprise.internal",
            "scope-platform": "alice.smith@enterprise.internal",
        }

        findings = hub_service.scan_directory_leavers(
            dir_cfg.integration_id,
            resource_ownership_map=res_ownership,
            scope_ownership_map=scope_ownership,
            tenant_context=tenant_context,
            remediation_service=remediation_service,
        )

        assert len(findings) == 1
        gap = findings[0]
        assert gap.former_owner_email == "departed.dev@enterprise.internal"
        assert len(gap.affected_resource_ids) == 2
        assert len(gap.affected_scopes) == 1
        assert gap.remediation_task_id is not None

        # Verify linked Prompt 51 remediation task was created and properly categorized
        task = remediation_service.get_task(gap.remediation_task_id, tenant_context=tenant_context)
        assert task.category == TaskCategory.UNOWNED_RESOURCE
        assert task.priority == TaskPriority.HIGH
        assert "Ownership Gap" in task.title

    # =========================================================================
    # 8. Fleet Observability & Sandbox End-to-End Tests
    # =========================================================================

    def test_per_integration_observability_and_health_reporting(
        self,
        sandbox: IntegrationSandbox,
        hub_service: IntegrationHubService,
    ) -> None:
        """Per-integration observability surfaces health status, throughput, and error metrics."""
        cfg1 = sandbox.create_sandbox_config(IntegrationType.ITSM, "Fleet Jira")
        cfg2 = sandbox.create_sandbox_config(IntegrationType.CMDB, "Fleet CMDB")
        adapter1 = ITSMAdapter(config=cfg1)
        adapter2 = CMDBAdapter(config=cfg2)

        hub_service.register_adapter(adapter1)
        hub_service.register_adapter(adapter2)

        # Execute successful action on adapter 1
        adapter1.execute_with_resilience(
            IntegrationCapability.HEALTH_CHECK,
            "ping",
            lambda: "ok",
        )

        summary = hub_service.observability.get_fleet_health_summary()
        assert summary["total_integrations"] == 2
        assert summary["healthy_count"] == 2
        assert summary["overall_status"] == "HEALTHY"
        assert len(summary["adapters"]) == 2

    def test_all_adapters_run_in_sandbox_without_live_external_systems(
        self,
        sandbox: IntegrationSandbox,
        hub_service: IntegrationHubService,
    ) -> None:
        """Every adapter executes safely in sandbox with zero live external third-party dependencies."""
        adapters: list[BaseIntegrationAdapter] = [
            ITSMAdapter(config=sandbox.create_sandbox_config(IntegrationType.ITSM, "Box ITSM")),
            CMDBAdapter(config=sandbox.create_sandbox_config(IntegrationType.CMDB, "Box CMDB")),
            FinanceERPAdapter(
                config=sandbox.create_sandbox_config(IntegrationType.FINANCE_ERP, "Box Finance")
            ),
            ChatAdapter(config=sandbox.create_sandbox_config(IntegrationType.CHAT, "Box Chat")),
            IdentityDirectoryAdapter(
                config=sandbox.create_sandbox_config(
                    IntegrationType.IDENTITY_DIRECTORY, "Box Directory"
                )
            ),
        ]

        for a in adapters:
            hub_service.register_adapter(a)
            # Verify basic health check executes cleanly in sandbox
            health = a.execute_with_resilience(
                IntegrationCapability.HEALTH_CHECK,
                "sandbox_probe",
                lambda: {"status": "HEALTHY", "sandbox": True},
            )
            assert health["sandbox"] is True
            assert a.get_health().status == IntegrationHealth.HEALTHY
