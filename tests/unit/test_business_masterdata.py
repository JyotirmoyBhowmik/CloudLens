"""Unit and contract tests for Business Master Data and domain engines (Prompt 46).

Verifies:
1. Budget allocation requires registered master entities (no free text).
2. Dynamic fiscal calendar recalculates period boundaries with zero code change.
3. Uploaded negotiated rates supersede list rates and are visibly labeled 'MANUAL'.
4. Holiday calendar suppresses schedule-adherence exceptions for that day.
5. Multi-currency conversion uses tenant FX presentation policy with rate/date display.
6. Tag policy enforces mandatory keys, allowed values, regex rules, and blocking postures.
7. Geography compliance verifies regional workloads against sovereign data residency.
8. API endpoints expose business master services cleanly.
"""

from datetime import date
from decimal import Decimal

import pytest
from starlette.testclient import TestClient

from api.cloudlens_api.main import app
from domain.models.exceptions import MasterDataException
from masterdata import (
    BudgetAllocationService,
    ContractRateEngine,
    CurrencyConverterEngine,
    FinancialCalendarEngine,
    GeographyComplianceEngine,
    MasterDataService,
    RuntimeScheduleAdherenceEngine,
    TagPolicyEngine,
    reset_master_data_service,
)


@pytest.fixture
def master_service() -> MasterDataService:
    reset_master_data_service()
    return MasterDataService(auto_seed=True)


@pytest.fixture
def client() -> TestClient:
    reset_master_data_service()
    return TestClient(app)


# ==============================================================================
# 1. Budget Allocation & Organization Masters
# ==============================================================================


def test_budget_creation_requires_registered_master_data(master_service: MasterDataService):
    """Acceptance 1: A budget can be created against a cost centre and a business unit

    that exist as master data, not as free text. Free text identifiers are prohibited.
    """
    svc = BudgetAllocationService(master_service)

    # 1. Valid budget creation against registered Cost Centre and linked Business Unit
    budget = svc.create_budget_allocation(
        tenant_id="tenant-global-finops",
        name="FY2026 Executive Cloud Budget",
        amount=Decimal("250000.00"),
        currency="USD",
        fiscal_year=2026,
        cost_centre_code="CC-1001",
        business_unit_code="BU_GLOBAL_CORP",
        created_by="finops_admin",
    )
    assert budget.id.startswith("bgt-tenant-g-cc-1001-2026")
    assert budget.cost_centre_code == "CC-1001"
    assert budget.cost_centre_name == "Executive Governance & Corporate Affairs"
    assert budget.business_unit_code == "BU_GLOBAL_CORP"
    assert budget.business_unit_name == "Global Corporate"
    assert budget.amount == Decimal("250000.00")

    # 2. Strict Rule: Free-text cost centre must be rejected
    with pytest.raises(MasterDataException) as exc_info:
        svc.create_budget_allocation(
            tenant_id="tenant-global-finops",
            name="Shadow IT Budget",
            amount=Decimal("10000.00"),
            currency="USD",
            fiscal_year=2026,
            cost_centre_code="FREE_TEXT_COST_CENTRE",
            business_unit_code="BU_GLOBAL_CORP",
            created_by="rogue_user",
        )
    assert "Free text identifiers are prohibited" in str(exc_info.value)
    assert "FREE_TEXT_COST_CENTRE" in str(exc_info.value)

    # 3. Strict Rule: Free-text business unit must be rejected
    with pytest.raises(MasterDataException) as exc_bu:
        svc.create_budget_allocation(
            tenant_id="tenant-global-finops",
            name="Shadow BU Budget",
            amount=Decimal("10000.00"),
            currency="USD",
            fiscal_year=2026,
            cost_centre_code="CC-1001",
            business_unit_code="FREE_TEXT_BU",
            created_by="rogue_user",
        )
    assert "Free text identifiers are prohibited" in str(exc_bu.value)
    assert "FREE_TEXT_BU" in str(exc_bu.value)

    # 4. Strict Rule: Cost centre and business unit linkage mismatch must be rejected
    # CC-1001 is mapped to BU_GLOBAL_CORP, not BU_RETAIL_BANKING
    with pytest.raises(MasterDataException) as exc_mismatch:
        svc.create_budget_allocation(
            tenant_id="tenant-global-finops",
            name="Mismatched Allocation",
            amount=Decimal("50000.00"),
            currency="USD",
            fiscal_year=2026,
            cost_centre_code="CC-1001",
            business_unit_code="BU_RETAIL_BANKING",
            created_by="finops_admin",
        )
    assert "mapped to Business Unit" in str(exc_mismatch.value)

    # 5. Invalid currency must be rejected
    with pytest.raises(MasterDataException) as exc_curr:
        svc.create_budget_allocation(
            tenant_id="tenant-global-finops",
            name="Bad Currency Budget",
            amount=Decimal("50000.00"),
            currency="BITCOIN_FAKE",
            fiscal_year=2026,
            cost_centre_code="CC-1001",
            business_unit_code="BU_GLOBAL_CORP",
            created_by="finops_admin",
        )
    assert "not a registered currency master" in str(exc_curr.value)


