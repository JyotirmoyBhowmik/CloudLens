"""Master Catalogue of Platform Reports (Prompt 35 / BBP Section 36).

Enforces:
- 14 MVP report definitions (RPT-01 through RPT-14).
- 5 Pricing-specific report definitions (RPT-15 through RPT-19).
- 2 Phase 2 flag-gated report definitions (RPT-P2-UNUSUAL, RPT-P2-IDLE).
"""

from __future__ import annotations

from domain.reports.models import (
    ExportFormat,
    ReportCategory,
    ReportCode,
    ReportDefinition,
)

MASTER_REPORT_CATALOGUE: list[ReportDefinition] = [
    # ==========================================================================
    # 1. MVP Report Set (14 Reports: RPT-01 to RPT-14)
    # ==========================================================================
    ReportDefinition(
        id="tpl-cost-monthly",
        code=ReportCode.RPT_01_MONTHLY_COST,
        name="Monthly Cloud Cost Report",
        description="Comprehensive monthly cloud spend trends across accounts, subscriptions, and projects with MoM variance.",
        category=ReportCategory.FINANCIAL,
        supported_formats=[
            ExportFormat.PDF,
            ExportFormat.XLSX,
            ExportFormat.CSV,
            ExportFormat.JSON,
        ],
        default_grouping="scope",
    ),
    ReportDefinition(
        id="tpl-cost-provider",
        code=ReportCode.RPT_02_PROVIDER_COST,
        name="Provider Cost Breakdown Report",
        description="Distribution of infrastructure spend across cloud providers (AWS, Azure, GCP, OCI) with market share percentages.",
        category=ReportCategory.FINANCIAL,
        supported_formats=[
            ExportFormat.PDF,
            ExportFormat.XLSX,
            ExportFormat.CSV,
            ExportFormat.JSON,
        ],
        default_grouping="provider",
    ),
    ReportDefinition(
        id="tpl-cost-service",
        code=ReportCode.RPT_03_SERVICE_COST,
        name="Service Cost Breakdown Report",
        description="Spend breakdown by standardized service category (Compute, Storage, Database, Networking) and underlying service name.",
        category=ReportCategory.FINANCIAL,
        supported_formats=[
            ExportFormat.PDF,
            ExportFormat.XLSX,
            ExportFormat.CSV,
            ExportFormat.JSON,
        ],
        default_grouping="service",
    ),
    ReportDefinition(
        id="tpl-budget-variance",
        code=ReportCode.RPT_04_BUDGET_VARIANCE,
        name="Budget Variance & Health Report",
        description="Planned budget allocations vs actual metered spend vs variances, including green/amber/red threshold status.",
        category=ReportCategory.FINANCIAL,
        supported_formats=[
            ExportFormat.PDF,
            ExportFormat.XLSX,
            ExportFormat.CSV,
            ExportFormat.JSON,
        ],
        default_grouping="scope",
    ),
    ReportDefinition(
        id="tpl-cost-forecast",
        code=ReportCode.RPT_05_SPEND_FORECAST,
        name="Spend Forecast & Trajectory Report",
        description="Projected period-end spend with statistical confidence intervals and budget breach risk indicators.",
        category=ReportCategory.FINANCIAL,
        supported_formats=[
            ExportFormat.PDF,
            ExportFormat.XLSX,
            ExportFormat.CSV,
            ExportFormat.JSON,
        ],
        default_grouping="scope",
    ),
    ReportDefinition(
        id="tpl-usage-consumption",
        code=ReportCode.RPT_06_USAGE_TELEMETRY,
        name="Usage & Consumption Telemetry Report",
        description="Detailed consumption telemetry (core-hours, storage-GB, network bandwidth, API volume) with unit normalisation.",
        category=ReportCategory.OPERATIONAL,
        supported_formats=[ExportFormat.XLSX, ExportFormat.CSV, ExportFormat.JSON],
        default_grouping="metric",
    ),
    ReportDefinition(
        id="tpl-runtime-compliance",
        code=ReportCode.RPT_07_RUNTIME_COMPLIANCE,
        name="Runtime & Schedule Compliance Report",
        description="Operational state tracking (Running, Stopped, Deallocated) and excess cost incurred outside declared operating schedules.",
        category=ReportCategory.OPERATIONAL,
        supported_formats=[
            ExportFormat.PDF,
            ExportFormat.XLSX,
            ExportFormat.CSV,
            ExportFormat.JSON,
        ],
        default_grouping="schedule",
    ),
    ReportDefinition(
        id="tpl-topology-dependency",
        code=ReportCode.RPT_08_DEPENDENCY_CHAIN,
        name="Dependency Chain & Blast Radius Report",
        description="Typed dependency graph connections, application chain cost rollups, and blast radius impact analysis.",
        category=ReportCategory.ARCHITECTURE,
        supported_formats=[
            ExportFormat.PDF,
            ExportFormat.XLSX,
            ExportFormat.CSV,
            ExportFormat.JSON,
        ],
        default_grouping="application",
    ),
    ReportDefinition(
        id="tpl-gov-exceptions",
        code=ReportCode.RPT_09_GOVERNANCE_EXCEPTIONS,
        name="Governance Exception & Tagging Debt Report",
        description="Catalog of unowned resources, missing mandatory tags, orphaned storage disks, and unclassified services.",
        category=ReportCategory.GOVERNANCE,
        supported_formats=[
            ExportFormat.PDF,
            ExportFormat.XLSX,
            ExportFormat.CSV,
            ExportFormat.JSON,
        ],
        default_grouping="violation_type",
    ),
    ReportDefinition(
        id="tpl-connector-status",
        code=ReportCode.RPT_10_CONNECTOR_STATUS,
        name="Connector Health & Sync Status Report",
        description="Operational status of multi-cloud connector integrations, ingestion timestamps, sync latency, and failure logs.",
        category=ReportCategory.OPERATIONAL,
        supported_formats=[
            ExportFormat.PDF,
            ExportFormat.XLSX,
            ExportFormat.CSV,
            ExportFormat.JSON,
        ],
        default_grouping="provider",
    ),
    ReportDefinition(
        id="tpl-executive-summary",
        code=ReportCode.RPT_11_EXECUTIVE_SUMMARY,
        name="Executive Summary Leadership Pack",
        description="Consolidated leadership brief: total monthly cloud spend, MoM trend, top 5 cost drivers, budget compliance, and governance score.",
        category=ReportCategory.FINANCIAL,
        supported_formats=[
            ExportFormat.PDF,
            ExportFormat.XLSX,
            ExportFormat.CSV,
            ExportFormat.JSON,
        ],
        default_grouping="kpi",
    ),
    ReportDefinition(
        id="tpl-reconciliation-variance",
        code=ReportCode.RPT_12_RECONCILIATION,
        name="Authoritative Invoice Period Reconciliation Report",
        description="Closed-period reconciliation comparing authoritative provider invoice totals against normalised internal facts.",
        category=ReportCategory.FINANCIAL,
        supported_formats=[
            ExportFormat.PDF,
            ExportFormat.XLSX,
            ExportFormat.CSV,
            ExportFormat.JSON,
        ],
        default_grouping="provider",
    ),
    ReportDefinition(
        id="tpl-access-review",
        code=ReportCode.RPT_13_ACCESS_REVIEW,
        name="Access Review & Identity Governance Report",
        description="User identity audit, role assignments, direct and inherited scope grants, MFA enforcement, and break-glass account status.",
        category=ReportCategory.SECURITY,
        supported_formats=[
            ExportFormat.PDF,
            ExportFormat.XLSX,
            ExportFormat.CSV,
            ExportFormat.JSON,
        ],
        default_grouping="role",
    ),
    ReportDefinition(
        id="tpl-audit-extract",
        code=ReportCode.RPT_14_AUDIT_EXTRACT,
        name="Immutable Audit Trail Extract",
        description="Cryptographically chained immutable audit event records detailing actor identity, action, entity affected, and timestamp.",
        category=ReportCategory.AUDIT,
        supported_formats=[ExportFormat.CSV, ExportFormat.JSON],
        default_grouping="event_type",
    ),
    # ==========================================================================
    # 2. Pricing-Specific Reports (5 Reports: RPT-15 to RPT-19)
    # ==========================================================================
    ReportDefinition(
        id="tpl-pricing-rates",
        code=ReportCode.RPT_15_PRICING_RATES,
        name="Pricing Rates in Use Report",
        description="Current effective unit rates applied across services, SKUs, and regions with provenance source and effective dates.",
        category=ReportCategory.PRICING,
        supported_formats=[ExportFormat.XLSX, ExportFormat.CSV, ExportFormat.JSON],
        default_grouping="service",
    ),
    ReportDefinition(
        id="tpl-pricing-free-tier",
        code=ReportCode.RPT_16_FREE_TIER_USAGE,
        name="Free-Tier Usage & Allowance Exhaustion Report",
        description="Free allowance consumption tracking, threshold utilization, and proximity warnings before paid tiers engage.",
        category=ReportCategory.PRICING,
        supported_formats=[
            ExportFormat.PDF,
            ExportFormat.XLSX,
            ExportFormat.CSV,
            ExportFormat.JSON,
        ],
        default_grouping="provider",
    ),
    ReportDefinition(
        id="tpl-pricing-cost-drivers",
        code=ReportCode.RPT_17_COST_DRIVERS,
        name="Cost Driver Decomposition Report",
        description="Decomposition of material cloud spend into volume change, unit rate variance, and architectural/configuration shift.",
        category=ReportCategory.PRICING,
        supported_formats=[
            ExportFormat.PDF,
            ExportFormat.XLSX,
            ExportFormat.CSV,
            ExportFormat.JSON,
        ],
        default_grouping="service",
    ),
    ReportDefinition(
        id="tpl-pricing-changes",
        code=ReportCode.RPT_18_PRICING_CHANGES,
        name="Pricing Changes & Rate Drift Report",
        description="Provider catalog price updates, list rate deltas, and projected annual financial impact on active estate.",
        category=ReportCategory.PRICING,
        supported_formats=[
            ExportFormat.PDF,
            ExportFormat.XLSX,
            ExportFormat.CSV,
            ExportFormat.JSON,
        ],
        default_grouping="provider",
    ),
    ReportDefinition(
        id="tpl-pricing-freshness",
        code=ReportCode.RPT_19_DATA_FRESHNESS,
        name="Data Freshness & Ingestion Lag Report",
        description="Data freshness per provider and domain (Cost, Inventory, Pricing), ingestion lag hours, and SLA compliance status.",
        category=ReportCategory.OPERATIONAL,
        supported_formats=[
            ExportFormat.PDF,
            ExportFormat.XLSX,
            ExportFormat.CSV,
            ExportFormat.JSON,
        ],
        default_grouping="provider",
    ),
    # ==========================================================================
    # 3. Phase 2 Flag-Gated Reports (2 Reports)
    # ==========================================================================
    ReportDefinition(
        id="tpl-phase2-unusual",
        code=ReportCode.RPT_P2_UNUSUAL_CONSUMPTION,
        name="Unusual Consumption & Anomaly Report",
        description="Phase 2 machine learning and statistical spike detection flagging abnormal consumption surges (Z-score > 3.0).",
        category=ReportCategory.OPERATIONAL,
        supported_formats=[
            ExportFormat.PDF,
            ExportFormat.XLSX,
            ExportFormat.CSV,
            ExportFormat.JSON,
        ],
        default_grouping="service",
        is_phase_2=True,
        phase_2_flag="PHASE_2_ANOMALY_DETECTION",
    ),
    ReportDefinition(
        id="tpl-phase2-idle",
        code=ReportCode.RPT_P2_IDLE_RESOURCES,
        name="Idle & Orphaned Resource Optimization Report",
        description="Phase 2 detection of zero-utilization compute instances, unattached disks, and idle load balancers with cost saving potential.",
        category=ReportCategory.FINANCIAL,
        supported_formats=[
            ExportFormat.PDF,
            ExportFormat.XLSX,
            ExportFormat.CSV,
            ExportFormat.JSON,
        ],
        default_grouping="provider",
        is_phase_2=True,
        phase_2_flag="PHASE_2_IDLE_DETECTION",
    ),
]


def get_report_definition(identifier: str) -> ReportDefinition | None:
    """Finds report definition by template ID or canonical code."""
    ident_lower = identifier.lower().strip()
    ident_code = identifier.upper().strip()
    for r in MASTER_REPORT_CATALOGUE:
        if r.id.lower() == ident_lower or r.code.value.upper() == ident_code:
            return r
    return None
