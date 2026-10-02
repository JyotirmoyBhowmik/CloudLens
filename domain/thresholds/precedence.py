"""Precedence Resolution and Source Traceability Engine (Prompt 27 Items 165-167).

Enforces:
- Prompt 27 Precedence Chain:
  1. Temporary override (with mandatory reason and auto-expiry)
  2. Administrative override (with recorded reason & approval)
  3. Local rule (directly attached to entity)
  4. Nearest ancestor (scope, service, environment)
  5. Tenant default (tenant fallback)
- Prompt 27 / AC-064 / FR-262:
  'Threshold detail shows whether the applied threshold is local, inherited or overridden, and from where.'
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import UTC, datetime

from domain.thresholds.models import (
    ThresholdBandDefinition,
    ThresholdBasis,
    ThresholdOverride,
    ThresholdRule,
    ThresholdSourceType,
)

logger = logging.getLogger(__name__)


class ResolvedThreshold:
    """Resolved threshold rule and active bands with full origin provenance."""

    def __init__(
        self,
        *,
        rule: ThresholdRule,
        bands: list[ThresholdBandDefinition],
        source_type: ThresholdSourceType,
        source_id: str,
        source_display: str,
        active_override: ThresholdOverride | None = None,
    ) -> None:
        self.rule = rule
        self.bands = bands
        self.source_type = source_type
        self.source_id = source_id
        self.source_display = source_display
        self.active_override = active_override


class PrecedenceResolver:
    """Resolves applicable threshold rules following strict 5-tier governance precedence."""

    @staticmethod
    def resolve(
        *,
        entity_id: str,
        basis: ThresholdBasis,
        scope_id: str | None = None,
        service_id: str | None = None,
        environment: str | None = None,
        rules: Sequence[ThresholdRule],
        overrides: Sequence[ThresholdOverride],
        tenant_default_rule: ThresholdRule,
        as_of: datetime | None = None,
    ) -> ResolvedThreshold:
        """Walks the precedence hierarchy and returns the winning threshold with origin disclosure."""
        check_time = as_of or datetime.now(UTC)

        # 1. First Precedence: Temporary Override (TEMPORARY_OVERRIDE)
        for ovr in overrides:
            if (
                ovr.is_active
                and ovr.source_type == ThresholdSourceType.TEMPORARY_OVERRIDE
                and ovr.target_id in (entity_id, scope_id)
                and not ovr.is_expired(as_of=check_time)
            ):
                bands = ovr.custom_bands or tenant_default_rule.bands
                return ResolvedThreshold(
                    rule=tenant_default_rule,
                    bands=bands,
                    source_type=ThresholdSourceType.TEMPORARY_OVERRIDE,
                    source_id=ovr.id,
                    source_display=f"Temporary override '{ovr.id}' on {ovr.target_id} (Reason: {ovr.reason})",
                    active_override=ovr,
                )

        # 2. Second Precedence: Administrative Override (ADMIN_OVERRIDE)
        for ovr in overrides:
            if (
                ovr.is_active
                and ovr.source_type == ThresholdSourceType.ADMIN_OVERRIDE
                and ovr.target_id in (entity_id, scope_id)
                and not ovr.is_expired(as_of=check_time)
            ):
                bands = ovr.custom_bands or tenant_default_rule.bands
                return ResolvedThreshold(
                    rule=tenant_default_rule,
                    bands=bands,
                    source_type=ThresholdSourceType.ADMIN_OVERRIDE,
                    source_id=ovr.id,
                    source_display=f"Administrative override '{ovr.id}' on {ovr.target_id} (Approved by: {ovr.approved_by or 'admin'})",
                    active_override=ovr,
                )

        # 3. Third Precedence: Local Rule (directly attached to resource/entity)
        for rule in rules:
            if rule.basis == basis and rule.resource_id == entity_id:
                return ResolvedThreshold(
                    rule=rule,
                    bands=rule.bands,
                    source_type=ThresholdSourceType.LOCAL,
                    source_id=rule.id,
                    source_display=f"Local rule '{rule.name}' attached to entity '{entity_id}'",
                )

        # 4. Fourth Precedence: Nearest Ancestor (Scope -> Service -> Environment)
        # 4a. Ancestor Scope
        if scope_id:
            for rule in rules:
                if rule.basis == basis and rule.scope_id == scope_id:
                    return ResolvedThreshold(
                        rule=rule,
                        bands=rule.bands,
                        source_type=ThresholdSourceType.INHERITED_ANCESTOR,
                        source_id=rule.id,
                        source_display=f"Inherited from ancestor scope '{scope_id}' via rule '{rule.name}'",
                    )

        # 4b. Ancestor Service
        if service_id:
            for rule in rules:
                if rule.basis == basis and rule.service_id == service_id:
                    return ResolvedThreshold(
                        rule=rule,
                        bands=rule.bands,
                        source_type=ThresholdSourceType.INHERITED_ANCESTOR,
                        source_id=rule.id,
                        source_display=f"Inherited from ancestor service '{service_id}' via rule '{rule.name}'",
                    )

        # 4c. Ancestor Environment Tier
        if environment:
            env_norm = environment.strip().lower()
            for rule in rules:
                if (
                    rule.basis == basis
                    and rule.environment
                    and rule.environment.strip().lower() == env_norm
                ):
                    return ResolvedThreshold(
                        rule=rule,
                        bands=rule.bands,
                        source_type=ThresholdSourceType.INHERITED_ANCESTOR,
                        source_id=rule.id,
                        source_display=f"Inherited from environment tier '{environment}' via rule '{rule.name}'",
                    )

        # 5. Fifth Precedence: Tenant Default Fallback
        # Look for explicit tenant default rule for this basis, otherwise use fallback
        for rule in rules:
            if rule.basis == basis and rule.is_tenant_default:
                return ResolvedThreshold(
                    rule=rule,
                    bands=rule.bands,
                    source_type=ThresholdSourceType.TENANT_DEFAULT,
                    source_id=rule.id,
                    source_display=f"Tenant default rule '{rule.name}'",
                )

        return ResolvedThreshold(
            rule=tenant_default_rule,
            bands=tenant_default_rule.bands,
            source_type=ThresholdSourceType.TENANT_DEFAULT,
            source_id=tenant_default_rule.id,
            source_display=f"Tenant default rule '{tenant_default_rule.name}'",
        )