# ==============================================================================
# 2. Dynamic Financial Calendar Engine
# ==============================================================================


def test_dynamic_fiscal_year_period_boundary_recalculation(master_service: MasterDataService):
    """Acceptance 2: Changing the fiscal year start changes every period boundary

    across the product with no code change.
    """
    engine = FinancialCalendarEngine(master_service)

    # 1. Standard calendar starting in January (FC_STANDARD_JAN)
    jan_periods = engine.get_fiscal_periods("FC_STANDARD_JAN", 2026)
    assert len(jan_periods) == 12
    # Period 1 should be Jan 1 to Jan 31
    assert jan_periods[0].period_number == 1
    assert jan_periods[0].start_date == date(2026, 1, 1)
    assert jan_periods[0].end_date == date(2026, 1, 31)
    # Period 12 should be Dec 1 to Dec 31
    assert jan_periods[11].period_number == 12
    assert jan_periods[11].start_date == date(2026, 12, 1)
    assert jan_periods[11].end_date == date(2026, 12, 31)

    # 2. Commonwealth calendar starting in April (FC_APRIL_UK)
    uk_periods = engine.get_fiscal_periods("FC_APRIL_UK", 2026)
    assert len(uk_periods) == 12
    # Period 1 starts April 1, 2026
    assert uk_periods[0].period_number == 1
    assert uk_periods[0].start_date == date(2026, 4, 1)
    assert uk_periods[0].end_date == date(2026, 4, 30)
    # Period 12 ends March 31, 2027
    assert uk_periods[11].period_number == 12
    assert uk_periods[11].start_date == date(2027, 3, 1)
    assert uk_periods[11].end_date == date(2027, 3, 31)

    # 3. Dynamic test: Modify calendar start month in master data with ZERO CODE CHANGE
    cal = master_service.get_record("FISCAL_CALENDAR", "FC_STANDARD_JAN")
    assert cal is not None
    # Change fiscal year start to July (Month 7, Australian/NZ fiscal year style)
    updated_attrs = dict(cal.attributes)
    updated_attrs["fiscal_year_start_month"] = 7
    master_service.update_record(
        master_type="FISCAL_CALENDAR",
        code="FC_STANDARD_JAN",
        display_name=cal.display_name,
        attributes=updated_attrs,
        change_reason="Shift enterprise corporate fiscal year start to July 1",
        changed_by="corporate_treasury",
        force_publish=True,
    )

    # Verify boundaries shifted immediately with zero code changes
    recalculated_periods = engine.get_fiscal_periods("FC_STANDARD_JAN", 2026)
    assert len(recalculated_periods) == 12
    # Period 1 is now July 2026
    assert recalculated_periods[0].period_number == 1
    assert recalculated_periods[0].start_date == date(2026, 7, 1)
    assert recalculated_periods[0].end_date == date(2026, 7, 31)
    # Period 12 is now June 2027
    assert recalculated_periods[11].period_number == 12
    assert recalculated_periods[11].start_date == date(2027, 6, 1)
    assert recalculated_periods[11].end_date == date(2027, 6, 30)

    # 4. Period lookup for specific date
    p_lookup = engine.get_period_for_date("FC_APRIL_UK", date(2026, 5, 15))
    assert p_lookup.period_number == 2  # May is P2 for April fiscal year
    assert p_lookup.start_date == date(2026, 5, 1)


