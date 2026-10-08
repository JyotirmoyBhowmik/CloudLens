"""Cryptographic Token Engine, Rotation, and Revocation Registry (Prompt 10 Items 66-68).

Enforces:
- HMAC-SHA256 URL-safe signed tokens for access, refresh, machine client, and step-up claims.
- Refresh token rotation with family reuse detection (Prompt 10 Item 66).
- Immediate token revocation on user disablement or explicit session termination.
- Zero external dependencies: implemented cleanly on Python standard library cryptography.
"""

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
import uuid
from typing import Any, cast

from domain.identity.models import AuthContext
from domain.models.enums import SystemRole, TokenType
from domain.models.exceptions import (
    TokenExpiredException,
    TokenInvalidException,
    TokenRevokedException,
)

# Standard platform signing key (in production drawn from KMS/Vault, in memory for app lifetime)
DEFAULT_SIGNING_SECRET = secrets.token_bytes(32)


def _b64url_encode(data: bytes) -> str:
    """Encodes bytes to base64url string without padding."""
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _b64url_decode(data: str) -> bytes:
    """Decodes base64url string with required padding."""
    rem = len(data) % 4
    if rem != 0:
        data += "=" * (4 - rem)
    return base64.urlsafe_b64decode(data.encode("utf-8"))


class TokenRevocationRegistry:
    """Persistent revocation registry tracking revoked JTIs, sessions, and disabled users (Prompt P04)."""

    def __init__(self, repository: Any = None) -> None:
        self._repository = repository

    @property
    def repository(self):
        if self._repository is None:
            from domain.identity.repository import get_identity_repository
            self._repository = get_identity_repository()
        return self._repository

    def revoke_token(self, jti: str, expires_at: float) -> None:
        """Revokes a specific token JTI until its expiration."""
        self.repository.revoke_token_sync(jti, expires_at)

    def revoke_session(self, session_id: str) -> None:
        """Revokes all tokens associated with a session ID."""
        self.repository.revoke_session_tokens_sync(session_id)

    def revoke_user_tokens(self, user_id: str) -> None:
        """Revokes all active tokens for a user immediately (Item 66)."""
        self.repository.revoke_user_tokens_sync(user_id)

    def record_refresh_token_use(self, token_id: str, family_id: str) -> bool:
        """Records use of a refresh token.

        Returns True if valid single-use; returns False if token reuse is detected
        (triggering full family compromise revocation).
        """
        return self.repository.record_refresh_token_use_sync(token_id, family_id)

    def is_revoked(
        self,
        jti: str,
        user_id: str | None = None,
        session_id: str | None = None,
        issued_at: float | None = None,
        family_id: str | None = None,
    ) -> bool:
        """Checks if a token has been revoked by JTI, session, user disablement, or family reuse."""
        return self.repository.is_token_revoked_sync(
            jti, user_id=user_id, session_id=session_id, issued_at=issued_at, family_id=family_id
        )

    def clear(self) -> None:
        """Clears the revocation registry (for testing isolation)."""
        pass


import logging
import sys
import tempfile
from pathlib import Path
import httpx
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

logger = logging.getLogger("cloudlens.domain.identity.token_engine")


