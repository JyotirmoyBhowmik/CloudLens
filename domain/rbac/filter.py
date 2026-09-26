"""Access Control Filter and Disclosure Rule Engine (Prompt 11 Item 73, 74).

Implements:
1. Rate detail redaction (Item 73):
   Operations users can see cost totals (billed_cost, effective_cost) without seeing granular rates.
2. The Disclosure Rule on aggregates (Item 74):
   When access control removes data from an aggregate, the response and UI must report it explicitly.
   Silent filtering is a defect.
"""

from collections.abc import Callable
from copy import deepcopy
from typing import Any

from pydantic import BaseModel

from domain.rbac.evaluator import ScopeGrantEvaluator
from domain.rbac.models import (
    DisclosureMetadata,
    FilteredAggregateResult,
    ResourceTarget,
    ScopeGrant,
)

RATE_FIELDS: set[str] = {
    "contracted_unit_price",
    "list_unit_price",
    "unit_rate",
    "unit_price",
    "rate",
    "rate_card_margin",
    "pricing_quantity",
    "discount_percentage",
}


class AccessControlFilter:
    """Filters datasets and aggregates with rate-masking and mandatory disclosure metadata."""

    def __init__(self, evaluator: ScopeGrantEvaluator | None = None) -> None:
        self._evaluator = evaluator or ScopeGrantEvaluator()

    def redact_rates(self, item: Any) -> Any:
        """Redacts sensitive unit rate pricing fields while leaving cost totals intact (Item 73)."""
        if isinstance(item, dict):
            redacted = deepcopy(item)
            for k in RATE_FIELDS:
                if k in redacted:
                    redacted[k] = None
            return redacted

        if isinstance(item, BaseModel):
            updates = {k: None for k in RATE_FIELDS if hasattr(item, k)}
            return item.model_copy(update=updates)

        if hasattr(item, "__dict__"):
            redacted_obj = deepcopy(item)
            for k in RATE_FIELDS:
                if hasattr(redacted_obj, k):
                    setattr(redacted_obj, k, None)
            return redacted_obj

        return item

    def extract_target_from_item(self, item: Any) -> ResourceTarget:
        """Extracts a ResourceTarget from arbitrary item types."""
        if isinstance(item, ResourceTarget):
            return item

        if isinstance(item, dict):
            return ResourceTarget(
                resource_id=item.get("resource_id") or item.get("id"),
                provider=item.get("provider"),
                account_id=item.get("account_id") or item.get("subscription_id"),
                hierarchy_path=item.get("hierarchy_path") or [],
                project_id=item.get("project_id"),
                application_id=item.get("application_id") or item.get("application_code"),
                cost_centre_id=item.get("cost_centre_id") or item.get("cost_center_id"),
                business_unit_id=item.get("business_unit_id"),
                is_financial=bool(item.get("is_financial", True)),
                is_rate_detail=bool(item.get("is_rate_detail", False)),
                is_administrative=bool(item.get("is_administrative", False)),
            )

        # Attribute lookup for BaseModel or class instances
        return ResourceTarget(
            resource_id=getattr(item, "resource_id", None) or getattr(item, "id", None),
            provider=getattr(item, "provider", None),
            account_id=getattr(item, "account_id", None) or getattr(item, "subscription_id", None),
            hierarchy_path=getattr(item, "hierarchy_path", []),
            project_id=getattr(item, "project_id", None),
            application_id=getattr(item, "application_id", None)
            or getattr(item, "application_code", None),
            cost_centre_id=getattr(item, "cost_centre_id", None)
            or getattr(item, "cost_center_id", None),
            business_unit_id=getattr(item, "business_unit_id", None),
            is_financial=bool(getattr(item, "is_financial", True)),
            is_rate_detail=bool(getattr(item, "is_rate_detail", False)),
            is_administrative=bool(getattr(item, "is_administrative", False)),
        )

    def filter_dataset(
        self,
        user_id: str,
        tenant_id: str,
        role_codes: list[str],
        permission_code: str,
        items: list[Any],
        grants: list[ScopeGrant],
        target_extractor: Callable[[Any], ResourceTarget] | None = None,
    ) -> FilteredAggregateResult:
        """Filters a collection of items according to scope grants and permissions.

        Enforces:
        - Strict Deny-Over-Allow (Item 72).
        - Separation of financial detail vs cost totals (Item 73).
        - Disclosure Rule (Item 74): reports is_filtered, hidden_count, filtered_dimensions, notice.
        """
        allowed_items: list[Any] = []
        hidden_count = 0
        filtered_dimensions: set[str] = set()

        for item in items:
            target = (
                target_extractor(item) if target_extractor else self.extract_target_from_item(item)
            )
            decision = self._evaluator.evaluate(
                user_id=user_id,
                tenant_id=tenant_id,
                role_codes=role_codes,
                permission_code=permission_code,
                target=target,
                grants=grants,
            )

            if decision.allowed:
                if not decision.can_view_rates:
                    allowed_items.append(self.redact_rates(item))
                else:
                    allowed_items.append(item)
            else:
                hidden_count += 1
                # Determine which dimension caused exclusion
                dim_found = False
                for g in grants:
                    if g.is_active:
                        _, fail_dim = self._evaluator.matches_dimension(g, target)
                        if fail_dim:
                            filtered_dimensions.add(fail_dim)
                            dim_found = True
                if not dim_found:
                    if target.business_unit_id:
                        filtered_dimensions.add("cost_centre_business_unit")
                    elif target.provider:
                        filtered_dimensions.add("provider")
                    elif target.account_id:
                        filtered_dimensions.add("account_billing_boundary")
                    else:
                        filtered_dimensions.add("scope")

        is_filtered = hidden_count > 0
        sorted_dims = sorted(filtered_dimensions)

        notice: str | None = None
        if is_filtered:
            notice = (
                f"Access control filtered {hidden_count} of {len(items)} items "
                f"due to scope boundaries on: {', '.join(sorted_dims)}."
            )

        disclosure = DisclosureMetadata(
            is_filtered=is_filtered,
            filtered_dimensions=sorted_dims,
            hidden_count=hidden_count,
            total_unfiltered_count=len(items),
            disclosure_notice=notice,
        )

        return FilteredAggregateResult(data=allowed_items, disclosure=disclosure)
