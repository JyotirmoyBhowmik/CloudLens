"""CloudLens Canonical Unit Normalisation & Conversion Engine.

STRICT RULE (Prompt 04 Item 28 / Prompt 07 Item 49):
Must achieve 100% test coverage with exact Decimal mathematical conversions.
All unit conversions are backed by the declarative Unit Catalogue.
"""

from decimal import ROUND_HALF_EVEN, Decimal

from domain.catalogues.models import Dimensionality
from domain.catalogues.repository import CatalogueRepository
from domain.catalogues.unit_service import UnitConversionService
from domain.rules.monetary import to_decimal

# Shared catalogue repository & unit service backed by canonical seeds
_default_repo = CatalogueRepository(load_seeds=True)
_default_unit_service = UnitConversionService(_default_repo)


def convert_unit(
    value: Decimal | float | str | int,
    from_unit: str,
    to_unit: str,
    duration_hours: Decimal | float | str | int | None = None,
    decimal_places: int | None = 4,
) -> Decimal:
    """General unit conversion through the declarative Unit Catalogue."""
    return _default_unit_service.convert(
        value=value,
        from_unit=from_unit,
        to_unit=to_unit,
        duration_hours=duration_hours,
        decimal_places=decimal_places,
    )


def convert_storage(
    value: Decimal | float | str,
    from_unit: str,
    to_unit: str,
    decimal_places: int = 4,
) -> Decimal:
    """Converts digital storage quantities between binary units (KiB, MiB, GiB, TiB, PiB)."""
    val = to_decimal(value)
    if val < Decimal("0"):
        raise ValueError("Storage quantity cannot be negative.")

    src = _default_repo.get_unit(from_unit)
    if not src or src.dimensionality != Dimensionality.DIGITAL_STORAGE:
        raise ValueError(f"Unsupported source storage unit: '{from_unit}'.")

    dst = _default_repo.get_unit(to_unit)
    if not dst or dst.dimensionality != Dimensionality.DIGITAL_STORAGE:
        raise ValueError(f"Unsupported destination storage unit: '{to_unit}'.")

    return _default_unit_service.convert(
        value=val,
        from_unit=from_unit,
        to_unit=to_unit,
        decimal_places=decimal_places,
    )


def convert_network_bandwidth(
    value: Decimal | float | str,
    from_unit: str,
    to_unit: str,
    decimal_places: int = 4,
) -> Decimal:
    """Converts network bandwidth between decimal units (bps, Kbps, Mbps, Gbps)."""
    val = to_decimal(value)
    if val < Decimal("0"):
        raise ValueError("Network bandwidth cannot be negative.")

    src = _default_repo.get_unit(from_unit)
    if not src or src.dimensionality != Dimensionality.DATA_RATE:
        raise ValueError(f"Unsupported source network unit: '{from_unit}'.")

    dst = _default_repo.get_unit(to_unit)
    if not dst or dst.dimensionality != Dimensionality.DATA_RATE:
        raise ValueError(f"Unsupported destination network unit: '{to_unit}'.")

    return _default_unit_service.convert(
        value=val,
        from_unit=from_unit,
        to_unit=to_unit,
        decimal_places=decimal_places,
    )


def convert_time_to_hours(
    value: Decimal | float | str,
    from_unit: str,
    decimal_places: int = 4,
) -> Decimal:
    """Converts temporal units to canonical cloud billing hours (730 hours/month)."""
    val = to_decimal(value)
    if val < Decimal("0"):
        raise ValueError("Duration cannot be negative.")

    src = _default_repo.get_unit(from_unit)
    if not src or src.dimensionality != Dimensionality.TIME:
        raise ValueError(f"Unsupported time unit: '{from_unit}'.")

    return _default_unit_service.convert(
        value=val,
        from_unit=from_unit,
        to_unit="hours",
        decimal_places=decimal_places,
    )


def compute_core_hours(
    vcpus: int | Decimal,
    duration_hours: Decimal | float | str,
) -> Decimal:
    """Calculates compute consumption in vCPU-hours."""
    cpu = to_decimal(vcpus)
    dur = to_decimal(duration_hours)
    if cpu <= Decimal("0") or dur <= Decimal("0"):
        return Decimal("0.0000")
    return (cpu * dur).quantize(Decimal("0.0001"), rounding=ROUND_HALF_EVEN)
