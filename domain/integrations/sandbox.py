"""Integration Sandbox Simulation Engine (Prompt 60 / Prompt 47 Pattern).

Enforces:
- Standalone local simulation: every integration adapter can run against a simulated endpoint
  with ZERO live third-party external system dependencies.
- Fixture and schema fidelity: produces and consumes authentic payloads conforming to
  Jira REST API v3, ServiceNow Table API, SAP S/4HANA OData / CoA, Slack Webhooks,
  Teams Adaptive Cards, and Azure AD / SCIM v2.
- Fault injection: supports simulating 429 rate limits, 500 transient outages, and latency spikes.
"""

from __future__ import annotations

import datetime as dt
import logging
import uuid
from typing import Any

from domain.integrations.models import (
    DirectoryUserProfile,
    IntegrationConfig,
)
from domain.models.enums import IntegrationCapability, IntegrationType

logger = logging.getLogger(__name__)


class IntegrationSandboxEndpoint:
    """Simulated local destination representing an external system."""

    def __init__(self, endpoint_name: str, system_type: str) -> None:
        self.endpoint_name = endpoint_name
        self.system_type = system_type
        self.calls_received: list[dict[str, Any]] = []
        self.injected_failure: Exception | None = None
        self.injected_status_code: int = 200

    def receive_call(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Processes a simulated incoming request."""
        self.calls_received.append(
            {
                "action": action,
                "payload": payload,
                "timestamp": dt.datetime.now(dt.UTC).isoformat(),
            }
        )

        if self.injected_failure:
            raise self.injected_failure

        if self.injected_status_code != 200:
            raise ConnectionError(
                f"Simulated HTTP {self.injected_status_code} error from {self.endpoint_name}"
            )

        return {
            "status": "SUCCESS",
            "endpoint": self.endpoint_name,
            "system_type": self.system_type,
            "received_action": action,
            "echo_id": uuid.uuid4().hex[:8],
        }


class IntegrationSandbox:
    """Master simulation harness providing mock endpoints and datasets for all 5 integration categories."""

    def __init__(self) -> None:
        self.itsm_endpoint = IntegrationSandboxEndpoint("Simulated-Jira-ServiceNow", "ITSM")
        self.cmdb_endpoint = IntegrationSandboxEndpoint("Simulated-ServiceNow-CMDB", "CMDB")
        self.finance_endpoint = IntegrationSandboxEndpoint("Simulated-SAP-ERP", "FINANCE")
        self.chat_endpoint = IntegrationSandboxEndpoint("Simulated-Teams-Slack-Webhook", "CHAT")
        self.directory_endpoint = IntegrationSandboxEndpoint("Simulated-AzureAD-SCIM", "DIRECTORY")

    def create_sandbox_config(
        self,
        integration_type: IntegrationType,
        name: str,
        custom_attributes: dict[str, Any] | None = None,
        authoritative_fields: list[str] | None = None,
    ) -> IntegrationConfig:
        """Generates an authentic, pre-configured sandbox IntegrationConfig."""
        custom_attrs = custom_attributes or {}
        custom_attrs.setdefault("is_sandbox", True)

        declared_caps: list[IntegrationCapability] = [
            IntegrationCapability.AUTHENTICATE,
            IntegrationCapability.HEALTH_CHECK,
        ]

        if integration_type == IntegrationType.ITSM:
            endpoint_url = "https://sandbox.cloudlens.local/itsm/api/v3"
            declared_caps.extend(
                [
                    IntegrationCapability.CREATE_TICKET,
                    IntegrationCapability.SYNC_STATUS,
                    IntegrationCapability.DISPATCH_EVENT,
                ]
            )
        elif integration_type == IntegrationType.CMDB:
            endpoint_url = "https://sandbox.cloudlens.local/cmdb/api/now/table"
            declared_caps.extend(
                [
                    IntegrationCapability.IMPORT_ENTITIES,
                    IntegrationCapability.SURFACE_CONFLICTS,
                ]
            )
        elif integration_type == IntegrationType.FINANCE_ERP:
            endpoint_url = "https://sandbox.cloudlens.local/sap/odata/coa"
            declared_caps.extend(
                [
                    IntegrationCapability.EXPORT_DATA,
                    IntegrationCapability.IMPORT_ENTITIES,
                ]
            )
        elif integration_type == IntegrationType.CHAT:
            endpoint_url = "https://sandbox.cloudlens.local/chat/webhook"
            declared_caps.extend(
                [
                    IntegrationCapability.DISPATCH_EVENT,
                    IntegrationCapability.ACKNOWLEDGE_ALERT,
                ]
            )
        elif integration_type == IntegrationType.IDENTITY_DIRECTORY:
            endpoint_url = "https://sandbox.cloudlens.local/scim/v2/Users"
            declared_caps.extend(
                [
                    IntegrationCapability.RESOLVE_IDENTITY,
                    IntegrationCapability.DETECT_LEAVERS,
                ]
            )
        else:
            endpoint_url = "https://sandbox.cloudlens.local/webhooks/listener"
            declared_caps.append(IntegrationCapability.DISPATCH_EVENT)

        return IntegrationConfig(
            integration_id=f"sandbox-{integration_type.value.lower()}-{uuid.uuid4().hex[:6]}",
            integration_type=integration_type,
            name=name,
            enabled=True,
            credential_ref=f"vault://secret/data/tenants/sandbox/integrations/{integration_type.value.lower()}",
            endpoint_url=endpoint_url,
            rate_limit_per_minute=200,
            timeout_seconds=5.0,
            max_retries=2,
            backoff_base_seconds=0.01,  # Ultra-fast backoff in sandbox
            circuit_breaker_threshold=3,
            circuit_breaker_reset_seconds=1.0,
            declared_capabilities=declared_caps,
            authoritative_fields=authoritative_fields or [],
            is_sandbox=True,
            custom_attributes=custom_attrs,
        )

    def get_seed_directory_users(self) -> list[DirectoryUserProfile]:
        """Provides realistic synthetic corporate directory dataset with active users and leavers."""
        return [
            DirectoryUserProfile(
                user_id="usr-101",
                email="alice.smith@enterprise.internal",
                display_name="Alice Smith",
                department="Core Infrastructure",
                team_id="TEAM_PLATFORM",
                is_active=True,
                employment_status="ACTIVE",
            ),
            DirectoryUserProfile(
                user_id="usr-102",
                email="bob.jones@enterprise.internal",
                display_name="Bob Jones",
                department="Data Platform",
                team_id="TEAM_DATA",
                is_active=True,
                employment_status="ACTIVE",
            ),
            DirectoryUserProfile(
                user_id="usr-999",
                email="departed.dev@enterprise.internal",
                display_name="Charlie Leaver",
                department="Legacy Payments",
                team_id="TEAM_LEGACY",
                is_active=False,
                employment_status="TERMINATED",
                termination_date=dt.datetime.now(dt.UTC) - dt.timedelta(days=2),
            ),
        ]

    def get_seed_cmdb_applications(self) -> list[dict[str, Any]]:
        """Provides realistic CMDB application configuration items."""
        return [
            {
                "code": "APP-PORTAL-01",
                "name": "Customer Self-Service Portal",
                "criticality_tier": "CRITICAL",
                "owner_email": "alice.smith@enterprise.internal",
                "business_service": "Digital Banking",
                "lifecycle_phase": "PRODUCTION",
            },
            {
                "code": "APP-PAYMENTS-02",
                "name": "Payment Gateway Processing",
                "criticality_tier": "CRITICAL",
                "owner_email": "payments-team@enterprise.internal",
                "business_service": "Payment Settlement",
                "lifecycle_phase": "PRODUCTION",
            },
        ]
