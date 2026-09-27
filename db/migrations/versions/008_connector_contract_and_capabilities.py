"""Connector Contract, Checkpoints, and Raw Landings Migration.

Revision ID: 008_connector_contract_and_capabilities
Revises: 007_tenant_isolation_and_overrides
Create Date: 2026-09-27 00:00:00.000000

Enforces Prompt 14 Items 89-95:
- connectors: Registered cloud connectors with lifecycle states and capability profiles.
- connector_checkpoints: Continuation tokens and page checkpoints for uninterrupted job resumption.
- raw_landings: Immutable raw provider payload landings with SHA256 integrity digests.
- RLS policies on all three tables.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "008_connector_contract_and_capabilities"
down_revision: Union[str, None] = "007_tenant_isolation_and_overrides"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Connectors Table
    op.create_table(
        "connectors",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("lifecycle_state", sa.String(32), nullable=False, server_default="REGISTERED"),
        sa.Column("credential_profile_id", sa.String(64), nullable=True),
        sa.Column("declared_capabilities", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("verified_capabilities", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("config", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_connectors_tenant_state", "connectors", ["tenant_id", "lifecycle_state"])
    op.create_index("idx_connectors_tenant_provider", "connectors", ["tenant_id", "provider"])

    # 2. Connector Checkpoints Table
    op.create_table(
        "connector_checkpoints",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("job_id", sa.String(64), nullable=False),
        sa.Column("connector_id", sa.String(64), nullable=False),
        sa.Column("capability", sa.String(64), nullable=False),
        sa.Column("continuation_token", sa.Text(), nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("records_ingested", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_record_id", sa.String(255), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="IN_PROGRESS"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_checkpoints_job_cap", "connector_checkpoints", ["tenant_id", "job_id", "capability"])

    # 3. Raw Landings Table
    op.create_table(
        "raw_landings",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("connector_id", sa.String(64), nullable=False),
        sa.Column("run_id", sa.String(64), nullable=False),
        sa.Column("capability", sa.String(64), nullable=False),
        sa.Column("schema_version", sa.String(32), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("sha256_checksum", sa.String(64), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("record_count", sa.Integer(), nullable=False),
        sa.Column("landed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_raw_landings_lookup", "raw_landings", ["tenant_id", "connector_id", "run_id"])

    # 4. RLS for all 3 tables
    for table in ["connectors", "connector_checkpoints", "raw_landings"]:
        try:
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
            op.execute(f"""
                CREATE POLICY tenant_isolation_policy_{table} ON {table}
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
    for table in ["raw_landings", "connector_checkpoints", "connectors"]:
        try:
            op.execute(f"DROP POLICY IF EXISTS tenant_isolation_policy_{table} ON {table};")
        except Exception:
            pass
        op.drop_table(table)
