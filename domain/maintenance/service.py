"""Maintenance Mode Domain Service (Prompt R-FEAT / IMP-01).

Governs:
- Global and per-tenant maintenance mode flags.
- Read-only API enforcement: blocks mutating methods (POST, PUT, PATCH, DELETE)
  while preserving read-only queries (GET, HEAD, OPTIONS).
- Audit trail for maintenance toggles.
- Beat pause synchronization for background workers.
- Exemption paths (health checks, admin login, control tower maintenance toggle).
"""

from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime
from typing import Any

from masterdata.improvement_features import get_feature_config

logger = logging.getLogger("cloudlens.domain.maintenance")


class MaintenanceModeService:
    """Thread-safe service managing platform and tenant maintenance modes."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._global_maintenance: bool = False
        self._tenant_maintenance: dict[str, bool] = {}
        self._maintenance_reasons: dict[str, str] = {}
        self._activated_at: dict[str, str] = {}
        self._config = get_feature_config("IMP_01_MAINTENANCE_MODE")

    def is_maintenance_mode(self, tenant_id: str | None = None) -> bool:
        """Returns True if global maintenance is active or specific tenant is in maintenance."""
        with self._lock:
            if self._global_maintenance:
                return True
            if tenant_id and self._tenant_maintenance.get(tenant_id, False):
                return True
            return False

    def is_global_maintenance(self) -> bool:
        """Returns True if global platform-wide maintenance is active."""
        with self._lock:
            return self._global_maintenance

    def set_maintenance_mode(
        self,
        enabled: bool,
        tenant_id: str | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Toggles maintenance mode globally or for a specific tenant."""
        now_str = datetime.now(UTC).isoformat()
        reason_str = reason or self._config.get("default_message", "Scheduled platform maintenance.")

        with self._lock:
            if tenant_id:
                self._tenant_maintenance[tenant_id] = enabled
                maintenance_scope = f"tenant:{tenant_id}"
            else:
                self._global_maintenance = enabled
                maintenance_scope = "global"

            if enabled:
                self._maintenance_reasons[maintenance_scope] = reason_str
                self._activated_at[maintenance_scope] = now_str
            else:
                self._maintenance_reasons.pop(maintenance_scope, None)
                self._activated_at.pop(maintenance_scope, None)

        logger.info(
            "Maintenance mode updated: enabled=%s, tenant_id=%s, reason=%s",
            enabled,
            tenant_id,
            reason_str,
        )
        return {
            "enabled": enabled,
            "scope": "tenant" if tenant_id else "global",
            "tenant_id": tenant_id,
            "reason": reason_str,
            "timestamp": now_str,
        }

    def get_status(self, tenant_id: str | None = None) -> dict[str, Any]:
        """Returns maintenance status details for banner and telemetry."""
        with self._lock:
            is_active = self._global_maintenance or (
                bool(tenant_id and self._tenant_maintenance.get(tenant_id, False))
            )
            maintenance_scope = f"tenant:{tenant_id}" if (tenant_id and self._tenant_maintenance.get(tenant_id)) else "global"
            return {
                "active": is_active,
                "global_active": self._global_maintenance,
                "tenant_active": bool(tenant_id and self._tenant_maintenance.get(tenant_id, False)),
                "message": self._maintenance_reasons.get(
                    maintenance_scope,
                    self._config.get("default_message", "Platform is under maintenance."),
                ),
                "retry_after_seconds": self._config.get("retry_after_seconds", 300),
                "activated_at": self._activated_at.get(maintenance_scope),
            }

    def is_request_exempt(self, path: str, method: str, roles: list[str] | None = None) -> bool:
        """Evaluates whether an API request is exempt from maintenance mode rejection."""
        if method.upper() in {"GET", "HEAD", "OPTIONS"}:
            return True

        # Check exempt path prefixes
        exempt_prefixes = self._config.get("exempt_path_prefixes", [])
        for prefix in exempt_prefixes:
            if path.startswith(prefix):
                return True

        # Check exempt roles (e.g. SUPER_ADMIN, PLATFORM_ADMIN unflagging maintenance)
        exempt_roles = set(self._config.get("exempt_roles", ["SUPER_ADMIN", "PLATFORM_ADMIN"]))
        if roles and (set(roles) & exempt_roles):
            # Admin actions on control-tower are permitted
            if path.startswith("/api/v1/control-tower"):
                return True

        return False


_MAINTENANCE_SERVICE_INSTANCE = MaintenanceModeService()


def get_maintenance_mode_service() -> MaintenanceModeService:
    """Returns singleton maintenance mode service instance."""
    return _MAINTENANCE_SERVICE_INSTANCE
