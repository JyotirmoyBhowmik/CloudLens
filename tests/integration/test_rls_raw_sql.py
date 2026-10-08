"""Raw-SQL Row-Level Security Isolation Proof (Prompt P03 Done When Item 2).

Proves:
1. Under application role (cloudlens_app: non-owner, non-bypassrls), RLS policies are strictly enforced.
2. When app.current_tenant_id is set to 'tenant-A', queries cannot read 'tenant-B' data.
3. When app.current_tenant_id is set to 'tenant-B', queries cannot read 'tenant-A' data.
4. When app.current_tenant_id is unconfigured or empty, queries return 0 rows.
"""

import asyncio
import json
import pytest
from sqlalchemy import text
from db.session import get_tenant_session

pytestmark = [pytest.mark.realdb, pytest.mark.level02]


@pytest.mark.asyncio
async def test_rls_raw_sql_tenant_a_cannot_read_b():
    """Validates raw SQL RLS isolation between tenant A and tenant B."""
    tenant_a = "tenant-proof-alpha"
    tenant_b = "tenant-proof-beta"

    # Seed data using elevated superuser session
    async with get_tenant_session() as session:
        # Clear any existing proof rows
        await session.execute(
            text("DELETE FROM tenant_settings WHERE tenant_id IN (:ta, :tb);"),
            {"ta": tenant_a, "tb": tenant_b},
        )
        # Insert raw rows for tenant A and tenant B
        await session.execute(
            text("""
                INSERT INTO tenant_settings (tenant_id, settings, updated_at)
                VALUES
                    (:ta, CAST(:settings_a AS jsonb), NOW()),
                    (:tb, CAST(:settings_b AS jsonb), NOW());
            """),
            {
                "ta": tenant_a,
                "settings_a": json.dumps({"tenant_id": tenant_a, "reporting_currency": "USD"}),
                "tb": tenant_b,
                "settings_b": json.dumps({"tenant_id": tenant_b, "reporting_currency": "EUR"}),
            },
        )
        await session.commit()

    # TEST EXECUTION UNDER CLOUDLENS_APP ROLE (Non-owner, Non-BYPASSRLS)
    async with get_tenant_session() as session:
        # 1. Assume app role
        await session.execute(text("SET ROLE cloudlens_app;"))

        # 2. SET LOCAL app.current_tenant_id = tenant-A
        await session.execute(
            text("SELECT set_config('app.current_tenant_id', :tid, true);"),
            {"tid": tenant_a},
        )

        res_a = await session.execute(
            text("SELECT tenant_id, settings->>'reporting_currency' FROM tenant_settings ORDER BY tenant_id;")
        )
        rows_a = res_a.fetchall()

        # Tenant A can only see tenant A's row; tenant B is invisible
        assert len(rows_a) == 1, f"Expected exactly 1 row for tenant A, got {len(rows_a)}"
        assert rows_a[0][0] == tenant_a
        assert rows_a[0][1] == "USD"

        # 3. SET LOCAL app.current_tenant_id = tenant-B
        await session.execute(
            text("SELECT set_config('app.current_tenant_id', :tid, true);"),
            {"tid": tenant_b},
        )

        res_b = await session.execute(
            text("SELECT tenant_id, settings->>'reporting_currency' FROM tenant_settings ORDER BY tenant_id;")
        )
        rows_b = res_b.fetchall()

        # Tenant B can only see tenant B's row; tenant A is invisible
        assert len(rows_b) == 1, f"Expected exactly 1 row for tenant B, got {len(rows_b)}"
        assert rows_b[0][0] == tenant_b
        assert rows_b[0][1] == "EUR"

        # 4. SET LOCAL app.current_tenant_id = '' (Unauthenticated / invalid context)
        await session.execute(
            text("SELECT set_config('app.current_tenant_id', '', true);")
        )

        res_empty = await session.execute(
            text("SELECT tenant_id FROM tenant_settings WHERE tenant_id IN (:ta, :tb);"),
            {"ta": tenant_a, "tb": tenant_b},
        )
        rows_empty = res_empty.fetchall()
        assert len(rows_empty) == 0, f"Expected 0 rows for empty tenant context, got {len(rows_empty)}"

    print("\n[RLS RAW-SQL PROOF] Verified: Tenant A cannot read Tenant B; Tenant B cannot read Tenant A.")
