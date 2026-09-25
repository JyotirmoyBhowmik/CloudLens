"""SQLAlchemy Declarative Physical Schema Definitions.

Enforces Prompt 06 Items 39, 40, 42, 44:
- Full schema from BBP Section 39.2 (PKs, UKs, FKs, indexes).
- Tenant_id on every multi-tenant table and in the leading position of composite indexes.
- Range-partitioned fact tables: cost_fact (billing_period_start), usage_fact (interval_start),
  runtime_state (window_start), audit_event (occurred_at).
- Materialized aggregate tables: (scope, service, day) and (scope, day).
"""

from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


# ==============================================================================
# 1. Multi-Tenant Organization & Hierarchy Boundary
# ==============================================================================


class TenantModel(Base):
    __tablename__ = "tenants"

    id = Column(String(64), primary_key=True)
    name = Column(String(255), nullable=False)
    reporting_currency = Column(String(3), nullable=False, default="USD")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    scopes = relationship("ScopeModel", back_populates="tenant", cascade="all, delete-orphan")


class ScopeModel(Base):
    __tablename__ = "scopes"

    id = Column(String(64), primary_key=True)
    tenant_id = Column(String(64), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    parent_id = Column(String(64), ForeignKey("scopes.id"), nullable=True)
    name = Column(String(255), nullable=False)
    canonical_role = Column(
        String(32), nullable=False
    )  # TENANT, ROOT_GROUP, GROUP, BILLING_BOUNDARY, etc.
    provider = Column(String(16), nullable=False)  # aws, azure, gcp, oci, canonical
    native_type = Column(
        String(100), nullable=False
    )  # ManagementGroup, OrganizationalUnit, Folder, Compartment
    native_id = Column(String(500), nullable=False)
    materialized_path = Column(String(1000), nullable=False)
    depth = Column(Integer, nullable=False, default=0)
    is_sub_group_applicable = Column(Boolean, nullable=False, default=True)
    sub_group_absence_reason = Column(String(64), nullable=True)
    provider_native = Column(JSONB, nullable=False, server_default="{}")
    source_provenance = Column(JSONB, nullable=False, server_default="{}")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    tenant = relationship("TenantModel", back_populates="scopes")
    children = relationship("ScopeModel", backref="parent", remote_side=[id])

    __table_args__ = (
        Index("idx_scopes_tenant_path", "tenant_id", "materialized_path"),
        Index("idx_scopes_tenant_parent", "tenant_id", "parent_id"),
        Index("idx_scopes_tenant_native", "tenant_id", "provider", "native_id"),
        Index("idx_scopes_tenant_role", "tenant_id", "canonical_role"),
    )


class ScopeHistoryModel(Base):
    """SCD Type 2 materialized path and lineage history."""

    __tablename__ = "scope_history"

    id = Column(String(64), primary_key=True)
    tenant_id = Column(String(64), nullable=False)
    scope_id = Column(String(64), nullable=False)
    parent_scope_id = Column(String(64), nullable=True)
    materialized_path = Column(String(1000), nullable=False)
    canonical_role = Column(String(32), nullable=False)
    native_id = Column(String(500), nullable=False)
    native_type = Column(String(100), nullable=False)
    effective_from = Column(DateTime(timezone=True), nullable=False)
    effective_to = Column(DateTime(timezone=True), nullable=True)
    change_reason = Column(String(100), nullable=False, default="INITIAL_DISCOVERY")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        Index(
            "idx_scope_hist_tenant_scope_time",
            "tenant_id",
            "scope_id",
            "effective_from",
            "effective_to",
        ),
        Index("idx_scope_hist_tenant_path", "tenant_id", "materialized_path"),
    )


# ==============================================================================
# 2. Structural Inventory & Organizational Dimensions
# ==============================================================================


class BusinessUnitModel(Base):
    __tablename__ = "business_units"

    id = Column(String(64), primary_key=True)
    tenant_id = Column(String(64), nullable=False)
    code = Column(String(64), nullable=False)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (Index("idx_bu_tenant_code", "tenant_id", "code", unique=True),)


