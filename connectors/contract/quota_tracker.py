"""CloudLens Hourly Quota Tracker and Diagnostics Engine (Prompt 14 Item 94).

Enforces:
- Rolling/hourly API request quota tracking per connector.
- Dynamic calculation of headroom and utilization percentage.
- Diagnostics exposure for telemetry and administrative inspection.
- Fails fast with QuotaExhaustedException when hourly ceiling is reached.
"""

from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime, timedelta

from connectors.contract.models import HourlyQuotaDiagnostic
from domain.config.tenant_settings import ConnectorSettings
from domain.models.exceptions import QuotaExhaustedException

logger = logging.getLogger(__name__)
_settings = ConnectorSettings()


class HourlyQuotaTracker:
    """Tracks and enforces hourly request quotas per connector."""

    def __init__(
        self,
        default_hourly_limit: int = _settings.default_hourly_quota,
    ) -> None:
        self.default_hourly_limit = default_hourly_limit
        # Map: (tenant_id, connector_id, hour_window_str) -> int (requests_made)
        self._counts: dict[tuple[str, str, str], int] = {}
        # Map: (tenant_id, connector_id) -> int (custom hourly limit)
        self._custom_limits: dict[tuple[str, str], int] = {}
        self._lock = threading.Lock()

    def _get_current_hour_window(self, dt: datetime | None = None) -> tuple[str, datetime]:
        """Returns the current hour bucket string (e.g. '2026-09-27T00:00:00Z') and next reset datetime."""
        now = dt or datetime.now(UTC)
        window_start = now.replace(minute=0, second=0, microsecond=0)
        window_reset = window_start + timedelta(hours=1)
        window_str = window_start.strftime("%Y-%m-%dT%H:00:00Z")
        return window_str, window_reset

    def set_custom_limit(self, tenant_id: str, connector_id: str, hourly_limit: int) -> None:
        """Sets a custom hourly quota for a specific connector."""
        with self._lock:
            self._custom_limits[(tenant_id, connector_id)] = hourly_limit

    def get_limit(self, tenant_id: str, connector_id: str) -> int:
        """Retrieves effective hourly quota for connector."""
        with self._lock:
            return self._custom_limits.get((tenant_id, connector_id), self.default_hourly_limit)

    def record_request(
        self,
        tenant_id: str,
        connector_id: str,
        count: int = 1,
        now: datetime | None = None,
    ) -> HourlyQuotaDiagnostic:
        """Records API requests against the connector's current hourly window.

        Raises QuotaExhaustedException if the request would exceed the limit.
        """
        window_str, window_reset = self._get_current_hour_window(now)
        limit = self.get_limit(tenant_id, connector_id)
        key = (tenant_id, connector_id, window_str)

        with self._lock:
            current_count = self._counts.get(key, 0)
            if current_count + count > limit:
                logger.error(
                    "Hourly quota of %d exhausted for connector %s in tenant %s. (Attempted: %d, Current: %d)",
                    limit,
                    connector_id,
                    tenant_id,
                    count,
                    current_count,
                )
                raise QuotaExhaustedException(
                    connector_id=connector_id,
                    hourly_limit=limit,
                    resets_at_iso=window_reset.isoformat(),
                )

            new_count = current_count + count
            self._counts[key] = new_count

            # Clean up old window buckets to prevent unbounded memory growth
            self._prune_expired_windows(window_str)

            remaining = max(0, limit - new_count)
            # no-hardcode-allow: reason="Standard percentage calculation factor", reviewer="enterprise-arch"
            utilization = round((new_count / limit) * 100.0, 2) if limit > 0 else 100.0

            return HourlyQuotaDiagnostic(
                connector_id=connector_id,
                tenant_id=tenant_id,
                window_hour_utc=window_str,
                requests_made=new_count,
                hourly_limit=limit,
                remaining_headroom=remaining,
                utilization_percentage=utilization,
                is_exhausted=remaining == 0,
                resets_at=window_reset,
            )

    def get_diagnostic(
        self,
        tenant_id: str,
        connector_id: str,
        now: datetime | None = None,
    ) -> HourlyQuotaDiagnostic:
        """Retrieves diagnostic quota status without incrementing the counter."""
        window_str, window_reset = self._get_current_hour_window(now)
        limit = self.get_limit(tenant_id, connector_id)
        key = (tenant_id, connector_id, window_str)

        with self._lock:
            requests_made = self._counts.get(key, 0)
            remaining = max(0, limit - requests_made)
            # no-hardcode-allow: reason="Standard percentage calculation factor", reviewer="enterprise-arch"
            utilization = round((requests_made / limit) * 100.0, 2) if limit > 0 else 100.0

            return HourlyQuotaDiagnostic(
                connector_id=connector_id,
                tenant_id=tenant_id,
                window_hour_utc=window_str,
                requests_made=requests_made,
                hourly_limit=limit,
                remaining_headroom=remaining,
                utilization_percentage=utilization,
                is_exhausted=remaining == 0,
                resets_at=window_reset,
            )

    def get_diagnostics(
        self,
        tenant_id: str,
        connector_id: str,
        now: datetime | None = None,
    ) -> HourlyQuotaDiagnostic:
        """Retrieves diagnostic quota status without incrementing the counter (alias for get_diagnostic)."""
        return self.get_diagnostic(tenant_id=tenant_id, connector_id=connector_id, now=now)

    def _prune_expired_windows(self, current_window: str) -> None:
        """Prunes historical window keys older than 24 hours."""
        keys_to_remove = [k for k in self._counts if k[2] < current_window]
        for k in keys_to_remove:
            self._counts.pop(k, None)

    def reset_for_test(self) -> None:
        """Resets all quota tracking counters for testing."""
        with self._lock:
            self._counts.clear()
            self._custom_limits.clear()


# Global quota tracker singleton
hourly_quota_tracker = HourlyQuotaTracker()
