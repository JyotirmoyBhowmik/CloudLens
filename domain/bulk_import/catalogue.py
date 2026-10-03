"""Importable Entity Catalogue and Specification Registry (Prompt 53).

Maintains the master-data configuration declaring:
- Column definitions, valid master references, required flags, and help text.
- Natural keys for row-level matching and diffing.
- Master-data configured atomicity policies (ALL_OR_NOTHING vs PARTIAL_SUCCESS).
- Dynamic integration with Prompt 45 SYSTEM_MASTER_REGISTRY.
"""

from __future__ import annotations

from domain.bulk_import.models import (
    AtomicityPolicy,
    ColumnDefinition,
    EntityImportMetadata,
    ImportMode,
)
from masterdata.registry import SYSTEM_MASTER_REGISTRY, list_registered_masters
from masterdata.service import get_master_data_service


def _build_core_catalogue() -> dict[str, EntityImportMetadata]:
    """Builds the canonical catalogue of core domain importable entities."""
    return {
        "APPLICATION": EntityImportMetadata(
            entity_type="APPLICATION",
            display_name="Enterprise Applications",
            description="Enterprise application portfolio records with criticality, ownership, and financial links.",
            natural_key_columns=["code"],
            default_atomicity_policy=AtomicityPolicy.PARTIAL_SUCCESS,
            allowed_modes=[
                ImportMode.INSERT_ONLY,
                ImportMode.UPDATE_ONLY,
                ImportMode.UPSERT,
                ImportMode.DEACTIVATE_MISSING,
            ],
            rollback_window_hours=48,
            columns=[
                ColumnDefinition(
                    name="code",
                    data_type="string",
                    required=True,
                    description="Unique application portfolio code (e.g. APP-PAYMENTS, APP-CHECKOUT)",
                    sample_value="APP-PORTAL-01",
                ),
                ColumnDefinition(
                    name="name",
                    data_type="string",
                    required=True,
                    description="Human-readable application title",
                    sample_value="Customer Self-Service Portal",
                ),
                ColumnDefinition(
                    name="criticality_tier",
                    data_type="string",
                    required=False,
                    description="Operational criticality tier",
                    master_reference="POLICY_SEVERITY",
                    allowed_values=["CRITICAL", "HIGH", "MEDIUM", "LOW"],
                    sample_value="HIGH",
                ),
                ColumnDefinition(
                    name="business_owner",
                    data_type="string",
                    required=False,
                    description="Accountable business owner or team ID",
                    master_reference="OWNER_TEAM",
                    sample_value="TEAM-FINOPS",
                ),
                ColumnDefinition(
                    name="technical_owner",
                    data_type="string",
                    required=False,
                    description="Lead engineer or architecture contact ID",
                    master_reference="OWNER_TEAM",
                    sample_value="TEAM-PLATFORM",
                ),
                ColumnDefinition(
                    name="cost_centre",
                    data_type="string",
                    required=False,
                    description="Financial cost centre code funding this application",
                    master_reference="COST_CENTRE",
                    sample_value="CC-101",
                ),
                ColumnDefinition(
                    name="business_unit",
                    data_type="string",
                    required=False,
                    description="Sponsoring business unit code",
                    master_reference="BUSINESS_UNIT",
                    sample_value="BU-RETAIL",
                ),
                ColumnDefinition(
                    name="lifecycle_state",
                    data_type="string",
                    required=False,
                    description="Lifecycle state: ACTIVE, DEPRECATED, or PLANNED",
                    allowed_values=["ACTIVE", "DEPRECATED", "PLANNED"],
                    sample_value="ACTIVE",
                ),
            ],
        ),
        "RESOURCE_CURATION": EntityImportMetadata(
            entity_type="RESOURCE_CURATION",
            display_name="Resource Ownership & Curated Attributes",
            description="Bulk curated assignment of owners, applications, environments, and cost centres to cloud resources.",
            natural_key_columns=["resource_id"],
            default_atomicity_policy=AtomicityPolicy.PARTIAL_SUCCESS,
            allowed_modes=[ImportMode.UPDATE_ONLY, ImportMode.UPSERT],
            rollback_window_hours=24,
            columns=[
                ColumnDefinition(
                    name="resource_id",
                    data_type="string",
                    required=True,
                    description="Canonical resource identifier (e.g. res-vm-001 or native provider ARN/URI)",
                    sample_value="res-vm-001",
                ),
                ColumnDefinition(
                    name="owner_id",
                    data_type="string",
                    required=False,
                    description="Curated accountable owner or team ID",
                    master_reference="OWNER_TEAM",
                    sample_value="TEAM-CORE-ENG",
                ),
                ColumnDefinition(
                    name="application_id",
                    data_type="string",
                    required=False,
                    description="Curated application portfolio code",
                    master_reference="APPLICATION",
                    sample_value="APP-PORTAL-01",
                ),
                ColumnDefinition(
                    name="environment_id",
                    data_type="string",
                    required=False,
                    description="Curated deployment environment code",
                    master_reference="ENVIRONMENT",
                    sample_value="ENV-PROD",
                ),
                ColumnDefinition(
                    name="cost_center_id",
                    data_type="string",
                    required=False,
                    description="Curated financial cost centre code",
                    master_reference="COST_CENTRE",
                    sample_value="CC-101",
                ),
                ColumnDefinition(
                    name="curation_reason",
                    data_type="string",
                    required=False,
                    description="Business justification explaining this manual curation assignment",
                    sample_value="CMDB annual reconciliation migration",
                ),
            ],
        ),
        "DEPENDENCY_EDGE": EntityImportMetadata(
            entity_type="DEPENDENCY_EDGE",
            display_name="CMDB Dependency Edges",
            description="Bulk import of service-to-service, application-to-resource, and network topology dependency edges.",
            natural_key_columns=["source_id", "target_id", "relationship_type"],
            default_atomicity_policy=AtomicityPolicy.PARTIAL_SUCCESS,
            allowed_modes=[
                ImportMode.INSERT_ONLY,
                ImportMode.UPDATE_ONLY,
                ImportMode.UPSERT,
                ImportMode.DEACTIVATE_MISSING,
            ],
            rollback_window_hours=24,
            columns=[
                ColumnDefinition(
                    name="source_id",
                    data_type="string",
                    required=True,
                    description="Upstream dependent entity ID or resource ID",
                    sample_value="APP-PORTAL-01",
                ),
                ColumnDefinition(
                    name="target_id",
                    data_type="string",
                    required=True,
                    description="Downstream supplier or dependency entity ID",
                    sample_value="res-rds-db-01",
                ),
                ColumnDefinition(
                    name="relationship_type",
                    data_type="string",
                    required=True,
                    description="Type of relationship from RELATIONSHIP_TYPE master",
                    master_reference="RELATIONSHIP_TYPE",
                    sample_value="CALLS_API",
                ),
                ColumnDefinition(
                    name="criticality",
                    data_type="string",
                    required=False,
                    description="Impact criticality tier",
                    master_reference="POLICY_SEVERITY",
                    allowed_values=["CRITICAL", "HIGH", "MEDIUM", "LOW"],
                    sample_value="HIGH",
                ),
                ColumnDefinition(
                    name="is_billable",
                    data_type="boolean",
                    required=False,
                    description="Whether costs flow across this dependency edge",
                    sample_value=True,
                ),
                ColumnDefinition(
                    name="confidence",
                    data_type="number",
                    required=False,
                    description="Confidence score between 0.0 and 1.0",
                    sample_value=0.95,
                ),
            ],
        ),
        "BUSINESS_UNIT": EntityImportMetadata(
            entity_type="BUSINESS_UNIT",
            display_name="Business Units",
            description="Top-level organizational divisions with leadership and cost allocation hierarchies.",
            natural_key_columns=["code"],
            default_atomicity_policy=AtomicityPolicy.PARTIAL_SUCCESS,
            allowed_modes=[
                ImportMode.INSERT_ONLY,
                ImportMode.UPDATE_ONLY,
                ImportMode.UPSERT,
                ImportMode.DEACTIVATE_MISSING,
            ],
            rollback_window_hours=72,
            columns=[
                ColumnDefinition(
                    name="code",
                    data_type="string",
                    required=True,
                    description="Business unit code identifier (e.g. BU-RETAIL)",
                    sample_value="BU-RETAIL",
                ),
                ColumnDefinition(
                    name="display_name",
                    data_type="string",
                    required=True,
                    description="Full business unit title",
                    sample_value="Retail & Consumer Banking",
                ),
                ColumnDefinition(
                    name="head_of_unit",
                    data_type="string",
                    required=False,
                    description="Executive sponsor or VP identity",
                    sample_value="Jane Doe (EVP)",
                ),
                ColumnDefinition(
                    name="description",
                    data_type="string",
                    required=False,
                    description="Scope and description of business unit",
                    sample_value="Consumer division managing digital banking apps",
                ),
            ],
        ),
        "COST_CENTRE": EntityImportMetadata(
            entity_type="COST_CENTRE",
            display_name="Financial Cost Centres",
            description="General Ledger accounting cost centres linked to business units.",
            natural_key_columns=["code"],
            default_atomicity_policy=AtomicityPolicy.PARTIAL_SUCCESS,
            allowed_modes=[
                ImportMode.INSERT_ONLY,
                ImportMode.UPDATE_ONLY,
                ImportMode.UPSERT,
                ImportMode.DEACTIVATE_MISSING,
            ],
            rollback_window_hours=72,
            columns=[
                ColumnDefinition(
                    name="code",
                    data_type="string",
                    required=True,
                    description="Cost centre accounting code (e.g. CC-101)",
                    sample_value="CC-101",
                ),
                ColumnDefinition(
                    name="display_name",
                    data_type="string",
                    required=True,
                    description="Cost centre title",
                    sample_value="Core Digital Infrastructure",
                ),
                ColumnDefinition(
                    name="business_unit_code",
                    data_type="string",
                    required=True,
                    description="Parent business unit code",
                    master_reference="BUSINESS_UNIT",
                    sample_value="BU-RETAIL",
                ),
                ColumnDefinition(
                    name="gl_account_reference",
                    data_type="string",
                    required=False,
                    description="SAP/Oracle General Ledger account reference",
                    sample_value="GL-6420-CLOUD",
                ),
                ColumnDefinition(
                    name="owner_id",
                    data_type="string",
                    required=False,
                    description="Accountable budget holder ID",
                    master_reference="OWNER_TEAM",
                    sample_value="TEAM-FINOPS",
                ),
            ],
        ),
        "OWNER_TEAM": EntityImportMetadata(
            entity_type="OWNER_TEAM",
            display_name="Owners and Engineering Teams",
            description="People, engineering squads, and FinOps stewards with contact channels.",
            natural_key_columns=["code"],
            default_atomicity_policy=AtomicityPolicy.PARTIAL_SUCCESS,
            allowed_modes=[
                ImportMode.INSERT_ONLY,
                ImportMode.UPDATE_ONLY,
                ImportMode.UPSERT,
                ImportMode.DEACTIVATE_MISSING,
            ],
            rollback_window_hours=48,
            columns=[
                ColumnDefinition(
                    name="code",
                    data_type="string",
                    required=True,
                    description="Unique team or owner code (e.g. TEAM-FINOPS)",
                    sample_value="TEAM-FINOPS",
                ),
                ColumnDefinition(
                    name="display_name",
                    data_type="string",
                    required=True,
                    description="Team or individual display name",
                    sample_value="Central FinOps & Governance Team",
                ),
                ColumnDefinition(
                    name="role",
                    data_type="string",
                    required=False,
                    description="Functional role",
                    sample_value="Cloud Economics & Cost Stewards",
                ),
                ColumnDefinition(
                    name="directory_reference",
                    data_type="string",
                    required=False,
                    description="Corporate Active Directory or Okta Group ID",
                    sample_value="sg-cloudlens-finops",
                ),
            ],
        ),
        "ENVIRONMENT": EntityImportMetadata(
            entity_type="ENVIRONMENT",
            display_name="Deployment Environments",
            description="Environment tiers (Production, Staging, Dev) with production flags.",
            natural_key_columns=["code"],
            default_atomicity_policy=AtomicityPolicy.PARTIAL_SUCCESS,
            allowed_modes=[
                ImportMode.INSERT_ONLY,
                ImportMode.UPDATE_ONLY,
                ImportMode.UPSERT,
                ImportMode.DEACTIVATE_MISSING,
            ],
            rollback_window_hours=48,
            columns=[
                ColumnDefinition(
                    name="code",
                    data_type="string",
                    required=True,
                    description="Environment code (e.g. ENV-PROD, ENV-STAGING)",
                    sample_value="ENV-PROD",
                ),
                ColumnDefinition(
                    name="display_name",
                    data_type="string",
                    required=True,
                    description="Environment title",
                    sample_value="Production Live Workloads",
                ),
                ColumnDefinition(
                    name="is_production",
                    data_type="boolean",
                    required=True,
                    description="True if workloads are customer-facing production",
                    sample_value=True,
                ),
                ColumnDefinition(
                    name="default_schedule",
                    data_type="string",
                    required=False,
                    description="Standard operational runtime schedule code",
                    sample_value="24x7_ALWAYS_ON",
                ),
            ],
        ),
        "PROJECT": EntityImportMetadata(
            entity_type="PROJECT",
            display_name="Projects & Capital Initiatives",
            description="Internal projects, capitalization flags, and cost centre alignments.",
            natural_key_columns=["code"],
            default_atomicity_policy=AtomicityPolicy.PARTIAL_SUCCESS,
            allowed_modes=[
                ImportMode.INSERT_ONLY,
                ImportMode.UPDATE_ONLY,
                ImportMode.UPSERT,
                ImportMode.DEACTIVATE_MISSING,
            ],
            rollback_window_hours=48,
            columns=[
                ColumnDefinition(
                    name="code",
                    data_type="string",
                    required=True,
                    description="Project code (e.g. PRJ-MIGRATION)",
                    sample_value="PRJ-MIGRATION",
                ),
                ColumnDefinition(
                    name="display_name",
                    data_type="string",
                    required=True,
                    description="Project title",
                    sample_value="Cloud Modernization & Replatforming",
                ),
                ColumnDefinition(
                    name="cost_centre_code",
                    data_type="string",
                    required=False,
                    description="Funding cost centre",
                    master_reference="COST_CENTRE",
                    sample_value="CC-101",
                ),
                ColumnDefinition(
                    name="is_capitalised",
                    data_type="boolean",
                    required=False,
                    description="Whether spend is capitalized as intangible software asset",
                    sample_value=True,
                ),
            ],
        ),
        "BUDGET": EntityImportMetadata(
            entity_type="BUDGET",
            display_name="Financial Budgets & Envelopes",
            description="Budget envelopes per business unit, cost centre, or application. Atomic all-or-nothing by default.",
            natural_key_columns=["budget_id"],
            default_atomicity_policy=AtomicityPolicy.ALL_OR_NOTHING,
            allowed_modes=[
                ImportMode.INSERT_ONLY,
                ImportMode.UPDATE_ONLY,
                ImportMode.UPSERT,
            ],
            rollback_window_hours=24,
            columns=[
                ColumnDefinition(
                    name="budget_id",
                    data_type="string",
                    required=True,
                    description="Unique budget allocation identifier (e.g. BGT-2026-RETAIL)",
                    sample_value="BGT-2026-RETAIL",
                ),
                ColumnDefinition(
                    name="name",
                    data_type="string",
                    required=True,
                    description="Budget envelope title",
                    sample_value="Retail Banking FY2026 Cloud Budget",
                ),
                ColumnDefinition(
                    name="amount",
                    data_type="number",
                    required=True,
                    description="Authorized budget amount",
                    sample_value=1200000.0,
                ),
                ColumnDefinition(
                    name="currency",
                    data_type="string",
                    required=True,
                    description="Currency code",
                    master_reference="CURRENCY",
                    sample_value="USD",
                ),
                ColumnDefinition(
                    name="fiscal_year",
                    data_type="number",
                    required=True,
                    description="Fiscal year integer",
                    sample_value=2026,
                ),
                ColumnDefinition(
                    name="business_unit_code",
                    data_type="string",
                    required=True,
                    description="Target business unit",
                    master_reference="BUSINESS_UNIT",
                    sample_value="BU-RETAIL",
                ),
                ColumnDefinition(
                    name="cost_centre_code",
                    data_type="string",
                    required=False,
                    description="Optional target cost centre",
                    master_reference="COST_CENTRE",
                    sample_value="CC-101",
                ),
            ],
        ),
        "EXCHANGE_RATE": EntityImportMetadata(
            entity_type="EXCHANGE_RATE",
            display_name="Foreign Exchange Rates",
            description="Effective-dated currency conversion rates by rate type (Spot, Monthly Average, Budget).",
            natural_key_columns=["from_currency", "to_currency", "effective_date", "rate_type"],
            default_atomicity_policy=AtomicityPolicy.ALL_OR_NOTHING,
            allowed_modes=[
                ImportMode.INSERT_ONLY,
                ImportMode.UPDATE_ONLY,
                ImportMode.UPSERT,
            ],
            rollback_window_hours=24,
            columns=[
                ColumnDefinition(
                    name="from_currency",
                    data_type="string",
                    required=True,
                    description="Source currency code (e.g. EUR)",
                    master_reference="CURRENCY",
                    sample_value="EUR",
                ),
                ColumnDefinition(
                    name="to_currency",
                    data_type="string",
                    required=True,
                    description="Target currency code (e.g. USD)",
                    master_reference="CURRENCY",
                    sample_value="USD",
                ),
                ColumnDefinition(
                    name="rate",
                    data_type="number",
                    required=True,
                    description="Exchange multiplier rate",
                    sample_value=1.085,
                ),
                ColumnDefinition(
                    name="effective_date",
                    data_type="date",
                    required=True,
                    description="Effective date string (YYYY-MM-DD)",
                    sample_value="2026-09-01",
                ),
                ColumnDefinition(
                    name="rate_type",
                    data_type="string",
                    required=True,
                    description="Rate type: SPOT, MONTHLY_AVERAGE, BUDGET, CONSTANT",
                    allowed_values=["SPOT", "MONTHLY_AVERAGE", "BUDGET", "CONSTANT"],
                    sample_value="MONTHLY_AVERAGE",
                ),
                ColumnDefinition(
                    name="source",
                    data_type="string",
                    required=False,
                    description="Source agency or provider (e.g. Bloomberg, ECB)",
                    sample_value="ECB",
                ),
            ],
        ),
        "RATE_CARD": EntityImportMetadata(
            entity_type="RATE_CARD",
            display_name="Rate Cards & Negotiated Pricing",
            description="Contracted discount rates and custom negotiated pricing superseding provider public rates.",
            natural_key_columns=["provider_code", "service_code", "sku_id"],
            default_atomicity_policy=AtomicityPolicy.ALL_OR_NOTHING,
            allowed_modes=[
                ImportMode.INSERT_ONLY,
                ImportMode.UPDATE_ONLY,
                ImportMode.UPSERT,
                ImportMode.DEACTIVATE_MISSING,
            ],
            rollback_window_hours=48,
            columns=[
                ColumnDefinition(
                    name="provider_code",
                    data_type="string",
                    required=True,
                    description="Cloud provider code",
                    master_reference="CLOUD_PROVIDER",
                    sample_value="AWS",
                ),
                ColumnDefinition(
                    name="service_code",
                    data_type="string",
                    required=True,
                    description="Cloud service code",
                    master_reference="SERVICE",
                    sample_value="AmazonEC2",
                ),
                ColumnDefinition(
                    name="sku_id",
                    data_type="string",
                    required=True,
                    description="SKU identifier or instance family",
                    sample_value="m5.large",
                ),
                ColumnDefinition(
                    name="contracted_rate",
                    data_type="number",
                    required=True,
                    description="Negotiated hourly/unit price",
                    sample_value=0.0768,
                ),
                ColumnDefinition(
                    name="list_rate",
                    data_type="number",
                    required=False,
                    description="Standard public list price",
                    sample_value=0.096,
                ),
                ColumnDefinition(
                    name="currency",
                    data_type="string",
                    required=True,
                    description="Pricing currency",
                    master_reference="CURRENCY",
                    sample_value="USD",
                ),
                ColumnDefinition(
                    name="effective_from",
                    data_type="date",
                    required=True,
                    description="Effective start date (YYYY-MM-DD)",
                    sample_value="2026-01-01",
                ),
                ColumnDefinition(
                    name="contract_reference",
                    data_type="string",
                    required=False,
                    description="Enterprise agreement reference number",
                    sample_value="EA-AWS-2026-9912",
                ),
            ],
        ),
        "HOLIDAY_CALENDAR": EntityImportMetadata(
            entity_type="HOLIDAY_CALENDAR",
            display_name="Holiday Calendars",
            description="Statutory regional public holidays for schedule adherence exception suppression.",
            natural_key_columns=["location_code", "holiday_date"],
            default_atomicity_policy=AtomicityPolicy.PARTIAL_SUCCESS,
            allowed_modes=[
                ImportMode.INSERT_ONLY,
                ImportMode.UPDATE_ONLY,
                ImportMode.UPSERT,
                ImportMode.DEACTIVATE_MISSING,
            ],
            rollback_window_hours=72,
            columns=[
                ColumnDefinition(
                    name="location_code",
                    data_type="string",
                    required=True,
                    description="Location site or jurisdiction code",
                    master_reference="LOCATION",
                    sample_value="LOC_US_EAST_VA",
                ),
                ColumnDefinition(
                    name="holiday_date",
                    data_type="date",
                    required=True,
                    description="Holiday calendar date (YYYY-MM-DD)",
                    sample_value="2026-11-26",
                ),
                ColumnDefinition(
                    name="holiday_name",
                    data_type="string",
                    required=True,
                    description="Official public holiday name",
                    sample_value="Thanksgiving Day",
                ),
                ColumnDefinition(
                    name="year",
                    data_type="number",
                    required=True,
                    description="Calendar year",
                    sample_value=2026,
                ),
            ],
        ),
        "LICENCE": EntityImportMetadata(
            entity_type="LICENCE",
            display_name="Software Licences & BYOL",
            description="Software licence entitlements, core counts, and BYOL tracking.",
            natural_key_columns=["code"],
            default_atomicity_policy=AtomicityPolicy.PARTIAL_SUCCESS,
            allowed_modes=[
                ImportMode.INSERT_ONLY,
                ImportMode.UPDATE_ONLY,
                ImportMode.UPSERT,
                ImportMode.DEACTIVATE_MISSING,
            ],
            rollback_window_hours=48,
            columns=[
                ColumnDefinition(
                    name="code",
                    data_type="string",
                    required=True,
                    description="Licence entitlement code (e.g. LIC-RHEL-01)",
                    sample_value="LIC-RHEL-01",
                ),
                ColumnDefinition(
                    name="display_name",
                    data_type="string",
                    required=True,
                    description="Software title and edition",
                    sample_value="Red Hat Enterprise Linux Server",
                ),
                ColumnDefinition(
                    name="entitlement_count",
                    data_type="number",
                    required=True,
                    description="Purchased total seats/cores entitlement",
                    sample_value=500,
                ),
                ColumnDefinition(
                    name="is_byol",
                    data_type="boolean",
                    required=True,
                    description="Whether Bring-Your-Own-Licence applies",
                    sample_value=True,
                ),
                ColumnDefinition(
                    name="renewal_date",
                    data_type="date",
                    required=False,
                    description="Agreement expiry date (YYYY-MM-DD)",
                    sample_value="2027-03-31",
                ),
            ],
        ),
        "USER_ROLE_GRANT": EntityImportMetadata(
            entity_type="USER_ROLE_GRANT",
            display_name="User Role & Scope Grants",
            description="Bulk user role assignments and scope boundaries. High security sensitivity (ALL_OR_NOTHING).",
            natural_key_columns=["user_email", "role_code", "scope_id"],
            default_atomicity_policy=AtomicityPolicy.ALL_OR_NOTHING,
            allowed_modes=[
                ImportMode.INSERT_ONLY,
                ImportMode.UPDATE_ONLY,
                ImportMode.UPSERT,
                ImportMode.DEACTIVATE_MISSING,
            ],
            rollback_window_hours=24,
            columns=[
                ColumnDefinition(
                    name="user_email",
                    data_type="string",
                    required=True,
                    description="Corporate email of user identity",
                    sample_value="dev-lead@cloudlens.internal",
                ),
                ColumnDefinition(
                    name="role_code",
                    data_type="string",
                    required=True,
                    description="Canonical role code from ROLE master",
                    master_reference="ROLE",
                    sample_value="FINOPS_PRACTITIONER",
                ),
                ColumnDefinition(
                    name="scope_type",
                    data_type="string",
                    required=True,
                    description="Granted scope level: TENANT, BUSINESS_UNIT, COST_CENTRE, SUBSCRIPTION",
                    allowed_values=["TENANT", "BUSINESS_UNIT", "COST_CENTRE", "SUBSCRIPTION"],
                    sample_value="BUSINESS_UNIT",
                ),
                ColumnDefinition(
                    name="scope_id",
                    data_type="string",
                    required=True,
                    description="Granted target scope identifier",
                    sample_value="BU-RETAIL",
                ),
            ],
        ),
        "TAG_POLICY": EntityImportMetadata(
            entity_type="TAG_POLICY",
            display_name="Tag Policy Definitions & Allowed Values",
            description="Corporate mandatory tags, valid value lists, and regex patterns.",
            natural_key_columns=["code"],
            default_atomicity_policy=AtomicityPolicy.PARTIAL_SUCCESS,
            allowed_modes=[
                ImportMode.INSERT_ONLY,
                ImportMode.UPDATE_ONLY,
                ImportMode.UPSERT,
                ImportMode.DEACTIVATE_MISSING,
            ],
            rollback_window_hours=48,
            columns=[
                ColumnDefinition(
                    name="code",
                    data_type="string",
                    required=True,
                    description="Tag policy code",
                    sample_value="TAG_POL_MANDATORY_ENV",
                ),
                ColumnDefinition(
                    name="display_name",
                    data_type="string",
                    required=True,
                    description="Tag policy title",
                    sample_value="Mandatory Environment Tag Policy",
                ),
                ColumnDefinition(
                    name="enforcement_posture",
                    data_type="string",
                    required=True,
                    description="Enforcement posture: ADVISORY, WARNING, BLOCKING",
                    allowed_values=["ADVISORY", "WARNING", "BLOCKING"],
                    sample_value="WARNING",
                ),
            ],
        ),
        "THRESHOLD_SET": EntityImportMetadata(
            entity_type="THRESHOLD_SET",
            display_name="Monitoring Threshold Sets",
            description="Resource monitoring threshold configurations for idle, budget, and spend anomaly alerts.",
            natural_key_columns=["code"],
            default_atomicity_policy=AtomicityPolicy.ALL_OR_NOTHING,
            allowed_modes=[
                ImportMode.INSERT_ONLY,
                ImportMode.UPDATE_ONLY,
                ImportMode.UPSERT,
            ],
            rollback_window_hours=48,
            columns=[
                ColumnDefinition(
                    name="code",
                    data_type="string",
                    required=True,
                    description="Threshold set code",
                    sample_value="TH_VM_IDLE_AGGRESSIVE",
                ),
                ColumnDefinition(
                    name="display_name",
                    data_type="string",
                    required=True,
                    description="Threshold set title",
                    sample_value="Aggressive Virtual Machine Idle Detection",
                ),
                ColumnDefinition(
                    name="metric_code",
                    data_type="string",
                    required=True,
                    description="Target metric code from METRIC master",
                    master_reference="METRIC",
                    sample_value="CPU_UTILIZATION_PCT",
                ),
                ColumnDefinition(
                    name="threshold_value",
                    data_type="number",
                    required=True,
                    description="Evaluation trigger boundary value",
                    sample_value=5.0,
                ),
            ],
        ),
    }