class CostCenterModel(Base):
    __tablename__ = "cost_centers"

    id = Column(String(64), primary_key=True)
    tenant_id = Column(String(64), nullable=False)
    business_unit_id = Column(String(64), ForeignKey("business_units.id"), nullable=True)
    code = Column(String(64), nullable=False)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (Index("idx_cc_tenant_code", "tenant_id", "code", unique=True),)


class ProjectModel(Base):
    __tablename__ = "projects"

    id = Column(String(64), primary_key=True)
    tenant_id = Column(String(64), nullable=False)
    cost_center_id = Column(String(64), ForeignKey("cost_centers.id"), nullable=True)
    code = Column(String(64), nullable=False)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (Index("idx_projects_tenant_code", "tenant_id", "code", unique=True),)


class OwnerModel(Base):
    __tablename__ = "owners"

    id = Column(String(64), primary_key=True)
    tenant_id = Column(String(64), nullable=False)
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)
    department = Column(String(100), nullable=False, default="Engineering")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (Index("idx_owners_tenant_email", "tenant_id", "email", unique=True),)


class ApplicationModel(Base):
    __tablename__ = "applications"

    id = Column(String(64), primary_key=True)
    tenant_id = Column(String(64), nullable=False)
    owner_id = Column(String(64), ForeignKey("owners.id"), nullable=True)
    code = Column(String(64), nullable=False)
    name = Column(String(255), nullable=False)
    criticality = Column(String(32), nullable=False, default="BUSINESS_CRITICAL")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (Index("idx_apps_tenant_code", "tenant_id", "code", unique=True),)


class EnvironmentModel(Base):
    __tablename__ = "environments"

    id = Column(String(64), primary_key=True)
    tenant_id = Column(String(64), nullable=False)
    name = Column(String(100), nullable=False)
    category = Column(String(32), nullable=False, default="PRODUCTION")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (Index("idx_envs_tenant_name", "tenant_id", "name", unique=True),)


class ServiceModel(Base):
    __tablename__ = "services"

    id = Column(String(64), primary_key=True)
    provider = Column(String(16), nullable=False)
    service_code = Column(String(100), nullable=False)
    name = Column(String(255), nullable=False)
    category = Column(String(32), nullable=False, default="OTHER")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (Index("idx_services_provider_code", "provider", "service_code", unique=True),)


class ResourceTypeModel(Base):
    __tablename__ = "resource_types"

    id = Column(String(64), primary_key=True)
    provider = Column(String(16), nullable=False)
    service_id = Column(String(64), ForeignKey("services.id"), nullable=False)
    native_type_name = Column(String(255), nullable=False)
    canonical_type = Column(String(100), nullable=False)
    service_category = Column(String(32), nullable=False, default="OTHER")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        Index("idx_res_types_provider_native", "provider", "native_type_name", unique=True),
    )


class RegionModel(Base):
    __tablename__ = "regions"

    id = Column(String(64), primary_key=True)
    provider = Column(String(16), nullable=False)
    native_name = Column(String(64), nullable=False)
    display_name = Column(String(255), nullable=False)
    geography = Column(String(100), nullable=False)
    is_multi_az = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (Index("idx_regions_provider_native", "provider", "native_name", unique=True),)


class AvailabilityZoneModel(Base):
    __tablename__ = "availability_zones"

    id = Column(String(64), primary_key=True)
    region_id = Column(String(64), ForeignKey("regions.id"), nullable=False)
    provider = Column(String(16), nullable=False)
    native_zone_id = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        Index(
            "idx_az_provider_region_zone", "provider", "region_id", "native_zone_id", unique=True
        ),
    )


