"""Business Master Data Engines & Reference Domain Services (Prompt 46).

Enforces Prompt 46:
1. Budget allocation against registered Cost Centre and Business Unit masters (not free text).
2. Dynamic fiscal calendar period boundary recalculation with zero code changes.
3. Contracted negotiated rate precedence with explicit 'MANUAL' source labeling.
4. Holiday calendar suppression of runtime schedule-adherence exceptions.
5. Multi-currency conversion driven by tenant FX presentation policy.
6. Tag policy validation and enforcement postures.
7. Regional compliance and data-residency verification.
"""

import re
from calendar import monthrange
from datetime import date, datetime
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal

from pydantic import BaseModel, Field

from domain.models.exceptions import MasterDataException
from masterdata.models import MasterDataRecord
from masterdata.service import MasterDataService, get_master_data_service

# ==============================================================================
# 1. Budget Allocation Service (Item 11 & Acceptance 1)
# ==============================================================================


class BudgetAllocation(BaseModel):
    """Verified financial budget allocation bound to registered master data."""

    id: str
    tenant_id: str
    name: str
    amount: Decimal
    currency: str
    fiscal_year: int
    cost_centre_code: str
    cost_centre_name: str
    business_unit_code: str
    business_unit_name: str
    created_by: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class BudgetAllocationService:
    """Service ensuring financial budgets bind strictly to registered master entities."""

    def __init__(self, master_service: MasterDataService | None = None) -> None:
        self._master_service = master_service or get_master_data_service()

    def create_budget_allocation(
        self,
        tenant_id: str,
        name: str,
        amount: Decimal,
        currency: str,
        fiscal_year: int,
        cost_centre_code: str,
        business_unit_code: str,
        created_by: str,
        as_of: datetime | None = None,
    ) -> BudgetAllocation:
        """Creates a budget allocation.

        Acceptance: A budget can be created against a cost centre and a business unit
        that exist as master data, not as free text.
        """
        # 1. Validate Cost Centre master
        cost_centre = self._master_service.get_record(
            master_type="COST_CENTRE",
            code=cost_centre_code,
            as_of=as_of,
            tenant_id=tenant_id,
        )
        if not cost_centre:
            raise MasterDataException(
                f"Cannot create budget: Cost Centre '{cost_centre_code}' does not exist as an active master record. Free text identifiers are prohibited."
            )

        # 2. Validate Business Unit master
        business_unit = self._master_service.get_record(
            master_type="BUSINESS_UNIT",
            code=business_unit_code,
            as_of=as_of,
            tenant_id=tenant_id,
        )
        if not business_unit:
            raise MasterDataException(
                f"Cannot create budget: Business Unit '{business_unit_code}' does not exist as an active master record. Free text identifiers are prohibited."
            )

        # 3. Verify linkage between Cost Centre and Business Unit
        linked_bu = cost_centre.attributes.get("business_unit_code") or cost_centre.parent_code
        if linked_bu and linked_bu.upper() != business_unit_code.upper():
            raise MasterDataException(
                f"Cost Centre '{cost_centre_code}' is mapped to Business Unit '{linked_bu}', not '{business_unit_code}'."
            )

        # 4. Validate Currency
        curr = self._master_service.get_record("CURRENCY", currency)
        if not curr:
            raise MasterDataException(f"Currency '{currency}' is not a registered currency master.")

        alloc_id = f"bgt-{tenant_id[:8]}-{cost_centre_code.lower()}-{fiscal_year}"
        return BudgetAllocation(
            id=alloc_id,
            tenant_id=tenant_id,
            name=name,
            amount=amount,
            currency=currency.upper(),
            fiscal_year=fiscal_year,
            cost_centre_code=cost_centre.code,
            cost_centre_name=cost_centre.display_name,
            business_unit_code=business_unit.code,
            business_unit_name=business_unit.display_name,
            created_by=created_by,
        )


