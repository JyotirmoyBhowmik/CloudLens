"""Statement Distribution & Multi-Format Export Engine (Prompt 52).

Enforces:
- Multi-format exports: JSON, Markdown, HTML, CSV.
- Delivery channels: email notification payload, object storage location, persistent in-app history.
- Prominent showback status and rate disclosure on all rendered formats.
- Scheduled and on-demand distribution workflows.
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any

from domain.audit.service import AuditService, get_audit_service
from domain.models.enums import AuditEventType
from domain.statements.models import (
    ExportFormat,
    ShowbackStatement,
)
from domain.tenant.context import TenantContext, require_tenant_context


class StatementDistributionEngine:
    """Handles rendering, multi-format export, and multi-channel delivery of showback packs."""

    def __init__(
        self,
        audit_service: AuditService | None = None,
        base_storage_path: Path | str | None = None,
    ) -> None:
        self.audit_service = audit_service or get_audit_service()
        self.base_storage_path = Path(base_storage_path or Path("./artifacts/statements"))

    def render_markdown(self, statement: ShowbackStatement) -> str:
        """Renders executive showback statement in GitHub Flavored Markdown."""
        lines = [
            f"# {statement.scope_name} — Cost Showback Statement",
            "",
            "> [!IMPORTANT]",
            f"> **{statement.showback_banner}**",
            "",
            "## 1. Executive Summary",
            "",
            f"- **Billing Period:** `{statement.period}`",
            f"- **Statement ID:** `{statement.statement_id}` (Version {statement.version})",
            f"- **Recipient Scope:** `{statement.scope_type.value}: {statement.scope_code}`",
            f"- **Accountable Owner:** `{statement.recipient_owner_id}` ({statement.recipient_owner_email})",
            f"- **Status:** `{statement.status.value}`",
            f"- **Presentation Currency:** `{statement.currency}` ({statement.currency_disclosure.rate_type} Rate: {statement.currency_disclosure.exchange_rate} as of {statement.currency_disclosure.rate_effective_date})",
            f"- **Total Allocated Cost:** **${statement.total_allocated_cost:,.2f}**",
            f"  - Direct Attributed Spend: ${statement.direct_allocated_cost:,.2f}",
            f"  - Shared Service Apportionments: ${statement.shared_service_apportioned_cost:,.2f}",
            f"  - Unallocated Pool Cost: ${statement.unallocated_cost:,.2f}",
            "",
            "## 2. Budget Performance & Period Variance",
            "",
            f"- **Assigned Budget Ceiling:** ${statement.budget_amount:,.2f}",
            f"- **Variance:** ${statement.budget_variance_amount:,.2f} ({statement.budget_variance_pct:+.1f}%) — **Status:** `{statement.budget_status.value}`",
            f"- **Budget Commentary:** {statement.budget_commentary}",
            f"- **Prior Period Spend ({statement.prior_period}):** ${statement.prior_period_cost:,.2f}",
            f"- **Month-over-Month Movement:** ${statement.period_movement_amount:+,.2f} ({statement.period_movement_pct:+.1f}%) — `{statement.movement_direction.value}`",
            f"- **Movement Commentary:** {statement.movement_commentary}",
            "",
            "## 3. Shared-Service Apportionments (With Explicit Basis)",
            "",
            "| Shared Service | Provider | Gross Cost | Share % | Apportioned Cost | Allocation Rule | Apportionment Basis |",
            "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
        ]

        for s in statement.shared_service_apportionments:
            lines.append(
                f"| **{s.shared_service_name}** | {s.provider} | ${s.source_total_cost:,.2f} | "
                f"{s.apportionment_percentage:.1f}% | ${s.apportioned_amount:,.2f} | "
                f"`{s.allocation_rule_id}` | {s.apportionment_basis} |"
            )

        lines.extend(
            [
                "",
                "## 4. Largest Cost Shifts & Drivers",
                "",
                "| Cost Item | Prior Period | Current Period | Shift ($) | Shift (%) | Narrative Business Explanation |",
                "| :--- | :--- | :--- | :--- | :--- | :--- |",
            ]
        )

        for m in statement.largest_movements:
            lines.append(
                f"| **{m.item_name}** | ${m.prior_amount:,.2f} | ${m.current_amount:,.2f} | "
                f"${m.delta_amount:+,.2f} | {m.delta_pct:+.1f}% | {m.narrative_explanation} |"
            )

        lines.extend(
            [
                "",
                "## 5. Multi-Cloud Provider Breakdown",
                "",
                "| Provider | Allocated Spend | Share (%) | Prior Period Spend | Shift ($) |",
                "| :--- | :--- | :--- | :--- | :--- |",
            ]
        )

        for p in statement.provider_breakdown:
            lines.append(
                f"| **{p.provider}** | ${p.allocated_amount:,.2f} | {p.share_percentage:.1f}% | "
                f"${p.prior_period_amount:,.2f} | ${p.movement_amount:+,.2f} |"
            )

        if statement.discount_benefit:
            d = statement.discount_benefit
            lines.extend(
                [
                    "",
                    "## 6. Realised Discount & Commitment Benefit",
                    "",
                    f"- **Equivalent List Cost:** ${d.list_cost:,.2f}",
                    f"- **Contracted Enterprise Cost:** ${d.contracted_cost:,.2f}",
                    f"- **Effective Cost Paid:** ${d.effective_cost:,.2f}",
                    f"- **Total Realised Discount Savings:** **${d.realised_discount_amount:,.2f}** ({d.realised_discount_percentage:.1f}%)",
                ]
            )

        lines.extend(
            [
                "",
                "---",
                f"*Generated by CloudLens Cost Allocation Engine on {statement.generated_at}.*",
                f"*Statement Mode: `{statement.mode.value}` (Phase 2 Chargeback: `Disabled`).*",
            ]
        )

        return "\n".join(lines)

    def render_csv(self, statement: ShowbackStatement) -> str:
        """Renders statement line items into CSV."""
        out = io.StringIO()
        writer = csv.writer(out, lineterminator="\n")

        writer.writerow(
            ["Section", "ItemKey", "ItemName", "Amount", "Currency", "BasisOrRule", "Status"]
        )
        writer.writerow(
            [
                "Header",
                statement.statement_id,
                statement.scope_name,
                str(statement.total_allocated_cost),
                statement.currency,
                "SHOWBACK",
                statement.status.value,
            ]
        )

        for s in statement.shared_service_apportionments:
            writer.writerow(
                [
                    "SharedApportionment",
                    s.shared_service_id,
                    s.shared_service_name,
                    str(s.apportioned_amount),
                    statement.currency,
                    s.apportionment_basis,
                    "APPORTIONED",
                ]
            )

        for p in statement.provider_breakdown:
            writer.writerow(
                [
                    "Provider",
                    p.provider,
                    f"{p.provider} Direct",
                    str(p.allocated_amount),
                    statement.currency,
                    f"{p.share_percentage}%",
                    "ALLOCATED",
                ]
            )

        for c in statement.category_breakdown:
            writer.writerow(
                [
                    "Category",
                    c.service_category,
                    c.service_category,
                    str(c.allocated_amount),
                    statement.currency,
                    f"{c.share_percentage}%",
                    "ALLOCATED",
                ]
            )

        return out.getvalue()

    def export_statement(
        self, statement: ShowbackStatement, format: ExportFormat = ExportFormat.MARKDOWN
    ) -> str:
        """Serializes statement to requested export format."""
        if format == ExportFormat.MARKDOWN:
            return self.render_markdown(statement)
        elif format == ExportFormat.CSV:
            return self.render_csv(statement)
        elif format == ExportFormat.JSON:
            return json.dumps(statement.model_dump(), indent=2, default=str)
        elif format == ExportFormat.HTML:
            md_text = self.render_markdown(statement)
            return f"<html><body><pre>{md_text}</pre></body></html>"
        return self.render_markdown(statement)

    def dispatch_delivery(
        self,
        statement: ShowbackStatement,
        *,
        channels: list[str] | None = None,
        tenant_context: TenantContext,
    ) -> dict[str, Any]:
        """Dispatches statement to object storage and simulated email distribution channels."""
        tc = require_tenant_context(tenant_context)
        delivery_channels = channels or ["OBJECT_STORAGE", "EMAIL"]
        results: dict[str, Any] = {}

        # 1. Object Storage Export
        if "OBJECT_STORAGE" in delivery_channels:
            dest_dir = (
                self.base_storage_path / f"tenant_id={tc.tenant_id}" / f"period={statement.period}"
            )
            dest_dir.mkdir(parents=True, exist_ok=True)

            md_path = dest_dir / f"{statement.statement_id}.md"
            json_path = dest_dir / f"{statement.statement_id}.json"

            md_path.write_text(self.render_markdown(statement), encoding="utf-8")
            json_path.write_text(
                self.export_statement(statement, ExportFormat.JSON), encoding="utf-8"
            )

            results["storage_path_md"] = str(md_path)
            results["storage_path_json"] = str(json_path)

        # 2. Email Delivery Simulation
        if "EMAIL" in delivery_channels:
            email_payload = {
                "recipient_to": statement.recipient_owner_email,
                "subject": f"CloudLens Monthly Showback Statement: {statement.scope_name} ({statement.period})",
                "statement_id": statement.statement_id,
                "period": statement.period,
                "total_cost": f"${statement.total_allocated_cost:,.2f} {statement.currency}",
                "review_deadline": statement.review_deadline,
                "download_link": f"/api/v1/statements/{statement.statement_id}/export?format=MARKDOWN",
            }
            results["email_dispatch"] = email_payload

        # 3. Record audit event
        self.audit_service.record_event(
            tenant_context=tc,
            event_type=AuditEventType.STATEMENT_DISTRIBUTED,
            actor=tc.user_id,
            action="STATEMENT_DISTRIBUTED",
            resource_type="SHOWBACK_STATEMENT",
            resource_id=statement.statement_id,
            payload={
                "channels": delivery_channels,
                "recipient_email": statement.recipient_owner_email,
                "results": results,
            },
        )

        return results
