"""Real-Database Session & Token Revocation Restart Tests (Prompt P04).

Enforces:
- Revoked session remains revoked after fresh repository instantiation (simulating process restart).
- Revoked token JTI remains revoked after restart.
- Revocation registry and token families survive process restarts.
"""

import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from domain.identity.models import Session, User
from domain.identity.repository import SqlIdentityRepository
from domain.models.enums import AuthMethod, UserStatus

pytestmark = [pytest.mark.realdb]


@pytest.mark.asyncio
async def test_session_revocation_survives_process_restart():
    """Proves that revoked sessions remain revoked across independent repository instances."""
    tenant_id = f"ten-{uuid.uuid4().hex[:8]}"
    user_id = f"usr-{uuid.uuid4().hex[:12]}"
    session_id = f"sess-{uuid.uuid4().hex[:12]}"
    family_id = f"fam-{uuid.uuid4().hex[:12]}"
    now = datetime.now(UTC)

    # 1. Process A: Save user and active session using instance A
    repo_a = SqlIdentityRepository()
    user = User(
        id=user_id,
        tenant_id=tenant_id,
        email="restart-test@cloudlens.internal",
        display_name="Restart Test User",
        status=UserStatus.ACTIVE,
        roles=[],
        auth_method=AuthMethod.OIDC,
        is_break_glass=False,
        created_at=now,
        updated_at=now,
    )
    await repo_a.save_user(user)

    session_entity = Session(
        id=session_id,
        session_id=session_id,
        tenant_id=tenant_id,
        user_id=user_id,
        token_family_id=family_id,
        created_at=now,
        expires_at=now + timedelta(hours=1),
        last_activity_at=now,
        is_active=True,
    )
    await repo_a.save_session(session_entity)

    # Verify session is initially active
    saved_sess = await repo_a.get_session(session_id)
    assert saved_sess is not None
    assert saved_sess.is_active is True

    # 2. Process A: Revoke the session
    revoked = await repo_a.revoke_session(session_id, reason="SECURITY_LOGOUT")
    assert revoked is True

    # 3. Process B: Discard repo_a and instantiate fresh repo_b (simulating process restart)
    del repo_a
    repo_b = SqlIdentityRepository()

    # Verify session is still revoked in repo_b
    reloaded_sess = await repo_b.get_session(session_id)
    assert reloaded_sess is not None
    assert reloaded_sess.is_active is False
    assert reloaded_sess.revoked_at is not None
    assert reloaded_sess.revocation_reason == "SECURITY_LOGOUT"


@pytest.mark.asyncio
async def test_token_revocation_survives_process_restart():
    """Proves that revoked JTI and token family compromise survive process restarts."""
    jti = f"jti-{uuid.uuid4().hex[:16]}"
    family_id = f"fam-{uuid.uuid4().hex[:12]}"
    expires_at = time.time() + 3600

    # 1. Process A: Revoke token JTI and mark family compromised
    repo_a = SqlIdentityRepository()
    await repo_a.revoke_token(jti, expires_at=expires_at)

    # Record token usage in family
    is_valid = await repo_a.record_refresh_token_use("tok-1", family_id)
    assert is_valid is True

    # Replaying tok-1 should detect reuse and mark family compromised
    is_replay_valid = await repo_a.record_refresh_token_use("tok-1", family_id)
    assert is_replay_valid is False

    # 2. Process B: Instantiate fresh repo_b (simulating process restart)
    del repo_a
    repo_b = SqlIdentityRepository()

    # Verify JTI is revoked in repo_b
    is_revoked = await repo_b.is_token_revoked(jti=jti)
    assert is_revoked is True

    # Verify token family is compromised in repo_b
    is_family_revoked = await repo_b.is_token_revoked(jti="any-new-jti", family_id=family_id)
    assert is_family_revoked is True