# ==============================================================================
# 3. Runtime Schedule Adherence & Holiday Suppression
# ==============================================================================


def test_holiday_calendar_suppresses_runtime_schedule_exceptions(
    master_service: MasterDataService,
):
    """Acceptance 4: A holiday in the holiday calendar suppresses a schedule-adherence

    exception for that day.
    """
    engine = RuntimeScheduleAdherenceEngine(master_service)

    # 1. Non-prod resource running on New Year's Day (2026-01-01 is a US Federal Holiday)
    new_years_day = date(2026, 1, 1)  # Thursday, holiday in HOL_US_FEDERAL
    res_holiday = engine.evaluate_schedule_adherence(
        resource_id="i-0abcd1234ef567890",
        environment_code="DEV",
        current_status="RUNNING",  # Would be an exception because non-prod is expected STOPPED
        check_date=new_years_day,
        location_code="LOC_US_EAST_VA",
    )
    assert res_holiday.is_holiday is True
    assert res_holiday.holiday_name == "New Year's Day"
    assert res_holiday.expected_status == "STOPPED"
    # Mandatory Acceptance: exception is suppressed!
    assert res_holiday.is_suppressed is True
    assert res_holiday.exception_detected is False
    assert "suppresses schedule-adherence exception" in (res_holiday.suppression_reason or "")

    # 2. Non-prod resource stopped on an ordinary working day (2026-09-02 Wednesday)
    normal_working_day = date(2026, 9, 2)
    res_workday = engine.evaluate_schedule_adherence(
        resource_id="i-0abcd1234ef567890",
        environment_code="DEV",
        current_status="STOPPED",  # Non-prod expected RUNNING on weekday daytime
        check_date=normal_working_day,
        location_code="LOC_US_EAST_VA",
    )
    assert res_workday.is_holiday is False
    assert res_workday.is_working_day is True
    assert res_workday.expected_status == "RUNNING"
    assert res_workday.is_suppressed is False
    assert res_workday.exception_detected is True  # Real exception detected

    # 3. Production environment: Always expected RUNNING, never suppressed by holiday
    res_prod = engine.evaluate_schedule_adherence(
        resource_id="i-prod-0998877",
        environment_code="PROD",
        current_status="STOPPED",  # Production stopped is a critical outage
        check_date=new_years_day,
        location_code="LOC_US_EAST_VA",
    )
    assert res_prod.is_production is True
    assert res_prod.expected_status == "RUNNING"
    assert res_prod.exception_detected is True
    assert res_prod.is_suppressed is False


# ==============================================================================
# 4. Contract Rate Engine & Explicit MANUAL Source Labeling
# ==============================================================================


def test_contracted_negotiated_rate_precedence_and_source_transparency(
    master_service: MasterDataService,
):
    """Acceptance 3: An uploaded negotiated rate supersedes the provider list rate

    and is visibly labelled as a manual-source rate.
    Rule: Do not let an uploaded rate be presented as provider-API-derived.
    """
    engine = ContractRateEngine(master_service)

    # 1. AWS EC2 m5.large has both list_rate (0.096) and contracted_rate (0.078)
    rate_result = engine.resolve_effective_rate(
        provider_code="AWS",
        service_code="AmazonEC2",
        sku_id="m5.large-us-east-1",
    )
    # Negotiated contracted rate must supersede list rate
    assert rate_result.is_contracted_rate is True
    assert rate_result.effective_rate == Decimal("0.078000")
    assert rate_result.list_rate == Decimal("0.096000")
    assert rate_result.contracted_rate == Decimal("0.078000")

    # Mandatory source label: Must be 'MANUAL', never 'PROVIDER_API'
    assert rate_result.rate_source == "MANUAL"
    assert "[Source: MANUAL]" in rate_result.rate_label
    assert rate_result.contract_reference == "AGR-2026-AWS-9872"

    # 2. Azure D4s_v5 has contracted rate (0.165 vs 0.192 list)
    azure_rate = engine.resolve_effective_rate(
        provider_code="AZURE",
        service_code="VirtualMachines",
        sku_id="standard-d4s-v5-eastus",
    )
    assert azure_rate.is_contracted_rate is True
    assert azure_rate.effective_rate == Decimal("0.165000")
    assert azure_rate.rate_source == "MANUAL"
    assert "[Source: MANUAL]" in azure_rate.rate_label

    # 3. GCP n2-standard-4 has NO contracted rate -> falls back to list rate
    gcp_rate = engine.resolve_effective_rate(
        provider_code="GCP",
        service_code="ComputeEngine",
        sku_id="n2-standard-4-us-central1",
    )
    assert gcp_rate.is_contracted_rate is False
    assert gcp_rate.effective_rate == Decimal("0.194800")
    assert gcp_rate.rate_source == "PROVIDER_API"
    assert "[Source: PROVIDER_API]" in gcp_rate.rate_label

    # 4. Unknown SKU raises MasterDataException
    with pytest.raises(MasterDataException):
        engine.resolve_effective_rate("AWS", "AmazonEC2", "non-existent-sku-xyz")


