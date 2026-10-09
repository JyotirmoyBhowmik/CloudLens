"""Persistence Tier 5: Remaining Modules (Prompt P08).

Revision ID: 016_persistence_tier5_remaining_modules
Revises: 015_persistence_tier4_governance_and_estate
Create Date: 2026-10-09 04:30:00.000000

Enforces Prompt P08:
- report_jobs, report_artifacts, report_schedules
- analytics_jobs, analytics_snapshots, partition_watermarks
- commitments, commitment_recommendations, commitment_utilization_history,
  commitment_coverage_snapshots, commitment_exchanges, amortization_ledger_entries
- budget_cycles, budget_submissions, budget_submission_history, budget_targets, planning_scenarios
- lifecycle_resources, lifecycle_requests, lifecycle_programmes, orphan_residue_items
- connector_lifecycle_states, connector_capability_health
- in_app_notifications, outbound_events
- Row-Level Security (ENABLE RLS + FORCE RLS) across all tenant tables and grants to cloudlens_app.
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "016_persistence_tier5_remaining_modules"
down_revision: Union[str, None] = "015_persistence_tier4_governance_and_estate"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Fix resource_types index to support versioning
    op.drop_index("idx_res_types_provider_native", table_name="resource_types", if_exists=True)
    op.create_index(
        "idx_res_types_provider_native_version",
        "resource_types",
        ["provider", "native_type_name", "version"],
        unique=True,
        if_not_exists=True,
    )

    # -------------------------------------------------------------------------
    # 1. Reports: Jobs, Artifacts, Schedules
    # -------------------------------------------------------------------------
    op.create_table(
        "report_jobs",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("report_type", sa.String(64), nullable=True),
        sa.Column("status", sa.String(32), nullable=True),
        sa.Column("parameters", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("artifact_id", sa.String(64), nullable=True),
        sa.Column("created_by", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("job_payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_index("idx_report_jobs_tenant", "report_jobs", ["tenant_id"])

    op.create_table(
        "report_artifacts",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("report_id", sa.String(64), nullable=False),
        sa.Column("content_type", sa.String(128), nullable=True),
        sa.Column("artifact_bytes", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_report_artifacts_tenant", "report_artifacts", ["tenant_id", "report_id"])

    op.create_table(
        "report_schedules",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("report_type", sa.String(64), nullable=True),
        sa.Column("cron_expression", sa.String(128), nullable=True),
        sa.Column("parameters", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("schedule_payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_index("idx_report_schedules_tenant", "report_schedules", ["tenant_id"])

    # -------------------------------------------------------------------------
    # 2. Analytics & Watermarks
    # -------------------------------------------------------------------------
    op.create_table(
        "analytics_jobs",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("status", sa.String(32), nullable=True),
        sa.Column("parameters", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("row_count", sa.Integer(), server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("job_payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_index("idx_analytics_jobs_tenant", "analytics_jobs", ["tenant_id"])

    op.create_table(
        "analytics_snapshots",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("period", sa.String(32), nullable=False),
        sa.Column("facts_payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("dimensions_payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_analytics_snapshots_tenant_period", "analytics_snapshots", ["tenant_id", "period"])

    op.create_table(
        "partition_watermarks",
        sa.Column("id", sa.String(128), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("period", sa.String(64), nullable=False),
        sa.Column("current_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("last_watermark_timestamp", sa.String(128), nullable=True),
        sa.Column("last_extract_timestamp", sa.String(128), nullable=True),
        sa.Column("is_restated", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("superseded_versions", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_partition_watermarks_tenant_period", "partition_watermarks", ["tenant_id", "period"], unique=True)

    # -------------------------------------------------------------------------
    # 3. Commitments & Amortization Ledger
    # -------------------------------------------------------------------------
    op.create_table(
        "commitments",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("commitment_type", sa.String(64), nullable=True),
        sa.Column("provider", sa.String(32), nullable=True),
        sa.Column("status", sa.String(32), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_commitments_tenant", "commitments", ["tenant_id"])

    op.create_table(
        "commitment_recommendations",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(32), nullable=True),
        sa.Column("status", sa.String(32), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_commitment_recs_tenant", "commitment_recommendations", ["tenant_id"])

    op.create_table(
        "commitment_utilization_history",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("commitment_id", sa.String(64), nullable=True),
        sa.Column("utilization_rate", sa.Numeric(10, 4), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_index("idx_commitment_util_tenant", "commitment_utilization_history", ["tenant_id", "commitment_id"])

    op.create_table(
        "commitment_coverage_snapshots",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("period", sa.String(32), nullable=True),
        sa.Column("coverage_rate", sa.Numeric(10, 4), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_index("idx_commitment_cov_tenant", "commitment_coverage_snapshots", ["tenant_id", "period"])

    op.create_table(
        "commitment_exchanges",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("from_commitment_id", sa.String(64), nullable=True),
        sa.Column("to_commitment_id", sa.String(64), nullable=True),
        sa.Column("status", sa.String(32), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_commitment_exchanges_tenant", "commitment_exchanges", ["tenant_id"])

    op.create_table(
        "amortization_ledger_entries",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("commitment_id", sa.String(64), nullable=True),
        sa.Column("period", sa.String(32), nullable=True),
        sa.Column("amount", sa.Numeric(18, 4), nullable=True),
        sa.Column("currency", sa.String(8), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_index("idx_amortization_ledger_tenant", "amortization_ledger_entries", ["tenant_id", "commitment_id"])

    # -------------------------------------------------------------------------
    # 4. Planning: Cycles, Submissions, Targets, Scenarios
    # -------------------------------------------------------------------------
    op.create_table(
        "budget_cycles",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("fiscal_period", sa.String(64), nullable=True),
        sa.Column("status", sa.String(32), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_budget_cycles_tenant", "budget_cycles", ["tenant_id"])

    op.create_table(
        "budget_submissions",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("cycle_id", sa.String(64), nullable=False),
        sa.Column("scope_id", sa.String(64), nullable=True),
        sa.Column("status", sa.String(32), nullable=True),
        sa.Column("submitted_by", sa.String(128), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_index("idx_budget_submissions_tenant_cycle", "budget_submissions", ["tenant_id", "cycle_id"])

    op.create_table(
        "budget_submission_history",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("submission_id", sa.String(64), nullable=False),
        sa.Column("action", sa.String(64), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_index("idx_budget_sub_history_tenant", "budget_submission_history", ["tenant_id", "submission_id"])

    op.create_table(
        "budget_targets",
        sa.Column("id", sa.String(128), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("cycle_id", sa.String(64), nullable=False),
        sa.Column("scope_id", sa.String(64), nullable=False),
        sa.Column("amount", sa.Numeric(18, 4), nullable=True),
        sa.Column("currency", sa.String(8), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_index("idx_budget_targets_tenant_cycle", "budget_targets", ["tenant_id", "cycle_id"])

    op.create_table(
        "planning_scenarios",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_index("idx_planning_scenarios_tenant", "planning_scenarios", ["tenant_id"])

    # -------------------------------------------------------------------------
    # 5. Lifecycle & Residue
    # -------------------------------------------------------------------------
    op.create_table(
        "lifecycle_resources",
        sa.Column("id", sa.String(128), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("resource_id", sa.String(128), nullable=False),
        sa.Column("state", sa.String(64), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_index("idx_lifecycle_resources_tenant", "lifecycle_resources", ["tenant_id"])

    op.create_table(
        "lifecycle_requests",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_index("idx_lifecycle_requests_tenant", "lifecycle_requests", ["tenant_id"])

    op.create_table(
        "lifecycle_programmes",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("programme_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_index("idx_lifecycle_programmes_tenant", "lifecycle_programmes", ["tenant_id"])

    op.create_table(
        "orphan_residue_items",
        sa.Column("id", sa.String(128), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("resource_id", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_index("idx_orphan_residue_tenant", "orphan_residue_items", ["tenant_id"])

    # -------------------------------------------------------------------------
    # 6. Connector Lifecycle States & Capability Health
    # -------------------------------------------------------------------------
    op.create_table(
        "connector_lifecycle_states",
        sa.Column("id", sa.String(128), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("connector_id", sa.String(64), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_index("idx_connector_lifecycle_tenant", "connector_lifecycle_states", ["tenant_id", "connector_id"])

    op.create_table(
        "connector_capability_health",
        sa.Column("id", sa.String(128), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("connector_id", sa.String(64), nullable=False),
        sa.Column("capability", sa.String(64), nullable=False),
        sa.Column("is_healthy", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_index("idx_connector_cap_health_tenant", "connector_capability_health", ["tenant_id", "connector_id"])

    # -------------------------------------------------------------------------
    # 7. In-App Notifications & Outbound Events
    # -------------------------------------------------------------------------
    op.create_table(
        "in_app_notifications",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("recipient_user_id", sa.String(128), nullable=False),
        sa.Column("alert_id", sa.String(64), nullable=True),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("severity", sa.String(32), nullable=True),
        sa.Column("is_read", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_index("idx_in_app_notif_tenant_user", "in_app_notifications", ["tenant_id", "recipient_user_id"])

    op.create_table(
        "outbound_events",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("event_type", sa.String(128), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(32), server_default=sa.text("'PENDING'")),
        sa.Column("sequence_number", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_outbound_events_tenant", "outbound_events", ["tenant_id"])

    # -------------------------------------------------------------------------
    # 8. Row-Level Security Enforcement & Role Grants
    # -------------------------------------------------------------------------
    tier5_tenant_tables = [
        "report_jobs",
        "report_artifacts",
        "report_schedules",
        "analytics_jobs",
        "analytics_snapshots",
        "partition_watermarks",
        "commitments",
        "commitment_recommendations",
        "commitment_utilization_history",
        "commitment_coverage_snapshots",
        "commitment_exchanges",
        "amortization_ledger_entries",
        "budget_cycles",
        "budget_submissions",
        "budget_submission_history",
        "budget_targets",
        "planning_scenarios",
        "lifecycle_resources",
        "lifecycle_requests",
        "lifecycle_programmes",
        "orphan_residue_items",
        "connector_lifecycle_states",
        "connector_capability_health",
        "in_app_notifications",
        "outbound_events",
    ]

    for tbl in tier5_tenant_tables:
        op.execute(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {tbl} FORCE ROW LEVEL SECURITY;")
        op.execute(f"""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_policies WHERE tablename = '{tbl}' AND policyname = '{tbl}_tenant_isolation'
                ) THEN
                    CREATE POLICY {tbl}_tenant_isolation ON {tbl}
                        FOR ALL
                        USING (tenant_id = current_setting('app.current_tenant_id', true) OR current_setting('cloudlens.bypass_rls', true) = 'on')
                        WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true) OR current_setting('cloudlens.bypass_rls', true) = 'on');
                END IF;
            END $$;
        """)
        op.execute(f"GRANT ALL PRIVILEGES ON TABLE {tbl} TO cloudlens_app;")


def downgrade() -> None:
    pass
