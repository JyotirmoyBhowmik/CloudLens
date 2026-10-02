"""Restricted Node Evaluation and RBAC Masking Engine (Prompt 33 / BBP Section 25).

Enforces:
1. Restricted-node rule: Nodes the user is not entitled to see render as Restricted
   placeholders rather than being omitted.
2. Negative constraint: Do NOT silently omit inaccessible nodes.
3. Evaluates caller TenantContext and ScopeGrants using ScopeGrantEvaluator.
4. Masks entity display names, financial metrics, and operational metadata while
   preserving graph topology and edge connectivity.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from domain.models.enums import (
    EntityReferenceType,
    NodeCostTrend,
    NodeScheduleState,
    ThresholdBadge,
    TopologyBudgetStatus,
    TopologyPricingClassification,
)
from domain.rbac.evaluator import ScopeGrantEvaluator
from domain.rbac.models import AuthorizationDecision, ResourceTarget, ScopeGrant
from domain.tenant.context import TenantContext, require_tenant_context
from domain.topology.models import NodeEnrichmentData, TopologyEdge, TopologyNode

logger = logging.getLogger(__name__)

RESTRICTED_DISPLAY_NAME_PREFIX = "[Restricted"
RESTRICTED_DEFAULT_NAME = "[Restricted Entity]"


class RestrictedNodeEvaluator:
    """Evaluates caller entitlement to topology nodes and applies privacy masking."""

    def __init__(
        self,
        scope_evaluator: ScopeGrantEvaluator | None = None,
        default_allow_admin: bool = True,
    ) -> None:
        self.scope_evaluator = scope_evaluator or ScopeGrantEvaluator()
        self.default_allow_admin = default_allow_admin

    def evaluate_access(
        self,
        node: TopologyNode,
        *,
        grants: list[ScopeGrant] | None = None,
        tenant_context: TenantContext,
    ) -> bool:
        """Determines if the caller has entitlement to view full details of this node.

        Returns True if authorized, False if access should be restricted.
        """
        tc = require_tenant_context(tenant_context)

        # If no explicit grants exist in tenant context and user is superadmin/platform admin,
        # or grants list is empty, evaluate RBAC scope
        active_grants = grants or []

        # If user has explicit Super Admin or Platform Admin role codes in context, allow access
        roles = tc.roles if hasattr(tc, "roles") and tc.roles else []
        if any(
            r in ("SUPER_ADMIN", "PLATFORM_ADMIN", "super_admin", "platform_admin") for r in roles
        ):
            return True

        if not active_grants:
            # When no grants are configured, default to allowing tenant members access to their own tenant's topology
            return True

        # Build ResourceTarget from node attributes
        enrichment = node.enrichment
        provider = enrichment.provider if enrichment else None
        cost_center = enrichment.cost_center if enrichment else None
        business_unit = enrichment.business_unit if enrichment else None

        app_id = None
        if node.entity_ref.entity_type == EntityReferenceType.APPLICATION:
            app_id = node.entity_ref.entity_id

        target = ResourceTarget(
            resource_id=node.entity_ref.entity_id,
            provider=provider,
            account_id=node.entity_ref.entity_id
            if node.entity_ref.entity_type == EntityReferenceType.SCOPE
            else None,
            application_id=app_id,
            project_id=node.entity_ref.entity_id
            if node.entity_ref.entity_type == EntityReferenceType.SCOPE
            else None,
            cost_centre_id=cost_center,
            business_unit_id=business_unit,
        )

        decision: AuthorizationDecision = self.scope_evaluator.evaluate_scope_grants(
            user_id=tc.user_id,
            tenant_id=tc.tenant_id,
            role_codes=roles,
            grants=active_grants,
            target=target,
        )

        return decision.allowed

    def mask_node(self, node: TopologyNode) -> TopologyNode:
        """Applies privacy masking to an inaccessible node while retaining graph topology."""
        entity_type_name = node.entity_ref.entity_type.value.capitalize()
        masked_name = f"{RESTRICTED_DISPLAY_NAME_PREFIX} {entity_type_name}]"

        masked_enrichment = NodeEnrichmentData(
            status="RESTRICTED",
            cost=Decimal("0.0"),
            currency=node.enrichment.currency if node.enrichment else "USD",
            budget_utilisation_pct=None,
            budget_status=TopologyBudgetStatus.OK,
            runtime_state=NodeScheduleState.UNKNOWN,
            usage={},
            threshold_state=ThresholdBadge.GREEN,
            cost_trend=NodeCostTrend.STABLE,
            cost_trend_pct=0.0,
            forecast_cost=None,
            pricing_classification=TopologyPricingClassification.ON_DEMAND,
            owner="[Restricted]",
            business_unit="[Restricted]",
            cost_center="[Restricted]",
            provider=node.enrichment.provider if node.enrichment else None,
            tags={"access": "restricted"},
        )

        return node.model_copy(
            update={
                "display_name": masked_name,
                "is_restricted": True,
                "direct_cost": Decimal("0.0"),
                "attributed_chain_cost": Decimal("0.0"),
                "cost_share_pct": 0.0,
                "enrichment": masked_enrichment,
            }
        )

    def mask_edges_for_restricted_nodes(
        self, edges: list[TopologyEdge], restricted_node_ids: set[str]
    ) -> list[TopologyEdge]:
        """Marks edges that touch restricted nodes."""
        updated_edges: list[TopologyEdge] = []
        for e in edges:
            if e.source_id in restricted_node_ids or e.target_id in restricted_node_ids:
                updated_edges.append(e.model_copy(update={"is_restricted": True}))
            else:
                updated_edges.append(e)
        return updated_edges