# ==============================================================================
# 2. Financial Calendar Engine (Item 15 & Acceptance 2)
# ==============================================================================


class FiscalPeriod(BaseModel):
    """Dynamic period definition representing an accounting boundary."""

    calendar_code: str
    fiscal_year: int
    period_number: int
    period_name: str
    start_date: date
    end_date: date
    close_date: date


class FinancialCalendarEngine:
    """Calculates financial period boundaries entirely from master data without code changes."""

    def __init__(self, master_service: MasterDataService | None = None) -> None:
        self._master_service = master_service or get_master_data_service()

    def get_fiscal_periods(
        self,
        calendar_code: str,
        fiscal_year: int,
        as_of: datetime | None = None,
    ) -> list[FiscalPeriod]:
        """Calculates all 12 period boundaries for a fiscal year from master data.

        Acceptance: Changing the fiscal year start changes every period boundary
        across the product with no code change.
        """
        record = self._master_service.get_record("FISCAL_CALENDAR", calendar_code, as_of=as_of)
        if not record:
            raise MasterDataException(
                f"Fiscal calendar '{calendar_code}' not found in master registry."
            )

        start_month = int(record.attributes.get("fiscal_year_start_month", 1))
        start_day = int(record.attributes.get("fiscal_year_start_day", 1))

        periods: list[FiscalPeriod] = []

        for p_idx in range(12):
            period_num = p_idx + 1
            # Calculate current month and year
            total_month = (start_month - 1) + p_idx
            p_year = fiscal_year + (total_month // 12) if start_month > 1 else fiscal_year
            p_month = (total_month % 12) + 1

            _, days_in_month = monthrange(p_year, p_month)
            p_start = date(p_year, p_month, min(start_day, days_in_month))
            p_end = date(p_year, p_month, days_in_month)

            # Close date: 5 days after period end by default
            close_day = min(5, days_in_month)
            next_month = (p_month % 12) + 1
            next_year = p_year + (1 if p_month == 12 else 0)
            p_close = date(next_year, next_month, close_day)

            periods.append(
                FiscalPeriod(
                    calendar_code=calendar_code,
                    fiscal_year=fiscal_year,
                    period_number=period_num,
                    period_name=f"Period {period_num} ({p_start.strftime('%b %Y')})",
                    start_date=p_start,
                    end_date=p_end,
                    close_date=p_close,
                )
            )

        return periods

    def get_period_for_date(
        self,
        calendar_code: str,
        target_date: date,
        as_of: datetime | None = None,
    ) -> FiscalPeriod:
        """Determines which fiscal period a given date falls into."""
        # Check surrounding fiscal years
        for f_year in (target_date.year - 1, target_date.year, target_date.year + 1):
            periods = self.get_fiscal_periods(calendar_code, f_year, as_of=as_of)
            for p in periods:
                if p.start_date <= target_date <= p.end_date:
                    return p

        # Fallback to current year first period if unbounded
        periods = self.get_fiscal_periods(calendar_code, target_date.year, as_of=as_of)
        return periods[0]


# ==============================================================================
# 3. Runtime Schedule Adherence Engine (Item 15 & Acceptance 4)
# ==============================================================================


class ScheduleAdherenceResult(BaseModel):
    """Result of evaluating operational runtime state against schedule & holiday calendar."""

    resource_id: str
    environment_code: str
    is_production: bool
    check_date: date
    is_working_day: bool
    is_holiday: bool
    holiday_name: str | None = None
    expected_status: str
    exception_detected: bool
    is_suppressed: bool
    suppression_reason: str | None = None


class RuntimeScheduleAdherenceEngine:
    """Evaluates resource schedule adherence with holiday calendar suppression."""

    def __init__(self, master_service: MasterDataService | None = None) -> None:
        self._master_service = master_service or get_master_data_service()

    def evaluate_schedule_adherence(
        self,
        resource_id: str,
        environment_code: str,
        current_status: str,
        check_date: date,
        location_code: str = "LOC_US_EAST_VA",
    ) -> ScheduleAdherenceResult:
        """Evaluates whether an active resource adheres to environment schedules.

        Acceptance: A holiday in the holiday calendar suppresses a schedule-adherence
        exception for that day.
        """
        env = self._master_service.get_record("ENVIRONMENT", environment_code)
        is_prod = env.attributes.get("is_production", False) if env else False

        # Production environments always expected to be RUNNING
        if is_prod:
            expected = "RUNNING"
            is_exc = current_status.upper() != "RUNNING"
            return ScheduleAdherenceResult(
                resource_id=resource_id,
                environment_code=environment_code,
                is_production=True,
                check_date=check_date,
                is_working_day=True,
                is_holiday=False,
                expected_status=expected,
                exception_detected=is_exc,
                is_suppressed=False,
            )

        # Non-production: check working week and location holidays
        weekday = check_date.isoweekday()  # 1=Monday ... 7=Sunday
        is_weekend = weekday in (6, 7)

        # Check Holiday Calendar
        loc = self._master_service.get_record("LOCATION", location_code)
        hol_cal_code = (
            loc.attributes.get("holiday_calendar_code", "HOL_US_FEDERAL")
            if loc
            else "HOL_US_FEDERAL"
        )
        hol_cal = self._master_service.get_record("HOLIDAY_CALENDAR", hol_cal_code)

        is_holiday = False
        holiday_name = None
        date_str = check_date.isoformat()

        if hol_cal:
            holidays = hol_cal.attributes.get("holidays", [])
            for h in holidays:
                if h.get("date") == date_str:
                    is_holiday = True
                    holiday_name = h.get("name", "Public Holiday")
                    break

        is_working_day = not is_weekend and not is_holiday
        expected_status = "RUNNING" if is_working_day else "STOPPED"

        raw_exception = current_status.upper() != expected_status

        # Suppression Rule: If running on a holiday or weekend when stopped was expected,
        # or if stopped on a holiday, suppress the schedule-adherence alert
        is_suppressed = False
        suppression_reason = None

        if is_holiday:
            is_suppressed = True
            suppression_reason = (
                f"Statutory holiday '{holiday_name}' suppresses schedule-adherence exception."
            )
        elif is_weekend and raw_exception and current_status.upper() == "RUNNING":
            # Weekend override check
            pass

        return ScheduleAdherenceResult(
            resource_id=resource_id,
            environment_code=environment_code,
            is_production=False,
            check_date=check_date,
            is_working_day=is_working_day,
            is_holiday=is_holiday,
            holiday_name=holiday_name,
            expected_status=expected_status,
            exception_detected=raw_exception and not is_suppressed,
            is_suppressed=is_suppressed,
            suppression_reason=suppression_reason,
        )


# ==============================================================================
# 4. Contract Rate Engine (Item 17 & Acceptance 3)
# ==============================================================================


class EffectiveRateResult(BaseModel):
    """Result of rate lookup enforcing contracted rate precedence and manual labeling."""

    provider_code: str
    service_code: str
    sku_id: str
    effective_rate: Decimal
    list_rate: Decimal
    contracted_rate: Decimal | None
    currency: str
    is_contracted_rate: bool
    rate_source: str  # Must be 'MANUAL' for uploaded/contracted rates
    contract_reference: str | None = None
    rate_label: str  # Visibly displayed label


class ContractRateEngine:
    """Resolves rates with contracted-supersedes-list precedence and visible MANUAL labeling."""

    def __init__(self, master_service: MasterDataService | None = None) -> None:
        self._master_service = master_service or get_master_data_service()

    def resolve_effective_rate(
        self,
        provider_code: str,
        service_code: str,
        sku_id: str,
        as_of: datetime | None = None,
    ) -> EffectiveRateResult:
        """Resolves rate card.

        Acceptance: An uploaded negotiated rate supersedes the provider list rate
        and is visibly labelled as a manual-source rate.
        Rule: Do not let an uploaded rate be presented as provider-API-derived.
        """
        rate_cards = self._master_service.list_records("RATE_CARD", as_of=as_of)

        matched: MasterDataRecord | None = None
        for rc in rate_cards:
            attrs = rc.attributes
            if (
                attrs.get("provider_code", "").upper() == provider_code.upper()
                and attrs.get("service_code", "").upper() == service_code.upper()
                and attrs.get("sku_id", "").upper() == sku_id.upper()
            ):
                matched = rc
                break

        if not matched:
            raise MasterDataException(
                f"Rate card not found for {provider_code}/{service_code}/{sku_id}."
            )

        attrs = matched.attributes
        raw_list = Decimal(str(attrs.get("list_rate", "0.0")))
        raw_contracted = (
            Decimal(str(attrs["contracted_rate"]))
            if attrs.get("contracted_rate") is not None
            else None
        )
        curr = attrs.get("currency", "USD")
        contract_ref = attrs.get("contract_reference")

        # Contracted rate precedence rule
        if raw_contracted is not None:
            effective = raw_contracted
            is_contracted = True
            # Mandatory source labeling per Prompt 46 Item 17 & Acceptance 3
            source_label = "MANUAL"
            rate_label = f"Negotiated Contract Rate ({contract_ref or 'Custom'}) [Source: MANUAL]"
        else:
            effective = raw_list
            is_contracted = False
            source_label = attrs.get("source", "PROVIDER_API")
            rate_label = f"Provider Public List Rate [Source: {source_label}]"

        return EffectiveRateResult(
            provider_code=provider_code.upper(),
            service_code=service_code,
            sku_id=sku_id,
            effective_rate=effective,
            list_rate=raw_list,
            contracted_rate=raw_contracted,
            currency=curr,
            is_contracted_rate=is_contracted,
            rate_source=source_label,
            contract_reference=contract_ref,
            rate_label=rate_label,
        )


# ==============================================================================
# 5. Currency Converter Engine (Item 16 & Acceptance 5)
# ==============================================================================


class CurrencyConversionResult(BaseModel):
    """Result of multi-currency translation driven by tenant FX policy."""

    original_amount: Decimal
    from_currency: str
    reporting_currency: str
    rate_used: Decimal
    rate_type: str
    rate_date: str
    rate_source: str
    converted_amount: Decimal
    formatted_display: str


class CurrencyConverterEngine:
    """Translates costs into tenant reporting currency using policy-selected rate types."""

    def __init__(self, master_service: MasterDataService | None = None) -> None:
        self._master_service = master_service or get_master_data_service()

    def convert_cost(
        self,
        amount: Decimal,
        from_currency: str,
        presentation_context: str = "actual_cost",
        tenant_id: str | None = None,
        as_of_date: str | None = None,
    ) -> CurrencyConversionResult:
        """Converts cost amount to reporting currency per tenant policy.

        Acceptance: Converting a cost to the reporting currency uses the rate type
        the tenant policy selects, and the rate and rate date are displayed.
        """
        from_curr = from_currency.strip().upper()

        # 1. Resolve Tenant FX Policy
        policy = self._master_service.get_record(
            "TENANT_FX_POLICY", "FX_POLICY_DEFAULT", tenant_id=tenant_id
        )
        reporting_curr = policy.attributes.get("reporting_currency", "USD") if policy else "USD"
        pres_policies = policy.attributes.get("presentation_policies", {}) if policy else {}
        selected_rate_type = pres_policies.get(presentation_context, "MONTHLY_AVERAGE")

        # Identity conversion
        if from_curr == reporting_curr.upper():
            return CurrencyConversionResult(
                original_amount=amount,
                from_currency=from_curr,
                reporting_currency=reporting_curr,
                rate_used=Decimal("1.000000"),
                rate_type="IDENTITY",
                rate_date=as_of_date or datetime.utcnow().strftime("%Y-%m-%d"),
                rate_source="SYSTEM",
                converted_amount=amount,
                formatted_display=f"{reporting_curr} {amount:,.2f} (Rate: 1.000000, 1:1)",
            )

        # 2. Look up effective exchange rate for selected rate type
        rates = self._master_service.list_records("EXCHANGE_RATE")
        matched_rate: MasterDataRecord | None = None

        for r in rates:
            attrs = r.attributes
            if (
                attrs.get("from_currency", "").upper() == from_curr
                and attrs.get("to_currency", "").upper() == reporting_curr
                and attrs.get("rate_type", "").upper() == selected_rate_type.upper()
            ):
                matched_rate = r
                break

        # Fallback to inverse lookup if not direct
        inverse_rate = False
        if not matched_rate:
            for r in rates:
                attrs = r.attributes
                if (
                    attrs.get("from_currency", "").upper() == reporting_curr
                    and attrs.get("to_currency", "").upper() == from_curr
                    and attrs.get("rate_type", "").upper() == selected_rate_type.upper()
                ):
                    matched_rate = r
                    inverse_rate = True
                    break

        if not matched_rate:
            raise MasterDataException(
                f"Exchange rate not found from '{from_curr}' to '{reporting_curr}' for rate type '{selected_rate_type}'."
            )

        attrs = matched_rate.attributes
        raw_rate = Decimal(str(attrs["rate"]))
        rate_used = (Decimal("1.0") / raw_rate) if inverse_rate else raw_rate
        rate_date = str(attrs.get("effective_date", "2026-09-01"))
        rate_source = str(attrs.get("source", "MANUAL"))

        # 3. Currency rounding rule from CURRENCY master (Default: HALF_EVEN / Banker's rounding)
        curr_master = self._master_service.get_record("CURRENCY", reporting_curr)
        minor_units = int(curr_master.attributes.get("minor_units", 2)) if curr_master else 2
        rounding_rule_name = (
            curr_master.attributes.get("rounding_rule", "HALF_EVEN") if curr_master else "HALF_EVEN"
        )
        rounding_mode = ROUND_HALF_EVEN if rounding_rule_name == "HALF_EVEN" else ROUND_HALF_UP

        quantize_exp = Decimal("1") if minor_units == 0 else Decimal(f"1e-{minor_units}")
        converted = (amount * rate_used).quantize(quantize_exp, rounding=rounding_mode)

        sym = (
            curr_master.attributes.get("symbol", reporting_curr) if curr_master else reporting_curr
        )
        formatted = f"{sym}{converted:,.{minor_units}f} (Rate: {rate_used:.6f}, {selected_rate_type} on {rate_date} via {rate_source})"

        return CurrencyConversionResult(
            original_amount=amount,
            from_currency=from_curr,
            reporting_currency=reporting_curr,
            rate_used=rate_used,
            rate_type=selected_rate_type,
            rate_date=rate_date,
            rate_source=rate_source,
            converted_amount=converted,
            formatted_display=formatted,
        )


# ==============================================================================
# 6. Tag Policy Engine (Item 20)
# ==============================================================================


class TagComplianceReport(BaseModel):
    """Compliance assessment against registered tag policies."""

    policy_code: str
    is_compliant: bool
    missing_mandatory_keys: list[str]
    invalid_value_keys: dict[str, str]  # key -> reason
    regex_format_violations: dict[str, str]  # key -> pattern violated
    enforcement_posture: str  # REPORT_ONLY, EXCEPTION, BLOCK_AT_POLICY
    should_block_operation: bool


class TagPolicyEngine:
    """Validates resource tag dictionaries against corporate tag policies."""

    def __init__(self, master_service: MasterDataService | None = None) -> None:
        self._master_service = master_service or get_master_data_service()

    def evaluate_tags(
        self,
        tags: dict[str, str],
        policy_code: str = "TAG_POL_ENTERPRISE_MANDATORY",
    ) -> TagComplianceReport:
        """Evaluates tags against master tag policy."""
        policy = self._master_service.get_record("TAG_POLICY", policy_code)
        if not policy:
            raise MasterDataException(f"Tag policy '{policy_code}' not found in master registry.")

        attrs = policy.attributes
        mandatory_keys = attrs.get("mandatory_tag_keys", [])
        allowed_values = attrs.get("allowed_values", {})
        format_rules = attrs.get("format_rules", {})
        posture = attrs.get("enforcement_posture", "EXCEPTION")

        missing = [k for k in mandatory_keys if k not in tags or not tags[k]]
        invalid_vals: dict[str, str] = {}
        format_errs: dict[str, str] = {}

        for k, allowed in allowed_values.items():
            if k in tags and tags[k] not in allowed:
                invalid_vals[k] = f"Value '{tags[k]}' not in allowed set: {allowed}"

        for k, pattern in format_rules.items():
            if k in tags and tags[k]:
                if not re.match(pattern, tags[k]):
                    format_errs[k] = f"Value '{tags[k]}' failed regex: {pattern}"

        is_compliant = len(missing) == 0 and len(invalid_vals) == 0 and len(format_errs) == 0
        should_block = (not is_compliant) and (posture == "BLOCK_AT_POLICY")

        return TagComplianceReport(
            policy_code=policy_code,
            is_compliant=is_compliant,
            missing_mandatory_keys=missing,
            invalid_value_keys=invalid_vals,
            regex_format_violations=format_errs,
            enforcement_posture=posture,
            should_block_operation=should_block,
        )


# ==============================================================================
# 7. Geography Compliance Engine (Item 21)
# ==============================================================================


class GeographyComplianceResult(BaseModel):
    """Regional deployment and data residency compliance evaluation."""

    provider_code: str
    region_name: str
    geography_code: str | None
    geography_name: str | None
    jurisdiction: str | None
    data_residency_classification: str | None
    is_approved_for_deployment: bool
    compliance_message: str


class GeographyComplianceEngine:
    """Verifies regional workload placement against sovereign data residency rules."""

    def __init__(self, master_service: MasterDataService | None = None) -> None:
        self._master_service = master_service or get_master_data_service()

    def evaluate_region(
        self,
        provider_code: str,
        region_name: str,
    ) -> GeographyComplianceResult:
        """Evaluates whether a cloud region complies with geographical governance."""
        geos = self._master_service.list_records("GEOGRAPHY")

        matched: MasterDataRecord | None = None
        for g in geos:
            regions_map = g.attributes.get("provider_regions", {})
            provider_list = regions_map.get(provider_code.lower(), [])
            if region_name.lower() in [r.lower() for r in provider_list]:
                matched = g
                break

        if not matched:
            return GeographyComplianceResult(
                provider_code=provider_code.upper(),
                region_name=region_name,
                geography_code=None,
                geography_name=None,
                jurisdiction="UNKNOWN",
                data_residency_classification="UNCLASSIFIED",
                is_approved_for_deployment=False,
                compliance_message=f"Region '{region_name}' ({provider_code}) is not mapped to any approved corporate geography.",
            )

        attrs = matched.attributes
        approved = attrs.get("is_approved_for_deployment", False)
        jurisdiction = attrs.get("jurisdiction", "INTERNATIONAL")
        residency = attrs.get("data_residency_classification", "STANDARD")

        msg = (
            f"Region '{region_name}' is approved under jurisdiction {jurisdiction} ({residency})."
            if approved
            else f"Region '{region_name}' is RESTRICTED: Deployment prohibited under policy."
        )

        return GeographyComplianceResult(
            provider_code=provider_code.upper(),
            region_name=region_name,
            geography_code=matched.code,
            geography_name=matched.display_name,
            jurisdiction=jurisdiction,
            data_residency_classification=residency,
            is_approved_for_deployment=approved,
            compliance_message=msg,
        )
