"""Declarative Unit Conversion Engine.

Enforces Prompt 07 Item 49:
- All unit conversion goes through the Unit catalogue; no ad-hoc arithmetic anywhere else.
- Lossless bidirectional conversion between storage (e.g. GB) and time-storage (e.g. GB-month).
- Adding a new unit requires only a catalogue row with zero code changes.
- Incompatible dimensionalities raise domain IncompatibleUnitError.
"""

from datetime import datetime
from decimal import ROUND_HALF_EVEN, Decimal

from domain.catalogues.models import Dimensionality
from domain.catalogues.repository import CatalogueRepository
from domain.models.exceptions import IncompatibleUnitError, UnitConversionError
from domain.rules.monetary import to_decimal

# Standard cloud billing month duration in hours (FOCUS 1.0 specification)
STANDARD_BILLING_MONTH_HOURS = Decimal("730")


class UnitConversionService:
    """Enterprise Unit Normalisation and Conversion Service backed by Unit Catalogue."""

    def __init__(self, repository: CatalogueRepository) -> None:
        self._repo = repository

    def convert(
        self,
        value: Decimal | float | str | int,
        from_unit: str,
        to_unit: str,
        duration_hours: Decimal | float | str | int | None = None,
        decimal_places: int | None = 4,
        as_of: datetime | None = None,
    ) -> Decimal:
        """Converts quantities between units declaratively defined in the Unit catalogue.

        Supports:
        - Direct within-dimensionality conversions (e.g., KiB -> GiB, second -> hour, bps -> Gbps).
        - Cross-dimensional capacity-duration conversions (e.g., GB <-> GB-month).
        """
        val = to_decimal(value)
        if val < Decimal("0"):
            raise ValueError("Unit conversion value cannot be negative.")

        src = self._repo.get_unit(from_unit, as_of=as_of)
        if not src:
            self._repo.record_gap(
                catalogue_type="UNIT",
                provider="canonical",
                native_identifier=from_unit,
                context={"requested_target": to_unit},
            )
            raise UnitConversionError(f"Unsupported source unit: '{from_unit}'.")

        dst = self._repo.get_unit(to_unit, as_of=as_of)
        if not dst:
            self._repo.record_gap(
                catalogue_type="UNIT",
                provider="canonical",
                native_identifier=to_unit,
                context={"requested_source": from_unit},
            )
            raise UnitConversionError(f"Unsupported destination unit: '{to_unit}'.")

        # Case 1: Same unit symbol -> Identity
        if src.symbol.lower() == dst.symbol.lower():
            if decimal_places is not None:
                exp = Decimal("10") ** -decimal_places
                return val.quantize(exp, rounding=ROUND_HALF_EVEN)
            return val

        # Case 2: Same dimensionality -> Base conversion
        if src.dimensionality == dst.dimensionality:
            # val -> base -> target
            base_val = (val - src.offset_to_base) * src.scale_factor_to_base
            target_val = (base_val / dst.scale_factor_to_base) + dst.offset_to_base

            if decimal_places is not None:
                exp = Decimal("10") ** -decimal_places
                return target_val.quantize(exp, rounding=ROUND_HALF_EVEN)
            return target_val

        # Case 3: Compound Time-Storage conversions (DIGITAL_STORAGE <-> TIME_STORAGE)
        # e.g., GB <-> GB-month
        is_storage_to_timestorage = (
            src.dimensionality == Dimensionality.DIGITAL_STORAGE
            and dst.dimensionality == Dimensionality.TIME_STORAGE
        )
        is_timestorage_to_storage = (
            src.dimensionality == Dimensionality.TIME_STORAGE
            and dst.dimensionality == Dimensionality.DIGITAL_STORAGE
        )

        if is_storage_to_timestorage or is_timestorage_to_storage:
            eff_duration = (
                to_decimal(duration_hours)
                if duration_hours is not None
                else STANDARD_BILLING_MONTH_HOURS
            )
            if eff_duration <= Decimal("0"):
                raise ValueError("Duration hours for capacity-time conversion must be positive.")

            # Resolve canonical references
            gb_unit = self._repo.get_unit("GB", as_of=as_of) or self._repo.get_unit(
                "gib", as_of=as_of
            )
            gb_hour_unit = self._repo.get_unit("GB-hour", as_of=as_of)
            assert gb_unit is not None and gb_hour_unit is not None

            if is_storage_to_timestorage:
                # 1. Convert source storage to base Bytes, then to GB
                bytes_val = (val - src.offset_to_base) * src.scale_factor_to_base
                gb_val = bytes_val / gb_unit.scale_factor_to_base

                # 2. Compute GB-hours over stated duration
                gb_hours = gb_val * eff_duration

                # 3. Convert GB-hours to destination time-storage unit
                target_val = (gb_hours / dst.scale_factor_to_base) + dst.offset_to_base

            else:
                # is_timestorage_to_storage:
                # 1. Convert source time-storage to base GB-hours
                gb_hours = (val - src.offset_to_base) * src.scale_factor_to_base

                # 2. Divide by duration hours to get average GB
                gb_val = gb_hours / eff_duration

                # 3. Convert GB to target storage unit via Bytes
                bytes_val = gb_val * gb_unit.scale_factor_to_base
                target_val = (bytes_val / dst.scale_factor_to_base) + dst.offset_to_base

            if decimal_places is not None:
                exp = Decimal("10") ** -decimal_places
                return target_val.quantize(exp, rounding=ROUND_HALF_EVEN)
            return target_val

        # Case 4: Incompatible dimensionalities
        raise IncompatibleUnitError(
            from_unit=from_unit,
            to_unit=to_unit,
            from_dim=src.dimensionality,
            to_dim=dst.dimensionality,
        )
