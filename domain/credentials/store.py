"""Dedicated Secret Store Integration & Reference Engine (Prompt 12 Item 77).

Enforces:
- SEC-008 & SEC-009: Provider credential material is written directly to the secret store.
  The application database and entities hold ONLY an opaque reference URI.
- Pure reference-pattern: Credential material is never stored in application database columns
  even in encrypted form.
- Direct-write and deterministic revocation: Emergency revoke immediately purges raw material.
"""

import copy
import logging
import os
import sys
import threading
import urllib.parse
from abc import ABC, abstractmethod
from typing import Any

import httpx

from domain.config.surface import SecretStoreConfig
from domain.models.exceptions import (
    CredentialNotFoundException,
    CrossTenantCredentialAccessException,
    SecretStoreUnavailableException,
)

logger = logging.getLogger(__name__)


class SecretStore(ABC):
    """Abstract interface defining the dedicated external secret store contract."""

    @abstractmethod
    def store_secret(
        self,
        tenant_id: str,
        profile_id: str,
        version: int,
        secret_data: dict[str, Any],
    ) -> str:
        """Stores raw credential material directly into dedicated secret store.

        Returns an opaque reference URI (e.g. vault://secret/data/tenants/{tenant_id}/credentials/{profile_id}/v{version}).
        """
        pass

    @abstractmethod
    def get_secret(self, secret_ref: str, tenant_id: str | None = None) -> dict[str, Any]:
        """Retrieves raw credential material by opaque reference URI.

        Accessible ONLY to runtime cloud connectors during sync or connection verification.
        Validates tenant-scoped path if tenant_id is provided.
        """
        pass

    @abstractmethod
    def delete_secret(self, secret_ref: str, tenant_id: str | None = None) -> bool:
        """Permanently deletes credential material from the store upon revocation."""
        pass

    @abstractmethod
    def has_secret(self, secret_ref: str) -> bool:
        """Checks if a secret exists and has not been revoked."""
        pass

    @abstractmethod
    def health_check(self) -> bool:
        """Verifies store availability and responsiveness."""
        pass


class InMemorySecretStore(SecretStore):
    """Thread-safe, reference-based secret store simulating external HashiCorp Vault KV v2.

    Guarantees strict reference isolation: raw credential material exists ONLY in this
    dedicated storage boundary and is referenced across the platform solely by opaque URI.
    """

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
            raise SecretStoreUnavailableException(
                "Cannot store empty credential payload in SecretStore."
            )

        ref_uri = self._build_reference_uri(tenant_id, profile_id, version)
        with self._lock:
            # Store deep copy so mutations outside cannot corrupt stored secret material
            self._secrets[ref_uri] = copy.deepcopy(secret_data)

        logger.info(
            "Credential material written directly to dedicated secret store",
            extra={"tenant_id": tenant_id, "secret_ref": ref_uri, "version": version},
        )
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
        effective_actor = actor or "system"
        # Item 2.5: Secret reads are audited (actor, ref, purpose); secret VALUES never logged
        logger.info(
            "Secret material accessed from dedicated secret store",
            extra={
                "actor": effective_actor,
                "secret_ref": secret_ref,
                "purpose": purpose or "credential_read",
                "tenant_id": tenant_id,
            },
        )
        with self._lock:
            secret = self._secrets.get(secret_ref)

        if secret is None:
            raise CredentialNotFoundException(
                profile_id=secret_ref,
                tenant_id=tenant_id,
            )
        return copy.deepcopy(secret)

    def delete_secret(self, secret_ref: str, tenant_id: str | None = None) -> bool:
        self._validate_tenant_scope(secret_ref, tenant_id)
        with self._lock:
            removed = self._secrets.pop(secret_ref, None) is not None

        if removed:
            logger.info(
                "Credential material permanently purged from secret store",
                extra={"secret_ref": secret_ref},
            )
        return removed

    def has_secret(self, secret_ref: str) -> bool:
        with self._lock:
            return secret_ref in self._secrets

    def health_check(self) -> bool:
        return True

    def clear(self) -> None:
        """Utility for test suite reset."""
        with self._lock:
            self._secrets.clear()