# ==============================================================================
# 5. Multi-Currency Conversion Driven by Tenant FX Policy
# ==============================================================================


def test_tenant_fx_presentation_policy_currency_conversion(
    master_service: MasterDataService,
):
    """Acceptance 5: Converting a cost to the reporting currency uses the rate type

    the tenant policy selects, and the rate and rate date are displayed.
    """
    engine = CurrencyConverterEngine(master_service)

    amount_eur = Decimal("1000.00")

    # 1. Budget variance context selects BUDGET_RATE (0.900000 USD/EUR)
    # EUR to USD via inverse rate (1.0 / 0.900000 = 1.111111 USD per EUR)
    res_bgt = engine.convert_cost(
        amount=amount_eur,
        from_currency="EUR",
        presentation_context="budget_variance",
    )
    assert res_bgt.rate_type == "BUDGET_RATE"
    assert res_bgt.reporting_currency == "USD"
    assert res_bgt.rate_date == "2026-01-01"
    assert res_bgt.rate_source == "TREASURY"
    # Converted amount: 1000 / 0.90 = 1111.11
    assert res_bgt.converted_amount == Decimal("1111.11")
    assert "BUDGET_RATE" in res_bgt.formatted_display

    # 2. Actual cost context selects MONTHLY_AVERAGE (0.920000 USD/EUR)
    # EUR to USD via inverse rate (1.0 / 0.920000 = 1.086957 USD per EUR)
    res_act = engine.convert_cost(
        amount=amount_eur,
        from_currency="EUR",
        presentation_context="actual_cost",
    )
    assert res_act.rate_type == "MONTHLY_AVERAGE"
    assert res_act.rate_date == "2026-09-01"
    # Converted amount: 1000 / 0.92 = 1086.96
    assert res_act.converted_amount == Decimal("1086.96")
    assert "MONTHLY_AVERAGE" in res_act.formatted_display

    # 3. Real-time alert context selects SPOT rate (0.925000 USD/EUR)
    # EUR to USD via inverse rate (1.0 / 0.925000 = 1.081081 USD per EUR)
    res_spot = engine.convert_cost(
        amount=amount_eur,
        from_currency="EUR",
        presentation_context="real_time_alert",
    )
    assert res_spot.rate_type == "SPOT"
    assert res_spot.converted_amount == Decimal("1081.08")
    assert "SPOT" in res_spot.formatted_display

    # 4. Identity conversion: USD to USD
    res_usd = engine.convert_cost(
        amount=Decimal("500.00"),
        from_currency="USD",
    )
    assert res_usd.rate_type == "IDENTITY"
    assert res_usd.rate_used == Decimal("1.000000")
    assert res_usd.converted_amount == Decimal("500.00")

    # 5. Missing rate raises clean domain exception
    with pytest.raises(MasterDataException) as exc_fx:
        engine.convert_cost(
            amount=Decimal("100.00"),
            from_currency="UNSUPPORTED_CURR",
            presentation_context="actual_cost",
        )
    assert "Exchange rate not found" in str(exc_fx.value)


# ==============================================================================
# 6. Tag Policy Enforcement Postures
# ==============================================================================


