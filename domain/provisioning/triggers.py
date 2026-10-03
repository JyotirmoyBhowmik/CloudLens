"""Gate Trigger Engine (Prompt 55).

Enforces:
- Master-data gate triggers configurable per scope, per environment, and per value band.
- Actions: NO_GATE, NOTIFY_ONLY, APPROVAL_REQUIRED, APPROVAL_REQUIRED_SPECIFIC_CHAIN.
- HARD RULE: Default every trigger to NOTIFY_ONLY so that the organization
  opts into control rather than discovering it.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from domain.provisioning.models import GateTriggerAction, GateTriggerRule

logger = logging.getLogger(__name__)


class GateTriggerEngine:
    """Evaluates master-data gate trigger rules against proposed deployments."""

    def __init__(self, rules: list[GateTriggerRule] | None = None) -> None:
        self._rules: list[GateTriggerRule] = rules or []

    def register_rule(self, rule: GateTriggerRule) -> None:
        """Adds or updates a trigger rule."""
        self._rules = [r for r in self._rules if r.rule_id != rule.rule_id]
        self._rules.append(rule)

    def evaluate_trigger(
        self,
        scope_code: str,
        environment: str,
        monthly_cost: Decimal,
    ) -> tuple[GateTriggerAction, str | None]:
        """Evaluates gate trigger action.

        Precedence:
        1. Exact scope and exact environment
        2. Exact scope and wildcard environment ('*')
        3. Wildcard scope ('*') and exact environment
        4. Wildcard scope ('*') and wildcard environment ('*')
        5. HARD RULE: If no rule matches, default to NOTIFY_ONLY.

        Returns (GateTriggerAction, approver_chain_id).
        """
        env_upper = environment.strip().upper()
        norm_scope = scope_code.strip()

        candidates: list[GateTriggerRule] = []
        for r in self._rules:
            # Check monthly amount band
            if monthly_cost < r.min_monthly_amount:
                continue
            if r.max_monthly_amount is not None and monthly_cost > r.max_monthly_amount:
                continue

            r_scope = r.scope_code.strip()
            r_env = r.environment.strip().upper()

            scope_matches = r_scope == "*" or r_scope.lower() == norm_scope.lower()
            env_matches = r_env == "*" or r_env == env_upper

            if scope_matches and env_matches:
                candidates.append(r)

        if not candidates:
            # HARD RULE: Default every trigger to NOTIFY_ONLY
            logger.info(
                "No gate trigger rule matched for scope=%s, env=%s, amount=%s; defaulting to NOTIFY_ONLY",
                norm_scope,
                env_upper,
                monthly_cost,
            )
            return GateTriggerAction.NOTIFY_ONLY, None

        # Sort by specificity:
        # Score 3: exact scope, exact env
        # Score 2: exact scope, wildcard env
        # Score 1: wildcard scope, exact env
        # Score 0: wildcard scope, wildcard env
        def specificity_key(rule: GateTriggerRule) -> tuple[int, Decimal]:
            score = 0
            if rule.scope_code.strip() != "*":
                score += 2
            if rule.environment.strip().upper() != "*":
                score += 1
            # In case of tie, higher min_monthly_amount is more specific
            return (score, rule.min_monthly_amount)

        best_rule = max(candidates, key=specificity_key)
        return best_rule.action, best_rule.approver_chain_id
