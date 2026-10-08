"""Persistence Tier 4: Governance and Estate (Prompt P07).

Revision ID: 015_persistence_tier4_governance_and_estate
Revises: 014_persistence_tier3_cost_budgets_pricing
Create Date: 2026-10-09 02:00:00.000000

Enforces Prompt P07:
- alerts, alert_subscriptions, alert_delivery_logs, contextual_alerts
- policies (definitions from master data), policy_history, policy_findings, policy_exemptions
- workflow_requests, workflow_definitions, workflow_delegations
- remediation_tasks, remediation_savings_ledger, remediation_rules
- quotas, quota_increase_requests, quota_remediation_tasks
- provisioning_requests, provisioning_estimates, provisioning_gate_rules
- showback_statements, showback_statement_lines, showback_disputes, showback_adjustments
- bulk_import_runs, bulk_import_profiles, bulk_import_dry_runs, bulk_import_scheduled_jobs
- service_dependencies, dependency_conflicts, dependency_history
- usage_overrides, usage_expectations
- runtime_adherence_results, runtime_schedules, runtime_exemptions
- hierarchy_saved_views
- Row-Level Security (ENABLE RLS + FORCE RLS) across all tenant tables and grants to cloudlens_app.
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "015_persistence_tier4_governance_and_estate"
down_revision: Union[str, None] = "014_persistence_tier3_cost_budgets_pricing"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -------------------------------------------------------------------------
    # 0. Alter Existing Tables with Payload and Extension Columns
    # -------------------------------------------------------------------------
    op.execute("ALTER TABLE alerts ADD COLUMN IF NOT EXISTS alert_payload JSONB NOT NULL DEFAULT '{}'::jsonb;")
    op.execute("ALTER TABLE alerts ADD COLUMN IF NOT EXISTS fingerprint VARCHAR(128);")
    op.execute("ALTER TABLE alerts ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();")
    op.execute("CREATE INDEX IF NOT EXISTS idx_alerts_fingerprint ON alerts (tenant_id, fingerprint);")

    op.execute("ALTER TABLE policies ADD COLUMN IF NOT EXISTS policy_payload JSONB NOT NULL DEFAULT '{}'::jsonb;")
    op.execute("ALTER TABLE policies ADD COLUMN IF NOT EXISTS version INTEGER DEFAULT 1;")
    op.execute("ALTER TABLE policies ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();")

    # -------------------------------------------------------------------------
    # 1. Alerting: Subscriptions, Delivery Logs, Contextual Alerts
    # -------------------------------------------------------------------------
    op.create_table(
        "alert_subscriptions",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("subscription_payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_alert_subscriptions_tenant", "alert_subscriptions", ["tenant_id"])

    op.create_table(
        "alert_delivery_logs",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("alert_id", sa.String(64), nullable=False),
        sa.Column("channel", sa.String(64), nullable=False),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column("delivery_payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_alert_delivery_logs_tenant_alert", "alert_delivery_logs", ["tenant_id", "alert_id"])

    op.create_table(
        "contextual_alerts",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("alert_type", sa.String(64), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("context_entity_type", sa.String(64), nullable=False),
        sa.Column("context_entity_id", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(32), nullable=False),
        sa.Column("is_dismissed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("alert_payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_contextual_alerts_tenant_entity", "contextual_alerts", ["tenant_id", "context_entity_type", "context_entity_id"])

    # -------------------------------------------------------------------------
    # 2. Policies: History, Findings, Exemptions
    # -------------------------------------------------------------------------
    op.create_table(
        "policy_history",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("policy_id", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("policy_payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("tenant_id", "policy_id", "version"),
    )

    op.create_table(
        "policy_findings",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("policy_id", sa.String(64), nullable=False),
        sa.Column("entity_id", sa.String(128), nullable=False),
        sa.Column("lifecycle_status", sa.String(32), nullable=False, server_default="OPEN"),
        sa.Column("severity", sa.String(32), nullable=False, server_default="MEDIUM"),
        sa.Column("category", sa.String(64), nullable=True),
        sa.Column("mode", sa.String(32), nullable=False, server_default="ENFORCE"),
        sa.Column("finding_payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_evaluated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_policy_findings_tenant_status", "policy_findings", ["tenant_id", "lifecycle_status"])
    op.create_index("idx_policy_findings_tenant_entity_policy", "policy_findings", ["tenant_id", "entity_id", "policy_id"])

    op.create_table(
        "policy_exemptions",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("policy_id", sa.String(64), nullable=False),
        sa.Column("entity_id", sa.String(128), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("exemption_payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_policy_exemptions_tenant_policy", "policy_exemptions", ["tenant_id", "policy_id"])

    # -------------------------------------------------------------------------
    # 3. Workflows: Requests, Definitions, Delegations
    # -------------------------------------------------------------------------
    op.create_table(
        "workflow_requests",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("request_type", sa.String(64), nullable=False),
        sa.Column("state", sa.String(32), nullable=False, server_default="PENDING"),
        sa.Column("requester_id", sa.String(128), nullable=False),
        sa.Column("request_payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_workflow_requests_tenant_state", "workflow_requests", ["tenant_id", "state"])

    op.create_table(
        "workflow_definitions",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("request_type", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("definition_payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_workflow_definitions_tenant_type", "workflow_definitions", ["tenant_id", "request_type"])

    op.create_table(
        "workflow_delegations",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("delegator_id", sa.String(128), nullable=False),
        sa.Column("delegatee_id", sa.String(128), nullable=False),
        sa.Column("delegation_payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_workflow_delegations_tenant", "workflow_delegations", ["tenant_id"])

    # -------------------------------------------------------------------------
    # 4. Remediation: Tasks, Savings Ledger, Rules
    # -------------------------------------------------------------------------
    op.create_table(
        "remediation_tasks",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("state", sa.String(32), nullable=False, server_default="OPEN"),
        sa.Column("priority", sa.String(32), nullable=False, server_default="MEDIUM"),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("assignee_id", sa.String(128), nullable=True),
        sa.Column("task_payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_remediation_tasks_tenant_state", "remediation_tasks", ["tenant_id", "state"])

    op.create_table(
        "remediation_savings_ledger",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("task_id", sa.String(64), nullable=False),
        sa.Column("amount", sa.Numeric(18, 6), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("ledger_payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_remediation_savings_tenant", "remediation_savings_ledger", ["tenant_id", "task_id"])

    op.create_table(
        "remediation_rules",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("source_code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("rule_payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_remediation_rules_tenant", "remediation_rules", ["tenant_id"])

    # -------------------------------------------------------------------------
    # 5. Quotas: Quotas, Requests, Remediation Tasks
    # -------------------------------------------------------------------------
    op.create_table(
        "quotas",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("service_code", sa.String(64), nullable=False),
        sa.Column("quota_code", sa.String(128), nullable=False),
        sa.Column("scope_id", sa.String(64), nullable=True),
        sa.Column("quota_payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_quotas_tenant_provider_service", "quotas", ["tenant_id", "provider", "service_code"])

    op.create_table(
        "quota_increase_requests",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("quota_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="SUBMITTED"),
        sa.Column("request_payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_quota_increase_requests_tenant", "quota_increase_requests", ["tenant_id", "quota_id"])

    op.create_table(
        "quota_remediation_tasks",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("quota_id", sa.String(64), nullable=False),
        sa.Column("task_payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_quota_remediation_tasks_tenant", "quota_remediation_tasks", ["tenant_id", "quota_id"])

    # -------------------------------------------------------------------------
    # 6. Provisioning: Requests, Estimates, Gate Rules
    # -------------------------------------------------------------------------
    op.create_table(
        "provisioning_requests",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("requester_id", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="PENDING"),
        sa.Column("target_scope", sa.String(64), nullable=False),
        sa.Column("request_payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_provisioning_requests_tenant_status", "provisioning_requests", ["tenant_id", "status"])

    op.create_table(
        "provisioning_estimates",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("estimate_payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_provisioning_estimates_tenant", "provisioning_estimates", ["tenant_id"])

    op.create_table(
        "provisioning_gate_rules",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("rule_payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_provisioning_gate_rules_tenant", "provisioning_gate_rules", ["tenant_id"])

    # -------------------------------------------------------------------------
    # 7. Statements: Statements, Lines, Disputes, Adjustments
    # -------------------------------------------------------------------------
    op.create_table(
        "showback_statements",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("period", sa.String(16), nullable=False),
        sa.Column("scope_code", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="DRAFT"),
        sa.Column("statement_payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_showback_statements_tenant_period", "showback_statements", ["tenant_id", "period"])

    op.create_table(
        "showback_statement_lines",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("statement_id", sa.String(64), nullable=False),
        sa.Column("line_payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_showback_lines_tenant_statement", "showback_statement_lines", ["tenant_id", "statement_id"])

    op.create_table(
        "showback_disputes",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("statement_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="OPEN"),
        sa.Column("dispute_payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_showback_disputes_tenant_statement", "showback_disputes", ["tenant_id", "statement_id"])

    op.create_table(
        "showback_adjustments",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("statement_id", sa.String(64), nullable=False),
        sa.Column("adjustment_payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_showback_adjustments_tenant_statement", "showback_adjustments", ["tenant_id", "statement_id"])

    # -------------------------------------------------------------------------
    # 8. Bulk Imports: Runs, Profiles, Dry Runs, Scheduled Jobs
    # -------------------------------------------------------------------------
    op.create_table(
        "bulk_import_runs",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="COMPLETED"),
        sa.Column("run_payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_bulk_import_runs_tenant_type", "bulk_import_runs", ["tenant_id", "entity_type"])

    op.create_table(
        "bulk_import_profiles",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("profile_payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_bulk_import_profiles_tenant", "bulk_import_profiles", ["tenant_id"])

    op.create_table(
        "bulk_import_dry_runs",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("dry_run_payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_bulk_import_dry_runs_tenant", "bulk_import_dry_runs", ["tenant_id"])

    op.create_table(
        "bulk_import_scheduled_jobs",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("job_payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_bulk_import_jobs_tenant", "bulk_import_scheduled_jobs", ["tenant_id"])

    # -------------------------------------------------------------------------
    # 9. Dependencies: Edges, Conflicts, History
    # -------------------------------------------------------------------------
    op.create_table(
        "service_dependencies",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("source_id", sa.String(128), nullable=False),
        sa.Column("target_id", sa.String(128), nullable=False),
        sa.Column("relationship_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="ACTIVE"),
        sa.Column("edge_payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_service_dependencies_tenant_source_target", "service_dependencies", ["tenant_id", "source_id", "target_id"])

    op.create_table(
        "dependency_conflicts",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("edge_id", sa.String(64), nullable=False),
        sa.Column("conflict_type", sa.String(64), nullable=False),
        sa.Column("conflict_payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_dependency_conflicts_tenant", "dependency_conflicts", ["tenant_id", "edge_id"])

    op.create_table(
        "dependency_history",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("edge_id", sa.String(64), nullable=False),
        sa.Column("version_payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_dependency_history_tenant", "dependency_history", ["tenant_id", "edge_id"])

    # -------------------------------------------------------------------------
    # 10. Usage: Overrides, Expectations
    # -------------------------------------------------------------------------
    op.create_table(
        "usage_overrides",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("resource_id", sa.String(128), nullable=False),
        sa.Column("override_payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_usage_overrides_tenant_resource", "usage_overrides", ["tenant_id", "resource_id"])

    op.create_table(
        "usage_expectations",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("level", sa.String(32), nullable=False),
        sa.Column("target_id", sa.String(128), nullable=False),
        sa.Column("expectation_payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_usage_expectations_tenant", "usage_expectations", ["tenant_id", "level", "target_id"])

    # -------------------------------------------------------------------------
    # 11. Runtime: Adherence Results, Schedules, Exemptions
    # -------------------------------------------------------------------------
    op.create_table(
        "runtime_adherence_results",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("schedule_id", sa.String(64), nullable=False),
        sa.Column("result_payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("evaluation_window_end", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_runtime_adherence_tenant", "runtime_adherence_results", ["tenant_id", "schedule_id"])

    op.create_table(
        "runtime_schedules",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("schedule_payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_runtime_schedules_tenant", "runtime_schedules", ["tenant_id"])

    op.create_table(
        "runtime_exemptions",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("resource_id", sa.String(128), nullable=False),
        sa.Column("exemption_payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_runtime_exemptions_tenant", "runtime_exemptions", ["tenant_id", "resource_id"])

    # -------------------------------------------------------------------------
    # 12. Hierarchy & Estate: Saved Views
    # -------------------------------------------------------------------------
    op.create_table(
        "hierarchy_saved_views",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("user_id", sa.String(128), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("view_payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_hierarchy_saved_views_tenant", "hierarchy_saved_views", ["tenant_id", "user_id"])

    # -------------------------------------------------------------------------
    # 13. Row-Level Security (ENABLE RLS + FORCE RLS) & Grants
    # -------------------------------------------------------------------------
    tier4_tenant_tables = [
        "alert_subscriptions",
        "alert_delivery_logs",
        "contextual_alerts",
        "policy_history",
        "policy_findings",
        "policy_exemptions",
        "workflow_requests",
        "workflow_definitions",
        "workflow_delegations",
        "remediation_tasks",
        "remediation_savings_ledger",
        "remediation_rules",
        "quotas",
        "quota_increase_requests",
        "quota_remediation_tasks",
        "provisioning_requests",
        "provisioning_estimates",
        "provisioning_gate_rules",
        "showback_statements",
        "showback_statement_lines",
        "showback_disputes",
        "showback_adjustments",
        "bulk_import_runs",
        "bulk_import_profiles",
        "bulk_import_dry_runs",
        "bulk_import_scheduled_jobs",
        "service_dependencies",
        "dependency_conflicts",
        "dependency_history",
        "usage_overrides",
        "usage_expectations",
        "runtime_adherence_results",
        "runtime_schedules",
        "runtime_exemptions",
        "hierarchy_saved_views",
        "alerts",
        "policies",
        "scopes",
        "resources",
    ]

    for tbl in tier4_tenant_tables:
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

    # Also grant on usage_fact and runtime_state partitioned tables
    op.execute("GRANT ALL PRIVILEGES ON TABLE usage_fact TO cloudlens_app;")
    op.execute("GRANT ALL PRIVILEGES ON TABLE usage_fact_default TO cloudlens_app;")
    op.execute("GRANT ALL PRIVILEGES ON TABLE runtime_state TO cloudlens_app;")
    op.execute("GRANT ALL PRIVILEGES ON TABLE runtime_state_default TO cloudlens_app;")


def downgrade() -> None:
    pass
