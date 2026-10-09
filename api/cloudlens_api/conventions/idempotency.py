"""Idempotency Engine for Mutating REST Endpoints (Prompt 34 / API-105 / Rule 3.4 / Prompt P08).

Enforces:
- Idempotency key detection on mutating requests (POST, PUT, PATCH, DELETE).
- Identical replay caching returning header 'Idempotent-Replay: true'.
- Conflicting payload detection returning 409 Conflict with code 'CONFLICT'.
- Distributed caching via Redis with TTL (never source of truth).
- Thread-safe storage with TTL expiration.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("cloudlens.api.idempotency")


@dataclass
class IdempotencyRecord:
    """Cached response representation for idempotent execution replay."""

    payload_hash: str
    status_code: int
    headers: dict[str, str]
    body: bytes
    created_at: float = field(default_factory=time.time)


class IdempotencyStore:
    """Thread-safe cache for idempotency key tracking with TTL backed by Redis."""

    def __init__(self, ttl_seconds: int = 86400) -> None:
        self._ttl_seconds = ttl_seconds
        self._lock = threading.Lock()
        self._records: dict[tuple[str, str], IdempotencyRecord] = {}
        self._redis: Any | None = None
        self._redis_checked: bool = False

    def _get_redis(self) -> Any | None:
        if not self._redis_checked:
            try:
                import redis

                redis_url = os.getenv("REDIS_URL") or os.getenv("CELERY_BROKER_URL") or "redis://localhost:6379/0"
                client = redis.Redis.from_url(redis_url, socket_connect_timeout=1, socket_timeout=1)
                client.ping()
                self._redis = client
            except Exception:
                self._redis = None
            self._redis_checked = True
        return self._redis

    def compute_payload_hash(self, body_bytes: bytes) -> str:
        """Computes deterministic SHA-256 hash of request payload."""
        return hashlib.sha256(body_bytes).hexdigest()

    def get(self, tenant_id: str, key: str) -> IdempotencyRecord | None:
        """Retrieves cached record if present and not expired."""
        r = self._get_redis()
        if r is not None:
            try:
                r_key = f"idempotency:{tenant_id}:{key}"
                raw = r.get(r_key)
                if raw:
                    data = json.loads(raw)
                    return IdempotencyRecord(
                        payload_hash=data["payload_hash"],
                        status_code=data["status_code"],
                        headers=data["headers"],
                        body=base64.b64decode(data["body_b64"]),
                        created_at=data["created_at"],
                    )
            except Exception as e:
                logger.debug("Redis idempotency get error, checking local: %s", e)

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
        now = time.time()
        record = IdempotencyRecord(
            payload_hash=payload_hash,
            status_code=status_code,
            headers=dict(headers),
            body=body,
            created_at=now,
        )

        r = self._get_redis()
        if r is not None:
            try:
                r_key = f"idempotency:{tenant_id}:{key}"
                data = {
                    "payload_hash": payload_hash,
                    "status_code": status_code,
                    "headers": dict(headers),
                    "body_b64": base64.b64encode(body).decode("ascii"),
                    "created_at": now,
                }
                r.setex(r_key, self._ttl_seconds, json.dumps(data))
            except Exception as e:
                logger.debug("Redis idempotency store error: %s", e)

        with self._lock:
            self._records[(tenant_id, key)] = record

    def clear(self) -> None:
        """Clears all cached records (for testing)."""
        r = self._get_redis()
        if r is not None:
            try:
                keys = r.keys("idempotency:*")
                if keys:
                    r.delete(*keys)
            except Exception:
                pass
        with self._lock:
            self._records.clear()


# Global singleton store instance
idempotency_store = IdempotencyStore()
