"""FOCUS 1.0 Normalisation Mapper (Prompt 22 Items 2, 4, 5, 6).

Enforces:
- CST-001 & CST-002: Mapping provider-native or FOCUS billing data to canonical CostFact.
- CST-012: Distinct charge categorisation (Usage, Purchase, Tax, Credit, Adjustment).
  Purchases (e.g. reservations, savings plans) are strictly mapped to PURCHASE, never USAGE.
  Credits, refunds, and negative items are preserved as CREDIT, never silently netted into USAGE.
- All four cost measures retained: billed_cost, effective_cost, list_cost, contracted_cost.
- Realized discount value computed as a monetary value (list_cost - effective_cost).
- STRICT PROHIBITION: Store strictly in billing currency; never convert inside fact record.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from domain.cost.models import FocusCostFact
from domain.cost.schema_guard import SchemaVersionGuard
from domain.models.enums import (
    ChargeCategory,
    CostSourceType,
    ServiceCategory,
)
from domain.models.measures import FinancialMeasure, QuantityMeasure

logger = logging.getLogger(__name__)


class FocusMapper:
    """Translates provider-native and FOCUS-compliant billing exports into canonical FocusCostFacts."""

    @classmethod
    def map_dataset(
        cls,
        raw_records: list[dict[str, Any]],
        provider: str,
        schema_version: str,
        tenant_id: str,
        scope_id: str,
    ) -> list[FocusCostFact]:
        """Normalises a batch of raw records to canonical FocusCostFacts after schema verification."""
        SchemaVersionGuard.validate_schema(provider, schema_version)

        facts: list[FocusCostFact] = []
        is_focus = SchemaVersionGuard.is_focus_native(schema_version)

        for idx, row in enumerate(raw_records):
            if is_focus:
                fact = cls._map_focus_direct(
                    row, provider, schema_version, tenant_id, scope_id, idx
                )
            elif provider.lower() == "aws":
                fact = cls._map_aws_cur(row, schema_version, tenant_id, scope_id, idx)
            elif provider.lower() == "azure":
                fact = cls._map_azure_native(row, schema_version, tenant_id, scope_id, idx)
            elif provider.lower() == "gcp":
                fact = cls._map_gcp_native(row, schema_version, tenant_id, scope_id, idx)
            elif provider.lower() == "oci":
                fact = cls._map_oci_native(row, schema_version, tenant_id, scope_id, idx)
            else:
                fact = cls._map_focus_direct(
                    row, provider, schema_version, tenant_id, scope_id, idx
                )

            facts.append(fact)

        return facts

    @classmethod
    def _map_focus_direct(
        cls,
        row: dict[str, Any],
        provider: str,
        schema_version: str,
        tenant_id: str,
        scope_id: str,
        idx: int,
    ) -> FocusCostFact:
        """One-to-one mapping for datasets already adhering to the FOCUS 1.0 schema."""
        billed = Decimal(str(row.get("BilledCost", row.get("billed_cost", "0.0"))))
        effective = Decimal(str(row.get("EffectiveCost", row.get("effective_cost", billed))))
        list_val = (
            Decimal(str(row.get("ListCost", row.get("list_cost"))))
            if row.get("ListCost") or row.get("list_cost")
            else None
        )
        contracted_val = (
            Decimal(str(row.get("ContractedCost", row.get("contracted_cost"))))
            if row.get("ContractedCost") or row.get("contracted_cost")
            else None
        )

        billed_fm = FinancialMeasure(billed)
        effective_fm = FinancialMeasure(effective)
        list_fm = (
            FinancialMeasure(list_val)
            if list_val is not None
            else FinancialMeasure.not_applicable()
        )
        contracted_fm = (
            FinancialMeasure(contracted_val)
            if contracted_val is not None
            else FinancialMeasure.not_applicable()
        )

        # Realized discount computation (Item 5)
        realized_discount = (
            FinancialMeasure(round(list_val - effective, 6))
            if list_val is not None
            else FinancialMeasure.not_applicable()
        )

        charge_cat_str = str(row.get("ChargeCategory", row.get("charge_category", "Usage"))).strip()
        charge_category = cls._parse_charge_category(charge_cat_str, billed, row)

        period_start = cls._parse_datetime(
            row.get("ChargePeriodStart", row.get("charge_period_start", datetime.now(UTC)))
        )
        period_end = cls._parse_datetime(
            row.get("ChargePeriodEnd", row.get("charge_period_end", period_start))
        )

        qty_val = (
            Decimal(str(row.get("PricingQuantity", row.get("pricing_quantity"))))
            if row.get("PricingQuantity") is not None or row.get("pricing_quantity") is not None
            else None
        )
        pricing_qty = (
            QuantityMeasure(qty_val) if qty_val is not None else QuantityMeasure.not_applicable()
        )

        currency = (
            str(row.get("BillingCurrency", row.get("billing_currency", "USD"))).strip().upper()
        )

        return FocusCostFact(
            id=str(row.get("ChargeId", row.get("id", f"fact-{provider}-{idx}"))),
            tenant_id=tenant_id,
            scope_id=str(row.get("SubAccountId", row.get("scope_id", scope_id))),
            resource_id=row.get("ResourceId", row.get("resource_id")),
            provider=provider.lower(),
            service_id=str(row.get("ServiceName", row.get("service_id", "UnknownService"))),
            service_name=row.get("ServiceName", row.get("service_name")),
            service_category=cls._parse_service_category(row.get("ServiceCategory")),
            charge_period_start=period_start,
            charge_period_end=period_end,
            billing_period_start=period_start.date().replace(day=1),
            billing_period_end=period_end.date(),
            charge_category=charge_category,
            cost_source=CostSourceType.INVOICE,
            charge_subcategory=row.get("ChargeSubcategory", row.get("charge_subcategory")),
            charge_description=row.get("ChargeDescription", row.get("charge_description")),
            billed_cost=billed_fm,
            effective_cost=effective_fm,
            list_cost=list_fm,
            contracted_cost=contracted_fm,
            billing_currency=currency,  # STRICT: stored in native currency, never converted inside fact
            pricing_quantity=pricing_qty,
            pricing_unit=row.get("PricingUnit", row.get("pricing_unit")),
            commitment_id=row.get(
                "CommitmentDiscountId",
                row.get("CommitmentId", row.get("commitment_id")),
            ),
            commitment_type=row.get(
                "CommitmentDiscountType",
                row.get("CommitmentType", row.get("commitment_type")),
            ),
            is_commitment_covered=bool(
                row.get("CommitmentDiscountId")
                or row.get("CommitmentId")
                or row.get("commitment_id")
                or row.get("is_commitment_covered")
            ),
            realised_discount_value=realized_discount,
            tags=row.get("Tags", row.get("tags", {})),
            cost_categories=row.get("CostCategories", row.get("cost_categories", {})),
            provider_native=row,
            schema_version=schema_version,
        )

    @classmethod
    def _map_aws_cur(
        cls,
        row: dict[str, Any],
        schema_version: str,
        tenant_id: str,
        scope_id: str,
        idx: int,
    ) -> FocusCostFact:
        """Translates AWS CUR 2.0 native record to FOCUS 1.0."""
        unblended_cost = Decimal(
            str(row.get("lineItem/UnblendedCost", row.get("unblended_cost", "0.0")))
        )
        # In AWS CUR, effective cost includes amortized reservation/savings plan fee
        net_cost = Decimal(str(row.get("lineItem/NetUnblendedCost", unblended_cost)))
        amortized_fee = Decimal(
            str(
                row.get(
                    "reservation/AmortizedUpfrontFeeForBillingPeriod",
                    row.get("savingsPlan/AmortizedUpfrontCommitmentForBillingPeriod", "0.0"),
                )
            )
        )
        effective_cost = net_cost + amortized_fee

        usage_qty_val = Decimal(
            str(row.get("lineItem/UsageQuantity", row.get("usage_quantity", "0.0")))
        )
        # List cost
        if "pricing/publicOnDemandCost" in row:
            list_cost = Decimal(str(row["pricing/publicOnDemandCost"]))
        else:
            list_rate = row.get("pricing/publicOnDemandRate")
            list_cost = (
                Decimal(str(list_rate)) * usage_qty_val if list_rate is not None else unblended_cost
            )

        line_type = str(row.get("lineItem/LineItemType", "")).strip()

        # Strict charge categorisation (Prompt 22 Item 4)
        if line_type in ("Fee", "RIFee", "SavingsPlanNegation", "SavingsPlanCoveredUsage"):
            if "Fee" in line_type and unblended_cost > Decimal("0.0"):
                charge_category = ChargeCategory.PURCHASE
            else:
                charge_category = ChargeCategory.USAGE
        elif line_type in ("Tax",):
            charge_category = ChargeCategory.TAX
        elif line_type in ("Credit", "Refund") or unblended_cost < Decimal("0.0"):
            charge_category = ChargeCategory.CREDIT  # Preserved as credit, never netted into usage!
        elif line_type in ("Adjustment",):
            charge_category = ChargeCategory.ADJUSTMENT
        else:
            charge_category = ChargeCategory.USAGE

        time_interval = str(
            row.get(
                "identity/TimeInterval",
                row.get("start_time", "2026-03-01T00:00:00Z/2026-03-01T01:00:00Z"),
            )
        )
        start_time, end_time = cls._parse_time_interval(time_interval, row)

        tags = {
            k.replace("resourceTags/user:", "").replace("resourceTags/", ""): str(v)
            for k, v in row.items()
            if (k.startswith("resourceTags/") or k.startswith("resourceTags/user:"))
            and str(v).strip()
        }
        if "tags" in row and isinstance(row["tags"], dict):
            tags.update(row["tags"])

        cost_categories = {
            k.replace("costCategory/", ""): str(v)
            for k, v in row.items()
            if k.startswith("costCategory/") and str(v).strip()
        }
        if "cost_categories" in row and isinstance(row["cost_categories"], dict):
            cost_categories.update(row["cost_categories"])

        commitment_id = row.get("reservation/ReservationARN", row.get("savingsPlan/SavingsPlanARN"))
        is_committed = bool(
            commitment_id or "SavingsPlan" in line_type or "DiscountedUsage" in line_type
        )

        realized_discount = FinancialMeasure(round(list_cost - effective_cost, 6))

        return FocusCostFact(
            id=str(row.get("identity/LineItemId", row.get("line_item_id", f"fact-aws-{idx}"))),
            tenant_id=tenant_id,
            scope_id=str(row.get("lineItem/UsageAccountId", row.get("usage_account_id", scope_id))),
            resource_id=row.get("lineItem/ResourceId", row.get("resource_id")),
            provider="aws",
            service_id=str(row.get("lineItem/ProductCode", row.get("product_code", "AmazonEC2"))),
            service_name=str(row.get("product/ProductName", row.get("product_code", "AmazonEC2"))),
            service_category=cls._parse_service_category(row.get("lineItem/ProductCode")),
            charge_period_start=start_time,
            charge_period_end=end_time,
            billing_period_start=start_time.date().replace(day=1),
            billing_period_end=end_time.date(),
            charge_category=charge_category,
            cost_source=CostSourceType.INVOICE,
            charge_subcategory=line_type or "OnDemand",
            charge_description=row.get("lineItem/LineItemDescription", row.get("operation")),
            billed_cost=FinancialMeasure(unblended_cost),
            effective_cost=FinancialMeasure(effective_cost),
            list_cost=FinancialMeasure(list_cost),
            contracted_cost=FinancialMeasure.not_applicable(),
            billing_currency=str(
                row.get("lineItem/CurrencyCode", row.get("currency", "USD"))
            ).upper(),
            pricing_quantity=QuantityMeasure(usage_qty_val),
            pricing_unit=row.get("pricing/unit", row.get("pricing_unit", "Hrs")),
            commitment_id=commitment_id,
            commitment_type="SAVINGS_PLAN"
            if "savingsPlan" in str(commitment_id).lower()
            else "RESERVED_INSTANCE"
            if commitment_id
            else None,
            is_commitment_covered=is_committed,
            realised_discount_value=realized_discount,
            tags=tags,
            cost_categories=cost_categories,
            provider_native=row,
            schema_version=schema_version,
        )

    @classmethod
    def _map_azure_native(
        cls,
        row: dict[str, Any],
        schema_version: str,
        tenant_id: str,
        scope_id: str,
        idx: int,
    ) -> FocusCostFact:
        """Translates Azure EA / MCA Cost Details API v2 to FOCUS 1.0."""
        cost_in_billing = Decimal(str(row.get("costInBillingCurrency", row.get("cost", "0.0"))))
        effective_cost = Decimal(str(row.get("effectivePrice", cost_in_billing)))
        charge_type = str(row.get("chargeType", "Usage")).strip()

        if charge_type.lower() in ("purchase", "reservationpurchase"):
            charge_category = ChargeCategory.PURCHASE
        elif charge_type.lower() in ("tax",):
            charge_category = ChargeCategory.TAX
        elif charge_type.lower() in ("credit", "refund") or cost_in_billing < Decimal("0.0"):
            charge_category = ChargeCategory.CREDIT
        elif charge_type.lower() in ("adjustment",):
            charge_category = ChargeCategory.ADJUSTMENT
        else:
            charge_category = ChargeCategory.USAGE

        start_time = cls._parse_datetime(row.get("date", datetime.now(UTC)))
        end_time = cls._parse_datetime(row.get("date", start_time))

        qty_val = Decimal(str(row.get("quantity", "0.0")))
        reservation_id = row.get("reservationId")
        payg_cost = row.get("paygCostInBillingCurrency")
        list_cost = Decimal(str(payg_cost)) if payg_cost is not None else cost_in_billing
        realized_discount = max(list_cost - effective_cost, Decimal("0.0"))

        return FocusCostFact(
            id=str(row.get("id", f"fact-azure-{idx}")),
            tenant_id=tenant_id,
            scope_id=str(row.get("subscriptionId", scope_id)),
            resource_id=row.get("resourceId"),
            provider="azure",
            service_id=str(
                row.get("consumedService", row.get("meterCategory", "Microsoft.Compute"))
            ),
            service_name=str(row.get("meterCategory", "Compute")),
            service_category=cls._parse_service_category(
                row.get("consumedService") or row.get("meterCategory")
            ),
            charge_period_start=start_time,
            charge_period_end=end_time,
            billing_period_start=start_time.date().replace(day=1),
            billing_period_end=end_time.date(),
            charge_category=charge_category,
            cost_source=CostSourceType.INVOICE,
            charge_subcategory=charge_type,
            charge_description=row.get("meterName"),
            billed_cost=FinancialMeasure(cost_in_billing),
            effective_cost=FinancialMeasure(effective_cost),
            list_cost=FinancialMeasure(list_cost),
            contracted_cost=FinancialMeasure.not_applicable(),
            billing_currency=str(row.get("billingCurrency", "USD")).upper(),
            pricing_quantity=QuantityMeasure(qty_val),
            pricing_unit=row.get("unitOfMeasure"),
            commitment_id=reservation_id,
            commitment_type="RESERVED_INSTANCE" if reservation_id else None,
            is_commitment_covered=bool(reservation_id),
            realised_discount_value=FinancialMeasure(realized_discount)
            if realized_discount > Decimal("0.0")
            else FinancialMeasure.not_applicable(),
            tags=row.get("tags", {}),
            provider_native=row,
            schema_version=schema_version,
        )

    @classmethod
    def _map_gcp_native(
        cls,
        row: dict[str, Any],
        schema_version: str,
        tenant_id: str,
        scope_id: str,
        idx: int,
    ) -> FocusCostFact:
        """Translates GCP BigQuery detailed billing export v1 to FOCUS 1.0."""
        cost = Decimal(str(row.get("cost", "0.0")))
        credits = row.get("credits", [])
        total_credit_amount = Decimal("0.0")
        for cred in credits:
            total_credit_amount += Decimal(str(cred.get("amount", "0.0")))

        # In GCP, effective cost incorporates Sustained Usage Discounts and CUD credits
        effective_cost = cost + total_credit_amount  # credits in GCP are negative numbers

        cost_type = str(row.get("cost_type", "regular")).lower()
        if "purchase" in cost_type:
            charge_category = ChargeCategory.PURCHASE
        elif "tax" in cost_type:
            charge_category = ChargeCategory.TAX
        elif "adjustment" in cost_type or "rounding" in cost_type:
            charge_category = ChargeCategory.ADJUSTMENT
        elif cost < Decimal("0.0"):
            charge_category = ChargeCategory.CREDIT
        else:
            charge_category = ChargeCategory.USAGE

        start_time = cls._parse_datetime(row.get("usage_start_time", datetime.now(UTC)))
        end_time = cls._parse_datetime(row.get("usage_end_time", start_time))

        svc = row.get("service", {})
        service_id = (
            svc.get("description", svc.get("id", "Compute Engine"))
            if isinstance(svc, dict)
            else str(svc)
        )

        proj = row.get("project", {})
        project_id = proj.get("id", scope_id) if isinstance(proj, dict) else str(proj)

        usage = row.get("usage", {})
        qty_val = (
            Decimal(str(usage.get("amount", "0.0")))
            if isinstance(usage, dict)
            else Decimal(str(row.get("usage_quantity", "0.0")))
        )
        pricing_unit = usage.get("unit") if isinstance(usage, dict) else row.get("usage_unit")

        labels = row.get("labels", {})
        system_labels = row.get("system_labels", {})
        combined_tags = (
            {**labels, **system_labels}
            if isinstance(labels, dict) and isinstance(system_labels, dict)
            else {}
        )

        return FocusCostFact(
            id=str(row.get("export_time", f"fact-gcp-{idx}")),
            tenant_id=tenant_id,
            scope_id=str(project_id or scope_id),
            resource_id=row.get("resource", {}).get("name")
            if isinstance(row.get("resource"), dict)
            else row.get("resource_id"),
            provider="gcp",
            service_id=service_id,
            service_name=service_id,
            service_category=cls._parse_service_category(service_id),
            charge_period_start=start_time,
            charge_period_end=end_time,
            billing_period_start=start_time.date().replace(day=1),
            billing_period_end=end_time.date(),
            charge_category=charge_category,
            cost_source=CostSourceType.INVOICE,
            charge_subcategory=cost_type,
            charge_description=row.get("sku", {}).get("description")
            if isinstance(row.get("sku"), dict)
            else None,
            billed_cost=FinancialMeasure(cost),
            effective_cost=FinancialMeasure(effective_cost),
            list_cost=FinancialMeasure(cost),
            contracted_cost=FinancialMeasure.not_applicable(),
            billing_currency=str(row.get("currency", "USD")).upper(),
            pricing_quantity=QuantityMeasure(qty_val),
            pricing_unit=pricing_unit,
            is_commitment_covered=any("CUD" in str(c.get("name", "")) for c in credits)
            if isinstance(credits, list)
            else False,
            realised_discount_value=FinancialMeasure(abs(total_credit_amount))
            if total_credit_amount < Decimal("0.0")
            else FinancialMeasure.not_applicable(),
            tags=combined_tags,
            provider_native=row,
            schema_version=schema_version,
        )

    @classmethod
    def _map_oci_native(
        cls,
        row: dict[str, Any],
        schema_version: str,
        tenant_id: str,
        scope_id: str,
        idx: int,
    ) -> FocusCostFact:
        """Translates OCI Cost and Usage Report v1 to FOCUS 1.0."""
        billed_cost = Decimal(str(row.get("cost/myCost", row.get("cost", "0.0"))))
        line_item_type = str(row.get("lineItem/type", "Usage")).strip()

        if line_item_type.lower() in ("purchase", "subscription"):
            charge_category = ChargeCategory.PURCHASE
        elif line_item_type.lower() in ("tax",):
            charge_category = ChargeCategory.TAX
        elif line_item_type.lower() in ("credit", "refund") or billed_cost < Decimal("0.0"):
            charge_category = ChargeCategory.CREDIT
        elif line_item_type.lower() in ("adjustment",):
            charge_category = ChargeCategory.ADJUSTMENT
        else:
            charge_category = ChargeCategory.USAGE

        start_time = cls._parse_datetime(row.get("lineItem/intervalUsageStart", datetime.now(UTC)))
        end_time = cls._parse_datetime(row.get("lineItem/intervalUsageEnd", start_time))

        qty_val = Decimal(str(row.get("usage/billedQuantity", "0.0")))

        return FocusCostFact(
            id=str(row.get("lineItem/referenceNo", f"fact-oci-{idx}")),
            tenant_id=tenant_id,
            scope_id=str(row.get("lineItem/tenantId", scope_id)),
            resource_id=row.get("lineItem/resourceId"),
            provider="oci",
            service_id=str(row.get("product/service", "Compute")),
            service_name=str(row.get("product/service", "Compute")),
            service_category=cls._parse_service_category(row.get("product/service")),
            charge_period_start=start_time,
            charge_period_end=end_time,
            billing_period_start=start_time.date().replace(day=1),
            billing_period_end=end_time.date(),
            charge_category=charge_category,
            cost_source=CostSourceType.INVOICE,
            charge_subcategory=line_item_type,
            charge_description=row.get("product/description"),
            billed_cost=FinancialMeasure(billed_cost),
            effective_cost=FinancialMeasure(billed_cost),
            list_cost=FinancialMeasure(billed_cost),
            contracted_cost=FinancialMeasure.not_applicable(),
            billing_currency=str(row.get("cost/currency", "USD")).upper(),
            pricing_quantity=QuantityMeasure(qty_val),
            pricing_unit=row.get("usage/unit"),
            tags=row.get("tags", {}),
            provider_native=row,
            schema_version=schema_version,
        )

    # --------------------------------------------------------------------------
    # Helper parsing routines
    # --------------------------------------------------------------------------

    @classmethod
    def _parse_charge_category(
        cls, val: str, cost_amount: Decimal, row: dict[str, Any] | None = None
    ) -> ChargeCategory:
        """Parses charge category, strictly preventing purchases or credits from masquerading as usage."""
        v = val.strip().lower()
        desc = str(row.get("charge_description", "")).lower() if row else ""
        if "purchase" in v or "upfront" in v or "purchase" in desc or "reservation" in desc:
            return ChargeCategory.PURCHASE
        if "tax" in v or "tax" in desc:
            return ChargeCategory.TAX
        if "credit" in v or "refund" in v or cost_amount < Decimal("0.0"):
            return ChargeCategory.CREDIT
        if "adjustment" in v or "true-up" in v or "correction" in v:
            return ChargeCategory.ADJUSTMENT
        return ChargeCategory.USAGE

    @classmethod
    def _parse_service_category(cls, service_str: str | None) -> ServiceCategory:
        """Heuristic mapping from service descriptor to canonical ServiceCategory."""
        if not service_str:
            return ServiceCategory.OTHER
        s = str(service_str).lower()
        if any(
            w in s
            for w in (
                "ec2",
                "compute",
                "vm",
                "virtualmachine",
                "virtual machine",
                "virtual machines",
                "instance",
                "lambda",
                "functions",
            )
        ):
            return ServiceCategory.COMPUTE
        if any(w in s for w in ("s3", "blob", "storage", "gcs", "volume", "ebs", "disk")):
            return ServiceCategory.STORAGE
        if any(
            w in s for w in ("vpc", "network", "bandwidth", "route", "gateway", "dns", "egress")
        ):
            return ServiceCategory.NETWORKING
        if any(
            w in s for w in ("rds", "sql", "database", "dynamo", "cosmos", "bigtable", "spanner")
        ):
            return ServiceCategory.DATABASE
        if any(w in s for w in ("iam", "security", "guardduty", "key", "vault", "shield")):
            return ServiceCategory.SECURITY_IDENTITY
        if any(
            w in s for w in ("bigquery", "athena", "redshift", "analytics", "kinesis", "dataproc")
        ):
            return ServiceCategory.ANALYTICS
        if any(w in s for w in ("sagemaker", "vertex", "ai", "ml", "bedrock", "openai")):
            return ServiceCategory.AI_ML
        return ServiceCategory.OTHER

    @classmethod
    def _parse_datetime(cls, val: Any) -> datetime:
        """Parses an ISO 8601 string or datetime into UTC datetime."""
        if isinstance(val, datetime):
            return val if val.tzinfo else val.replace(tzinfo=UTC)
        if isinstance(val, date):
            return datetime(val.year, val.month, val.day, tzinfo=UTC)
        if isinstance(val, str):
            clean = val.replace("Z", "+00:00")
            try:
                dt = datetime.fromisoformat(clean)
                return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
            except ValueError:
                pass
        return datetime.now(UTC)

    @classmethod
    def _parse_time_interval(
        cls, time_interval: str, row: dict[str, Any]
    ) -> tuple[datetime, datetime]:
        """Splits an ISO interval string (start/end) into two UTC datetimes."""
        if "/" in time_interval:
            parts = time_interval.split("/")
            return cls._parse_datetime(parts[0]), cls._parse_datetime(parts[1])
        st = cls._parse_datetime(row.get("start_time", datetime.now(UTC)))
        et = cls._parse_datetime(row.get("end_time", st))
        return st, et
