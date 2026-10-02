"""Idempotency Engine for Mutating REST Endpoints (Prompt 34 / API-105 / Rule 3.4).

Enforces:
- Idempotency key detection on mutating requests (POST, PUT, PATCH, DELETE).
- Identical replay caching returning header 'Idempotent-Replay: true'.
- Conflicting payload detection returning 409 Conflict with code 'CONFLICT'.
- Thread-safe storage with TTL expiration.
"""

from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import dataclass, field


@dataclass
class IdempotencyRecord:
    """Cached response representation for idempotent execution replay."""

    payload_hash: str
    status_code: int
    headers: dict[str, str]
    body: bytes
    created_at: float = field(default_factory=time.time)


class IdempotencyStore:
    """Thread-safe in-memory cache for idempotency key tracking with TTL."""

    def __init__(self, ttl_seconds: int = 86400) -> None:
        self._ttl_seconds = ttl_seconds
        self._lock = threading.Lock()
        self._records: dict[
            tuple[str, str], IdempotencyRecord
        ] = {}  # (tenant_id, idempotency_key) -> Record

    def compute_payload_hash(self, body_bytes: bytes) -> str:
        """Computes deterministic SHA-256 hash of request payload."""
        return hashlib.sha256(body_bytes).hexdigest()

    def get(self, tenant_id: str, key: str) -> IdempotencyRecord | None:
        """Retrieves cached record if present and not expired."""
        with self._lock:
            record = self._records.get((tenant_id, key))
            if not record:
                return None
            if time.time() - record.created_at > self._ttl_seconds:
                del self._records[(tenant_id, key)]
                return None
            return record

    def store(
        self,
        tenant_id: str,
        key: str,
        payload_hash: str,
        status_code: int,
        headers: dict[str, str],
        body: bytes,
    ) -> None:
        """Stores execution response under given idempotency key."""
        with self._lock:
            self._records[(tenant_id, key)] = IdempotencyRecord(
                payload_hash=payload_hash,
                status_code=status_code,
                headers=dict(headers),
                body=body,
                created_at=time.time(),
            )

    def clear(self) -> None:
        """Clears all cached records (for testing)."""
        with self._lock:
            self._records.clear()


# Global singleton store instance
idempotency_store = IdempotencyStore()
