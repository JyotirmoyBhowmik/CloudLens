"""Integration Hub Master Service (Prompt 60 / BBP Section 13.5).

Unifies:
- Standardized adapter registration and lifecycle management mirroring cloud connectors.
- Outbound event publication, signing, and replay journaling.
- ITSM ticket creation and bidirectional task status synchronization.
- CMDB scheduled imports, declared field authority enforcement, and conflict surfacing.
- Finance/ERP Chart-of-Accounts cost exports and period-close accrual extracts.
- Microsoft Teams & Slack chat card dispatch and in-message alert acknowledgement.
- Corporate directory synchronization and proactive leaver ownership gap detection.
- Unified fleet observability and local sandbox simulation endpoints.
"""

from __future__ import annotations

import logging
from typing import Any

from domain.alerting.models import AlertEntity
from domain.integrations.adapters.chat import ChatAdapter
from domain.integrations.adapters.cmdb import CMDBAdapter
from domain.integrations.adapters.directory import IdentityDirectoryAdapter
from domain.integrations.adapters.finance import FinanceERPAdapter
from domain.integrations.adapters.itsm import ITSMAdapter
from domain.integrations.contract import BaseIntegrationAdapter
from domain.integrations.events import OutboundEventDispatcher
from domain.integrations.models import (
    CMDBConflictRecord,
    EventReplayRequest,
    ITSMTicket,
    OutboundEvent,
    PeriodCloseAccrualExtract,
)
from domain.integrations.observability import IntegrationObservabilityService
from domain.integrations.sandbox import IntegrationSandbox
from domain.models.enums import OutboundEventType
from domain.remediation.models import RemediationTask
from domain.remediation.service import RemediationService
from domain.tenant.context import TenantContext

logger = logging.getLogger(__name__)


