"""Materialized daily aggregate rollup tables for dashboard acceleration.

Revision ID: 003_materialized_aggregates
Revises: 002_partitioned_facts
Create Date: 2026-09-26 00:02:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "003_materialized_aggregates"
down_revision: Union[str, None] = "002_partitioned_facts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. agg_cost_scope_service_day
    op.create_table(
        "agg_cost_scope_service_day",
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("scope_id", sa.String(64), nullable=False),
        sa.Column("service_id", sa.String(64), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("billed_cost", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("effective_cost", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("refreshed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("tenant_id", "scope_id", "service_id", "day"),
    )
    op.create_index("idx_agg_scope_svc_day_tenant_day", "agg_cost_scope_service_day", ["tenant_id", "day"])
    op.create_index("idx_agg_scope_svc_day_tenant_scope", "agg_cost_scope_service_day", ["tenant_id", "scope_id", "day"])

    # 2. agg_cost_scope_day
    op.create_table(
        "agg_cost_scope_day",
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("scope_id", sa.String(64), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("billed_cost", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("effective_cost", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("refreshed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("tenant_id", "scope_id", "day"),
    )
    op.create_index("idx_agg_scope_day_tenant_day", "agg_cost_scope_day", ["tenant_id", "day"])


def downgrade() -> None:
    op.drop_table("agg_cost_scope_day")
    op.drop_table("agg_cost_scope_service_day")
