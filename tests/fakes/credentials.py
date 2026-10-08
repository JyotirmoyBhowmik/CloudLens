"""In-memory fake for CredentialProfile unit testing."""

from __future__ import annotations

from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession

from domain.credentials.models import CredentialProfile
from domain.models.enums import ProviderType


class InMemoryCredentialRepository:
    """In-memory test fake for CredentialProfile repository."""

    is_in_memory: bool = True

    def __init__(self) -> None:
        self._profiles: dict[str, CredentialProfile] = {}

    async def get(self, profile_id: str, session: AsyncSession | None = None) -> CredentialProfile | None:
        return self._profiles.get(profile_id)

    async def save(self, profile: CredentialProfile, session: AsyncSession | None = None) -> CredentialProfile:
        if not profile.secret_ref.startswith("vault://"):
            raise ValueError(f"Secret reference must start with 'vault://', got: '{profile.secret_ref}'")
        self._profiles[profile.id] = profile
        return profile

    async def list_for_tenant(
        self, tenant_id: str, provider: ProviderType | None = None, session: AsyncSession | None = None
    ) -> list[CredentialProfile]:
        profiles = [p for p in self._profiles.values() if p.tenant_id == tenant_id]
        if provider:
            profiles = [p for p in profiles if p.provider == provider]
        return profiles

    async def delete(self, profile_id: str, session: AsyncSession | None = None) -> bool:
        return bool(self._profiles.pop(profile_id, None))

    def get_sync(self, profile_id: str) -> CredentialProfile | None:
        return self._profiles.get(profile_id)

    def save_sync(self, profile: CredentialProfile) -> CredentialProfile:
        if not profile.secret_ref.startswith("vault://"):
            raise ValueError(f"Secret reference must start with 'vault://', got: '{profile.secret_ref}'")
        self._profiles[profile.id] = profile
        return profile

    def list_for_tenant_sync(
        self, tenant_id: str, provider: ProviderType | None = None
    ) -> list[CredentialProfile]:
        profiles = [p for p in self._profiles.values() if p.tenant_id == tenant_id]
        if provider:
            profiles = [p for p in profiles if p.provider == provider]
        return profiles

    def delete_sync(self, profile_id: str) -> bool:
        return bool(self._profiles.pop(profile_id, None))
