"""CloudLens Per-Capability Circuit Breaker (Prompt 14 Item 92 / Rule 3.3).

Enforces:
- Independent circuit breaker per (connector_id, capability).
- Fast failure when in OPEN state to prevent cascading provider outages.
- Automatic recovery probing via HALF_OPEN state after cooldown timeout.
- Complete failure isolation: a failure in cost ingestion never blocks inventory.
"""

from __future__ import annotations

import logging
import threading
import time

from domain.config.tenant_settings import ConnectorSettings
from domain.models.enums import CircuitBreakerState, ConnectorCapability
from domain.models.exceptions import CircuitBreakerOpenException

logger = logging.getLogger(__name__)
_settings = ConnectorSettings()


class CapabilityCircuitBreaker:
    """Circuit breaker dedicated to a single capability on a single connector."""

    def __init__(
        self,
        connector_id: str,
        capability: ConnectorCapability,
        failure_threshold: int = _settings.circuit_breaker_failure_threshold,
        recovery_timeout_seconds: float = _settings.circuit_breaker_recovery_timeout_seconds,
        success_threshold: int = _settings.circuit_breaker_success_threshold,
    ) -> None:
        self.connector_id = connector_id
        self.capability = capability
        self.failure_threshold = failure_threshold
        self.recovery_timeout_seconds = recovery_timeout_seconds
        self.success_threshold = success_threshold

        self._state = CircuitBreakerState.CLOSED
        self._consecutive_failures = 0
        self._consecutive_successes = 0
        self._last_state_change = time.monotonic()
        self._last_failure_time: float | None = None
        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitBreakerState:
        """Returns the current effective circuit state (accounting for recovery timeout)."""
        with self._lock:
            if self._state == CircuitBreakerState.OPEN:
                elapsed = time.monotonic() - self._last_state_change
                if elapsed >= self.recovery_timeout_seconds:
                    self._state = CircuitBreakerState.HALF_OPEN
                    self._last_state_change = time.monotonic()
                    self._consecutive_successes = 0
                    logger.info(
                        "Circuit breaker for %s:%s transitioned from OPEN to HALF_OPEN (probe allowed)",
                        self.connector_id,
                        self.capability.value,
                    )
            return self._state

    def check_permission(self) -> None:
        """Checks if a request is allowed to proceed.

        Raises CircuitBreakerOpenException if the circuit is OPEN.
        """
        current_state = self.state
        if current_state == CircuitBreakerState.OPEN:
            with self._lock:
                elapsed = time.monotonic() - self._last_state_change
                remaining = max(0.0, self.recovery_timeout_seconds - elapsed)
            raise CircuitBreakerOpenException(
                connector_id=self.connector_id,
                capability=self.capability.value,
                recovery_time_seconds=remaining,
            )

    def record_success(self) -> None:
        """Records a successful operation."""
        with self._lock:
            if self._state == CircuitBreakerState.HALF_OPEN:
                self._consecutive_successes += 1
                if self._consecutive_successes >= self.success_threshold:
                    self._state = CircuitBreakerState.CLOSED
                    self._consecutive_failures = 0
                    self._consecutive_successes = 0
                    self._last_state_change = time.monotonic()
                    logger.info(
                        "Circuit breaker for %s:%s reset to CLOSED after %d successful probes",
                        self.connector_id,
                        self.capability.value,
                        self.success_threshold,
                    )
            elif self._state == CircuitBreakerState.CLOSED:
                self._consecutive_failures = 0

    def record_failure(self, error: Exception | str | None = None) -> None:
        """Records an execution failure."""
        with self._lock:
            now = time.monotonic()
            self._last_failure_time = now
            self._consecutive_failures += 1

            if self._state == CircuitBreakerState.HALF_OPEN:
                # Probing in HALF_OPEN failed -> trip back to OPEN
                self._state = CircuitBreakerState.OPEN
                self._last_state_change = now
                self._consecutive_successes = 0
                logger.warning(
                    "Circuit breaker for %s:%s probe FAILED. Tripping back to OPEN. Error: %s",
                    self.connector_id,
                    self.capability.value,
                    error,
                )
            elif self._state == CircuitBreakerState.CLOSED:
                if self._consecutive_failures >= self.failure_threshold:
                    self._state = CircuitBreakerState.OPEN
                    self._last_state_change = now
                    logger.error(
                        "Circuit breaker for %s:%s TRIPPED to OPEN after %d consecutive failures. Cooldown: %.1fs. Error: %s",
                        self.connector_id,
                        self.capability.value,
                        self._consecutive_failures,
                        self.recovery_timeout_seconds,
                        error,
                    )

    def reset(self) -> None:
        """Administratively resets circuit breaker to CLOSED."""
        with self._lock:
            self._state = CircuitBreakerState.CLOSED
            self._consecutive_failures = 0
            self._consecutive_successes = 0
            self._last_state_change = time.monotonic()


class CircuitBreakerRegistry:
    """Thread-safe registry managing per-capability circuit breakers across all connectors."""

    def __init__(self) -> None:
        self._breakers: dict[tuple[str, str], CapabilityCircuitBreaker] = {}
        self._lock = threading.Lock()

    def get_breaker(
        self,
        connector_id: str,
        capability: ConnectorCapability,
    ) -> CapabilityCircuitBreaker:
        """Retrieves or lazily instantiates the breaker for (connector_id, capability)."""
        key = (connector_id, capability.value)
        with self._lock:
            if key not in self._breakers:
                self._breakers[key] = CapabilityCircuitBreaker(
                    connector_id=connector_id,
                    capability=capability,
                )
            return self._breakers[key]

    def reset_all(self, connector_id: str | None = None) -> None:
        """Resets breakers for testing or manual recovery."""
        with self._lock:
            if connector_id:
                for (cid, _), cb in list(self._breakers.items()):
                    if cid == connector_id:
                        cb.reset()
            else:
                self._breakers.clear()


# Global circuit breaker registry
circuit_breaker_registry = CircuitBreakerRegistry()
