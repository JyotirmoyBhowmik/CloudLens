"""Approval Authority Master (AM-12) Resolver (Prompt 55).

Enforces:
- Master data driven approval-authority resolution (AM-12).
- Never resolves approvers to named individuals in code.
- Resolves to authorized organizational roles or resolution strategies
  (e.g., FINOPS_ADMIN, SCOPE_OWNER, COST_CENTRE_OWNER, BU_OWNER).
- Enforces amount band thresholds and SLA working hours.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from domain.models.enums import ApprovalChainMode, ApproverResolutionType
from domain.provisioning.models import ApprovalAuthorityRule

logger = logging.getLogger(__name__)


class ApprovalAuthorityMaster:
    """AM-12 Master Engine resolving authorized approvers by scope and value threshold."""

    def __init__(self, rules: list[ApprovalAuthorityRule] | None = None) -> None:
        self._rules: list[ApprovalAuthorityRule] = rules or []

    def register_rule(self, rule: ApprovalAuthorityRule) -> None:
        """Registers or replaces an AM-12 authority rule."""
        self._rules = [r for r in self._rules if r.rule_id != rule.rule_id]
        self._rules.append(rule)

    def resolve_authority(
        self,
        scope_type: str,
        scope_code: str,
        monthly_amount: Decimal,
    ) -> ApprovalAuthorityRule:
        """Resolves the governing approval authority rule from AM-12 master data.

        Returns an ApprovalAuthorityRule indicating the required role/resolution type,
        chain mode, and SLA working hours.
        NEVER returns named individuals in code.
        """
        st_norm = scope_type.strip().upper()
        sc_norm = scope_code.strip()

        candidates: list[ApprovalAuthorityRule] = []
        for r in self._rules:
            # Check monthly amount threshold
            if monthly_amount < r.min_monthly_amount:
                continue
            if r.max_monthly_amount is not None and monthly_amount > r.max_monthly_amount:
                continue

            r_type = r.scope_type.strip().upper()
            r_code = r.scope_code.strip()

            type_matches = r_type == "*" or r_type == st_norm
            code_matches = r_code == "*" or r_code.lower() == sc_norm.lower()

            if type_matches and code_matches:
                candidates.append(r)

        if not candidates:
            logger.info(
                "No specific AM-12 rule for scope_type=%s, scope_code=%s, amount=%s; returning default FinOps role",
                st_norm,
                sc_norm,
                monthly_amount,
            )
            return ApprovalAuthorityRule(
                rule_id="AM12-DEFAULT",
                scope_type=st_norm,
                scope_code=sc_norm,
                min_monthly_amount=Decimal("0.00"),
                max_monthly_amount=None,
                approver_role="FINOPS_ADMIN",
                approver_resolution=ApproverResolutionType.ROLE,
                chain_mode=ApprovalChainMode.SERIAL,
                sla_working_hours=24,
            )

        # Sort by specificity: exact code > wildcard code, then highest min_monthly_amount
        def specificity_key(rule: ApprovalAuthorityRule) -> tuple[int, Decimal]:
            score = 1 if rule.scope_code.strip() != "*" else 0
            return (score, rule.min_monthly_amount)

        best_rule = max(candidates, key=specificity_key)
        return best_rule
