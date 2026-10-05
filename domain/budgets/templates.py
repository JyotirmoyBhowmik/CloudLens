"""Budget Template Catalogue per Scope Type (Prompt 28).

Enforces:
- Prompt 28: Implement budget templates per scope type providing default period,
  thresholds and recipients.
"""

from __future__ import annotations

from domain.budgets.models import BudgetTemplate, BudgetThreshold
from domain.models.enums import BudgetPeriod, BudgetScopeType

BUDGET_TEMPLATES_BY_SCOPE: dict[BudgetScopeType, BudgetTemplate] = {
    BudgetScopeType.ORGANISATION: BudgetTemplate(
        code="TMPL_ORGANISATION",
        scope_type=BudgetScopeType.ORGANISATION,
        display_name="Enterprise Organization Master Budget Template",
        description="Comprehensive organization-wide fiscal-year ceiling with executive FinOps notifications.",
        default_period=BudgetPeriod.FISCAL_YEAR,
        default_thresholds=[
            BudgetThreshold(percentage=75.0, band="WARNING"),
            BudgetThreshold(percentage=90.0, band="HIGH"),
            BudgetThreshold(percentage=100.0, band="CRITICAL"),
        ],
        default_alert_recipients=[],
        suggested_forecast_threshold=95.0,
    ),
    BudgetScopeType.PROVIDER: BudgetTemplate(
        code="TMPL_PROVIDER",
        scope_type=BudgetScopeType.PROVIDER,
        display_name="Hyperscaler Cloud Provider Budget Template",
        description="Monthly cloud provider spend ceiling tracked against committed spend discounts.",
        default_period=BudgetPeriod.MONTHLY,
        default_thresholds=[
            BudgetThreshold(percentage=80.0, band="WARNING"),
            BudgetThreshold(percentage=95.0, band="HIGH"),
            BudgetThreshold(percentage=100.0, band="CRITICAL"),
        ],
        default_alert_recipients=[],
        suggested_forecast_threshold=100.0,
    ),
    BudgetScopeType.MANAGEMENT_GROUP: BudgetTemplate(
        code="TMPL_MANAGEMENT_GROUP",
        scope_type=BudgetScopeType.MANAGEMENT_GROUP,
        display_name="Azure Management Group Budget Template",
        description="Multi-subscription hierarchical ceiling for cross-account governance.",
        default_period=BudgetPeriod.QUARTERLY,
        default_thresholds=[
            BudgetThreshold(percentage=75.0, band="WARNING"),
            BudgetThreshold(percentage=90.0, band="HIGH"),
            BudgetThreshold(percentage=100.0, band="CRITICAL"),
        ],
        default_alert_recipients=[],
        suggested_forecast_threshold=95.0,
    ),
    BudgetScopeType.SUBSCRIPTION: BudgetTemplate(
        code="TMPL_SUBSCRIPTION",
        scope_type=BudgetScopeType.SUBSCRIPTION,
        display_name="Cloud Subscription Operating Budget Template",
        description="Monthly subscription burn tracking with alert routing to subscription owner.",
        default_period=BudgetPeriod.MONTHLY,
        default_thresholds=[
            BudgetThreshold(percentage=80.0, band="WARNING"),
            BudgetThreshold(percentage=100.0, band="CRITICAL"),
        ],
        default_alert_recipients=[],
        suggested_forecast_threshold=100.0,
    ),
    BudgetScopeType.AWS_OU: BudgetTemplate(
        code="TMPL_AWS_OU",
        scope_type=BudgetScopeType.AWS_OU,
        display_name="AWS Organizational Unit (OU) Budget Template",
        description="Multi-account OU financial control boundary with early burn detection.",
        default_period=BudgetPeriod.MONTHLY,
        default_thresholds=[
            BudgetThreshold(percentage=80.0, band="WARNING"),
            BudgetThreshold(percentage=95.0, band="HIGH"),
            BudgetThreshold(percentage=100.0, band="CRITICAL"),
        ],
        default_alert_recipients=[],
        suggested_forecast_threshold=100.0,
    ),
    BudgetScopeType.AWS_ACCOUNT: BudgetTemplate(
        code="TMPL_AWS_ACCOUNT",
        scope_type=BudgetScopeType.AWS_ACCOUNT,
        display_name="AWS Account Operating Budget Template",
        description="Dedicated AWS Account monthly allocation boundary.",
        default_period=BudgetPeriod.MONTHLY,
        default_thresholds=[
            BudgetThreshold(percentage=80.0, band="WARNING"),
            BudgetThreshold(percentage=100.0, band="CRITICAL"),
        ],
        default_alert_recipients=[],
        suggested_forecast_threshold=100.0,
    ),
    BudgetScopeType.GCP_FOLDER: BudgetTemplate(
        code="TMPL_GCP_FOLDER",
        scope_type=BudgetScopeType.GCP_FOLDER,
        display_name="GCP Resource Hierarchy Folder Budget Template",
        description="GCP folder-level aggregate budget allocation across child projects.",
        default_period=BudgetPeriod.MONTHLY,
        default_thresholds=[
            BudgetThreshold(percentage=80.0, band="WARNING"),
            BudgetThreshold(percentage=100.0, band="CRITICAL"),
        ],
        default_alert_recipients=[],
        suggested_forecast_threshold=100.0,
    ),
    BudgetScopeType.GCP_PROJECT: BudgetTemplate(
        code="TMPL_GCP_PROJECT",
        scope_type=BudgetScopeType.GCP_PROJECT,
        display_name="GCP Project Operating Budget Template",
        description="Monthly project cost tracking with billing account alignment.",
        default_period=BudgetPeriod.MONTHLY,
        default_thresholds=[
            BudgetThreshold(percentage=80.0, band="WARNING"),
            BudgetThreshold(percentage=100.0, band="CRITICAL"),
        ],
        default_alert_recipients=[],
        suggested_forecast_threshold=100.0,
    ),
    BudgetScopeType.OCI_COMPARTMENT: BudgetTemplate(
        code="TMPL_OCI_COMPARTMENT",
        scope_type=BudgetScopeType.OCI_COMPARTMENT,
        display_name="OCI Compartment Budget Template",
        description="Oracle Cloud Infrastructure compartment spending allocation.",
        default_period=BudgetPeriod.MONTHLY,
        default_thresholds=[
            BudgetThreshold(percentage=80.0, band="WARNING"),
            BudgetThreshold(percentage=100.0, band="CRITICAL"),
        ],
        default_alert_recipients=[],
        suggested_forecast_threshold=100.0,
    ),
    BudgetScopeType.RESOURCE_GROUP: BudgetTemplate(
        code="TMPL_RESOURCE_GROUP",
        scope_type=BudgetScopeType.RESOURCE_GROUP,
        display_name="Resource Group Spend Ceiling Template",
        description="Collocated resource collection spending cap.",
        default_period=BudgetPeriod.MONTHLY,
        default_thresholds=[
            BudgetThreshold(percentage=85.0, band="WARNING"),
            BudgetThreshold(percentage=100.0, band="CRITICAL"),
        ],
        default_alert_recipients=[],
        suggested_forecast_threshold=100.0,
    ),
    BudgetScopeType.APPLICATION: BudgetTemplate(
        code="TMPL_APPLICATION",
        scope_type=BudgetScopeType.APPLICATION,
        display_name="Logical Application Operating Budget Template",
        description="Service-oriented application spend boundary independent of cloud hosting provider.",
        default_period=BudgetPeriod.MONTHLY,
        default_thresholds=[
            BudgetThreshold(percentage=75.0, band="WARNING"),
            BudgetThreshold(percentage=90.0, band="HIGH"),
            BudgetThreshold(percentage=100.0, band="CRITICAL"),
        ],
        default_alert_recipients=[],
        suggested_forecast_threshold=95.0,
    ),
    BudgetScopeType.ENVIRONMENT: BudgetTemplate(
        code="TMPL_ENVIRONMENT",
        scope_type=BudgetScopeType.ENVIRONMENT,
        display_name="Environment Sandbox/Production Spend Cap Template",
        description="Environment isolation budget ceiling (e.g. dev sandbox cap or production baseline).",
        default_period=BudgetPeriod.MONTHLY,
        default_thresholds=[
            BudgetThreshold(percentage=80.0, band="WARNING"),
            BudgetThreshold(percentage=100.0, band="CRITICAL"),
        ],
        default_alert_recipients=[],
        suggested_forecast_threshold=100.0,
    ),
    BudgetScopeType.SERVICE: BudgetTemplate(
        code="TMPL_SERVICE",
        scope_type=BudgetScopeType.SERVICE,
        display_name="Cloud Platform Service Allocation Template",
        description="Specific cloud service usage envelope (e.g. EC2, BigQuery, Blob Storage).",
        default_period=BudgetPeriod.MONTHLY,
        default_thresholds=[
            BudgetThreshold(percentage=80.0, band="WARNING"),
            BudgetThreshold(percentage=100.0, band="CRITICAL"),
        ],
        default_alert_recipients=[],
        suggested_forecast_threshold=100.0,
    ),
    BudgetScopeType.RESOURCE: BudgetTemplate(
        code="TMPL_RESOURCE",
        scope_type=BudgetScopeType.RESOURCE,
        display_name="Critical Resource Cost Guardrail Template",
        description="Single heavyweight cloud resource financial threshold guardrail.",
        default_period=BudgetPeriod.MONTHLY,
        default_thresholds=[
            BudgetThreshold(percentage=85.0, band="WARNING"),
            BudgetThreshold(percentage=100.0, band="CRITICAL"),
        ],
        default_alert_recipients=[],
        suggested_forecast_threshold=100.0,
    ),
    BudgetScopeType.COST_CENTRE: BudgetTemplate(
        code="TMPL_COST_CENTRE",
        scope_type=BudgetScopeType.COST_CENTRE,
        display_name="Corporate Cost Centre Fiscal Budget Template",
        description="General Ledger Cost Centre allocation aligned with enterprise chart of accounts.",
        default_period=BudgetPeriod.FISCAL_YEAR,
        default_thresholds=[
            BudgetThreshold(percentage=75.0, band="WARNING"),
            BudgetThreshold(percentage=90.0, band="HIGH"),
            BudgetThreshold(percentage=100.0, band="CRITICAL"),
        ],
        default_alert_recipients=[],
        suggested_forecast_threshold=90.0,
    ),
    BudgetScopeType.BUSINESS_UNIT: BudgetTemplate(
        code="TMPL_BUSINESS_UNIT",
        scope_type=BudgetScopeType.BUSINESS_UNIT,
        display_name="Business Unit Annual Cloud Budget Template",
        description="Strategic Business Unit financial ceiling with showback reporting support.",
        default_period=BudgetPeriod.ANNUAL,
        default_thresholds=[
            BudgetThreshold(percentage=75.0, band="WARNING"),
            BudgetThreshold(percentage=90.0, band="HIGH"),
            BudgetThreshold(percentage=100.0, band="CRITICAL"),
        ],
        default_alert_recipients=[],
        suggested_forecast_threshold=95.0,
    ),
    BudgetScopeType.PROJECT: BudgetTemplate(
        code="TMPL_PROJECT",
        scope_type=BudgetScopeType.PROJECT,
        display_name="Capital Project Initiative Milestone Budget Template",
        description="Time-bound project or initiative budget with milestone-based burn velocity tracking.",
        default_period=BudgetPeriod.QUARTERLY,
        default_thresholds=[
            BudgetThreshold(percentage=70.0, band="WARNING"),
            BudgetThreshold(percentage=85.0, band="HIGH"),
            BudgetThreshold(percentage=100.0, band="CRITICAL"),
        ],
        default_alert_recipients=[],
        suggested_forecast_threshold=90.0,
    ),
}


def get_template_for_scope(scope_type: BudgetScopeType) -> BudgetTemplate:
    """Retrieves standard pre-configured budget template for a given scope type."""
    return BUDGET_TEMPLATES_BY_SCOPE[scope_type]


def list_all_budget_templates() -> list[BudgetTemplate]:
    """Returns all 17 scope type budget templates."""
    return list(BUDGET_TEMPLATES_BY_SCOPE.values())
