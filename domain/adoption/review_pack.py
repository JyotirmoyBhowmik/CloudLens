"""Quarterly Platform Review Pack Generator (Prompt 61 / Prompt 35 Pattern).

Enforces:
- Single-Action Generation: The complete review pack generates in one cohesive operation.
- Six Executive Review Dimensions:
  1. Adoption Telemetry (by role and team, with non-surveillance privacy notice)
  2. Governance Operations (MTTA, MTTC, aging, open/closed trend)
  3. Platform Value Ledger (empirical realised savings alongside platform self-costs and ROI multiple)
  4. Data Quality Score (composite score with 7 inspectable components)
  5. Feature Adoption (active vs dormant capabilities)
  6. Onboarding Maturity Funnel (progression and stalled scope identification)
- Generates structured DTO and formal steering committee markdown document.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any

from domain.adoption.models import (
    DataQualityReport,
    FeatureAdoptionReport,
    GovernanceOperationsReport,
    OnboardingFunnelReport,
    PlatformValueLedgerReport,
    QuarterlyReviewPack,
    UsageTelemetryReport,
)
from domain.tenant.context import TenantContext

logger = logging.getLogger(__name__)


class QuarterlyReviewPackGenerator:
    """Consolidates all adoption, governance, and financial evidence into an executive steering committee review pack."""

    def generate_review_pack(
        self,
        quarter_label: str,
        *,
        adoption_summary: UsageTelemetryReport,
        governance_operations: GovernanceOperationsReport,
        value_ledger: PlatformValueLedgerReport,
        data_quality: DataQualityReport,
        feature_adoption: FeatureAdoptionReport,
        onboarding_funnel: OnboardingFunnelReport,
        outstanding_governance_gaps: list[dict[str, Any]] | None = None,
        tenant_context: TenantContext,
    ) -> QuarterlyReviewPack:
        """Generates the consolidated steering committee review pack in one action."""
        now = dt.datetime.now(dt.UTC)
        gaps = outstanding_governance_gaps or []

        # Executive Summary Narrative
        exec_summary = (
            f"During {quarter_label}, CloudLens delivered a verified cumulative net value of "
            f"${float(value_ledger.net_value_delivered):,.2f} ({value_ledger.roi_multiple}x ROI) after "
            f"accounting for platform self-costs of ${float(value_ledger.platform_running_cost.total_platform_cost):,.2f}. "
            f"Overall enterprise Data Quality scored {data_quality.headline_score:.1f}% [{data_quality.rating.value}], "
            f"with governance operations closing {governance_operations.tasks.closed_count} remediation tasks "
            f"({governance_operations.tasks.closure_rate:.1f}% closure rate, MTTC {governance_operations.tasks.mean_time_to_close_hours:.1f}h). "
            f"Feature adoption demonstrates {len(feature_adoption.active_features)} active capabilities with "
            f"{len(feature_adoption.dormant_features)} dormant capabilities requiring promotional focus."
        )

        # Build Markdown Document
        doc_lines = [
            f"# CloudLens Platform Quarterly Review Pack — {quarter_label}",
            f"**Organization:** {tenant_context.tenant_id} | **Evaluated At:** {now.strftime('%Y-%m-%d %H:%M UTC')}",
            "",
            "## 1. Executive Summary",
            exec_summary,
            "",
            "## 2. Platform Value Case & ROI Ledger",
            f"- **Cumulative Realised Savings:** ${float(value_ledger.cumulative_realised_savings):,.2f}",
            f"- **Platform Operating Cost:** ${float(value_ledger.platform_running_cost.total_platform_cost):,.2f}",
            f"  - BigQuery Query Charges: ${float(value_ledger.platform_running_cost.bigquery_query_cost):,.2f}",
            f"  - Connector API Call Charges: ${float(value_ledger.platform_running_cost.connector_api_cost):,.2f}",
            f"  - Infrastructure Base Hosting: ${float(value_ledger.platform_running_cost.infrastructure_hosting_cost):,.2f}",
            f"- **Net Value Delivered:** ${float(value_ledger.net_value_delivered):,.2f}",
            f"- **Platform ROI Multiple:** **{value_ledger.roi_multiple}x**",
            "",
            "### Savings Attributed by Operational Lever",
        ]

        for src, amt in value_ledger.savings_by_source.items():
            doc_lines.append(f"- **{src}:** ${float(amt):,.2f}")

        doc_lines.extend(
            [
                "",
                "## 3. Data Quality Score & Component Inspection",
                f"**Headline Composite Score:** **{data_quality.headline_score:.1f}%** ({data_quality.rating.value})",
                "",
                "| Component Dimension | Score | Weight | Inspection Details |",
                "| :--- | :--- | :--- | :--- |",
            ]
        )

        for comp in data_quality.components:
            details_str = ", ".join(f"{k}={v}" for k, v in list(comp.inspectable_details.items())[:3])
            doc_lines.append(
                f"| `{comp.component_name}` | {comp.score:.1f}% | {int(comp.weight * 100)}% | {details_str or 'Compliant'} |"
            )

        doc_lines.extend(
            [
                "",
                "## 4. Governance Operations & Process Velocity",
                f"- **Alerts Raised / Acknowledged / Actioned:** {governance_operations.alerts.raised_count} / {governance_operations.alerts.acknowledged_count} / {governance_operations.alerts.actioned_count} ({governance_operations.alerts.acknowledgement_rate:.1f}%)",
                f"- **Mean Time to Acknowledge (MTTA):** {governance_operations.alerts.mean_time_to_acknowledge_hours:.1f} hours",
                f"- **Tasks Created / Closed / Verified:** {governance_operations.tasks.created_count} / {governance_operations.tasks.closed_count} / {governance_operations.tasks.verified_count} ({governance_operations.tasks.closure_rate:.1f}%)",
                f"- **Mean Time to Close (MTTC):** {governance_operations.tasks.mean_time_to_close_hours:.1f} hours",
                f"- **Overdue Tasks:** {governance_operations.overdue_aging.total_overdue} total (1-7d: {governance_operations.overdue_aging.overdue_1_to_7_days}, 8-30d: {governance_operations.overdue_aging.overdue_8_to_30_days}, >30d: {governance_operations.overdue_aging.overdue_30_plus_days})",
                f"- **Active Governance Exemptions:** {governance_operations.exemptions.active_exemptions}",
                "",
                "## 5. Usage Telemetry & Role Adoption",
                "> [!NOTE]",
                f"> {adoption_summary.privacy_policy_notice}",
                "",
                f"- **Total Telemetry Events:** {adoption_summary.total_events}",
                f"- **Active Roles Engaged:** {len(adoption_summary.aggregations_by_role)}",
                f"- **Active Teams Engaged:** {len(adoption_summary.aggregations_by_team)}",
                "",
                "## 6. Feature Adoption & Dormant Capability Analysis",
                f"- **Active Features:** {len(feature_adoption.active_features)}",
                f"- **Dormant Features (Enabled but 0 usage):** {len(feature_adoption.dormant_features)} ({feature_adoption.dormancy_rate:.1f}% dormancy rate)",
                "",
                "## 7. Onboarding Maturity Funnel",
                f"- **Total Scopes Tracked:** {onboarding_funnel.total_scopes}",
                f"- **Completed Full Funnel:** {onboarding_funnel.completed_funnels}",
                f"- **Stalled Scopes (>14 days in stage):** {onboarding_funnel.stalled_funnels}",
            ]
        )

        if gaps:
            doc_lines.extend(
                [
                    "",
                    "## 8. Outstanding Governance Gaps & Recommended Interventions",
                ]
            )
            for g in gaps:
                doc_lines.append(f"- **Finding:** {g.get('finding', 'N/A')} — **Action:** {g.get('action', 'N/A')}")

        doc_lines.extend(
            [
                "",
                "---",
                "*Generated automatically by CloudLens Platform Review Pack Engine.*",
            ]
        )

        pack = QuarterlyReviewPack(
            tenant_id=tenant_context.tenant_id,
            quarter_label=quarter_label,
            generated_at=now,
            executive_summary=exec_summary,
            adoption_summary=adoption_summary,
            governance_operations=governance_operations,
            value_ledger=value_ledger,
            data_quality=data_quality,
            feature_adoption=feature_adoption,
            onboarding_funnel=onboarding_funnel,
            outstanding_governance_gaps=gaps,
            document_markdown="\n".join(doc_lines),
        )

        logger.info(
            "Generated Steering Committee Review Pack '%s' for '%s' in one action.",
            pack.pack_id,
            quarter_label,
        )
        return pack
