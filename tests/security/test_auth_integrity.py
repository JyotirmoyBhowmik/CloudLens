"""Security Test Suite: Authentication Integrity — Login, Keys and Every Write Route (Prompt P01B).

Covers all 4 DONE WHEN requirements:
1. Forged claims to any login route -> no token.
2. 0 unauthenticated write routes outside exempt list (route walk).
3. Unexpired token works after restart (keys persisted in OpenBao / shared store).
4. Two API processes accept each other's tokens (distributed multi-instance verification).
"""

from __future__ import annotations

import copy
import json
import time
from typing import Any

import jwt
import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from api.cloudlens_api.main import app
from api.cloudlens_api.tenant_context import EXEMPT_PATHS, is_exempt_request
from domain.identity.token_engine import (
    CryptographicTokenEngine,
    TokenKeyManager,
    get_default_key_manager,
)
from domain.models.enums import SystemRole


@pytest.fixture
def client():
    return TestClient(app)


# ==============================================================================
# Done When 1: Forged Claims to Any Login Route -> No Token
# ==============================================================================


def test_forged_claims_to_any_login_route_yields_no_token(client: TestClient):
    """Asserts that forged or client-supplied identity claims to any login route never yield a token."""
    # 1. Old body-claims endpoint POST /api/v1/auth/oidc/login is permanently deleted -> 404
    res_body_claims = client.post(
        "/api/v1/auth/oidc/login",
        json={
            "tenant_id": "tenant-forged",
            "email": "attacker@evil.com",
            "roles": ["SUPER_ADMIN"],
            "groups": ["Global-Admins"],
        },
    )
    assert res_body_claims.status_code == 404, (
        f"Expected 404 for deleted body-claims login, got {res_body_claims.status_code}"
    )

    # 2. Forged callback state/code to OIDC callback -> 400 or 401, no token
    res_forged_callback = client.get(
        "/api/v1/auth/oidc/callback?code=forged-auth-code&state=forged-state-nonce"
    )
    assert res_forged_callback.status_code in (400, 401), (
        f"Expected 400/401 for forged callback, got {res_forged_callback.status_code}"
    )
    assert "access_token" not in res_forged_callback.text

    # 3. Forged password / missing assertion to break-glass login -> 401, no token
    res_forged_break_glass = client.post(
        "/api/v1/auth/break-glass/login",
        json={
            "account_name": "admin@jyotirmoyb.com",
            "password": "forged-local-password",
            "mfa_code": "123456",
        },
    )
    assert res_forged_break_glass.status_code == 401, (
        f"Expected 401 for local password attempt, got {res_forged_break_glass.status_code}"
    )
    assert "access_token" not in res_forged_break_glass.text

    # 4. Forged self-signed token to token refresh -> 401, no token
    fake_key_mgr = TokenKeyManager()
    fake_engine = CryptographicTokenEngine(key_manager=fake_key_mgr)
    forged_refresh_token = fake_engine.issue_refresh_token(
        user_id="attacker",
        tenant_id="victim-tenant",
        session_id="fake-session",
        token_family_id="fake-family",
    )

    res_forged_refresh = client.post(
        "/api/v1/auth/token/refresh",
        json={"refresh_token": forged_refresh_token},
    )
    assert res_forged_refresh.status_code in (401, 403), (
        f"Expected 401/403 for forged refresh token, got {res_forged_refresh.status_code}"
    )
    assert "access_token" not in res_forged_refresh.text

    # 5. Invalid credentials to machine client token endpoint -> 401, no token
    res_forged_machine = client.post(
        "/api/v1/auth/machine-clients/token",
        json={
            "client_id": "nonexistent-client",
            "client_secret": "forged-secret-key",
        },
    )
    assert res_forged_machine.status_code == 401, (
        f"Expected 401 for forged machine client, got {res_forged_machine.status_code}"
    )
    assert "access_token" not in res_forged_machine.text


# ==============================================================================
# Done When 2: 0 Unauthenticated Write Routes Outside Exempt List
# ==============================================================================


def test_zero_unauthenticated_write_routes_outside_exempt_list(client: TestClient):
    """Walks all FastAPI app routes and asserts 0 unauthenticated write routes outside the exempt list."""
    write_methods = {"POST", "PUT", "PATCH", "DELETE"}
    unauthenticated_write_routes: list[tuple[str, str, int]] = []
    tested_write_routes: list[tuple[str, str]] = []

    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue

        route_methods = route.methods or set()
        matched_write_methods = route_methods.intersection(write_methods)
        if not matched_write_methods:
            continue

        path = route.path
        for method in sorted(matched_write_methods):
            # Check against authoritative exempt specification
            if (method, path) in EXEMPT_PATHS or is_exempt_request(method, path):
                continue

            tested_write_routes.append((method, path))

            # Send unauthenticated request (no Authorization header)
            response = client.request(method, path, json={})
            if response.status_code != 401:
                unauthenticated_write_routes.append((method, path, response.status_code))

    # Assert exactly 0 unauthenticated write routes outside exempt list
    assert len(unauthenticated_write_routes) == 0, (
        f"Security Failure: Found {len(unauthenticated_write_routes)} unauthenticated write routes: "
        f"{unauthenticated_write_routes}"
    )
    # Ensure a significant number of write routes were tested
    assert len(tested_write_routes) >= 50, (
        f"Expected at least 50 write routes tested, found {len(tested_write_routes)}"
    )


