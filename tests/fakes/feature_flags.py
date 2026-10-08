"""In-memory fake for FeatureFlagRepository unit testing."""

from __future__ import annotations

from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession

from domain.config.feature_flags import FlagAuditEvent


class InMemoryFeatureFlagRepository:
    """In-memory test fake for FeatureFlagRepository."""

    is_in_memory: bool = True

    def __init__(self) -> None:
        self._tenant_overrides: dict[tuple[str, str], bool] = {}
        self._global_overrides: dict[str, bool] = {}
        self._audit_log: list[FlagAuditEvent] = []

    async def get_override(
        self, flag_key: str, tenant_id: str | None = None, session: AsyncSession | None = None
    ) -> bool | None:
        if tenant_id:
            return self._tenant_overrides.get((tenant_id, flag_key))
        return self._global_overrides.get(flag_key)

    async def set_override(
        self,
        flag_key: str,
        enabled: bool,
        tenant_id: str | None = None,
        updated_by: str = "system",
        reason: str = "",
        session: AsyncSession | None = None,
    ) -> None:
        if tenant_id:
            self._tenant_overrides[(tenant_id, flag_key)] = enabled
        else:
            self._global_overrides[flag_key] = enabled

    async def record_audit(
        self, event: FlagAuditEvent, session: AsyncSession | None = None
    ) -> None:
        self._audit_log.append(event)

    async def get_audit_log(
        self,
        flag_key: str | None = None,
        tenant_id: str | None = None,
        session: AsyncSession | None = None,
    ) -> list[FlagAuditEvent]:
        res = self._audit_log
        if flag_key:
            res = [e for e in res if e.flag_key == flag_key]
        if tenant_id:
            res = [e for e in res if e.tenant_id == tenant_id]
        return list(reversed(res))

    def get_override_sync(self, flag_key: str, tenant_id: str | None = None) -> bool | None:
        if tenant_id:
            return self._tenant_overrides.get((tenant_id, flag_key))
        return self._global_overrides.get(flag_key)

    def set_override_sync(
        self,
        flag_key: str,
        enabled: bool,
        tenant_id: str | None = None,
        updated_by: str = "system",
        reason: str = "",
    ) -> None:
        if tenant_id:
            self._tenant_overrides[(tenant_id, flag_key)] = enabled
        else:
            self._global_overrides[flag_key] = enabled

    def record_audit_sync(self, event: FlagAuditEvent) -> None:
        self._audit_log.append(event)

    def get_audit_log_sync(
        self, flag_key: str | None = None, tenant_id: str | None = None
    ) -> list[FlagAuditEvent]:
        res = self._audit_log
        if flag_key:
            res = [e for e in res if e.flag_key == flag_key]
        if tenant_id:
            res = [e for e in res if e.tenant_id == tenant_id]
        return list(reversed(res))
