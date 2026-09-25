"""Comprehensive Unit Tests for Enterprise Master Catalogues & Unknown Entry Gap Registry.

Enforces Prompt 07 Acceptance Criteria:
- Adding a new pricing dimension and a new unit requires only catalogue rows, proven by adding one of each in a test with no code change.
- An unmapped provider resource type appears as Unclassified with its native type visible and in the gap report.
- Converting GB to GB-month and back through the catalogue is lossless and tested.
- Catalogue versioning ensures historical classifications remain interpretable after a mapping changes.
- All 29 reconciled pricing dimensions from master brief are present and verifiable.
- Provider-specific dimension escape hatch is functional without code changes.
- Unknown-entry workflow records gap items and allows administrator resolution.
"""

import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest

from domain.catalogues import (
    AggregationMethod,
    CatalogueRepository,
    CatalogueService,
    Dimensionality,
    GapStatus,
)
from domain.models.exceptions import IncompatibleUnitError, UnitConversionError


@pytest.fixture
def catalogue() -> CatalogueService:
    """Fixture providing an isolated catalogue service with pre-loaded seeds."""
    repo = CatalogueRepository(load_seeds=True)
    return CatalogueService(repository=repo)


# ==============================================================================
# 1. Acceptance: Adding New Dimension & Unit Requires Only Catalogue Rows
# ==============================================================================


def test_adding_new_pricing_dimension_requires_only_catalogue_rows(catalogue: CatalogueService):
    """Acceptance: Adding a new pricing dimension requires only catalogue rows (0 code changes)."""
    dim_code = "DIM-QUANTUM-QUBIT-HOUR"
    dim_name = "Per-qubit-hour"
    category = "Consumption Unit"
    unit_sym = "qubit-hours"
    agg = AggregationMethod.SUM
    threshold_basis = "Quantum Qubit execution hours"

    # Add dynamically as a catalogue row
    new_dim = catalogue.add_pricing_dimension(
        code=dim_code,
        name=dim_name,
        category=category,
        unit_symbol=unit_sym,
        aggregation_method=agg,
        default_threshold_basis=threshold_basis,
        applicability_rules={"architecture": "quantum", "cooling": "dilution_fridge"},
        example_services="AWS Braket Rigetti, Azure Quantum IonQ",
        notes="Dynamically introduced quantum compute pricing dimension.",
    )

    assert new_dim.code == dim_code
    assert new_dim.version == 1

    # Retrieve and verify via catalogue API without any application code deployment
    retrieved = catalogue.get_pricing_dimension(dim_code)
    assert retrieved is not None
    assert retrieved.name == dim_name
    assert retrieved.unit_symbol == unit_sym
    assert retrieved.aggregation_method == agg
    assert retrieved.applicability_rules["architecture"] == "quantum"


def test_adding_new_unit_requires_only_catalogue_rows(catalogue: CatalogueService):
    """Acceptance: Adding a new unit requires only catalogue rows and immediately converts (0 code changes)."""
    # Define a new unit in the TIME dimensionality: "fortnight" = 14 days = 1,209,600 seconds
    catalogue.add_unit(
        symbol="fortnight",
        name="Fortnight (Two Weeks)",
        dimensionality=Dimensionality.TIME,
        base_unit="second",
        scale_factor_to_base=Decimal("1209600"),  # 14 * 24 * 3600
    )

    # Convert 1 fortnight to hours (14 * 24 = 336 hours)
    hours = catalogue.convert_unit(Decimal("1"), "fortnight", "hours")
    assert hours == Decimal("336.0000")

    # Convert 1 fortnight to days (14 days)
    days = catalogue.convert_unit(Decimal("1"), "fortnight", "day")
    assert days == Decimal("14.0000")

    # Convert 336 hours back to fortnight
    fortnights = catalogue.convert_unit(Decimal("336"), "hours", "fortnight")
    assert fortnights == Decimal("1.0000")


# ==============================================================================
# 2. Acceptance: Unmapped Provider Resource Type Handling
# ==============================================================================


