"""Threshold Engine Domain Service Facade (Prompt 27).

Coordinates:
- Contiguous, non-overlapping threshold rules lifecycle.
- Overrides (temporary with mandatory reason & expiry, and administrative).
- Precedence resolution (TEMPORARY -> ADMIN -> LOCAL -> ANCESTOR -> TENANT_DEFAULT).
- Evaluation with complete anti-flapping (dwell time, hysteresis, cool-down, storm grouping, data quality gate).
- Audit trail for rule creation, updates, overrides, and state transitions.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from domain.audit.service import AuditEventCreate, get_audit_service
from domain.models.enums import AuditEventType
from domain.models.exceptions import (
    ThresholdOverrideNotFoundException,
    ThresholdRuleNotFoundException,
)
from domain.tenant.context import TenantContext
from domain.thresholds.defaults import create_tenant_default_budget_rule
from domain.thresholds.evaluator import ThresholdEvaluator
from domain.thresholds.models import (
    ThresholdBasis,
    ThresholdEvaluateRequest,
    ThresholdEvaluationResult,
    ThresholdOverride,
    ThresholdOverrideCreateRequest,
    ThresholdRule,
    ThresholdRuleCreateRequest,
    ThresholdSourceType,
)
from domain.thresholds.precedence import PrecedenceResolver, ResolvedThreshold
from domain.thresholds.preview import (
    HistoricalDataPoint,
    ThresholdPreviewSimulationResult,
    simulate_threshold_rule,
)
from domain.thresholds.repository import ThresholdRepository, get_threshold_repository

logger = logging.getLogger(__name__)


class ThresholdService:
    """Unified domain service coordinating the generic 6-state, 10-basis threshold engine."""

    def __init__(
        self,
        repository: ThresholdRepository | None = None,
        evaluator: ThresholdEvaluator | None = None,
    ) -> None:
        self.repository = repository or get_threshold_repository()
        self.evaluator = evaluator or ThresholdEvaluator()

    # ==========================================================================
    # 1. Threshold Rule Management
    # ==========================================================================

    def create_rule(
        self,
        request: ThresholdRuleCreateRequest,
        *,
        actor_id: str = "system",
        tenant_context: TenantContext,
    ) -> ThresholdRule:
        """Creates a new threshold rule with strict non-overlapping contiguous band validation."""
        rule_id = request.id or f"thr-rule-{uuid.uuid4().hex[:8]}"
        rule = ThresholdRule(
            id=rule_id,
            tenant_id=tenant_context.tenant_id,
            name=request.name,
            description=request.description,
            basis=request.basis,
            bands=request.bands,
            anti_flapping=request.anti_flapping,
            scope_id=request.scope_id,
            service_id=request.service_id,
            resource_id=request.resource_id,
            environment=request.environment,
            is_tenant_default=request.is_tenant_default,
            unit=request.unit,
        )
        saved = self.repository.save_rule(rule, tenant_context=tenant_context)

        # Audit creation
        try:
            audit_svc = get_audit_service()
            audit_svc.append_event(
                tenant_context=tenant_context,
                event_in=AuditEventCreate(
                    event_type=AuditEventType.THRESHOLD_RULE_CREATED,
                    actor_id=actor_id,
                    actor_roles=["OPERATOR"],
                    action="THRESHOLD_RULE_CREATED",
                    resource_type="THRESHOLD_RULE",
                    resource_id=saved.id,
                    details={
                        "rule_name": saved.name,
                        "basis": saved.basis.value,
                        "band_count": len(saved.bands),
                        "scope_id": saved.scope_id or "",
                        "is_tenant_default": saved.is_tenant_default,
                    },
                    correlation_id=tenant_context.correlation_id,
                ),
            )
        except Exception as audit_err:
            logger.warning("Failed to audit threshold rule creation: %s", audit_err)

        return saved

    def update_rule(
        self,
        rule_id: str,
        request: ThresholdRuleCreateRequest,
        *,
        actor_id: str = "system",
        tenant_context: TenantContext,
    ) -> ThresholdRule:
        """Updates an existing threshold rule."""
        existing = self.repository.get_rule(rule_id, tenant_context=tenant_context)
        if not existing:
            raise ThresholdRuleNotFoundException(rule_id)

        updated_rule = ThresholdRule(
            id=rule_id,
            tenant_id=tenant_context.tenant_id,
            name=request.name,
            description=request.description,
            basis=request.basis,
            bands=request.bands,
            anti_flapping=request.anti_flapping,
            scope_id=request.scope_id,
            service_id=request.service_id,
            resource_id=request.resource_id,
            environment=request.environment,
            is_tenant_default=request.is_tenant_default,
            unit=request.unit,
        )
        saved = self.repository.save_rule(updated_rule, tenant_context=tenant_context)

        # Audit update
        try:
            audit_svc = get_audit_service()
            audit_svc.append_event(
                tenant_context=tenant_context,
                event_in=AuditEventCreate(
                    event_type=AuditEventType.THRESHOLD_RULE_UPDATED,
                    actor_id=actor_id,
                    actor_roles=["OPERATOR"],
                    action="THRESHOLD_RULE_UPDATED",
                    resource_type="THRESHOLD_RULE",
                    resource_id=saved.id,
                    details={"rule_name": saved.name, "basis": saved.basis.value},
                    correlation_id=tenant_context.correlation_id,
                ),
            )
        except Exception as audit_err:
            logger.warning("Failed to audit threshold rule update: %s", audit_err)

        return saved

    def get_rule(self, rule_id: str, *, tenant_context: TenantContext) -> ThresholdRule:
        """Retrieves a threshold rule by ID or raises ThresholdRuleNotFoundException."""
        rule = self.repository.get_rule(rule_id, tenant_context=tenant_context)
        if not rule:
            raise ThresholdRuleNotFoundException(rule_id)
        return rule

    def list_rules(
        self,
        *,
        tenant_context: TenantContext,
        basis: ThresholdBasis | None = None,
    ) -> list[ThresholdRule]:
        """Lists threshold rules within tenant scope."""
        return self.repository.list_rules(tenant_context=tenant_context, basis=basis)

    def delete_rule(self, rule_id: str, *, tenant_context: TenantContext) -> bool:
        """Deletes a threshold rule within tenant scope."""
        return self.repository.delete_rule(rule_id, tenant_context=tenant_context)

    # ==========================================================================
    # 2. Threshold Override Management (Prompt 27 Items 166-167)
    # ==========================================================================

    def create_override(
        self,
        request: ThresholdOverrideCreateRequest,
        *,
        actor_id: str,
        approved_by: str | None = None,
        tenant_context: TenantContext,
    ) -> ThresholdOverride:
        """Creates an operational or administrative threshold override with mandatory rationale."""
        override = ThresholdOverride(
            tenant_id=tenant_context.tenant_id,
            target_id=request.target_id,
            source_type=request.source_type,
            custom_bands=request.custom_bands,
            reason=request.reason,
            created_by=actor_id,
            approved_by=approved_by,
            valid_from=request.valid_from or datetime.now(UTC),
            expires_at=request.expires_at,
        )
        saved = self.repository.save_override(override, tenant_context=tenant_context)

        # Audit override creation
        try:
            audit_svc = get_audit_service()
            audit_svc.append_event(
                tenant_context=tenant_context,
                event_in=AuditEventCreate(
                    event_type=AuditEventType.THRESHOLD_OVERRIDE_CREATED,
                    actor_id=actor_id,
                    actor_roles=["OPERATOR"],
                    action="THRESHOLD_OVERRIDE_CREATED",
                    resource_type="THRESHOLD_OVERRIDE",
                    resource_id=saved.id,
                    details={
                        "target_id": saved.target_id,
                        "source_type": saved.source_type.value,
                        "reason": saved.reason,
                        "expires_at": saved.expires_at.isoformat() if saved.expires_at else None,
                    },
                    correlation_id=tenant_context.correlation_id,
                ),
            )
        except Exception as audit_err:
            logger.warning("Failed to audit threshold override creation: %s", audit_err)

        return saved

    def get_override(self, override_id: str, *, tenant_context: TenantContext) -> ThresholdOverride:
        """Retrieves a threshold override by ID."""
        override = self.repository.get_override(override_id, tenant_context=tenant_context)
        if not override:
            raise ThresholdOverrideNotFoundException(override_id)
        return override

    def list_overrides(
        self,
        *,
        tenant_context: TenantContext,
        target_id: str | None = None,
        active_only: bool = True,
    ) -> list[ThresholdOverride]:
        """Lists overrides within tenant scope."""
        return self.repository.list_overrides(
            tenant_context=tenant_context, target_id=target_id, active_only=active_only
        )

    def delete_override(self, override_id: str, *, tenant_context: TenantContext) -> bool:
        """Deletes a threshold override within tenant scope."""
        return self.repository.delete_override(override_id, tenant_context=tenant_context)

    # ==========================================================================
    # 3. Threshold Evaluation & Precedence Resolution
    # ==========================================================================

    def evaluate_entity(
        self,
        request: ThresholdEvaluateRequest,
        *,
        evaluated_at: datetime | None = None,
        tenant_context: TenantContext,
    ) -> ThresholdEvaluationResult:
        """Evaluates an entity's metric value following strict 5-tier resolution and anti-flapping."""
        all_rules = self.repository.list_rules(tenant_context=tenant_context)
        all_overrides = self.repository.list_overrides(
            tenant_context=tenant_context, active_only=True
        )

        # Determine tenant default rule fallback for this basis
        tenant_default = next(
            (r for r in all_rules if r.basis == request.basis and r.is_tenant_default),
            create_tenant_default_budget_rule(tenant_context.tenant_id),
        )

        # Precedence resolution (TEMPORARY -> ADMIN -> LOCAL -> ANCESTOR -> TENANT_DEFAULT)
        if request.rule_id:
            # If explicit rule was specified in the request
            rule = next(
                (r for r in all_rules if r.id == request.rule_id),
                tenant_default,
            )
            src_type = (
                ThresholdSourceType.INHERITED_ANCESTOR
                if rule.scope_id
                else ThresholdSourceType.LOCAL
            )
            resolved = ResolvedThreshold(
                rule=rule,
                bands=rule.bands,
                source_type=src_type,
                source_id=rule.id,
                source_display=f"Explicit rule '{rule.name}'",
            )

        else:
            resolved = PrecedenceResolver.resolve(
                entity_id=request.entity_id,
                basis=request.basis,
                scope_id=request.scope_id,
                service_id=request.service_id,
                environment=request.environment,
                rules=all_rules,
                overrides=all_overrides,
                tenant_default_rule=tenant_default,
                as_of=evaluated_at,
            )

        # Execute evaluation through anti-flapping engine
        eval_result = self.evaluator.evaluate(
            entity_id=request.entity_id,
            value=request.value,
            resolved=resolved,
            scope_id=request.scope_id,
            evaluated_at=evaluated_at,
            tenant_context=tenant_context,
        )

        # Persist outcome
        self.repository.save(eval_result, tenant_context=tenant_context)

        # Audit state transition if state changed
        if eval_result.transition_occurred:
            try:
                audit_svc = get_audit_service()
                audit_svc.append_event(
                    tenant_context=tenant_context,
                    event_in=AuditEventCreate(
                        event_type=AuditEventType.THRESHOLD_STATE_TRANSITIONED,
                        actor_id="system",
                        actor_roles=["SYSTEM"],
                        action="THRESHOLD_STATE_TRANSITIONED",
                        resource_type="RESOURCE",
                        resource_id=request.entity_id,
                        details={
                            "previous_state": eval_result.previous_committed_state.value
                            if eval_result.previous_committed_state
                            else None,
                            "committed_state": eval_result.committed_state.value,
                            "evaluated_state": eval_result.evaluated_state.value,
                            "measured_value": str(eval_result.measured_value)
                            if eval_result.measured_value is not None
                            else None,
                            "resolved_source": eval_result.resolved_source_display,
                            "is_flapping_suppressed": eval_result.is_flapping_suppressed,
                            "suppression_reason": eval_result.suppression_reason,
                        },
                        correlation_id=tenant_context.correlation_id,
                    ),
                )
            except Exception as audit_err:
                logger.warning("Failed to audit threshold state transition: %s", audit_err)

        return eval_result

    def get_latest_state(
        self, entity_id: str, *, tenant_context: TenantContext
    ) -> ThresholdEvaluationResult | None:
        """Retrieves the most recent evaluation outcome for an entity."""
        return self.repository.get_latest_for_entity(entity_id, tenant_context=tenant_context)

    def list_history(
        self, entity_id: str, *, tenant_context: TenantContext, limit: int = 50
    ) -> list[ThresholdEvaluationResult]:
        """Lists historical evaluation results for an entity."""
        return self.repository.list_for_entity(
            entity_id, tenant_context=tenant_context, limit=limit
        )

    # ==========================================================================
    # 4. Phase 2 Preview Simulation (Flag-gated)
    # ==========================================================================

    def preview_rule(
        self,
        rule: ThresholdRule,
        data_points: list[HistoricalDataPoint],
        *,
        scope_id: str | None = None,
        tenant_context: TenantContext,
        override_enabled_flag: bool | None = None,
    ) -> ThresholdPreviewSimulationResult:
        """Simulates rule over historical series. Gated by ENABLE_THRESHOLD_PREVIEW."""
        return simulate_threshold_rule(
            rule=rule,
            data_points=data_points,
            tenant_context=tenant_context,
            scope_id=scope_id,
            override_enabled_flag=override_enabled_flag,
        )


_threshold_service_instance: ThresholdService | None = None


def get_threshold_service() -> ThresholdService:
    """Returns singleton ThresholdService instance."""
    global _threshold_service_instance
    if _threshold_service_instance is None:
        _threshold_service_instance = ThresholdService()
    return _threshold_service_instance


def reset_threshold_service() -> None:
    """Resets singleton ThresholdService for test isolation."""
    global _threshold_service_instance
    _threshold_service_instance = None
