"""Integration Hub Domain Models and DTOs (Prompt 60 / BBP Section 13.5 & 35).

Enforces:
- Common integration configuration, security parameters, and credential references.
- Versioned outbound domain events with signed headers and replay window specifications.
- ITSM ticket mapping with bidirectional synchronisation state.
- CMDB authority declaration, conflict surfacing, and import provenance.
- Finance/ERP Chart-of-Accounts (CoA) structures and period-close accrual extracts.
- Chat message payloads (Teams Adaptive Cards & Slack Block Kit) with in-message actions.
- Directory user profiles and early leaver ownership gap findings.
- Rigorous per-integration health and telemetry metrics.
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from domain.models.enums import (
    FieldAuthority,
    IntegrationCapability,
    IntegrationDeliveryOutcome,
    IntegrationHealth,
    IntegrationType,
    OutboundEventType,
)


class IntegrationConfig(BaseModel):
    """Master-data-driven configuration for an external integration adapter."""

    integration_id: str = Field(..., description="Unique integration instance identifier")
    integration_type: IntegrationType = Field(..., description="Adapter category")
    name: str = Field(..., min_length=2, description="Human-readable integration name")
    enabled: bool = Field(default=True, description="Whether this integration is currently active")
    credential_ref: str = Field(
        ...,
        description="Opaque secret store reference URI (e.g. vault://secret/...); raw secrets forbidden",
    )
    endpoint_url: str = Field(..., description="External target API endpoint or webhook URL")
    rate_limit_per_minute: int = Field(
        default=120, ge=1, description="Bounded rate limit requests per minute"
    )
    timeout_seconds: float = Field(
        default=10.0, gt=0.0, description="Explicit HTTP request timeout"
    )
    max_retries: int = Field(default=3, ge=0, description="Maximum retry attempts on network error")
    backoff_base_seconds: float = Field(
        default=1.0, gt=0.0, description="Exponential backoff base duration"
    )
    circuit_breaker_threshold: int = Field(
        default=5, ge=1, description="Consecutive failure limit before tripping circuit breaker"
    )
    circuit_breaker_reset_seconds: float = Field(
        default=60.0, gt=0.0, description="Cooldown seconds before attempting half-open state"
    )
    declared_capabilities: list[IntegrationCapability] = Field(
        default_factory=list, description="Explicit list of capabilities supported by this adapter"
    )
    signing_secret_ref: str | None = Field(
        default=None, description="Secret store reference for webhook payload signing key"
    )
    authoritative_fields: list[str] = Field(
        default_factory=list,
        description="Field names where this integration is declared as the sole authoritative source",
    )
    is_sandbox: bool = Field(
        default=False, description="When true, directs traffic to simulated sandbox endpoint"
    )
    custom_attributes: dict[str, Any] = Field(
        default_factory=dict, description="Adapter-specific configuration attributes"
    )


class IntegrationHealthRecord(BaseModel):
    """Telemetry and health observability record for an integration adapter."""

    integration_id: str = Field(..., description="Target integration instance identifier")
    status: IntegrationHealth = Field(
        default=IntegrationHealth.HEALTHY, description="Current health status"
    )
    last_success_at: dt.datetime | None = Field(
        default=None, description="Timestamp of last successful operation"
    )
    last_failure_at: dt.datetime | None = Field(
        default=None, description="Timestamp of last encountered failure"
    )
    consecutive_failures: int = Field(
        default=0, ge=0, description="Counter of consecutive failed operations"
    )
    last_error_message: str | None = Field(
        default=None, description="Sanitized description of the last error"
    )
    lag_ms: float = Field(
        default=0.0, ge=0.0, description="Operational latency or delivery lag in milliseconds"
    )
    throughput_per_minute: float = Field(
        default=0.0, ge=0.0, description="Current throughput rate (operations/min)"
    )
    total_delivered: int = Field(default=0, ge=0, description="Total successful deliveries/actions")
    total_retried: int = Field(default=0, ge=0, description="Total transient retries executed")
    total_failed: int = Field(default=0, ge=0, description="Total permanent delivery failures")
    total_dead_letter: int = Field(
        default=0, ge=0, description="Total events moved to dead-letter storage"
    )
    last_checked_at: dt.datetime = Field(
        default_factory=lambda: dt.datetime.now(dt.UTC), description="Telemetry evaluation time"
    )


class OutboundEvent(BaseModel):
    """Canonical versioned domain event published for external integration consumption."""

    event_id: str = Field(
        default_factory=lambda: f"evt-{uuid.uuid4().hex[:12]}",
        description="Globally unique domain event ID",
    )
    event_type: OutboundEventType = Field(..., description="Canonical event taxonomy type")
    schema_version: str = Field(
        default="1.0", description="Strict semver string for the event payload schema"
    )
    tenant_id: str = Field(..., description="Tenant boundary")
    timestamp: dt.datetime = Field(
        default_factory=lambda: dt.datetime.now(dt.UTC), description="Event emission UTC timestamp"
    )
    correlation_id: str = Field(
        default_factory=lambda: f"corr-{uuid.uuid4().hex[:10]}",
        description="Distributed tracing correlation ID",
    )
    partition_key: str = Field(
        ...,
        description="Partition dimension (scope/resource/task ID) ensuring causal ordering",
    )
    sequence_number: int = Field(
        default=1, ge=1, description="Monotonically increasing sequence number within partition"
    )
    payload: dict[str, Any] = Field(..., description="Validated event body payload")
    signature: str | None = Field(
        default=None, description="HMAC-SHA256 signature hex digest computed over event bytes"
    )


class OutboundDeliveryAttempt(BaseModel):
    """Audit log entry capturing an outbound webhook or API delivery attempt."""

    attempt_id: str = Field(
        default_factory=lambda: f"att-{uuid.uuid4().hex[:8]}",
        description="Unique delivery attempt ID",
    )
    event_id: str = Field(..., description="Referenced outbound event ID")
    integration_id: str = Field(..., description="Destination integration adapter ID")
    attempt_number: int = Field(..., ge=1, description="Attempt sequence number (1-based)")
    timestamp: dt.datetime = Field(
        default_factory=lambda: dt.datetime.now(dt.UTC), description="Dispatch timestamp"
    )
    outcome: IntegrationDeliveryOutcome = Field(..., description="Delivery attempt outcome")
    http_status: int | None = Field(default=None, description="Received HTTP response code if any")
    duration_ms: float = Field(default=0.0, ge=0.0, description="Round-trip duration in ms")
    error_message: str | None = Field(
        default=None, description="Sanitized error description on failure"
    )


class EventReplayRequest(BaseModel):
    """Criteria for requesting historical event replay within the replay window."""

    tenant_id: str = Field(..., description="Tenant boundary")
    from_timestamp: dt.datetime = Field(..., description="Start of replay window (UTC)")
    to_timestamp: dt.datetime = Field(..., description="End of replay window (UTC)")
    event_types: list[OutboundEventType] | None = Field(
        default=None, description="Optional filter by event types"
    )
    partition_key: str | None = Field(
        default=None, description="Optional partition-specific replay filter"
    )
    max_events: int = Field(default=1000, ge=1, le=10000, description="Maximum events to replay")


class ITSMTicket(BaseModel):
    """Mirrored representation of an external ITSM ticket linked to CloudLens."""

    ticket_id: str = Field(
        default_factory=lambda: f"tkt-{uuid.uuid4().hex[:8]}",
        description="Internal tracking ID for the ticket binding",
    )
    external_system: str = Field(default="JIRA", description="ITSM system (JIRA, SERVICENOW)")
    external_ticket_id: str = Field(
        ..., description="External ticket key (e.g. 'INC-10928' or 'JIRA-4819')"
    )
    cloudlens_entity_type: str = Field(..., description="Linked entity kind ('TASK' or 'ALERT')")
    cloudlens_entity_id: str = Field(..., description="Identifier of the linked internal entity")
    title: str = Field(..., description="Ticket title / summary")
    description: str = Field(..., description="Ticket body with context and evidence")
    priority: str = Field(..., description="External priority level (e.g. 'P1-Urgent', 'P2-High')")
    status: str = Field(
        default="OPEN", description="Normalized ticket status (OPEN, IN_PROGRESS, RESOLVED, CLOSED)"
    )
    evidence_summary: str = Field(default="", description="Summary of attached empirical evidence")
    deep_link: str = Field(default="", description="Deep link back into CloudLens UI")
    created_at: dt.datetime = Field(
        default_factory=lambda: dt.datetime.now(dt.UTC), description="Binding creation time"
    )
    last_synced_at: dt.datetime = Field(
        default_factory=lambda: dt.datetime.now(dt.UTC), description="Last synchronization time"
    )


class CMDBConflictRecord(BaseModel):
    """Audit record capturing a divergence between CMDB authority and local CloudLens data."""

    conflict_id: str = Field(
        default_factory=lambda: f"conf-{uuid.uuid4().hex[:8]}",
        description="Unique conflict instance ID",
    )
    tenant_id: str = Field(..., description="Tenant boundary")
    entity_type: str = Field(
        ..., description="Entity category (APPLICATION, BUSINESS_SERVICE, OWNER, DEPENDENCY_EDGE)"
    )
    natural_key: str = Field(..., description="Natural key identifying the entity")
    field_name: str = Field(..., description="Specific attribute in conflict")
    cmdb_value: Any = Field(..., description="Value asserted by external CMDB")
    cloudlens_value: Any = Field(..., description="Local value in CloudLens")
    declared_authority: FieldAuthority = Field(
        default=FieldAuthority.CMDB, description="System nominated as the authority"
    )
    detected_at: dt.datetime = Field(
        default_factory=lambda: dt.datetime.now(dt.UTC), description="Detection timestamp"
    )
    surfaced: bool = Field(
        default=True, description="Whether the conflict is surfaced in UI/governance"
    )
    resolved: bool = Field(
        default=False, description="Whether human resolution has reconciled the conflict"
    )
    resolved_by: str | None = Field(default=None, description="Actor resolving the conflict")
    resolution_note: str | None = Field(default=None, description="Justification note")


class CostCentreAccrualItem(BaseModel):
    """Individual cost centre accrual item aligned with General Ledger Chart of Accounts."""

    cost_centre_code: str = Field(..., description="Cost centre master code")
    cost_centre_name: str = Field(..., description="Cost centre display name")
    business_unit_code: str = Field(..., description="Parent business unit code")
    gl_account_code: str = Field(..., description="General ledger account code (e.g. 'GL-52010')")
    accrued_amount: Decimal = Field(..., ge=Decimal("0.00"), description="Total accrued cost amount")
    currency: str = Field(default="USD", description="Currency code")
    unbilled_usage_amount: Decimal = Field(
        default=Decimal("0.00"), ge=Decimal("0.00"), description="Estimated unbilled usage portion"
    )
    amortised_commitment_amount: Decimal = Field(
        default=Decimal("0.00"),
        ge=Decimal("0.00"),
        description="Amortised reservation / savings plan portion",
    )
    description: str = Field(default="", description="Line item accounting description")


class PeriodCloseAccrualExtract(BaseModel):
    """Period-close accrual extract delivered to enterprise Finance/ERP systems."""

    extract_id: str = Field(
        default_factory=lambda: f"acc-{uuid.uuid4().hex[:8]}",
        description="Unique extract document ID",
    )
    tenant_id: str = Field(..., description="Tenant boundary")
    fiscal_period: str = Field(
        ..., description="Target closed fiscal period (e.g. '2026-09' or 'FY26-P09')"
    )
    cutoff_timestamp: dt.datetime = Field(..., description="Cutoff timestamp for billing ingestion")
    currency: str = Field(default="USD", description="Currency code")
    total_accrual: Decimal = Field(
        ..., ge=Decimal("0.00"), description="Grand total accrued expenditure"
    )
    cost_centre_items: list[CostCentreAccrualItem] = Field(
        default_factory=list, description="Itemized accrual lines by cost centre and GL account"
    )
    chart_of_accounts_version: str = Field(
        default="COA-v2.1", description="Chart of accounts master schema version"
    )
    generated_at: dt.datetime = Field(
        default_factory=lambda: dt.datetime.now(dt.UTC), description="Generation timestamp"
    )


class ChatAlertCard(BaseModel):
    """Formatted interactive notification card for Microsoft Teams or Slack."""

    card_id: str = Field(
        default_factory=lambda: f"chat-{uuid.uuid4().hex[:8]}",
        description="Internal tracking ID for chat card",
    )
    platform: str = Field(..., description="Destination chat platform ('TEAMS' or 'SLACK')")
    alert_id: str = Field(..., description="Linked CloudLens alert ID")
    tenant_id: str = Field(..., description="Tenant boundary")
    title: str = Field(..., description="Card title")
    severity: str = Field(..., description="Urgency severity")
    summary: str = Field(..., description="Context summary")
    deep_link: str = Field(..., description="Web link to open alert directly in CloudLens")
    action_callback_url: str = Field(..., description="Endpoint URL for interactive buttons")
    formatted_payload: dict[str, Any] = Field(
        ..., description="Native Teams Adaptive Card or Slack Block Kit payload structure"
    )
    is_acknowledged: bool = Field(
        default=False, description="Whether alert was acknowledged via in-message action"
    )
    acknowledged_by: str | None = Field(
        default=None, description="Actor email/ID who acknowledged via chat"
    )
    acknowledged_at: dt.datetime | None = Field(
        default=None, description="Timestamp of chat acknowledgement"
    )


class DirectoryUserProfile(BaseModel):
    """External corporate directory user snapshot (Azure AD / Okta SCIM)."""

    user_id: str = Field(..., description="Directory principal ID / UPN")
    email: str = Field(..., description="Email address")
    display_name: str = Field(..., description="Full human name")
    department: str = Field(default="", description="Department name")
    team_id: str = Field(default="", description="Assigned team identifier")
    is_active: bool = Field(default=True, description="Account active flag in directory")
    employment_status: str = Field(
        default="ACTIVE", description="Employment state ('ACTIVE', 'TERMINATED', 'ON_LEAVE')"
    )
    termination_date: dt.datetime | None = Field(
        default=None, description="Official departure / termination date"
    )


class OwnershipGapFinding(BaseModel):
    """Proactive governance finding when a departed employee still owns cloud resources."""

    finding_id: str = Field(
        default_factory=lambda: f"gap-{uuid.uuid4().hex[:8]}",
        description="Unique finding identifier",
    )
    tenant_id: str = Field(..., description="Tenant boundary")
    former_owner_email: str = Field(..., description="Email of departed employee")
    former_owner_name: str = Field(..., description="Name of departed employee")
    termination_date: dt.datetime | None = Field(
        default=None, description="Official termination timestamp"
    )
    affected_resource_ids: list[str] = Field(
        default_factory=list, description="IDs of cloud resources currently assigned to leaver"
    )
    affected_scopes: list[str] = Field(
        default_factory=list, description="Scopes (projects/subscriptions) assigned to leaver"
    )
    remediation_task_id: str | None = Field(
        default=None, description="Linked Prompt 51 remediation task ID"
    )
    detected_at: dt.datetime = Field(
        default_factory=lambda: dt.datetime.now(dt.UTC), description="Detection timestamp"
    )
    status: str = Field(default="ACTIVE", description="Finding lifecycle status ('ACTIVE', 'RESOLVED')")
