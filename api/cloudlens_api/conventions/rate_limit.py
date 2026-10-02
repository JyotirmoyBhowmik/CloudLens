"""Per-Token and Per-Client Rate Limiting with Standard Headers (Prompt 34 / API-106).

Enforces:
- Rate limiting per caller identity token / client IP address.
- Injects standard RFC rate limit headers:
  - RateLimit-Limit
  - RateLimit-Remaining
  - RateLimit-Reset
- Returns 429 Too Many Requests with code 'RATE_LIMITED' when quota exceeded.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field


@dataclass
class RateLimitBucket:
    """Sliding-window or leaky-bucket rate limiter tracker."""

    requests: list[float] = field(default_factory=list)


class TokenRateLimiter:
    """Thread-safe rate limiter tracking per-key request counts in a sliding window."""

    def __init__(self, limit: int = 1000, window_seconds: int = 60) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._lock = threading.Lock()
        self._buckets: dict[str, RateLimitBucket] = {}

    def check_and_record(self, key: str) -> tuple[bool, int, int, int]:
        """Checks if request is allowed, records timestamp, and returns:

        (allowed, limit, remaining, reset_seconds)
        """
        now = time.time()
        window_start = now - self.window_seconds

        with self._lock:
            bucket = self._buckets.setdefault(key, RateLimitBucket())
            # Evict timestamps older than window
            bucket.requests = [ts for ts in bucket.requests if ts > window_start]

            count = len(bucket.requests)
            if count >= self.limit:
                # Quota exceeded
                oldest = bucket.requests[0] if bucket.requests else now
                reset_seconds = max(1, int(oldest + self.window_seconds - now))
                return False, self.limit, 0, reset_seconds

            bucket.requests.append(now)
            remaining = max(0, self.limit - (count + 1))
            oldest = bucket.requests[0]
            reset_seconds = max(1, int(oldest + self.window_seconds - now))
            return True, self.limit, remaining, reset_seconds

    def reset(self) -> None:
        """Clears all buckets (for testing)."""
        with self._lock:
            self._buckets.clear()


# Global singleton rate limiter instance
token_rate_limiter = TokenRateLimiter(limit=1000, window_seconds=60)
