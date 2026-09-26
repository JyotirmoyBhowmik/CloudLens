"""Allocation Rule Engine with First-Match-Wins Precedence (Prompt 08 Item 57, 58).

Enforces:
1. Strict first-match-wins precedence order:
   - Direct resource assignment
   - Tag rule
   - Scope rule
   - Service rule
   - Split rule (proportional or fixed, validated to sum to 100%)
   - Unallocated fallback
2. Split rule percentages must sum to 100% or be rejected at save time.
3. Every allocated cost row records the winning rule and audit explanation.
4. Unallocated cost is never absorbed or hidden into another bucket.
"""

from decimal import Decimal

from domain.attribution.models import (
    AllocatedCostRow,
    AllocationRule,
    AllocationRuleType,
)
from domain.models.exceptions import InvalidSplitRuleException
from domain.models.facts import CostFact
from domain.models.inventory import Resource, Service
from domain.rules.monetary import round_currency, to_decimal
from normalisation.tags.models import NormalizedTag


class AllocationRuleEngine:
    """Evaluates cost facts against configured FinOps allocation rules."""

    def __init__(self, rules: list[AllocationRule] | None = None) -> None:
        self.rules: list[AllocationRule] = []
        if rules:
            for r in rules:
                self.add_rule(r)

    def add_rule(self, rule: AllocationRule) -> None:
        """Adds a rule to the engine. Rejects invalid split rules at save time."""
        # Validation already triggered by Pydantic model_validator, but explicitly double-checked
        if rule.rule_type == AllocationRuleType.SPLIT_RULE:
            if not rule.split_targets:
                raise InvalidSplitRuleException(
                    f"Split rule '{rule.name}' must have at least one split target."
                )
            total = sum(t.percentage for t in rule.split_targets)
            if total != Decimal("100.0"):
                raise InvalidSplitRuleException(
                    f"Split rule '{rule.name}' percentages sum to {total}%, expected exactly 100.0%."
                )

        self.rules.append(rule)
        # Sort rules by precedence tier, then by priority
        self._sort_rules()

    def _rule_tier_rank(self, rule_type: AllocationRuleType) -> int:
        if rule_type == AllocationRuleType.DIRECT_RESOURCE:
            return 1
        if rule_type == AllocationRuleType.TAG_RULE:
            return 2
        if rule_type == AllocationRuleType.SCOPE_RULE:
            return 3
        if rule_type == AllocationRuleType.SERVICE_RULE:
            return 4
        if rule_type == AllocationRuleType.SPLIT_RULE:
            return 5
        return 6

    def _sort_rules(self) -> None:
        self.rules.sort(key=lambda r: (self._rule_tier_rank(r.rule_type), r.priority))

    def allocate_cost_fact(
        self,
        cost_fact: CostFact,
        resource: Resource | None = None,
        tags: list[NormalizedTag] | None = None,
        service: Service | None = None,
    ) -> list[AllocatedCostRow]:
        """Evaluates cost fact against rules with first-match-wins semantics.

        Returns one or more AllocatedCostRow instances (multiple rows in case of split rule).
        """
        # Determine total cost to allocate (effective cost takes priority, fallback billed cost)
        total_cost = (
            cost_fact.effective_cost.value_or(Decimal("0.00"))
            if cost_fact.effective_cost.is_present
            else cost_fact.billed_cost.value_or(Decimal("0.00"))
        )
        total_cost_dec = to_decimal(total_cost)

        active_rules = [r for r in self.rules if r.is_active]

        for rule in active_rules:
            # --------------------------------------------------------------
            # Tier 1: Direct Resource Assignment
            # --------------------------------------------------------------
            if rule.rule_type == AllocationRuleType.DIRECT_RESOURCE:
                matched = False
                if rule.match_resource_id:
                    if resource and resource.id == rule.match_resource_id:
                        matched = True
                    elif cost_fact.resource_id == rule.match_resource_id:
                        matched = True

                if matched:
                    return [
                        AllocatedCostRow(
                            cost_fact_id=cost_fact.id,
                            resource_id=cost_fact.resource_id,
                            scope_id=cost_fact.scope_id,
                            total_cost=total_cost_dec,
                            allocated_amount=total_cost_dec,
                            currency=cost_fact.billing_currency,
                            cost_center_code=rule.target_cost_center_code or "UNALLOCATED",
                            business_unit_code=rule.target_business_unit_code,
                            project_code=rule.target_project_code,
                            winning_rule_type=AllocationRuleType.DIRECT_RESOURCE,
                            winning_rule_id=rule.id,
                            winning_rule_name=rule.name,
                            rule_explanation=(
                                f"Direct resource assignment matched rule '{rule.name}' for "
                                f"resource '{rule.match_resource_id}'"
                            ),
                            split_percentage=Decimal("100.0"),
                        )
                    ]

            # --------------------------------------------------------------
            # Tier 2: Tag Rule
            # --------------------------------------------------------------
            elif rule.rule_type == AllocationRuleType.TAG_RULE:
                matched = False
                matched_tag_desc = ""
                if tags and rule.match_tag_key:
                    for t in tags:
                        if t.normalized_key.lower() == rule.match_tag_key.lower():
                            if (
                                rule.match_tag_value is None
                                or t.value.strip().lower() == rule.match_tag_value.lower()
                            ):
                                matched = True
                                matched_tag_desc = f"{t.normalized_key}={t.value}"
                                break

                if matched:
                    return [
                        AllocatedCostRow(
                            cost_fact_id=cost_fact.id,
                            resource_id=cost_fact.resource_id,
                            scope_id=cost_fact.scope_id,
                            total_cost=total_cost_dec,
                            allocated_amount=total_cost_dec,
                            currency=cost_fact.billing_currency,
                            cost_center_code=rule.target_cost_center_code or "UNALLOCATED",
                            business_unit_code=rule.target_business_unit_code,
                            project_code=rule.target_project_code,
                            winning_rule_type=AllocationRuleType.TAG_RULE,
                            winning_rule_id=rule.id,
                            winning_rule_name=rule.name,
                            rule_explanation=(
                                f"Tag allocation rule '{rule.name}' matched tag '{matched_tag_desc}'"
                            ),
                            split_percentage=Decimal("100.0"),
                        )
                    ]

            # --------------------------------------------------------------
            # Tier 3: Scope Rule
            # --------------------------------------------------------------
            elif rule.rule_type == AllocationRuleType.SCOPE_RULE:
                if rule.match_scope_id and cost_fact.scope_id == rule.match_scope_id:
                    return [
                        AllocatedCostRow(
                            cost_fact_id=cost_fact.id,
                            resource_id=cost_fact.resource_id,
                            scope_id=cost_fact.scope_id,
                            total_cost=total_cost_dec,
                            allocated_amount=total_cost_dec,
                            currency=cost_fact.billing_currency,
                            cost_center_code=rule.target_cost_center_code or "UNALLOCATED",
                            business_unit_code=rule.target_business_unit_code,
                            project_code=rule.target_project_code,
                            winning_rule_type=AllocationRuleType.SCOPE_RULE,
                            winning_rule_id=rule.id,
                            winning_rule_name=rule.name,
                            rule_explanation=(
                                f"Scope allocation rule '{rule.name}' matched scope '{rule.match_scope_id}'"
                            ),
                            split_percentage=Decimal("100.0"),
                        )
                    ]

            # --------------------------------------------------------------
            # Tier 4: Service Rule
            # --------------------------------------------------------------
            elif rule.rule_type == AllocationRuleType.SERVICE_RULE:
                matched = False
                service_desc = ""
                if service:
                    if rule.match_service_id and (
                        service.id == rule.match_service_id
                        or service.service_code.lower() == rule.match_service_id.lower()
                    ):
                        matched = True
                        service_desc = f"service {service.service_code}"
                    elif (
                        rule.match_service_category
                        and service.category.value == rule.match_service_category
                    ):
                        matched = True
                        service_desc = f"service category {service.category.value}"

                if matched:
                    return [
                        AllocatedCostRow(
                            cost_fact_id=cost_fact.id,
                            resource_id=cost_fact.resource_id,
                            scope_id=cost_fact.scope_id,
                            total_cost=total_cost_dec,
                            allocated_amount=total_cost_dec,
                            currency=cost_fact.billing_currency,
                            cost_center_code=rule.target_cost_center_code or "UNALLOCATED",
                            business_unit_code=rule.target_business_unit_code,
                            project_code=rule.target_project_code,
                            winning_rule_type=AllocationRuleType.SERVICE_RULE,
                            winning_rule_id=rule.id,
                            winning_rule_name=rule.name,
                            rule_explanation=(
                                f"Service allocation rule '{rule.name}' matched {service_desc}"
                            ),
                            split_percentage=Decimal("100.0"),
                        )
                    ]

            # --------------------------------------------------------------
            # Tier 5: Split Rule
            # --------------------------------------------------------------
            elif rule.rule_type == AllocationRuleType.SPLIT_RULE:
                # Check predicate if configured (e.g. scope or service or general)
                matched = True
                if rule.match_scope_id and cost_fact.scope_id != rule.match_scope_id:
                    matched = False
                if (
                    rule.match_service_id
                    and service
                    and service.service_code != rule.match_service_id
                ):
                    matched = False

                if matched:
                    allocated_rows: list[AllocatedCostRow] = []
                    allocated_so_far = Decimal("0.00")
                    num_targets = len(rule.split_targets)

                    for idx, target in enumerate(rule.split_targets):
                        # Use exact percentage arithmetic with bankers rounding
                        if idx == num_targets - 1:
                            # Final split adjustment ensures exact penny reconciliation
                            share_amount = total_cost_dec - allocated_so_far
                        else:
                            ratio = target.percentage / Decimal("100.0")
                            share_amount = round_currency(total_cost_dec * ratio)
                            allocated_so_far += share_amount

                        row = AllocatedCostRow(
                            cost_fact_id=cost_fact.id,
                            resource_id=cost_fact.resource_id,
                            scope_id=cost_fact.scope_id,
                            total_cost=total_cost_dec,
                            allocated_amount=share_amount,
                            currency=cost_fact.billing_currency,
                            cost_center_code=target.cost_center_code,
                            business_unit_code=target.business_unit_code,
                            project_code=rule.target_project_code,
                            winning_rule_type=AllocationRuleType.SPLIT_RULE,
                            winning_rule_id=rule.id,
                            winning_rule_name=rule.name,
                            rule_explanation=(
                                f"Split rule '{rule.name}' allocated {target.percentage}% share to "
                                f"CostCenter '{target.cost_center_code}'"
                            ),
                            split_percentage=target.percentage,
                        )
                        allocated_rows.append(row)

                    return allocated_rows

        # ------------------------------------------------------------------
        # Tier 6: Unallocated Fallback (Prompt 08 Item 58)
        # ------------------------------------------------------------------
        # Explicit unallocated bucket, never silently absorbed into "Other"
        return [
            AllocatedCostRow(
                cost_fact_id=cost_fact.id,
                resource_id=cost_fact.resource_id,
                scope_id=cost_fact.scope_id,
                total_cost=total_cost_dec,
                allocated_amount=total_cost_dec,
                currency=cost_fact.billing_currency,
                cost_center_code="UNALLOCATED",
                business_unit_code=None,
                project_code=None,
                winning_rule_type=AllocationRuleType.UNALLOCATED,
                winning_rule_id=None,
                winning_rule_name="Default Unallocated Fallback",
                rule_explanation=(
                    "No allocation rule matched this cost fact. Cost attributed to UNALLOCATED fallback. "
                    "Unallocated costs are visible at all aggregation levels and never absorbed."
                ),
                split_percentage=Decimal("100.0"),
            )
        ]