class IntegrationHubService:
    """Master orchestrator for all external integrations across the enterprise."""

    def __init__(
        self,
        event_dispatcher: OutboundEventDispatcher | None = None,
        observability_service: IntegrationObservabilityService | None = None,
    ) -> None:
        self.event_dispatcher = event_dispatcher or OutboundEventDispatcher()
        self.observability = observability_service or IntegrationObservabilityService()
        self.sandbox = IntegrationSandbox()
        # Registry: integration_id -> BaseIntegrationAdapter
        self._adapters: dict[str, BaseIntegrationAdapter] = {}

    def register_adapter(self, adapter: BaseIntegrationAdapter) -> None:
        """Registers an integration adapter with the hub and observability service."""
        self._adapters[adapter.integration_id] = adapter
        self.observability.register_adapter(adapter)
        logger.info(
            "Registered integration adapter '%s' (%s) [Type: %s].",
            adapter.integration_id,
            adapter.name,
            adapter.integration_type.value,
        )

    def get_adapter(self, integration_id: str) -> BaseIntegrationAdapter:
        """Retrieves a registered adapter by ID."""
        adapter = self._adapters.get(integration_id)
        if not adapter:
            raise KeyError(f"Integration adapter '{integration_id}' is not registered.")
        return adapter

    def list_adapters(self) -> list[BaseIntegrationAdapter]:
        """Lists all registered integration adapters."""
        return list(self._adapters.values())

    # =========================================================================
    # Outbound Event Publication & Replay
    # =========================================================================

    def publish_domain_event(
        self,
        event_type: OutboundEventType | str,
        payload: dict[str, Any],
        partition_key: str,
        *,
        tenant_context: TenantContext,
        correlation_id: str | None = None,
    ) -> OutboundEvent:
        """Publishes a versioned domain event with partition sequencing and cryptographic signature."""
        return self.event_dispatcher.create_event(
            event_type=event_type,
            payload=payload,
            partition_key=partition_key,
            tenant_context=tenant_context,
            correlation_id=correlation_id,
        )

    def replay_events(self, request: EventReplayRequest) -> list[OutboundEvent]:
        """Replays journaled events within the specified time window."""
        return self.event_dispatcher.replay_events(request)

    # =========================================================================
    # ITSM Adapter Delegation
    # =========================================================================

    def create_itsm_ticket_from_task(
        self,
        integration_id: str,
        task: RemediationTask,
        *,
        tenant_context: TenantContext,
    ) -> ITSMTicket:
        """Creates an external ITSM ticket linked to a CloudLens remediation task."""
        adapter = self.get_adapter(integration_id)
        if not isinstance(adapter, ITSMAdapter):
            raise TypeError(f"Adapter '{integration_id}' is not an ITSMAdapter.")
        return adapter.create_ticket_from_task(task, tenant_context=tenant_context)

    def create_itsm_ticket_from_alert(
        self,
        integration_id: str,
        alert: AlertEntity,
        *,
        tenant_context: TenantContext,
    ) -> ITSMTicket:
        """Creates an external ITSM ticket linked to a CloudLens alert."""
        adapter = self.get_adapter(integration_id)
        if not isinstance(adapter, ITSMAdapter):
            raise TypeError(f"Adapter '{integration_id}' is not an ITSMAdapter.")
        return adapter.create_ticket_from_alert(alert, tenant_context=tenant_context)

    def sync_itsm_ticket_status(
        self,
        integration_id: str,
        external_ticket_id: str,
        new_status: str,
        actor_id: str,
        reason: str | None = None,
        *,
        remediation_service: RemediationService | None = None,
        remediation_task: RemediationTask | None = None,
        tenant_context: TenantContext | None = None,
    ) -> ITSMTicket:
        """Synchronises external ticket status with internal task bidirectionally."""
        adapter = self.get_adapter(integration_id)
        if not isinstance(adapter, ITSMAdapter):
            raise TypeError(f"Adapter '{integration_id}' is not an ITSMAdapter.")
        return adapter.sync_external_ticket_status(
            external_ticket_id=external_ticket_id,
            new_external_status=new_status,
            actor_id=actor_id,
            reason=reason,
            remediation_service=remediation_service,
            remediation_task=remediation_task,
            tenant_context=tenant_context,
        )

    # =========================================================================
    # CMDB Adapter Delegation
    # =========================================================================

    def import_cmdb_records(
        self,
        integration_id: str,
        entity_type: str,
        records: list[dict[str, Any]],
        natural_key_field: str = "code",
        *,
        tenant_context: TenantContext,
    ) -> dict[str, Any]:
        """Imports CMDB configuration items with declared provenance."""
        adapter = self.get_adapter(integration_id)
        if not isinstance(adapter, CMDBAdapter):
            raise TypeError(f"Adapter '{integration_id}' is not a CMDBAdapter.")
        return adapter.import_cmdb_records(
            entity_type=entity_type,
            records=records,
            natural_key_field=natural_key_field,
            tenant_context=tenant_context,
        )

    def validate_or_block_cmdb_overwrite(
        self,
        integration_id: str,
        entity_type: str,
        natural_key: str,
        proposed_updates: dict[str, Any],
        *,
        tenant_context: TenantContext,
        raise_on_blocked: bool = True,
    ) -> list[CMDBConflictRecord]:
        """Enforces CMDB authority and blocks unauthorized overwrites by CloudLens."""
        adapter = self.get_adapter(integration_id)
        if not isinstance(adapter, CMDBAdapter):
            raise TypeError(f"Adapter '{integration_id}' is not a CMDBAdapter.")
        return adapter.validate_or_block_overwrite(
            entity_type=entity_type,
            natural_key=natural_key,
            proposed_updates=proposed_updates,
            tenant_context=tenant_context,
            raise_on_blocked=raise_on_blocked,
        )

    # =========================================================================
    # Finance & ERP Adapter Delegation
    # =========================================================================

    def export_finance_coa_costs(
        self,
        integration_id: str,
        allocated_costs: list[dict[str, Any]],
        *,
        tenant_context: TenantContext,
    ) -> dict[str, Any]:
        """Exports costs aligned with the general ledger Chart of Accounts."""
        adapter = self.get_adapter(integration_id)
        if not isinstance(adapter, FinanceERPAdapter):
            raise TypeError(f"Adapter '{integration_id}' is not a FinanceERPAdapter.")
        return adapter.export_chart_of_accounts_costs(
            allocated_costs=allocated_costs,
            tenant_context=tenant_context,
        )

    def generate_period_close_accrual(
        self,
        integration_id: str,
        fiscal_period: str,
        cost_centre_breakdown: list[dict[str, Any]],
        *,
        tenant_context: TenantContext,
        currency: str = "USD",
    ) -> PeriodCloseAccrualExtract:
        """Generates the sealed period-close accrual extract for finance accounting."""
        adapter = self.get_adapter(integration_id)
        if not isinstance(adapter, FinanceERPAdapter):
            raise TypeError(f"Adapter '{integration_id}' is not a FinanceERPAdapter.")
        return adapter.generate_period_close_accrual_extract(
            fiscal_period=fiscal_period,
            cost_centre_breakdown=cost_centre_breakdown,
            tenant_context=tenant_context,
            currency=currency,
        )

    # =========================================================================
    # Chat Adapter Delegation
    # =========================================================================

    def dispatch_alert_to_chat(
        self,
        integration_id: str,
        alert: AlertEntity,
        *,
        tenant_context: TenantContext,
    ) -> Any:
        """Formats and posts an interactive notification card to Teams or Slack."""
        adapter = self.get_adapter(integration_id)
        if not isinstance(adapter, ChatAdapter):
            raise TypeError(f"Adapter '{integration_id}' is not a ChatAdapter.")
        return adapter.dispatch_alert_card(alert, tenant_context=tenant_context)

    def acknowledge_alert_from_chat(
        self,
        integration_id: str,
        alert_id: str,
        actor_email: str,
        reason: str | None = None,
        *,
        tenant_context: TenantContext,
        target_alert: AlertEntity | None = None,
    ) -> dict[str, Any]:
        """Actions an alert acknowledgement originating from an interactive chat button."""
        adapter = self.get_adapter(integration_id)
        if not isinstance(adapter, ChatAdapter):
            raise TypeError(f"Adapter '{integration_id}' is not a ChatAdapter.")
        return adapter.handle_in_message_acknowledgement(
            alert_id=alert_id,
            actor_email=actor_email,
            reason=reason,
            tenant_context=tenant_context,
            target_alert=target_alert,
        )

    # =========================================================================
    # Corporate Directory Adapter Delegation
    # =========================================================================

    def scan_directory_leavers(
        self,
        integration_id: str,
        resource_ownership_map: dict[str, str],
        scope_ownership_map: dict[str, str],
        *,
        tenant_context: TenantContext,
        remediation_service: RemediationService | None = None,
    ) -> Any:
        """Detects departed employees and raises proactive ownership gaps before resources orphan."""
        adapter = self.get_adapter(integration_id)
        if not isinstance(adapter, IdentityDirectoryAdapter):
            raise TypeError(f"Adapter '{integration_id}' is not an IdentityDirectoryAdapter.")
        return adapter.detect_leavers(
            resource_ownership_map=resource_ownership_map,
            scope_ownership_map=scope_ownership_map,
            tenant_context=tenant_context,
            remediation_service=remediation_service,
        )
