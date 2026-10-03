"""Showback & Cost Allocation Statement Domain Service Facade (Prompt 52).

Enforces:
- Prompt 52 / BBP Sections 17.5, 22, 36; Master brief Section 51.
- Complete orchestration of showback statements, period close cycle, and distribution.
- Non-destructive restatement adjustments (Do not alter a finalised statement in place).
- Mandatory visible basis for shared-service cost apportionments.
- Formal line disputes routed through generic workflow engine with documented reallocations.
- Formal recipient acceptance with executive outstanding-acceptance reporting.
- Allocation transparency views with permissioned granular charge line drill-through.
- Multi-currency presentation with exchange rate disclosures.
- Phase 2 chargeback toggle gating.
"""

from __future__ import annotations

import datetime as dt
import logging
import threading
from decimal import Decimal
from typing import Any

from domain.cost.currency_service import CurrencyConversionService
from domain.models.enums import DecisionOutcome
from domain.models.exceptions import StatementNotFoundException
from domain.rules.monetary import to_decimal
from domain.statements.acceptance import StatementAcceptanceEngine
from domain.statements.cycle import PeriodCloseCycleEngine
from domain.statements.disputes import StatementDisputeManager
from domain.statements.distribution import StatementDistributionEngine
from domain.statements.generator import StatementGenerator
from domain.statements.models import (
    AllocationTransparencyView,
    ExportFormat,
    OutstandingAcceptanceReport,
    ReallocationRecord,
    RecipientScopeType,
    SharedServiceApportionmentItem,
    ShowbackStatement,
    StatementAdjustment,
    StatementDispute,
    StatementLifecycleStatus,
    StatementTemplate,
)
from domain.statements.repository import (
    StatementRepository,
    get_statement_repository,
    reset_statement_repository,
)
from domain.statements.templates import StatementTemplateEngine
from domain.statements.transparency import AllocationTransparencyEngine
from domain.tenant.context import TenantContext, require_tenant_context

logger = logging.getLogger(__name__)