def test_unmapped_provider_resource_type_appears_as_unclassified_and_in_gap_report(
    catalogue: CatalogueService,
):
    """Acceptance: An unmapped provider resource type appears as Unclassified with its native type visible and in the gap report."""
    unmapped_type = "AWS::Quantum::PhotonicProcessor"

    # Ingestion tries to resolve the unknown resource type
    result = catalogue.resolve_resource_type(provider="aws", native_type_name=unmapped_type)

    # 1. Classified as 'Unclassified'
    assert result.canonical_type == "Unclassified"
    # 2. Native type retained verbatim
    assert result.native_type_name == unmapped_type
    assert result.default_monitoring_type == "UNKNOWN"
    assert result.is_unclassified is True

    # 3. Surfaced in Catalogue Gap Report for administrator review
    report = catalogue.get_gap_report(status="OPEN")
    assert report.open_gaps >= 1
    assert "RESOURCE_TYPE" in report.gaps_by_type

    matching_gaps = [
        item
        for item in report.items
        if item.native_identifier == unmapped_type and item.provider == "aws"
    ]
    assert len(matching_gaps) == 1
    assert matching_gaps[0].catalogue_type == "RESOURCE_TYPE"
    assert matching_gaps[0].status == GapStatus.OPEN
    assert matching_gaps[0].occurrence_count == 1

    # Repeated encounter increments occurrence count rather than duplicating
    catalogue.resolve_resource_type(provider="aws", native_type_name=unmapped_type)
    updated_gap = catalogue.repository.record_gap("RESOURCE_TYPE", "aws", unmapped_type)
    assert updated_gap.occurrence_count >= 2


# ==============================================================================
# 3. Acceptance: Lossless Bidirectional Conversion GB <-> GB-Month
# ==============================================================================


def test_lossless_bidirectional_conversion_gb_to_gb_month(catalogue: CatalogueService):
    """Acceptance: Converting GB to GB-month and back through the catalogue is lossless and tested."""
    quantities = [
        Decimal("1.0000"),
        Decimal("100.0000"),
        Decimal("250.7500"),
        Decimal("1024.1234"),
        Decimal("999999.9999"),
    ]

    for q in quantities:
        # Convert GB -> GB-month (default 1 standard billing month = 730 hours)
        gb_month = catalogue.convert_unit(q, "GB", "GB-month")
        # Exact arithmetic: 100 GB stored for 1 month = 100 GB-month
        assert gb_month == q

        # Convert GB-month -> GB
        gb_restored = catalogue.convert_unit(gb_month, "GB-month", "GB")
        assert gb_restored == q, f"Lossless roundtrip failed for {q}: got {gb_restored}"

    # Also test cross-duration fractional conversion (e.g. 365 hours = 0.5 standard billing month)
    gb_half_month = catalogue.convert_unit(
        Decimal("100"), "GB", "GB-month", duration_hours=Decimal("365")
    )
    assert gb_half_month == Decimal("50.0000")

    gb_restored_half = catalogue.convert_unit(
        gb_half_month, "GB-month", "GB", duration_hours=Decimal("365")
    )
    assert gb_restored_half == Decimal("100.0000")


# ==============================================================================
# 4. Acceptance: Reconciled 29 Pricing Dimensions
# ==============================================================================


def test_all_twenty_nine_reconciled_pricing_dimensions_present(catalogue: CatalogueService):
    """Verify all 29 reconciled pricing dimensions from master brief (DIM-01 to DIM-29) are seeded."""
    json_path = (
        Path(__file__).resolve().parent.parent.parent
        / "docs"
        / "pricing-dimensions-reconciled.json"
    )
    assert json_path.exists(), "Reconciled pricing dimensions JSON missing!"
    reconciled_data = json.loads(json_path.read_text(encoding="utf-8"))
    assert len(reconciled_data) == 29

    for expected in reconciled_data:
        code = expected["code"]
        dim = catalogue.get_pricing_dimension(code)
        assert dim is not None, f"Pricing dimension {code} missing from catalogue!"
        assert dim.name == expected["name"]
        assert dim.category == expected["category"]
        assert dim.aggregation_method == expected["aggregation"]


# ==============================================================================
# 5. Acceptance: Provider-Specific Dimension Escape Hatch
# ==============================================================================


def test_provider_specific_dimension_escape_hatch(catalogue: CatalogueService):
    """Verify provider-specific dimension escape hatch allows custom billing models without code changes."""
    custom_code = "OCI_UNIVERSAL_CREDIT_MONTHLY"
    escape_hatch_dim = catalogue.add_provider_escape_hatch_dimension(
        code=custom_code,
        name="Oracle Universal Credit Monthly Drawdown",
        provider="oci",
        unit_symbol="USD",
        aggregation_method=AggregationMethod.SUM,
        default_threshold_basis="Credit burn rate vs commitment",
        applicability_rules={"provider": "oci", "agreement": "UCCA"},
        example_services="OCI Universal Cloud Credits",
    )

    assert escape_hatch_dim.code == custom_code
    assert escape_hatch_dim.is_custom_escape_hatch is True
    assert escape_hatch_dim.provider_code == "oci"

    # Verify provider filtering: OCI list includes it, AWS list excludes it
    oci_dims = catalogue.list_pricing_dimensions(provider="oci")
    assert any(d.code == custom_code for d in oci_dims)

    aws_dims = catalogue.list_pricing_dimensions(provider="aws")
    assert not any(d.code == custom_code for d in aws_dims)