class ResourceModel(Base):
    __tablename__ = "resources"

    id = Column(String(64), primary_key=True)
    tenant_id = Column(String(64), nullable=False)
    scope_id = Column(String(64), ForeignKey("scopes.id"), nullable=False)
    native_id = Column(String(500), nullable=False)
    name = Column(String(255), nullable=False)
    provider = Column(String(16), nullable=False)
    service_id = Column(String(64), ForeignKey("services.id"), nullable=False)
    resource_type_id = Column(String(64), ForeignKey("resource_types.id"), nullable=False)
    region_id = Column(String(64), ForeignKey("regions.id"), nullable=False)
    availability_zone = Column(String(64), nullable=True)
    pricing_status = Column(String(32), nullable=False, default="PAID")
    tags = Column(JSONB, nullable=False, server_default="[]")
    application_id = Column(String(64), ForeignKey("applications.id"), nullable=True)
    environment_id = Column(String(64), ForeignKey("environments.id"), nullable=True)
    owner_id = Column(String(64), ForeignKey("owners.id"), nullable=True)
    cost_center_id = Column(String(64), ForeignKey("cost_centers.id"), nullable=True)
    business_unit_id = Column(String(64), ForeignKey("business_units.id"), nullable=True)
    project_id = Column(String(64), ForeignKey("projects.id"), nullable=True)
    provider_native = Column(JSONB, nullable=False, server_default="{}")
    source_provenance = Column(JSONB, nullable=False, server_default="{}")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("idx_resources_tenant_scope", "tenant_id", "scope_id"),
        Index("idx_resources_tenant_native", "tenant_id", "provider", "native_id"),
        Index("idx_resources_tenant_service", "tenant_id", "service_id"),
        Index("idx_resources_tenant_app", "tenant_id", "application_id"),
        Index("idx_resources_tenant_cost_center", "tenant_id", "cost_center_id"),
    )


# ==============================================================================
# 3. Partitioned Fact Tables (Range Partitioning per Item 40)
# ==============================================================================


class CostFactModel(Base):
    """Range-partitioned FOCUS 1.0 fact table partitioned by billing_period_start."""

    __tablename__ = "cost_fact"

    billing_period_start = Column(Date, primary_key=True, nullable=False)
    tenant_id = Column(String(64), primary_key=True, nullable=False)
    id = Column(String(64), primary_key=True, nullable=False)

    scope_id = Column(String(64), nullable=False)
    resource_id = Column(String(64), nullable=True)
    service_id = Column(String(64), nullable=False)
    charge_period_start = Column(DateTime(timezone=True), nullable=False)
    charge_period_end = Column(DateTime(timezone=True), nullable=False)
    charge_category = Column(String(32), nullable=False, default="Usage")
    charge_subcategory = Column(String(64), nullable=True)

    # 4-State Null Discipline numeric columns & state descriptors
    billed_cost = Column(Numeric(18, 6), nullable=True)
    billed_cost_state = Column(String(32), nullable=True)
    effective_cost = Column(Numeric(18, 6), nullable=True)
    effective_cost_state = Column(String(32), nullable=True)
    contracted_cost = Column(Numeric(18, 6), nullable=True)
    contracted_cost_state = Column(String(32), nullable=True)
    list_cost = Column(Numeric(18, 6), nullable=True)
    list_cost_state = Column(String(32), nullable=True)

    billing_currency = Column(String(3), nullable=False, default="USD")
    pricing_quantity = Column(Numeric(18, 6), nullable=True)
    pricing_quantity_state = Column(String(32), nullable=True)
    pricing_unit = Column(String(64), nullable=True)

    provider_native = Column(JSONB, nullable=False, server_default="{}")
    source_provenance = Column(JSONB, nullable=False, server_default="{}")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        Index("idx_cost_fact_tenant_scope_time", "tenant_id", "scope_id", "charge_period_start"),
        Index(
            "idx_cost_fact_tenant_service_time", "tenant_id", "service_id", "charge_period_start"
        ),
        Index(
            "idx_cost_fact_tenant_resource_time", "tenant_id", "resource_id", "charge_period_start"
        ),
        {"postgresql_partition_by": "RANGE (billing_period_start)"},
    )