class StatementService:
    """Unified domain service facade for showback statements and cost allocation packs."""

    def __init__(
        self,
        repository: StatementRepository | None = None,
        generator: StatementGenerator | None = None,
        cycle_engine: PeriodCloseCycleEngine | None = None,
        dispute_manager: StatementDisputeManager | None = None,
        acceptance_engine: StatementAcceptanceEngine | None = None,
        transparency_engine: AllocationTransparencyEngine | None = None,
        distribution_engine: StatementDistributionEngine | None = None,
        template_engine: StatementTemplateEngine | None = None,
        currency_service: CurrencyConversionService | None = None,
    ) -> None:
        self.repository = repository or get_statement_repository()
        self.template_engine = template_engine or StatementTemplateEngine()
        self.generator = generator or StatementGenerator(template_engine=self.template_engine)
        self.cycle_engine = cycle_engine or PeriodCloseCycleEngine()
        self.dispute_manager = dispute_manager or StatementDisputeManager()
        self.acceptance_engine = acceptance_engine or StatementAcceptanceEngine()
        self.transparency_engine = transparency_engine or AllocationTransparencyEngine()
        self.distribution_engine = distribution_engine or StatementDistributionEngine()
        self.currency_service = currency_service or CurrencyConversionService()

    # ==========================================================================
    # 1. Statement Generation & Retrieval
    # ==========================================================================

    def generate_statement(
        self,
        *,
        period: str,
        scope_type: RecipientScopeType = RecipientScopeType.BUSINESS_UNIT,
        scope_code: str = "BU-RETAIL",
        scope_name: str = "Retail & E-Commerce Business Unit",
        recipient_owner_id: str = "usr-retail-lead",
        recipient_owner_email: str = "retail-lead@company.com",
        tenant_context: TenantContext,
        template_id: str | None = None,
        custom_facts: list[dict[str, Any]] | None = None,
        custom_budget: Decimal | float | None = None,
        prior_period_cost: Decimal | float | None = None,
        shared_apportionments: list[SharedServiceApportionmentItem] | None = None,
        unallocated_cost: Decimal | float | None = None,
        target_currency: str = "USD",
        enable_chargeback_phase2: bool = False,
    ) -> ShowbackStatement:
        """Generates, saves, and returns a new draft ShowbackStatement."""
        tc = require_tenant_context(tenant_context)

        # Exchange rate lookup if multi-currency requested
        ex_rate = Decimal("1.0")
        rate_type = "CORPORATE_CLOSING"
        if target_currency.upper() != "USD":
            try:
                rate_rec = self.currency_service.get_effective_rate(
                    "USD", target_currency.upper(), dt.date.today()
                )
                if rate_rec:
                    ex_rate = rate_rec.rate
                    rate_type = "EFFECTIVE_CLOSING"
            except Exception:
                ex_rate = Decimal("0.92") if target_currency.upper() == "EUR" else Decimal("1.0")

        stmt = self.generator.generate_statement(
            period=period,
            scope_type=scope_type,
            scope_code=scope_code,
            scope_name=scope_name,
            recipient_owner_id=recipient_owner_id,
            recipient_owner_email=recipient_owner_email,
            tenant_context=tc,
            template_id=template_id,
            custom_facts=custom_facts,
            custom_budget=to_decimal(custom_budget) if custom_budget is not None else None,
            prior_period_cost=to_decimal(prior_period_cost)
            if prior_period_cost is not None
            else None,
            shared_apportionments=shared_apportionments,
            unallocated_cost=to_decimal(unallocated_cost) if unallocated_cost is not None else None,
            target_currency=target_currency.upper(),
            exchange_rate=ex_rate,
            rate_type=rate_type,
            enable_chargeback_phase2=enable_chargeback_phase2,
        )

        return self.repository.save_statement(stmt, tenant_context=tc)

    def get_statement(
        self, statement_id: str, *, tenant_context: TenantContext
    ) -> ShowbackStatement:
        """Retrieves a statement by ID or raises StatementNotFoundException."""
        tc = require_tenant_context(tenant_context)
        stmt = self.repository.get_statement(statement_id, tenant_context=tc)
        if not stmt:
            raise StatementNotFoundException(statement_id)
        return stmt

    def list_statements(
        self,
        *,
        tenant_context: TenantContext,
        period: str | None = None,
        scope_code: str | None = None,
        status: StatementLifecycleStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ShowbackStatement]:
        """Lists statements matching criteria."""
        return self.repository.list_statements(
            tenant_context=tenant_context,
            period=period,
            scope_code=scope_code,
            status=status,
            limit=limit,
            offset=offset,
        )

    # ==========================================================================
    # 2. Period Close Cycle & Restatement Adjustments
    # ==========================================================================

    def circulate_statement(
        self,
        statement_id: str,
        *,
        review_window_days: int = 5,
        tenant_context: TenantContext,
    ) -> ShowbackStatement:
        """Circulates draft statement to recipients with active review window."""
        stmt = self.get_statement(statement_id, tenant_context=tenant_context)
        circulated = self.cycle_engine.circulate_for_review(
            stmt, review_window_days=review_window_days, tenant_context=tenant_context
        )
        return self.repository.save_statement(circulated, tenant_context=tenant_context)

    def finalise_statement(
        self, statement_id: str, *, tenant_context: TenantContext
    ) -> ShowbackStatement:
        """Finalises the statement, locking it against any in-place alteration."""
        stmt = self.get_statement(statement_id, tenant_context=tenant_context)
        finalised = self.cycle_engine.finalise_statement(stmt, tenant_context=tenant_context)
        return self.repository.save_statement(finalised, tenant_context=tenant_context)

    def process_restatement_adjustment(
        self,
        statement_id: str,
        *,
        adjustment_deltas: list[dict[str, Any]],
        restatement_reason: str,
        tenant_context: TenantContext,
    ) -> tuple[ShowbackStatement, StatementAdjustment]:
        """Applies post-finalisation restatement without mutating the original statement in-place.

        Prompt 52 Rule:
        A restatement after finalisation produces a visible adjustment rather than a silently altered statement.
        """
        orig_stmt = self.get_statement(statement_id, tenant_context=tenant_context)

        adj_stmt, adj_record = self.cycle_engine.process_restatement_adjustment(
            orig_stmt,
            adjustment_deltas=adjustment_deltas,
            restatement_reason=restatement_reason,
            tenant_context=tenant_context,
        )

        # Update original statement status to SUPERSEDED
        self.repository.save_statement(orig_stmt, tenant_context=tenant_context)
        # Save newly emitted adjusted statement
        saved_adj_stmt = self.repository.save_statement(adj_stmt, tenant_context=tenant_context)
        # Persist adjustment record
        saved_adj_record = self.repository.save_adjustment(
            adj_record, tenant_context=tenant_context
        )

        return saved_adj_stmt, saved_adj_record

    def list_adjustments(
        self, statement_id: str, *, tenant_context: TenantContext
    ) -> list[StatementAdjustment]:
        """Lists all restatement adjustments associated with a statement."""
        return self.repository.list_adjustments_for_statement(
            statement_id, tenant_context=tenant_context
        )

    # ==========================================================================
    # 3. Dispute Path & Workflow Resolution
    # ==========================================================================

    def raise_dispute(
        self,
        statement_id: str,
        *,
        line_id: str,
        line_description: str,
        disputed_amount: Decimal | float,
        proposed_amount: Decimal | float,
        reason: str,
        tenant_context: TenantContext,
        assigned_owner: str = "finops-disputes@company.com",
    ) -> StatementDispute:
        """Queries/disputes a statement line, creating tracked item routed to workflow engine."""
        stmt = self.get_statement(statement_id, tenant_context=tenant_context)
        dispute = self.dispute_manager.raise_dispute(
            stmt,
            line_id=line_id,
            line_description=line_description,
            disputed_amount=disputed_amount,
            proposed_amount=proposed_amount,
            reason=reason,
            recipient_context=tenant_context,
            assigned_owner=assigned_owner,
        )
        self.repository.save_statement(stmt, tenant_context=tenant_context)
        return self.repository.save_dispute(dispute, tenant_context=tenant_context)

    def resolve_dispute(
        self,
        dispute_id: str,
        *,
        decision: DecisionOutcome | str,
        resolution_notes: str,
        target_reallocation_scope: str | None = None,
        tenant_context: TenantContext,
    ) -> tuple[StatementDispute, ReallocationRecord | None]:
        """Resolves dispute: if approved, records documented reallocation with audit trail."""
        dispute = self.repository.get_dispute(dispute_id, tenant_context=tenant_context)
        if not dispute:
            raise StatementNotFoundException(f"Dispute '{dispute_id}' not found.")

        stmt = self.get_statement(dispute.statement_id, tenant_context=tenant_context)
        resolved_disp, realloc = self.dispute_manager.resolve_dispute(
            dispute_id,
            statement=stmt,
            decision=decision,
            resolution_notes=resolution_notes,
            target_reallocation_scope=target_reallocation_scope,
            approver_context=tenant_context,
        )

        self.repository.save_dispute(resolved_disp, tenant_context=tenant_context)
        if realloc:
            self.repository.save_reallocation(realloc, tenant_context=tenant_context)

        return resolved_disp, realloc

    def list_disputes(
        self, statement_id: str, *, tenant_context: TenantContext
    ) -> list[StatementDispute]:
        """Lists all disputes for a statement."""
        return self.repository.list_disputes_for_statement(
            statement_id, tenant_context=tenant_context
        )

    # ==========================================================================
    # 4. Formal Acceptance & Outstanding Reports
    # ==========================================================================

    def accept_statement(
        self,
        statement_id: str,
        *,
        notes: str | None = None,
        tenant_context: TenantContext,
    ) -> ShowbackStatement:
        """Formally records recipient acceptance of the statement."""
        stmt = self.get_statement(statement_id, tenant_context=tenant_context)
        accepted = self.acceptance_engine.accept_statement(
            stmt, tenant_context=tenant_context, notes=notes
        )
        return self.repository.save_statement(accepted, tenant_context=tenant_context)

    def get_outstanding_acceptance_report(
        self, period: str, *, tenant_context: TenantContext
    ) -> OutstandingAcceptanceReport:
        """Generates executive compliance report of unaccepted statements."""
        statements = self.repository.list_statements(
            tenant_context=tenant_context, period=period, limit=5000
        )
        return self.acceptance_engine.generate_outstanding_acceptance_report(
            period=period, statements=statements, tenant_context=tenant_context
        )

    # ==========================================================================
    # 5. Allocation Transparency & Drill-Through
    # ==========================================================================

    def get_allocation_transparency(
        self,
        statement_id: str,
        line_id: str,
        *,
        tenant_context: TenantContext,
    ) -> AllocationTransparencyView:
        """Provides drill-through to winning rule, contributing resources, and permissioned charge lines."""
        stmt = self.get_statement(statement_id, tenant_context=tenant_context)
        return self.transparency_engine.get_allocation_transparency(
            stmt, line_id=line_id, user_context=tenant_context
        )

    # ==========================================================================
    # 6. Distribution & Multi-Format Exports
    # ==========================================================================

    def export_statement(
        self,
        statement_id: str,
        *,
        format: ExportFormat = ExportFormat.MARKDOWN,
        tenant_context: TenantContext,
    ) -> str:
        """Exports statement in requested format (MARKDOWN, HTML, CSV, JSON)."""
        stmt = self.get_statement(statement_id, tenant_context=tenant_context)
        return self.distribution_engine.export_statement(stmt, format=format)

    def distribute_statement(
        self,
        statement_id: str,
        *,
        channels: list[str] | None = None,
        tenant_context: TenantContext,
    ) -> dict[str, Any]:
        """Dispatches statement to object storage and simulated email channels."""
        stmt = self.get_statement(statement_id, tenant_context=tenant_context)
        return self.distribution_engine.dispatch_delivery(
            stmt, channels=channels, tenant_context=tenant_context
        )

    def list_templates(self) -> list[StatementTemplate]:
        """Lists available master-data statement layout templates."""
        return self.template_engine.list_templates()


_global_statement_service: StatementService | None = None
_service_lock = threading.RLock()


def get_statement_service() -> StatementService:
    """Returns singleton instance of StatementService."""
    global _global_statement_service
    if _global_statement_service is None:
        with _service_lock:
            if _global_statement_service is None:
                _global_statement_service = StatementService()
    return _global_statement_service


def reset_statement_service() -> None:
    """Resets singleton service and repository for testing isolation."""
    global _global_statement_service
    with _service_lock:
        _global_statement_service = None
    reset_statement_repository()
