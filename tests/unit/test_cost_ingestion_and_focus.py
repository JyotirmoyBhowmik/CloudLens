"""Comprehensive Unit Tests for FOCUS Cost Ingestion, Normalisation, Restatement, and Currency (Prompt 22).

Enforces:
- CST-001, CST-002, CST-003, CST-004, CST-008, CST-012, FR-802, FR-803.
- Idempotent bulk cost ingestion with atomic partition replacement (no duplication on re-ingest).
- Per-provider FOCUS mapping retaining all four cost measures: billed, effective, list, contracted.
- Restatement detection, flagging (is_restated=True), and prior values retention.
- Charge categorisation preventing reservation purchases or credits from masquerading as usage.
- Commitment & discount handling (BILLED vs AMORTISED basis, realised discount value).
- Query-time currency conversion with mandatory disclosure text (never converted in fact).
- Schema-version guard halting on unrecognised schemas.
- 4-step drill-through hierarchy governed by financial-detail RBAC.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from api.cloudlens_api.main import app
from domain.cost.currency_service import (
    get_currency_service,
    reset_currency_service,
)
from domain.cost.focus_mapper import FocusMapper
from domain.cost.models import CostPresentationBasis
from domain.cost.pipeline import (
    get_cost_pipeline,
    reset_cost_pipeline,
)
from domain.cost.repository import (
    get_cost_repository,
    reset_cost_repository,
)
from domain.cost.schema_guard import SchemaVersionGuard
from domain.models.enums import ChargeCategory, ServiceCategory
from domain.models.exceptions import (
    CurrencyConversionException,
    FinancialDetailAccessDeniedException,
    UnknownSchemaVersionException,
)
from domain.tenant.context import TenantContext


@pytest.fixture(autouse=True)
def reset_singletons():
    """Resets all singletons before and after each test."""
    reset_cost_repository()
    reset_cost_pipeline()
    reset_currency_service()
    yield
    reset_cost_repository()
    reset_cost_pipeline()
    reset_currency_service()


@pytest.fixture
def tenant_context() -> TenantContext:
    """Standard authenticated tenant context for FinOps testing."""
    return TenantContext(
        tenant_id="tenant-finops-omega",
        user_id="finops-admin@acme.com",
        email="finops-admin@acme.com",
        roles=["FinOpsAdmin", "FinancialDetailViewer"],
    )


@pytest.fixture
def test_client() -> TestClient:
    """FastAPI TestClient instance."""
    return TestClient(app)


# ==============================================================================
# 1. Schema Version Guard Tests (Prompt 22 Item 7)
# ==============================================================================


def test_schema_guard_valid_schemas():
    """Verifies that all supported FOCUS and provider-native schemas pass validation."""
    valid_pairs = [
        ("aws", "aws_cur_2_0"),
        ("aws", "aws_focus_1_0"),
        ("azure", "azure_cost_details_v2"),
        ("azure", "azure_cost_details_focus_1_0"),
        ("gcp", "gcp_billing_export_resource_v1"),
        ("gcp", "gcp_billing_focus_1_0"),
        ("oci", "oci_cost_report_v1"),
        ("oci", "oci_focus_1_0"),
    ]
    for provider, schema in valid_pairs:
        assert SchemaVersionGuard.is_supported(provider, schema) is True
        # Must not raise
        SchemaVersionGuard.validate_schema(provider, schema)


def test_schema_guard_unknown_schema_halts_and_raises():
    """Prompt 22 Item 7: Unknown dataset schema halts job and raises alert rather than guessing."""
    with pytest.raises(UnknownSchemaVersionException) as exc_info:
        SchemaVersionGuard.validate_schema("aws", "aws_unknown_legacy_csv_v0")
    assert "Unknown or unsupported" in exc_info.value.message

    with pytest.raises(UnknownSchemaVersionException):
        SchemaVersionGuard.validate_schema("invalid_cloud", "aws_focus_1_0")


# ==============================================================================
# 2. FOCUS Normalisation & 4 Cost Measures Tests (Prompt 22 Item 2)
# ==============================================================================


def test_focus_mapper_native_focus_1_0():
    """Verifies 1:1 mapping of native FOCUS datasets, retaining all 4 cost measures."""
    raw_records = [
        {
            "ChargePeriodStart": "2026-03-01T00:00:00Z",
            "ChargePeriodEnd": "2026-03-01T23:59:59Z",
            "BillingPeriodStart": "2026-03-01T00:00:00Z",
            "BillingPeriodEnd": "2026-03-31T23:59:59Z",
            "BilledCost": 120.50,
            "EffectiveCost": 96.40,
            "ListCost": 150.00,
            "ContractedCost": 120.50,
            "BillingCurrency": "USD",
            "ServiceName": "Amazon Elastic Compute Cloud",
            "ServiceCategory": "Compute",
            "ChargeCategory": "Usage",
            "ResourceId": "i-0a1b2c3d4e5f67890",
            "RegionId": "us-east-1",
            "CommitmentId": "sp-12345678",
            "CommitmentType": "SavingsPlan",
        }
    ]

    facts = FocusMapper.map_dataset(
        raw_records=raw_records,
        provider="aws",
        schema_version="aws_focus_1_0",
        tenant_id="tenant-finops-omega",
        scope_id="acc-production",
    )

    assert len(facts) == 1
    f = facts[0]
    assert f.provider == "aws"
    assert f.service_id == "Amazon Elastic Compute Cloud"
    assert f.service_category == ServiceCategory.COMPUTE
    assert f.charge_category == ChargeCategory.USAGE

    # Retain all four cost measures
    assert f.billed_cost.value == Decimal("120.50")
    assert f.effective_cost.value == Decimal("96.40")
    assert f.list_cost is not None and f.list_cost.value == Decimal("150.00")
    assert f.contracted_cost is not None and f.contracted_cost.value == Decimal("120.50")

    # Realised discount value computed as value (ListCost - EffectiveCost = 150.00 - 96.40 = 53.60)
    assert f.realised_discount_value is not None
    assert f.realised_discount_value.value == Decimal("53.60")

    # Native billing currency preserved without in-fact conversion
    assert f.billing_currency == "USD"
    assert f.currency == "USD"
    assert f.commitment_id == "sp-12345678"


def test_focus_mapper_aws_cur_2_0_normalisation():
    """Verifies normalisation of AWS CUR 2.0 dataset into canonical FOCUS facts."""
    raw_records = [
        {
            "lineItem/UsageStartDate": "2026-03-01T00:00:00Z",
            "lineItem/UsageEndDate": "2026-03-01T01:00:00Z",
            "bill/BillingPeriodStartDate": "2026-03-01T00:00:00Z",
            "bill/BillingPeriodEndDate": "2026-03-31T23:59:59Z",
            "lineItem/ProductCode": "AmazonEC2",
            "lineItem/UnblendedCost": "10.00",
            "lineItem/NetUnblendedCost": "8.50",
            "lineItem/LineItemType": "Usage",
            "lineItem/ResourceId": "arn:aws:ec2:us-east-1:123456789012:instance/i-123",
            "product/region": "us-east-1",
            "pricing/publicOnDemandCost": "12.00",
            "lineItem/CurrencyCode": "USD",
        }
    ]

    facts = FocusMapper.map_dataset(
        raw_records=raw_records,
        provider="aws",
        schema_version="aws_cur_2_0",
        tenant_id="tenant-finops-omega",
        scope_id="acc-production",
    )

    assert len(facts) == 1
    f = facts[0]
    assert f.service_id == "AmazonEC2"
    assert f.service_category == ServiceCategory.COMPUTE
    assert f.charge_category == ChargeCategory.USAGE
    assert f.billed_cost.value == Decimal("10.00")
    assert f.effective_cost.value == Decimal("8.50")
    assert f.list_cost is not None and f.list_cost.value == Decimal("12.00")
    assert f.realised_discount_value is not None and f.realised_discount_value.value == Decimal(
        "3.50"
    )


def test_focus_mapper_azure_cost_details_v2():
    """Verifies normalisation of Azure Cost Details v2 dataset."""
    raw_records = [
        {
            "date": "2026-03-05T00:00:00Z",
            "billingPeriodStartDate": "2026-03-01T00:00:00Z",
            "billingPeriodEndDate": "2026-03-31T23:59:59Z",
            "meterCategory": "Virtual Machines",
            "costInBillingCurrency": "45.20",
            "paygCostInBillingCurrency": "55.00",
            "chargeType": "Usage",
            "resourceId": "/subscriptions/sub-1/resourceGroups/rg-1/providers/Microsoft.Compute/virtualMachines/vm-prod",
            "resourceLocation": "eastus",
            "billingCurrency": "EUR",
        }
    ]

    facts = FocusMapper.map_dataset(
        raw_records=raw_records,
        provider="azure",
        schema_version="azure_cost_details_v2",
        tenant_id="tenant-finops-omega",
        scope_id="sub-1",
    )

    assert len(facts) == 1
    f = facts[0]
    assert f.service_category == ServiceCategory.COMPUTE
    assert f.billed_cost.value == Decimal("45.20")
    assert f.billing_currency == "EUR"
    assert f.list_cost is not None and f.list_cost.value == Decimal("55.00")


def test_focus_mapper_gcp_bigquery_export():
    """Verifies normalisation of GCP BigQuery detailed billing export records."""
    raw_records = [
        {
            "usage_start_time": "2026-03-01T00:00:00Z",
            "usage_end_time": "2026-03-01T01:00:00Z",
            "service": {"description": "Compute Engine"},
            "cost": 15.25,
            "currency": "USD",
            "usage": {"amount": 1.0, "unit": "hours"},
            "credits": [{"type": "SUSTAINED_USAGE_DISCOUNT", "amount": -2.25}],
            "project": {"id": "proj-analytics-prod"},
            "resource": {"name": "gce-instance-01"},
            "location": {"region": "us-central1"},
        }
    ]

    facts = FocusMapper.map_dataset(
        raw_records=raw_records,
        provider="gcp",
        schema_version="gcp_billing_export_resource_v1",
        tenant_id="tenant-finops-omega",
        scope_id="proj-analytics-prod",
    )

    assert len(facts) == 1
    f = facts[0]
    assert f.provider == "gcp"
    assert f.service_category == ServiceCategory.COMPUTE
    assert f.charge_category == ChargeCategory.USAGE
    assert f.billed_cost.value == Decimal("15.25")
    # Effective cost reflects credit deduction (15.25 - 2.25 = 13.00)
    assert f.effective_cost.value == Decimal("13.00")
    assert f.list_cost is not None and f.list_cost.value == Decimal("15.25")
    assert f.realised_discount_value is not None and f.realised_discount_value.value == Decimal(
        "2.25"
    )


def test_focus_mapper_oci_cost_reports():
    """Verifies normalisation of OCI Cost and Usage Reports (v1)."""
    raw_records = [
        {
            "lineItem/intervalUsageStart": "2026-03-01T00:00:00Z",
            "lineItem/intervalUsageEnd": "2026-03-01T01:00:00Z",
            "product/service": "Compute",
            "product/description": "VM.Standard2.1",
            "cost/myCost": "8.40",
            "cost/currency": "USD",
            "usage/billedQuantity": "1.0",
            "usage/unit": "Hours",
            "lineItem/reference": "ocid1.instance.oc1..test",
            "lineItem/type": "Usage",
        }
    ]

    facts = FocusMapper.map_dataset(
        raw_records=raw_records,
        provider="oci",
        schema_version="oci_cost_report_v1",
        tenant_id="tenant-finops-omega",
        scope_id="ocid1.compartment.oc1..test",
    )

    assert len(facts) == 1
    f = facts[0]
    assert f.provider == "oci"
    assert f.service_category == ServiceCategory.COMPUTE
    assert f.charge_category == ChargeCategory.USAGE
    assert f.billed_cost.value == Decimal("8.40")
    assert f.effective_cost.value == Decimal("8.40")
    assert f.billing_currency == "USD"


# ==============================================================================
# 3. Charge Categorisation (Prompt 22 Item 4)
# ==============================================================================


def test_charge_categorisation_purchase_not_usage_spike():
    """Prompt 22 Item 4: Upfront reservation purchase must appear as PURCHASE, not a usage spike."""
    raw_records = [
        {
            "ChargePeriodStart": "2026-03-01T00:00:00Z",
            "ChargePeriodEnd": "2026-03-01T23:59:59Z",
            "BilledCost": 5000.00,
            "EffectiveCost": 5000.00,
            "ServiceName": "AmazonEC2",
            "ChargeCategory": "Purchase",
            "ChargeDescription": "All Upfront 3-Year Standard RI Purchase",
            "CommitmentType": "ReservedInstance",
        },
        {
            "ChargePeriodStart": "2026-03-01T00:00:00Z",
            "ChargePeriodEnd": "2026-03-01T23:59:59Z",
            "BilledCost": 25.00,
            "EffectiveCost": 25.00,
            "ServiceName": "AmazonEC2",
            "ChargeCategory": "Usage",
            "ChargeDescription": "On-demand box usage",
        },
    ]

    facts = FocusMapper.map_dataset(
        raw_records=raw_records,
        provider="aws",
        schema_version="aws_focus_1_0",
        tenant_id="tenant-finops-omega",
        scope_id="acc-production",
    )

    assert len(facts) == 2
    ri_fact = next(f for f in facts if f.charge_category == ChargeCategory.PURCHASE)
    usage_fact = next(f for f in facts if f.charge_category == ChargeCategory.USAGE)

    assert ri_fact.charge_category == ChargeCategory.PURCHASE
    assert ri_fact.billed_cost.value == Decimal("5000.00")
    assert usage_fact.charge_category == ChargeCategory.USAGE
    assert usage_fact.billed_cost.value == Decimal("25.00")


def test_charge_categorisation_credits_never_netted_into_usage():
    """Prompt 22 Item 4: Negative charges and credits are never silently netted into usage."""
    raw_records = [
        {
            "ChargePeriodStart": "2026-03-01T00:00:00Z",
            "ChargePeriodEnd": "2026-03-01T23:59:59Z",
            "BilledCost": -150.00,
            "EffectiveCost": -150.00,
            "ServiceName": "AmazonS3",
            "ChargeCategory": "Credit",
            "ChargeDescription": "Enterprise promotional credit",
        }
    ]

    facts = FocusMapper.map_dataset(
        raw_records=raw_records,
        provider="aws",
        schema_version="aws_focus_1_0",
        tenant_id="tenant-finops-omega",
        scope_id="acc-production",
    )

    assert len(facts) == 1
    credit_fact = facts[0]
    assert credit_fact.charge_category == ChargeCategory.CREDIT
    assert credit_fact.billed_cost.value == Decimal("-150.00")


# ==============================================================================
# 4. Atomic Partition Replacement & Idempotency (Prompt 22 Item 1 & Acceptance)
# ==============================================================================


def test_idempotent_reingestion_no_duplication(tenant_context: TenantContext):
    """Prompt 22 Acceptance: Re-ingesting a period with identical data produces identical totals with no duplication."""
    pipeline = get_cost_pipeline()
    repository = get_cost_repository()

    dataset = [
        {
            "ChargePeriodStart": "2026-03-01T00:00:00Z",
            "ChargePeriodEnd": "2026-03-01T23:59:59Z",
            "BillingPeriodStart": "2026-03-01T00:00:00Z",
            "BillingPeriodEnd": "2026-03-31T23:59:59Z",
            "BilledCost": 100.00,
            "EffectiveCost": 100.00,
            "ServiceName": "AmazonEC2",
            "ResourceId": "i-test-1",
        },
        {
            "ChargePeriodStart": "2026-03-01T00:00:00Z",
            "ChargePeriodEnd": "2026-03-01T23:59:59Z",
            "BillingPeriodStart": "2026-03-01T00:00:00Z",
            "BillingPeriodEnd": "2026-03-31T23:59:59Z",
            "BilledCost": 50.00,
            "EffectiveCost": 50.00,
            "ServiceName": "AmazonS3",
            "ResourceId": "bucket-test-1",
        },
    ]

    # Ingestion 1
    res1 = pipeline.execute_bulk_ingestion(
        dataset=dataset,
        provider="aws",
        schema_version="aws_focus_1_0",
        scope_id="acc-prod",
        tenant_context=tenant_context,
    )
    assert res1.rows_ingested == 2
    assert res1.is_restatement_detected is False

    totals1 = repository.get_period_totals("2026-03", tenant_context=tenant_context)
    assert totals1["billed_cost"] == Decimal("150.00")
    assert totals1["row_count"] == Decimal(2)

    # Ingestion 2 (Identical dataset re-ingested)
    res2 = pipeline.execute_bulk_ingestion(
        dataset=dataset,
        provider="aws",
        schema_version="aws_focus_1_0",
        scope_id="acc-prod",
        tenant_context=tenant_context,
    )
    assert res2.rows_ingested == 2
    assert res2.is_restatement_detected is False

    totals2 = repository.get_period_totals("2026-03", tenant_context=tenant_context)
    # Totals and row counts must remain identical with ZERO duplicates
    assert totals2["billed_cost"] == Decimal("150.00")
    assert totals2["row_count"] == Decimal(2)


# ==============================================================================
# 5. Restatement Detection & Audit Trail (Prompt 22 Item 3 & Acceptance)
# ==============================================================================


def test_restatement_detection_retention_and_audit(tenant_context: TenantContext):
    """Prompt 22 Acceptance: Restatement is flagged and both original and restated values are retrievable."""
    pipeline = get_cost_pipeline()
    repository = get_cost_repository()

    initial_dataset = [
        {
            "ChargePeriodStart": "2026-03-01T00:00:00Z",
            "ChargePeriodEnd": "2026-03-01T23:59:59Z",
            "BillingPeriodStart": "2026-03-01T00:00:00Z",
            "BillingPeriodEnd": "2026-03-31T23:59:59Z",
            "BilledCost": 200.00,
            "EffectiveCost": 180.00,
            "ServiceName": "AmazonEC2",
            "ResourceId": "i-restatement-test",
        }
    ]

    # Initial ingestion
    res_initial = pipeline.execute_bulk_ingestion(
        dataset=initial_dataset,
        provider="aws",
        schema_version="aws_focus_1_0",
        scope_id="acc-prod",
        tenant_context=tenant_context,
    )
    assert res_initial.is_restatement_detected is False

    # Restated dataset with retroactive provider changes (cost updated from 200 to 240)
    restated_dataset = [
        {
            "ChargePeriodStart": "2026-03-01T00:00:00Z",
            "ChargePeriodEnd": "2026-03-01T23:59:59Z",
            "BillingPeriodStart": "2026-03-01T00:00:00Z",
            "BillingPeriodEnd": "2026-03-31T23:59:59Z",
            "BilledCost": 240.00,
            "EffectiveCost": 210.00,
            "ServiceName": "AmazonEC2",
            "ResourceId": "i-restatement-test",
        }
    ]

    res_restated = pipeline.execute_bulk_ingestion(
        dataset=restated_dataset,
        provider="aws",
        schema_version="aws_focus_1_0",
        scope_id="acc-prod",
        tenant_context=tenant_context,
    )
    assert res_restated.is_restatement_detected is True
    assert len(res_restated.restatement_records) == 1

    restatement_record = res_restated.restatement_records[0]
    assert restatement_record.billing_period == "2026-03"
    assert restatement_record.original_billed_total == Decimal("200.00")
    assert restatement_record.restated_billed_total == Decimal("240.00")
    assert restatement_record.billed_delta == Decimal("40.00")
    assert restatement_record.effective_delta == Decimal("30.00")

    # Verify new active partition rows are marked restated with prior values
    current_facts = repository.get_all_facts(
        tenant_context=tenant_context, billing_period="2026-03"
    )
    assert len(current_facts) == 1
    cf = current_facts[0]
    assert cf.is_restated is True
    assert cf.restatement_version == 2
    assert cf.billed_cost.value == Decimal("240.00")
    assert cf.prior_billed_cost is not None and cf.prior_billed_cost.value == Decimal("200.00")

    # Verify superseded partition is preserved and original values are retrievable
    historical_facts = repository.get_historical_partition(
        billing_period="2026-03", version=1, tenant_context=tenant_context
    )
    assert len(historical_facts) == 1
    assert historical_facts[0].billed_cost.value == Decimal("200.00")
    assert historical_facts[0].is_restated is False


# ==============================================================================
# 6. Currency Conversion at Query Time (Prompt 22 Item 6 & Acceptance)
# ==============================================================================


def test_currency_conversion_at_query_time_with_disclosure():
    """Prompt 22 Acceptance: Cost is stored in native currency and converted only at query time with rate and date displayed."""
    svc = get_currency_service()

    # Convert USD 100 to EUR
    converted = svc.convert_at_query_time(
        amount=Decimal("100.00"),
        from_currency="USD",
        to_currency="EUR",
        presentation_basis=CostPresentationBasis.BILLED,
    )

    assert converted.original_amount == Decimal("100.00")
    assert converted.original_currency == "USD"
    assert converted.target_currency == "EUR"
    assert converted.exchange_rate == Decimal("0.9250")
    assert converted.target_amount == Decimal("92.50")
    assert converted.rate_effective_date == date(2026, 3, 1)
    assert converted.presentation_basis == CostPresentationBasis.BILLED

    # Mandatory disclosure sentence
    assert "Converted from 100.00 USD to 92.50 EUR" in converted.disclosure
    assert "effective rate 0.9250 as of 2026-03-01" in converted.disclosure
    assert "ECB_DAILY_REFERENCE" in converted.disclosure


def test_currency_conversion_same_currency():
    """Query-time conversion with identical source and target currency returns rate 1.0 with no conversion fee."""
    svc = get_currency_service()
    res = svc.convert_at_query_time(
        amount=Decimal("250.75"),
        from_currency="USD",
        to_currency="USD",
    )
    assert res.target_amount == Decimal("250.75")
    assert res.exchange_rate == Decimal("1.0")


def test_currency_conversion_unsupported_rate_raises():
    """Attempting conversion with an unrecognised currency pair raises CurrencyConversionException."""
    svc = get_currency_service()
    with pytest.raises(CurrencyConversionException):
        svc.convert_at_query_time(
            amount=Decimal("100.00"),
            from_currency="USD",
            to_currency="XYZ",
        )


# ==============================================================================
# 7. Drill-Through Hierarchy & Financial Detail RBAC (Prompt 22 Item 8 & Acceptance)
# ==============================================================================


def test_drill_through_4_steps_and_rbac(tenant_context: TenantContext):
    """Prompt 22 Acceptance: 4-step drill-down reaches contributing charge lines; RBAC enforced."""
    repo = get_cost_repository()
    pipeline = get_cost_pipeline()

    dataset = [
        {
            "ChargePeriodStart": "2026-03-01T00:00:00Z",
            "ChargePeriodEnd": "2026-03-01T23:59:59Z",
            "BillingPeriodStart": "2026-03-01T00:00:00Z",
            "BillingPeriodEnd": "2026-03-31T23:59:59Z",
            "BilledCost": 300.00,
            "EffectiveCost": 270.00,
            "ServiceName": "AmazonEC2",
            "ChargeCategory": "Usage",
            "ResourceId": "i-compute-alpha",
        },
        {
            "ChargePeriodStart": "2026-03-01T00:00:00Z",
            "ChargePeriodEnd": "2026-03-01T23:59:59Z",
            "BillingPeriodStart": "2026-03-01T00:00:00Z",
            "BillingPeriodEnd": "2026-03-31T23:59:59Z",
            "BilledCost": 150.00,
            "EffectiveCost": 150.00,
            "ServiceName": "AmazonEC2",
            "ChargeCategory": "Purchase",
            "ResourceId": "ri-purchase-beta",
        },
    ]

    pipeline.execute_bulk_ingestion(
        dataset=dataset,
        provider="aws",
        schema_version="aws_focus_1_0",
        scope_id="acc-prod",
        tenant_context=tenant_context,
    )

    # Step 1: Level 1 (Scope Aggregate)
    node1 = repo.drill_down(tenant_context=tenant_context)
    assert node1.level == 1
    assert node1.billed_cost == Decimal("450.00")
    assert len(node1.children) >= 1
    assert node1.children[0].dimension_value == "acc-prod"

    # Step 2: Level 2 (Service Aggregate within Scope)
    node2 = repo.drill_down(tenant_context=tenant_context, scope_id="acc-prod")
    assert node2.level == 2
    assert node2.billed_cost == Decimal("450.00")
    assert any(c.dimension_value == "AmazonEC2" for c in node2.children)

    # Step 3: Level 3 (ChargeCategory Aggregate within Service)
    node3 = repo.drill_down(
        tenant_context=tenant_context,
        scope_id="acc-prod",
        service_id="AmazonEC2",
    )
    assert node3.level == 3
    assert any(c.dimension_value == ChargeCategory.USAGE.value for c in node3.children)
    assert any(c.dimension_value == ChargeCategory.PURCHASE.value for c in node3.children)

    # Step 4: Level 4 with financial permission -> returns raw charge lines
    node4 = repo.drill_down(
        tenant_context=tenant_context,
        scope_id="acc-prod",
        service_id="AmazonEC2",
        charge_category=ChargeCategory.USAGE,
        has_financial_permission=True,
    )
    assert node4.level == 4
    assert node4.billed_cost == Decimal("300.00")
    assert len(node4.charge_lines) == 1
    assert node4.charge_lines[0].resource_id == "i-compute-alpha"

    # Step 4: Level 4 WITHOUT financial permission -> MUST raise FinancialDetailAccessDeniedException
    with pytest.raises(FinancialDetailAccessDeniedException):
        repo.drill_down(
            tenant_context=tenant_context,
            scope_id="acc-prod",
            service_id="AmazonEC2",
            charge_category=ChargeCategory.USAGE,
            has_financial_permission=False,
        )


# ==============================================================================
# 8. API Integration Tests (FastAPI routes)
# ==============================================================================


def test_api_cost_ingest_and_summary(test_client: TestClient):
    """Verifies end-to-end API ingestion, summary calculation, and query-time currency conversion."""
    headers = {"X-Tenant-ID": "tenant-api-test"}

    ingest_payload = {
        "provider": "aws",
        "schema_version": "aws_focus_1_0",
        "scope_id": "acc-api-101",
        "lookback_window_months": 3,
        "records": [
            {
                "ChargePeriodStart": "2026-03-01T00:00:00Z",
                "ChargePeriodEnd": "2026-03-01T23:59:59Z",
                "BillingPeriodStart": "2026-03-01T00:00:00Z",
                "BillingPeriodEnd": "2026-03-31T23:59:59Z",
                "BilledCost": 500.00,
                "EffectiveCost": 450.00,
                "ListCost": 600.00,
                "ContractedCost": 500.00,
                "ServiceName": "AmazonEC2",
                "ChargeCategory": "Usage",
                "ResourceId": "i-api-test-vm",
            }
        ],
    }

    # 1. POST /api/v1/cost/ingest
    res_ingest = test_client.post("/api/v1/cost/ingest", json=ingest_payload, headers=headers)
    assert res_ingest.status_code == 201
    ingest_data = res_ingest.json()
    assert ingest_data["rows_ingested"] == 1
    assert ingest_data["is_restatement_detected"] is False

    # 2. GET /api/v1/cost/summary (Default USD)
    res_summary = test_client.get(
        "/api/v1/cost/summary?billing_period=2026-03",
        headers=headers,
    )
    assert res_summary.status_code == 200
    summary_data = res_summary.json()
    assert summary_data["row_count"] == 1
    assert summary_data["presentation_basis"] == "BILLED"
    assert Decimal(summary_data["billed_cost"]["target_amount"]) == Decimal("500.00")
    assert Decimal(summary_data["effective_cost"]["target_amount"]) == Decimal("450.00")
    assert Decimal(summary_data["realised_discount_value"]["target_amount"]) == Decimal("150.00")

    # 3. GET /api/v1/cost/summary with Query-Time Currency Conversion (EUR)
    res_eur = test_client.get(
        "/api/v1/cost/summary?billing_period=2026-03&target_currency=EUR",
        headers=headers,
    )
    assert res_eur.status_code == 200
    eur_data = res_eur.json()
    assert eur_data["billed_cost"]["target_currency"] == "EUR"
    # 500 * 0.9250 = 462.50 EUR
    assert Decimal(eur_data["billed_cost"]["target_amount"]) == Decimal("462.50")
    assert "Converted from 500.00 USD to 462.50 EUR" in eur_data["billed_cost"]["disclosure"]


def test_api_unknown_schema_returns_400(test_client: TestClient):
    """Verifies that an unknown dataset schema returns 400 Bad Request."""
    headers = {"X-Tenant-ID": "tenant-api-test"}
    payload = {
        "provider": "aws",
        "schema_version": "unsupported_random_schema_v99",
        "scope_id": "acc-1",
        "records": [{"BilledCost": 10}],
    }
    res = test_client.post("/api/v1/cost/ingest", json=payload, headers=headers)
    assert res.status_code == 400
    data = res.json()
    assert data["error_code"] == "UNKNOWN_SCHEMA_VERSION"


def test_api_drill_through_rbac_denial(test_client: TestClient):
    """Verifies that level 4 drill-through without financial permission returns 403 Forbidden."""
    headers = {"X-Tenant-ID": "tenant-api-test"}

    # Ingest baseline
    payload = {
        "provider": "aws",
        "schema_version": "aws_focus_1_0",
        "scope_id": "acc-test",
        "records": [
            {
                "ChargePeriodStart": "2026-03-01T00:00:00Z",
                "ChargePeriodEnd": "2026-03-01T23:59:59Z",
                "BilledCost": 10.00,
                "EffectiveCost": 10.00,
                "ServiceName": "AmazonS3",
                "ChargeCategory": "Usage",
            }
        ],
    }
    test_client.post("/api/v1/cost/ingest", json=payload, headers=headers)

    # Drill through level 4 with has_financial_permission=false -> 403 Forbidden
    res = test_client.get(
        "/api/v1/cost/drill-through?scope_id=acc-test&service_id=AmazonS3&charge_category=Usage&has_financial_permission=false",
        headers=headers,
    )
    assert res.status_code == 403
    err = res.json()
    assert err["error_code"] == "FINANCIAL_DETAIL_ACCESS_DENIED"
