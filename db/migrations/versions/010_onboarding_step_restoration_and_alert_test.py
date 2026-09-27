"""Onboarding Step Restoration, Alert Delivery Test, and First-Sync Progress Migration.

Revision ID: 010_onboarding_step_restoration_and_alert_test
Revises: 009_sync_orchestration_and_wizard
Create Date: 2026-09-27 00:00:00.000000

Enforces Prompt 15B Items 21-27 / D-07:
- notification_logs: Outbound notification dispatch and test alert log table (Item 25).
- first_sync_progress: Five visible first-sync background stages live tracking (Items 21, 22).
- RLS policies across both tables for strict tenant isolation.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "010_onboarding_step_restoration_and_alert_test"
down_revision: Union[str, None] = "009_sync_orchestration_and_wizard"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create notification_logs table (Prompt 15B Item 25)
    op.create_table(
        "notification_logs",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("alert_id", sa.String(64), nullable=True),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("recipient", sa.String(255), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="PENDING"),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("is_test", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("metadata_payload", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_notif_tenant_channel", "notification_logs", ["tenant_id", "channel"])
    op.create_index("idx_notif_tenant_test", "notification_logs", ["tenant_id", "is_test"])
    op.create_index("idx_notif_tenant_sent", "notification_logs", ["tenant_id", "sent_at"])

    # 2. Create first_sync_progress table (Prompt 15B Items 21, 22)
    op.create_table(
        "first_sync_progress",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("session_id", sa.String(64), nullable=False),
        sa.Column("connector_id", sa.String(64), nullable=False),
        sa.Column("initial_sync_job_id", sa.String(64), nullable=True),
        sa.Column("overall_status", sa.String(32), nullable=False, server_default="RUNNING"),
        sa.Column("stages_data", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("total_stages", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("completed_stages", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("estimated_time_to_first_cost_seconds", sa.Integer(), nullable=False, server_default="14400"),
        sa.Column("landing_destination", sa.String(500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_first_sync_tenant_session", "first_sync_progress", ["tenant_id", "session_id"], unique=True)
    op.create_index("idx_first_sync_tenant_connector", "first_sync_progress", ["tenant_id", "connector_id"])

    # 3. Enable RLS and add tenant isolation policies
    op.execute("ALTER TABLE notification_logs ENABLE ROW LEVEL SECURITY;")
    op.execute(
        """
        CREATE POLICY tenant_isolation_notification_logs ON notification_logs
        AS RESTRICTIVE
        USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), ''))
        WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), ''));
        """
    )

    op.execute("ALTER TABLE first_sync_progress ENABLE ROW LEVEL SECURITY;")
    op.execute(
        """
        CREATE POLICY tenant_isolation_first_sync_progress ON first_sync_progress
        AS RESTRICTIVE
        USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), ''))
        WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), ''));
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation_first_sync_progress ON first_sync_progress;")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_notification_logs ON notification_logs;")
    op.drop_table("first_sync_progress")
    op.drop_table("notification_logs")