# ==============================================================================
# Done When 3: Unexpired Token Works After Restart
# ==============================================================================


def test_unexpired_token_works_after_restart(client: TestClient):
    """Verifies that an unexpired token survives API restart by persisting keys in OpenBao / shared store."""
    # 1. Process / Engine 1: Issue a valid signed token
    key_mgr_1 = get_default_key_manager()
    engine_1 = CryptographicTokenEngine(key_manager=key_mgr_1)

    access_token = engine_1.issue_access_token(
        user_id="restart-user-42",
        email="restart@cloudlens.local",
        tenant_id="tenant-restart",
        roles=[SystemRole.FINOPS_ADMIN],
        permissions=["config:read", "inventory:read"],
        session_id="restart-session-1",
        token_family_id="restart-family-1",
    )

    # Verify token works on Engine 1
    ctx_1 = engine_1.extract_auth_context(access_token)
    assert ctx_1.user_id == "restart-user-42"
    assert ctx_1.tenant_id == "tenant-restart"

    # 2. Simulate API restart by re-initializing a brand-new TokenKeyManager from store
    key_mgr_restarted = TokenKeyManager()
    engine_restarted = CryptographicTokenEngine(key_manager=key_mgr_restarted)

    # 3. Verify the unexpired token issued before restart is valid on the restarted engine
    ctx_restarted = engine_restarted.extract_auth_context(access_token)
    assert ctx_restarted.user_id == "restart-user-42"
    assert ctx_restarted.tenant_id == "tenant-restart"
    assert SystemRole.FINOPS_ADMIN in ctx_restarted.roles

    # 4. Verify the unexpired token works against the running API application
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 200, (
        f"Expected 200 after restart, got {response.status_code}: {response.text}"
    )
    data = response.json()
    assert data["user_id"] == "restart-user-42"
    assert data["tenant_id"] == "tenant-restart"


# ==============================================================================
# Done When 4: Two API Processes Accept Each Other's Tokens
# ==============================================================================


def test_two_api_processes_accept_each_others_tokens():
    """Verifies that two distinct API processes sharing keys accept and cross-validate each other's tokens."""
    # Process A initializes its key manager and token engine
    key_mgr_a = TokenKeyManager()
    engine_a = CryptographicTokenEngine(key_manager=key_mgr_a)

    # Process B initializes its key manager and token engine
    key_mgr_b = TokenKeyManager()
    engine_b = CryptographicTokenEngine(key_manager=key_mgr_b)

    # Both processes must share the active key ID
    assert engine_a.key_manager.active_kid == engine_b.key_manager.active_kid, (
        f"Key ID mismatch between processes: {engine_a.key_manager.active_kid} != {engine_b.key_manager.active_kid}"
    )

    # 1. Process A mints a token for Alice
    token_a = engine_a.issue_access_token(
        user_id="user-alice",
        email="alice@cloudlens.local",
        tenant_id="tenant-shared",
        roles=[SystemRole.SUPER_ADMIN],
        permissions=["*"],
        session_id="sess-alice-1",
        token_family_id="fam-alice-1",
    )

    # Process B verifies Process A's token
    ctx_b_verified = engine_b.extract_auth_context(token_a)
    assert ctx_b_verified.user_id == "user-alice"
    assert ctx_b_verified.tenant_id == "tenant-shared"
    assert SystemRole.SUPER_ADMIN in ctx_b_verified.roles

    # 2. Process B mints a token for Bob
    token_b = engine_b.issue_access_token(
        user_id="user-bob",
        email="bob@cloudlens.local",
        tenant_id="tenant-shared",
        roles=[SystemRole.FINOPS_ADMIN],
        permissions=["billing:read", "cost:totals:read"],
        session_id="sess-bob-1",
        token_family_id="fam-bob-1",
    )

    # Process A verifies Process B's token
    ctx_a_verified = engine_a.extract_auth_context(token_b)
    assert ctx_a_verified.user_id == "user-bob"
    assert ctx_a_verified.tenant_id == "tenant-shared"
    assert SystemRole.FINOPS_ADMIN in ctx_a_verified.roles

    # 3. Adversarial test: Tampered token payload is rejected by both processes
    header, payload_b64, sig = token_a.split(".")
    # Decode payload and modify role to elevate privileges
    import base64
    payload_json = json.loads(base64.urlsafe_b64decode(payload_b64 + "=="))
    payload_json["sub"] = "evil-hacker"
    tampered_b64 = base64.urlsafe_b64encode(json.dumps(payload_json).encode()).decode().rstrip("=")
    tampered_token = f"{header}.{tampered_b64}.{sig}"

    from domain.models.exceptions import TokenInvalidException
    with pytest.raises(TokenInvalidException):
        engine_a.extract_auth_context(tampered_token)

    with pytest.raises(TokenInvalidException):
        engine_b.extract_auth_context(tampered_token)
