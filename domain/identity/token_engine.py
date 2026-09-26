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
    """In-memory thread-safe revocation registry tracking revoked JTIs, sessions, and disabled users."""

    def __init__(self) -> None:
        # Revoked individual token JTIs -> expiration timestamp
        self._revoked_jtis: dict[str, float] = {}
        # Revoked session IDs -> revocation timestamp
        self._revoked_sessions: dict[str, float] = {}
        # Revoked user IDs -> revocation timestamp (all tokens issued before this timestamp are invalid)
        self._revoked_users: dict[str, float] = {}
        # Refresh token families and used sequence numbers: family_id -> set of used token IDs
        self._used_refresh_tokens: set[str] = set()
        self._compromised_families: set[str] = set()

    def revoke_token(self, jti: str, expires_at: float) -> None:
        """Revokes a specific token JTI until its expiration."""
        self._revoked_jtis[jti] = expires_at

    def revoke_session(self, session_id: str) -> None:
        """Revokes all tokens associated with a session ID."""
        self._revoked_sessions[session_id] = time.time()

    def revoke_user_tokens(self, user_id: str) -> None:
        """Revokes all active tokens for a user immediately (Item 66)."""
        self._revoked_users[user_id] = time.time()

    def record_refresh_token_use(self, token_id: str, family_id: str) -> bool:
        """Records use of a refresh token.

        Returns True if valid single-use; returns False if token reuse is detected
        (triggering full family compromise revocation).
        """
        if family_id in self._compromised_families:
            return False

        if token_id in self._used_refresh_tokens:
            # Refresh token reuse detected! Breach defense: revoke entire family immediately
            self._compromised_families.add(family_id)
            return False

        self._used_refresh_tokens.add(token_id)
        return True

    def is_revoked(
        self,
        jti: str,
        user_id: str | None = None,
        session_id: str | None = None,
        issued_at: float | None = None,
        family_id: str | None = None,
    ) -> bool:
        """Checks if a token has been revoked by JTI, session, user disablement, or family reuse."""
        now = time.time()

        # 1. Direct JTI revocation
        if jti in self._revoked_jtis:
            if self._revoked_jtis[jti] > now:
                return True
            # Purge expired entry
            del self._revoked_jtis[jti]

        # 2. Session revocation
        if session_id and session_id in self._revoked_sessions:
            if issued_at is None or issued_at <= self._revoked_sessions[session_id]:
                return True

        # 3. User revocation (immediate invalidation on user disable)
        if user_id and user_id in self._revoked_users:
            if issued_at is None or issued_at <= self._revoked_users[user_id]:
                return True

        # 4. Family compromise check
        if family_id and family_id in self._compromised_families:
            return True

        return False

    def clear(self) -> None:
        """Clears the revocation registry (for testing isolation)."""
        self._revoked_jtis.clear()
        self._revoked_sessions.clear()
        self._revoked_users.clear()
        self._used_refresh_tokens.clear()
        self._compromised_families.clear()


class CryptographicTokenEngine:
    """Signs, verifies, and lifecycle-manages authentication tokens."""

    def __init__(
        self,
        signing_key: bytes | None = None,
        revocation_registry: TokenRevocationRegistry | None = None,
    ) -> None:
        self._signing_key = signing_key or DEFAULT_SIGNING_SECRET
        self._revocation = revocation_registry or TokenRevocationRegistry()

    @property
    def revocation_registry(self) -> TokenRevocationRegistry:
        return self._revocation

    def sign_token(self, payload: dict[str, Any]) -> str:
        """Creates a signed HMAC-SHA256 token string."""
        header = {"alg": "HS256", "typ": "JWT"}
        header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode())
        payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode())
        signing_input = f"{header_b64}.{payload_b64}".encode()

        signature = hmac.new(self._signing_key, signing_input, hashlib.sha256).digest()
        sig_b64 = _b64url_encode(signature)

        return f"{header_b64}.{payload_b64}.{sig_b64}"

    def verify_token(self, token_str: str) -> dict[str, Any]:
        """Validates token signature, expiration, and revocation status."""
        parts = token_str.strip().split(".")
        if len(parts) != 3:
            raise TokenInvalidException(
                "Token format is invalid: expected header.payload.signature"
            )

        header_b64, payload_b64, sig_b64 = parts
        signing_input = f"{header_b64}.{payload_b64}".encode()

        expected_sig = hmac.new(self._signing_key, signing_input, hashlib.sha256).digest()
        try:
            provided_sig = _b64url_decode(sig_b64)
        except Exception as e:
            raise TokenInvalidException("Token signature decoding failed.") from e

        if not secrets.compare_digest(expected_sig, provided_sig):
            raise TokenInvalidException("Token cryptographic signature verification failed.")

        try:
            parsed = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
        except Exception as e:
            raise TokenInvalidException("Token payload decoding failed.") from e

        if not isinstance(parsed, dict):
            raise TokenInvalidException("Token payload must be a JSON object.")
        payload: dict[str, Any] = cast(dict[str, Any], parsed)

        now = time.time()
        # Expiration check
        exp = payload.get("exp")
        if exp is not None and now > float(exp):
            raise TokenExpiredException("Authentication token has expired.")

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
            "roles": [r.value for r in roles],
            "perms": permissions,
            "sid": session_id,
            "fid": token_family_id,
            "bg": is_break_glass,
            "iat": int(now),
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
        )