class ImportableEntityCatalogue:
    """Registry maintaining specifications for all importable entities and registered masters."""

    def __init__(self) -> None:
        self._catalogue = _build_core_catalogue()

    def get_metadata(self, entity_type: str) -> EntityImportMetadata | None:
        """Retrieves import metadata for an entity type or registered master."""
        et = entity_type.strip().upper()
        if et in self._catalogue:
            return self._catalogue[et]

        # Dynamically support any registered master from Prompt 45
        if et in SYSTEM_MASTER_REGISTRY:
            master = SYSTEM_MASTER_REGISTRY[et]
            return EntityImportMetadata(
                entity_type=et,
                display_name=master.name,
                description=master.purpose,
                natural_key_columns=["code"],
                default_atomicity_policy=AtomicityPolicy.ALL_OR_NOTHING
                if master.requires_approval
                else AtomicityPolicy.PARTIAL_SUCCESS,
                allowed_modes=[
                    ImportMode.INSERT_ONLY,
                    ImportMode.UPDATE_ONLY,
                    ImportMode.UPSERT,
                    ImportMode.DEACTIVATE_MISSING,
                ],
                rollback_window_hours=48,
                columns=[
                    ColumnDefinition(
                        name="code",
                        data_type="string",
                        required=True,
                        description=f"Unique code for {master.name}",
                        sample_value=f"{et}_01",
                    ),
                    ColumnDefinition(
                        name="display_name",
                        data_type="string",
                        required=True,
                        description=f"Display name for {master.name}",
                        sample_value=f"Sample {master.name}",
                    ),
                    ColumnDefinition(
                        name="description",
                        data_type="string",
                        required=False,
                        description=f"Description of {master.name}",
                        sample_value="Imported master record",
                    ),
                    ColumnDefinition(
                        name="sort_order",
                        data_type="number",
                        required=False,
                        description="Presentation sort order index",
                        sample_value=10,
                    ),
                    ColumnDefinition(
                        name="parent_code",
                        data_type="string",
                        required=False,
                        description="Optional parent hierarchy code",
                        sample_value=None,
                    ),
                ],
            )

        return None

    def list_all(self) -> list[EntityImportMetadata]:
        """Lists all registered importable entities including registered master types."""
        res: list[EntityImportMetadata] = list(self._catalogue.values())
        for master in list_registered_masters():
            if master.code not in self._catalogue:
                meta = self.get_metadata(master.code)
                if meta:
                    res.append(meta)
        return res

    def get_valid_master_values(self, master_type: str, tenant_id: str | None = None) -> list[str]:
        """Dynamically retrieves live valid codes for a master reference.

        Enforces: "drawn from the relevant masters" and "Do not accept a value that does not exist in its master".
        """
        mt = master_type.strip().upper()
        master_service = get_master_data_service()
        try:
            records = master_service.list_records(mt, tenant_id=tenant_id, include_inactive=False)
            return [r.code for r in records if r.is_active]
        except Exception:
            return []


# Global singleton instance
_catalogue_instance = ImportableEntityCatalogue()


def get_import_catalogue() -> ImportableEntityCatalogue:
    """Returns the singleton ImportableEntityCatalogue."""
    return _catalogue_instance