class UsageFactModel(Base):
    """Range-partitioned usage fact table partitioned by interval_start."""

    __tablename__ = "usage_fact"

    interval_start = Column(DateTime(timezone=True), primary_key=True, nullable=False)
    tenant_id = Column(String(64), primary_key=True, nullable=False)
    id = Column(String(64), primary_key=True, nullable=False)

    scope_id = Column(String(64), nullable=False)
    resource_id = Column(String(64), nullable=False)
    interval_end = Column(DateTime(timezone=True), nullable=False)
    metric_name = Column(String(100), nullable=False)

    usage_quantity = Column(Numeric(18, 6), nullable=True)
    usage_quantity_state = Column(String(32), nullable=True)
    usage_unit = Column(String(64), nullable=False)

    provider_native = Column(JSONB, nullable=False, server_default="{}")
    source_provenance = Column(JSONB, nullable=False, server_default="{}")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        Index("idx_usage_fact_tenant_res_time", "tenant_id", "resource_id", "interval_start"),
        Index(
            "idx_usage_fact_tenant_scope_metric",
            "tenant_id",
            "scope_id",
            "metric_name",
            "interval_start",
        ),
        {"postgresql_partition_by": "RANGE (interval_start)"},
    )


class RuntimeStateModel(Base):
    """Range-partitioned runtime utilization snapshot partitioned by window_start."""

    __tablename__ = "runtime_state"

    window_start = Column(DateTime(timezone=True), primary_key=True, nullable=False)
    tenant_id = Column(String(64), primary_key=True, nullable=False)
    id = Column(String(64), primary_key=True, nullable=False)

    resource_id = Column(String(64), nullable=False)
    status = Column(String(32), nullable=False, default="RUNNING")
    cpu_utilization_avg = Column(Numeric(5, 2), nullable=True)
    cpu_utilization_state = Column(String(32), nullable=True)
    memory_utilization_avg = Column(Numeric(5, 2), nullable=True)
    memory_utilization_state = Column(String(32), nullable=True)
    is_idle = Column(Boolean, nullable=True)

    provider_native = Column(JSONB, nullable=False, server_default="{}")
    source_provenance = Column(JSONB, nullable=False, server_default="{}")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        Index("idx_runtime_state_tenant_res_time", "tenant_id", "resource_id", "window_start"),
        {"postgresql_partition_by": "RANGE (window_start)"},
    )


class AuditEventModel(Base):
    """Append-only audit event table partitioned by occurred_at."""

    __tablename__ = "audit_event"

    occurred_at = Column(DateTime(timezone=True), primary_key=True, nullable=False)
    tenant_id = Column(String(64), primary_key=True, nullable=False)
    id = Column(String(64), primary_key=True, nullable=False)

    actor_id = Column(String(255), nullable=False)
    action = Column(String(100), nullable=False)
    entity_type = Column(String(100), nullable=False)
    entity_id = Column(String(255), nullable=False)
    payload_before = Column(JSONB, nullable=True)
    payload_after = Column(JSONB, nullable=True)
    correlation_id = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        Index(
            "idx_audit_event_tenant_entity", "tenant_id", "entity_type", "entity_id", "occurred_at"
        ),
        Index("idx_audit_event_tenant_actor", "tenant_id", "actor_id", "occurred_at"),
        {"postgresql_partition_by": "RANGE (occurred_at)"},
    )


# ==============================================================================
# 4. Materialized Daily Aggregate Tables (Item 42)
# ==============================================================================


