"""Initial schema with multi-tenant inventory, scopes, and governance.

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-09-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Tenants
    op.create_table(
        "tenants",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("reporting_currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # 2. Scopes (Self-referencing tree)
    op.create_table(
        "scopes",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("parent_id", sa.String(64), sa.ForeignKey("scopes.id"), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("canonical_role", sa.String(32), nullable=False),
        sa.Column("provider", sa.String(16), nullable=False),
        sa.Column("native_type", sa.String(100), nullable=False),
        sa.Column("native_id", sa.String(500), nullable=False),
        sa.Column("materialized_path", sa.String(1000), nullable=False),
        sa.Column("depth", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_sub_group_applicable", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sub_group_absence_reason", sa.String(64), nullable=True),
        sa.Column("provider_native", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("source_provenance", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_scopes_tenant_path", "scopes", ["tenant_id", "materialized_path"])
    op.create_index("idx_scopes_tenant_parent", "scopes", ["tenant_id", "parent_id"])
    op.create_index("idx_scopes_tenant_native", "scopes", ["tenant_id", "provider", "native_id"])

    # 3. Scope History (SCD Type 2)
    op.create_table(
        "scope_history",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("scope_id", sa.String(64), nullable=False),
        sa.Column("parent_scope_id", sa.String(64), nullable=True),
        sa.Column("materialized_path", sa.String(1000), nullable=False),
        sa.Column("canonical_role", sa.String(32), nullable=False),
        sa.Column("native_id", sa.String(500), nullable=False),
        sa.Column("native_type", sa.String(100), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("change_reason", sa.String(100), nullable=False, server_default="INITIAL_DISCOVERY"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_scope_hist_tenant_scope_time", "scope_history", ["tenant_id", "scope_id", "effective_from", "effective_to"])

    # 4. Inventory Catalog Dimensions
    op.create_table(
        "business_units",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_bu_tenant_code", "business_units", ["tenant_id", "code"], unique=True)

    op.create_table(
        "cost_centers",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("business_unit_id", sa.String(64), sa.ForeignKey("business_units.id"), nullable=True),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_cc_tenant_code", "cost_centers", ["tenant_id", "code"], unique=True)

    op.create_table(
        "projects",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("cost_center_id", sa.String(64), sa.ForeignKey("cost_centers.id"), nullable=True),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_projects_tenant_code", "projects", ["tenant_id", "code"], unique=True)

    op.create_table(
        "owners",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("department", sa.String(100), nullable=False, server_default="Engineering"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_owners_tenant_email", "owners", ["tenant_id", "email"], unique=True)

    op.create_table(
        "applications",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("owner_id", sa.String(64), sa.ForeignKey("owners.id"), nullable=True),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("criticality", sa.String(32), nullable=False, server_default="BUSINESS_CRITICAL"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_apps_tenant_code", "applications", ["tenant_id", "code"], unique=True)

    op.create_table(
        "environments",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("category", sa.String(32), nullable=False, server_default="PRODUCTION"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_envs_tenant_name", "environments", ["tenant_id", "name"], unique=True)

    op.create_table(
        "services",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("provider", sa.String(16), nullable=False),
        sa.Column("service_code", sa.String(100), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("category", sa.String(32), nullable=False, server_default="OTHER"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_services_provider_code", "services", ["provider", "service_code"], unique=True)

    op.create_table(
        "resource_types",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("provider", sa.String(16), nullable=False),
        sa.Column("service_id", sa.String(64), sa.ForeignKey("services.id"), nullable=False),
        sa.Column("native_type_name", sa.String(255), nullable=False),
        sa.Column("canonical_type", sa.String(100), nullable=False),
        sa.Column("service_category", sa.String(32), nullable=False, server_default="OTHER"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_res_types_provider_native", "resource_types", ["provider", "native_type_name"], unique=True)

    op.create_table(
        "regions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("provider", sa.String(16), nullable=False),
        sa.Column("native_name", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("geography", sa.String(100), nullable=False),
        sa.Column("is_multi_az", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_regions_provider_native", "regions", ["provider", "native_name"], unique=True)

    op.create_table(
        "availability_zones",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("region_id", sa.String(64), sa.ForeignKey("regions.id"), nullable=False),
        sa.Column("provider", sa.String(16), nullable=False),
        sa.Column("native_zone_id", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_az_provider_region_zone", "availability_zones", ["provider", "region_id", "native_zone_id"], unique=True)

    # 5. Resources Table
    op.create_table(
        "resources",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("scope_id", sa.String(64), sa.ForeignKey("scopes.id"), nullable=False),
        sa.Column("native_id", sa.String(500), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("provider", sa.String(16), nullable=False),
        sa.Column("service_id", sa.String(64), sa.ForeignKey("services.id"), nullable=False),
        sa.Column("resource_type_id", sa.String(64), sa.ForeignKey("resource_types.id"), nullable=False),
        sa.Column("region_id", sa.String(64), sa.ForeignKey("regions.id"), nullable=False),
        sa.Column("availability_zone", sa.String(64), nullable=True),
        sa.Column("pricing_status", sa.String(32), nullable=False, server_default="PAID"),
        sa.Column("tags", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("application_id", sa.String(64), sa.ForeignKey("applications.id"), nullable=True),
        sa.Column("environment_id", sa.String(64), sa.ForeignKey("environments.id"), nullable=True),
        sa.Column("owner_id", sa.String(64), sa.ForeignKey("owners.id"), nullable=True),
        sa.Column("cost_center_id", sa.String(64), sa.ForeignKey("cost_centers.id"), nullable=True),
        sa.Column("business_unit_id", sa.String(64), sa.ForeignKey("business_units.id"), nullable=True),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=True),
        sa.Column("provider_native", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("source_provenance", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_resources_tenant_scope", "resources", ["tenant_id", "scope_id"])
    op.create_index("idx_resources_tenant_native", "resources", ["tenant_id", "provider", "native_id"])
    op.create_index("idx_resources_tenant_service", "resources", ["tenant_id", "service_id"])
    op.create_index("idx_resources_tenant_app", "resources", ["tenant_id", "application_id"])
    op.create_index("idx_resources_tenant_cost_center", "resources", ["tenant_id", "cost_center_id"])

    # 6. Governance & Management Tables
    op.create_table(
        "budgets",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("scope_id", sa.String(64), sa.ForeignKey("scopes.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("amount", sa.Numeric(18, 6), nullable=False),
        sa.Column("amount_state", sa.String(32), nullable=True),
        sa.Column("period", sa.String(32), nullable=False, server_default="MONTHLY"),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("threshold_set_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_budgets_tenant_scope", "budgets", ["tenant_id", "scope_id"])

    op.create_table(
        "threshold_sets",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("amber_percentage", sa.Numeric(5, 2), nullable=False, server_default="80.0"),
        sa.Column("red_percentage", sa.Numeric(5, 2), nullable=False, server_default="90.0"),
        sa.Column("critical_percentage", sa.Numeric(5, 2), nullable=False, server_default="100.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "policies",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("rule_type", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(32), nullable=False, server_default="MEDIUM"),
        sa.Column("parameters", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "alerts",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("alert_type", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(32), nullable=False, server_default="WARNING"),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="ACTIVE"),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_alerts_tenant_status", "alerts", ["tenant_id", "status", "triggered_at"])

    op.create_table(
        "sync_jobs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("connector_type", sa.String(16), nullable=False),
        sa.Column("scope_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="SCHEDULED"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rows_ingested", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_sync_jobs_tenant_connector", "sync_jobs", ["tenant_id", "connector_type", "started_at"])


def downgrade() -> None:
    op.drop_table("sync_jobs")
    op.drop_table("alerts")
    op.drop_table("policies")
    op.drop_table("threshold_sets")
    op.drop_table("budgets")
    op.drop_table("resources")
    op.drop_table("availability_zones")
    op.drop_table("regions")
    op.drop_table("resource_types")
    op.drop_table("services")
    op.drop_table("environments")
    op.drop_table("applications")
    op.drop_table("owners")
    op.drop_table("projects")
    op.drop_table("cost_centers")
    op.drop_table("business_units")
    op.drop_table("scope_history")
    op.drop_table("scopes")
    op.drop_table("tenants")
