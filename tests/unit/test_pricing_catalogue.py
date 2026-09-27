"""Comprehensive Unit Tests for Enterprise Pricing Catalogue with History (Prompt 20 / Track E).

Enforces:
- PR-001, PR-002, PR-008, PR-016, API-028.
- Full 20-attribute pricing catalogue entity set.
- Slowly Changing Dimension (SCD Type 2) historical accuracy:
  Point-in-time query returns exact rate effective on past date, not today's rate.
- STRICT PROHIBITION 1: Never overwrite a rate in place.
- STRICT PROHIBITION 2: Never model free tier as a boolean flag.
- STRICT PROHIBITION 3: Where contracted rate exists, list rate is never presented
  as organisation's rate, but both are retained so realized discount is tracked.
- Structured Tier and Volume pricing calculation.
- Rate variance detection and Pricing Change Signal emission.
- Unknown-SKU path: On-demand lookup and gap recording without failing ingestion.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from api.cloudlens_api.main import app
from domain.models.exceptions import (
    InvalidFreeAllowanceException,
    InvalidPricingTierException,
    PricingSCDConflictException,
)
from domain.pricing.models import (
    CommitmentInfo,
    DiscountInfo,
    FreeAllowance,
    PricingChangeRecord,
    PricingRecord,
    PricingTierModel,
    RateType,
    TierBracket,
    TierStructure,
)
from domain.pricing.repository import PricingRepository
from domain.pricing.service import PricingCatalogueService


@pytest.fixture
def clean_repo() -> PricingRepository:
    """Fixture providing clean repository with multi-cloud seed data."""
    return PricingRepository(load_seed_data=True)


@pytest.fixture
def pricing_service(clean_repo: PricingRepository) -> PricingCatalogueService:
    """Fixture providing pricing catalogue service."""
    return PricingCatalogueService(repository=clean_repo, enable_connector_lookups=True)


@pytest.fixture
def client() -> TestClient:
    """FastAPI TestClient fixture."""
    return TestClient(app)


# ==============================================================================
# 1. Full 20-Attribute Entity Set Verification
# ==============================================================================


def test_pricing_record_full_attribute_set():
    """Verify PricingRecord contains all 20 required enterprise attributes."""
    now = datetime.now(UTC)
    record = PricingRecord(
        provider="aws",  # 1. Provider
        service="AmazonEC2",  # 2. Service
        service_sku="AWS-EC2-C6I-2XLARGE",  # 3. Service SKU
        resource_type="virtual_machine",  # 4. Resource type
        region="us-east-1",  # 5. Region
        pricing_dimension="DIM-03",  # 6. Pricing dimension
        unit="Hrs",  # 7. Unit
        unit_price=0.3400,  # 8. Unit price
        currency="USD",  # 9. Currency
        free_allowance=FreeAllowance(  # 10. Free allowance (structured, never boolean)
            quantity=0.0,
            unit="Hrs",
            reset_period="MONTHLY",
            post_allowance_rate=0.3400,
        ),
        tier=TierStructure(  # 11. Tier
            pricing_model=PricingTierModel.GRADUATED,
            brackets=[TierBracket(tier_start=0.0, tier_end=None, tier_unit_rate=0.3400)],
        ),
        minimum_charge=0.0,  # 12. Minimum charge
        effective_from=now,  # 13. Effective date
        effective_to=None,  # 14. Expiration date
        discount_info=DiscountInfo(  # 15. Discount info
            discount_type="PERCENTAGE",
            discount_percentage=10.0,
            contract_reference="EA-TEST-001",
        ),
        commitment_info=CommitmentInfo(  # 16. Commitment info
            commitment_type="SAVINGS_PLAN",
            term_months=12,
            payment_option="NO_UPFRONT",
        ),
        source="aws_price_list_bulk",  # 17. Source
        source_url="https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/index.json",  # 18. Source URL
        retrieved_at=now,  # 19. Retrieval timestamp
        attributes={
            "instanceType": "c6i.2xlarge",
            "vcpu": 8,
        },  # 20. Provider-specific attribute bag
        rate_type=RateType.LIST,
    )

    assert record.provider == "aws"
    assert record.service == "AmazonEC2"
    assert record.service_sku == "AWS-EC2-C6I-2XLARGE"
    assert record.resource_type == "virtual_machine"
    assert record.region == "us-east-1"
    assert record.pricing_dimension == "DIM-03"
    assert record.unit == "Hrs"
    assert record.unit_price == 0.3400
    assert record.currency == "USD"
    assert record.free_allowance is not None
    assert record.free_allowance.quantity == 0.0
    assert record.tier is not None
    assert record.minimum_charge == 0.0
    assert record.effective_from == now
    assert record.effective_to is None
    assert record.discount_info is not None
    assert record.commitment_info is not None
    assert record.source == "aws_price_list_bulk"
    assert record.source_url is not None
    assert record.retrieved_at == now
    assert record.attributes["instanceType"] == "c6i.2xlarge"


# ==============================================================================
# 2. SCD Type 2 Point-in-Time Accuracy & No In-Place Overwrites
# ==============================================================================


def test_point_in_time_historical_query_returns_past_rate_not_today(
    pricing_service: PricingCatalogueService,
):
    """Historical point-in-time rate query returns the exact price effective on that past date."""
    # Seed data has AWS EC2 t3.xlarge:
    # v1 effective from 2024-01-01 to 2024-07-01 at rate 0.1800 (past)
    # v2 effective from 2024-07-01 onwards at rate 0.1664 (current)
    past_date = datetime(2024, 3, 15, 12, 0, 0, tzinfo=UTC)
    current_date = datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)

    # 1. Query past date (requesting retail list rate to observe SCD Type 2 version)
    quote_past = pricing_service.resolve_price_at_date(
        provider="aws",
        service_sku="AWS-EC2-T3-XLARGE-US-EAST",
        region="us-east-1",
        pricing_dimension="DIM-03",
        query_date=past_date,
        prefer_contracted=False,
    )
    assert quote_past.effective_price == 0.1800
    assert quote_past.record_version == 1

    # 2. Query current date
    quote_current = pricing_service.resolve_price_at_date(
        provider="aws",
        service_sku="AWS-EC2-T3-XLARGE-US-EAST",
        region="us-east-1",
        pricing_dimension="DIM-03",
        query_date=current_date,
        prefer_contracted=False,
    )
    assert quote_current.effective_price == 0.1664
    assert quote_current.record_version == 2


def test_scd_type_2_rate_progression_never_overwrites_in_place(
    pricing_service: PricingCatalogueService,
):
    """STRICT PROHIBITION: Never overwrite a rate in place.

    When a rate change arrives:
    - Active record is closed (effective_to set, is_active=False).
    - New record is created with incremented version.
    - Previous historical records remain intact and immutable.
    """
    initial_time = datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)
    updated_time = datetime(2025, 6, 1, 0, 0, 0, tzinfo=UTC)

    # Ingest version 1
    rec_v1 = PricingRecord(
        provider="azure",
        service="Storage",
        service_sku="AZ-BLOB-HOT-LRS",
        resource_type="object_storage",
        region="eastus",
        pricing_dimension="DIM-11",
        unit="GB-Mo",
        unit_price=0.0180,
        currency="USD",
        effective_from=initial_time,
        source="azure_retail_api",
    )
    stored_v1, change_v1 = pricing_service.ingest_price_record(rec_v1)
    assert stored_v1.version == 1
    assert stored_v1.is_active is True
    assert stored_v1.effective_to is None
    assert change_v1 is None

    # Ingest version 2 with updated price
    rec_v2 = PricingRecord(
        provider="azure",
        service="Storage",
        service_sku="AZ-BLOB-HOT-LRS",
        resource_type="object_storage",
        region="eastus",
        pricing_dimension="DIM-11",
        unit="GB-Mo",
        unit_price=0.0150,  # Price drop
        currency="USD",
        effective_from=updated_time,
        source="azure_retail_api",
    )
    stored_v2, change_v2 = pricing_service.ingest_price_record(rec_v2)

    # Assert new record properties
    assert stored_v2.version == 2
    assert stored_v2.is_active is True
    assert stored_v2.effective_from == updated_time
    assert stored_v2.effective_to is None

    # Assert old record was NOT overwritten in place
    old_record = pricing_service.repository.get_by_id(stored_v1.id)
    assert old_record is not None
    assert old_record.unit_price == 0.0180  # Rate was preserved!
    assert old_record.is_active is False
    assert old_record.effective_to == updated_time

    # Assert change record was emitted
    assert change_v2 is not None
    assert change_v2.old_unit_price == 0.0180
    assert change_v2.new_unit_price == 0.0150
    assert change_v2.absolute_change == -0.003
    assert change_v2.percentage_change < 0.0


def test_scd_type_2_rejects_backdated_effective_from_conflict(
    pricing_service: PricingCatalogueService,
):
    """Attempting to ingest a new active record with effective_from earlier than existing active record raises exception."""
    t1 = datetime(2025, 2, 1, 0, 0, 0, tzinfo=UTC)
    t_invalid = datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)

    rec1 = PricingRecord(
        provider="gcp",
        service="Cloud Storage",
        service_sku="GCP-GCS-STANDARD",
        resource_type="object_storage",
        region="us-central1",
        pricing_dimension="DIM-11",
        unit="GB-Mo",
        unit_price=0.020,
        effective_from=t1,
        source="gcp_billing_catalog",
    )
    pricing_service.ingest_price_record(rec1)

    rec_invalid = PricingRecord(
        provider="gcp",
        service="Cloud Storage",
        service_sku="GCP-GCS-STANDARD",
        resource_type="object_storage",
        region="us-central1",
        pricing_dimension="DIM-11",
        unit="GB-Mo",
        unit_price=0.022,
        effective_from=t_invalid,  # Earlier than active record!
        source="gcp_billing_catalog",
    )
    with pytest.raises(PricingSCDConflictException):
        pricing_service.ingest_price_record(rec_invalid)


# ==============================================================================
# 3. Pricing Change Detection & Signal Emission
# ==============================================================================


def test_pricing_change_signal_dispatched_to_listener(
    pricing_service: PricingCatalogueService,
):
    """Scheduled refresh detects price change, generates change record, and fires listener."""
    captured_signals: list[PricingChangeRecord] = []

    def on_change(signal: PricingChangeRecord):
        captured_signals.append(signal)

    pricing_service.register_change_listener(on_change)

    start_date = datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)
    change_date = datetime(2025, 3, 1, 0, 0, 0, tzinfo=UTC)

    # Initial record
    initial_rec = PricingRecord(
        provider="oci",
        service="Block Storage",
        service_sku="B91234",
        resource_type="storage_volume",
        region="us-ashburn-1",
        pricing_dimension="DIM-11",
        unit="GB-Mo",
        unit_price=0.0425,
        effective_from=start_date,
        source="oci_rate_card",
    )
    pricing_service.ingest_price_record(initial_rec)
    assert len(captured_signals) == 0

    # Rate change record
    updated_rec = PricingRecord(
        provider="oci",
        service="Block Storage",
        service_sku="B91234",
        resource_type="storage_volume",
        region="us-ashburn-1",
        pricing_dimension="DIM-11",
        unit="GB-Mo",
        unit_price=0.0380,  # Drop from 0.0425
        effective_from=change_date,
        source="oci_rate_card",
    )
    _, change = pricing_service.ingest_price_record(updated_rec)

    assert change is not None
    assert len(captured_signals) == 1
    sig = captured_signals[0]
    assert sig.provider == "oci"
    assert sig.service_sku == "B91234"
    assert sig.old_unit_price == 0.0425
    assert sig.new_unit_price == 0.0380
    assert sig.absolute_change == -0.0045


def test_idempotent_ingestion_does_not_create_new_version(
    pricing_service: PricingCatalogueService,
):
    """Re-ingesting unchanged price rate updates timestamp without creating new SCD version."""
    t1 = datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)
    rec = PricingRecord(
        provider="aws",
        service="DynamoDB",
        service_sku="AWS-DDB-WRITE-UNITS",
        resource_type="database",
        region="us-east-1",
        pricing_dimension="DIM-09",  # Per-operation
        unit="WCU-Hrs",
        unit_price=0.00065,
        effective_from=t1,
        source="aws_price_list_bulk",
    )
    stored1, change1 = pricing_service.ingest_price_record(rec)
    assert stored1.version == 1
    assert change1 is None

    # Ingest same rate again later
    later_fetch = t1 + timedelta(days=7)
    rec_same = rec.model_copy(update={"retrieved_at": later_fetch})
    stored2, change2 = pricing_service.ingest_price_record(rec_same)

    assert stored2.version == 1  # Version did NOT increment
    assert stored2.id == stored1.id
    assert change2 is None


# ==============================================================================
# 4. List vs Contracted Rate Precedence
# ==============================================================================


def test_contracted_rate_precedence_and_discount_realization(
    pricing_service: PricingCatalogueService,
):
    """Where a contracted rate exists, list rate is NEVER presented as organisation rate.

    Both are retained so the realised discount can be verified.
    """
    now = datetime.now(UTC)

    # AWS EC2 t3.xlarge in seed catalog has:
    # List rate: 0.1664
    # EDP Contracted rate: 0.1331 (20% discount)
    quote = pricing_service.resolve_price_at_date(
        provider="aws",
        service_sku="AWS-EC2-T3-XLARGE-US-EAST",
        region="us-east-1",
        pricing_dimension="DIM-03",
        query_date=now,
        prefer_contracted=True,
    )

    # 1. Effective price MUST be the contracted rate, not retail
    assert quote.effective_price == 0.1331
    assert quote.rate_type_applied == RateType.CONTRACTED
    assert quote.is_contracted_precedence_applied is True

    # 2. List price is retained in the quote
    assert quote.list_price == 0.1664

    # 3. Realized discount is calculated accurately
    assert quote.realized_discount_amount == pytest.approx(0.0333, abs=1e-4)
    assert quote.realized_discount_percent == pytest.approx(20.01, abs=0.1)


def test_list_rate_used_when_no_contracted_rate_exists(
    pricing_service: PricingCatalogueService,
):
    """When no contracted rate exists for a SKU, list rate is returned with 0 discount."""
    now = datetime.now(UTC)
    rec = PricingRecord(
        provider="aws",
        service="AmazonSNS",
        service_sku="AWS-SNS-REQUESTS",
        resource_type="messaging",
        region="us-east-1",
        pricing_dimension="DIM-05",  # Per-request
        unit="Requests",
        unit_price=0.0000005,
        effective_from=now - timedelta(days=30),
        source="aws_price_list_bulk",
        rate_type=RateType.LIST,
    )
    pricing_service.ingest_price_record(rec)

    quote = pricing_service.resolve_price_at_date(
        provider="aws",
        service_sku="AWS-SNS-REQUESTS",
        region="us-east-1",
        pricing_dimension="DIM-05",
        query_date=now,
        prefer_contracted=True,
    )

    assert quote.effective_price == 0.0000005
    assert quote.rate_type_applied == RateType.LIST
    assert quote.is_contracted_precedence_applied is False
    assert quote.realized_discount_amount == 0.0
    assert quote.realized_discount_percent == 0.0


# ==============================================================================
# 5. Structured Tier and Volume Pricing
# ==============================================================================


def test_graduated_tier_calculation():
    """Validates graduated incremental tier bracket calculation."""
    # First 50 TB @ 0.023, Next 450 TB @ 0.022, Over 500 TB @ 0.021
    tier = TierStructure(
        pricing_model=PricingTierModel.GRADUATED,
        brackets=[
            TierBracket(tier_start=0.0, tier_end=50.0, tier_unit_rate=0.023),
            TierBracket(tier_start=50.0, tier_end=500.0, tier_unit_rate=0.022),
            TierBracket(tier_start=500.0, tier_end=None, tier_unit_rate=0.021),
        ],
    )

    # 1. 30 TB -> strictly within tier 1
    cost_30 = tier.calculate_cost(30.0)
    assert cost_30 == pytest.approx(30.0 * 0.023, abs=1e-6)

    # 2. 100 TB -> 50 TB @ 0.023 + 50 TB @ 0.022
    expected_100 = (50.0 * 0.023) + (50.0 * 0.022)
    assert tier.calculate_cost(100.0) == pytest.approx(expected_100, abs=1e-6)

    # 3. 600 TB -> 50 @ 0.023 + 450 @ 0.022 + 100 @ 0.021
    expected_600 = (50.0 * 0.023) + (450.0 * 0.022) + (100.0 * 0.021)
    assert tier.calculate_cost(600.0) == pytest.approx(expected_600, abs=1e-6)


def test_volume_all_units_tier_calculation():
    """Validates volume tier calculation where all units qualify at highest bracket."""
    tier = TierStructure(
        pricing_model=PricingTierModel.VOLUME,
        brackets=[
            TierBracket(tier_start=0.0, tier_end=100.0, tier_unit_rate=0.10),
            TierBracket(tier_start=100.0, tier_end=500.0, tier_unit_rate=0.08),
            TierBracket(tier_start=500.0, tier_end=None, tier_unit_rate=0.05),
        ],
    )

    # 50 units -> 50 * 0.10
    assert tier.calculate_cost(50.0) == pytest.approx(5.0, abs=1e-6)

    # 200 units -> all 200 * 0.08
    assert tier.calculate_cost(200.0) == pytest.approx(16.0, abs=1e-6)

    # 600 units -> all 600 * 0.05
    assert tier.calculate_cost(600.0) == pytest.approx(30.0, abs=1e-6)


def test_tier_brackets_must_be_strictly_ordered():
    """Overlapping tier brackets raise InvalidPricingTierException."""
    with pytest.raises(InvalidPricingTierException):
        TierStructure(
            brackets=[
                TierBracket(tier_start=0.0, tier_end=100.0, tier_unit_rate=0.10),
                TierBracket(
                    tier_start=50.0, tier_end=200.0, tier_unit_rate=0.08
                ),  # 50 < 100 overlap!
            ]
        )


# ==============================================================================
# 6. Structured Free Allowance (Never a Boolean Flag)
# ==============================================================================


def test_free_allowance_structured_representation():
    """Free allowance must be structured data with quantity, unit, reset period, and post-rate."""
    allowance = FreeAllowance(
        quantity=1000000.0,
        unit="Requests",
        reset_period="MONTHLY",
        post_allowance_rate=0.0000002,
        is_exhaustible=True,
    )
    assert allowance.quantity == 1000000.0
    assert allowance.unit == "Requests"
    assert allowance.reset_period == "MONTHLY"
    assert allowance.post_allowance_rate == 0.0000002


def test_free_allowance_rejects_negative_or_blank():
    """Negative quantity or empty unit string raises InvalidFreeAllowanceException."""
    with pytest.raises(InvalidFreeAllowanceException):
        FreeAllowance(quantity=-10.0, unit="Hrs")

    with pytest.raises(InvalidFreeAllowanceException):
        FreeAllowance(quantity=10.0, unit="")


# ==============================================================================
# 7. Unknown-SKU Path & Fault Tolerance
# ==============================================================================


def test_unknown_sku_triggers_on_demand_lookup_and_ingestion(
    pricing_service: PricingCatalogueService,
):
    """Encountering an uncatalogued SKU triggers on-demand fetch from connector."""
    # "AWS-RDS-DB-R5-2XLARGE" is in AWSPricingService bulk catalog but not seeded in PricingRepository
    quote = pricing_service.resolve_price_at_date(
        provider="aws",
        service_sku="AWS-RDS-DB-R5-2XLARGE",
        region="us-east-1",
        pricing_dimension="DIM-03",
    )
    assert quote.effective_price > 0.0
    assert "RDS" in quote.service


def test_unresolvable_unknown_sku_recorded_in_gap_report_without_crashing_ingestion(
    pricing_service: PricingCatalogueService,
):
    """Unresolvable SKU records an UnknownSkuRecord and returns None without throwing."""
    fake_sku = "AWS-TOTALLY-UNKNOWN-SKU-99999"
    result = pricing_service.handle_unknown_sku(
        provider="aws",
        sku=fake_sku,
        raw_payload={"line_item": "unknown_item", "billed_cost": 42.0},
        service_hint="HypotheticalService",
        region_hint="us-east-1",
    )
    assert result is None  # Ingestion pipeline continues safely!

    # Check gap registry
    gaps = pricing_service.list_unknown_skus(provider="aws")
    matching_gap = next((g for g in gaps if g.service_sku == fake_sku), None)
    assert matching_gap is not None
    assert matching_gap.status == "UNRESOLVED"
    assert matching_gap.occurrence_count == 1
    assert matching_gap.raw_payload["billed_cost"] == 42.0


def test_resolving_unknown_sku_updates_gap_status(
    pricing_service: PricingCatalogueService,
):
    """Marking an unknown SKU resolved updates the gap record."""
    sku = "CUSTOM-SKU-123"
    pricing_service.handle_unknown_sku(provider="azure", sku=sku)

    updated = pricing_service.repository.mark_unknown_sku_resolved(
        provider="azure",
        service_sku=sku,
        resolved_pricing_id="pr-resolved-abc",
        notes="Manually mapped by cloud admin",
    )
    assert updated is not None
    assert updated.status == "RESOLVED"
    assert updated.resolved_pricing_id == "pr-resolved-abc"


# ==============================================================================
# 8. API Contract Verification
# ==============================================================================


def test_api_pricing_catalog_endpoint(client: TestClient):
    """GET /api/v1/pricing/catalog returns paginated pricing records."""
    response = client.get("/api/v1/pricing/catalog?provider=aws&page=1&page_size=10")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert data["total"] > 0
    first_item = data["items"][0]
    assert first_item["provider"] == "aws"
    assert "unit_price" in first_item


def test_api_pricing_resolve_endpoint(client: TestClient):
    """POST /api/v1/pricing/resolve returns resolved quote with contracted rate precedence."""
    payload = {
        "provider": "aws",
        "service_sku": "AWS-EC2-T3-XLARGE-US-EAST",
        "region": "us-east-1",
        "pricing_dimension": "DIM-03",
        "prefer_contracted": True,
    }
    response = client.post("/api/v1/pricing/resolve", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["effective_price"] == 0.1331  # Contracted EDP price
    assert data["list_price"] == 0.1664
    assert data["is_contracted_precedence_applied"] is True


def test_api_pricing_changes_endpoint(client: TestClient):
    """GET /api/v1/pricing/changes returns detected rate variances."""
    response = client.get("/api/v1/pricing/changes")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_api_unknown_skus_endpoint(client: TestClient):
    """GET /api/v1/pricing/unknown-skus returns gap records."""
    response = client.get("/api/v1/pricing/unknown-skus")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
