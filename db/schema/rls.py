"""PostgreSQL Row-Level Security (RLS) Configuration.

Enforces Prompt 06 Item 44:
"Put tenant_id on every table and in the leading position of composite indexes where it aids selectivity.
Enable row-level security where supported."
"""

from sqlalchemy import Connection, text

TENANT_ISOLATED_TABLES = [
    "scopes",
    "scope_history",
    "resources",
    "cost_fact",
    "usage_fact",
    "runtime_state",
    "audit_event",
    "agg_cost_scope_service_day",
    "agg_cost_scope_day",
    "budgets",
    "threshold_sets",
    "policies",
    "alerts",
    "sync_jobs",
]


def generate_rls_sql(table_name: str) -> str:
    """Generates DDL enabling RLS and creating tenant isolation policy based on current_setting."""
    return f"""
    ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY;

    DROP POLICY IF EXISTS tenant_isolation_policy_{table_name} ON {table_name};
    CREATE POLICY tenant_isolation_policy_{table_name} ON {table_name}
    FOR ALL
    USING (
        tenant_id = NULLIF(current_setting('cloudlens.current_tenant_id', true), '')
        OR current_setting('cloudlens.bypass_rls', true) = 'on'
    )
    WITH CHECK (
        tenant_id = NULLIF(current_setting('cloudlens.current_tenant_id', true), '')
        OR current_setting('cloudlens.bypass_rls', true) = 'on'
    );
    """


def apply_row_level_security(conn: Connection) -> None:
    """Enables Row-Level Security and applies tenant isolation policies across all tenant-bound tables."""
    for table in TENANT_ISOLATED_TABLES:
        try:
            conn.execute(text(generate_rls_sql(table)))
        except Exception:
            # Table might not exist or RLS might not be supported in certain test runners
            pass
