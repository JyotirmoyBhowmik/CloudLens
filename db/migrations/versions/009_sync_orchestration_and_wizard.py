"""Sync Orchestration, Quarantine, Wizard Sessions, and Schedules Migration.

Revision ID: 009_sync_orchestration_and_wizard
Revises: 008_connector_contract_and_capabilities
Create Date: 2026-09-27 00:00:00.000000

Enforces Prompt 15 Items 97-105:
- sync_scope_results: Per-scope execution status for partial failure isolation (Item 99).
- quarantine_records: Dead-letter quarantine with reasons visible to operators (Item 99).
- wizard_sessions: Thirteen-step onboarding wizard save-and-resume persistence (Item 100).
- connector_schedules: Configured per-connector, per-capability schedules with intervals (Item 98).
- sync_jobs: Added idempotency key, sync type, dataset version, period bounds, and scope lists.
- RLS policies across all four tables.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "009_sync_orchestration_and_wizard"
down_revision: Union[str, None] = "008_connector_contract_and_capabilities"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Update sync_jobs table with Prompt 15 orchestration columns
    try:
        op.add_column("sync_jobs", sa.Column("connector_id", sa.String(64), nullable=True))
        op.add_column("sync_jobs", sa.Column("sync_type", sa.String(32), nullable=False, server_default="scheduled_sync"))
        op.add_column("sync_jobs", sa.Column("capability", sa.String(64), nullable=True))
        op.add_column("sync_jobs", sa.Column("dataset_version", sa.String(64), nullable=True))
        op.add_column("sync_jobs", sa.Column("idempotency_key", sa.String(255), nullable=True))
        op.add_column("sync_jobs", sa.Column("period_start", sa.DateTime(timezone=True), nullable=True))
        op.add_column("sync_jobs", sa.Column("period_end", sa.DateTime(timezone=True), nullable=True))
        op.add_column("sync_jobs", sa.Column("scopes_requested", postgresql.JSONB(), nullable=False, server_default="[]"))
        op.add_column("sync_jobs", sa.Column("scopes_completed", postgresql.JSONB(), nullable=False, server_default="[]"))
        op.add_column("sync_jobs", sa.Column("scopes_failed", postgresql.JSONB(), nullable=False, server_default="[]"))
        op.create_index("idx_sync_jobs_idempotency", "sync_jobs", ["tenant_id", "idempotency_key"])
    except Exception:
        pass

    # 2. Sync Scope Results Table
    op.create_table(
        "sync_scope_results",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("job_id", sa.String(64), nullable=False),
        sa.Column("scope_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="SUCCESS"),
        sa.Column("records_ingested", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_scope_results_lookup", "sync_scope_results", ["tenant_id", "job_id", "scope_id"])

    # 3. Quarantine Records Table
    op.create_table(
        "quarantine_records",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("connector_id", sa.String(64), nullable=False),
        sa.Column("job_id", sa.String(64), nullable=True),
        sa.Column("capability", sa.String(64), nullable=False),
        sa.Column("quarantine_reason", sa.String(64), nullable=False),
        sa.Column("error_details", sa.Text(), nullable=False),
        sa.Column("payload_summary", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("raw_payload_path", sa.Text(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="QUARANTINED"),
        sa.Column("quarantined_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.String(255), nullable=True),
    )
    op.create_index("idx_quarantine_tenant_status", "quarantine_records", ["tenant_id", "status", "quarantined_at"])

    # 4. Wizard Sessions Table
    op.create_table(
        "wizard_sessions",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("provider", sa.String(32), nullable=True),
        sa.Column("current_step", sa.String(64), nullable=False, server_default="select_provider"),
        sa.Column("completed_steps", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("wizard_data", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(32), nullable=False, server_default="IN_PROGRESS"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_wizard_tenant_user", "wizard_sessions", ["tenant_id", "user_id", "status"])

    # 5. Connector Schedules Table
    op.create_table(
        "connector_schedules",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("connector_id", sa.String(64), nullable=False),
        sa.Column("capability", sa.String(64), nullable=False),
        sa.Column("interval_minutes", sa.Integer(), nullable=False),
        sa.Column("cron_expression", sa.String(64), nullable=True),
        sa.Column("lookback_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_successful_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_schedules_lookup", "connector_schedules", ["tenant_id", "connector_id", "capability"])

    # 6. RLS Policies
    for table in ["sync_scope_results", "quarantine_records", "wizard_sessions", "connector_schedules"]:
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
    for table in ["connector_schedules", "wizard_sessions", "quarantine_records", "sync_scope_results"]:
        try:
            op.execute(f"DROP POLICY IF EXISTS tenant_isolation_policy_{table} ON {table};")
        except Exception:
            pass
        op.drop_table(table)
