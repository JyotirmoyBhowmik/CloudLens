"""Period Close Cycle & Non-Destructive Restatement Engine (Prompt 52).

Enforces:
- Period close cycle: Draft statement generated at period close + provider finalisation lag,
  circulated to recipients, open for review for a configured window, then finalised.
- Strict immutability of finalised statements:
  Rule: 'Do not alter a finalised statement in place.'
- Restatements after finalisation produce a visible adjustment version rather than silently altering.
- Complete audit trail of circulation, finalisation, and restatement adjustments.
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from domain.audit.service import AuditService, get_audit_service
from domain.models.enums import AuditEventType
from domain.models.exceptions import (
    FinalisedStatementModificationForbiddenException,
    StatementAlreadyFinalisedException,
)
from domain.rules.monetary import round_currency, to_decimal
from domain.statements.models import (
    AdjustmentLine,
    ShowbackStatement,
    StatementAdjustment,
    StatementLifecycleStatus,
)
from domain.tenant.context import TenantContext, require_tenant_context


class PeriodCloseCycleEngine:
    """Manages statement circulation, review windows, finalisation, and restatements."""

    def __init__(self, audit_service: AuditService | None = None) -> None:
        self.audit_service = audit_service or get_audit_service()

    def circulate_for_review(
        self,
        statement: ShowbackStatement,
        *,
        review_window_days: int = 5,
        tenant_context: TenantContext,
    ) -> ShowbackStatement:
        """Circulates draft statement to recipients with active review window."""
        tc = require_tenant_context(tenant_context)
        now = dt.datetime.now(dt.UTC)
        deadline = now + dt.timedelta(days=review_window_days)

        statement.status = StatementLifecycleStatus.IN_REVIEW
        statement.circulated_at = now.isoformat()
        statement.review_deadline = deadline.isoformat()

        # Record audit event
        self.audit_service.record_event(
            tenant_context=tc,
            event_type=AuditEventType.STATEMENT_CIRCULATED,
            actor=tc.user_id,
            action="STATEMENT_CIRCULATED_FOR_REVIEW",
            resource_type="SHOWBACK_STATEMENT",
            resource_id=statement.statement_id,
            payload={
                "period": statement.period,
                "scope_code": statement.scope_code,
                "review_deadline": statement.review_deadline,
                "total_cost": str(statement.total_allocated_cost),
            },
        )
        return statement

    def finalise_statement(
        self,
        statement: ShowbackStatement,
        *,
        tenant_context: TenantContext,
    ) -> ShowbackStatement:
        """Finalises the showback statement, locking it against any in-place mutation."""
        tc = require_tenant_context(tenant_context)

        if statement.status == StatementLifecycleStatus.FINALISED:
            raise StatementAlreadyFinalisedException(
                f"Statement '{statement.statement_id}' is already finalised."
            )

        now = dt.datetime.now(dt.UTC)
        statement.status = StatementLifecycleStatus.FINALISED
        statement.finalised_at = now.isoformat()

        self.audit_service.record_event(
            tenant_context=tc,
            event_type=AuditEventType.STATEMENT_FINALISED,
            actor=tc.user_id,
            action="STATEMENT_FINALISED",
            resource_type="SHOWBACK_STATEMENT",
            resource_id=statement.statement_id,
            payload={
                "period": statement.period,
                "scope_code": statement.scope_code,
                "finalised_at": statement.finalised_at,
                "total_cost": str(statement.total_allocated_cost),
            },
        )
        return statement

    def assert_modifiable(self, statement: ShowbackStatement) -> None:
        """Enforces hard rule: 'Do not alter a finalised statement in place.'"""
        if statement.status == StatementLifecycleStatus.FINALISED:
            raise FinalisedStatementModificationForbiddenException(statement.statement_id)

    def process_restatement_adjustment(
        self,
        original_statement: ShowbackStatement,
        *,
        adjustment_deltas: list[dict[str, Any]],
        restatement_reason: str,
        tenant_context: TenantContext,
    ) -> tuple[ShowbackStatement, StatementAdjustment]:
        """Emits a distinct adjustment statement without altering the finalised statement in-place.

        Prompt 52 Rule:
        A restatement after finalisation produces a visible adjustment rather than a silently altered statement.
        """
        tc = require_tenant_context(tenant_context)
        now = dt.datetime.now(dt.UTC)

        adj_id = f"adj-{original_statement.period}-{uuid.uuid4().hex[:8]}"
        new_version = original_statement.version + 1
        base_id_parts = original_statement.statement_id.rsplit("-v", 1)
        base_id = base_id_parts[0]
        new_statement_id = f"{base_id}-v{new_version}"

        # 1. Calculate net adjustments
        net_delta = Decimal("0.00")
        lines: list[AdjustmentLine] = []

        for delta_dict in adjustment_deltas:
            line_id = delta_dict.get("line_id", f"adj-line-{uuid.uuid4().hex[:6]}")
            desc = delta_dict.get("description", "Restatement correction")
            orig = to_decimal(delta_dict.get("original_amount", 0.0))
            delta = to_decimal(delta_dict.get("adjustment_delta", 0.0))
            adjusted = round_currency(orig + delta)
            reason = delta_dict.get("reason", restatement_reason)

            net_delta += delta
            lines.append(
                AdjustmentLine(
                    line_id=line_id,
                    description=desc,
                    original_amount=orig,
                    adjustment_delta=delta,
                    adjusted_amount=adjusted,
                    reason=reason,
                )
            )

        new_total_cost = round_currency(original_statement.total_allocated_cost + net_delta)

        # 2. Build Authoritative Adjustment Record
        adjustment_record = StatementAdjustment(
            adjustment_id=adj_id,
            tenant_id=tc.tenant_id,
            original_statement_id=original_statement.statement_id,
            adjusted_statement_id=new_statement_id,
            version=new_version,
            original_total=original_statement.total_allocated_cost,
            adjustment_total=net_delta,
            adjusted_total=new_total_cost,
            restatement_reason=restatement_reason,
            adjustment_timestamp=now.isoformat(),
            adjusted_by=tc.user_id,
            lines=lines,
        )

        # 3. Create newly emitted statement copy
        adjusted_statement = original_statement.model_copy(deep=True)
        adjusted_statement.statement_id = new_statement_id
        adjusted_statement.version = new_version
        adjusted_statement.supersedes_statement_id = original_statement.statement_id
        adjusted_statement.status = StatementLifecycleStatus.ADJUSTED
        adjusted_statement.total_allocated_cost = new_total_cost
        adjusted_statement.budget_variance_amount = round_currency(
            new_total_cost - adjusted_statement.budget_amount
        )
        adjusted_statement.generated_at = now.isoformat()
        adjusted_statement.finalised_at = now.isoformat()

        # 4. Mark original statement as SUPERSEDED (non-destructive!)
        original_statement.status = StatementLifecycleStatus.SUPERSEDED

        # 5. Record audit event
        self.audit_service.record_event(
            tenant_context=tc,
            event_type=AuditEventType.STATEMENT_ADJUSTED_AFTER_RESTATEMENT,
            actor=tc.user_id,
            action="STATEMENT_RESTATEMENT_ADJUSTMENT_EMITTED",
            resource_type="SHOWBACK_STATEMENT",
            resource_id=new_statement_id,
            payload={
                "original_statement_id": original_statement.statement_id,
                "adjustment_id": adj_id,
                "net_adjustment": str(net_delta),
                "new_total": str(new_total_cost),
                "reason": restatement_reason,
            },
        )

        return adjusted_statement, adjustment_record