def test_tag_policy_validation_and_enforcement_postures(
    master_service: MasterDataService,
):
    """Item 20: Validates resource tags against corporate policies and posture levels."""
    engine = TagPolicyEngine(master_service)

    # 1. Fully compliant tags
    compliant_tags = {
        "Environment": "Production",
        "Application": "CloudLens",
        "CostCentre": "CC-1001",
        "Owner": "finops@enterprise.corp",
    }
    report = engine.evaluate_tags(compliant_tags, "TAG_POL_ENTERPRISE_MANDATORY")
    assert report.is_compliant is True
    assert len(report.missing_mandatory_keys) == 0
    assert len(report.invalid_value_keys) == 0
    assert len(report.regex_format_violations) == 0
    assert report.should_block_operation is False

    # 2. Missing mandatory tags & invalid enum value
    bad_tags = {
        "Environment": "ExperimentalSandbox",  # Not in allowed values
        "CostCentre": "INVALID_CC_FORMAT",  # Fails CC-[0-9]{4} regex
        # Missing 'Application' and 'Owner'
    }
    report_bad = engine.evaluate_tags(bad_tags, "TAG_POL_ENTERPRISE_MANDATORY")
    assert report_bad.is_compliant is False
    assert "Application" in report_bad.missing_mandatory_keys
    assert "Owner" in report_bad.missing_mandatory_keys
    assert "Environment" in report_bad.invalid_value_keys
    assert "CostCentre" in report_bad.regex_format_violations
    # Posture is EXCEPTION, so does not block operation
    assert report_bad.enforcement_posture == "EXCEPTION"
    assert report_bad.should_block_operation is False

    # 3. BLOCK_AT_POLICY posture blocks operation when non-compliant
    report_block = engine.evaluate_tags(
        {"Environment": "Staging"},  # Only Production is allowed in production-strict policy
        "TAG_POL_PRODUCTION_STRICT",
    )
    assert report_block.is_compliant is False
    assert report_block.enforcement_posture == "BLOCK_AT_POLICY"
    assert report_block.should_block_operation is True


# ==============================================================================
# 7. Geography & Sovereign Data Residency Compliance
# ==============================================================================


def test_geography_sovereignty_and_data_residency_compliance(
    master_service: MasterDataService,
):
    """Item 21: Evaluates regional cloud placements against sovereign jurisdiction rules."""
    engine = GeographyComplianceEngine(master_service)

    # 1. US East (Approved, FEDRAMP_HIGH)
    res_us = engine.evaluate_region("AWS", "us-east-1")
    assert res_us.is_approved_for_deployment is True
    assert res_us.jurisdiction == "US"
    assert res_us.data_residency_classification == "FEDRAMP_HIGH"
    assert res_us.geography_code == "GEO_US_EAST"

    # 2. EU Central / Frankfurt (Approved, GDPR_RESTRICTED)
    res_eu = engine.evaluate_region("AZURE", "germanywestcentral")
    assert res_eu.is_approved_for_deployment is True
    assert res_eu.jurisdiction == "EU"
    assert res_eu.data_residency_classification == "GDPR_RESTRICTED"
    assert res_eu.geography_code == "GEO_EU_CENTRAL"

    # 3. Restricted offshore region (Blocked under corporate policy)
    res_restricted = engine.evaluate_region("AWS", "cn-north-1")
    assert res_restricted.is_approved_for_deployment is False
    assert res_restricted.geography_code == "GEO_UNAPPROVED_RESTRICTED"
    assert "RESTRICTED: Deployment prohibited" in res_restricted.compliance_message

    # 4. Unmapped region (Flagged unclassified and unapproved)
    res_unknown = engine.evaluate_region("AWS", "ap-nonexistent-99")
    assert res_unknown.is_approved_for_deployment is False
    assert res_unknown.jurisdiction == "UNKNOWN"
    assert res_unknown.data_residency_classification == "UNCLASSIFIED"


# ==============================================================================
# 8. Business Master REST API Endpoints
# ==============================================================================


