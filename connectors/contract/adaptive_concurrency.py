"""CloudLens Adaptive Concurrency Controller (Prompt 14 Item 92).

Enforces:
- Additive Increase / Multiplicative Decrease (AIMD) concurrency adaptation.
- Halving concurrency ceiling under provider 429 / throttling events.
- Gradual recovery (concurrency restoration) after continuous healthy operation.
- Guarded semaphore granting execution slots without dropping records.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Any

from domain.config.tenant_settings import ConnectorSettings

logger = logging.getLogger(__name__)
_settings = ConnectorSettings()


class AdaptiveConcurrencyController:
    """Dynamic concurrency governor employing AIMD to mitigate provider throttling."""

    def __init__(
        self,
        connector_id: str,
        min_concurrency: int = _settings.adaptive_concurrency_min,
        max_concurrency: int = _settings.adaptive_concurrency_max,
        initial_concurrency: int = _settings.adaptive_concurrency_initial,
        # no-hardcode-allow: reason="Consecutive success threshold required to increment concurrency", reviewer="enterprise-arch"
        recovery_success_threshold: int = 5,
    ) -> None:
        self.connector_id = connector_id
        self.min_concurrency = min_concurrency
        self.max_concurrency = max_concurrency
        self.current_concurrency = initial_concurrency
        self.recovery_success_threshold = recovery_success_threshold

        self._active_requests = 0
        self._consecutive_successes = 0
        self._lock = threading.Lock()
        self._condition = threading.Condition(self._lock)
        self._async_semaphore = asyncio.Semaphore(initial_concurrency)

    @property
    def concurrency_limit(self) -> int:
        """Current maximum active concurrent requests allowed."""
        with self._lock:
            return self.current_concurrency

    @property
    def active_count(self) -> int:
        """Number of active requests currently inflight."""
        with self._lock:
            return self._active_requests

    def record_throttle(self, error_detail: str | None = None) -> int:
        """Triggered upon HTTP 429 or provider rate-limit error.

        Performs Multiplicative Decrease: halves current concurrency ceiling.
        """
        with self._condition:
            old_limit = self.current_concurrency
            # no-hardcode-allow: reason="Multiplicative decrease factor 0.5 (halving) for AIMD congestion control", reviewer="enterprise-arch"
            new_limit = max(self.min_concurrency, int(self.current_concurrency * 0.5))
            self.current_concurrency = new_limit
            self._consecutive_successes = 0

            logger.warning(
                "Throttling detected on connector %s. Concurrency halved: %d -> %d. Detail: %s",
                self.connector_id,
                old_limit,
                new_limit,
                error_detail or "HTTP 429 Too Many Requests",
            )
            self._condition.notify_all()
            return new_limit

    def record_success(self) -> int:
        """Triggered upon successful request completion.

        Performs Additive Increase: increments ceiling after N consecutive successes.
        """
        with self._condition:
            self._consecutive_successes += 1
            if self._consecutive_successes >= self.recovery_success_threshold:
                if self.current_concurrency < self.max_concurrency:
                    # no-hardcode-allow: reason="Additive increase step of 1 for AIMD congestion control", reviewer="enterprise-arch"
                    self.current_concurrency += 1
                    logger.info(
                        "Connector %s healthy streak reached (%d). Concurrency restored to %d",
                        self.connector_id,
                        self._consecutive_successes,
                        self.current_concurrency,
                    )
                self._consecutive_successes = 0

            self._condition.notify_all()
            return self.current_concurrency

    def acquire_slot_sync(self, timeout: float = 30.0) -> bool:
        """Synchronously blocks until an active concurrency slot is available."""
        with self._condition:
            end_time = time.monotonic() + timeout
            while self._active_requests >= self.current_concurrency:
                remaining = end_time - time.monotonic()
                if remaining <= 0:
                    return False
                # no-hardcode-allow: reason="Slice wait duration for condition predicate polling", reviewer="enterprise-arch"
                wait_slice = min(remaining, 0.5)
                self._condition.wait(timeout=wait_slice)
            self._active_requests += 1
            return True

    def release_slot_sync(self) -> None:
        """Releases an acquired concurrency slot."""
        with self._condition:
            if self._active_requests > 0:
                self._active_requests -= 1
            self._condition.notify_all()

    async def acquire_slot_async(self, timeout: float = 30.0) -> bool:
        """Asynchronously waits until a concurrency slot becomes available."""
        # no-hardcode-allow: reason="Async polling sleep interval while waiting for slot", reviewer="enterprise-arch"
        step = 0.05
        waited = 0.0
        while waited < timeout:
            with self._lock:
                if self._active_requests < self.current_concurrency:
                    self._active_requests += 1
                    return True
            await asyncio.sleep(step)
            waited += step
        return False

    def release_slot_async(self) -> None:
        """Releases an asynchronously acquired concurrency slot."""
        self.release_slot_sync()


class ConcurrencyLease:
    """Context manager for acquiring and releasing concurrency slots."""

    def __init__(self, controller: AdaptiveConcurrencyController, is_async: bool = True) -> None:
        self.controller = controller
        self.is_async = is_async
        self._acquired = False

    async def __aenter__(self) -> ConcurrencyLease:
        self._acquired = await self.controller.acquire_slot_async()
        if not self._acquired:
            raise TimeoutError(
                f"Failed to acquire concurrency slot for connector {self.controller.connector_id}"
            )
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self._acquired:
            self.controller.release_slot_async()

    def __enter__(self) -> ConcurrencyLease:
        self._acquired = self.controller.acquire_slot_sync()
        if not self._acquired:
            raise TimeoutError(
                f"Failed to acquire concurrency slot for connector {self.controller.connector_id}"
            )
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self._acquired:
            self.controller.release_slot_sync()
