"""Real-Database Integration Test: Wizard Resumes After Restart (Prompt P05).

Enforces:
- Pattern P1/P4: PostgreSQL authoritative persistence with tenant RLS isolation.
- Wizard session survives process restart:
  1. Process A writes a wizard session with partial progress and state.
  2. Process A is terminated/discarded.
  3. Process B loads the session from the database; state and current step are fully restored.
  4. Process B advances the wizard step and persists.
  5. Process C confirms resumption and forward transition across another restart.
"""

import uuid
from datetime import UTC, datetime

import pytest

from domain.models.enums import ProviderType, WizardStep
from domain.tenant.context import TenantContext
from domain.tenant.models import Tenant
from domain.tenant.repository import SqlTenantRepository
from domain.wizard.models import WizardSession
from domain.wizard.repository import SqlWizardRepository

pytestmark = [pytest.mark.realdb]


@pytest.mark.asyncio
async def test_wizard_resumes_after_restart():
    """Verify that onboarding wizard sessions reliably resume after process restarts."""
    tenant_id = f"ten-{uuid.uuid4().hex[:12]}"
    user_id = f"usr-{uuid.uuid4().hex[:12]}"
    now = datetime.now(UTC)

    # 1. Setup tenant
    tenant_repo = SqlTenantRepository()
    tenant = Tenant(
        id=tenant_id,
        name=f"Wizard Tenant {tenant_id}",
        reporting_currency="USD",
        created_at=now,
        updated_at=now,
    )
    await tenant_repo.save(tenant)
    ctx = TenantContext(tenant_id=tenant_id, user_id=user_id)

    session_id = f"wiz-{uuid.uuid4().hex[:12]}"
    initial_draft_data = {
        "account_id": "123456789012",
        "role_arn": "arn:aws:iam::123456789012:role/CloudLensRole",
        "external_id": "ext-secret-12345",
        "regions": ["us-east-1", "us-west-2"],
    }

    # -------------------------------------------------------------------------
    # PROCESS A: Start wizard, complete SELECT_PROVIDER, now on ENTER_CREDENTIALS
    # -------------------------------------------------------------------------
    repo_a = SqlWizardRepository()
    session_a = WizardSession(
        id=session_id,
        tenant_id=tenant_id,
        user_id=user_id,
        provider=ProviderType.AWS,
        connection_method="ROLE_DELEGATION",
        current_step=WizardStep.ENTER_CREDENTIALS,
        completed_steps=[WizardStep.SELECT_PROVIDER],
        wizard_data=initial_draft_data,
        selected_scopes=["scope-1", "scope-2"],
        include_future_scopes=True,
        status="IN_PROGRESS",
        created_at=now,
        updated_at=now,
    )
    saved_a = await repo_a.save_async(session_a, tenant_context=ctx)
    assert saved_a.id == session_id

    # Simulate crash / process restart: discard Process A completely
    del repo_a
    del session_a

    # -------------------------------------------------------------------------
    # PROCESS B: Restarted process resumes the exact active session
    # -------------------------------------------------------------------------
    repo_b = SqlWizardRepository()

    # Verify lookup by ID survives restart
    resumed_b = await repo_b.get_async(session_id, tenant_context=ctx)
    assert resumed_b is not None
    assert resumed_b.id == session_id
    assert resumed_b.tenant_id == tenant_id
    assert resumed_b.user_id == user_id
    assert resumed_b.provider == ProviderType.AWS
    assert resumed_b.connection_method == "ROLE_DELEGATION"
    assert resumed_b.current_step == WizardStep.ENTER_CREDENTIALS
    assert resumed_b.completed_steps == [WizardStep.SELECT_PROVIDER]
    assert resumed_b.wizard_data["account_id"] == "123456789012"
    assert resumed_b.wizard_data["role_arn"] == "arn:aws:iam::123456789012:role/CloudLensRole"
    assert resumed_b.selected_scopes == ["scope-1", "scope-2"]
    assert resumed_b.include_future_scopes is True
    assert resumed_b.status == "IN_PROGRESS"

    # Verify active session for user survives restart
    active_b = await repo_b.get_active_for_user_async(user_id, tenant_context=ctx)
    assert active_b is not None
    assert active_b.id == session_id

    # Advance wizard to VALIDATE_CREDENTIALS in Process B
    resumed_b.current_step = WizardStep.VALIDATE_CREDENTIALS
    resumed_b.completed_steps = [WizardStep.SELECT_PROVIDER, WizardStep.ENTER_CREDENTIALS]
    resumed_b.wizard_data["credentials_validated"] = True
    await repo_b.save_async(resumed_b, tenant_context=ctx)

    # Simulate another crash / process restart: discard Process B
    del repo_b
    del resumed_b
    del active_b

    # -------------------------------------------------------------------------
    # PROCESS C: Fresh process confirms state advancement persisted
    # -------------------------------------------------------------------------
    repo_c = SqlWizardRepository()
    final_c = await repo_c.get_async(session_id, tenant_context=ctx)
    assert final_c is not None
    assert final_c.current_step == WizardStep.VALIDATE_CREDENTIALS
    assert final_c.completed_steps == [WizardStep.SELECT_PROVIDER, WizardStep.ENTER_CREDENTIALS]
    assert final_c.wizard_data["credentials_validated"] is True
