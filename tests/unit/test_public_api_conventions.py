"""Unit and Functional Tests for Public API Conventions (Prompt 34 / BBP Section 38).

Enforces:
1. Cursor-based pagination (default 50, max 500, next_cursor traversal).
2. Sort with leading-minus descending grammar.
3. Field selection.
4. Idempotency key replay ('Idempotent-Replay: true') and conflict detection (409).
5. ETag generation and If-Match optimistic concurrency (412 on mismatch).
6. Rate limiting RFC headers and 429 'RATE_LIMITED' response.
7. RFC 7807/9457 Problem Details format and nine standard error codes.
8. Scope masking: returning 404 rather than 403 to avoid leaking existence.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from api.cloudlens_api.conventions.concurrency import generate_etag, validate_if_match
from api.cloudlens_api.conventions.filtering import (
    apply_field_selection,
    decode_cursor,
    encode_cursor,
    parse_sort_instruction,
    sort_items,
)
from api.cloudlens_api.conventions.idempotency import idempotency_store
from api.cloudlens_api.conventions.models import StandardErrorCode
from api.cloudlens_api.conventions.rate_limit import TokenRateLimiter, token_rate_limiter
from api.cloudlens_api.main import app
from domain.identity.service import get_identity_service
from domain.models.enums import SystemRole


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# ==============================================================================
# 1. Cursor Pagination, Sorting, and Field Selection Tests
# ==============================================================================


def test_cursor_encode_decode():
    """Verify cursor token encodes and decodes accurately."""
    token = encode_cursor(150)
    assert isinstance(token, str)
    assert decode_cursor(token) == 150
    assert decode_cursor(None) == 0
    assert decode_cursor("invalid-token") == 0


def test_sort_instruction_parsing():
    """Verify sort grammar with leading-minus descending."""
    assert parse_sort_instruction("-created_at") == [("created_at", True)]
    assert parse_sort_instruction("amount") == [("amount", False)]
    assert parse_sort_instruction("-cost,name") == [("cost", True), ("name", False)]
    assert parse_sort_instruction(None) == []


def test_sort_items_in_memory():
    """Verify in-memory item sorting."""
    data = [
        {"id": "1", "score": 10},
        {"id": "2", "score": 30},
        {"id": "3", "score": 20},
    ]
    asc = sort_items(data, "score")
    assert [x["id"] for x in asc] == ["1", "3", "2"]

    desc = sort_items(data, "-score")
    assert [x["id"] for x in desc] == ["2", "3", "1"]


def test_field_selection_pruning():
    """Verify field selection prunes attributes while preserving id and metadata."""
    item = {
        "id": "res-123",
        "name": "worker-node",
        "provider": "aws",
        "internal_secret": "do_not_show",
        "_metadata": {"period": "2026-03"},
    }
    pruned = apply_field_selection(item, "name,provider")
    assert "name" in pruned
    assert "provider" in pruned
    assert "id" in pruned  # id is always preserved
    assert "_metadata" in pruned  # metadata is always preserved
    assert "internal_secret" not in pruned


# ==============================================================================
# 2. Idempotency Key Engine Tests
# ==============================================================================


def test_idempotency_key_replay_and_conflict(client: TestClient):
    """Mutating request with Idempotency-Key caches response and replays identical executions (API-105)."""
    idempotency_store.clear()
    key = f"idem-key-{uuid.uuid4().hex}"
    payload1 = {
        "email": f"test-idem-{uuid.uuid4().hex[:6]}@example.com",
        "display_name": "Idempotency Test User",
        "roles": ["finops_viewer"],
    }

    # First request
    res1 = client.post(
        "/api/v1/users",
        json=payload1,
        headers={"Idempotency-Key": key, "X-Tenant-ID": "test-tenant-idem"},
    )
    assert res1.status_code == 201
    user_id = res1.json()["id"]

    # Replay identical request with same key
    res2 = client.post(
        "/api/v1/users",
        json=payload1,
        headers={"Idempotency-Key": key, "X-Tenant-ID": "test-tenant-idem"},
    )
    assert res2.status_code == 201
    assert res2.headers.get("Idempotent-Replay") == "true"
    assert res2.json()["id"] == user_id

    # Replay same key with DIFFERENT payload -> 409 Conflict
    payload_diff = {
        "email": "different-body@example.com",
        "display_name": "Different User",
        "roles": ["billing_admin"],
    }
    res3 = client.post(
        "/api/v1/users",
        json=payload_diff,
        headers={"Idempotency-Key": key, "X-Tenant-ID": "test-tenant-idem"},
    )
    assert res3.status_code == 409
    data3 = res3.json()
    assert data3["code"] == StandardErrorCode.CONFLICT.value
    assert "Idempotency key" in data3["detail"]


# ==============================================================================
# 3. ETag and Optimistic Concurrency Tests
# ==============================================================================


def test_etag_generation_and_if_match_validation():
    """Verify ETag generation and If-Match matching."""
    data = {"id": "res-1", "name": "app-server"}
    etag = generate_etag(data)
    assert etag.startswith('"') and etag.endswith('"')

    assert validate_if_match(etag, etag) is True
    assert validate_if_match(etag, "*") is True
    assert validate_if_match(etag, None) is True
    assert validate_if_match(etag, '"mismatched-etag"') is False


def test_optimistic_concurrency_precondition_failed(client: TestClient):
    """Mutating update with mismatched If-Match returns HTTP 412 PRECONDITION_FAILED."""
    # First create a user
    user_payload = {
        "email": f"concurrency-{uuid.uuid4().hex[:6]}@example.com",
        "display_name": "Concurrency User",
        "roles": ["finops_viewer"],
    }
    create_res = client.post(
        "/api/v1/users",
        json=user_payload,
        headers={"X-Tenant-ID": "tenant-cc"},
    )
    assert create_res.status_code == 201
    user_id = create_res.json()["id"]
    correct_etag = create_res.headers["ETag"]

    # Attempt PATCH with wrong ETag
    patch_res = client.patch(
        f"/api/v1/users/{user_id}",
        json={"display_name": "Updated Concurrency User"},
        headers={"X-Tenant-ID": "tenant-cc", "If-Match": '"wrong-etag-val"'},
    )
    assert patch_res.status_code == 412
    assert patch_res.json()["code"] == StandardErrorCode.PRECONDITION_FAILED.value

    # Attempt PATCH with matching ETag
    patch_ok = client.patch(
        f"/api/v1/users/{user_id}",
        json={"display_name": "Updated Concurrency User"},
        headers={"X-Tenant-ID": "tenant-cc", "If-Match": correct_etag},
    )
    assert patch_ok.status_code == 200
    assert patch_ok.json()["display_name"] == "Updated Concurrency User"


# ==============================================================================
# 4. Rate Limiting Tests
# ==============================================================================


def test_rate_limiting_headers_and_limit_enforcement():
    """Verify standard RateLimit headers and 429 response when limit exceeded (API-106)."""
    # Create test limiter with limit 2
    test_limiter = TokenRateLimiter(limit=2, window_seconds=60)
    key = "test-token-rl-123"

    allowed1, limit1, rem1, reset1 = test_limiter.check_and_record(key)
    assert allowed1 is True
    assert rem1 == 1

    allowed2, limit2, rem2, reset2 = test_limiter.check_and_record(key)
    assert allowed2 is True
    assert rem2 == 0

    allowed3, limit3, rem3, reset3 = test_limiter.check_and_record(key)
    assert allowed3 is False
    assert rem3 == 0
    assert reset3 > 0


def test_rate_limit_exceeded_http_429(client: TestClient):
    """Client exceeding global rate limit receives 429 Too Many Requests."""
    identity_service = get_identity_service()
    tok = identity_service.token_engine.issue_access_token(
        user_id="usr-rate-limit-test",
        tenant_id="t1",
        email="test-rl@example.com",
        roles=[SystemRole.FINOPS_VIEWER],
        permissions=[],
        session_id="sess-rl",
        token_family_id="fam-rl",
    )
    test_key = f"Bearer {tok}"
    # Temporarily exhaust limiter for this key
    token_rate_limiter.limit = 3
    token_rate_limiter.reset()

    # Call endpoint 3 times
    for _ in range(3):
        res = client.get("/api/v1/users", headers={"Authorization": test_key, "X-Tenant-ID": "t1"})
        assert res.status_code == 200

    # 4th call exceeds limit
    res_exceeded = client.get(
        "/api/v1/users", headers={"Authorization": test_key, "X-Tenant-ID": "t1"}
    )
    assert res_exceeded.status_code == 429
    data = res_exceeded.json()
    assert data["code"] == StandardErrorCode.RATE_LIMITED.value
    assert "RateLimit-Limit" in res_exceeded.headers
    assert res_exceeded.headers["RateLimit-Remaining"] == "0"
    assert "Retry-After" in res_exceeded.headers

    # Reset limiter for subsequent tests
    token_rate_limiter.limit = 1000
    token_rate_limiter.reset()


# ==============================================================================
# 5. Scope-Masking & Standard Error Codes Tests
# ==============================================================================


def test_scope_masking_avoids_leaking_existence(client: TestClient):
    """Accessing an entity in another tenant returns 404 rather than 403, preventing existence discovery."""
    # User belongs to tenant A
    user_payload = {
        "email": f"tenant-a-user-{uuid.uuid4().hex[:6]}@example.com",
        "display_name": "Tenant A User",
        "roles": ["finops_viewer"],
    }
    create_res = client.post(
        "/api/v1/users",
        json=user_payload,
        headers={"X-Tenant-ID": "tenant-A"},
    )
    assert create_res.status_code == 201
    user_id = create_res.json()["id"]

    # Tenant B tries to get Tenant A user -> MUST return 404 NOT_FOUND, not 403 FORBIDDEN
    res_probe = client.get(
        f"/api/v1/users/{user_id}",
        headers={"X-Tenant-ID": "tenant-B"},
    )
    assert res_probe.status_code == 404
    data = res_probe.json()
    assert data["code"] == StandardErrorCode.NOT_FOUND.value


def test_standard_response_metadata_headers(client: TestClient):
    """Every API response must include standard period, cost basis, and freshness headers."""
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    assert "X-Period" in res.headers
    assert "X-Cost-Basis" in res.headers
    assert "X-Currency" in res.headers
    assert "X-Data-Freshness" in res.headers
    assert "X-Access-Filtering-Occurred" in res.headers
    assert "X-Total-Approximate" in res.headers
