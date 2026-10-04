"""Integration Framework Contract and Shared Base Adapter (Prompt 60 / BBP Section 13.5).

Mirrors the CloudLens connector contract:
- Explicit declared capabilities enforced at runtime (Item 89/90 pattern).
- Secret store credential resolution through opaque reference URIs (SEC-008/SEC-009).
- Master-data-driven configuration with rate limiting, timeouts, and circuit breakers.
- Resilient execution with retry, exponential backoff, jitter, and circuit breaker protection.
- Health tracking and delivery telemetry mirroring connector diagnostics.
"""

from __future__ import annotations

import datetime as dt
import logging
import random
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any, TypeVar

from domain.credentials.store import SecretStore
from domain.integrations.exceptions import (
    IntegrationCircuitOpenException,
    IntegrationRateLimitExceededException,
    UndeclaredIntegrationCapabilityException,
)
from domain.integrations.models import (
    IntegrationConfig,
    IntegrationHealthRecord,
    OutboundDeliveryAttempt,
)
from domain.models.enums import (
    IntegrationCapability,
    IntegrationDeliveryOutcome,
    IntegrationHealth,
    IntegrationType,
)

logger = logging.getLogger(__name__)
T = TypeVar("T")


class BaseIntegrationAdapter(ABC):
    """Abstract base class for all enterprise integration adapters."""

    def __init__(
        self,
        config: IntegrationConfig,
        declared_capabilities: set[IntegrationCapability] | None = None,
    ) -> None:
        self.config = config
        self.integration_id = config.integration_id
        self.integration_type: IntegrationType = config.integration_type
        self.name = config.name
        self.enabled = config.enabled

        # Set declared capabilities
        self._declared_capabilities: set[IntegrationCapability] = (
            declared_capabilities
            if declared_capabilities is not None
            else (set(config.declared_capabilities) or self.default_capabilities())
        )

        # Health & Telemetry State
        self._health = IntegrationHealthRecord(
            integration_id=self.integration_id,
            status=IntegrationHealth.HEALTHY if self.enabled else IntegrationHealth.PAUSED,
        )

        # Circuit breaker state
        self._consecutive_failures = 0
        self._circuit_open = False
        self._circuit_opened_at: dt.datetime | None = None

        # Rate limiting state (sliding minute window)
        self._request_timestamps: list[float] = []

        # Audit log of delivery attempts
        self._delivery_audits: list[OutboundDeliveryAttempt] = []

    @property
    @abstractmethod
    def adapter_name(self) -> str:
        """Unique adapter system identifier (e.g. 'jira_itsm', 'servicenow_cmdb', 'teams_chat')."""

    def default_capabilities(self) -> set[IntegrationCapability]:
        """Default capabilities declared by this adapter class if not passed explicitly."""
        return {IntegrationCapability.AUTHENTICATE, IntegrationCapability.HEALTH_CHECK}

    @property
    def declared_capabilities(self) -> set[IntegrationCapability]:
        """Set of capabilities statically declared and supported by this adapter."""
        return set(self._declared_capabilities)

    def has_capability(self, capability: IntegrationCapability) -> bool:
        """Checks whether this adapter explicitly declares the given capability."""
        return capability in self._declared_capabilities

    def _assert_declared(self, capability: IntegrationCapability) -> None:
        """Guards capability invocation. Fails fast if capability is not declared."""
        if not self.has_capability(capability):
            logger.error(
                "Attempted invocation of undeclared capability '%s' on adapter '%s' (%s)",
                capability.value,
                self.integration_id,
                self.adapter_name,
            )
            raise UndeclaredIntegrationCapabilityException(
                f"Adapter '{self.integration_id}' ({self.adapter_name}) does not declare "
                f"capability '{capability.value}'."
            )

    def resolve_credentials(
        self, secret_store: SecretStore | None, tenant_id: str | None = None
    ) -> dict[str, Any]:
        """Resolves credential material from the secret store via opaque reference URI."""
        if self.config.is_sandbox:
            return {"api_key": "sandbox-simulated-key", "token": "sandbox-token"}

        if not secret_store:
            return {}

        return secret_store.get_secret(self.config.credential_ref, tenant_id)

    def _check_circuit_breaker(self) -> None:
        """Evaluates circuit breaker state and enforces cooldown / half-open probing."""
        if not self._circuit_open:
            return

        if self._circuit_opened_at is None:
            self._circuit_open = False
            return

        elapsed = (dt.datetime.now(dt.UTC) - self._circuit_opened_at).total_seconds()
        if elapsed > self.config.circuit_breaker_reset_seconds:
            # Half-open trial
            logger.info(
                "Circuit breaker cooldown elapsed (%0.1fs); attempting half-open probe for '%s'.",
                elapsed,
                self.integration_id,
            )
            self._circuit_open = False
        else:
            raise IntegrationCircuitOpenException(
                f"Circuit breaker is OPEN for adapter '{self.integration_id}'. "
                f"Failures: {self._consecutive_failures}, cooldown remaining: {self.config.circuit_breaker_reset_seconds - elapsed:.1f}s."
            )

    def _check_rate_limit(self) -> None:
        """Enforces rate limiting using a sliding 60-second window."""
        now_ts = time.time()
        # Evict timestamps older than 60 seconds
        self._request_timestamps = [t for t in self._request_timestamps if now_ts - t < 60.0]
        if len(self._request_timestamps) >= self.config.rate_limit_per_minute:
            raise IntegrationRateLimitExceededException(
                f"Rate limit exceeded on adapter '{self.integration_id}': "
                f"{len(self._request_timestamps)} requests in last 60s (limit: {self.config.rate_limit_per_minute}/min)."
            )
        self._request_timestamps.append(now_ts)

    def execute_with_resilience(
        self,
        capability: IntegrationCapability,
        action_name: str,
        fn: Callable[[], T],
        event_id: str | None = None,
    ) -> T:
        """Executes an operation with capability validation, rate limiting, retries, and circuit breaker."""
        self._assert_declared(capability)
        self._check_circuit_breaker()
        self._check_rate_limit()

        max_retries = self.config.max_retries
        backoff_base = self.config.backoff_base_seconds
        attempt = 1
        start_time = time.time()

        while attempt <= max_retries + 1:
            try:
                result = fn()
                duration_ms = (time.time() - start_time) * 1000.0

                # Reset failure counters on success
                self._consecutive_failures = 0
                self._circuit_open = False
                self._circuit_opened_at = None

                # Record health
                self._health.last_success_at = dt.datetime.now(dt.UTC)
                self._health.consecutive_failures = 0
                self._health.lag_ms = duration_ms
                self._health.total_delivered += 1
                self._health.status = IntegrationHealth.HEALTHY

                # Audit success
                if event_id:
                    self._delivery_audits.append(
                        OutboundDeliveryAttempt(
                            event_id=event_id,
                            integration_id=self.integration_id,
                            attempt_number=attempt,
                            outcome=IntegrationDeliveryOutcome.DELIVERED,
                            duration_ms=duration_ms,
                            http_status=200,
                        )
                    )

                return result

            except Exception as exc:
                duration_ms = (time.time() - start_time) * 1000.0
                logger.warning(
                    "Adapter '%s' action '%s' failed on attempt %d: %s",
                    self.integration_id,
                    action_name,
                    attempt,
                    exc,
                )

                if attempt <= max_retries:
                    self._health.total_retried += 1
                    # Jittered exponential backoff
                    sleep_duration = backoff_base * (2 ** (attempt - 1)) + random.uniform(0.01, 0.1)  # noqa: S311
                    time.sleep(min(sleep_duration, 1.0))  # Bound sleep in tests
                    attempt += 1
                else:
                    # Permanent failure after exhausting retries
                    self._consecutive_failures += 1
                    self._health.last_failure_at = dt.datetime.now(dt.UTC)
                    self._health.consecutive_failures = self._consecutive_failures
                    self._health.last_error_message = str(exc)
                    self._health.total_failed += 1

                    # Check circuit breaker trip
                    if self._consecutive_failures >= self.config.circuit_breaker_threshold:
                        self._circuit_open = True
                        self._circuit_opened_at = dt.datetime.now(dt.UTC)
                        self._health.status = IntegrationHealth.UNHEALTHY
                        logger.error(
                            "Circuit breaker TRIPPED for adapter '%s' after %d consecutive failures.",
                            self.integration_id,
                            self._consecutive_failures,
                        )
                    else:
                        self._health.status = IntegrationHealth.DEGRADED

                    if event_id:
                        self._delivery_audits.append(
                            OutboundDeliveryAttempt(
                                event_id=event_id,
                                integration_id=self.integration_id,
                                attempt_number=attempt,
                                outcome=IntegrationDeliveryOutcome.FAILED,
                                duration_ms=duration_ms,
                                error_message=str(exc),
                            )
                        )
                    raise

        raise RuntimeError(f"Unexpected termination in resilient loop for {self.integration_id}")

    def get_health(self) -> IntegrationHealthRecord:
        """Returns the current operational health record for this adapter."""
        now_ts = time.time()
        active_window = [t for t in self._request_timestamps if now_ts - t < 60.0]
        self._health.throughput_per_minute = float(len(active_window))
        self._health.last_checked_at = dt.datetime.now(dt.UTC)
        return self._health

    def get_delivery_audits(self) -> list[OutboundDeliveryAttempt]:
        """Returns historical delivery audit entries for inspection."""
        return list(self._delivery_audits)
