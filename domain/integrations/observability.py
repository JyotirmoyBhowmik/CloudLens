"""Per-Integration Observability and Telemetry Engine (Prompt 60 / BBP Section 13.5).

Enforces:
- Parity with Connector Health (Prompt 14 / Prompt 47):
  Integrations are treated as first-class infrastructural dependencies.
  A broken integration is as visible as a broken connector.
- Telemetry: tracks last success, delivery lag (ms), error rates, throughput (ops/min),
  circuit breaker status, and delivery outcome counts (delivered, retrying, failed, dead-letter).
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any

from domain.integrations.contract import BaseIntegrationAdapter
from domain.integrations.models import IntegrationHealthRecord
from domain.models.enums import IntegrationHealth

logger = logging.getLogger(__name__)


class IntegrationObservabilityService:
    """Aggregates and evaluates health metrics across all registered integration adapters."""

    def __init__(self) -> None:
        self._adapters: dict[str, BaseIntegrationAdapter] = {}

    def register_adapter(self, adapter: BaseIntegrationAdapter) -> None:
        """Enrolls an adapter into continuous observability monitoring."""
        self._adapters[adapter.integration_id] = adapter

    def unregister_adapter(self, integration_id: str) -> None:
        """Removes an adapter from monitoring."""
        self._adapters.pop(integration_id, None)

    def get_adapter_health(self, integration_id: str) -> IntegrationHealthRecord:
        """Retrieves real-time health telemetry for a specific adapter."""
        adapter = self._adapters.get(integration_id)
        if not adapter:
            raise KeyError(f"Integration adapter '{integration_id}' is not registered.")
        return adapter.get_health()

    def get_fleet_health_summary(self) -> dict[str, Any]:
        """Produces a holistic health dashboard summary across all integration adapters."""
        total = len(self._adapters)
        healthy = 0
        degraded = 0
        unhealthy = 0
        paused = 0

        details: list[dict[str, Any]] = []

        for adapter_id, adapter in self._adapters.items():
            health = adapter.get_health()
            if health.status == IntegrationHealth.HEALTHY:
                healthy += 1
            elif health.status == IntegrationHealth.DEGRADED:
                degraded += 1
            elif health.status == IntegrationHealth.UNHEALTHY:
                unhealthy += 1
            elif health.status == IntegrationHealth.PAUSED:
                paused += 1

            details.append(
                {
                    "integration_id": adapter_id,
                    "adapter_name": adapter.adapter_name,
                    "type": adapter.integration_type.value,
                    "status": health.status.value,
                    "last_success_at": (
                        health.last_success_at.isoformat() if health.last_success_at else None
                    ),
                    "last_failure_at": (
                        health.last_failure_at.isoformat() if health.last_failure_at else None
                    ),
                    "consecutive_failures": health.consecutive_failures,
                    "lag_ms": round(health.lag_ms, 2),
                    "throughput_per_minute": round(health.throughput_per_minute, 2),
                    "total_delivered": health.total_delivered,
                    "total_retried": health.total_retried,
                    "total_failed": health.total_failed,
                    "total_dead_letter": health.total_dead_letter,
                    "last_error": health.last_error_message,
                }
            )

        overall_status = "HEALTHY"
        if unhealthy > 0:
            overall_status = "UNHEALTHY"
        elif degraded > 0:
            overall_status = "DEGRADED"

        return {
            "evaluated_at": dt.datetime.now(dt.UTC).isoformat(),
            "overall_status": overall_status,
            "total_integrations": total,
            "healthy_count": healthy,
            "degraded_count": degraded,
            "unhealthy_count": unhealthy,
            "paused_count": paused,
            "adapters": details,
        }
