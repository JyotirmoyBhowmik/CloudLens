"""Range-partitioned fact tables and append-only audit enforcement.

Revision ID: 002_partitioned_facts
Revises: 001_initial_schema
Create Date: 2026-09-26 00:01:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002_partitioned_facts"
down_revision: Union[str, None] = "001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. cost_fact PARTITION BY RANGE (billing_period_start)
    op.execute(
        """
        CREATE TABLE cost_fact (
            billing_period_start DATE NOT NULL,
            tenant_id VARCHAR(64) NOT NULL,
            id VARCHAR(64) NOT NULL,
            scope_id VARCHAR(64) NOT NULL,
            resource_id VARCHAR(64),
            service_id VARCHAR(64) NOT NULL,
            charge_period_start TIMESTAMPTZ NOT NULL,
            charge_period_end TIMESTAMPTZ NOT NULL,
            charge_category VARCHAR(32) NOT NULL DEFAULT 'Usage',
            charge_subcategory VARCHAR(64),
            billed_cost NUMERIC(18,6),
            billed_cost_state VARCHAR(32),
            effective_cost NUMERIC(18,6),
            effective_cost_state VARCHAR(32),
            contracted_cost NUMERIC(18,6),
            contracted_cost_state VARCHAR(32),
            list_cost NUMERIC(18,6),
            list_cost_state VARCHAR(32),
            billing_currency VARCHAR(3) NOT NULL DEFAULT 'USD',
            pricing_quantity NUMERIC(18,6),
            pricing_quantity_state VARCHAR(32),
            pricing_unit VARCHAR(64),
            provider_native JSONB NOT NULL DEFAULT '{}'::jsonb,
            source_provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (billing_period_start, tenant_id, id)
        ) PARTITION BY RANGE (billing_period_start);
        """
    )
    op.execute("CREATE INDEX idx_cost_fact_tenant_scope_time ON cost_fact (tenant_id, scope_id, charge_period_start);")
    op.execute("CREATE INDEX idx_cost_fact_tenant_service_time ON cost_fact (tenant_id, service_id, charge_period_start);")
    op.execute("CREATE INDEX idx_cost_fact_tenant_resource_time ON cost_fact (tenant_id, resource_id, charge_period_start);")

    # 2. usage_fact PARTITION BY RANGE (interval_start)
    op.execute(
        """
        CREATE TABLE usage_fact (
            interval_start TIMESTAMPTZ NOT NULL,
            tenant_id VARCHAR(64) NOT NULL,
            id VARCHAR(64) NOT NULL,
            scope_id VARCHAR(64) NOT NULL,
            resource_id VARCHAR(64) NOT NULL,
            interval_end TIMESTAMPTZ NOT NULL,
            metric_name VARCHAR(100) NOT NULL,
            usage_quantity NUMERIC(18,6),
            usage_quantity_state VARCHAR(32),
            usage_unit VARCHAR(64) NOT NULL,
            provider_native JSONB NOT NULL DEFAULT '{}'::jsonb,
            source_provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (interval_start, tenant_id, id)
        ) PARTITION BY RANGE (interval_start);
        """
    )
    op.execute("CREATE INDEX idx_usage_fact_tenant_res_time ON usage_fact (tenant_id, resource_id, interval_start);")
    op.execute("CREATE INDEX idx_usage_fact_tenant_scope_metric ON usage_fact (tenant_id, scope_id, metric_name, interval_start);")

    # 3. runtime_state PARTITION BY RANGE (window_start)
    op.execute(
        """
        CREATE TABLE runtime_state (
            window_start TIMESTAMPTZ NOT NULL,
            tenant_id VARCHAR(64) NOT NULL,
            id VARCHAR(64) NOT NULL,
            resource_id VARCHAR(64) NOT NULL,
            status VARCHAR(32) NOT NULL DEFAULT 'RUNNING',
            cpu_utilization_avg NUMERIC(5,2),
            cpu_utilization_state VARCHAR(32),
            memory_utilization_avg NUMERIC(5,2),
            memory_utilization_state VARCHAR(32),
            is_idle BOOLEAN,
            provider_native JSONB NOT NULL DEFAULT '{}'::jsonb,
            source_provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (window_start, tenant_id, id)
        ) PARTITION BY RANGE (window_start);
        """
    )
    op.execute("CREATE INDEX idx_runtime_state_tenant_res_time ON runtime_state (tenant_id, resource_id, window_start);")

    # 4. audit_event PARTITION BY RANGE (occurred_at)
    op.execute(
        """
        CREATE TABLE audit_event (
            occurred_at TIMESTAMPTZ NOT NULL,
            tenant_id VARCHAR(64) NOT NULL,
            id VARCHAR(64) NOT NULL,
            actor_id VARCHAR(255) NOT NULL,
            action VARCHAR(100) NOT NULL,
            entity_type VARCHAR(100) NOT NULL,
            entity_id VARCHAR(255) NOT NULL,
            payload_before JSONB,
            payload_after JSONB,
            correlation_id VARCHAR(64) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (occurred_at, tenant_id, id)
        ) PARTITION BY RANGE (occurred_at);
        """
    )
    op.execute("CREATE INDEX idx_audit_event_tenant_entity ON audit_event (tenant_id, entity_type, entity_id, occurred_at);")
    op.execute("CREATE INDEX idx_audit_event_tenant_actor ON audit_event (tenant_id, actor_id, occurred_at);")

    # 5. Pre-create DEFAULT partitions so write never fails per Prompt 06 Item 40
    op.execute("CREATE TABLE cost_fact_default PARTITION OF cost_fact DEFAULT;")
    op.execute("CREATE TABLE usage_fact_default PARTITION OF usage_fact DEFAULT;")
    op.execute("CREATE TABLE runtime_state_default PARTITION OF runtime_state DEFAULT;")
    op.execute("CREATE TABLE audit_event_default PARTITION OF audit_event DEFAULT;")

    # 6. Append-only triggers on audit_event per Prompt 06 Item 45
    op.execute(
        """
        CREATE OR REPLACE FUNCTION enforce_audit_event_append_only()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'PERMISSION_DENIED: audit_event table is append-only at the database level. UPDATE and DELETE operations are strictly prohibited (Prompt 06 Item 45).';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_audit_event_no_update
        BEFORE UPDATE ON audit_event
        FOR EACH ROW EXECUTE FUNCTION enforce_audit_event_append_only();
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_audit_event_no_delete
        BEFORE DELETE ON audit_event
        FOR EACH ROW EXECUTE FUNCTION enforce_audit_event_append_only();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_audit_event_no_delete ON audit_event;")
    op.execute("DROP TRIGGER IF EXISTS trg_audit_event_no_update ON audit_event;")
    op.execute("DROP FUNCTION IF EXISTS enforce_audit_event_append_only();")

    op.execute("DROP TABLE IF EXISTS audit_event CASCADE;")
    op.execute("DROP TABLE IF EXISTS runtime_state CASCADE;")
    op.execute("DROP TABLE IF EXISTS usage_fact CASCADE;")
    op.execute("DROP TABLE IF EXISTS cost_fact CASCADE;")