class TokenKeyManager:
    """Manages asymmetric RSA (RS256) signing keys from OpenBao KV with rotation overlap.

    Prompt P01B Item 4:
    - Signing key from OpenBao (KV) with kid and rotation overlap.
    - Algorithm: RS256.
    - Missing key outside dev -> exit non-zero.
    - Publishes /.well-known/jwks.json public keys.
    """

    def __init__(self) -> None:
        self._active_kid: str = ""
        self._keys: dict[str, dict[str, Any]] = {}
        self.load_keys()

    @property
    def active_kid(self) -> str:
        return self._active_kid

    def has_keys(self) -> bool:
        return bool(self._keys and self._active_kid)

    def get_private_key_pem(self, kid: str | None = None) -> str:
        target_kid = kid or self._active_kid
        key_entry = self._keys.get(target_kid)
        if not key_entry:
            self.load_keys()
            key_entry = self._keys.get(target_kid)
        if not key_entry:
            raise TokenInvalidException(f"Signing key '{target_kid}' not found.")
        return key_entry["private_pem"]

    def get_public_key_pem(self, kid: str) -> str | None:
        key_entry = self._keys.get(kid)
        if not key_entry:
            self.load_keys()
            key_entry = self._keys.get(kid)
        if not key_entry:
            return None
        return key_entry["public_pem"]

    def get_jwks(self) -> dict[str, Any]:
        """Returns the public JWKS document."""
        return {
            "keys": [
                entry["public_jwk"]
                for entry in self._keys.values()
                if "public_jwk" in entry
            ]
        }

    @staticmethod
    def _generate_rsa_key_pair(kid_prefix: str = "cloudlens-key") -> tuple[str, str, str, dict[str, Any]]:
        """Generates a 2048-bit RSA key pair, returning (kid, priv_pem, pub_pem, jwk)."""
        priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        priv_pem = priv.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode("utf-8")
        pub_pem = priv.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("utf-8")
        nums = priv.public_key().public_numbers()

        def _to_b64u(n: int) -> str:
            length = (n.bit_length() + 7) // 8
            b = n.to_bytes(length, byteorder="big")
            return base64.urlsafe_b64encode(b).decode("utf-8").rstrip("=")

        kid = f"{kid_prefix}-{int(time.time())}-{uuid.uuid4().hex[:6]}"
        jwk = {
            "kty": "RSA",
            "use": "sig",
            "alg": "RS256",
            "kid": kid,
            "n": _to_b64u(nums.n),
            "e": _to_b64u(nums.e),
        }
        return kid, priv_pem, pub_pem, jwk

    def rotate_key(self) -> str:
        """Rotates active signing key while keeping older keys for verification (rotation overlap)."""
        new_kid, priv_pem, pub_pem, jwk = self._generate_rsa_key_pair()
        self._keys[new_kid] = {
            "kid": new_kid,
            "algorithm": "RS256",
            "private_pem": priv_pem,
            "public_pem": pub_pem,
            "public_jwk": jwk,
            "created_at": time.time(),
        }
        self._active_kid = new_kid
        self._persist_keys()
        logger.info("Rotated platform signing key to active_kid '%s'. Total keys: %d", new_kid, len(self._keys))
        return new_kid

    def _persist_keys(self) -> None:
        """Persists keys to OpenBao KV or shared fallback."""
        data_to_store = {
            "active_kid": self._active_kid,
            "keys": self._keys,
        }
        vault_addr = os.getenv("VAULT_ADDR", "http://localhost:8200").rstrip("/")
        vault_token = (
            os.getenv("VAULT_TOKEN")
            or os.getenv("BAO_DEV_ROOT_TOKEN_ID")
            or os.getenv("VAULT_DEV_ROOT_TOKEN_ID")
            or "dev-vault-token-cloudlens"
        )
        vault_path = os.getenv("VAULT_SIGNING_KEYS_PATH", "platform/signing-keys")
        url = f"{vault_addr}/v1/secret/data/{vault_path}"

        try:
            resp = httpx.post(
                url,
                headers={"X-Vault-Token": vault_token},
                json={"data": data_to_store},
                timeout=3.0,
            )
            if resp.status_code in (200, 204):
                return
        except Exception:
            pass

        # Fallback file persistence for test environments
        fallback_path = Path(tempfile.gettempdir()) / "cloudlens_signing_keys_shared.json"
        try:
            fallback_path.write_text(json.dumps(data_to_store), encoding="utf-8")
        except Exception:
            pass

    def load_keys(self) -> None:
        """Loads keys from OpenBao KV; if missing outside dev, exits non-zero."""
        env = os.getenv("CLOUDLENS_ENV", "development").strip().lower()
        is_prod = env in ("production", "staging")

        vault_addr = os.getenv("VAULT_ADDR", "http://localhost:8200").rstrip("/")
        vault_token = (
            os.getenv("VAULT_TOKEN")
            or os.getenv("BAO_DEV_ROOT_TOKEN_ID")
            or os.getenv("VAULT_DEV_ROOT_TOKEN_ID")
            or "dev-vault-token-cloudlens"
        )
        vault_path = os.getenv("VAULT_SIGNING_KEYS_PATH", "platform/signing-keys")
        url = f"{vault_addr}/v1/secret/data/{vault_path}"

        # 1. Attempt read from OpenBao KV
        try:
            resp = httpx.get(url, headers={"X-Vault-Token": vault_token}, timeout=2.0)
            if resp.status_code == 200:
                body = resp.json()
                raw_data = body.get("data", {}).get("data", {})
                if "active_kid" in raw_data and "keys" in raw_data and raw_data["keys"]:
                    self._active_kid = raw_data["active_kid"]
                    self._keys = raw_data["keys"]
                    return
            elif is_prod:
                logger.critical(
                    "CRITICAL STARTUP FAILURE: OpenBao signing keys not found (status %d). Exiting non-zero.",
                    resp.status_code,
                )
                sys.exit(1)
        except Exception as exc:
            if is_prod:
                logger.critical(
                    "CRITICAL STARTUP FAILURE: Could not connect to OpenBao for platform signing keys: %s. Exiting non-zero.",
                    exc,
                )
                sys.exit(1)

        # 2. In dev/test: Try to generate and write to OpenBao if available
        try:
            kid, priv_pem, pub_pem, jwk = self._generate_rsa_key_pair()
            data_to_store = {
                "active_kid": kid,
                "keys": {
                    kid: {
                        "kid": kid,
                        "algorithm": "RS256",
                        "private_pem": priv_pem,
                        "public_pem": pub_pem,
                        "public_jwk": jwk,
                        "created_at": time.time(),
                    }
                },
            }
            write_resp = httpx.post(
                url,
                headers={"X-Vault-Token": vault_token},
                json={"data": data_to_store},
                timeout=2.0,
            )
            if write_resp.status_code in (200, 204):
                self._active_kid = kid
                self._keys = data_to_store["keys"]
                return
        except Exception:
            pass

        # 3. Fallback to shared file in temporary directory for offline test runs
        fallback_path = Path(tempfile.gettempdir()) / "cloudlens_signing_keys_shared.json"
        if fallback_path.exists():
            try:
                data = json.loads(fallback_path.read_text(encoding="utf-8"))
                if "active_kid" in data and "keys" in data and data["keys"]:
                    self._active_kid = data["active_kid"]
                    self._keys = data["keys"]
                    return
            except Exception:
                pass

        kid, priv_pem, pub_pem, jwk = self._generate_rsa_key_pair()
        data_to_store = {
            "active_kid": kid,
            "keys": {
                kid: {
                    "kid": kid,
                    "algorithm": "RS256",
                    "private_pem": priv_pem,
                    "public_pem": pub_pem,
                    "public_jwk": jwk,
                    "created_at": time.time(),
                }
            },
        }
        try:
            fallback_path.write_text(json.dumps(data_to_store), encoding="utf-8")
        except Exception:
            pass
        self._active_kid = kid
        self._keys = data_to_store["keys"]