class VaultSecretStore(SecretStore):
    """HashiCorp Vault and OpenBao KV v2 secret store implementation (Prompt R-SEC Part 2).

    Directly interacts with HashiCorp Vault / OpenBao KV v2 HTTP API via httpx.
    Supports Token (dev env), AppRole, and Kubernetes Service Account authentication.
    """

    def __init__(self, config: SecretStoreConfig, client: httpx.Client | None = None) -> None:
        self.config = config
        self._client = client or httpx.Client(timeout=10.0)
        self._cached_token: str | None = None
        self._token_lock = threading.Lock()

    def _build_reference_uri(self, tenant_id: str, profile_id: str, version: int) -> str:
        clean_tenant = urllib.parse.quote(tenant_id, safe="")
        clean_profile = urllib.parse.quote(profile_id, safe="")
        return f"vault://{self.config.mount_point}/data/tenants/{clean_tenant}/credentials/{clean_profile}/v{version}"

    def _extract_subpath(self, secret_ref: str) -> str:
        prefix = f"vault://{self.config.mount_point}/data/"
        if secret_ref.startswith(prefix):
            return secret_ref[len(prefix) :]
        parts = urllib.parse.urlparse(secret_ref)
        path = parts.path.lstrip("/")
        if path.startswith("data/"):
            return path[len("data/") :]
        return path

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

    def _get_token(self) -> str:
        with self._token_lock:
            if self._cached_token:
                return self._cached_token

            auth_method = (self.config.auth_method or "token").lower()
            vault_url = self.config.vault_url.rstrip("/")

            # 1. AppRole Authentication
            if auth_method == "approle" or (self.config.role_id and self.config.secret_id):
                try:
                    resp = self._client.post(
                        f"{vault_url}/v1/auth/approle/login",
                        json={"role_id": self.config.role_id, "secret_id": self.config.secret_id},
                    )
                    resp.raise_for_status()
                    self._cached_token = resp.json()["auth"]["client_token"]
                    return self._cached_token
                except Exception as e:
                    raise SecretStoreUnavailableException(f"Vault AppRole authentication failed: {e}") from e

            # 2. Kubernetes Service Account Authentication
            elif auth_method == "kubernetes" or self.config.kubernetes_role:
                try:
                    jwt_path = self.config.kubernetes_jwt_path
                    with open(jwt_path, encoding="utf-8") as f:
                        jwt_token = f.read().strip()
                    resp = self._client.post(
                        f"{vault_url}/v1/auth/kubernetes/login",
                        json={"role": self.config.kubernetes_role, "jwt": jwt_token},
                    )
                    resp.raise_for_status()
                    self._cached_token = resp.json()["auth"]["client_token"]
                    return self._cached_token
                except Exception as e:
                    raise SecretStoreUnavailableException(f"Vault Kubernetes authentication failed: {e}") from e

            # 3. Token Authentication (dev env / explicit config)
            else:
                token = (
                    self.config.vault_token
                    or os.getenv("VAULT_TOKEN")
                    or os.getenv("VAULT_DEV_ROOT_TOKEN_ID")
                )
                if not token:
                    raise SecretStoreUnavailableException(
                        "Vault authentication token missing. Configure token, AppRole or Kubernetes auth."
                    )
                self._cached_token = token
                return token

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
        clean_tenant = urllib.parse.quote(tenant_id, safe="")
        clean_profile = urllib.parse.quote(profile_id, safe="")
        subpath = f"tenants/{clean_tenant}/credentials/{clean_profile}/v{version}"
        vault_url = self.config.vault_url.rstrip("/")
        url = f"{vault_url}/v1/{self.config.mount_point}/data/{subpath}"

        token = self._get_token()
        try:
            resp = self._client.post(
                url,
                headers={"X-Vault-Token": token},
                json={"data": secret_data},
            )
            if resp.status_code not in (200, 204):
                raise SecretStoreUnavailableException(
                    f"Vault KV v2 store failed with status {resp.status_code}: {resp.text}"
                )
        except SecretStoreUnavailableException:
            raise
        except Exception as e:
            raise SecretStoreUnavailableException(f"Vault store connection failure: {e}") from e

        logger.info(
            "Credential material written directly to Vault KV v2 secret store",
            extra={"tenant_id": tenant_id, "secret_ref": ref_uri, "version": version},
        )
        return ref_uri

    def get_secret(
        self,
        secret_ref: str,
        tenant_id: str | None = None,
        actor: str | None = None,
        purpose: str | None = None,
    ) -> dict[str, Any]:
        self._validate_tenant_scope(secret_ref, tenant_id)
        effective_actor = actor or "system"

        # Item 2.5: Secret reads are audited (actor, ref, purpose); secret VALUES never logged
        logger.info(
            "Secret material accessed from dedicated Vault secret store",
            extra={
                "actor": effective_actor,
                "secret_ref": secret_ref,
                "purpose": purpose or "credential_read",
                "tenant_id": tenant_id,
            },
        )

        subpath = self._extract_subpath(secret_ref)
        vault_url = self.config.vault_url.rstrip("/")
        url = f"{vault_url}/v1/{self.config.mount_point}/data/{subpath}"
        token = self._get_token()

        try:
            resp = self._client.get(url, headers={"X-Vault-Token": token})
            if resp.status_code == 404:
                raise CredentialNotFoundException(profile_id=secret_ref, tenant_id=tenant_id)
            if resp.status_code != 200:
                raise SecretStoreUnavailableException(
                    f"Vault KV v2 get failed with status {resp.status_code}: {resp.text}"
                )
            payload = resp.json()
            data = payload.get("data", {}).get("data")
            if data is None:
                raise CredentialNotFoundException(profile_id=secret_ref, tenant_id=tenant_id)
            return copy.deepcopy(data)
        except (CredentialNotFoundException, SecretStoreUnavailableException):
            raise
        except Exception as e:
            raise SecretStoreUnavailableException(f"Vault get connection failure: {e}") from e

    def delete_secret(self, secret_ref: str, tenant_id: str | None = None) -> bool:
        self._validate_tenant_scope(secret_ref, tenant_id)
        subpath = self._extract_subpath(secret_ref)
        vault_url = self.config.vault_url.rstrip("/")
        url = f"{vault_url}/v1/{self.config.mount_point}/metadata/{subpath}"
        token = self._get_token()

        try:
            resp = self._client.delete(url, headers={"X-Vault-Token": token})
            if resp.status_code in (200, 204):
                logger.info(
                    "Credential material permanently purged from Vault KV v2 store",
                    extra={"secret_ref": secret_ref},
                )
                return True
            return False
        except Exception as e:
            logger.error(f"Vault delete failed: {e}")
            return False

    def has_secret(self, secret_ref: str) -> bool:
        subpath = self._extract_subpath(secret_ref)
        vault_url = self.config.vault_url.rstrip("/")
        url = f"{vault_url}/v1/{self.config.mount_point}/data/{subpath}"
        try:
            token = self._get_token()
            resp = self._client.get(url, headers={"X-Vault-Token": token})
            return resp.status_code == 200
        except Exception:
            return False

    def health_check(self) -> bool:
        vault_url = self.config.vault_url.rstrip("/")
        url = f"{vault_url}/v1/sys/health"
        try:
            resp = self._client.get(url)
            # 200: healthy active; 429: standby; 472/473: performance/DR standby
            return resp.status_code in (200, 429, 472, 473)
        except Exception:
            return False


