"""Domain Models for Notification Logging and Onboarding Alert Delivery Testing (Prompt 15B Items 24, 25).

Enforces:
- Prompt 15B Item 24: Alert delivery test step verifying configured notification channels.
- Prompt 15B Item 25: Test alerts clearly marked as tests and recorded in notification log, NOT alert list.
- CON-015: The wizard must conduct an alert and notification delivery test before setup completion.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from domain.models.base import CanonicalEntity
from domain.models.enums import NotificationChannel, NotificationStatus


class NotificationLogRecord(CanonicalEntity):
    """Immutable audit record of outbound notification dispatch (Prompt 15B Item 25)."""

    tenant_id: str = Field(..., description="Organization tenant ID owning notification")
    alert_id: str | None = Field(
        default=None,
        description="Linked operational Alert ID if applicable; None for synthetic tests",
    )
    channel: NotificationChannel = Field(
        ..., description="Delivery channel (EMAIL, SLACK, WEBHOOK, PAGERDUTY, TEAMS)"
    )
    recipient: str = Field(..., description="Destination address, URL, or channel name")
    status: NotificationStatus = Field(
        default=NotificationStatus.PENDING, description="Dispatch outcome (SENT, FAILED, PENDING)"
    )
    message: str = Field(..., description="Outbound message body")
    is_test: bool = Field(
        default=False, description="Whether this notification was a synthetic delivery test"
    )
    latency_ms: int | None = Field(
        default=None, description="Observed round-trip dispatch latency in milliseconds"
    )
    error_message: str | None = Field(
        default=None, description="Detailed diagnostic error message if dispatch failed"
    )
    sent_at: datetime | None = Field(default=None, description="Confirmation timestamp in UTC")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional context and tracing metadata"
    )


class ChannelTestInput(BaseModel):
    """Specification for testing a candidate notification channel."""

    channel: NotificationChannel = Field(..., description="Channel type to test")
    recipient: str = Field(..., description="Target destination address, hook, or handle")
    simulate_failure: bool = Field(
        default=False, description="Flag for automated testing of channel rejection"
    )


class ChannelTestResult(BaseModel):
    """Individual channel test evaluation outcome (Prompt 15B Item 24)."""

    channel: NotificationChannel = Field(..., description="Channel evaluated")
    recipient: str = Field(..., description="Target address or webhook URI")
    status: NotificationStatus = Field(..., description="Delivery outcome (SENT or FAILED)")
    latency_ms: int = Field(default=0, description="Round-trip response latency in milliseconds")
    error_message: str | None = Field(default=None, description="Failure diagnostic if rejected")


class AlertDeliveryTestReport(BaseModel):
    """Consolidated report across all tested notification channels (Prompt 15B Item 24)."""

    session_id: str = Field(..., description="Wizard session ID")
    tenant_id: str = Field(..., description="Tenant ID")
    is_test: bool = Field(default=True, description="Always True; strictly marked as test")
    test_message: str = Field(..., description="Synthetic test notification content")
    tested_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Test execution timestamp"
    )
    channels: list[ChannelTestResult] = Field(
        default_factory=list, description="Per-channel delivery results"
    )
    total_channels: int = Field(default=0, description="Count of channels evaluated")
    successful_channels: int = Field(default=0, description="Count of channels that succeeded")
    failed_channels: int = Field(default=0, description="Count of channels that failed")
    can_proceed: bool = Field(
        default=False,
        description="Whether completion is permitted (at least 1 channel succeeded or override applied)",
    )
    blocked_reason: str | None = Field(
        default=None, description="Reason completion is blocked if all channels failed"
    )
    override_applied: bool = Field(
        default=False, description="Whether an administrative override bypassed failure"
    )


__all__ = [
    "NotificationLogRecord",
    "ChannelTestInput",
    "ChannelTestResult",
    "AlertDeliveryTestReport",
]
