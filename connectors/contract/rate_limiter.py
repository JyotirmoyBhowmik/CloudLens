"""CloudLens Shared Rate Limiter & Backoff Engine (Prompt 14 Item 92).

Enforces:
- Shared token bucket rate limiter per connector.
- Provider retry hint extraction (Retry-After header / HTTP date).
- Exponential backoff with full jitter (Rule 3.2).
"""

from __future__ import annotations

import asyncio
import logging
import random
import re
import threading
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

from domain.config.tenant_settings import ConnectorSettings
from domain.models.exceptions import RateLimitExceededException

logger = logging.getLogger(__name__)
_settings = ConnectorSettings()


class SharedTokenBucket:
    """Thread-safe and asyncio-compatible token bucket shared across workers for a connector."""

    def __init__(
        self,
        connector_id: str,
        rate_per_second: float = _settings.default_rate_limit_per_second,
        burst_capacity: float = _settings.default_burst_capacity,
    ) -> None:
        self.connector_id = connector_id
        self.rate_per_second = rate_per_second
        self.burst_capacity = burst_capacity
        self.tokens = burst_capacity
        self.last_refill = time.monotonic()
        self._lock = threading.Lock()
        self._async_lock = asyncio.Lock()

    def _refill(self) -> None:
        """Internal token replenishment based on elapsed time."""
        now = time.monotonic()
        elapsed = now - self.last_refill
        if elapsed > 0:
            new_tokens = elapsed * self.rate_per_second
            self.tokens = min(self.burst_capacity, self.tokens + new_tokens)
            self.last_refill = now

    def try_acquire(self, tokens: float = 1.0) -> bool:
        """Non-blocking token acquisition."""
        with self._lock:
            self._refill()
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False

    async def acquire_async(
        self,
        tokens: float = 1.0,
        timeout: float = 30.0,
    ) -> bool:
        """Asynchronously acquires tokens, waiting if necessary up to timeout."""
        start_time = time.monotonic()
        while True:
            with self._lock:
                self._refill()
                if self.tokens >= tokens:
                    self.tokens -= tokens
                    return True
                deficit = tokens - self.tokens
                wait_time = deficit / self.rate_per_second if self.rate_per_second > 0 else 1.0

            elapsed = time.monotonic() - start_time
            if elapsed + wait_time > timeout:
                logger.warning(
                    "Token bucket acquisition timed out for connector %s after %.2fs",
                    self.connector_id,
                    elapsed,
                )
                raise RateLimitExceededException(
                    connector_id=self.connector_id,
                    retry_after=wait_time,
                )

            # Cap individual sleep slices to avoid oversleeping
            # no-hardcode-allow: reason="Slice sleep granularity to bound waiting loop", reviewer="enterprise-arch"
            sleep_duration = min(wait_time, 0.5)
            await asyncio.sleep(sleep_duration)

    def acquire_sync(
        self,
        tokens: float = 1.0,
        timeout: float = 30.0,
    ) -> bool:
        """Synchronously acquires tokens, blocking current thread up to timeout."""
        start_time = time.monotonic()
        while True:
            with self._lock:
                self._refill()
                if self.tokens >= tokens:
                    self.tokens -= tokens
                    return True
                deficit = tokens - self.tokens
                wait_time = deficit / self.rate_per_second if self.rate_per_second > 0 else 1.0

            elapsed = time.monotonic() - start_time
            if elapsed + wait_time > timeout:
                raise RateLimitExceededException(
                    connector_id=self.connector_id,
                    retry_after=wait_time,
                )

            # no-hardcode-allow: reason="Slice sleep granularity to bound waiting loop", reviewer="enterprise-arch"
            sleep_duration = min(wait_time, 0.5)
            time.sleep(sleep_duration)


def parse_retry_after(headers_or_payload: Any) -> float | None:
    """Extracts retry hints (Retry-After header, integer seconds, or RFC 2822 date).

    Honours provider retry directives verbatim.
    """
    if not headers_or_payload:
        return None

    raw_val: Any = None
    if isinstance(headers_or_payload, dict):
        for k, v in headers_or_payload.items():
            if str(k).lower() in ("retry-after", "retry_after", "retryafter"):
                raw_val = v
                break
    elif hasattr(headers_or_payload, "headers") and isinstance(headers_or_payload.headers, dict):
        return parse_retry_after(headers_or_payload.headers)
    elif isinstance(headers_or_payload, (int, float)):
        return float(headers_or_payload)
    elif isinstance(headers_or_payload, str):
        raw_val = headers_or_payload

    if raw_val is None:
        return None

    # 1. Direct integer/float seconds
    try:
        val_float = float(raw_val)
        return max(0.0, val_float)
    except (ValueError, TypeError):
        pass

    # 2. HTTP-date parsing (RFC 2822 / 1123)
    try:
        target_dt = parsedate_to_datetime(str(raw_val))
        now_dt = datetime.now(UTC)
        diff_seconds = (target_dt - now_dt).total_seconds()
        return max(0.0, diff_seconds)
    except Exception:
        pass

    # 3. String pattern match: "retry in X seconds"
    match = re.search(r"(\d+(?:\.\d+)?)\s*s(?:ec|econds)?", str(raw_val), re.IGNORECASE)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            pass

    return None


def calculate_backoff(
    attempt: int,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    retry_after: float | None = None,
) -> float:
    """Calculates exponential backoff with full jitter (Rule 3.2).

    If provider gave a Retry-After hint, honors it with a small positive jitter.
    """
    if retry_after is not None and retry_after > 0:
        # no-hardcode-allow: reason="Positive jitter bounds on explicit provider retry header", reviewer="enterprise-arch"
        jitter = random.uniform(0.1, 0.5)
        return retry_after + jitter

    # Full jitter algorithm: sleep = uniform(0, min(max_delay, base_delay * 2^attempt))
    # no-hardcode-allow: reason="Exponential multiplier factor for backoff", reviewer="enterprise-arch"
    factor = 2**attempt
    ceiling = min(max_delay, base_delay * factor)
    # no-hardcode-allow: reason="Randomized lower bound for backoff jitter", reviewer="enterprise-arch"
    return max(0.1, random.uniform(0.1, ceiling))
