"""Enterprise Master Catalogues & Unknown Entry Gap Registry Migration.

Revision ID: 005_catalogues_and_gap_registry
Revises: 004_expand_migrate_contract
Create Date: 2026-09-26 01:00:00.000000

Enforces Prompt 07 Items 47-53:
- ServiceCategory and Service catalogues aligned to FOCUS.
- ResourceType catalogue with default monitoring type and versioning.
- Unit catalogue with canonical symbol, dimensionality and declarative conversion factors.
- Metric catalogue with code, unit, aggregation method, applicable monitoring types.
- PricingDimension catalogue covering all twenty-nine dimensions plus escape hatch.
- Catalogue versioning and effective-dating.
- Unknown-entry gap registry for administrator workflow.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "005_catalogues_and_gap_registry"
down_revision: Union[str, None] = "004_expand_migrate_contract"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Service Categories (FOCUS aligned)
    op.create_table(
        "service_categories",
        sa.Column("code", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_focus_standard", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # 2. Service Mappings (Provider-Native Service Name Mappings with Effective-Dating)
    op.create_table(
        "service_mappings",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("service_id", sa.String(64), sa.ForeignKey("services.id"), nullable=False),
        sa.Column("provider", sa.String(16), nullable=False),
        sa.Column("native_service_name", sa.String(255), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "idx_svc_map_lookup",
        "service_mappings",
        ["provider", "native_service_name", "effective_from", "effective_to"],
    )

    # 3. Enhance Resource Types with Default Monitoring Type, Versioning, and Effective Dating
    op.add_column(
        "resource_types",
        sa.Column("default_monitoring_type", sa.String(64), nullable=False, server_default="UNKNOWN"),
    )
    op.add_column(
        "resource_types",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "resource_types",
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.add_column(
        "resource_types",
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "resource_types",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index(
        "idx_res_types_lookup",
        "resource_types",
        ["provider", "native_type_name", "effective_from", "effective_to"],
    )

    # 4. Unit Catalogue
    op.create_table(
        "unit_catalogue",
        sa.Column("symbol", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("dimensionality", sa.String(64), nullable=False),
        sa.Column("base_unit", sa.String(64), nullable=False),
        sa.Column("scale_factor_to_base", sa.Numeric(36, 18), nullable=False),
        sa.Column("offset_to_base", sa.Numeric(36, 18), nullable=False, server_default="0"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_units_dim", "unit_catalogue", ["dimensionality"])

    # 5. Metric Catalogue
    op.create_table(
        "metric_catalogue",
        sa.Column("code", sa.String(100), primary_key=True),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("unit_symbol", sa.String(64), sa.ForeignKey("unit_catalogue.symbol"), nullable=False),
        sa.Column("aggregation_method", sa.String(32), nullable=False),
        sa.Column("applicable_monitoring_types", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # 6. Pricing Dimension Catalogue (29 Reconciled Dimensions + Escape Hatch)
    op.create_table(
        "pricing_dimension_catalogue",
        sa.Column("code", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("unit_symbol", sa.String(64), nullable=False),
        sa.Column("aggregation_method", sa.String(32), nullable=False),
        sa.Column("default_threshold_basis", sa.String(255), nullable=False),
        sa.Column("applicability_rules", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("is_custom_escape_hatch", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("provider_code", sa.String(16), nullable=True),
        sa.Column("example_services", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # 7. Unknown-Entry Catalogue Gap Registry
    op.create_table(
        "catalogue_gaps",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=True),
        sa.Column("catalogue_type", sa.String(32), nullable=False),
        sa.Column("provider", sa.String(16), nullable=False),
        sa.Column("native_identifier", sa.String(500), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="OPEN"),
        sa.Column("occurrence_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("context_payload", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("resolution_notes", sa.Text(), nullable=True),
        sa.Column("resolved_by", sa.String(255), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "idx_cat_gaps_lookup",
        "catalogue_gaps",
        ["catalogue_type", "provider", "native_identifier", "status"],
    )
    op.create_index(
        "idx_cat_gaps_status",
        "catalogue_gaps",
        ["status", "last_seen_at"],
    )


def downgrade() -> None:
    op.drop_table("catalogue_gaps")
    op.drop_table("pricing_dimension_catalogue")
    op.drop_table("metric_catalogue")
    op.drop_table("unit_catalogue")
    op.drop_index("idx_res_types_lookup", table_name="resource_types")
    op.drop_column("resource_types", "is_active")
    op.drop_column("resource_types", "effective_to")
    op.drop_column("resource_types", "effective_from")
    op.drop_column("resource_types", "version")
    op.drop_column("resource_types", "default_monitoring_type")
    op.drop_table("service_mappings")
    op.drop_table("service_categories")
