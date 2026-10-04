"""Finance & ERP Integration Adapter (Prompt 60 / BBP Section 13.5).

Enforces:
- Inherits from BaseIntegrationAdapter with declared capabilities:
  AUTHENTICATE, HEALTH_CHECK, EXPORT_DATA, IMPORT_ENTITIES.
- Chart of Accounts (CoA) structure: exports cost centre, business unit, and allocated costs.
- Authority over Financial Hierarchy: imports cost centre and business unit masters
  where Finance is declared as the sole organizational authority.
- Period-Close Accrual Extract: computes period-close accruals including unbilled usage,
  commitment amortisation, and GL account journal entries at fiscal period close.
"""

from __future__ import annotations

import datetime as dt
import logging
from decimal import Decimal
from typing import Any

from domain.integrations.contract import BaseIntegrationAdapter
from domain.integrations.models import (
    CostCentreAccrualItem,
    IntegrationConfig,
    PeriodCloseAccrualExtract,
)
from domain.models.enums import (
    IntegrationCapability,
)
from domain.tenant.context import TenantContext
from masterdata.service import MasterDataService

logger = logging.getLogger(__name__)


class FinanceERPAdapter(BaseIntegrationAdapter):
    """Adapter for ERP and Financial Management Systems (SAP, Workday, Oracle ERP)."""

    def __init__(
        self,
        config: IntegrationConfig,
        declared_capabilities: set[IntegrationCapability] | None = None,
    ) -> None:
        super().__init__(config, declared_capabilities)
        # Store for generated period-close accrual extracts
        self._accrual_extracts: dict[str, PeriodCloseAccrualExtract] = {}
        # Store for imported financial masters: code -> record
        self._finance_cost_centres: dict[str, dict[str, Any]] = {}
        self._finance_business_units: dict[str, dict[str, Any]] = {}

    @property
    def adapter_name(self) -> str:
        return f"{self.config.custom_attributes.get('system_type', 'sap').lower()}_finance"

    def default_capabilities(self) -> set[IntegrationCapability]:
        return {
            IntegrationCapability.AUTHENTICATE,
            IntegrationCapability.HEALTH_CHECK,
            IntegrationCapability.EXPORT_DATA,
            IntegrationCapability.IMPORT_ENTITIES,
        }

    def import_financial_masters(
        self,
        cost_centres: list[dict[str, Any]],
        business_units: list[dict[str, Any]],
        *,
        tenant_context: TenantContext,
        master_data_service: MasterDataService | None = None,
    ) -> dict[str, int]:
        """Imports Cost Centre and Business Unit master records from authoritative Finance/ERP."""

        def _action() -> dict[str, int]:
            _ = master_data_service
            bu_count = 0
            cc_count = 0

            # Import Business Units
            for bu in business_units:
                code = str(bu.get("code", "")).strip().upper()
                if not code:
                    continue
                rec = {
                    "code": code,
                    "name": bu.get("name", code),
                    "head_of_unit": bu.get("head_of_unit", ""),
                    "cost_centre_prefix": bu.get("cost_centre_prefix", ""),
                    "tenant_id": tenant_context.tenant_id,
                    "_imported_from": self.adapter_name,
                }
                self._finance_business_units[code] = rec
                bu_count += 1

            # Import Cost Centres
            for cc in cost_centres:
                code = str(cc.get("code", "")).strip().upper()
                if not code:
                    continue
                rec = {
                    "code": code,
                    "name": cc.get("name", code),
                    "business_unit_code": cc.get("business_unit_code", ""),
                    "gl_account_code": cc.get("gl_account_code", "GL-52010"),
                    "tenant_id": tenant_context.tenant_id,
                    "_imported_from": self.adapter_name,
                }
                self._finance_cost_centres[code] = rec
                cc_count += 1

            logger.info(
                "Finance ERP master import complete: %d business units, %d cost centres.",
                bu_count,
                cc_count,
            )
            return {"business_units_imported": bu_count, "cost_centres_imported": cc_count}

        return self.execute_with_resilience(
            IntegrationCapability.IMPORT_ENTITIES,
            "import_financial_masters",
            _action,
        )

    def export_chart_of_accounts_costs(
        self,
        allocated_costs: list[dict[str, Any]],
        *,
        tenant_context: TenantContext,
    ) -> dict[str, Any]:
        """Exports allocated costs mapped to enterprise Chart of Accounts GL account structures."""

        def _action() -> dict[str, Any]:
            coa_entries: list[dict[str, Any]] = []
            total_allocated = Decimal("0.00")

            for cost_item in allocated_costs:
                cc_code = cost_item.get("cost_centre_code", "CC-DEFAULT")
                bu_code = cost_item.get("business_unit_code", "BU-DEFAULT")
                amount = Decimal(str(cost_item.get("amount", "0.00")))
                gl_code = cost_item.get("gl_account_code", "GL-52010-CLOUD-INFRA")

                total_allocated += amount
                coa_entries.append(
                    {
                        "cost_centre": cc_code,
                        "business_unit": bu_code,
                        "gl_account": gl_code,
                        "amount": float(amount),
                        "currency": cost_item.get("currency", "USD"),
                        "accounting_period": cost_item.get(
                            "fiscal_period", dt.datetime.now(dt.UTC).strftime("%Y-%m")
                        ),
                    }
                )

            return {
                "tenant_id": tenant_context.tenant_id,
                "chart_of_accounts_version": self.config.custom_attributes.get(
                    "coa_version", "COA-v2.1"
                ),
                "total_allocated": float(total_allocated),
                "line_item_count": len(coa_entries),
                "entries": coa_entries,
            }

        return self.execute_with_resilience(
            IntegrationCapability.EXPORT_DATA,
            "export_chart_of_accounts_costs",
            _action,
        )

    def generate_period_close_accrual_extract(
        self,
        fiscal_period: str,
        cost_centre_breakdown: list[dict[str, Any]],
        *,
        tenant_context: TenantContext,
        currency: str = "USD",
    ) -> PeriodCloseAccrualExtract:
        """Computes and seals the official Period-Close Accrual Extract for Finance & GL posting.

        Finance requires this extract immediately at period close to accrue unbilled usage,
        reconcile committed amortisations, and generate debits/credits in the General Ledger.
        """

        def _action() -> PeriodCloseAccrualExtract:
            items: list[CostCentreAccrualItem] = []
            grand_total = Decimal("0.00")

            for row in cost_centre_breakdown:
                cc_code = row.get("cost_centre_code", "CC-GENERIC")
                cc_name = row.get("cost_centre_name", f"Cost Centre {cc_code}")
                bu_code = row.get("business_unit_code", "BU-CORP")
                gl_code = row.get("gl_account_code", "GL-52010-CLOUD-OPEX")
                unbilled = Decimal(str(row.get("unbilled_usage_amount", "0.00")))
                amortised = Decimal(str(row.get("amortised_commitment_amount", "0.00")))
                total_accrued = Decimal(str(row.get("accrued_amount", unbilled + amortised)))

                grand_total += total_accrued
                items.append(
                    CostCentreAccrualItem(
                        cost_centre_code=cc_code,
                        cost_centre_name=cc_name,
                        business_unit_code=bu_code,
                        gl_account_code=gl_code,
                        accrued_amount=total_accrued,
                        currency=currency,
                        unbilled_usage_amount=unbilled,
                        amortised_commitment_amount=amortised,
                        description=f"Period close accrual for {fiscal_period} [{cc_code}]",
                    )
                )

            extract = PeriodCloseAccrualExtract(
                tenant_id=tenant_context.tenant_id,
                fiscal_period=fiscal_period,
                cutoff_timestamp=dt.datetime.now(dt.UTC),
                currency=currency,
                total_accrual=grand_total,
                cost_centre_items=items,
                chart_of_accounts_version=self.config.custom_attributes.get(
                    "coa_version", "COA-v2.1"
                ),
            )

            self._accrual_extracts[extract.extract_id] = extract
            logger.info(
                "Generated Period-Close Accrual Extract '%s' for period '%s' (Total: $%0.2f %s, Items: %d).",
                extract.extract_id,
                fiscal_period,
                float(grand_total),
                currency,
                len(items),
            )
            return extract

        return self.execute_with_resilience(
            IntegrationCapability.EXPORT_DATA,
            "generate_period_close_accrual_extract",
            _action,
        )

    def get_accrual_extract(self, extract_id: str) -> PeriodCloseAccrualExtract | None:
        """Retrieves an existing period-close accrual extract by ID."""
        return self._accrual_extracts.get(extract_id)