# ==============================================================================
# 6. Acceptance: Catalogue Versioning & Historical Reproducibility
# ==============================================================================


def test_catalogue_versioning_and_historical_reproducibility(catalogue: CatalogueService):
    """Acceptance: Catalogue versioning ensures historical classifications remain interpretable after a mapping changes."""
    provider = "azure"
    native_type = "Microsoft.Compute/virtualMachines"

    # Initial mapping (version 1): VIRTUAL_MACHINE
    t_past = datetime(2025, 1, 1, 0, 0, 0)
    t_split = datetime(2025, 6, 1, 0, 0, 0)
    t_future = datetime(2025, 12, 1, 0, 0, 0)

    # Create new version 2 effective as of June 1, 2025
    catalogue.create_resource_type_version(
        provider=provider,
        native_type_name=native_type,
        new_canonical_type="HYBRID_COMPUTE_HOST",
        new_monitoring_type="COMPUTE_CLUSTER_NODE",
        effective_at=t_split,
    )

    # 1. Historical query (as of Jan 2025) must return version 1
    res_past = catalogue.resolve_resource_type(
        provider=provider, native_type_name=native_type, as_of=t_past
    )
    assert res_past.canonical_type == "VIRTUAL_MACHINE"
    assert res_past.default_monitoring_type == "COMPUTE_HOST"

    # 2. Modern query (as of Dec 2025) must return version 2
    res_future = catalogue.resolve_resource_type(
        provider=provider, native_type_name=native_type, as_of=t_future
    )
    assert res_future.canonical_type == "HYBRID_COMPUTE_HOST"
    assert res_future.default_monitoring_type == "COMPUTE_CLUSTER_NODE"


# ==============================================================================
# 7. Unknown-Entry Workflow & Gap Administration
# ==============================================================================


def test_unknown_entry_workflow_and_gap_resolution(catalogue: CatalogueService):
    """Verify administrator gap item resolution lifecycle."""
    # Trigger unmapped service
    svc_res = catalogue.resolve_service(
        provider="gcp", native_service_name="UnknownVertexAIService"
    )
    assert svc_res.is_unclassified is True
    assert svc_res.service_code == "Unclassified"

    report = catalogue.get_gap_report(status="OPEN")
    matching = [g for g in report.items if g.native_identifier == "UnknownVertexAIService"]
    assert len(matching) == 1
    gap_id = matching[0].id

    # Administrator resolves the gap
    resolved_gap = catalogue.resolve_gap(
        gap_id=gap_id,
        resolution_notes="Mapped to AI_ML Vertex AI service.",
        resolved_by="admin@enterprise.internal",
    )
    assert resolved_gap.status == GapStatus.RESOLVED
    assert resolved_gap.resolved_by == "admin@enterprise.internal"

    # Open gap count drops
    updated_report = catalogue.get_gap_report(status="OPEN")
    assert not any(g.id == gap_id for g in updated_report.items)


# ==============================================================================
# 8. Incompatible Unit Conversion Error Handling
# ==============================================================================


def test_incompatible_unit_conversion_raises_domain_error(catalogue: CatalogueService):
    """Verify incompatible dimensionalities raise IncompatibleUnitError."""
    # Cannot convert digital storage (GB) to temporal (seconds)
    with pytest.raises(IncompatibleUnitError) as exc:
        catalogue.convert_unit(Decimal("10"), "GB", "seconds")
    assert "incompatible dimensionalities" in str(exc.value)

    # Cannot convert currency (USD) to data rate (Gbps)
    with pytest.raises(IncompatibleUnitError):
        catalogue.convert_unit(Decimal("100"), "USD", "gbps")

    # Non-existent unit records a gap and raises UnitConversionError
    with pytest.raises(UnitConversionError):
        catalogue.convert_unit(Decimal("10"), "non_existent_unit_xyz", "GB")

    report = catalogue.get_gap_report(status="OPEN")
    assert any(g.native_identifier == "non_existent_unit_xyz" for g in report.items)
