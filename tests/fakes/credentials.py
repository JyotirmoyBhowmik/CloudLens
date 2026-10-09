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


import copy
import logging
import threading
import urllib.parse
from domain.credentials.store import SecretStore
from domain.models.exceptions import (
    CredentialNotFoundException,
    CrossTenantCredentialAccessException,
    SecretStoreUnavailableException,
)

logger = logging.getLogger("cloudlens.fakes.credentials")


class InMemorySecretStore(SecretStore):
    """Thread-safe in-memory test fake simulating external HashiCorp Vault KV v2."""

    is_in_memory: bool = True

    def __init__(self, mount_point: str = "secret") -> None:
        self._mount_point = mount_point
        self._secrets: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def _build_reference_uri(self, tenant_id: str, profile_id: str, version: int) -> str:
        clean_tenant = urllib.parse.quote(tenant_id, safe="")
        clean_profile = urllib.parse.quote(profile_id, safe="")
        return f"vault://{self._mount_point}/data/tenants/{clean_tenant}/credentials/{clean_profile}/v{version}"

    def store_secret(
        self,
        tenant_id: str,
        profile_id: str,
        version: int,
        secret_data: dict[str, Any],
    ) -> str:
        if not secret_data:
            raise SecretStoreUnavailableException("Cannot store empty credential payload in SecretStore.")

        ref_uri = self._build_reference_uri(tenant_id, profile_id, version)
        with self._lock:
            self._secrets[ref_uri] = copy.deepcopy(secret_data)
        return ref_uri

    def _validate_tenant_scope(self, secret_ref: str, tenant_id: str | None) -> None:
        if tenant_id:
            clean_tenant = urllib.parse.quote(tenant_id, safe="")
            expected_prefix = f"/tenants/{clean_tenant}/"
            if expected_prefix not in secret_ref:
                raise CrossTenantCredentialAccessException(
                    profile_id=secret_ref,
                    caller_tenant_id=tenant_id,
                    owner_tenant_id="external",
                )

    def get_secret(
        self,
        secret_ref: str,
        tenant_id: str | None = None,
        actor: str | None = None,
        purpose: str | None = None,
    ) -> dict[str, Any]:
        self._validate_tenant_scope(secret_ref, tenant_id)
        with self._lock:
            secret = self._secrets.get(secret_ref)
        if secret is None:
            raise CredentialNotFoundException(profile_id=secret_ref, tenant_id=tenant_id)
        return copy.deepcopy(secret)

    def delete_secret(self, secret_ref: str, tenant_id: str | None = None) -> bool:
        self._validate_tenant_scope(secret_ref, tenant_id)
        with self._lock:
            return self._secrets.pop(secret_ref, None) is not None

    def has_secret(self, secret_ref: str) -> bool:
        with self._lock:
            return secret_ref in self._secrets

    def health_check(self) -> bool:
        return True

    def clear(self) -> None:
        with self._lock:
            self._secrets.clear()
