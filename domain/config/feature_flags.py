"""CloudLens Feature Flag Evaluation Service & Audit Hook.

Enforces:
1. Strict registration check: unregistered flags raise UnregisteredFeatureFlagError.
2. Global and tenant-scoped evaluations.
3. Automated audit logging for every flag state change.
"""

import os
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from masterdata.registries.feature_flags import FEATURE_FLAG_REGISTRY, FeatureFlagDefinition


class UnregisteredFeatureFlagError(ValueError):
    """Raised when an application attempts to evaluate or mutate an unregistered feature flag."""

    def __init__(self, flag_key: str):
        super().__init__(
            f"Feature flag '{flag_key}' is not registered in the canonical registry. "
            f"All flags must be explicitly declared in masterdata/registries/feature_flags.py."
        )
        self.flag_key = flag_key


class FlagAuditEvent(BaseModel):
    """Audit trail record for feature flag modifications."""

    flag_key: str = Field(description="Feature flag identifier")
    tenant_id: str | None = Field(default=None, description="Tenant scope if tenant-specific")
    old_value: bool = Field(description="Previous toggle state")
    new_value: bool = Field(description="New toggle state")
    changed_by: str = Field(description="Identity / principal who changed the flag")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(), description="ISO UTC timestamp"
    )
    reason: str = Field(default="", description="Audit rationale for change")


class FeatureFlagService:
    """Evaluates and manages feature flags globally and per-tenant."""

    def __init__(self) -> None:
        # (tenant_id, flag_key) -> bool
        self._tenant_overrides: dict[tuple[str, str], bool] = {}
        # flag_key -> bool
        self._global_overrides: dict[str, bool] = {}
        # Audit log history
        self._audit_log: list[FlagAuditEvent] = []

    def is_registered(self, flag_key: str) -> bool:
        """Check whether a flag is in the canonical registry."""
        return flag_key in FEATURE_FLAG_REGISTRY

    def get_definition(self, flag_key: str) -> FeatureFlagDefinition:
        """Retrieve flag definition from registry, raising error if unregistered."""
        if not self.is_registered(flag_key):
            raise UnregisteredFeatureFlagError(flag_key)
        return FEATURE_FLAG_REGISTRY[flag_key]

    def evaluate(self, flag_key: str, tenant_id: str | None = None) -> bool:
        """Evaluate effective state for a flag.

        Precedence order:
        1. Tenant override (if tenant_id provided)
        2. Global runtime override
        3. Environment variable (CLOUDLENS_FLAG_<KEY_UPPER>)
        4. Canonical registry default
        """
        definition = self.get_definition(flag_key)

        # 1. Tenant override
        if tenant_id is not None and (tenant_id, flag_key) in self._tenant_overrides:
            return self._tenant_overrides[(tenant_id, flag_key)]

        # 2. Global runtime override
        if flag_key in self._global_overrides:
            return self._global_overrides[flag_key]

        # 3. Environment variable
        env_var_name = f"CLOUDLENS_FLAG_{flag_key.upper()}"
        if env_var_name in os.environ:
            val = os.environ[env_var_name].strip().lower()
            return val in ("1", "true", "yes", "on")

        # 4. Canonical default
        return definition.default_enabled

    def set_flag(
        self,
        flag_key: str,
        enabled: bool,
        tenant_id: str | None = None,
        changed_by: str = "system",
        reason: str = "",
    ) -> FlagAuditEvent:
        """Set feature flag override and record audit event."""
        # Validate registration
        self.get_definition(flag_key)

        current_val = self.evaluate(flag_key, tenant_id=tenant_id)

        if tenant_id is not None:
            self._tenant_overrides[(tenant_id, flag_key)] = enabled
        else:
            self._global_overrides[flag_key] = enabled

        audit_event = FlagAuditEvent(
            flag_key=flag_key,
            tenant_id=tenant_id,
            old_value=current_val,
            new_value=enabled,
            changed_by=changed_by,
            reason=reason,
        )
        self._audit_log.append(audit_event)
        return audit_event

    def get_audit_log(
        self,
        flag_key: str | None = None,
        tenant_id: str | None = None,
    ) -> list[FlagAuditEvent]:
        """Query feature flag audit log with optional filtering."""
        results = self._audit_log
        if flag_key:
            results = [e for e in results if e.flag_key == flag_key]
        if tenant_id:
            results = [e for e in results if e.tenant_id == tenant_id]
        return list(reversed(results))

    def list_flags(self, tenant_id: str | None = None) -> list[dict[str, Any]]:
        """List all canonical flags with effective values."""
        results = []
        for key, definition in sorted(FEATURE_FLAG_REGISTRY.items()):
            effective = self.evaluate(key, tenant_id=tenant_id)
            results.append(
                {
                    "key": key,
                    "name": definition.name,
                    "description": definition.description,
                    "stage": definition.stage,
                    "category": definition.category,
                    "default_enabled": definition.default_enabled,
                    "effective_enabled": effective,
                    "tenant_id": tenant_id,
                }
            )
        return results

    def reset(self) -> None:
        """Reset all runtime overrides and audit entries (for testing)."""
        self._tenant_overrides.clear()
        self._global_overrides.clear()
        self._audit_log.clear()


# Global singleton instance
feature_flag_service = FeatureFlagService()
