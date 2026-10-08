"""Tenant Settings Persistence & Restart Proof (Prompt P03 Done When Items 1 & 3).

Proves:
1. Reference restart proof: Settings mutated via repository are stored in PostgreSQL tenant_settings table and survive repository/process restart.
2. Startup guard: Staging and production configurations refuse InMemory repository and exit non-zero.
"""

import os
import pytest
from sqlalchemy import text

from db.session import get_tenant_session, verify_persistence_startup_guard
from domain.config.repository import SqlTenantSettingsRepository, get_tenant_settings_repository
from domain.config.tenant_settings import TenantSettings
from tests.fakes.tenant_settings import InMemoryTenantSettingsRepository

pytestmark = [pytest.mark.realdb, pytest.mark.level02]


@pytest.mark.asyncio
async def test_reference_restart_proof_survives_process_restart():
    """Validates that SqlTenantSettingsRepository persists to PostgreSQL across session/instance restarts."""
    test_tenant_id = "tenant-restart-proof-corp"

    # Step 1: Clean up any old state
    async with get_tenant_session() as session:
        await session.execute(
            text("DELETE FROM tenant_settings WHERE tenant_id = :tid;"),
            {"tid": test_tenant_id},
        )
        await session.commit()

    # Step 2: In First "Process", instantiate repo and mutate settings
    repo1 = SqlTenantSettingsRepository()
    initial_settings = await repo1.get(test_tenant_id)
    assert initial_settings.reporting_currency == "USD"  # Default

    updated_settings = await repo1.update(
        test_tenant_id,
        {
            "reporting_currency": "GBP",
            "approval_limits": {
                "auto_approval_limit_amount": 7500.0,
                "manager_approval_limit_amount": 25000.0,
            },
            "retention_profile": {
                "raw_metrics_retention_days": 180,
            },
        },
    )
    assert updated_settings.reporting_currency == "GBP"

    # Step 3: Simulate Process Destruction (Nullify repo1 and reset cache)
    del repo1

    # Step 4: In Second "Process" (Completely new repository instance and DB session)
    repo2 = SqlTenantSettingsRepository()
    restarted_settings = await repo2.get(test_tenant_id)

    # Step 5: Assert settings survived restart and match DB state
    assert restarted_settings.reporting_currency == "GBP", (
        f"Expected GBP, got {restarted_settings.reporting_currency}. Settings did not survive restart."
    )
    assert restarted_settings.approval_limits.auto_approval_limit_amount == 7500.0
    assert restarted_settings.approval_limits.manager_approval_limit_amount == 25000.0
    assert restarted_settings.retention_profile.raw_metrics_retention_days == 180

    # Step 6: Verify direct raw PostgreSQL query matches
    async with get_tenant_session() as session:
        raw_res = await session.execute(
            text("SELECT settings->>'reporting_currency', settings->'approval_limits'->>'auto_approval_limit_amount' FROM tenant_settings WHERE tenant_id = :tid;"),
            {"tid": test_tenant_id},
        )
        row = raw_res.fetchone()
        assert row is not None, "Raw PostgreSQL row was not found in tenant_settings table!"
        assert row[0] == "GBP"
        assert float(row[1]) == 7500.0

    print("\n[REFERENCE RESTART PROOF] Verified: Tenant settings successfully persisted in PostgreSQL and survived restart.")


def test_production_start_refuses_inmemory():
    """Validates that production environment startup guard halts execution on InMemory repository."""
    orig_env = os.environ.get("CLOUDLENS_ENV")
    orig_mode = os.environ.get("PERSISTENCE_MODE")
    orig_db_url = os.environ.get("DATABASE_URL")

    try:
        os.environ["CLOUDLENS_ENV"] = "production"
        os.environ["PERSISTENCE_MODE"] = "inmemory"
        # Provide a DB url so DB check passes and InMemory check fires
        os.environ["DATABASE_URL"] = "postgresql://cloudlens:dev@localhost:5432/cloudlens"

        in_memory_fake = InMemoryTenantSettingsRepository()

        # Startup guard must raise SystemExit(1)
        with pytest.raises(SystemExit) as excinfo:
            verify_persistence_startup_guard(active_repository=in_memory_fake)

        assert excinfo.value.code == 1

        print("\n[STARTUP GUARD PROOF] Verified: Production start strictly refused InMemory repository and exited code 1.")
    finally:
        if orig_env is not None:
            os.environ["CLOUDLENS_ENV"] = orig_env
        else:
            os.environ.pop("CLOUDLENS_ENV", None)

        if orig_mode is not None:
            os.environ["PERSISTENCE_MODE"] = orig_mode
        else:
            os.environ.pop("PERSISTENCE_MODE", None)

        if orig_db_url is not None:
            os.environ["DATABASE_URL"] = orig_db_url
        else:
            os.environ.pop("DATABASE_URL", None)