# Global default store instance
_global_secret_store: SecretStore | None = None
_store_lock = threading.Lock()


def get_secret_store(config: SecretStoreConfig | None = None) -> SecretStore:
    """Singleton provider for active dedicated SecretStore (Prompt R-SEC Part 2).

    InMemorySecretStore is selectable ONLY when CLOUDLENS_ENV=development AND backend_type=memory explicitly.
    """
    global _global_secret_store
    with _store_lock:
        if _global_secret_store is None:
            cfg = config or SecretStoreConfig()
            env = os.getenv("CLOUDLENS_ENV", "development").lower()
            backend = (os.getenv("SECRET_STORE_BACKEND") or cfg.backend_type or "vault").lower()

            if backend == "vault":
                _global_secret_store = VaultSecretStore(cfg)
            elif backend == "memory":
                if env != "development":
                    logger.critical(
                        "InMemorySecretStore is strictly forbidden in %s environment. Refusing to initialize.",
                        env,
                    )
                    raise SecretStoreUnavailableException(
                        f"InMemorySecretStore is permitted ONLY when CLOUDLENS_ENV=development. Current env: {env}"
                    )
                _global_secret_store = InMemorySecretStore(mount_point=cfg.mount_point)
            else:
                if env in ("staging", "production"):
                    logger.critical(
                        "Backend type '%s' is strictly forbidden in %s. Only 'vault' is permitted.",
                        backend,
                        env,
                    )
                    raise SecretStoreUnavailableException(f"Unsupported backend '{backend}' in {env}")
                _global_secret_store = InMemorySecretStore(mount_point=cfg.mount_point)
        return _global_secret_store


def verify_secret_store_startup_guard() -> None:
    """Startup guard: in staging/production, fail closed if backend is not vault or health_check fails."""
    env = os.getenv("CLOUDLENS_ENV", "development").lower()
    if env in ("staging", "production"):
        cfg = SecretStoreConfig()
        backend = (os.getenv("SECRET_STORE_BACKEND") or cfg.backend_type or "").lower()
        if backend != "vault":
            logger.critical(
                "CRITICAL STARTUP FAILURE: CLOUDLENS_ENV is '%s' but secret store backend is '%s' (not 'vault'). Exiting non-zero.",
                env,
                backend,
            )
            sys.exit(1)
        store = get_secret_store(cfg)
        if not store.health_check():
            logger.critical(
                "CRITICAL STARTUP FAILURE: CLOUDLENS_ENV is '%s' but Vault health_check() failed. Exiting non-zero.",
                env,
            )
            sys.exit(1)


def reset_secret_store() -> None:
    """Resets global secret store singleton for unit test isolation."""
    global _global_secret_store
    with _store_lock:
        if _global_secret_store and isinstance(_global_secret_store, InMemorySecretStore):
            _global_secret_store.clear()
        _global_secret_store = None

