"""CloudLens Guarded Connector Execution Engine (Prompt 14 Items 90, 92, 93, 94, 95).

Enforces:
- Strict undeclared capability rejection (Item 90).
- Per-capability circuit breaking and failure isolation (Items 91, 92).
- Shared token bucket rate limiting and retry-after honoring (Item 92).
- Adaptive concurrency control (AIMD) under throttling (Item 92).
- Checkpointed pagination without duplicate records (Item 93).
- Hourly quota consumption and diagnostics (Item 94).
- Immutable raw payload landing in tenant-scoped object storage (Item 95).
- Verbatim provider error reporting with plain-language explanations (Do Not swallow errors).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Callable, Coroutine
from typing import Any, TypeVar

from connectors.contract.adaptive_concurrency import AdaptiveConcurrencyController
from connectors.contract.base import BaseCloudConnector
from connectors.contract.checkpoint_store import CheckpointStore, checkpoint_store
from connectors.contract.circuit_breaker import CircuitBreakerRegistry, circuit_breaker_registry
from connectors.contract.lifecycle import ConnectorLifecycleManager, connector_lifecycle_manager
from connectors.contract.models import (
    CapabilityErrorDetail,
    PagedResult,
    PaginationParams,
)
from connectors.contract.quota_tracker import HourlyQuotaTracker, hourly_quota_tracker
from connectors.contract.rate_limiter import SharedTokenBucket, calculate_backoff, parse_retry_after
from connectors.contract.raw_landing import RawLandingService, raw_landing_service
from domain.models.enums import ConnectorCapability
from domain.models.exceptions import (
    MissingTenantContextException,
    ProviderRawErrorException,
    UndeclaredCapabilityException,
)
from domain.tenant.context import TenantContext

logger = logging.getLogger(__name__)
T = TypeVar("T")


class ConnectorExecutionEngine:
    """Orchestrates guarded invocation of connector capabilities with full resilience."""

    def __init__(
        self,
        rate_limiter: SharedTokenBucket | None = None,
        concurrency_controller: AdaptiveConcurrencyController | None = None,
        cb_registry: CircuitBreakerRegistry | None = None,
        lifecycle_manager: ConnectorLifecycleManager | None = None,
        quota_tracker: HourlyQuotaTracker | None = None,
        landing_service: RawLandingService | None = None,
        chk_store: CheckpointStore | None = None,
    ) -> None:
        self._custom_rate_limiter = rate_limiter
        self._custom_concurrency_controller = concurrency_controller
        self._rate_limiters: dict[str, SharedTokenBucket] = {}
        self._concurrency_controllers: dict[str, AdaptiveConcurrencyController] = {}
        self._cb_registry = cb_registry or circuit_breaker_registry
        self._lifecycle = lifecycle_manager or connector_lifecycle_manager
        self._quota = quota_tracker or hourly_quota_tracker
        self._landing = landing_service or raw_landing_service
        self._checkpoints = chk_store or checkpoint_store

    def _get_rate_limiter(self, connector_id: str) -> SharedTokenBucket:
        if connector_id not in self._rate_limiters:
            self._rate_limiters[connector_id] = self._custom_rate_limiter or SharedTokenBucket(
                connector_id=connector_id
            )
        return self._rate_limiters[connector_id]

    def _get_concurrency_controller(self, connector_id: str) -> AdaptiveConcurrencyController:
        if connector_id not in self._concurrency_controllers:
            self._concurrency_controllers[connector_id] = (
                self._custom_concurrency_controller
                or AdaptiveConcurrencyController(connector_id=connector_id)
            )
        return self._concurrency_controllers[connector_id]

    async def execute_capability(
        self,
        tenant_context: TenantContext,
        connector: BaseCloudConnector,
        capability: ConnectorCapability,
        operation: Callable[[], Coroutine[Any, Any, T]],
        max_retries: int = 3,
        run_id: str | None = None,
        page_number: int = 1,
        land_payload: bool = True,
        schema_version: str = "2026-09-01",
    ) -> T:
        """Executes a capability call through the full resilience stack.

        Guarantees:
        1. Fails fast if capability is not declared (Prompt 14 Item 90).
        2. Fails fast if circuit breaker is OPEN (Item 92).
        3. Fails fast if hourly quota is exhausted (Item 94).
        4. Acquires rate limiter token and adaptive concurrency lease.
        5. On throttle, backs off, halves concurrency, retries without dropping data.
        6. On success, records healthy status, restores concurrency, lands raw payload.
        7. On failure, surfaces verbatim provider error alongside explanation.
        """
        if not tenant_context or not tenant_context.tenant_id:
            raise MissingTenantContextException(
                "Cannot execute connector capability without authenticated TenantContext."
            )

        connector_id = connector.connector_id
        tenant_id = tenant_context.tenant_id

        # 1. Undeclared Capability Guard (Item 90: Platform must NEVER invoke undeclared capability)
        if not connector.has_capability(capability):
            raise UndeclaredCapabilityException(
                connector_id=connector_id,
                capability=capability.value,
            )

        # 2. Per-Capability Circuit Breaker Guard (Item 92)
        breaker = self._cb_registry.get_breaker(connector_id, capability)
        breaker.check_permission()

        # 3. Hourly Quota Check (Item 94)
        self._quota.record_request(tenant_id=tenant_id, connector_id=connector_id, count=1)

        rate_limiter = self._get_rate_limiter(connector_id)
        concurrency = self._get_concurrency_controller(connector_id)

        active_run_id = run_id or f"run-{uuid.uuid4().hex[:10]}"
        attempt = 0

        while attempt <= max_retries:
            # 4. Acquire Rate Limiter Token (Item 92)
            await rate_limiter.acquire_async(tokens=1.0)

            # 5. Acquire Adaptive Concurrency Slot (Item 92)
            slot_acquired = await concurrency.acquire_slot_async()
            if not slot_acquired:
                # If concurrency slot timed out, sleep briefly and retry
                await asyncio.sleep(0.5)
                attempt += 1
                continue

            try:
                # 6. Execute Provider Capability Operation
                result = await operation()

                # Success path
                concurrency.record_success()
                breaker.record_success()
                self._lifecycle.record_capability_success(
                    tenant_context=tenant_context,
                    connector_id=connector_id,
                    capability=capability,
                )

                # 7. Raw Payload Landing (Item 95)
                if land_payload and result is not None:
                    self._landing.land_raw_payload(
                        tenant_context=tenant_context,
                        connector_id=connector_id,
                        run_id=active_run_id,
                        capability=capability,
                        page_number=page_number,
                        raw_payload=result,
                        schema_version=schema_version,
                    )

                return result

            except Exception as exc:
                # Check for throttling / rate limit errors
                err_str = str(exc)
                is_throttled = (
                    "429" in err_str
                    or "RateExceeded" in err_str
                    or "TooManyRequests" in err_str
                    or "Throttl" in err_str
                )

                if is_throttled and attempt < max_retries:
                    # Adaptive Concurrency Reduction: Multiplicative Decrease (Item 92)
                    concurrency.record_throttle(error_detail=err_str)
                    retry_after = parse_retry_after(exc)
                    backoff = calculate_backoff(
                        attempt=attempt,
                        base_delay=1.0,
                        max_delay=30.0,
                        retry_after=retry_after,
                    )
                    logger.warning(
                        "Throttling on connector %s (%s). Backing off %.2fs (attempt %d/%d)",
                        connector_id,
                        capability.value,
                        backoff,
                        attempt + 1,
                        max_retries,
                    )
                    attempt += 1
                    await asyncio.sleep(backoff)
                    continue

                # Non-throttled failure or retries exhausted
                plain_explanation = self._generate_plain_language_explanation(
                    connector.provider_name, capability, exc
                )
                error_detail = CapabilityErrorDetail(
                    capability=capability,
                    verbatim_error=err_str,
                    plain_language_explanation=plain_explanation,
                )

                # Per-Capability Failure Isolation (Item 91)
                self._lifecycle.record_capability_failure(
                    tenant_context=tenant_context,
                    connector_id=connector_id,
                    capability=capability,
                    error_detail=error_detail,
                )

                # Surface verbatim provider error alongside plain-language explanation (Prompt 14 constraint)
                raise ProviderRawErrorException(
                    provider=connector.provider_name,
                    capability=capability.value,
                    verbatim_error=err_str,
                    plain_language_explanation=plain_explanation,
                ) from exc

            finally:
                concurrency.release_slot_async()

        raise ProviderRawErrorException(
            provider=connector.provider_name,
            capability=capability.value,
            verbatim_error=f"Maximum retries ({max_retries}) exceeded under continuous throttling.",
            plain_language_explanation="The cloud provider continuously rejected requests with throttling errors. Concurrency was reduced to minimum.",
        )

    async def execute_paginated_capability(
        self,
        tenant_context: TenantContext,
        connector: BaseCloudConnector,
        capability: ConnectorCapability,
        page_fetcher: Callable[[PaginationParams], Coroutine[Any, Any, PagedResult[T]]],
        job_id: str,
        page_size: int = 100,
        max_pages: int | None = None,
        simulate_kill_after_page: int | None = None,
    ) -> list[T]:
        """Executes a paginated sync with continuation tokens persisted after every page.

        Guarantees:
        - Checkpoint persisted after each page.
        - Resumes from checkpoint continuation token if job was previously interrupted.
        - Zero duplicate records and zero lost records (Item 93).
        """
        if not tenant_context or not tenant_context.tenant_id:
            raise MissingTenantContextException(
                "Cannot execute paginated sync without authenticated TenantContext."
            )

        connector_id = connector.connector_id
        accumulated_items: list[T] = []

        # 1. Check for existing checkpoint to resume
        latest_chk = self._checkpoints.get_latest_checkpoint(
            tenant_context=tenant_context,
            job_id=job_id,
            capability=capability,
        )

        continuation_token: str | None = None
        current_page = 1
        records_so_far = 0

        if latest_chk and latest_chk.status == "IN_PROGRESS" and latest_chk.continuation_token:
            continuation_token = latest_chk.continuation_token
            current_page = latest_chk.page_number + 1
            records_so_far = latest_chk.records_ingested
            logger.info(
                "Resuming job %s from checkpoint: page=%d, records_so_far=%d, token=%s",
                job_id,
                current_page,
                records_so_far,
                continuation_token,
            )

        pages_executed = 0
        while True:
            pagination = PaginationParams(
                page_size=page_size,
                continuation_token=continuation_token,
                page_number=current_page,
            )

            def _make_page_fetcher(p: PaginationParams):
                async def _fetch() -> Any:
                    return await page_fetcher(p)

                return _fetch

            # Execute single page through guarded engine
            page_result = await self.execute_capability(
                tenant_context=tenant_context,
                connector=connector,
                capability=capability,
                operation=_make_page_fetcher(pagination),
                run_id=job_id,
                page_number=current_page,
            )

            items = list(page_result)
            accumulated_items.extend(items)
            records_so_far += len(items)

            # Determine next continuation token
            next_token = (
                page_result.continuation_token if isinstance(page_result, PagedResult) else None
            )
            is_truncated = (
                page_result.is_truncated
                if isinstance(page_result, PagedResult)
                else bool(next_token)
            )

            # Persist checkpoint immediately after landing this page
            self._checkpoints.save_checkpoint(
                tenant_context=tenant_context,
                job_id=job_id,
                connector_id=connector_id,
                capability=capability,
                continuation_token=next_token if is_truncated else None,
                page_number=current_page,
                records_ingested=records_so_far,
                status="IN_PROGRESS" if is_truncated else "COMPLETED",
            )

            # Simulated worker interruption test hook
            if simulate_kill_after_page is not None and current_page == simulate_kill_after_page:
                logger.warning(
                    "Simulated worker kill triggered after page %d for job %s", current_page, job_id
                )
                raise InterruptedError(f"Simulated worker kill after page {current_page}")

            if not is_truncated or not next_token:
                break

            continuation_token = next_token
            current_page += 1
            pages_executed += 1
            if max_pages and pages_executed >= max_pages:
                break

        return accumulated_items

    def _generate_plain_language_explanation(
        self,
        provider: str,
        capability: ConnectorCapability,
        exc: Exception,
    ) -> str:
        """Translates cryptic provider API exceptions into plain-language business explanations."""
        err_text = str(exc).lower()
        if "accessdenied" in err_text or "unauthorized" in err_text or "forbidden" in err_text:
            return (
                f"The {provider.upper()} API rejected the request due to missing permissions for "
                f"capability '{capability.value}'. Verify that your credential profile has the necessary read-only role."
            )
        if "throttl" in err_text or "429" in err_text or "rateexceeded" in err_text:
            return (
                f"The {provider.upper()} API rate limit was exceeded for '{capability.value}'. "
                f"CloudLens reduced request concurrency and will automatically resume once the window resets."
            )
        if "notfound" in err_text or "404" in err_text:
            return (
                f"The requested scope or resource was not found in {provider.upper()}. "
                "It may have been deleted or moved to a different management hierarchy."
            )
        return f"A provider communication error occurred while invoking '{capability.value}' on {provider.upper()}."


# Global execution engine singleton
connector_execution_engine = ConnectorExecutionEngine()
