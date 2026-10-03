"""Master-Data-Driven Statement Templates & Narrative Phrasing Engine (Prompt 52).

Enforces:
- Statement layout, sections, groupings, and narrative phrasing as master data.
- Finance configures statement presentation without requiring code deployments.
- Standard default templates for Business Units, Cost Centres, and Applications.
"""

from __future__ import annotations

from decimal import Decimal

from domain.statements.models import StatementTemplate

# Canonical standard business unit executive template
STANDARD_BUSINESS_UNIT_TEMPLATE = StatementTemplate(
    template_id="tpl-standard-bu",
    name="Executive Business Unit Showback Pack",
    description="Standard executive summary, budget variance, and multi-dimensional allocation pack for Business Unit leaders.",
    sections_enabled=[
        "opening_summary",
        "kpi_summary",
        "budget_variance",
        "prior_period_comparison",
        "provider_breakdown",
        "service_category_breakdown",
        "application_breakdown",
        "environment_breakdown",
        "largest_movements",
        "shared_service_apportionment",
        "unallocated_cost",
        "discount_benefit",
        "governance_freshness",
    ],
    section_order=[
        "opening_summary",
        "kpi_summary",
        "budget_variance",
        "prior_period_comparison",
        "provider_breakdown",
        "service_category_breakdown",
        "application_breakdown",
        "environment_breakdown",
        "largest_movements",
        "shared_service_apportionment",
        "unallocated_cost",
        "discount_benefit",
        "governance_freshness",
    ],
    narrative_phrasing={
        "showback_banner": (
            "SHOWBACK STATEMENT — FOR INTERNAL MANAGEMENT INFORMATION ONLY. "
            "THIS STATEMENT DOES NOT CONSTITUTE A GENERAL LEDGER JOURNAL CHARGE."
        ),
        "budget_on_track": (
            "Spend of ${cost} is within the allocated budget of ${budget} "
            "with a favorable variance of ${variance} ({variance_pct}% headroom)."
        ),
        "budget_exceeded": (
            "Spend of ${cost} exceeded the allocated budget of ${budget} "
            "by ${variance} ({variance_pct}% overage)."
        ),
        "movement_increase": (
            "Spend increased by ${delta} ({pct}%) compared to prior period {prior_period}, "
            "primarily driven by {top_driver}."
        ),
        "movement_decrease": (
            "Spend decreased by ${delta} ({pct}%) compared to prior period {prior_period}."
        ),
        "movement_flat": "Spend remained consistent with prior period {prior_period} (under 1% variance).",
    },
)

# Canonical cost centre template
COST_CENTRE_TEMPLATE = StatementTemplate(
    template_id="tpl-cost-centre",
    name="Cost Centre Operational Showback Pack",
    description="Operational accounting showback pack organized by cost center with focus on service categories and shared platform apportionment.",
    sections_enabled=[
        "opening_summary",
        "kpi_summary",
        "budget_variance",
        "prior_period_comparison",
        "service_category_breakdown",
        "shared_service_apportionment",
        "unallocated_cost",
        "largest_movements",
        "discount_benefit",
        "governance_freshness",
    ],
    section_order=[
        "opening_summary",
        "kpi_summary",
        "budget_variance",
        "prior_period_comparison",
        "service_category_breakdown",
        "shared_service_apportionment",
        "unallocated_cost",
        "largest_movements",
        "discount_benefit",
        "governance_freshness",
    ],
    narrative_phrasing={
        "showback_banner": (
            "SHOWBACK STATEMENT — COST CENTRE MANAGEMENT ACCOUNTING. "
            "OPERATIONAL COST ALLOCATION ONLY. NOT A FORMAL ERP GL POSTING."
        ),
        "budget_on_track": "Operating costs of ${cost} tracked favorably against budget ${budget} (${variance} surplus).",
        "budget_exceeded": "Operating costs of ${cost} exceeded budget ceiling ${budget} (${variance} overrun).",
        "movement_increase": "Operational spend increased by ${delta} ({pct}%) from period {prior_period}.",
        "movement_decrease": "Operational spend declined by ${delta} ({pct}%) from period {prior_period}.",
        "movement_flat": "Operating expenses steady compared to {prior_period}.",
    },
)

