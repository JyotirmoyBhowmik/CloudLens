"""Rate-Limiting, Abuse Detection & Account Lockout Tracker (Prompt R-FEAT / IMP-07 / Prompt P08).

Governs:
- 429 rate limit events recording per token / IP.
- Top API callers metrics and call volume aggregation.
- Authentication failure source tracking.
- Automated progressive lockout after N consecutive failures (M1/M2 driven).
- Distributed lockout and failure tracking backed by Redis with TTL.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from masterdata.improvement_features import get_feature_config

logger = logging.getLogger("cloudlens.domain.abuse")


class AbuseTracker:
    """Thread-safe tracker for API consumption metrics, rate limiting events, and abuse lockout."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._config = get_feature_config("IMP_07_RATE_LIMIT_ABUSE")
        self._rate_limit_hits: Counter[str] = Counter()
        self._caller_counts: Counter[str] = Counter()
        self._local_auth_failures: dict[str, list[float]] = {}
        self._local_locked_principals: dict[str, float] = {}
        self._recent_events: list[dict[str, Any]] = []
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

    def record_call(self, caller_id: str) -> None:
        """Records a successful or standard API call from caller."""
        with self._lock:
            self._caller_counts[caller_id] += 1

    def record_429(self, caller_id: str, path: str) -> None:
        """Records a 429 rate limit hit."""
        with self._lock:
            self._rate_limit_hits[caller_id] += 1
            event = {
                "type": "RATE_LIMIT_429",
                "caller_id": caller_id,
                "path": path,
                "timestamp": datetime.now(UTC).isoformat(),
            }
            self._recent_events.append(event)
            if len(self._recent_events) > 500:
                self._recent_events = self._recent_events[-500:]

    def is_locked_out(self, principal_id: str) -> tuple[bool, int]:
        """Checks if principal (user or IP) is currently in lockout. Returns (is_locked, remaining_seconds)."""
        r = self._get_redis()
        if r is not None:
            try:
                ttl = r.ttl(f"abuse:lockout:{principal_id}")
                if ttl > 0:
                    return True, ttl
                if ttl == -2:
                    return False, 0
            except Exception as e:
                logger.debug("Redis abuse is_locked_out check error: %s", e)

        now = time.time()
        with self._lock:
            unlock_time = self._local_locked_principals.get(principal_id)
            if not unlock_time:
                return False, 0
            if now >= unlock_time:
                self._local_locked_principals.pop(principal_id, None)
                self._local_auth_failures.pop(principal_id, None)
                return False, 0
            remaining = int(unlock_time - now)
            return True, remaining

    def record_auth_failure(self, principal_id: str, ip_address: str | None = None) -> tuple[bool, int]:
        """Records authentication failure and triggers lockout if max attempts exceeded.

        Returns (is_now_locked, remaining_seconds).
        """
        now = time.time()
        window_seconds = self._config.get("abuse_detection_window_seconds", 60)
        max_failures = self._config.get("lockout_max_failures", 5)
        lockout_duration = self._config.get("lockout_duration_seconds", 900)

        r = self._get_redis()
        if r is not None:
            try:
                fail_key = f"abuse:failures:{principal_id}"
                lock_key = f"abuse:lockout:{principal_id}"
                window_start = now - window_seconds

                pipe = r.pipeline()
                pipe.zremrangebyscore(fail_key, 0, window_start)
                pipe.zadd(fail_key, {f"{now}:{time.time_ns()}": now})
                pipe.expire(fail_key, window_seconds + 5)
                pipe.zcard(fail_key)
                _, _, _, count = pipe.execute()

                if count >= max_failures:
                    r.setex(lock_key, lockout_duration, "1")
                    logger.warning(
                        "Security lockout activated in Redis for principal '%s' after %d failed attempts",
                        principal_id,
                        count,
                    )
                    return True, lockout_duration
                return False, 0
            except Exception as e:
                logger.debug("Redis auth failure tracking error, falling back to local: %s", e)

        with self._lock:
            failures = self._local_auth_failures.setdefault(principal_id, [])
            failures = [ts for ts in failures if (now - ts) <= window_seconds]
            failures.append(now)
            self._local_auth_failures[principal_id] = failures

            if len(failures) >= max_failures:
                unlock_time = now + lockout_duration
                self._local_locked_principals[principal_id] = unlock_time
                event = {
                    "type": "ACCOUNT_LOCKOUT",
                    "principal_id": principal_id,
                    "ip_address": ip_address,
                    "duration_seconds": lockout_duration,
                    "timestamp": datetime.now(UTC).isoformat(),
                }
                self._recent_events.append(event)
                logger.warning(
                    "Security lockout activated for principal '%s' after %d failed attempts",
                    principal_id,
                    len(failures),
                )
                return True, lockout_duration

            return False, 0

    def record_auth_success(self, principal_id: str) -> None:
        """Clears failure count on successful sign-in."""
        r = self._get_redis()
        if r is not None:
            try:
                r.delete(f"abuse:failures:{principal_id}")
            except Exception:
                pass
        with self._lock:
            self._local_auth_failures.pop(principal_id, None)

    def unlock_principal(self, principal_id: str) -> bool:
        """Manually unlocks a locked principal (admin override)."""
        r = self._get_redis()
        redis_existed = False
        if r is not None:
            try:
                redis_existed = bool(r.delete(f"abuse:lockout:{principal_id}", f"abuse:failures:{principal_id}"))
            except Exception:
                pass
        with self._lock:
            local_existed = principal_id in self._local_locked_principals
            self._local_locked_principals.pop(principal_id, None)
            self._local_auth_failures.pop(principal_id, None)
            return redis_existed or local_existed

    def get_abuse_summary(self) -> dict[str, Any]:
        """Returns consolidated rate-limiting and abuse telemetry for Control Tower."""
        now = time.time()
        with self._lock:
            active_lockouts = []
            for princ, unlock_ts in list(self._local_locked_principals.items()):
                if unlock_ts > now:
                    active_lockouts.append({
                        "principal_id": princ,
                        "remaining_seconds": int(unlock_ts - now),
                        "unlocks_at": datetime.fromtimestamp(unlock_ts, UTC).isoformat(),
                    })
                else:
                    self._local_locked_principals.pop(princ, None)

            top_callers = [
                {"caller": k, "requests": v}
                for k, v in self._caller_counts.most_common(10)
            ]
            top_429s = [
                {"caller": k, "hits": v}
                for k, v in self._rate_limit_hits.most_common(10)
            ]

            return {
                "active_lockouts_count": len(active_lockouts),
                "active_lockouts": active_lockouts,
                "top_callers": top_callers,
                "top_429_recipients": top_429s,
                "recent_security_events": list(self._recent_events[-20:]),
            }

    def reset(self) -> None:
        """Resets tracker state for test isolation."""
        r = self._get_redis()
        if r is not None:
            try:
                keys = r.keys("abuse:*")
                if keys:
                    r.delete(*keys)
            except Exception:
                pass
        with self._lock:
            self._rate_limit_hits.clear()
            self._caller_counts.clear()
            self._local_auth_failures.clear()
            self._local_locked_principals.clear()
            self._recent_events.clear()


# Global singleton instance
abuse_tracker = AbuseTracker()


def get_abuse_tracker() -> AbuseTracker:
    """Returns singleton instance of AbuseTracker."""
    return abuse_tracker


def reset_abuse_tracker() -> AbuseTracker:
    """Resets singleton instance for tests."""
    abuse_tracker.reset()
    return abuse_tracker
