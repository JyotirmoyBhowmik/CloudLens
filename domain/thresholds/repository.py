"""Tenant-Scoped Repository for Threshold Rules, Overrides, and Evaluation Results (Prompt 27).

Enforces:
- Prompt 13 Item 84: 100% TenantContext validation across all repository operations.
- Tenant isolation per BBP Section 41 and SEC-015.
- Prompt 27: Five-tier resolution precedence rules, anti-flapping evaluation states, and overrides.
"""

from __future__ import annotations

import builtins
import logging
from typing import Any

from domain.tenant.context import TenantContext
from domain.tenant.repository import TenantAwareRepository
from domain.thresholds.defaults import create_tenant_default_budget_rule
from domain.thresholds.models import (
    StormGroupEvent,
    ThresholdBasis,
    ThresholdEvaluationResult,
    ThresholdOverride,
    ThresholdRule,
)

logger = logging.getLogger(__name__)


class ThresholdRepository(TenantAwareRepository[ThresholdEvaluationResult]):
    """Tenant-scoped repository persisting threshold rules, overrides, and evaluation outcomes."""

    def __init__(self) -> None:
        # Key: (tenant_id, result_id) -> ThresholdEvaluationResult
        self._results: dict[tuple[str, str], ThresholdEvaluationResult] = {}
        # Key: (tenant_id, rule_id) -> ThresholdRule
        self._rules: dict[tuple[str, str], ThresholdRule] = {}
        # Key: (tenant_id, override_id) -> ThresholdOverride
        self._overrides: dict[tuple[str, str], ThresholdOverride] = {}
        # Key: (tenant_id, storm_event_id) -> StormGroupEvent
        self._storm_events: dict[tuple[str, str], StormGroupEvent] = {}

    def ensure_tenant_default_rules(self, *, tenant_context: TenantContext) -> None:
        """Seeds canonical default threshold rules for a tenant if none exist."""
        self._validate_tenant_context(tenant_context)
        tenant_id = tenant_context.tenant_id
        default_budget_key = (tenant_id, f"thr-default-budget-{tenant_id}")
        if default_budget_key not in self._rules:
            default_rule = create_tenant_default_budget_rule(tenant_id)
            self._rules[default_budget_key] = default_rule

    # ==========================================================================
    # 1. TenantAwareRepository Required Base Methods (Evaluation Results)
    # ==========================================================================

    def get(
        self, entity_id: str, *, tenant_context: TenantContext
    ) -> ThresholdEvaluationResult | None:
        """Retrieves a single threshold evaluation result by ID within tenant scope."""
        self._validate_tenant_context(tenant_context)
        return self._results.get((tenant_context.tenant_id, entity_id))

    def list(
        self,
        *,
        tenant_context: TenantContext,
        filter_params: Any = None,
        limit: int = 50,
        offset: int = 0,
    ) -> builtins.list[ThresholdEvaluationResult]:
        """Lists threshold evaluation results within the tenant scope."""
        self._validate_tenant_context(tenant_context)
        _ = filter_params
        matching = [
            res for (t_id, _), res in self._results.items() if t_id == tenant_context.tenant_id
        ]
        matching.sort(key=lambda r: r.evaluated_at, reverse=True)
        return matching[offset : offset + limit]

    def save(
        self, entity: ThresholdEvaluationResult, *, tenant_context: TenantContext
    ) -> ThresholdEvaluationResult:
        """Persists or updates an evaluation result ensuring tenant isolation."""
        self._validate_tenant_context(tenant_context)
        if entity.tenant_id != tenant_context.tenant_id:
            raise ValueError(
                f"Evaluation result tenant '{entity.tenant_id}' mismatches context '{tenant_context.tenant_id}'."
            )
        self._results[(tenant_context.tenant_id, entity.id)] = entity
        return entity

    def delete(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        """Deletes an evaluation result within tenant scope."""
        self._validate_tenant_context(tenant_context)
        key = (tenant_context.tenant_id, entity_id)
        if key in self._results:
            del self._results[key]
            return True
        return False

    def exists(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        """Checks if an evaluation result exists within tenant scope."""
        self._validate_tenant_context(tenant_context)
        return (tenant_context.tenant_id, entity_id) in self._results

    # ==========================================================================
    # 2. Evaluation Results Additional Query Methods
    # ==========================================================================

    def get_latest_for_entity(
        self, entity_id: str, *, tenant_context: TenantContext
    ) -> ThresholdEvaluationResult | None:
        """Retrieves the most recent evaluation outcome for a target entity."""
        self._validate_tenant_context(tenant_context)
        matching = [
            res
            for (t_id, _), res in self._results.items()
            if t_id == tenant_context.tenant_id and res.entity_id == entity_id
        ]
        if not matching:
            return None
        matching.sort(key=lambda r: r.evaluated_at, reverse=True)
        return matching[0]

    def list_for_entity(
        self, entity_id: str, *, tenant_context: TenantContext, limit: int = 50
    ) -> builtins.list[ThresholdEvaluationResult]:
        """Lists historical evaluation results for an entity ordered most recent first."""
        self._validate_tenant_context(tenant_context)
        matching = [
            res
            for (t_id, _), res in self._results.items()
            if t_id == tenant_context.tenant_id and res.entity_id == entity_id
        ]
        matching.sort(key=lambda r: r.evaluated_at, reverse=True)
        return matching[:limit]

    # ==========================================================================
    # 3. Threshold Rules Operations
    # ==========================================================================

    def save_rule(self, rule: ThresholdRule, *, tenant_context: TenantContext) -> ThresholdRule:
        """Saves or updates a threshold rule within the tenant scope."""
        self._validate_tenant_context(tenant_context)
        if rule.tenant_id != tenant_context.tenant_id:
            raise ValueError(
                f"Rule tenant '{rule.tenant_id}' mismatches context '{tenant_context.tenant_id}'."
            )
        self._rules[(tenant_context.tenant_id, rule.id)] = rule
        return rule

    def get_rule(self, rule_id: str, *, tenant_context: TenantContext) -> ThresholdRule | None:
        """Retrieves a threshold rule by ID."""
        self._validate_tenant_context(tenant_context)
        return self._rules.get((tenant_context.tenant_id, rule_id))

    def list_rules(
        self,
        *,
        tenant_context: TenantContext,
        basis: ThresholdBasis | None = None,
    ) -> builtins.list[ThresholdRule]:
        """Lists all threshold rules for a tenant, optionally filtered by basis."""
        self._validate_tenant_context(tenant_context)
        self.ensure_tenant_default_rules(tenant_context=tenant_context)
        rules = [r for (t_id, _), r in self._rules.items() if t_id == tenant_context.tenant_id]

        if basis is not None:
            rules = [r for r in rules if r.basis == basis]
        return rules

    def delete_rule(self, rule_id: str, *, tenant_context: TenantContext) -> bool:
        """Deletes a threshold rule within tenant scope."""
        self._validate_tenant_context(tenant_context)
        key = (tenant_context.tenant_id, rule_id)
        if key in self._rules:
            del self._rules[key]
            return True
        return False

    # ==========================================================================
    # 4. Threshold Overrides Operations
    # ==========================================================================

    def save_override(
        self, override: ThresholdOverride, *, tenant_context: TenantContext
    ) -> ThresholdOverride:
        """Saves or updates a threshold override within tenant scope."""
        self._validate_tenant_context(tenant_context)
        if override.tenant_id != tenant_context.tenant_id:
            raise ValueError(
                f"Override tenant '{override.tenant_id}' mismatches context '{tenant_context.tenant_id}'."
            )
        self._overrides[(tenant_context.tenant_id, override.id)] = override
        return override

    def get_override(
        self, override_id: str, *, tenant_context: TenantContext
    ) -> ThresholdOverride | None:
        """Retrieves a threshold override by ID."""
        self._validate_tenant_context(tenant_context)
        return self._overrides.get((tenant_context.tenant_id, override_id))

    def list_overrides(
        self,
        *,
        tenant_context: TenantContext,
        target_id: str | None = None,
        active_only: bool = True,
    ) -> builtins.list[ThresholdOverride]:
        """Lists threshold overrides for a tenant."""
        self._validate_tenant_context(tenant_context)
        overrides = [
            o for (t_id, _), o in self._overrides.items() if t_id == tenant_context.tenant_id
        ]
        if target_id is not None:
            overrides = [o for o in overrides if o.target_id == target_id]
        if active_only:
            overrides = [o for o in overrides if o.is_active and not o.is_expired()]
        return overrides

    def delete_override(self, override_id: str, *, tenant_context: TenantContext) -> bool:
        """Deletes a threshold override within tenant scope."""
        self._validate_tenant_context(tenant_context)
        key = (tenant_context.tenant_id, override_id)
        if key in self._overrides:
            del self._overrides[key]
            return True
        return False

    # ==========================================================================
    # 5. Storm Group Events Operations
    # ==========================================================================

    def save_storm_event(
        self, event: StormGroupEvent, *, tenant_context: TenantContext
    ) -> StormGroupEvent:
        """Saves a grouped storm alert event."""
        self._validate_tenant_context(tenant_context)
        self._storm_events[(tenant_context.tenant_id, event.id)] = event
        return event

    def list_storm_events(
        self,
        *,
        tenant_context: TenantContext,
        scope_id: str | None = None,
        limit: int = 50,
    ) -> builtins.list[StormGroupEvent]:
        """Lists storm group events within tenant scope."""
        self._validate_tenant_context(tenant_context)
        events = [
            e for (t_id, _), e in self._storm_events.items() if t_id == tenant_context.tenant_id
        ]
        if scope_id:
            events = [e for e in events if e.scope_id == scope_id]
        events.sort(key=lambda ev: ev.cycle_timestamp, reverse=True)
        return events[:limit]


_threshold_repository_instance: ThresholdRepository | None = None


def get_threshold_repository() -> ThresholdRepository:
    """Returns singleton ThresholdRepository instance."""
    global _threshold_repository_instance
    if _threshold_repository_instance is None:
        _threshold_repository_instance = ThresholdRepository()
    return _threshold_repository_instance


def reset_threshold_repository() -> None:
    """Resets the singleton ThresholdRepository for test isolation."""
    global _threshold_repository_instance
    _threshold_repository_instance = None
