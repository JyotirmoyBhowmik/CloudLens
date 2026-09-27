"""Connector Synchronization Scheduler and Cadence Warning Engine (Prompt 15 Item 98).

Enforces:
- Prompt 15 Item 98: Per-connector, per-capability schedules with recommended defaults:
  - Inventory every 4–6h with daily full sync.
  - Cost every 4–8h with 3–7 day restatement look-back.
  - Usage hourly to daily.
  - Pricing weekly plus on-demand on unknown SKU.
  - Relationships daily.
  - Provider budgets daily.
- Every interval is configurable.
- Non-blocking warnings when configured interval is unlikely to yield new data.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from domain.audit.models import AuditEventCreate
from domain.audit.service import get_audit_service
from domain.config.tenant_settings import tenant_settings_store
from domain.models.enums import AuditEventType, ConnectorCapability
from domain.sync.models import CadenceWarning, ConnectorSchedule
from domain.sync.repository import (
    ConnectorScheduleRepository,
    get_connector_schedule_repository,
)
from domain.tenant.context import TenantContext

logger = logging.getLogger(__name__)

# Minutes per hour multiplier
MINUTES_IN_HOUR = 60  # no-hardcode-allow: reason="Fixed SI conversion constant: 60 minutes per hour", reviewer="enterprise-arch"


class SyncScheduler:
    """Manages connector schedules, applies tenant configuration defaults, and evaluates cadence warnings."""

    def __init__(self, schedule_repo: ConnectorScheduleRepository | None = None) -> None:
        self._schedule_repo = schedule_repo or get_connector_schedule_repository()
        self._audit_service = get_audit_service()

    def get_default_schedules(
        self, connector_id: str, tenant_context: TenantContext
    ) -> list[ConnectorSchedule]:
        """Constructs canonical default schedules populated from dynamic tenant settings."""
        settings = tenant_settings_store.get(tenant_context.tenant_id).sync_schedule_settings

        now = datetime.now(UTC)
        schedules = [
            # Inventory (every 4-6h)
            ConnectorSchedule(
                id=f"sched-{uuid.uuid4().hex[:12]}",
                tenant_id=tenant_context.tenant_id,
                connector_id=connector_id,
                capability=ConnectorCapability.DISCOVER_RESOURCES,
                interval_minutes=settings.inventory_interval_hours * MINUTES_IN_HOUR,
                lookback_days=0,
                is_enabled=True,
                created_at=now,
            ),
            # Cost (every 4-8h with 3-7 day restatement look-back)
            ConnectorSchedule(
                id=f"sched-{uuid.uuid4().hex[:12]}",
                tenant_id=tenant_context.tenant_id,
                connector_id=connector_id,
                capability=ConnectorCapability.COLLECT_COST_BULK,
                interval_minutes=settings.cost_interval_hours * MINUTES_IN_HOUR,
                lookback_days=settings.cost_restatement_lookback_days,
                is_enabled=True,
                created_at=now,
            ),
            # Usage (hourly to daily)
            ConnectorSchedule(
                id=f"sched-{uuid.uuid4().hex[:12]}",
                tenant_id=tenant_context.tenant_id,
                connector_id=connector_id,
                capability=ConnectorCapability.COLLECT_USAGE,
                interval_minutes=settings.usage_interval_hours * MINUTES_IN_HOUR,
                lookback_days=0,
                is_enabled=True,
                created_at=now,
            ),
            # Pricing (weekly = 168h)
            ConnectorSchedule(
                id=f"sched-{uuid.uuid4().hex[:12]}",
                tenant_id=tenant_context.tenant_id,
                connector_id=connector_id,
                capability=ConnectorCapability.COLLECT_PRICING_PUBLIC,
                interval_minutes=settings.pricing_interval_hours * MINUTES_IN_HOUR,
                lookback_days=0,
                is_enabled=True,
                created_at=now,
            ),
            # Relationships (daily = 24h)
            ConnectorSchedule(
                id=f"sched-{uuid.uuid4().hex[:12]}",
                tenant_id=tenant_context.tenant_id,
                connector_id=connector_id,
                capability=ConnectorCapability.DISCOVER_RELATIONSHIPS,
                interval_minutes=settings.relationships_interval_hours * MINUTES_IN_HOUR,
                lookback_days=0,
                is_enabled=True,
                created_at=now,
            ),
            # Provider budgets (daily = 24h)
            ConnectorSchedule(
                id=f"sched-{uuid.uuid4().hex[:12]}",
                tenant_id=tenant_context.tenant_id,
                connector_id=connector_id,
                capability=ConnectorCapability.COLLECT_BUDGETS,
                interval_minutes=settings.provider_budgets_interval_hours * MINUTES_IN_HOUR,
                lookback_days=0,
                is_enabled=True,
                created_at=now,
            ),
        ]
        return schedules

    def initialize_connector_schedules(
        self, connector_id: str, tenant_context: TenantContext
    ) -> list[ConnectorSchedule]:
        """Persists default schedules for a newly registered or onboarded connector."""
        defaults = self.get_default_schedules(connector_id, tenant_context)
        persisted: list[ConnectorSchedule] = []
        for sched in defaults:
            existing = self._schedule_repo.get_by_connector_and_capability(
                connector_id=connector_id,
                capability=sched.capability,
                tenant_context=tenant_context,
            )
            if not existing:
                saved = self._schedule_repo.save(sched, tenant_context=tenant_context)
                persisted.append(saved)
            else:
                persisted.append(existing)
        return persisted

    def check_interval_cadence(
        self,
        capability: ConnectorCapability,
        interval_minutes: int,
        tenant_context: TenantContext,
    ) -> CadenceWarning | None:
        """Evaluates whether an interval is unlikely to yield new data and generates a non-blocking warning."""
        settings = tenant_settings_store.get(tenant_context.tenant_id).sync_schedule_settings
        interval_hours = interval_minutes / MINUTES_IN_HOUR

        # Cost check
        if capability in (
            ConnectorCapability.COLLECT_COST_BULK,
            ConnectorCapability.COLLECT_COST_QUERY,
        ):
            if interval_hours < settings.min_cost_interval_hours:
                return CadenceWarning(
                    capability=capability,
                    interval_hours=interval_hours,
                    recommended_min_hours=float(settings.min_cost_interval_hours),
                    warning_message=(
                        f"Configured interval ({interval_hours:.1f}h) is shorter than recommended "
                        f"cadence ({settings.min_cost_interval_hours}h). Cloud provider billing data "
                        f"(AWS CUR, Azure Cost Export, GCP BigQuery Export) is published at most "
                        f"3 to 4 times per day; more frequent collection is unlikely to yield new data "
                        f"and may trigger API rate limits."
                    ),
                )

        # Pricing check
        elif capability in (
            ConnectorCapability.COLLECT_PRICING_PUBLIC,
            ConnectorCapability.COLLECT_PRICING_NEGOTIATED,
        ):
            if interval_hours < settings.min_pricing_interval_hours:
                return CadenceWarning(
                    capability=capability,
                    interval_hours=interval_hours,
                    recommended_min_hours=float(settings.min_pricing_interval_hours),
                    warning_message=(
                        f"Configured interval ({interval_hours:.1f}h) is shorter than recommended "
                        f"cadence ({settings.min_pricing_interval_hours}h). Cloud provider price lists and "
                        f"pricing catalogs are updated on weekly or monthly schedules; more frequent checks will consume "
                        f"quota without discovering changes."
                    ),
                )

        # Budgets check
        elif capability == ConnectorCapability.COLLECT_BUDGETS:
            if interval_hours < settings.min_budget_interval_hours:
                return CadenceWarning(
                    capability=capability,
                    interval_hours=interval_hours,
                    recommended_min_hours=float(settings.min_budget_interval_hours),
                    warning_message=(
                        f"Configured interval ({interval_hours:.1f}h) is shorter than recommended "
                        f"cadence ({settings.min_budget_interval_hours}h). Provider budgets recalculate "
                        f"on multi-hour cycles; polling more often is unlikely to yield updated spend figures."
                    ),
                )

        return None

    def update_schedule(
        self,
        connector_id: str,
        capability: ConnectorCapability,
        interval_minutes: int,
        lookback_days: int | None,
        is_enabled: bool,
        tenant_context: TenantContext,
    ) -> tuple[ConnectorSchedule, CadenceWarning | None]:
        """Updates schedule parameters and returns the updated entity along with any cadence warning."""
        # 1. Evaluate warning (warn but do not block, per Item 98)
        warning = self.check_interval_cadence(
            capability=capability,
            interval_minutes=interval_minutes,
            tenant_context=tenant_context,
        )

        # 2. Retrieve or create schedule
        sched = self._schedule_repo.get_by_connector_and_capability(
            connector_id=connector_id,
            capability=capability,
            tenant_context=tenant_context,
        )

        now = datetime.now(UTC)
        if not sched:
            sched = ConnectorSchedule(
                id=f"sched-{uuid.uuid4().hex[:12]}",
                tenant_id=tenant_context.tenant_id,
                connector_id=connector_id,
                capability=capability,
                interval_minutes=interval_minutes,
                lookback_days=lookback_days or 0,
                is_enabled=is_enabled,
                created_at=now,
                updated_at=now,
            )
        else:
            sched.interval_minutes = interval_minutes
            if lookback_days is not None:
                sched.lookback_days = lookback_days
            sched.is_enabled = is_enabled
            sched.updated_at = now

        saved = self._schedule_repo.save(sched, tenant_context=tenant_context)

        # 3. Emit audit event
        try:
            self._audit_service.append_event(
                tenant_context=tenant_context,
                event_in=AuditEventCreate(
                    event_type=AuditEventType.SCHEDULE_UPDATED,
                    actor_id=tenant_context.user_id,
                    actor_roles=tenant_context.roles,
                    action=AuditEventType.SCHEDULE_UPDATED.value,
                    resource_type="ConnectorSchedule",
                    resource_id=saved.id,
                    details={
                        "connector_id": connector_id,
                        "capability": capability.value,
                        "interval_minutes": interval_minutes,
                        "lookback_days": saved.lookback_days,
                        "is_enabled": is_enabled,
                        "warning": warning.warning_message if warning else None,
                    },
                    correlation_id=tenant_context.correlation_id,
                ),
            )
        except Exception as exc:
            logger.warning("Failed to emit audit event for schedule update: %s", exc)

        return saved, warning


# Global singleton scheduler
_sync_scheduler = SyncScheduler()


def get_sync_scheduler() -> SyncScheduler:
    return _sync_scheduler
