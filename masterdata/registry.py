"""Master Registry Manifest for CloudLens.

Enforces Prompt 45 Item 2:
- Manifest declaring every master in the system.
- Purpose, schema, global/tenant-scoped, editable, approval requirement, consuming modules, seed file.
- Rule: Nothing may be a master without appearing in the registry.
"""

from masterdata.models import MasterRegistryEntry

# ==============================================================================
# Master Registry Manifest
# ==============================================================================

SYSTEM_MASTER_REGISTRY: dict[str, MasterRegistryEntry] = {
    "SERVICE_CATEGORY": MasterRegistryEntry(
        code="SERVICE_CATEGORY",
        name="FOCUS Service Categories",
        purpose="Classifies cloud services into standardized taxonomy aligned to FOCUS 1.0.",
        schema_def={"is_focus_standard": "boolean"},
        is_tenant_scoped=False,
        is_editable=True,
        requires_approval=True,
        consuming_modules=["normalisation", "pricing", "ingestion", "reporting"],
        seed_file="masterdata/seeds/service_category.json",
        expected_review_period_days=180,
    ),
    "RESOURCE_TYPE": MasterRegistryEntry(
        code="RESOURCE_TYPE",
        name="Canonical Resource Types",
        purpose="Defines canonical infrastructure resource types and default monitoring roles.",
        schema_def={"default_monitoring_type": "string", "service_category": "string"},
        is_tenant_scoped=False,
        is_editable=True,
        requires_approval=True,
        consuming_modules=["inventory", "connectors", "normalisation", "monitoring"],
        seed_file="masterdata/seeds/resource_type.json",
        expected_review_period_days=90,
    ),
    "UNIT": MasterRegistryEntry(
        code="UNIT",
        name="Units of Measurement",
        purpose="Defines canonical symbols, dimensionality, and declarative conversion factors.",
        schema_def={
            "dimensionality": "string",
            "base_unit": "string",
            "scale_factor_to_base": "number",
            "offset_to_base": "number",
        },
        is_tenant_scoped=False,
        is_editable=True,
        requires_approval=True,
        consuming_modules=["normalisation", "pricing", "usage", "reporting"],
        seed_file="masterdata/seeds/unit.json",
        expected_review_period_days=180,
    ),
    "METRIC": MasterRegistryEntry(
        code="METRIC",
        name="Metric Catalogue",
        purpose="Defines operational metrics, aggregation methods, and applicable monitoring types.",
        schema_def={
            "unit_symbol": "string",
            "aggregation_method": "string",
            "applicable_monitoring_types": "array",
        },
        is_tenant_scoped=False,
        is_editable=True,
        requires_approval=True,
        consuming_modules=["monitoring", "runtime", "thresholds"],
        seed_file="masterdata/seeds/metric.json",
        expected_review_period_days=180,
    ),
    "PRICING_DIMENSION": MasterRegistryEntry(
        code="PRICING_DIMENSION",
        name="Reconciled Pricing Dimensions",
        purpose="Taxonomy of 29 pricing dimensions and models across consumption, structure, and qualifiers.",
        schema_def={
            "category": "string",
            "unit_symbol": "string",
            "aggregation_method": "string",
            "default_threshold_basis": "string",
            "is_custom_escape_hatch": "boolean",
            "provider_code": "string",
        },
        is_tenant_scoped=True,  # Tenants/providers can register custom escape hatch dimensions
        is_editable=True,
        requires_approval=True,
        consuming_modules=["pricing", "billing", "cost", "budgeting"],
        seed_file="masterdata/seeds/pricing_dimension.json",
        expected_review_period_days=90,
    ),
    "CLOUD_PROVIDER": MasterRegistryEntry(
        code="CLOUD_PROVIDER",
        name="Cloud Providers",
        purpose="Supported hyperscale cloud service providers and canonical boundaries.",
        schema_def={"api_endpoint": "string", "icon": "string"},
        is_tenant_scoped=False,
        is_editable=False,
        requires_approval=True,
        consuming_modules=["connectors", "ingestion", "auth", "inventory"],
        seed_file="masterdata/seeds/cloud_provider.json",
        expected_review_period_days=365,
    ),
    "RUNTIME_STATUS": MasterRegistryEntry(
        code="RUNTIME_STATUS",
        name="Resource Runtime Status",
        purpose="Canonical operational lifecycle states for compute, database, and container resources.",
        schema_def={"is_billable": "boolean", "color_hex": "string"},
        is_tenant_scoped=False,
        is_editable=False,
        requires_approval=True,
        consuming_modules=["inventory", "monitoring", "runtime", "recommendations"],
        seed_file="masterdata/seeds/runtime_status.json",
        expected_review_period_days=365,
    ),
    "CHARGE_CATEGORY": MasterRegistryEntry(
        code="CHARGE_CATEGORY",
        name="FOCUS Charge Categories",
        purpose="Standardized billing charge classifications (Usage, Purchase, Adjustment, Tax, Credit).",
        schema_def={"is_recurring": "boolean"},
        is_tenant_scoped=False,
        is_editable=False,
        requires_approval=True,
        consuming_modules=["billing", "cost", "amortisation", "reporting"],
        seed_file="masterdata/seeds/charge_category.json",
        expected_review_period_days=365,
    ),
    "PRICING_STATUS": MasterRegistryEntry(
        code="PRICING_STATUS",
        name="Resource Pricing Statuses",
        purpose="Seven canonical pricing classifications per BBP Section 16 (FREE, PAID, ESTIMATED, etc.).",
        schema_def={"requires_rate_lookup": "boolean"},
        is_tenant_scoped=False,
        is_editable=False,
        requires_approval=True,
        consuming_modules=["inventory", "pricing", "cost"],
        seed_file="masterdata/seeds/pricing_status.json",
        expected_review_period_days=365,
    ),
    "POLICY_SEVERITY": MasterRegistryEntry(
        code="POLICY_SEVERITY",
        name="Governance Policy Severities",
        purpose="Severity ranking for compliance, security, and cost anomaly policy violations.",
        schema_def={"sla_hours": "number", "level_order": "number"},
        is_tenant_scoped=False,
        is_editable=True,
        requires_approval=False,
        consuming_modules=["governance", "alerting", "notifications"],
        seed_file="masterdata/seeds/policy_severity.json",
        expected_review_period_days=180,
    ),
    "THRESHOLD_BAND": MasterRegistryEntry(
        code="THRESHOLD_BAND",
        name="Threshold Evaluation Bands",
        purpose="Standardized threshold evaluation states (Nominal, Warning, Critical, Exceeded).",
        schema_def={"urgency": "string", "triggers_alert": "boolean"},
        is_tenant_scoped=True,
        is_editable=True,
        requires_approval=False,
        consuming_modules=["budgeting", "alerting", "monitoring"],
        seed_file="masterdata/seeds/threshold_band.json",
        expected_review_period_days=180,
    ),
}


def get_registered_master(master_type: str) -> MasterRegistryEntry | None:
    """Retrieves registry metadata for a given master type."""
    return SYSTEM_MASTER_REGISTRY.get(master_type.strip().upper())


def list_registered_masters() -> list[MasterRegistryEntry]:
    """Returns all declared masters in the system."""
    return list(SYSTEM_MASTER_REGISTRY.values())


def is_master_registered(master_type: str) -> bool:
    """Verifies whether a master type is officially registered in the manifest."""
    return master_type.strip().upper() in SYSTEM_MASTER_REGISTRY