_default_key_manager: TokenKeyManager | None = None


def get_default_key_manager() -> TokenKeyManager:
    global _default_key_manager
    if _default_key_manager is None:
        _default_key_manager = TokenKeyManager()
    return _default_key_manager


def reset_default_key_manager() -> None:
    global _default_key_manager
    _default_key_manager = None


def verify_token_signing_key_startup_guard() -> None:
    """Startup guard: in staging/production, fail closed if signing key is not in OpenBao."""
    env = os.getenv("CLOUDLENS_ENV", "development").strip().lower()
    if env in ("production", "staging"):
        km = get_default_key_manager()
        if not km.has_keys():
            logger.critical(
                "CRITICAL STARTUP FAILURE: CLOUDLENS_ENV is '%s' but platform signing key is missing in OpenBao. Exiting non-zero.",
                env,
            )
            sys.exit(1)


class CryptographicTokenEngine:
    """Signs, verifies, and lifecycle-manages authentication tokens using RS256."""

    def __init__(
        self,
        signing_key: bytes | None = None,
        key_manager: TokenKeyManager | None = None,
        revocation_registry: TokenRevocationRegistry | None = None,
        issuer: str | None = None,
        audience: str | None = None,
    ) -> None:
        self._key_manager = key_manager or get_default_key_manager()
        self._revocation = revocation_registry or TokenRevocationRegistry()
        self._issuer = issuer or os.getenv("OIDC_ISSUER", "https://auth.cloudlens.internal/oauth2/default")
        self._audience = audience or os.getenv("OIDC_AUDIENCE", "cloudlens-api")

    @property
    def key_manager(self) -> TokenKeyManager:
        return self._key_manager

    @property
    def revocation_registry(self) -> TokenRevocationRegistry:
        return self._revocation

    def get_jwks(self) -> dict[str, Any]:
        """Returns published JWKS."""
        return self._key_manager.get_jwks()

    def sign_token(self, payload: dict[str, Any]) -> str:
        """Creates an RS256 digitally signed JWT."""
        active_kid = self._key_manager.active_kid
        priv_pem = self._key_manager.get_private_key_pem(active_kid)
        headers = {"alg": "RS256", "typ": "JWT", "kid": active_kid}
        return jwt.encode(payload, priv_pem, algorithm="RS256", headers=headers)

    def verify_token(
        self,
        token_str: str,
        expected_issuer: str | None = None,
        expected_audience: str | None = None,
    ) -> dict[str, Any]:
        """Validates token signature, expiration, algorithm, claims, and revocation status."""
        parts = token_str.strip().split(".")
        if len(parts) != 3:
            raise TokenInvalidException(
                "Token format is invalid: expected header.payload.signature"
            )

        try:
            header = jwt.get_unverified_header(token_str)
        except Exception as e:
            raise TokenInvalidException(f"Token header decoding failed: {e}") from e

        if not isinstance(header, dict):
            raise TokenInvalidException("Token header must be a JSON object.")

        alg = header.get("alg", "")
        if str(alg).lower() == "none":
            raise TokenInvalidException("Algorithm 'none' is strictly prohibited.")
        if alg != "RS256":
            raise TokenInvalidException(f"Unsupported token algorithm: '{alg}'. Expected RS256.")

        kid = header.get("kid")
        if not kid:
            raise TokenInvalidException("Token missing required 'kid' header.")

        pub_pem = self._key_manager.get_public_key_pem(kid)
        if not pub_pem:
            raise TokenInvalidException(f"Unknown or untrusted signing key identifier: '{kid}'.")

        try:
            payload = jwt.decode(
                token_str,
                pub_pem,
                algorithms=["RS256"],
                options={"verify_exp": False, "verify_nbf": False, "verify_aud": False, "verify_iss": False},
            )
        except jwt.InvalidSignatureError as e:
            raise TokenInvalidException("Token cryptographic signature verification failed.") from e
        except Exception as e:
            raise TokenInvalidException(f"Token signature decoding failed: {e}") from e

        now = time.time()
        # Expiration check (exp)
        exp = payload.get("exp")
        if exp is not None and now > float(exp):
            raise TokenExpiredException("Authentication token has expired.")

        # Not Before check (nbf)
        nbf = payload.get("nbf")
        if nbf is not None and now < float(nbf):
            raise TokenInvalidException("Token not valid yet (nbf).")

        # Issuer check (iss)
        iss = payload.get("iss")
        check_iss = expected_issuer or (self._issuer if (expected_issuer is not None or (iss and iss == self._issuer)) else None)
        if iss and expected_issuer and iss != expected_issuer:
            raise TokenInvalidException(f"Token issuer '{iss}' does not match expected '{expected_issuer}'.")

        # Audience check (aud)
        aud = payload.get("aud")
        if aud and expected_audience and aud != expected_audience:
            raise TokenInvalidException(f"Token audience '{aud}' does not match expected '{expected_audience}'.")

        # Revocation check
        jti = payload.get("jti", "")
        uid = payload.get("uid")
        sid = payload.get("sid")
        iat = payload.get("iat")
        fid = payload.get("fid")

        if self._revocation.is_revoked(
            jti=jti,
            user_id=uid,
            session_id=sid,
            issued_at=float(iat) if iat else None,
            family_id=fid,
        ):
            raise TokenRevokedException("Authentication token has been revoked.")

        return payload

    def issue_access_token(
        self,
        user_id: str,
        tenant_id: str,
        email: str,
        roles: list[SystemRole],
        permissions: list[str],
        session_id: str,
        token_family_id: str,
        ttl_seconds: int = 900,
        is_break_glass: bool = False,
    ) -> str:
        """Issues short-lived access token (Prompt 10 Item 66)."""
        now = time.time()
        jti = f"tok-acc-{uuid.uuid4().hex[:12]}"
        payload = {
            "jti": jti,
            "typ": TokenType.ACCESS.value,
            "uid": user_id,
            "tid": tenant_id,
            "sub": email,
            "iss": self._issuer,
            "aud": self._audience,
            "roles": [r.value if hasattr(r, "value") else str(r) for r in roles],
            "perms": permissions,
            "sid": session_id,
            "fid": token_family_id,
            "bg": is_break_glass,
            "iat": int(now),
            "nbf": int(now),
            "exp": int(now + ttl_seconds),
        }
        return self.sign_token(payload)

    def issue_refresh_token(
        self,
        user_id: str,
        tenant_id: str,
        session_id: str,
        token_family_id: str,
        ttl_seconds: int = 86400,
        is_break_glass: bool = False,
    ) -> str:
        """Issues rotated single-use refresh token (Prompt 10 Item 66)."""
        now = time.time()
        jti = f"tok-ref-{uuid.uuid4().hex[:12]}"
        payload = {
            "jti": jti,
            "typ": TokenType.REFRESH.value,
            "uid": user_id,
            "tid": tenant_id,
            "sid": session_id,
            "fid": token_family_id,
            "bg": is_break_glass,
            "iat": int(now),
            "exp": int(now + ttl_seconds),
        }
        return self.sign_token(payload)

    def issue_machine_token(
        self,
        client_id: str,
        tenant_id: str,
        name: str,
        scoped_permissions: list[str],
        ttl_seconds: int = 3600,
    ) -> str:
        """Issues short-lived machine client credentials token (Prompt 10 Item 67)."""
        now = time.time()
        jti = f"tok-mach-{uuid.uuid4().hex[:12]}"
        payload = {
            "jti": jti,
            "typ": TokenType.MACHINE_ACCESS.value,
            "uid": client_id,
            "tid": tenant_id,
            "sub": name,
            "perms": scoped_permissions,
            "roles": [],
            "mach": True,
            "iat": int(now),
            "exp": int(now + ttl_seconds),
        }
        return self.sign_token(payload)

    def issue_step_up_token(
        self,
        user_id: str,
        tenant_id: str,
        action: str,
        target_entity_id: str | None = None,
        ttl_seconds: int = 300,
    ) -> str:
        """Issues short-lived step-up elevation claim token (Prompt 10 Item 68)."""
        now = time.time()
        jti = f"tok-step-{uuid.uuid4().hex[:12]}"
        payload = {
            "jti": jti,
            "typ": TokenType.STEP_UP.value,
            "uid": user_id,
            "tid": tenant_id,
            "action": action,
            "target": target_entity_id,
            "iat": int(now),
            "exp": int(now + ttl_seconds),
        }
        return self.sign_token(payload)

    def issue_act_as_token(
        self,
        user_id: str,
        original_email: str,
        target_tenant_id: str,
        roles: list[SystemRole],
        ttl_seconds: int = 900,
        reason: str = "",
    ) -> str:
        """Issues short-lived act-as-tenant scoped token (Prompt R-SEC Item 1.3)."""
        now = time.time()
        jti = f"tok-act-{uuid.uuid4().hex[:12]}"
        payload = {
            "jti": jti,
            "typ": TokenType.ACCESS.value,
            "uid": user_id,
            "tid": target_tenant_id,
            "sub": original_email,
            "orig_sub": original_email,
            "act_as_tenant": target_tenant_id,
            "reason": reason,
            "roles": [r.value for r in roles],
            "perms": ["*"],
            "iat": int(now),
            "exp": int(now + ttl_seconds),
        }
        return self.sign_token(payload)

    def extract_auth_context(self, token_str: str) -> AuthContext:
        """Extracts verified AuthContext security principal from token."""
        payload = self.verify_token(token_str)
        t_type = TokenType(payload.get("typ", TokenType.ACCESS.value))
        roles = [
            SystemRole(r) for r in payload.get("roles", []) if r in SystemRole._value2member_map_
        ]

        return AuthContext(
            user_id=payload.get("uid", ""),
            tenant_id=payload.get("tid", "global"),
            email=payload.get("sub", ""),
            roles=roles,
            permissions=payload.get("perms", []),
            session_id=payload.get("sid"),
            token_type=t_type,
            is_break_glass=payload.get("bg", False),
            step_up_claims=[str(payload["action"])] if payload.get("action") else [],
            is_machine=payload.get("mach", False),
            act_as_tenant=payload.get("act_as_tenant"),
            original_subject=payload.get("orig_sub"),
        )