def test_business_masterdata_rest_api_endpoints(client: TestClient):
    """Tests all REST endpoints dedicated to business master data operations."""
    # 1. POST /api/v1/masterdata/budgets/validate (Success)
    valid_budget_payload = {
        "tenant_id": "tenant-corp-test",
        "name": "Cloud Core Budget",
        "amount": 75000.00,
        "currency": "USD",
        "fiscal_year": 2026,
        "cost_centre_code": "CC-1001",
        "business_unit_code": "BU_GLOBAL_CORP",
    }
    res_bgt = client.post("/api/v1/masterdata/budgets/validate", json=valid_budget_payload)
    assert res_bgt.status_code == 200
    bgt_data = res_bgt.json()
    assert bgt_data["cost_centre_code"] == "CC-1001"
    assert bgt_data["business_unit_code"] == "BU_GLOBAL_CORP"

    # 2. POST /api/v1/masterdata/budgets/validate (Failure - Free text rejected)
    bad_budget_payload = dict(valid_budget_payload)
    bad_budget_payload["cost_centre_code"] = "FREE_TEXT_CC"
    res_bgt_fail = client.post("/api/v1/masterdata/budgets/validate", json=bad_budget_payload)
    assert res_bgt_fail.status_code == 400
    err_body = res_bgt_fail.json()
    err_msg = err_body.get("message") or err_body.get("detail", "")
    assert "Free text identifiers are prohibited" in err_msg

    # 3. GET /api/v1/masterdata/calendar/fiscal-periods
    res_cal = client.get(
        "/api/v1/masterdata/calendar/fiscal-periods?calendar_code=FC_STANDARD_JAN&fiscal_year=2026"
    )
    assert res_cal.status_code == 200
    periods = res_cal.json()
    assert len(periods) == 12
    assert periods[0]["period_number"] == 1
    assert periods[0]["start_date"] == "2026-01-01"

    # 4. POST /api/v1/masterdata/schedule-adherence/evaluate (Holiday suppression)
    res_adh = client.post(
        "/api/v1/masterdata/schedule-adherence/evaluate",
        json={
            "resource_id": "vm-dev-01",
            "environment_code": "DEV",
            "current_status": "RUNNING",
            "check_date": "2026-01-01",
            "location_code": "LOC_US_EAST_VA",
        },
    )
    assert res_adh.status_code == 200
    adh_data = res_adh.json()
    assert adh_data["is_holiday"] is True
    assert adh_data["is_suppressed"] is True
    assert adh_data["exception_detected"] is False

    # 5. POST /api/v1/masterdata/currency/convert
    res_fx = client.post(
        "/api/v1/masterdata/currency/convert",
        json={
            "amount": 1000.00,
            "from_currency": "EUR",
            "presentation_context": "actual_cost",
        },
    )
    assert res_fx.status_code == 200
    fx_data = res_fx.json()
    assert fx_data["rate_type"] == "MONTHLY_AVERAGE"
    assert fx_data["reporting_currency"] == "USD"
    assert float(fx_data["converted_amount"]) == 1086.96

    # 6. GET /api/v1/masterdata/rate-cards/effective-rate
    res_rc = client.get(
        "/api/v1/masterdata/rate-cards/effective-rate?provider_code=AWS&service_code=AmazonEC2&sku_id=m5.large-us-east-1"
    )
    assert res_rc.status_code == 200
    rc_data = res_rc.json()
    assert rc_data["is_contracted_rate"] is True
    assert rc_data["rate_source"] == "MANUAL"
    assert "[Source: MANUAL]" in rc_data["rate_label"]

    # 7. POST /api/v1/masterdata/tag-policy/evaluate
    res_tag = client.post(
        "/api/v1/masterdata/tag-policy/evaluate",
        json={
            "tags": {
                "Environment": "Production",
                "Application": "CloudLens",
                "CostCentre": "CC-1001",
                "Owner": "finops@enterprise.corp",
            },
            "policy_code": "TAG_POL_ENTERPRISE_MANDATORY",
        },
    )
    assert res_tag.status_code == 200
    assert res_tag.json()["is_compliant"] is True

    # 8. GET /api/v1/masterdata/geography/compliance
    res_geo = client.get(
        "/api/v1/masterdata/geography/compliance?provider_code=AWS&region_name=us-east-1"
    )
    assert res_geo.status_code == 200
    geo_data = res_geo.json()
    assert geo_data["is_approved_for_deployment"] is True
    assert geo_data["jurisdiction"] == "US"
