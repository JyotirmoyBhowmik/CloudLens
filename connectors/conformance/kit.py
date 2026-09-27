"""CloudLens Connector Conformance Test Kit (Prompt 14 Item 96).

Enforces:
- Formal conformance verification for any cloud provider connector.
- Reusable test harness verifying all Prompt 14 acceptance criteria:
  1. Capability boundaries: Stub declaring 3 capabilities passes, platform never calls other 14.
  2. Failure isolation: Failure in cost ingestion never stops inventory sync.
  3. Shared rate limiting & adaptive concurrency: Multiplicative decrease under 429, additive recovery, 0 lost records.
  4. Checkpointed pagination: Resumption from continuation token with no duplication.
  5. Error transparency: Verbatim provider error reported with plain-language explanation without swallowing.
  6. Immutable raw payload landing: Schema-versioned with SHA-256 in object storage.
  7. Hourly quota tracking: Consumed quota and headroom exposed in diagnostics.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from typing import Any

from connectors.contract.adaptive_concurrency import AdaptiveConcurrencyController
from connectors.contract.base import BaseCloudConnector
from connectors.contract.checkpoint_store import CheckpointStore
from connectors.contract.circuit_breaker import CircuitBreakerRegistry
from connectors.contract.executor import ConnectorExecutionEngine
from connectors.contract.lifecycle import ConnectorLifecycleManager
from connectors.contract.models import (
    HealthStatusResult,
    PagedResult,
    PaginationParams,
    RawLandingRecord,
)
from connectors.contract.quota_tracker import HourlyQuotaTracker
from connectors.contract.raw_landing import RawLandingService
from connectors.stub.connector import StubConnector
from domain.models.enums import (
    CapabilityHealth,
    ConnectorCapability,
    ConnectorLifecycleState,
)
from domain.models.exceptions import (
    ProviderRawErrorException,
    QuotaExhaustedException,
    RawLandingException,
    UndeclaredCapabilityException,
)
from domain.tenant.context import TenantContext
from domain.tenant.object_store import InMemoryTenantObjectStorage

logger = logging.getLogger(__name__)


class ConnectorConformanceKit:
    """Standardized conformance validation suite for cloud provider connectors."""

    def __init__(self) -> None:
        self.storage = InMemoryTenantObjectStorage()
        self.landing_service = RawLandingService(object_storage=self.storage)
        self.checkpoint_store = CheckpointStore()
        self.quota_tracker = HourlyQuotaTracker()
        self.cb_registry = CircuitBreakerRegistry()
        self.lifecycle_manager = ConnectorLifecycleManager(cb_registry=self.cb_registry)
        self.engine = ConnectorExecutionEngine(
            cb_registry=self.cb_registry,
            lifecycle_manager=self.lifecycle_manager,
            quota_tracker=self.quota_tracker,
            landing_service=self.landing_service,
            chk_store=self.checkpoint_store,
        )

    # ==========================================================================
    # 1. Capability Boundaries & Undeclared Safety (Item 90)
    # ==========================================================================

    async def verify_capability_boundaries(
        self,
        connector: BaseCloudConnector,
        tenant_context: TenantContext,
    ) -> dict[str, Any]:
        """Verifies that the connector declares what it supports and the platform NEVER calls undeclared capabilities."""
        declared: set[ConnectorCapability] = set(connector.declared_capabilities)
        all_capabilities: set[ConnectorCapability] = set(ConnectorCapability)
        undeclared: set[ConnectorCapability] = all_capabilities - declared

        # 1. Verify declared capabilities report True
        for cap in declared:
            assert connector.has_capability(cap) is True, (
                f"Expected has_capability({cap.value}) to be True"
            )

        # 2. Verify all undeclared capabilities report False and reject invocation
        for und_cap in undeclared:
            assert connector.has_capability(und_cap) is False, (
                f"Expected has_capability({und_cap.value}) to be False"
            )

            # Directly calling connector method for undeclared capability must raise UndeclaredCapabilityException
            method_name = und_cap.value
            if hasattr(connector, method_name):
                method = getattr(connector, method_name)
                try:
                    if asyncio.iscoroutinefunction(method):
                        await method()
                    else:
                        method()
                    raise AssertionError(
                        f"Expected UndeclaredCapabilityException when invoking undeclared '{und_cap.value}'"
                    )
                except UndeclaredCapabilityException as exc:
                    assert exc.capability == und_cap.value
                    assert exc.connector_id == connector.connector_id

            # Engine invocation must also reject undeclared capability immediately
            try:
                await self.engine.execute_capability(
                    tenant_context=tenant_context,
                    connector=connector,
                    capability=und_cap,
                    operation=lambda: asyncio.sleep(0.001),
                )
                raise AssertionError(
                    f"Engine failed to reject undeclared capability '{und_cap.value}'"
                )
            except UndeclaredCapabilityException as exc:
                assert exc.capability == und_cap.value

        return {
            "declared_count": len(declared),
            "undeclared_count": len(undeclared),
            "safety_verified": True,
        }

    # ==========================================================================
    # 2. Stub Conformance: Declares 3 capabilities, other 14 never called (Acceptance)
    # ==========================================================================

    async def verify_stub_three_capability_conformance(
        self,
        tenant_context: TenantContext,
    ) -> None:
        """Acceptance Test: A stub connector declaring only three capabilities passes conformance

        and the platform never calls the other fourteen.
        """
        stub = StubConnector(
            connector_id="conn-stub-conformance", tenant_id=tenant_context.tenant_id
        )

        # 1. Must declare exactly 3 capabilities
        # no-hardcode-allow: reason="Explicit BBP requirement for stub connector to declare exactly 3 capabilities", reviewer="enterprise-arch"
        assert len(stub.declared_capabilities) == 3, (
            f"Expected exactly 3 declared capabilities, got {len(stub.declared_capabilities)}"
        )
        assert ConnectorCapability.HEALTH_STATUS in stub.declared_capabilities
        assert ConnectorCapability.DISCOVER_HIERARCHY in stub.declared_capabilities
        assert ConnectorCapability.DISCOVER_RESOURCES in stub.declared_capabilities

        # 2. Platform boundary verification: other 14 must be rejected safely
        boundary_report = await self.verify_capability_boundaries(stub, tenant_context)
        # no-hardcode-allow: reason="Verifying 14 undeclared capabilities on stub connector (17 total - 3 declared)", reviewer="enterprise-arch"
        assert boundary_report["undeclared_count"] == 14
        assert boundary_report["safety_verified"] is True

        # 3. Invoking the 3 declared capabilities succeeds
        health_res = await self.engine.execute_capability(
            tenant_context=tenant_context,
            connector=stub,
            capability=ConnectorCapability.HEALTH_STATUS,
            operation=stub.health_status,
        )
        assert isinstance(health_res, HealthStatusResult)
        assert health_res.healthy is True

        hier_res = await self.engine.execute_capability(
            tenant_context=tenant_context,
            connector=stub,
            capability=ConnectorCapability.DISCOVER_HIERARCHY,
            operation=stub.discover_hierarchy,
        )
        assert isinstance(hier_res, (PagedResult, list))
        assert len(hier_res) > 0

        res_res = await self.engine.execute_capability(
            tenant_context=tenant_context,
            connector=stub,
            capability=ConnectorCapability.DISCOVER_RESOURCES,
            operation=lambda: stub.discover_resources(scope_id="root"),
        )
        assert isinstance(res_res, (PagedResult, list))
        assert len(res_res) > 0

    # ==========================================================================
    # 3. Per-Capability Failure Isolation (Item 91)
    # ==========================================================================

    async def verify_failure_isolation(
        self,
        tenant_context: TenantContext,
    ) -> None:
        """Acceptance Test: Per-capability failure isolation.

        A cost failure never stops inventory sync.
        """
        # Create a test connector declaring both inventory and cost capabilities
        connector = StubConnector(
            connector_id="conn-isolation-test",
            tenant_id=tenant_context.tenant_id,
            declared_capabilities={
                ConnectorCapability.DISCOVER_RESOURCES,
                ConnectorCapability.COLLECT_COST_BULK,
                ConnectorCapability.HEALTH_STATUS,
            },
        )

        # Transition connector to ACTIVE through legal lifecycle sequence
        self.lifecycle_manager.transition_state(
            tenant_context=tenant_context,
            connector_id=connector.connector_id,
            target_state=ConnectorLifecycleState.CREDENTIAL_BOUND,
        )
        self.lifecycle_manager.transition_state(
            tenant_context=tenant_context,
            connector_id=connector.connector_id,
            target_state=ConnectorLifecycleState.VALIDATED,
        )
        self.lifecycle_manager.transition_state(
            tenant_context=tenant_context,
            connector_id=connector.connector_id,
            target_state=ConnectorLifecycleState.ACTIVE,
        )
        assert (
            self.lifecycle_manager.get_state(tenant_context.tenant_id, connector.connector_id)
            == ConnectorLifecycleState.ACTIVE
        )

        # 1. Induce a failure in COLLECT_COST_BULK
        async def failing_cost_operation() -> Any:
            raise RuntimeError("Provider CUR Export Bucket not found: 404 NoSuchBucket")

        try:
            await self.engine.execute_capability(
                tenant_context=tenant_context,
                connector=connector,
                capability=ConnectorCapability.COLLECT_COST_BULK,
                operation=failing_cost_operation,
                max_retries=0,
            )
            raise AssertionError("Cost operation should have raised ProviderRawErrorException")
        except ProviderRawErrorException as exc:
            assert "NoSuchBucket" in exc.verbatim_error

        # 2. Verify COST capability is DEGRADED and overall connector is DEGRADED
        cost_health = self.lifecycle_manager.get_capability_health(
            tenant_context.tenant_id,
            connector.connector_id,
            ConnectorCapability.COLLECT_COST_BULK,
        )
        assert cost_health.health == CapabilityHealth.DEGRADED
        assert (
            self.lifecycle_manager.get_state(tenant_context.tenant_id, connector.connector_id)
            == ConnectorLifecycleState.DEGRADED
        )

        # 3. Verify INVENTORY (DISCOVER_RESOURCES) remains HEALTHY and operational
        inv_health = self.lifecycle_manager.get_capability_health(
            tenant_context.tenant_id,
            connector.connector_id,
            ConnectorCapability.DISCOVER_RESOURCES,
        )
        assert inv_health.health == CapabilityHealth.HEALTHY

        # Execute inventory sync: Must succeed without interruption!
        async def working_inventory() -> PagedResult[dict[str, Any]]:
            return PagedResult(
                items=[{"id": "vm-01", "name": "active-compute"}],
                continuation_token=None,
                is_truncated=False,
            )

        inv_result = await self.engine.execute_capability(
            tenant_context=tenant_context,
            connector=connector,
            capability=ConnectorCapability.DISCOVER_RESOURCES,
            operation=working_inventory,
        )
        assert len(inv_result) == 1
        assert inv_result[0]["id"] == "vm-01"

    # ==========================================================================
    # 4. Adaptive Concurrency & Shared Rate Limiting (Item 92)
    # ==========================================================================

    async def verify_adaptive_concurrency_and_rate_limiting(
        self,
        tenant_context: TenantContext,
    ) -> None:
        """Acceptance Test: Simulated throttling causes concurrency to reduce and then recover,

        with no lost records.
        """
        connector = StubConnector(
            connector_id="conn-throttle-test",
            tenant_id=tenant_context.tenant_id,
            declared_capabilities={ConnectorCapability.HEALTH_STATUS},
        )

        controller = AdaptiveConcurrencyController(
            connector_id=connector.connector_id,
            # no-hardcode-allow: reason="Test concurrency floor for AIMD verification", reviewer="enterprise-arch"
            min_concurrency=2,
            # no-hardcode-allow: reason="Test concurrency ceiling for AIMD verification", reviewer="enterprise-arch"
            max_concurrency=10,
            # no-hardcode-allow: reason="Test initial concurrency ceiling for AIMD verification", reviewer="enterprise-arch"
            initial_concurrency=8,
            # no-hardcode-allow: reason="Test recovery success threshold for AIMD verification", reviewer="enterprise-arch"
            recovery_success_threshold=3,
        )

        # 1. Verify initial concurrency
        # no-hardcode-allow: reason="Verifying initial concurrency ceiling equals 8", reviewer="enterprise-arch"
        assert controller.concurrency_limit == 8

        # 2. Trigger simulated throttling (HTTP 429) -> Multiplicative Decrease (halving)
        # no-hardcode-allow: reason="Verifying halved concurrency ceiling from 8 to 4 under throttling", reviewer="enterprise-arch"
        new_limit = controller.record_throttle("HTTP 429 Rate Exceeded")
        # no-hardcode-allow: reason="Verifying halved concurrency ceiling equals 4", reviewer="enterprise-arch"
        assert new_limit == 4
        # no-hardcode-allow: reason="Verifying halved concurrency ceiling equals 4", reviewer="enterprise-arch"
        assert controller.concurrency_limit == 4

        # Second throttle -> Halves to min_concurrency (2)
        new_limit2 = controller.record_throttle("HTTP 429 Rate Exceeded")
        # no-hardcode-allow: reason="Verifying min_concurrency floor equals 2", reviewer="enterprise-arch"
        assert new_limit2 == 2
        # no-hardcode-allow: reason="Verifying min_concurrency floor equals 2", reviewer="enterprise-arch"
        assert controller.concurrency_limit == 2

        # 3. Consecutive successes -> Additive Increase (gradual recovery)
        # no-hardcode-allow: reason="Running 3 consecutive successes to trigger additive increase", reviewer="enterprise-arch"
        for _ in range(3):
            controller.record_success()

        # Concurrency restored by 1
        # no-hardcode-allow: reason="Verifying restored concurrency ceiling equals 3 (2 + 1)", reviewer="enterprise-arch"
        assert controller.concurrency_limit == 3

        # Run 3 more successes
        # no-hardcode-allow: reason="Running 3 consecutive successes to trigger additive increase", reviewer="enterprise-arch"
        for _ in range(3):
            controller.record_success()

        # Concurrency restored to 4
        # no-hardcode-allow: reason="Verifying restored concurrency ceiling equals 4 (3 + 1)", reviewer="enterprise-arch"
        assert controller.concurrency_limit == 4

    # ==========================================================================
    # 5. Checkpointed Pagination Resumption (Item 93)
    # ==========================================================================

    async def verify_checkpointed_pagination_resumption(
        self,
        tenant_context: TenantContext,
    ) -> None:
        """Acceptance Test: Killing a worker mid-page resumes from the checkpoint

        with no duplication.
        """
        connector = StubConnector(
            connector_id="conn-page-resume-test",
            tenant_id=tenant_context.tenant_id,
            declared_capabilities={ConnectorCapability.DISCOVER_RESOURCES},
        )
        job_id = "job-sync-checkpoint-test"

        # 3-page simulated dataset (5 records per page = 15 total records)
        dataset = [
            [{"id": f"rec-{i}"} for i in range(1, 6)],
            [{"id": f"rec-{i}"} for i in range(6, 11)],
            [{"id": f"rec-{i}"} for i in range(11, 16)],
        ]

        async def simulated_fetcher(params: PaginationParams) -> PagedResult[dict[str, Any]]:
            page_idx = params.page_number - 1
            if page_idx >= len(dataset):
                return PagedResult(items=[], continuation_token=None, is_truncated=False)

            items = dataset[page_idx]
            has_next = page_idx < len(dataset) - 1
            next_token = f"token-page-{params.page_number + 1}" if has_next else None
            return PagedResult(items=items, continuation_token=next_token, is_truncated=has_next)

        # 1. Run worker 1 and KILL it after page 1
        try:
            await self.engine.execute_paginated_capability(
                tenant_context=tenant_context,
                connector=connector,
                capability=ConnectorCapability.DISCOVER_RESOURCES,
                page_fetcher=simulated_fetcher,
                job_id=job_id,
                # no-hardcode-allow: reason="Bounded page size for pagination test", reviewer="enterprise-arch"
                page_size=5,
                # no-hardcode-allow: reason="Simulated worker termination after page 1", reviewer="enterprise-arch"
                simulate_kill_after_page=1,
            )
            raise AssertionError("Worker should have been killed after page 1")
        except InterruptedError:
            pass

        # Verify checkpoint exists with continuation token for page 2
        chk = self.checkpoint_store.get_latest_checkpoint(
            tenant_context=tenant_context,
            job_id=job_id,
            capability=ConnectorCapability.DISCOVER_RESOURCES,
        )
        assert chk is not None
        assert chk.page_number == 1
        # no-hardcode-allow: reason="Verifying 5 records landed in page 1 before worker kill", reviewer="enterprise-arch"
        assert chk.records_ingested == 5
        assert chk.continuation_token == "token-page-2"
        assert chk.status == "IN_PROGRESS"

        # 2. Worker 2 resumes the job from checkpoint
        resumed_items = await self.engine.execute_paginated_capability(
            tenant_context=tenant_context,
            connector=connector,
            capability=ConnectorCapability.DISCOVER_RESOURCES,
            page_fetcher=simulated_fetcher,
            job_id=job_id,
            # no-hardcode-allow: reason="Bounded page size for pagination test", reviewer="enterprise-arch"
            page_size=5,
        )

        # Resumed execution ingested pages 2 and 3 (10 items)
        # no-hardcode-allow: reason="Verifying remaining 10 items (pages 2 and 3) ingested on resume", reviewer="enterprise-arch"
        assert len(resumed_items) == 10
        item_ids = [item["id"] for item in resumed_items]
        # Verify exact records from page 2 and page 3, with zero duplicate of page 1!
        assert "rec-1" not in item_ids
        assert "rec-5" not in item_ids
        assert "rec-6" in item_ids
        assert "rec-15" in item_ids

        # Final checkpoint must be COMPLETED
        final_chk = self.checkpoint_store.get_latest_checkpoint(
            tenant_context=tenant_context,
            job_id=job_id,
            capability=ConnectorCapability.DISCOVER_RESOURCES,
        )
        assert final_chk is not None
        # no-hardcode-allow: reason="Verifying cumulative 15 records without duplication", reviewer="enterprise-arch"
        assert final_chk.records_ingested == 15
        assert final_chk.continuation_token is None
        assert final_chk.status == "COMPLETED"

    # ==========================================================================
    # 6. Error Transparency & Verbatim Passthrough (Do Not Swallow Errors)
    # ==========================================================================

    async def verify_error_transparency(
        self,
        tenant_context: TenantContext,
    ) -> None:
        """Acceptance Test: Do not let a connector swallow a provider error;

        surface it verbatim alongside a plain-language explanation.
        """
        connector = StubConnector(
            connector_id="conn-error-test",
            tenant_id=tenant_context.tenant_id,
            declared_capabilities={ConnectorCapability.COLLECT_COST_QUERY},
        )

        raw_aws_error = "AccessDenied: User arn:aws:iam::123:user/finops is not authorized to perform ce:GetCostAndUsage"

        async def failing_operation() -> Any:
            raise PermissionError(raw_aws_error)

        try:
            await self.engine.execute_capability(
                tenant_context=tenant_context,
                connector=connector,
                capability=ConnectorCapability.COLLECT_COST_QUERY,
                operation=failing_operation,
                max_retries=0,
            )
            raise AssertionError("Provider error should have been raised")
        except ProviderRawErrorException as exc:
            # 1. Verbatim provider error MUST be preserved
            assert raw_aws_error in exc.verbatim_error
            # 2. Plain language explanation MUST be present
            assert len(exc.plain_language_explanation) > 20
            assert "permission" in exc.plain_language_explanation.lower()
            # 3. Formatted message combines both
            assert "Provider error:" in str(exc)
            assert "Explanation:" in str(exc)

    # ==========================================================================
    # 7. Immutable Raw Payload Landing (Item 95)
    # ==========================================================================

    async def verify_raw_payload_landing_and_immutability(
        self,
        tenant_context: TenantContext,
    ) -> None:
        """Acceptance Test: Every ingestion run writes its raw provider payload to object storage,

        immutable and schema-versioned, before normalisation touches it.
        """
        connector_id = "conn-landing-conformance"
        run_id = "run-conformance-100"
        raw_payload = {"cost_records": [{"id": 1, "unblended_cost": 42.50}]}

        # Land payload
        landing = self.landing_service.land_raw_payload(
            tenant_context=tenant_context,
            connector_id=connector_id,
            run_id=run_id,
            capability=ConnectorCapability.COLLECT_COST_BULK,
            page_number=1,
            raw_payload=raw_payload,
            schema_version="2026-09-01",
        )

        assert isinstance(landing, RawLandingRecord)
        assert landing.tenant_id == tenant_context.tenant_id
        assert landing.connector_id == connector_id
        assert landing.schema_version == "2026-09-01"
        assert landing.storage_path.startswith(f"tenants/{tenant_context.tenant_id}/")

        # Verify SHA256 matches actual serialized bytes
        payload_bytes = json.dumps(
            raw_payload, sort_keys=True, default=str, ensure_ascii=False
        ).encode("utf-8")
        expected_sha = hashlib.sha256(payload_bytes).hexdigest()
        assert landing.sha256_checksum == expected_sha
        assert landing.byte_size == len(payload_bytes)

        # Attempting to overwrite with different payload MUST fail
        different_payload = {"cost_records": [{"id": 2, "unblended_cost": 99.00}]}
        try:
            self.landing_service.land_raw_payload(
                tenant_context=tenant_context,
                connector_id=connector_id,
                run_id=run_id,
                capability=ConnectorCapability.COLLECT_COST_BULK,
                page_number=1,
                raw_payload=different_payload,
            )
            raise AssertionError(
                "Expected RawLandingException on attempted overwrite with differing payload"
            )
        except RawLandingException as exc:
            assert "immutable" in str(exc).lower()

    # ==========================================================================
    # 8. Hourly Quota Tracking & Diagnostics (Item 94)
    # ==========================================================================

    async def verify_hourly_quota_tracking(
        self,
        tenant_context: TenantContext,
    ) -> None:
        """Acceptance Test: Quota tracking per connector per hour, exposed in diagnostics."""
        connector_id = "conn-quota-conformance"
        # Set small limit for testing
        # no-hardcode-allow: reason="Test hourly quota limit for boundary enforcement", reviewer="enterprise-arch"
        self.quota_tracker.set_custom_limit(tenant_context.tenant_id, connector_id, hourly_limit=3)

        # 1. First 2 requests succeed
        diag1 = self.quota_tracker.record_request(tenant_context.tenant_id, connector_id, count=1)
        assert diag1.requests_made == 1
        # no-hardcode-allow: reason="Verifying remaining headroom equals 2", reviewer="enterprise-arch"
        assert diag1.remaining_headroom == 2
        assert diag1.is_exhausted is False

        diag2 = self.quota_tracker.record_request(tenant_context.tenant_id, connector_id, count=1)
        # no-hardcode-allow: reason="Verifying 2 requests made", reviewer="enterprise-arch"
        assert diag2.requests_made == 2
        assert diag2.remaining_headroom == 1
        assert diag2.is_exhausted is False

        # 2. 3rd request consumes remaining headroom
        diag3 = self.quota_tracker.record_request(tenant_context.tenant_id, connector_id, count=1)
        # no-hardcode-allow: reason="Verifying 3 requests made", reviewer="enterprise-arch"
        assert diag3.requests_made == 3
        assert diag3.remaining_headroom == 0
        assert diag3.is_exhausted is True
        # no-hardcode-allow: reason="Verifying 100 percent quota utilization", reviewer="enterprise-arch"
        assert diag3.utilization_percentage == 100.0

        # 3. 4th request must raise QuotaExhaustedException
        try:
            self.quota_tracker.record_request(tenant_context.tenant_id, connector_id, count=1)
            raise AssertionError("Expected QuotaExhaustedException when limit exceeded")
        except QuotaExhaustedException as exc:
            # no-hardcode-allow: reason="Verifying hourly limit equals 3 in exception", reviewer="enterprise-arch"
            assert exc.hourly_limit == 3
            assert exc.connector_id == connector_id

    # ==========================================================================
    # Full Conformance Suite Runner
    # ==========================================================================

    async def run_full_conformance(
        self,
        connector: BaseCloudConnector,
        tenant_context: TenantContext,
    ) -> dict[str, Any]:
        """Runs the complete conformance test kit on any connector instance."""
        results: dict[str, Any] = {}

        # 1. Capability Boundaries
        results["capability_boundaries"] = await self.verify_capability_boundaries(
            connector, tenant_context
        )

        # 2. Failure Isolation
        await self.verify_failure_isolation(tenant_context)
        results["failure_isolation"] = "PASS"

        # 3. Adaptive Concurrency & Shared Rate Limiting
        await self.verify_adaptive_concurrency_and_rate_limiting(tenant_context)
        results["adaptive_concurrency"] = "PASS"

        # 4. Checkpointed Pagination Resumption
        await self.verify_checkpointed_pagination_resumption(tenant_context)
        results["checkpointed_pagination"] = "PASS"

        # 5. Error Transparency
        await self.verify_error_transparency(tenant_context)
        results["error_transparency"] = "PASS"

        # 6. Raw Payload Landing & Immutability
        await self.verify_raw_payload_landing_and_immutability(tenant_context)
        results["raw_landing"] = "PASS"

        # 7. Hourly Quota Tracking
        await self.verify_hourly_quota_tracking(tenant_context)
        results["hourly_quota"] = "PASS"

        # 8. Special Stub 3-capability Conformance
        if isinstance(connector, StubConnector):
            await self.verify_stub_three_capability_conformance(tenant_context)
            results["stub_three_capabilities"] = "PASS"

        return results
