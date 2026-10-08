"""In-memory fake repository for Threshold Rules, Overrides, and Results (Prompt P06)."""

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


class InMemoryThresholdRepository(TenantAwareRepository[ThresholdEvaluationResult]):
    """Tenant-scoped repository persisting threshold rules, overrides, and evaluation outcomes."""

    is_in_memory: bool = True

    def __init__(self) -> None:
        self._results: dict[tuple[str, str], ThresholdEvaluationResult] = {}
        self._rules: dict[tuple[str, str], ThresholdRule] = {}
        self._overrides: dict[tuple[str, str], ThresholdOverride] = {}
        self._storm_events: dict[tuple[str, str], StormGroupEvent] = {}

    def ensure_tenant_default_rules(self, *, tenant_context: TenantContext) -> None:
        self._validate_tenant_context(tenant_context)
        tenant_id = tenant_context.tenant_id
        default_budget_key = (tenant_id, f"thr-default-budget-{tenant_id}")
        if default_budget_key not in self._rules:
            default_rule = create_tenant_default_budget_rule(tenant_id)
            self._rules[default_budget_key] = default_rule

    def get(
        self, entity_id: str, *, tenant_context: TenantContext
    ) -> ThresholdEvaluationResult | None:
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
        self._validate_tenant_context(tenant_context)
        if entity.tenant_id != tenant_context.tenant_id:
            raise ValueError(
                f"Evaluation result tenant '{entity.tenant_id}' mismatches context '{tenant_context.tenant_id}'."
            )
        self._results[(tenant_context.tenant_id, entity.id)] = entity
        return entity

    def delete(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        self._validate_tenant_context(tenant_context)
        key = (tenant_context.tenant_id, entity_id)
        if key in self._results:
            del self._results[key]
            return True
        return False

    def exists(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        self._validate_tenant_context(tenant_context)
        return (tenant_context.tenant_id, entity_id) in self._results

    def get_latest_for_entity(
        self, entity_id: str, *, tenant_context: TenantContext
    ) -> ThresholdEvaluationResult | None:
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
        self._validate_tenant_context(tenant_context)
        matching = [
            res
            for (t_id, _), res in self._results.items()
            if t_id == tenant_context.tenant_id and res.entity_id == entity_id
        ]
        matching.sort(key=lambda r: r.evaluated_at, reverse=True)
        return matching[:limit]

    def save_rule(self, rule: ThresholdRule, *, tenant_context: TenantContext) -> ThresholdRule:
        self._validate_tenant_context(tenant_context)
        if rule.tenant_id != tenant_context.tenant_id:
            raise ValueError(
                f"Rule tenant '{rule.tenant_id}' mismatches context '{tenant_context.tenant_id}'."
            )
        self._rules[(tenant_context.tenant_id, rule.id)] = rule
        return rule

    def get_rule(self, rule_id: str, *, tenant_context: TenantContext) -> ThresholdRule | None:
        self._validate_tenant_context(tenant_context)
        return self._rules.get((tenant_context.tenant_id, rule_id))

    def list_rules(
        self,
        *,
        tenant_context: TenantContext,
        basis: ThresholdBasis | None = None,
    ) -> builtins.list[ThresholdRule]:
        self._validate_tenant_context(tenant_context)
        self.ensure_tenant_default_rules(tenant_context=tenant_context)
        rules = [r for (t_id, _), r in self._rules.items() if t_id == tenant_context.tenant_id]
        if basis is not None:
            rules = [r for r in rules if r.basis == basis]
        return rules

    def delete_rule(self, rule_id: str, *, tenant_context: TenantContext) -> bool:
        self._validate_tenant_context(tenant_context)
        key = (tenant_context.tenant_id, rule_id)
        if key in self._rules:
            del self._rules[key]
            return True
        return False

    def save_override(
        self, override: ThresholdOverride, *, tenant_context: TenantContext
    ) -> ThresholdOverride:
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
        self._validate_tenant_context(tenant_context)
        return self._overrides.get((tenant_context.tenant_id, override_id))

    def list_overrides(
        self,
        *,
        tenant_context: TenantContext,
        target_id: str | None = None,
        active_only: bool = True,
    ) -> builtins.list[ThresholdOverride]:
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
        self._validate_tenant_context(tenant_context)
        key = (tenant_context.tenant_id, override_id)
        if key in self._overrides:
            del self._overrides[key]
            return True
        return False

    def save_storm_event(
        self, event: StormGroupEvent, *, tenant_context: TenantContext
    ) -> StormGroupEvent:
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
        self._validate_tenant_context(tenant_context)
        events = [
            e for (t_id, _), e in self._storm_events.items() if t_id == tenant_context.tenant_id
        ]
        if scope_id:
            events = [e for e in events if e.scope_id == scope_id]
        events.sort(key=lambda ev: ev.cycle_timestamp, reverse=True)
        return events[:limit]