class AggCostScopeServiceDayModel(Base):
    """Pre-computed materialized aggregate slice by (tenant, scope, service, day)."""

    __tablename__ = "agg_cost_scope_service_day"

    tenant_id = Column(String(64), primary_key=True, nullable=False)
    scope_id = Column(String(64), primary_key=True, nullable=False)
    service_id = Column(String(64), primary_key=True, nullable=False)
    day = Column(Date, primary_key=True, nullable=False)

    billed_cost = Column(Numeric(18, 6), nullable=False, default=0)
    effective_cost = Column(Numeric(18, 6), nullable=False, default=0)
    row_count = Column(Integer, nullable=False, default=0)
    refreshed_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("idx_agg_scope_svc_day_tenant_day", "tenant_id", "day"),
        Index("idx_agg_scope_svc_day_tenant_scope", "tenant_id", "scope_id", "day"),
    )


class AggCostScopeDayModel(Base):
    """Pre-computed materialized aggregate slice by (tenant, scope, day)."""

    __tablename__ = "agg_cost_scope_day"

    tenant_id = Column(String(64), primary_key=True, nullable=False)
    scope_id = Column(String(64), primary_key=True, nullable=False)
    day = Column(Date, primary_key=True, nullable=False)

    billed_cost = Column(Numeric(18, 6), nullable=False, default=0)
    effective_cost = Column(Numeric(18, 6), nullable=False, default=0)
    row_count = Column(Integer, nullable=False, default=0)
    refreshed_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (Index("idx_agg_scope_day_tenant_day", "tenant_id", "day"),)


# ==============================================================================
# 5. Governance, Policy & Budgeting Tables
# ==============================================================================


class BudgetModel(Base):
    __tablename__ = "budgets"

    id = Column(String(64), primary_key=True)
    tenant_id = Column(String(64), nullable=False)
    scope_id = Column(String(64), ForeignKey("scopes.id"), nullable=False)
    name = Column(String(255), nullable=False)
    amount = Column(Numeric(18, 6), nullable=False)
    amount_state = Column(String(32), nullable=True)
    period = Column(String(32), nullable=False, default="MONTHLY")
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=True)
    threshold_set_id = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (Index("idx_budgets_tenant_scope", "tenant_id", "scope_id"),)


class ThresholdSetModel(Base):
    __tablename__ = "threshold_sets"

    id = Column(String(64), primary_key=True)
    tenant_id = Column(String(64), nullable=False)
    name = Column(String(100), nullable=False)
    amber_percentage = Column(Numeric(5, 2), nullable=False, default=Decimal("80.0"))
    red_percentage = Column(Numeric(5, 2), nullable=False, default=Decimal("90.0"))
    critical_percentage = Column(Numeric(5, 2), nullable=False, default=Decimal("100.0"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (Index("idx_threshold_sets_tenant", "tenant_id", "name"),)


class PolicyModel(Base):
    __tablename__ = "policies"

    id = Column(String(64), primary_key=True)
    tenant_id = Column(String(64), nullable=False)
    name = Column(String(255), nullable=False)
    rule_type = Column(String(64), nullable=False)
    severity = Column(String(32), nullable=False, default="MEDIUM")
    parameters = Column(JSONB, nullable=False, server_default="{}")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (Index("idx_policies_tenant_type", "tenant_id", "rule_type"),)


class AlertModel(Base):
    __tablename__ = "alerts"

    id = Column(String(64), primary_key=True)
    tenant_id = Column(String(64), nullable=False)
    alert_type = Column(String(64), nullable=False)
    severity = Column(String(32), nullable=False, default="WARNING")
    message = Column(Text, nullable=False)
    status = Column(String(32), nullable=False, default="ACTIVE")
    triggered_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (Index("idx_alerts_tenant_status", "tenant_id", "status", "triggered_at"),)


class SyncJobModel(Base):
    __tablename__ = "sync_jobs"

    id = Column(String(64), primary_key=True)
    tenant_id = Column(String(64), nullable=False)
    connector_type = Column(String(16), nullable=False)
    scope_id = Column(String(64), nullable=False)
    status = Column(String(32), nullable=False, default="SCHEDULED")
    started_at = Column(DateTime(timezone=True), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    rows_ingested = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        Index("idx_sync_jobs_tenant_connector", "tenant_id", "connector_type", "started_at"),
    )