# Canonical engineering application template
APPLICATION_TEMPLATE = StatementTemplate(
    template_id="tpl-application-eng",
    name="Engineering Application Showback Pack",
    description="Application engineering workload showback with breakdown by environment, cloud provider, and shared infrastructure.",
    sections_enabled=[
        "opening_summary",
        "kpi_summary",
        "budget_variance",
        "environment_breakdown",
        "provider_breakdown",
        "largest_movements",
        "shared_service_apportionment",
        "discount_benefit",
    ],
    section_order=[
        "opening_summary",
        "kpi_summary",
        "budget_variance",
        "environment_breakdown",
        "provider_breakdown",
        "largest_movements",
        "shared_service_apportionment",
        "discount_benefit",
    ],
    narrative_phrasing={
        "showback_banner": (
            "ENGINEERING WORKLOAD SHOWBACK — INFRASTRUCTURE CONSUMPTION REPORT. "
            "FOR WORKLOAD EFFICIENCY OPTIMIZATION."
        ),
        "budget_on_track": "Workload infrastructure spend of ${cost} is within targeted threshold of ${budget}.",
        "budget_exceeded": "Workload infrastructure spend of ${cost} exceeded target threshold of ${budget}.",
        "movement_increase": "Workload compute/storage consumption increased by ${delta} ({pct}%) from {prior_period}.",
        "movement_decrease": "Workload consumption decreased by ${delta} ({pct}%) from {prior_period}.",
        "movement_flat": "Workload consumption was flat compared to {prior_period}.",
    },
)


DEFAULT_STATEMENT_TEMPLATES: dict[str, StatementTemplate] = {
    STANDARD_BUSINESS_UNIT_TEMPLATE.template_id: STANDARD_BUSINESS_UNIT_TEMPLATE,
    COST_CENTRE_TEMPLATE.template_id: COST_CENTRE_TEMPLATE,
    APPLICATION_TEMPLATE.template_id: APPLICATION_TEMPLATE,
}


class StatementTemplateEngine:
    """Evaluates and renders narrative phrasing based on configured templates."""

    def __init__(self, templates: dict[str, StatementTemplate] | None = None) -> None:
        self._templates: dict[str, StatementTemplate] = dict(
            templates or DEFAULT_STATEMENT_TEMPLATES
        )

    def get_template(self, template_id: str | None) -> StatementTemplate:
        """Retrieves template by ID or falls back to STANDARD_BUSINESS_UNIT_TEMPLATE."""
        if not template_id or template_id not in self._templates:
            return STANDARD_BUSINESS_UNIT_TEMPLATE
        return self._templates[template_id]

    def register_template(self, template: StatementTemplate) -> None:
        """Registers or updates a statement template."""
        self._templates[template.template_id] = template

    def list_templates(self) -> list[StatementTemplate]:
        """Lists all registered templates."""
        return list(self._templates.values())

    def render_budget_commentary(
        self,
        template: StatementTemplate,
        cost: Decimal,
        budget: Decimal,
        variance: Decimal,
        variance_pct: Decimal,
    ) -> str:
        """Generates dynamic natural language commentary on budget status."""
        phrasing = template.narrative_phrasing
        if budget <= Decimal("0.00"):
            return f"Total spend of ${cost:,.2f} has no formal budget ceiling assigned for this period."

        if cost <= budget:
            tpl = phrasing.get(
                "budget_on_track",
                "Spend of ${cost} is within allocated budget of ${budget} by ${variance} ({variance_pct}% headroom).",
            )
            fav_variance = abs(variance)
            return tpl.format(
                cost=f"{cost:,.2f}",
                budget=f"{budget:,.2f}",
                variance=f"{fav_variance:,.2f}",
                variance_pct=f"{abs(variance_pct):.1f}",
            )
        else:
            tpl = phrasing.get(
                "budget_exceeded",
                "Spend of ${cost} exceeded allocated budget of ${budget} by ${variance} ({variance_pct}% overage).",
            )
            return tpl.format(
                cost=f"{cost:,.2f}",
                budget=f"{budget:,.2f}",
                variance=f"{variance:,.2f}",
                variance_pct=f"{variance_pct:.1f}",
            )

    def render_movement_commentary(
        self,
        template: StatementTemplate,
        current: Decimal,
        prior: Decimal,
        delta: Decimal,
        pct: Decimal,
        prior_period: str,
        top_driver: str | None = None,
    ) -> str:
        """Generates dynamic commentary on period-over-period cost movement."""
        phrasing = template.narrative_phrasing
        if prior <= Decimal("0.00"):
            return f"Initial baseline period. Current spend is ${current:,.2f}."

        if abs(pct) < Decimal("1.0"):
            tpl = phrasing.get(
                "movement_flat",
                "Spend remained consistent with prior period {prior_period} (under 1% variance).",
            )
            return tpl.format(prior_period=prior_period)

        if delta > Decimal("0.00"):
            tpl = phrasing.get(
                "movement_increase",
                "Spend increased by ${delta} ({pct}%) compared to prior period {prior_period} primarily driven by {top_driver}.",
            )
            return tpl.format(
                delta=f"{delta:,.2f}",
                pct=f"{pct:.1f}",
                prior_period=prior_period,
                top_driver=top_driver or "general workload expansion",
            )
        else:
            tpl = phrasing.get(
                "movement_decrease",
                "Spend decreased by ${delta} ({pct}%) compared to prior period {prior_period}.",
            )
            return tpl.format(
                delta=f"{abs(delta):,.2f}",
                pct=f"{abs(pct):.1f}",
                prior_period=prior_period,
            )
