"""Unit Tests for CloudLens Connector Contract & Resilience (Prompt 14 / BBP Section 26).

Validates:
- Item 89: Canonical seventeen capabilities defined on BaseCloudConnector.
- Item 90: Capability declaration, runtime probing, and undeclared call rejection.
- Item 91: Lifecycle state machine (Registered to Suspended) with failure isolation.
- Item 92: Shared rate limiting, retry-after hints, exponential backoff with jitter, adaptive concurrency (AIMD), and per-capability circuit breakers.
- Item 93: Mandatory pagination with checkpointed continuation tokens and duplicate-free resumption.
- Item 94: Hourly quota tracking and diagnostics.
- Item 95: Immutable raw payload landing with SHA256 integrity digests before normalization.
- Do Not: Error transparency - verbatim provider error surfaced alongside plain-language explanation.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from fastapi.testclient import TestClient

from api.cloudlens_api.main import app
from connectors.contract.checkpoint_store import CheckpointStore
from connectors.contract.circuit_breaker import CapabilityCircuitBreaker, CircuitBreakerRegistry
from connectors.contract.executor import ConnectorExecutionEngine
from connectors.contract.lifecycle import ConnectorLifecycleManager
from connectors.contract.models import (
    PagedResult,
    PaginationParams,
    RawLandingRecord,
)
from connectors.contract.quota_tracker import HourlyQuotaTracker
from connectors.contract.rate_limiter import SharedTokenBucket, calculate_backoff, parse_retry_after
from connectors.contract.raw_landing import RawLandingService
from connectors.stub.connector import StubConnector
from domain.identity.service import get_identity_service
from domain.models.enums import (
    CapabilityHealth,
    CircuitBreakerState,
    ConnectorCapability,
    ConnectorLifecycleState,
    SystemRole,
)
from domain.models.exceptions import (
    CircuitBreakerOpenException,
    InvalidConnectorStateTransitionException,
    ProviderRawErrorException,
    QuotaExhaustedException,
    RawLandingException,
    UndeclaredCapabilityException,
)
from domain.tenant.context import TenantContext
from domain.tenant.object_store import InMemoryTenantObjectStorage

client = TestClient(app)


@pytest.fixture
def tenant_ctx() -> TenantContext:
    return TenantContext(tenant_id="tenant-p14-test")


@pytest.fixture
def admin_token(tenant_ctx: TenantContext) -> str:
    identity_svc = get_identity_service()
    token_engine = identity_svc.token_engine
    return token_engine.issue_access_token(
        user_id="usr-super-admin",
        tenant_id=tenant_ctx.tenant_id,
        email="admin@jyotirmoyb.com",
        roles=[SystemRole.GLOBAL_ADMIN],
        permissions=["connectors:read", "connectors:write", "credentials:read"],
        session_id="ses-p14-admin",
        token_family_id="fam-p14-admin",
    )


# ==============================================================================
# 1. Canonical Seventeen Capabilities (Item 89)
# ==============================================================================


def test_canonical_seventeen_capabilities_defined():
    """Validates that all seventeen capabilities defined in BBP Section 26 exist in ConnectorCapability."""
    expected = {
        "authenticate",
        "validate_permissions",
        "discover_organizations",
        "discover_accounts",
        "discover_hierarchy",
        "discover_resources",
        "discover_services",
        "collect_cost_bulk",
        "collect_cost_query",
        "collect_usage",
        "collect_pricing_public",
        "collect_pricing_negotiated",
        "collect_tags",
        "discover_relationships",
        "collect_budgets",
        "health_status",
        "provider_metadata",
    }
    actual = {c.value for c in ConnectorCapability}
    assert actual == expected
    assert len(actual) == 17


# ==============================================================================
# 2. Capability Declaration and Undeclared Safety (Item 90)
# ==============================================================================


@pytest.mark.asyncio
async def test_undeclared_capability_fails_fast_and_platform_never_invokes(
    tenant_ctx: TenantContext,
):
    """Validates that invoking an undeclared capability fails fast and is never executed."""
    connector = StubConnector(
        connector_id="conn-decl-test",
        tenant_id=tenant_ctx.tenant_id,
        declared_capabilities={ConnectorCapability.HEALTH_STATUS},
    )

    assert connector.has_capability(ConnectorCapability.HEALTH_STATUS) is True
    assert connector.has_capability(ConnectorCapability.COLLECT_COST_BULK) is False

    # Direct method call raises UndeclaredCapabilityException
    with pytest.raises(UndeclaredCapabilityException) as exc_info:
        await connector.collect_cost_bulk(start_date="2026-09-01", end_date="2026-09-27")
    assert exc_info.value.capability == "collect_cost_bulk"

    # Engine invocation also guards and raises UndeclaredCapabilityException
    engine = ConnectorExecutionEngine()
    with pytest.raises(UndeclaredCapabilityException):
        await engine.execute_capability(
            tenant_context=tenant_ctx,
            connector=connector,
            capability=ConnectorCapability.COLLECT_COST_BULK,
            operation=lambda: asyncio.sleep(0.001),
        )


# ==============================================================================
# 3. Lifecycle States & Transitions (Item 91)
# ==============================================================================


def test_connector_lifecycle_state_machine_legal_transitions(tenant_ctx: TenantContext):
    """Validates legal transitions across all seven lifecycle states."""
    manager = ConnectorLifecycleManager()
    connector_id = "conn-lifecycle-01"

    # Initial state
    assert (
        manager.get_state(tenant_ctx.tenant_id, connector_id) == ConnectorLifecycleState.REGISTERED
    )

    # REGISTERED -> CREDENTIAL_BOUND
    s1 = manager.transition_state(
        tenant_ctx, connector_id, ConnectorLifecycleState.CREDENTIAL_BOUND
    )
    assert s1 == ConnectorLifecycleState.CREDENTIAL_BOUND

    # CREDENTIAL_BOUND -> VALIDATED
    s2 = manager.transition_state(tenant_ctx, connector_id, ConnectorLifecycleState.VALIDATED)
    assert s2 == ConnectorLifecycleState.VALIDATED

    # VALIDATED -> ACTIVE
    s3 = manager.transition_state(tenant_ctx, connector_id, ConnectorLifecycleState.ACTIVE)
    assert s3 == ConnectorLifecycleState.ACTIVE

    # ACTIVE -> DEGRADED
    s4 = manager.transition_state(tenant_ctx, connector_id, ConnectorLifecycleState.DEGRADED)
    assert s4 == ConnectorLifecycleState.DEGRADED

    # DEGRADED -> ACTIVE
    s5 = manager.transition_state(tenant_ctx, connector_id, ConnectorLifecycleState.ACTIVE)
    assert s5 == ConnectorLifecycleState.ACTIVE

    # ACTIVE -> SUSPENDED
    s6 = manager.transition_state(tenant_ctx, connector_id, ConnectorLifecycleState.SUSPENDED)
    assert s6 == ConnectorLifecycleState.SUSPENDED

    # SUSPENDED -> ACTIVE
    s7 = manager.transition_state(tenant_ctx, connector_id, ConnectorLifecycleState.ACTIVE)
    assert s7 == ConnectorLifecycleState.ACTIVE


def test_connector_lifecycle_illegal_transition_rejected(tenant_ctx: TenantContext):
    """Validates that illegal lifecycle state transitions are rejected with domain exception."""
    manager = ConnectorLifecycleManager()
    connector_id = "conn-lifecycle-illegal"

    # Cannot transition directly from REGISTERED to ACTIVE without credentials/validation
    with pytest.raises(InvalidConnectorStateTransitionException) as exc_info:
        manager.transition_state(tenant_ctx, connector_id, ConnectorLifecycleState.ACTIVE)
    assert exc_info.value.current_state == "REGISTERED"
    assert exc_info.value.attempted_state == "ACTIVE"


# ==============================================================================
# 4. Failure Isolation: Cost Failure Never Stops Inventory Sync (Item 91)
# ==============================================================================


@pytest.mark.asyncio
async def test_per_capability_failure_isolation_cost_never_stops_inventory(
    tenant_ctx: TenantContext,
):
    """Validates that failure in cost ingestion degrades cost but inventory continues unaffected."""
    cb_reg = CircuitBreakerRegistry()
    manager = ConnectorLifecycleManager(cb_registry=cb_reg)
    engine = ConnectorExecutionEngine(cb_registry=cb_reg, lifecycle_manager=manager)

    connector = StubConnector(
        connector_id="conn-isolation-unit",
        tenant_id=tenant_ctx.tenant_id,
        declared_capabilities={
            ConnectorCapability.HEALTH_STATUS,
            ConnectorCapability.DISCOVER_RESOURCES,
            ConnectorCapability.COLLECT_COST_BULK,
        },
    )

    manager.transition_state(
        tenant_ctx, connector.connector_id, ConnectorLifecycleState.CREDENTIAL_BOUND
    )
    manager.transition_state(tenant_ctx, connector.connector_id, ConnectorLifecycleState.VALIDATED)
    manager.transition_state(tenant_ctx, connector.connector_id, ConnectorLifecycleState.ACTIVE)

    # 1. Induce cost collection failure
    async def bad_cost() -> Any:
        raise ConnectionResetError("Provider BigQuery export timed out")

    with pytest.raises(ProviderRawErrorException):
        await engine.execute_capability(
            tenant_context=tenant_ctx,
            connector=connector,
            capability=ConnectorCapability.COLLECT_COST_BULK,
            operation=bad_cost,
            max_retries=0,
        )

    # Connector is DEGRADED, Cost capability is DEGRADED
    assert (
        manager.get_state(tenant_ctx.tenant_id, connector.connector_id)
        == ConnectorLifecycleState.DEGRADED
    )
    cost_h = manager.get_capability_health(
        tenant_ctx.tenant_id, connector.connector_id, ConnectorCapability.COLLECT_COST_BULK
    )
    assert cost_h.health == CapabilityHealth.DEGRADED

    # Inventory capability is still HEALTHY!
    inv_h = manager.get_capability_health(
        tenant_ctx.tenant_id, connector.connector_id, ConnectorCapability.DISCOVER_RESOURCES
    )
    assert inv_h.health == CapabilityHealth.HEALTHY

    # Executing inventory sync must succeed cleanly
    inv_res = await engine.execute_capability(
        tenant_context=tenant_ctx,
        connector=connector,
        capability=ConnectorCapability.DISCOVER_RESOURCES,
        operation=lambda: connector.discover_resources(scope_id="sub-01"),
    )
    assert len(inv_res) > 0


# ==============================================================================
# 5. Rate Limiting, Retry Hints, Backoff & Circuit Breaker (Item 92)
# ==============================================================================


@pytest.mark.asyncio
async def test_shared_token_bucket_rate_limiting():
    """Validates shared token bucket rate replenishment and acquisition."""
    # Rate: 10 tokens/sec, burst 2
    bucket = SharedTokenBucket(connector_id="test-bucket", rate_per_second=10.0, burst_capacity=2.0)

    # Acquire 2 burst tokens immediately
    assert bucket.try_acquire(1.0) is True
    assert bucket.try_acquire(1.0) is True
    # 3rd fails immediately without waiting
    assert bucket.try_acquire(1.0) is False

    # Async wait should replenish after ~100ms
    acquired = await bucket.acquire_async(tokens=1.0, timeout=1.0)
    assert acquired is True


def test_retry_after_parsing():
    """Validates extraction of retry hints from provider headers, strings, and dates."""
    assert parse_retry_after({"Retry-After": "12"}) == 12.0
    assert parse_retry_after({"retry-after": 5}) == 5.0
    assert parse_retry_after({"other-header": "test"}) is None
    assert parse_retry_after("Rate limit exceeded. Retry in 15 seconds") == 15.0


def test_exponential_backoff_with_full_jitter():
    """Validates exponential backoff with full jitter and retry_after priority."""
    # Explicit retry_after gets priority + jitter
    delay1 = calculate_backoff(attempt=0, base_delay=1.0, max_delay=30.0, retry_after=10.0)
    assert delay1 >= 10.1

    # Standard full jitter is bounded within [0.1, base * 2^attempt]
    delay2 = calculate_backoff(attempt=2, base_delay=1.0, max_delay=30.0)
    assert 0.1 <= delay2 <= 4.0


@pytest.mark.asyncio
async def test_per_capability_circuit_breaker():
    """Validates per-capability circuit breaker transitions: CLOSED -> OPEN -> HALF_OPEN -> CLOSED."""
    cb = CapabilityCircuitBreaker(
        connector_id="conn-cb-test",
        capability=ConnectorCapability.COLLECT_COST_BULK,
        failure_threshold=2,
        recovery_timeout_seconds=0.1,  # Fast for test
        success_threshold=1,
    )

    assert cb.state == CircuitBreakerState.CLOSED
    cb.check_permission()

    # 1st failure: still CLOSED
    cb.record_failure("Err 1")
    assert cb.state == CircuitBreakerState.CLOSED

    # 2nd failure: trips to OPEN
    cb.record_failure("Err 2")
    assert cb.state == CircuitBreakerState.OPEN

    # While OPEN, check_permission must fail fast
    with pytest.raises(CircuitBreakerOpenException):
        cb.check_permission()

    # Wait for cooldown timeout
    await asyncio.sleep(0.15)

    # State transitions to HALF_OPEN
    assert cb.state == CircuitBreakerState.HALF_OPEN
    cb.check_permission()

    # Successful probe restores CLOSED
    cb.record_success()
    assert cb.state == CircuitBreakerState.CLOSED


# ==============================================================================
# 6. Checkpointed Pagination Resumption without Duplication (Item 93)
# ==============================================================================


@pytest.mark.asyncio
async def test_checkpointed_pagination_resumption_no_duplication(tenant_ctx: TenantContext):
    """Validates that killing a worker mid-page resumes from continuation token with no duplicate records."""
    chk_store = CheckpointStore()
    engine = ConnectorExecutionEngine(chk_store=chk_store)

    connector = StubConnector(
        connector_id="conn-page-unit",
        tenant_id=tenant_ctx.tenant_id,
        declared_capabilities={ConnectorCapability.DISCOVER_RESOURCES},
    )
    job_id = "job-unit-chk-001"

    pages = [
        [{"id": "item-1"}, {"id": "item-2"}],
        [{"id": "item-3"}, {"id": "item-4"}],
    ]

    async def paged_fetch(p: PaginationParams) -> PagedResult[dict[str, Any]]:
        idx = p.page_number - 1
        if idx >= len(pages):
            return PagedResult(items=[], continuation_token=None, is_truncated=False)
        has_more = idx < len(pages) - 1
        tok = f"token-{idx + 2}" if has_more else None
        return PagedResult(items=pages[idx], continuation_token=tok, is_truncated=has_more)

    # 1. Run and simulate kill after page 1
    try:
        await engine.execute_paginated_capability(
            tenant_context=tenant_ctx,
            connector=connector,
            capability=ConnectorCapability.DISCOVER_RESOURCES,
            page_fetcher=paged_fetch,
            job_id=job_id,
            page_size=2,
            simulate_kill_after_page=1,
        )
    except InterruptedError:
        pass

    chk1 = chk_store.get_latest_checkpoint(
        tenant_ctx, job_id, ConnectorCapability.DISCOVER_RESOURCES
    )
    assert chk1 is not None
    assert chk1.page_number == 1
    assert chk1.records_ingested == 2
    assert chk1.continuation_token == "token-2"

    # 2. Second worker resumes job
    resumed = await engine.execute_paginated_capability(
        tenant_context=tenant_ctx,
        connector=connector,
        capability=ConnectorCapability.DISCOVER_RESOURCES,
        page_fetcher=paged_fetch,
        job_id=job_id,
        page_size=2,
    )

    # Resumed worker should only receive items from page 2 (item-3, item-4)
    assert len(resumed) == 2
    assert resumed[0]["id"] == "item-3"
    assert resumed[1]["id"] == "item-4"

    chk2 = chk_store.get_latest_checkpoint(
        tenant_ctx, job_id, ConnectorCapability.DISCOVER_RESOURCES
    )
    assert chk2 is not None
    assert chk2.records_ingested == 4
    assert chk2.status == "COMPLETED"


# ==============================================================================
# 7. Hourly Quota Tracking & Diagnostics (Item 94)
# ==============================================================================


def test_hourly_quota_tracking_and_diagnostics(tenant_ctx: TenantContext):
    """Validates hourly quota headroom tracking and exhaustion rejection."""
    tracker = HourlyQuotaTracker(default_hourly_limit=5)
    connector_id = "conn-quota-test"

    diag = tracker.record_request(tenant_ctx.tenant_id, connector_id, count=3)
    assert diag.requests_made == 3
    assert diag.remaining_headroom == 2
    assert diag.is_exhausted is False

    diag2 = tracker.record_request(tenant_ctx.tenant_id, connector_id, count=2)
    assert diag2.requests_made == 5
    assert diag2.remaining_headroom == 0
    assert diag2.is_exhausted is True

    # 6th request fails
    with pytest.raises(QuotaExhaustedException) as exc:
        tracker.record_request(tenant_ctx.tenant_id, connector_id, count=1)
    assert exc.value.hourly_limit == 5


# ==============================================================================
# 8. Immutable Raw Payload Landing (Item 95)
# ==============================================================================


def test_raw_payload_landing_and_immutability(tenant_ctx: TenantContext):
    """Validates raw payload landing with SHA256 and overwrite rejection."""
    storage = InMemoryTenantObjectStorage()
    service = RawLandingService(object_storage=storage)

    payload = [{"row": 1, "cost": 12.34}]
    landing = service.land_raw_payload(
        tenant_context=tenant_ctx,
        connector_id="conn-landing-01",
        run_id="run-1",
        capability=ConnectorCapability.COLLECT_COST_BULK,
        page_number=1,
        raw_payload=payload,
    )

    assert isinstance(landing, RawLandingRecord)
    assert landing.record_count == 1
    assert landing.byte_size > 0
    assert len(landing.sha256_checksum) == 64

    # Overwrite with different data is rejected
    with pytest.raises(RawLandingException):
        service.land_raw_payload(
            tenant_context=tenant_ctx,
            connector_id="conn-landing-01",
            run_id="run-1",
            capability=ConnectorCapability.COLLECT_COST_BULK,
            page_number=1,
            raw_payload=[{"row": 2, "cost": 99.99}],
        )


# ==============================================================================
# 9. API Routes End-to-End Tests
# ==============================================================================


def test_api_connector_lifecycle_and_probing_endpoints(admin_token: str):
    """Validates API endpoints for registering, probing, quota diagnostics, and state transitions."""
    headers = {"Authorization": f"Bearer {admin_token}"}

    # 1. Register Connector
    create_payload = {
        "name": "Production AWS Connector",
        "provider": "AWS",
        "declared_capabilities": ["health_status", "discover_hierarchy", "discover_resources"],
        "config": {"account_id": "123456789012"},
    }
    res = client.post("/api/v1/connectors", json=create_payload, headers=headers)
    assert res.status_code == 201, res.text
    conn_data = res.json()
    conn_id = conn_data["id"]
    assert conn_data["lifecycle_state"] == "REGISTERED"

    # 2. Get Connector
    get_res = client.get(f"/api/v1/connectors/{conn_id}", headers=headers)
    assert get_res.status_code == 200
    assert get_res.json()["name"] == "Production AWS Connector"

    # 3. Probe Capabilities
    probe_res = client.post(f"/api/v1/connectors/{conn_id}/probe", headers=headers)
    assert probe_res.status_code == 200, probe_res.text
    profile = probe_res.json()
    assert "health_status" in profile["verified_capabilities"]

    # 4. Check Quota Diagnostics
    quota_res = client.get(f"/api/v1/connectors/{conn_id}/diagnostics/quota", headers=headers)
    assert quota_res.status_code == 200
    assert "hourly_limit" in quota_res.json()

    # 5. Transition to ACTIVE via legal lifecycle progression
    client.post(
        f"/api/v1/connectors/{conn_id}/transition",
        json={"target_state": "CREDENTIAL_BOUND", "reason": "Credentials attached"},
        headers=headers,
    )
    client.post(
        f"/api/v1/connectors/{conn_id}/transition",
        json={"target_state": "VALIDATED", "reason": "Preflight passed"},
        headers=headers,
    )
    trans_res = client.post(
        f"/api/v1/connectors/{conn_id}/transition",
        json={"target_state": "ACTIVE", "reason": "Operational activation"},
        headers=headers,
    )
    assert trans_res.status_code == 200
    assert trans_res.json()["lifecycle_state"] == "ACTIVE"
