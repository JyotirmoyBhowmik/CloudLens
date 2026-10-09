"""Per-Token and Per-Client Rate Limiting with Standard Headers (Prompt 34 / API-105 / Prompt P08).

Enforces:
- Distributed rate limiting via Redis sorted sets with TTL.
- Fallback local sliding-window bucket if Redis is temporarily unreachable.
- CACHE item backed by Redis with TTL, never source of truth.
- Injects standard RFC rate limit headers:
  - RateLimit-Limit
  - RateLimit-Remaining
  - RateLimit-Reset
- Returns 429 Too Many Requests with code 'RATE_LIMITED' when quota exceeded.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("cloudlens.api.rate_limit")


@dataclass
class RateLimitBucket:
    """Sliding-window or leaky-bucket rate limiter tracker."""

    requests: list[float] = field(default_factory=list)


class TokenRateLimiter:
    """Thread-safe rate limiter tracking per-key request counts in a sliding window using Redis with TTL."""

    def __init__(self, limit: int = 1000, window_seconds: int = 60) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._lock = threading.Lock()
        self._buckets: dict[str, RateLimitBucket] = {}
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

    def check_and_record(self, key: str) -> tuple[bool, int, int, int]:
        """Checks if request is allowed, records timestamp, and returns:

        (allowed, limit, remaining, reset_seconds)
        """
        now = time.time()
        window_start = now - self.window_seconds

        r = self._get_redis()
        if r is not None:
            try:
                r_key = f"ratelimit:{key}"
                pipe = r.pipeline()
                pipe.zremrangebyscore(r_key, 0, window_start)
                pipe.zcard(r_key)
                pipe.zrange(r_key, 0, 0, withscores=True)
                _, count, oldest = pipe.execute()

                if count >= self.limit:
                    oldest_ts = oldest[0][1] if oldest else now
                    reset_seconds = max(1, int(oldest_ts + self.window_seconds - now))
                    return False, self.limit, 0, reset_seconds

                pipe = r.pipeline()
                pipe.zadd(r_key, {f"{now}:{time.time_ns()}": now})
                pipe.expire(r_key, self.window_seconds + 5)
                pipe.execute()

                remaining = max(0, self.limit - (count + 1))
                oldest_ts = oldest[0][1] if oldest else now
                reset_seconds = max(1, int(oldest_ts + self.window_seconds - now))
                return True, self.limit, remaining, reset_seconds
            except Exception as e:
                logger.debug("Redis rate limiting error, falling back to local: %s", e)

        with self._lock:
            bucket = self._buckets.setdefault(key, RateLimitBucket())
            bucket.requests = [ts for ts in bucket.requests if ts > window_start]
            count = len(bucket.requests)

            if count >= self.limit:
                oldest_ts = bucket.requests[0] if bucket.requests else now
                reset_seconds = max(1, int(oldest_ts + self.window_seconds - now))
                return False, self.limit, 0, reset_seconds

            bucket.requests.append(now)
            remaining = max(0, self.limit - (count + 1))
            oldest_ts = bucket.requests[0]
            reset_seconds = max(1, int(oldest_ts + self.window_seconds - now))
            return True, self.limit, remaining, reset_seconds

    def reset(self) -> None:
        """Clears all buckets (for testing)."""
        r = self._get_redis()
        if r is not None:
            try:
                keys = r.keys("ratelimit:*")
                if keys:
                    r.delete(*keys)
            except Exception:
                pass
        with self._lock:
            self._buckets.clear()


# Global singleton rate limiter instance
token_rate_limiter = TokenRateLimiter(limit=1000, window_seconds=60)
