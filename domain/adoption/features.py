"""Feature Adoption & Dormancy Identification Engine (Prompt 61 / BBP Section 43).

Enforces:
- Identifies which capabilities are configured and used versus enabled but dormant.
- Acceptance requirement: A capability that is enabled but never used is identifiable.
- Surfaces dead features with actionable recommendations: promote, fix, or deprecate.
"""

from __future__ import annotations

import logging

from domain.adoption.models import (
    FeatureAdoptionItem,
    FeatureAdoptionReport,
)
from domain.models.enums import FeatureAdoptionStatus
from domain.tenant.context import TenantContext

logger = logging.getLogger(__name__)

CANONICAL_PLATFORM_CAPABILITIES = [
    {
        "key": "budget_planning",
        "name": "Budget Planning & Scenarios (Prompt 57)",
        "category": "FINANCIAL",
    },
    {
        "key": "commitment_renewal",
        "name": "Commitment & Coverage Management (Prompt 58)",
        "category": "FINANCIAL",
    },
    {
        "key": "decommissioning_workflow",
        "name": "Resource Lifecycle & Decommissioning (Prompt 59)",
        "category": "GOVERNANCE",
    },
    {
        "key": "itsm_integration",
        "name": "ITSM Bidirectional Ticket Sync (Prompt 60)",
        "category": "INTEGRATION",
    },
    {
        "key": "analytical_extract",
        "name": "Scheduled Analytical Extract & Semantic BI (Prompt 56)",
        "category": "ANALYTICS",
    },
    {
        "key": "remediation_tasks",
        "name": "Remediation & Realised Saving Ledger (Prompt 51)",
        "category": "GOVERNANCE",
    },
    {
        "key": "anomaly_alerting",
        "name": "Contextual Alerting & Storm Grouping (Prompt 31)",
        "category": "MONITORING",
    },
    {
        "key": "bulk_import",
        "name": "Generic Master Data Bulk Import (Prompt 53)",
        "category": "OPERATIONS",
    },
]


class FeatureAdoptionService:
    """Evaluates configured platform features against observed empirical telemetry."""

    def evaluate_feature_adoption(
        self,
        enabled_feature_flags: dict[str, bool],
        usage_by_feature: dict[str, int],
        active_teams_by_feature: dict[str, int] | None = None,
        *,
        tenant_context: TenantContext,
    ) -> FeatureAdoptionReport:
        """Categorises all platform features into active, dormant, or disabled states."""
        active: list[FeatureAdoptionItem] = []
        dormant: list[FeatureAdoptionItem] = []
        disabled: list[FeatureAdoptionItem] = []

        teams_map = active_teams_by_feature or {}

        for cap in CANONICAL_PLATFORM_CAPABILITIES:
            f_key = cap["key"]
            f_name = cap["name"]
            cat = cap["category"]

            is_enabled = enabled_feature_flags.get(f_key, True)
            actions_count = usage_by_feature.get(f_key, 0)
            teams_count = teams_map.get(f_key, 1 if actions_count > 0 else 0)

            if not is_enabled:
                item = FeatureAdoptionItem(
                    feature_key=f_key,
                    feature_name=f_name,
                    category=cat,
                    enabled=False,
                    status=FeatureAdoptionStatus.DISABLED,
                    usage_count_last_30_days=0,
                    active_teams_count=0,
                    recommendation="FEATURE_DISABLED",
                )
                disabled.append(item)
            elif actions_count > 0:
                rec = "HEALTHY" if actions_count >= 5 else "INVESTIGATE_LOW_ADOPTION"
                item = FeatureAdoptionItem(
                    feature_key=f_key,
                    feature_name=f_name,
                    category=cat,
                    enabled=True,
                    status=FeatureAdoptionStatus.CONFIGURED_AND_USED,
                    usage_count_last_30_days=actions_count,
                    active_teams_count=teams_count,
                    recommendation=rec,
                )
                active.append(item)
            else:
                # Enabled in config but ZERO usage -> DORMANT!
                item = FeatureAdoptionItem(
                    feature_key=f_key,
                    feature_name=f_name,
                    category=cat,
                    enabled=True,
                    status=FeatureAdoptionStatus.ENABLED_DORMANT,
                    usage_count_last_30_days=0,
                    active_teams_count=0,
                    recommendation="PROMOTE_DORMANT_FEATURE",
                )
                dormant.append(item)

        total_enabled = len(active) + len(dormant)
        dormancy_rate = (
            round((len(dormant) / total_enabled * 100.0) if total_enabled > 0 else 0.0, 1)
        )

        report = FeatureAdoptionReport(
            tenant_id=tenant_context.tenant_id,
            active_features=active,
            dormant_features=dormant,
            disabled_features=disabled,
            dormancy_rate=dormancy_rate,
        )

        logger.info(
            "Feature Adoption Analysis for tenant '%s': %d Active, %d Dormant (%0.1f%% dormancy rate), %d Disabled.",
            tenant_context.tenant_id,
            len(active),
            len(dormant),
            dormancy_rate,
            len(disabled),
        )
        return report
