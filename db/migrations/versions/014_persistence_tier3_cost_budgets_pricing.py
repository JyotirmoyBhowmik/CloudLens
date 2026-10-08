"""Persistence Tier 3: Cost, Pricing, Budgets, Thresholds, Forecast, Reconciliation (Prompt P06).

Revision ID: 014_persistence_tier3_cost_budgets_pricing
Revises: 013_persistence_tier2_unique_idempotency
Create Date: 2026-10-09 01:00:00.000000

Enforces Prompt P06:
- cost_restatements: Tracks superseded partitions and audit history across atomic partition replacement.
- budgets schema enrichment: Adds canonical fields (scope_type, currency, owner, thresholds JSONB, amendments JSONB).
- pricing_records & pricing_changes: SCD Type 2 point-in-time rates, effective-dating, and price variance change log.
- forecasts & forecast_milestones: Multi-method spend forecasts with predicted breach dates and milestone tracking.
- reconciliation_reports & reconciliation_investigations & estimate_vs_actual_items: Period invoice comparison and tolerance variance tracking.
- exchange_rates: Effective-dated currency conversion table with unique pair/date constraint.
- threshold_rules, threshold_overrides, threshold_evaluation_results: Hierarchical threshold governance rules and anti-flapping states.
- Row-Level Security (ENABLE RLS + FORCE RLS) across tenant tables and grants to cloudlens_app.
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "014_persistence_tier3_cost_budgets_pricing"
down_revision: Union[str, None] = "013_persistence_tier2_unique_idempotency"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -------------------------------------------------------------------------
    # 1. Cost Restatements Table
    # -------------------------------------------------------------------------
    op.create_table(
        "cost_restatements",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("billing_period", sa.String(16), nullable=False),
        sa.Column("original_billed_cost", sa.Numeric(18, 6), nullable=False),
        sa.Column("restated_billed_cost", sa.Numeric(18, 6), nullable=False),
        sa.Column("original_effective_cost", sa.Numeric(18, 6), nullable=False),
        sa.Column("restated_effective_cost", sa.Numeric(18, 6), nullable=False),
        sa.Column("reasons", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("superseded_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("restatement_detected_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_cost_restatements_tenant_period", "cost_restatements", ["tenant_id", "billing_period"])

    # -------------------------------------------------------------------------
    # 2. Enrich Budgets Table
    # -------------------------------------------------------------------------
    # Drop FK on scope_id if present to support 17 scope types
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.table_constraints WHERE constraint_name = 'budgets_scope_id_fkey') THEN
                ALTER TABLE budgets DROP CONSTRAINT budgets_scope_id_fkey;
            END IF;
        END $$;
    """)
    op.execute("ALTER TABLE budgets ALTER COLUMN start_date DROP NOT NULL;")
    op.execute("ALTER TABLE budgets ALTER COLUMN end_date DROP NOT NULL;")

    # Add enriched budget columns
    budget_cols = [
        ("scope_type", "VARCHAR(64) NOT NULL DEFAULT 'SUBSCRIPTION'"),
        ("parent_budget_id", "VARCHAR(64)"),
        ("currency", "VARCHAR(3) NOT NULL DEFAULT 'USD'"),
        ("owner", "VARCHAR(255) NOT NULL DEFAULT 'FinOps'"),
        ("approval_status", "VARCHAR(32) NOT NULL DEFAULT 'DRAFT'"),
        ("effective_date", "DATE"),
        ("expiry_date", "DATE"),
        ("forecast_threshold", "NUMERIC(5, 2) DEFAULT 100.0"),
        ("rollover_policy", "VARCHAR(32) NOT NULL DEFAULT 'NONE'"),
        ("notes", "TEXT"),
        ("budget_source", "VARCHAR(32) NOT NULL DEFAULT 'CLOUDLENS_LOGICAL'"),
        ("is_native", "BOOLEAN NOT NULL DEFAULT FALSE"),
        ("is_read_only", "BOOLEAN NOT NULL DEFAULT FALSE"),
        ("native_provider", "VARCHAR(32)"),
        ("native_budget_id", "VARCHAR(255)"),
        ("native_budget_name", "VARCHAR(255)"),
        ("thresholds", "JSONB NOT NULL DEFAULT '[]'::jsonb"),
        ("alert_recipients", "JSONB NOT NULL DEFAULT '[]'::jsonb"),
        ("escalation", "JSONB"),
        ("approval_decision", "JSONB"),
        ("amendments", "JSONB NOT NULL DEFAULT '[]'::jsonb"),
        ("updated_at", "TIMESTAMPTZ NOT NULL DEFAULT NOW()"),
    ]
    for col_name, col_def in budget_cols:
        op.execute(f"ALTER TABLE budgets ADD COLUMN IF NOT EXISTS {col_name} {col_def};")

    op.create_index("idx_budgets_tenant_scope_hier", "budgets", ["tenant_id", "scope_type", "scope_id"])
    op.create_index("idx_budgets_tenant_parent", "budgets", ["tenant_id", "parent_budget_id"])

    # -------------------------------------------------------------------------
    # 3. Pricing Records & Changes
    # -------------------------------------------------------------------------
    op.create_table(
        "pricing_records",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=True),
        sa.Column("provider", sa.String(16), nullable=False),
        sa.Column("sku", sa.String(255), nullable=True),
        sa.Column("region", sa.String(64), nullable=False),
        sa.Column("pricing_dimension", sa.String(64), nullable=False),
        sa.Column("rate_type", sa.String(32), nullable=False),
        sa.Column("rate", sa.Numeric(18, 6), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("unit", sa.String(64), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("tiers", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("attributes", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "idx_pricing_lookup",
        "pricing_records",
        ["provider", "sku", "region", "pricing_dimension", "rate_type", "effective_from", "effective_to"],
    )
    op.create_index("idx_pricing_tenant", "pricing_records", ["tenant_id", "provider", "sku"])

    op.create_table(
        "pricing_changes",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=True),
        sa.Column("provider", sa.String(16), nullable=False),
        sa.Column("sku", sa.String(255), nullable=True),
        sa.Column("region", sa.String(64), nullable=False),
        sa.Column("pricing_dimension", sa.String(64), nullable=False),
        sa.Column("rate_type", sa.String(32), nullable=False),
        sa.Column("old_rate", sa.Numeric(18, 6), nullable=True),
        sa.Column("new_rate", sa.Numeric(18, 6), nullable=False),
        sa.Column("percentage_change", sa.Numeric(8, 4), nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("change_reason", sa.String(255), nullable=True),
    )
    op.create_index("idx_pricing_changes_search", "pricing_changes", ["provider", "sku", "changed_at"])

    # -------------------------------------------------------------------------
    # 4. Forecasts & Milestones
    # -------------------------------------------------------------------------
    op.create_table(
        "forecasts",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("scope_type", sa.String(64), nullable=False),
        sa.Column("scope_id", sa.String(64), nullable=False),
        sa.Column("budget_id", sa.String(64), nullable=True),
        sa.Column("forecast_method", sa.String(64), nullable=False),
        sa.Column("evaluation_window_days", sa.Integer(), nullable=False),
        sa.Column("confidence_label", sa.String(32), nullable=False),
        sa.Column("predicted_amount", sa.Numeric(18, 6), nullable=False),
        sa.Column("predicted_breach_date", sa.Date(), nullable=True),
        sa.Column("baseline_amount", sa.Numeric(18, 6), nullable=True),
        sa.Column("details", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_forecasts_tenant_scope", "forecasts", ["tenant_id", "scope_type", "scope_id", "generated_at"])
    op.create_index("idx_forecasts_tenant_budget", "forecasts", ["tenant_id", "budget_id"])

    op.create_table(
        "forecast_milestones",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("forecast_id", sa.String(64), nullable=False),
        sa.Column("milestone_pct", sa.Integer(), nullable=False),
        sa.Column("actual_spend", sa.Numeric(18, 6), nullable=False),
        sa.Column("predicted_spend", sa.Numeric(18, 6), nullable=False),
        sa.Column("variance_pct", sa.Numeric(8, 4), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_milestones_tenant_forecast", "forecast_milestones", ["tenant_id", "forecast_id"])

    # -------------------------------------------------------------------------
    # 5. Reconciliation Reports & Investigations
    # -------------------------------------------------------------------------
    op.create_table(
        "reconciliation_reports",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("billing_period", sa.String(16), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("scope_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("platform_total", sa.Numeric(18, 6), nullable=False),
        sa.Column("provider_total", sa.Numeric(18, 6), nullable=False),
        sa.Column("variance_amount", sa.Numeric(18, 6), nullable=False),
        sa.Column("percentage_variance", sa.Numeric(8, 4), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("provenance", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("reconciled_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_reconcile_tenant_period", "reconciliation_reports", ["tenant_id", "billing_period", "provider"])

    op.create_table(
        "reconciliation_investigations",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("report_id", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("scope_id", sa.String(64), nullable=False),
        sa.Column("billing_period", sa.String(16), nullable=False),
        sa.Column("priority", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="OPEN"),
        sa.Column("classification", sa.String(64), nullable=False),
        sa.Column("platform_total", sa.Numeric(18, 6), nullable=False),
        sa.Column("provider_total", sa.Numeric(18, 6), nullable=False),
        sa.Column("variance_amount", sa.Numeric(18, 6), nullable=False),
        sa.Column("percentage_variance", sa.Numeric(8, 4), nullable=False),
        sa.Column("assigned_to", sa.String(255), nullable=True),
        sa.Column("resolution_notes", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_investigations_tenant_status", "reconciliation_investigations", ["tenant_id", "status"])

    op.create_table(
        "estimate_vs_actual_items",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("resource_id", sa.String(64), nullable=False),
        sa.Column("period", sa.String(16), nullable=False),
        sa.Column("estimated_cost", sa.Numeric(18, 6), nullable=False),
        sa.Column("actual_cost", sa.Numeric(18, 6), nullable=False),
        sa.Column("variance_amount", sa.Numeric(18, 6), nullable=False),
        sa.Column("variance_percentage", sa.Numeric(8, 4), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_est_vs_act_tenant", "estimate_vs_actual_items", ["tenant_id", "period"])

    # -------------------------------------------------------------------------
    # 6. Exchange Rates
    # -------------------------------------------------------------------------
    op.create_table(
        "exchange_rates",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("from_currency", sa.String(3), nullable=False),
        sa.Column("to_currency", sa.String(3), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("rate", sa.Numeric(18, 6), nullable=False),
        sa.Column("rate_type", sa.String(32), nullable=False, server_default="SPOT"),
        sa.Column("source", sa.String(64), nullable=False, server_default="SYSTEM"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "idx_exchange_rates_lookup",
        "exchange_rates",
        ["from_currency", "to_currency", "effective_date", "rate_type"],
        unique=True,
    )

    # -------------------------------------------------------------------------
    # 7. Threshold Rules, Overrides, & Results
    # -------------------------------------------------------------------------
    op.create_table(
        "threshold_rules",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("basis", sa.String(64), nullable=False),
        sa.Column("scope_type", sa.String(64), nullable=False),
        sa.Column("scope_id", sa.String(64), nullable=True),
        sa.Column("warning_threshold", sa.Numeric(18, 6), nullable=False),
        sa.Column("critical_threshold", sa.Numeric(18, 6), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("rule_payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_thresh_rules_tenant_basis", "threshold_rules", ["tenant_id", "basis"])

    op.create_table(
        "threshold_overrides",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("rule_id", sa.String(64), nullable=False),
        sa.Column("scope_id", sa.String(64), nullable=False),
        sa.Column("warning_threshold", sa.Numeric(18, 6), nullable=True),
        sa.Column("critical_threshold", sa.Numeric(18, 6), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_thresh_overrides_tenant_rule", "threshold_overrides", ["tenant_id", "rule_id", "scope_id"])

    op.create_table(
        "threshold_evaluation_results",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("rule_id", sa.String(64), nullable=False),
        sa.Column("scope_id", sa.String(64), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("current_value", sa.Numeric(18, 6), nullable=False),
        sa.Column("threshold_value", sa.Numeric(18, 6), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("result_payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_index("idx_thresh_results_tenant_state", "threshold_evaluation_results", ["tenant_id", "state", "evaluated_at"])

    # -------------------------------------------------------------------------
    # 8. Row-Level Security (RLS) & Privilege Grants
    # -------------------------------------------------------------------------
    tier3_tenant_tables = [
        "cost_restatements",
        "forecasts",
        "forecast_milestones",
        "reconciliation_reports",
        "reconciliation_investigations",
        "estimate_vs_actual_items",
        "threshold_rules",
        "threshold_overrides",
        "threshold_evaluation_results",
        "cost_fact",
        "agg_cost_scope_day",
        "agg_cost_scope_service_day",
    ]

    for tbl in tier3_tenant_tables:
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

    # Global tables (pricing_records, pricing_changes, exchange_rates)
    for tbl in ["pricing_records", "pricing_changes"]:
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
                        USING (tenant_id IS NULL OR tenant_id = current_setting('app.current_tenant_id', true) OR current_setting('cloudlens.bypass_rls', true) = 'on')
                        WITH CHECK (tenant_id IS NULL OR tenant_id = current_setting('app.current_tenant_id', true) OR current_setting('cloudlens.bypass_rls', true) = 'on');
                END IF;
            END $$;
        """)
        op.execute(f"GRANT ALL PRIVILEGES ON TABLE {tbl} TO cloudlens_app;")

    op.execute("GRANT ALL PRIVILEGES ON TABLE exchange_rates TO cloudlens_app;")
    op.execute("GRANT ALL PRIVILEGES ON TABLE budgets TO cloudlens_app;")
    op.execute("GRANT ALL PRIVILEGES ON TABLE cost_fact TO cloudlens_app;")
    op.execute("GRANT ALL PRIVILEGES ON TABLE cost_fact_default TO cloudlens_app;")
    op.execute("GRANT ALL PRIVILEGES ON TABLE agg_cost_scope_day TO cloudlens_app;")
    op.execute("GRANT ALL PRIVILEGES ON TABLE agg_cost_scope_service_day TO cloudlens_app;")


def downgrade() -> None:
    pass
