"""Raw-SQL Row-Level Security Isolation Proof (Prompt P03 Done When Item 2).

Demonstrates:
1. Under non-owner, non-bypassrls application role (cloudlens_app), PostgreSQL RLS is active.
2. Querying with app.current_tenant_id = 'tenant-A' returns ONLY tenant-A records.
3. Querying with app.current_tenant_id = 'tenant-B' returns ONLY tenant-B records.
4. Tenant A strictly cannot read Tenant B records.
"""

import asyncio
import sys

sys.path.insert(0, ".")

from db.session import get_tenant_session
from sqlalchemy import text


async def main():
    # 1. Clean and seed test rows using superuser
    async with get_tenant_session() as s:
        await s.execute(text("DELETE FROM tenant_settings WHERE tenant_id IN ('tenant-A', 'tenant-B');"))
        await s.execute(
            text("""
                INSERT INTO tenant_settings (tenant_id, settings, updated_at)
                VALUES
                    ('tenant-A', '{"name": "Tenant A"}'::jsonb, NOW()),
                    ('tenant-B', '{"name": "Tenant B"}'::jsonb, NOW());
            """)
        )
        await s.commit()

    # 2. Query under cloudlens_app application role with tenant isolation
    async with get_tenant_session() as s:
        await s.execute(text("SET ROLE cloudlens_app;"))

        # Query as Tenant A
        await s.execute(text("SELECT set_config('app.current_tenant_id', 'tenant-A', true);"))
        res_a = await s.execute(
            text("SELECT tenant_id FROM tenant_settings WHERE tenant_id IN ('tenant-A', 'tenant-B') ORDER BY tenant_id;")
        )
        rows_a = [r[0] for r in res_a.fetchall()]
        print("QUERY AS TENANT-A:", rows_a)

        # Query as Tenant B
        await s.execute(text("SELECT set_config('app.current_tenant_id', 'tenant-B', true);"))
        res_b = await s.execute(
            text("SELECT tenant_id FROM tenant_settings WHERE tenant_id IN ('tenant-A', 'tenant-B') ORDER BY tenant_id;")
        )
        rows_b = [r[0] for r in res_b.fetchall()]
        print("QUERY AS TENANT-B:", rows_b)

        # Assert isolation invariant
        assert rows_a == ["tenant-A"], f"Tenant A isolation failed: got {rows_a}"
        assert rows_b == ["tenant-B"], f"Tenant B isolation failed: got {rows_b}"
        print("[RLS RAW-SQL PROOF SUCCESS] Invariant holds: Tenant A cannot read Tenant B, Tenant B cannot read Tenant A.")


if __name__ == "__main__":
    asyncio.run(main())
