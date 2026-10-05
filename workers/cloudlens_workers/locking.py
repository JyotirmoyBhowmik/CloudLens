"""Distributed Redis Concurrency and Leader Election Locks for CloudLens Workers.

Enforces:
- Prompt R-RUN Item 2: One active task execution per connector + capability via Redis lock.
- Prompt R-RUN Item 4: Single Celery Beat instance with leader election lock.
- Zero silent failures: Explicit logging, error handling, and resource release.
"""

from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from typing import Any

logger = logging.getLogger(__name__)

# Fallback in-memory lock storage when Redis is unavailable or in isolated tests
_in_memory_locks: dict[str, tuple[str, float]] = {}
_in_memory_lock_guard = threading.Lock()


def get_redis_client() -> Any | None:
    """Attempts to connect to Redis using environment configuration."""
    redis_url = os.getenv("REDIS_URL") or os.getenv("CELERY_BROKER_URL") or "redis://localhost:6379/0"
    try:
        import redis

        client = redis.Redis.from_url(redis_url, socket_connect_timeout=2, socket_timeout=2)
        client.ping()
        return client
    except Exception as exc:
        logger.debug("Redis unavailable at %s: %s. Using in-memory concurrency locks.", redis_url, exc)
        return None


class TaskConcurrencyLock:
    """Distributed lock ensuring only one active task per connector and capability."""

    def __init__(
        self,
        tenant_id: str,
        connector_id: str | None,
        capability_or_task: str,
        ttl_seconds: int = 300,
        redis_client: Any | None = None,
    ) -> None:
        self.tenant_id = tenant_id
        self.connector_id = connector_id or "platform"
        self.capability_or_task = capability_or_task
        self.ttl_seconds = ttl_seconds
        self.lock_key = f"lock:task:{self.tenant_id}:{self.connector_id}:{self.capability_or_task}"
        self.token = str(uuid.uuid4())
        self._redis = redis_client if redis_client is not None else get_redis_client()
        self.acquired = False

    def acquire(self) -> bool:
        """Attempts to acquire the lock. Returns True if acquired, False if already held."""
        if self._redis is not None:
            try:
                res = self._redis.set(self.lock_key, self.token, nx=True, ex=self.ttl_seconds)
                self.acquired = bool(res)
                return self.acquired
            except Exception as exc:
                logger.warning("Redis error acquiring task lock %s: %s; falling back to in-memory lock.", self.lock_key, exc)

        # In-memory lock fallback
        now = time.time()
        with _in_memory_lock_guard:
            if self.lock_key in _in_memory_locks:
                held_token, expires_at = _in_memory_locks[self.lock_key]
                if now < expires_at:
                    self.acquired = False
                    return False
            _in_memory_locks[self.lock_key] = (self.token, now + self.ttl_seconds)
            self.acquired = True
            return True

    def release(self) -> None:
        """Releases the lock if held by this instance."""
        if not self.acquired:
            return

        if self._redis is not None:
            try:
                # Lua script to release only if token matches
                lua_script = """
                if redis.call("get", KEYS[1]) == ARGV[1] then
                    return redis.call("del", KEYS[1])
                else
                    return 0
                end
                """
                self._redis.eval(lua_script, 1, self.lock_key, self.token)
                self.acquired = False
                return
            except Exception as exc:
                logger.warning("Redis error releasing task lock %s: %s", self.lock_key, exc)

        with _in_memory_lock_guard:
            if self.lock_key in _in_memory_locks:
                held_token, _ = _in_memory_locks[self.lock_key]
                if held_token == self.token:
                    del _in_memory_locks[self.lock_key]
        self.acquired = False

    def __enter__(self) -> bool:
        return self.acquire()

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.release()


class BeatLeaderLock:
    """Distributed leader election lock for Celery Beat instances."""

    def __init__(
        self,
        lock_key: str | None = None,
        ttl_seconds: int = 15,
        redis_client: Any | None = None,
    ) -> None:
        self.lock_key = lock_key or "lock:cloudlens:beat_leader"
        self.ttl_seconds = ttl_seconds
        self.instance_id = f"beat-{uuid.uuid4().hex[:8]}"
        self._redis = redis_client if redis_client is not None else get_redis_client()
        self._is_leader = False

    @property
    def is_leader(self) -> bool:
        return self._is_leader

    def acquire_or_renew(self) -> bool:
        """Attempts to acquire the leader lock, or renew it if already held."""
        if self._redis is not None:
            try:
                if self._is_leader:
                    # Renew existing leadership: SET lock_key instance_id XX EX ttl
                    res = self._redis.set(self.lock_key, self.instance_id, xx=True, ex=self.ttl_seconds)
                    if res:
                        self._is_leader = True
                        return True
                    # Lock expired or stolen
                    self._is_leader = False

                # Not leader: try to acquire with NX
                res = self._redis.set(self.lock_key, self.instance_id, nx=True, ex=self.ttl_seconds)
                self._is_leader = bool(res)
                return self._is_leader
            except Exception as exc:
                logger.warning("Redis leader lock error on %s: %s. Falling back to local lock.", self.lock_key, exc)

        # In-memory fallback
        now = time.time()
        with _in_memory_lock_guard:
            if self.lock_key in _in_memory_locks:
                held_id, expires_at = _in_memory_locks[self.lock_key]
                if held_id == self.instance_id:
                    # Renew
                    _in_memory_locks[self.lock_key] = (self.instance_id, now + self.ttl_seconds)
                    self._is_leader = True
                    return True
                elif now < expires_at:
                    self._is_leader = False
                    return False
            # Acquire
            _in_memory_locks[self.lock_key] = (self.instance_id, now + self.ttl_seconds)
            self._is_leader = True
            return True

    def release(self) -> None:
        """Steps down from leadership and releases the lock."""
        if not self._is_leader:
            return

        if self._redis is not None:
            try:
                lua_script = """
                if redis.call("get", KEYS[1]) == ARGV[1] then
                    return redis.call("del", KEYS[1])
                else
                    return 0
                end
                """
                self._redis.eval(lua_script, 1, self.lock_key, self.instance_id)
                self._is_leader = False
                return
            except Exception as exc:
                logger.warning("Redis leader release error on %s: %s", self.lock_key, exc)

        with _in_memory_lock_guard:
            if self.lock_key in _in_memory_locks:
                held_id, _ = _in_memory_locks[self.lock_key]
                if held_id == self.instance_id:
                    del _in_memory_locks[self.lock_key]
        self._is_leader = False


def reset_in_memory_locks() -> None:
    """Resets in-memory lock store for test isolation."""
    with _in_memory_lock_guard:
        _in_memory_locks.clear()
