"""Policy Engine Service (Prompt 30, BBP Section 34, FR-740 to FR-746).

Orchestrates:
- Declarative policy authoring and versioning without code deployment (FR-740).
- Simulation and enforce modes with alert suppression (FR-741).
- Not Evaluable handling without false-positive violation generation (FR-742).
- Time-boxed, justified policy exemptions (FR-743).
- Finding deduplication and lifecycle state clearing (FR-744).
- Governance exception counting and temporal trending (FR-745).
- Sixteen seeded default policies with connector health enabled by default (FR-746).
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from domain.models.enums import (
    EvaluationOutcome,
    FindingLifecycleStatus,
    PolicyCategory,
    PolicyMode,
    PolicySeverity,
)
from domain.models.exceptions import (
    DuplicatePolicyException,
    InvalidExemptionException,
    PolicyNotFoundException,
)
from domain.policy.catalogue import get_default_policy_definitions
from domain.policy.evaluator import PolicyEvaluator
from domain.policy.models import (
    GovernanceTrendPoint,
    GovernanceTrendReport,
    PolicyCreateDTO,
    PolicyDefinition,
    PolicyEvaluationBatchResponse,
    PolicyEvaluationResult,
    PolicyExemption,
    PolicyExemptionCreateDTO,
    PolicyFinding,
    PolicySimulationResponse,
    PolicyUpdateDTO,
)
from domain.policy.repository import PolicyRepository, get_policy_repository
from domain.tenant.context import TenantContext


class PolicyService:
    """Enterprise domain service for governance policies and exception management."""

    def __init__(self, repository: PolicyRepository | None = None) -> None:
        self.repo = repository or get_policy_repository()

    # ==========================================================================
    # 1. Seeding & Discovery
    # ==========================================================================

    def ensure_default_policies_seeded(
        self, *, tenant_context: TenantContext
    ) -> list[PolicyDefinition]:
        """Ensures the 16+ default policies (POL-01 to POL-18) are seeded for tenant."""
        existing = self.repo.list_policies(tenant_context=tenant_context)
        if existing:
            return existing

        defaults = get_default_policy_definitions()
        seeded: list[PolicyDefinition] = []
        for policy in defaults:
            p = policy.model_copy()
            saved = self.repo.save_policy(p, tenant_context=tenant_context)
            seeded.append(saved)
        return seeded

    def list_policies(
        self,
        *,
        tenant_context: TenantContext,
        enabled_only: bool = False,
        category: PolicyCategory | None = None,
    ) -> list[PolicyDefinition]:
        """Lists policies for tenant."""
        return self.repo.list_policies(
            tenant_context=tenant_context,
            enabled_only=enabled_only,
            category=category,
        )

    def get_policy(self, policy_id: str, *, tenant_context: TenantContext) -> PolicyDefinition:
        """Retrieves a policy by ID, raising PolicyNotFoundException if missing."""
        policy = self.repo.get_policy(policy_id, tenant_context=tenant_context)
        if not policy:
            raise PolicyNotFoundException(policy_id)
        return policy

    def get_policy_version(
        self, policy_id: str, version: int, *, tenant_context: TenantContext
    ) -> PolicyDefinition:
        """Retrieves a specific historical version of a policy."""
        self.ensure_default_policies_seeded(tenant_context=tenant_context)
        policy = self.repo.get_policy_version(policy_id, version, tenant_context=tenant_context)
        if not policy:
            raise PolicyNotFoundException(f"{policy_id} (version {version})")
        return policy

    # ==========================================================================
    # 2. Dynamic Authoring & Versioning (FR-740)
    # ==========================================================================

    def create_policy(
        self, dto: PolicyCreateDTO, *, tenant_context: TenantContext
    ) -> PolicyDefinition:
        """Creates a new declarative policy dynamically with version 1 (FR-740)."""
        self.ensure_default_policies_seeded(tenant_context=tenant_context)
        existing = self.repo.get_policy(dto.id, tenant_context=tenant_context)
        if existing:
            raise DuplicatePolicyException(dto.id)

        dto.condition.validate_semantics()
        now = dt.datetime.now(dt.UTC)

        policy = PolicyDefinition(
            id=dto.id,
            version=1,
            name=dto.name,
            description=dto.description,
            category=dto.category,
            target_selector=dto.target_selector,
            condition=dto.condition,
            effect=dto.effect,
            severity=dto.severity,
            evaluation_schedule=dto.evaluation_schedule,
            mode=dto.mode,
            enabled=dto.enabled,
            created_at=now,
            updated_at=now,
            updated_by=tenant_context.actor_id,
            is_default=False,
        )
        return self.repo.save_policy(policy, tenant_context=tenant_context)

    def update_policy(
        self, policy_id: str, dto: PolicyUpdateDTO, *, tenant_context: TenantContext
    ) -> PolicyDefinition:
        """Updates an existing policy, creating a new immutable version (FR-740)."""
        current = self.get_policy(policy_id, tenant_context=tenant_context)
        now = dt.datetime.now(dt.UTC)

        # Validate condition if provided
        new_condition = dto.condition or current.condition
        new_condition.validate_semantics()

        new_version = current.version + 1
        updated = PolicyDefinition(
            id=current.id,
            version=new_version,
            name=dto.name if dto.name is not None else current.name,
            description=dto.description if dto.description is not None else current.description,
            category=dto.category if dto.category is not None else current.category,
            target_selector=dto.target_selector
            if dto.target_selector is not None
            else current.target_selector,
            condition=new_condition,
            effect=dto.effect if dto.effect is not None else current.effect,
            severity=dto.severity if dto.severity is not None else current.severity,
            evaluation_schedule=dto.evaluation_schedule
            if dto.evaluation_schedule is not None
            else current.evaluation_schedule,
            mode=dto.mode if dto.mode is not None else current.mode,
            enabled=dto.enabled if dto.enabled is not None else current.enabled,
            created_at=current.created_at,
            updated_at=now,
            updated_by=tenant_context.actor_id,
            is_default=current.is_default,
        )
        return self.repo.save_policy(updated, tenant_context=tenant_context)

    def set_policy_enabled(
        self, policy_id: str, enabled: bool, *, tenant_context: TenantContext
    ) -> PolicyDefinition:
        """Toggles policy enabled state without changing version."""
        current = self.get_policy(policy_id, tenant_context=tenant_context)
        now = dt.datetime.now(dt.UTC)
        current.enabled = enabled
        current.updated_at = now
        current.updated_by = tenant_context.actor_id
        return self.repo.save_policy(current, tenant_context=tenant_context)

    # ==========================================================================
    # 3. Time-Boxed Justified Exemptions (FR-743)
    # ==========================================================================

    def create_exemption(
        self, dto: PolicyExemptionCreateDTO, *, tenant_context: TenantContext
    ) -> PolicyExemption:
        """Creates a justified time-boxed exemption (FR-743)."""
        # Validate target policy exists
        self.get_policy(dto.policy_id, tenant_context=tenant_context)

        # Enforce non-empty justification
        if not dto.justification or not dto.justification.strip():
            raise InvalidExemptionException(
                "Exemption justification is mandatory and cannot be empty."
            )

        # Enforce future expiry
        now = dt.datetime.now(dt.UTC)
        if dto.expires_at <= now:
            raise InvalidExemptionException(
                f"Exemption expiry timestamp '{dto.expires_at.isoformat()}' must be strictly in the future."
            )

        exemption = PolicyExemption(
            policy_id=dto.policy_id,
            entity_id=dto.entity_id,
            scope_id=dto.scope_id,
            justification=dto.justification.strip(),
            requested_by=tenant_context.actor_id,
            approved_by=dto.approved_by,
            requires_approval=dto.requires_approval,
            is_approved=not dto.requires_approval or bool(dto.approved_by),
            created_at=now,
            expires_at=dto.expires_at,
        )
        saved = self.repo.save_exemption(exemption, tenant_context=tenant_context)

        # If an open finding exists for exempted entity/policy, transition to EXEMPTED
        if dto.entity_id:
            open_finding = self.repo.find_open_finding(
                dto.entity_id, dto.policy_id, tenant_context=tenant_context
            )
            if open_finding:
                open_finding.lifecycle_status = FindingLifecycleStatus.EXEMPTED
                open_finding.exemption_id = saved.id
                open_finding.alerts_suppressed = True
                open_finding.last_evaluated_at = now
                self.repo.save_finding(open_finding, tenant_context=tenant_context)

        return saved

    def list_exemptions(
        self,
        *,
        tenant_context: TenantContext,
        policy_id: str | None = None,
        entity_id: str | None = None,
        active_only: bool = False,
    ) -> list[PolicyExemption]:
        """Lists tenant exemptions."""
        return self.repo.list_exemptions(
            tenant_context=tenant_context,
            policy_id=policy_id,
            entity_id=entity_id,
            active_only=active_only,
        )

    def delete_exemption(self, exemption_id: str, *, tenant_context: TenantContext) -> bool:
        """Deletes an exemption by ID."""
        return self.repo.delete_exemption(exemption_id, tenant_context=tenant_context)

    # ==========================================================================
    # 4. Simulation Mode (FR-741)
    # ==========================================================================

    def simulate_policy(
        self,
        *,
        tenant_context: TenantContext,
        policy_id: str | None = None,
        inline_policy: PolicyCreateDTO | None = None,
        entities: list[dict[str, Any]],
    ) -> PolicySimulationResponse:
        """Executes policy simulation over entities, generating findings with ZERO alerts raised (FR-741)."""
        now = dt.datetime.now(dt.UTC)
        if inline_policy:
            inline_policy.condition.validate_semantics()
            policy = PolicyDefinition(
                id=inline_policy.id,
                version=1,
                name=inline_policy.name,
                description=inline_policy.description,
                category=inline_policy.category,
                target_selector=inline_policy.target_selector,
                condition=inline_policy.condition,
                effect=inline_policy.effect,
                severity=inline_policy.severity,
                evaluation_schedule=inline_policy.evaluation_schedule,
                mode=PolicyMode.SIMULATE,
                enabled=True,
                created_at=now,
                updated_at=now,
            )
        elif policy_id:
            saved = self.get_policy(policy_id, tenant_context=tenant_context)
            policy = saved.model_copy()
            policy.mode = PolicyMode.SIMULATE  # Forced simulate mode
        else:
            raise InvalidExemptionException(
                "Simulation requires either 'policy_id' or 'inline_policy'."
            )

        active_exemptions = self.repo.list_exemptions(
            tenant_context=tenant_context, active_only=True
        )

        results: list[PolicyEvaluationResult] = []
        findings: list[PolicyFinding] = []
        violations = 0
        compliant = 0
        not_evaluable = 0
        exempted = 0

        for entity in entities:
            res, finding = PolicyEvaluator.evaluate_policy_against_entity(
                policy=policy,
                entity_data=entity,
                active_exemptions=active_exemptions,
                as_of=now,
            )
            results.append(res)
            if res.outcome == EvaluationOutcome.VIOLATION:
                violations += 1
                if finding:
                    # Guarantee simulation constraints: findings recorded, zero alerts raised
                    finding.is_alertable = False
                    finding.alerts_suppressed = True
                    findings.append(finding)
            elif res.outcome == EvaluationOutcome.COMPLIANT:
                compliant += 1
            elif res.outcome == EvaluationOutcome.NOT_EVALUABLE:
                not_evaluable += 1
            elif res.outcome == EvaluationOutcome.EXEMPTED:
                exempted += 1

        return PolicySimulationResponse(
            policy_id=policy.id,
            policy_version=policy.version,
            mode=PolicyMode.SIMULATE,
            total_evaluated=len(entities),
            violations_count=violations,
            compliant_count=compliant,
            not_evaluable_count=not_evaluable,
            exempted_count=exempted,
            alerts_raised=0,  # Strict: simulation produces ZERO alerts
            findings=findings,
            results=results,
        )

    # ==========================================================================
    # 5. Live Evaluation & Finding Deduplication / Clearing (FR-742, FR-744)
    # ==========================================================================

    def evaluate_batch(
        self,
        entities: list[dict[str, Any]],
        *,
        tenant_context: TenantContext,
        policy_ids: list[str] | None = None,
    ) -> PolicyEvaluationBatchResponse:
        """Evaluates batch of entities against active policies with deduplication and clearing."""
        self.ensure_default_policies_seeded(tenant_context=tenant_context)
        now = dt.datetime.now(dt.UTC)

        if policy_ids:
            policies = [self.get_policy(pid, tenant_context=tenant_context) for pid in policy_ids]
        else:
            policies = self.repo.list_policies(tenant_context=tenant_context, enabled_only=True)

        active_exemptions = self.repo.list_exemptions(
            tenant_context=tenant_context, active_only=True
        )

        total_evaluations = 0
        violations_count = 0
        new_findings = 0
        updated_findings = 0
        cleared_findings = 0
        not_evaluable = 0
        exempted = 0
        alerts_generated = 0
        active_batch_findings: list[PolicyFinding] = []

        for entity in entities:
            entity_id = str(
                entity.get("id")
                or entity.get("resource_id")
                or entity.get("entity_id")
                or "unknown-entity"
            )

            for policy in policies:
                total_evaluations += 1
                res, candidate_finding = PolicyEvaluator.evaluate_policy_against_entity(
                    policy=policy,
                    entity_data=entity,
                    active_exemptions=active_exemptions,
                    as_of=now,
                )

                if res.outcome == EvaluationOutcome.NOT_EVALUABLE:
                    not_evaluable += 1
                    # Rule FR-742: Not Evaluable produces zero findings and is never a violation
                    continue

                elif res.outcome == EvaluationOutcome.EXEMPTED:
                    exempted += 1
                    open_fnd = self.repo.find_open_finding(
                        entity_id, policy.id, tenant_context=tenant_context
                    )
                    if open_fnd:
                        open_fnd.lifecycle_status = FindingLifecycleStatus.EXEMPTED
                        open_fnd.last_evaluated_at = now
                        self.repo.save_finding(open_fnd, tenant_context=tenant_context)
                    continue

                elif res.outcome == EvaluationOutcome.COMPLIANT:
                    # Clearing check (FR-744): If condition cleared, close existing open finding
                    open_fnd = self.repo.find_open_finding(
                        entity_id, policy.id, tenant_context=tenant_context
                    )
                    if open_fnd:
                        open_fnd.lifecycle_status = FindingLifecycleStatus.CLEARED
                        open_fnd.cleared_at = now
                        open_fnd.last_evaluated_at = now
                        self.repo.save_finding(open_fnd, tenant_context=tenant_context)
                        cleared_findings += 1

                elif res.outcome == EvaluationOutcome.VIOLATION and candidate_finding:
                    violations_count += 1
                    # Deduplication check (FR-744): Check for open finding on same entity, policy, and version
                    open_fnd = self.repo.find_open_finding(
                        entity_id,
                        policy.id,
                        policy.version,
                        tenant_context=tenant_context,
                    )
                    if open_fnd:
                        # Deduplicate: update existing open finding rather than creating second finding
                        open_fnd.consecutive_occurrences += 1
                        open_fnd.last_evaluated_at = now
                        open_fnd.observed_value = candidate_finding.observed_value
                        open_fnd.condition_summary = candidate_finding.condition_summary
                        saved = self.repo.save_finding(open_fnd, tenant_context=tenant_context)
                        updated_findings += 1
                        active_batch_findings.append(saved)
                    else:
                        # New open finding
                        saved = self.repo.save_finding(
                            candidate_finding, tenant_context=tenant_context
                        )
                        new_findings += 1
                        active_batch_findings.append(saved)
                        if saved.is_alertable:
                            alerts_generated += 1

        return PolicyEvaluationBatchResponse(
            total_entities=len(entities),
            total_evaluations=total_evaluations,
            violations_detected=violations_count,
            new_findings_created=new_findings,
            existing_findings_updated=updated_findings,
            findings_cleared=cleared_findings,
            not_evaluable_count=not_evaluable,
            exempted_count=exempted,
            alerts_generated=alerts_generated,
            findings=active_batch_findings,
        )

    def list_findings(
        self,
        *,
        tenant_context: TenantContext,
        status: FindingLifecycleStatus | None = None,
        severity: PolicySeverity | None = None,
        category: PolicyCategory | None = None,
        mode: PolicyMode | None = None,
        policy_id: str | None = None,
        entity_id: str | None = None,
    ) -> list[PolicyFinding]:
        """Lists stored findings."""
        return self.repo.list_findings(
            tenant_context=tenant_context,
            status=status,
            severity=severity,
            category=category,
            mode=mode,
            policy_id=policy_id,
            entity_id=entity_id,
        )

    def count_findings(
        self,
        *,
        tenant_context: TenantContext,
        status: FindingLifecycleStatus | None = None,
    ) -> int:
        """Counts stored findings using direct SQL SELECT COUNT(*) on policy_findings (Prompt P07)."""
        return self.repo.count_findings(tenant_context=tenant_context, status=status)

    # ==========================================================================
    # 6. Governance Exception Trending (FR-745)
    # ==========================================================================

    def get_governance_trend(
        self,
        start_date: dt.date,
        end_date: dt.date,
        *,
        tenant_context: TenantContext,
    ) -> GovernanceTrendReport:
        """Computes daily governance exception counts and resolution trends (FR-745)."""
        findings = self.repo.list_findings(tenant_context=tenant_context)
        day_count = (end_date - start_date).days + 1
        trend_points: list[GovernanceTrendPoint] = []

        total_detected = 0
        total_cleared = 0
        resolution_durations_hours: list[float] = []

        for i in range(max(1, day_count)):
            current_day = start_date + dt.timedelta(days=i)
            day_new = 0
            day_cleared = 0
            day_open = 0
            sev_breakdown: dict[str, int] = {s.value: 0 for s in PolicySeverity}
            cat_breakdown: dict[str, int] = {}

            for f in findings:
                f_det_date = f.first_detected_at.date()
                f_clr_date = f.cleared_at.date() if f.cleared_at else None

                # Detected on current day
                if f_det_date == current_day:
                    day_new += 1

                # Cleared on current day
                if f_clr_date == current_day:
                    day_cleared += 1

                # Open on current day
                is_open_on_day = f_det_date <= current_day and (
                    f_clr_date is None or f_clr_date > current_day
                )
                if is_open_on_day:
                    day_open += 1
                    sev_breakdown[f.severity.value] = sev_breakdown.get(f.severity.value, 0) + 1
                    cat_breakdown[f.category.value] = cat_breakdown.get(f.category.value, 0) + 1

            total_detected += day_new
            total_cleared += day_cleared
            trend_points.append(
                GovernanceTrendPoint(
                    date=current_day,
                    total_open=day_open,
                    new_findings=day_new,
                    cleared_findings=day_cleared,
                    net_change=day_new - day_cleared,
                    by_severity=sev_breakdown,
                    by_category=cat_breakdown,
                )
            )

        # Compute MTTR for findings cleared during window
        for f in findings:
            if (
                f.cleared_at
                and start_date <= f.cleared_at.date() <= end_date
                and f.first_detected_at
            ):
                dur_hrs = (f.cleared_at - f.first_detected_at).total_seconds() / 3600.0
                resolution_durations_hours.append(dur_hrs)

        mttr = (
            sum(resolution_durations_hours) / len(resolution_durations_hours)
            if resolution_durations_hours
            else 0.0
        )
        res_rate = (total_cleared / total_detected * 100.0) if total_detected > 0 else 100.0

        current_open = len(
            [f for f in findings if f.lifecycle_status == FindingLifecycleStatus.OPEN]
        )

        return GovernanceTrendReport(
            tenant_id=tenant_context.tenant_id,
            start_date=start_date,
            end_date=end_date,
            points=trend_points,
            current_open_count=current_open,
            total_detected_in_period=total_detected,
            total_cleared_in_period=total_cleared,
            mttr_hours=round(mttr, 2),
            resolution_rate_pct=round(res_rate, 2),
        )


# ==============================================================================
# Service Singleton Factory
# ==============================================================================

_policy_service_instance: PolicyService | None = None


def get_policy_service() -> PolicyService:
    """Returns singleton PolicyService instance."""
    global _policy_service_instance
    if _policy_service_instance is None:
        _policy_service_instance = PolicyService()
    return _policy_service_instance


def reset_policy_service() -> None:
    """Resets singleton PolicyService for test isolation."""
    global _policy_service_instance
    _policy_service_instance = None
