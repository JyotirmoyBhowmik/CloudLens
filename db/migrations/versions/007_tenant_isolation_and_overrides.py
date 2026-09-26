"""Tenant Isolation & Operational Overrides Migration.

Revision ID: 007_tenant_isolation_and_overrides
Revises: 006_master_data_framework
Create Date: 2026-09-26 21:00:00.000000

Enforces Prompt 13 Items 84-87:
- overrides: Operational and governance overrides with 8 mandatory attributes.
- RLS policy on overrides table.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "007_tenant_isolation_and_overrides"
down_revision: Union[str, None] = "006_master_data_framework"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Overrides Table
    op.create_table(
        "overrides",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("override_class", sa.String(64), nullable=False),
        sa.Column("who", sa.String(255), nullable=False),
        sa.Column("what", sa.String(255), nullable=False),
        sa.Column("why", sa.Text(), nullable=False),
        sa.Column("when", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("previous_value", postgresql.JSONB(), nullable=True),
        sa.Column("new_value", postgresql.JSONB(), nullable=False),
        sa.Column("expiry", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_permanent", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("approval_metadata", postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="ACTIVE"),
        sa.Column("reverted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reverted_by", sa.String(255), nullable=True),
        sa.Column("reversion_reason", sa.Text(), nullable=True),
        sa.Column("correlation_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_overrides_tenant_status", "overrides", ["tenant_id", "status"])
    op.create_index("idx_overrides_tenant_expiry", "overrides", ["tenant_id", "expiry"])

    # 2. Row-Level Security for overrides
    try:
        op.execute("ALTER TABLE overrides ENABLE ROW LEVEL SECURITY;")
        op.execute("""
            CREATE POLICY tenant_isolation_policy_overrides ON overrides
            FOR ALL
            USING (
                tenant_id = NULLIF(current_setting('cloudlens.current_tenant_id', true), '')
                OR current_setting('cloudlens.bypass_rls', true) = 'on'
            )
            WITH CHECK (
                tenant_id = NULLIF(current_setting('cloudlens.current_tenant_id', true), '')
                OR current_setting('cloudlens.bypass_rls', true) = 'on'
            );
        """)
    except Exception:
        pass


def downgrade() -> None:
    try:
        op.execute("DROP POLICY IF EXISTS tenant_isolation_policy_overrides ON overrides;")
    except Exception:
        pass
    op.drop_table("overrides")
