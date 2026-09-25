"""Master Data Management Framework & Registry Migration.

Revision ID: 006_master_data_framework
Revises: 005_catalogues_and_gap_registry
Create Date: 2026-09-26 02:00:00.000000

Enforces Prompt 45 Items 1-10:
- master_registry: manifest declaring every registered master in the system.
- master_data_records: universal effective-dated master record model.
- master_data_audit: full change history and lineage audit log.
- master_data_import_audit: import batch audit trail.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "006_master_data_framework"
down_revision: Union[str, None] = "005_catalogues_and_gap_registry"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Master Registry Manifest Table
    op.create_table(
        "master_registry",
        sa.Column("code", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("schema_def", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("is_tenant_scoped", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_editable", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("requires_approval", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("consuming_modules", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("seed_file", sa.String(255), nullable=False),
        sa.Column("expected_review_period_days", sa.Integer(), nullable=False, server_default="180"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # 2. Master Data Records Table
    op.create_table(
        "master_data_records",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("master_type", sa.String(64), sa.ForeignKey("master_registry.code"), nullable=False),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("parent_code", sa.String(100), nullable=True),
        sa.Column("attributes", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("tenant_id", sa.String(64), nullable=True),
        sa.Column("created_by", sa.String(255), nullable=False, server_default="SYSTEM"),
        sa.Column("approved_by", sa.String(255), nullable=True),
        sa.Column("lifecycle_status", sa.String(32), nullable=False, server_default="PUBLISHED"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "idx_master_type_code_time",
        "master_data_records",
        ["master_type", "code", "effective_from", "effective_to"],
    )
    op.create_index(
        "idx_master_tenant_type",
        "master_data_records",
        ["tenant_id", "master_type"],
    )

    # 3. Master Data Lineage & Audit Log Table
    op.create_table(
        "master_data_audit",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("record_id", sa.String(64), nullable=False),
        sa.Column("master_type", sa.String(64), nullable=False),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("changed_by", sa.String(255), nullable=False),
        sa.Column("change_reason", sa.Text(), nullable=False),
        sa.Column("diff_payload", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("snapshot", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "idx_master_audit_record",
        "master_data_audit",
        ["master_type", "code", "created_at"],
    )

    # 4. Master Data Import Audit Table
    op.create_table(
        "master_data_import_audit",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("master_type", sa.String(64), nullable=False),
        sa.Column("format", sa.String(16), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("success_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("errors_payload", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("imported_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("master_data_import_audit")
    op.drop_table("master_data_audit")
    op.drop_table("master_data_records")
    op.drop_table("master_registry")
