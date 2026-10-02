"""Policy Evaluation Engine (Prompt 30, FR-741, FR-742, FR-743).

Enforces:
- FR-741: Policies must support simulate and enforce modes, with simulation producing findings without alerting.
- FR-742: A policy condition that cannot be evaluated for an entity must produce 'Not Evaluable', never False / violation.
- FR-743: Policy exemptions must be time-boxed, justified, approved, and reported while active.
- Negative constraint: Do NOT let a missing field produce a violation (must be NOT_EVALUABLE).
"""

from __future__ import annotations

import datetime as dt
import re
from decimal import Decimal
from typing import Any

from domain.models.enums import (
    ConditionOperator,
    EvaluationOutcome,
    LogicalOperator,
    PolicyMode,
)
from domain.policy.models import (
    DeclarativeCondition,
    PolicyDefinition,
    PolicyEvaluationResult,
    PolicyExemption,
    PolicyFinding,
)


class _FieldResolutionResult:
    """Internal helper tracking resolved value and presence status."""

    def __init__(self, exists: bool, value: Any = None, missing_path: str = ""):
        self.exists = exists
        self.value = value
        self.missing_path = missing_path


class PolicyEvaluator:
    """Deterministic evaluator of declarative policies over canonical entity records."""

    @classmethod
    def resolve_field_path(
        cls, entity_data: dict[str, Any], field_path: str
    ) -> _FieldResolutionResult:
        """Resolves dot-notated field path against entity data, distinguishing None from missing.

        Checks both nested dicts and explicit flat keys. Also inspects 'unsupported_fields'
        and 'missing_fields' declarations on entity.
        """
        # 1. Check if provider/entity explicitly declares field as unsupported
        unsupported = entity_data.get("unsupported_fields") or []
        if field_path in unsupported:
            return _FieldResolutionResult(exists=False, missing_path=field_path)

        # 2. Check direct flat key first (e.g. "tags.CostCenter" as a top-level key)
        if field_path in entity_data:
            val = entity_data[field_path]
            # Sentinel check: if provider returns sentinel indicating not supplied
            if val == "__FIELD_NOT_SUPPLIED__":
                return _FieldResolutionResult(exists=False, missing_path=field_path)
            return _FieldResolutionResult(exists=True, value=val)

        # 3. Traverse dot-separated components
        parts = field_path.split(".")
        current: Any = entity_data
        for part in parts:
            if isinstance(current, dict):
                if part in current:
                    current = current[part]
                    if current == "__FIELD_NOT_SUPPLIED__":
                        return _FieldResolutionResult(exists=False, missing_path=field_path)
                else:
                    return _FieldResolutionResult(exists=False, missing_path=field_path)
            else:
                return _FieldResolutionResult(exists=False, missing_path=field_path)

        return _FieldResolutionResult(exists=True, value=current)

    @classmethod
    def _coerce_numeric(cls, val: Any) -> float | Decimal | None:
        """Attempts safe numeric conversion for comparison."""
        if val is None:
            return None
        if isinstance(val, (int, float, Decimal)):
            return val
        try:
            return float(str(val).strip())
        except (ValueError, TypeError):
            return None

    @classmethod
    def evaluate_leaf_condition(
        cls, condition: DeclarativeCondition, entity_data: dict[str, Any]
    ) -> tuple[EvaluationOutcome, str, Any, Any, list[str]]:
        """Evaluates a leaf declarative condition against an entity."""
        field_path = condition.field or ""
        op = condition.operator
        target = condition.value

        resolution = cls.resolve_field_path(entity_data, field_path)
        if not resolution.exists:
            # Rule FR-742: Where a policy references a field that a provider does not supply,
            # the result is Not Evaluable, never a violation.
            reason = f"Field '{field_path}' is not supplied by provider or absent on entity."
            return (EvaluationOutcome.NOT_EVALUABLE, reason, None, target, [field_path])

        actual = resolution.value

        # Operator implementations
        try:
            if op == ConditionOperator.IS_NULL:
                passed = actual is None
            elif op == ConditionOperator.IS_NOT_NULL:
                passed = actual is not None and str(actual).strip() != ""
            elif op == ConditionOperator.EQUALS:
                passed = actual == target
            elif op == ConditionOperator.NOT_EQUALS:
                passed = actual != target
            elif op in (
                ConditionOperator.GREATER_THAN,
                ConditionOperator.GREATER_THAN_OR_EQUAL,
                ConditionOperator.LESS_THAN,
                ConditionOperator.LESS_THAN_OR_EQUAL,
            ):
                num_actual = cls._coerce_numeric(actual)
                num_target = cls._coerce_numeric(target)
                if num_actual is None or num_target is None:
                    # Cannot compare non-numeric numerically -> Not Evaluable
                    return (
                        EvaluationOutcome.NOT_EVALUABLE,
                        f"Field '{field_path}' value '{actual}' is not numeric for operator '{op}'.",
                        actual,
                        target,
                        [field_path],
                    )
                if op == ConditionOperator.GREATER_THAN:
                    passed = num_actual > num_target
                elif op == ConditionOperator.GREATER_THAN_OR_EQUAL:
                    passed = num_actual >= num_target
                elif op == ConditionOperator.LESS_THAN:
                    passed = num_actual < num_target
                else:
                    passed = num_actual <= num_target

            elif op == ConditionOperator.CONTAINS:
                if isinstance(actual, (list, tuple, set)):
                    passed = target in actual
                elif isinstance(actual, str):
                    passed = str(target) in actual
                elif isinstance(actual, dict):
                    passed = str(target) in actual
                else:
                    passed = False

            elif op == ConditionOperator.NOT_CONTAINS:
                if isinstance(actual, (list, tuple, set)):
                    passed = target not in actual
                elif isinstance(actual, str):
                    passed = str(target) not in actual
                elif isinstance(actual, dict):
                    passed = str(target) not in actual
                else:
                    passed = True

            elif op == ConditionOperator.IN:
                if isinstance(target, (list, tuple, set)):
                    passed = actual in target
                else:
                    passed = False

            elif op == ConditionOperator.NOT_IN:
                if isinstance(target, (list, tuple, set)):
                    passed = actual not in target
                else:
                    passed = True

            elif op == ConditionOperator.MATCHES_REGEX:
                pattern = str(target)
                passed = bool(re.search(pattern, str(actual or "")))

            elif op == ConditionOperator.ALL_PRESENT:
                # Target is list of keys (e.g. ["CostCenter", "Environment", "Owner"])
                required_keys = target if isinstance(target, list) else [str(target)]
                if isinstance(actual, dict):
                    passed = all(
                        k in actual and actual[k] is not None and str(actual[k]).strip() != ""
                        for k in required_keys
                    )
                elif isinstance(actual, (list, tuple)):
                    passed = all(k in actual for k in required_keys)
                else:
                    passed = False

            elif op == ConditionOperator.ANY_PRESENT:
                required_keys = target if isinstance(target, list) else [str(target)]
                if isinstance(actual, dict):
                    passed = any(
                        k in actual and actual[k] is not None and str(actual[k]).strip() != ""
                        for k in required_keys
                    )
                elif isinstance(actual, (list, tuple)):
                    passed = any(k in actual for k in required_keys)
                else:
                    passed = False

            elif op == ConditionOperator.IN_APPROVED_LIST:
                approved_items = target if isinstance(target, list) else [str(target)]
                passed = actual in approved_items

            elif op == ConditionOperator.NOT_IN_APPROVED_LIST:
                approved_items = target if isinstance(target, list) else [str(target)]
                passed = actual not in approved_items

            else:
                passed = False

        except Exception as ex:
            return (
                EvaluationOutcome.NOT_EVALUABLE,
                f"Error evaluating condition on field '{field_path}': {ex}",
                actual,
                target,
                [field_path],
            )

        if passed:
            return (
                EvaluationOutcome.COMPLIANT,
                f"Condition met for field '{field_path}'.",
                actual,
                target,
                [],
            )
        else:
            return (
                EvaluationOutcome.VIOLATION,
                f"Violation: Field '{field_path}' with value '{actual}' violated condition '{op}' with expected '{target}'.",
                actual,
                target,
                [],
            )

    @classmethod
    def evaluate_condition(
        cls, condition: DeclarativeCondition, entity_data: dict[str, Any]
    ) -> tuple[EvaluationOutcome, str, Any, Any, list[str]]:
        """Recursively evaluates a declarative condition (composite or leaf)."""
        if condition.logical_op is None:
            return cls.evaluate_leaf_condition(condition, entity_data)

        # Composite evaluation
        missing_fields: list[str] = []
        outcomes: list[EvaluationOutcome] = []
        reasons: list[str] = []
        observed_vals: list[Any] = []
        expected_vals: list[Any] = []

        for child in condition.children:
            c_outcome, c_reason, c_obs, c_exp, c_missing = cls.evaluate_condition(
                child, entity_data
            )
            outcomes.append(c_outcome)
            reasons.append(c_reason)
            observed_vals.append(c_obs)
            expected_vals.append(c_exp)
            missing_fields.extend(c_missing)

        if condition.logical_op == LogicalOperator.AND:
            # If any is NOT_EVALUABLE, the composite is NOT_EVALUABLE
            if EvaluationOutcome.NOT_EVALUABLE in outcomes:
                return (
                    EvaluationOutcome.NOT_EVALUABLE,
                    "One or more required fields not supplied by provider in AND clause: "
                    + "; ".join(reasons),
                    observed_vals,
                    expected_vals,
                    missing_fields,
                )
            if any(o == EvaluationOutcome.VIOLATION for o in outcomes):
                return (
                    EvaluationOutcome.VIOLATION,
                    "Violation in AND clause: " + "; ".join(reasons),
                    observed_vals,
                    expected_vals,
                    [],
                )
            return (
                EvaluationOutcome.COMPLIANT,
                "All conditions satisfied in AND clause.",
                observed_vals,
                expected_vals,
                [],
            )

        elif condition.logical_op == LogicalOperator.OR:
            # If any is COMPLIANT, composite is COMPLIANT
            if any(o == EvaluationOutcome.COMPLIANT for o in outcomes):
                return (
                    EvaluationOutcome.COMPLIANT,
                    "Condition satisfied in OR clause.",
                    observed_vals,
                    expected_vals,
                    [],
                )
            # If all are NOT_EVALUABLE, composite is NOT_EVALUABLE
            if all(o == EvaluationOutcome.NOT_EVALUABLE for o in outcomes):
                return (
                    EvaluationOutcome.NOT_EVALUABLE,
                    "All options in OR clause not evaluable due to missing fields.",
                    observed_vals,
                    expected_vals,
                    missing_fields,
                )
            return (
                EvaluationOutcome.VIOLATION,
                "No conditions satisfied in OR clause: " + "; ".join(reasons),
                observed_vals,
                expected_vals,
                [],
            )

        elif condition.logical_op == LogicalOperator.NOT:
            first_outcome = outcomes[0] if outcomes else EvaluationOutcome.COMPLIANT
            if first_outcome == EvaluationOutcome.NOT_EVALUABLE:
                return (
                    EvaluationOutcome.NOT_EVALUABLE,
                    "Negated condition not evaluable due to missing fields.",
                    observed_vals,
                    expected_vals,
                    missing_fields,
                )
            if first_outcome == EvaluationOutcome.VIOLATION:
                return (
                    EvaluationOutcome.COMPLIANT,
                    "Condition inverted by NOT clause.",
                    observed_vals,
                    expected_vals,
                    [],
                )
            return (
                EvaluationOutcome.VIOLATION,
                "Condition failed NOT clause: negated assertion was satisfied.",
                observed_vals,
                expected_vals,
                [],
            )

        return (
            EvaluationOutcome.NOT_EVALUABLE,
            "Unknown logical operator.",
            None,
            None,
            [],
        )

    @classmethod
    def evaluate_policy_against_entity(
        cls,
        policy: PolicyDefinition,
        entity_data: dict[str, Any],
        active_exemptions: list[PolicyExemption] | None = None,
        as_of: dt.datetime | None = None,
    ) -> tuple[PolicyEvaluationResult, PolicyFinding | None]:
        """Evaluates an entity against a policy definition, checking targets, exemptions, and fields."""
        entity_id = str(
            entity_data.get("id")
            or entity_data.get("resource_id")
            or entity_data.get("entity_id")
            or "unknown-entity"
        )
        entity_name = str(entity_data.get("name") or entity_data.get("display_name") or entity_id)
        entity_type = str(entity_data.get("resource_type") or entity_data.get("type") or "resource")
        provider = str(entity_data.get("provider") or entity_data.get("cloud_provider") or "")
        scope_id = str(entity_data.get("scope_id") or entity_data.get("account_id") or "")
        eval_time = as_of or dt.datetime.now(dt.UTC)

        # 1. Target Selector Match
        if not policy.target_selector.matches(entity_data):
            result = PolicyEvaluationResult(
                policy_id=policy.id,
                policy_version=policy.version,
                entity_id=entity_id,
                outcome=EvaluationOutcome.COMPLIANT,
                reason="Entity does not match policy target selector scope/filters.",
                evaluated_at=eval_time,
            )
            return result, None

        # 2. Check Active Exemptions
        matching_exemption: PolicyExemption | None = None
        if active_exemptions:
            for exm in active_exemptions:
                if exm.policy_id == policy.id and exm.is_active(eval_time):
                    if exm.matches_entity(entity_id, scope_id):
                        matching_exemption = exm
                        break

        # 3. Evaluate Declarative Condition
        outcome, reason, obs_val, exp_val, missing_fields = cls.evaluate_condition(
            policy.condition, entity_data
        )

        # 4. If violation occurred but an active exemption is in effect -> outcome is EXEMPTED
        if outcome == EvaluationOutcome.VIOLATION and matching_exemption is not None:
            outcome = EvaluationOutcome.EXEMPTED
            reason = f"Violation excused under active exemption '{matching_exemption.id}': {matching_exemption.justification}"

        result = PolicyEvaluationResult(
            policy_id=policy.id,
            policy_version=policy.version,
            entity_id=entity_id,
            outcome=outcome,
            reason=reason,
            observed_value=obs_val,
            expected_value=exp_val,
            missing_fields=missing_fields,
            evaluated_at=eval_time,
        )

        # 5. Generate Finding if VIOLATION
        finding: PolicyFinding | None = None
        if outcome == EvaluationOutcome.VIOLATION:
            # Mode enforcement:
            # In SIMULATE mode, alerts_suppressed = True, is_alertable = False
            # In ENFORCE mode, alerts_suppressed = False, is_alertable = True
            is_sim = policy.mode == PolicyMode.SIMULATE
            finding = PolicyFinding(
                policy_id=policy.id,
                policy_version=policy.version,
                entity_id=entity_id,
                entity_name=entity_name,
                entity_type=entity_type,
                provider=provider,
                scope_id=scope_id,
                severity=policy.severity,
                category=policy.category,
                mode=policy.mode,
                observed_value=obs_val,
                expected_value=exp_val,
                condition_summary=reason,
                is_alertable=not is_sim,
                alerts_suppressed=is_sim,
                first_detected_at=eval_time,
                last_evaluated_at=eval_time,
            )

        return result, finding
