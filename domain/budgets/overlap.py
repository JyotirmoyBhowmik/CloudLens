"""Budget Overlap, Over-Allocation, and Double-Counting Detector (Prompt 28).

Enforces:
- Prompt 28: Overlap and over-allocation detection:
  * Warn when child budgets exceed the parent.
  * Display the unallocated remainder of a parent budget explicitly.
  * Flag — without forbidding — a logical budget that overlaps a native budget,
    because the same cost legitimately appears in both.
- Negative constraint: Do NOT silently prevent logical and native budgets from overlapping;
  flag and explain instead.
"""

from __future__ import annotations

from domain.budgets.models import (
    BudgetEntity,
    BudgetHierarchySummary,
    BudgetOverlapWarning,
)


class BudgetOverlapDetector:
    """Detects hierarchical over-allocations and logical vs native scope overlaps."""

    def analyze_hierarchy(
        self,
        parent_budget: BudgetEntity,
        child_budgets: list[BudgetEntity],
    ) -> BudgetHierarchySummary:
        """Computes hierarchical allocation, over-allocation status, and unallocated remainder."""
        total_child = sum(c.amount for c in child_budgets)
        unallocated = round(parent_budget.amount - total_child, 2)
        is_over = total_child > parent_budget.amount

        children_data = [
            {
                "id": c.id,
                "name": c.name,
                "scope_type": c.scope_type.value,
                "scope_id": c.scope_id,
                "amount": c.amount,
                "currency": c.currency,
                "approval_status": c.approval_status.value,
            }
            for c in child_budgets
        ]

        return BudgetHierarchySummary(
            parent_budget_id=parent_budget.id,
            parent_budget_name=parent_budget.name,
            parent_amount=parent_budget.amount,
            total_child_allocated=round(total_child, 2),
            unallocated_remainder=unallocated,
            is_over_allocated=is_over,
            child_count=len(child_budgets),
            children=children_data,
        )

    def detect_overlaps(
        self,
        target_budget: BudgetEntity,
        all_tenant_budgets: list[BudgetEntity],
    ) -> list[BudgetOverlapWarning]:
        """Scans candidate budgets for same-scope duplication, child over-allocation,

        and logical vs native infrastructure overlaps.

        Negative Constraint: Never suppresses or prevents overlapping budgets;
        flags and explains the dual tracking reality.
        """
        warnings: list[BudgetOverlapWarning] = []

        for other in all_tenant_budgets:
            if other.id == target_budget.id:
                continue

            # 1. Exact Same Scope & Period Collision
            if (
                other.scope_type == target_budget.scope_type
                and other.scope_id == target_budget.scope_id
                and other.is_active
            ):
                warnings.append(
                    BudgetOverlapWarning(
                        budget_id=target_budget.id,
                        budget_name=target_budget.name,
                        overlapping_budget_id=other.id,
                        overlapping_budget_name=other.name,
                        overlap_type="SAME_SCOPE_DUPLICATE",
                        scope_type=target_budget.scope_type,
                        scope_id=target_budget.scope_id,
                        overlapping_scope_type=other.scope_type,
                        overlapping_scope_id=other.scope_id,
                        explanation=(
                            f"Multiple active budgets defined for identical scope "
                            f"({target_budget.scope_type.value}:{target_budget.scope_id}). "
                            f"Both '{target_budget.name}' and '{other.name}' are tracking the same target boundary."
                        ),
                        severity="WARNING",
                    )
                )

            # 2. Logical vs Native Overlap (Honest Double-Counting Disclosure)
            is_target_logical = target_budget.is_logical
            is_other_logical = other.is_logical

            if is_target_logical != is_other_logical and other.is_active:
                logical_b = target_budget if is_target_logical else other
                native_b = other if is_target_logical else target_budget

                warnings.append(
                    BudgetOverlapWarning(
                        budget_id=target_budget.id,
                        budget_name=target_budget.name,
                        overlapping_budget_id=other.id,
                        overlapping_budget_name=other.name,
                        overlap_type="LOGICAL_NATIVE_OVERLAP",
                        scope_type=target_budget.scope_type,
                        scope_id=target_budget.scope_id,
                        overlapping_scope_type=other.scope_type,
                        overlapping_scope_id=other.scope_id,
                        explanation=(
                            f"Dual-accounting notice: Logical budget '{logical_b.name}' ({logical_b.scope_type.value}) "
                            f"and Provider Native budget '{native_b.name}' ({native_b.scope_type.value}) overlap. "
                            f"The same cloud expenditure legitimately appears in both governance frameworks. "
                            f"CloudLens maintains and tracks both budgets independently without artificial restriction."
                        ),
                        severity="INFO",
                    )
                )

        # 3. Child vs Parent Over-Allocation Check
        if target_budget.parent_budget_id:
            parent = next(
                (b for b in all_tenant_budgets if b.id == target_budget.parent_budget_id), None
            )
            if parent:
                siblings = [
                    b
                    for b in all_tenant_budgets
                    if b.parent_budget_id == parent.id and b.id != target_budget.id
                ]
                total_children = sum(b.amount for b in siblings) + target_budget.amount
                if total_children > parent.amount:
                    over_amount = round(total_children - parent.amount, 2)
                    over_pct = round((over_amount / parent.amount) * 100.0, 1)
                    warnings.append(
                        BudgetOverlapWarning(
                            budget_id=target_budget.id,
                            budget_name=target_budget.name,
                            overlapping_budget_id=parent.id,
                            overlapping_budget_name=parent.name,
                            overlap_type="CHILD_OVER_ALLOCATION",
                            scope_type=target_budget.scope_type,
                            scope_id=target_budget.scope_id,
                            overlapping_scope_type=parent.scope_type,
                            overlapping_scope_id=parent.scope_id,
                            explanation=(
                                f"Child budget allocations under '{parent.name}' total ${total_children:,.2f}, "
                                f"exceeding parent allocation ceiling of ${parent.amount:,.2f} by "
                                f"${over_amount:,.2f} ({over_pct}% over-allocated)."
                            ),
                            severity="WARNING",
                        )
                    )

        return warnings
