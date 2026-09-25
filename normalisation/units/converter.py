"""CloudLens Canonical Unit Normalisation & Conversion Engine.

STRICT RULE (Prompt 04 Item 28):
Must achieve 100% test coverage with exact Decimal mathematical conversions.
Supports:
- Binary Storage Units: B, KiB, MiB, GiB, TiB, PiB (1024 base)
- Decimal Network Units: bps, Kbps, Mbps, Gbps (1000 base)
- Temporal Units: seconds, minutes, hours, days, billing_months (730 hours)
"""

from decimal import ROUND_HALF_EVEN, Decimal

from domain.rules.monetary import to_decimal

# Storage multiplier constants relative to 1 Byte
STORAGE_FACTORS: dict[str, Decimal] = {
    "b": Decimal("1"),
    "bytes": Decimal("1"),
    "kib": Decimal("1024"),
    "mib": Decimal("1048576"),
    "gib": Decimal("1073741824"),
    "tib": Decimal("1099511627776"),
    "pib": Decimal("1125899906842624"),
}

# Network multiplier constants relative to 1 bit/sec
NETWORK_FACTORS: dict[str, Decimal] = {
    "bps": Decimal("1"),
    "kbps": Decimal("1000"),
    "mbps": Decimal("1000000"),
    "gbps": Decimal("1000000000"),
}

# Time multiplier constants relative to 1 hour
TIME_TO_HOURS: dict[str, Decimal] = {
    "second": Decimal("1") / Decimal("3600"),
    "seconds": Decimal("1") / Decimal("3600"),
    "minute": Decimal("1") / Decimal("60"),
    "minutes": Decimal("1") / Decimal("60"),
    "hour": Decimal("1"),
    "hours": Decimal("1"),
    "day": Decimal("24"),
    "days": Decimal("24"),
    "month": Decimal("730"),  # Standard FOCUS 1.0 / cloud billing month hours
    "months": Decimal("730"),
}


def convert_storage(
    value: Decimal | float | str,
    from_unit: str,
    to_unit: str,
    decimal_places: int = 4,
) -> Decimal:
    """Converts digital storage quantities between binary units (KiB, MiB, GiB, TiB, PiB)."""
    src = from_unit.strip().lower()
    dst = to_unit.strip().lower()

    if src not in STORAGE_FACTORS:
        raise ValueError(f"Unsupported source storage unit: '{from_unit}'.")
    if dst not in STORAGE_FACTORS:
        raise ValueError(f"Unsupported destination storage unit: '{to_unit}'.")

    val = to_decimal(value)
    if val < Decimal("0"):
        raise ValueError("Storage quantity cannot be negative.")

    # Convert to base Bytes, then to target unit
    bytes_val = val * STORAGE_FACTORS[src]
    result = bytes_val / STORAGE_FACTORS[dst]
    exponent = Decimal("10") ** -decimal_places
    return result.quantize(exponent, rounding=ROUND_HALF_EVEN)


def convert_network_bandwidth(
    value: Decimal | float | str,
    from_unit: str,
    to_unit: str,
    decimal_places: int = 4,
) -> Decimal:
    """Converts network bandwidth between decimal units (bps, Kbps, Mbps, Gbps)."""
    src = from_unit.strip().lower()
    dst = to_unit.strip().lower()

    if src not in NETWORK_FACTORS:
        raise ValueError(f"Unsupported source network unit: '{from_unit}'.")
    if dst not in NETWORK_FACTORS:
        raise ValueError(f"Unsupported destination network unit: '{to_unit}'.")

    val = to_decimal(value)
    if val < Decimal("0"):
        raise ValueError("Network bandwidth cannot be negative.")

    bps_val = val * NETWORK_FACTORS[src]
    result = bps_val / NETWORK_FACTORS[dst]
    exponent = Decimal("10") ** -decimal_places
    return result.quantize(exponent, rounding=ROUND_HALF_EVEN)


def convert_time_to_hours(
    value: Decimal | float | str,
    from_unit: str,
    decimal_places: int = 4,
) -> Decimal:
    """Converts temporal units to canonical cloud billing hours (730 hours/month)."""
    src = from_unit.strip().lower()
    if src not in TIME_TO_HOURS:
        raise ValueError(f"Unsupported time unit: '{from_unit}'.")

    val = to_decimal(value)
    if val < Decimal("0"):
        raise ValueError("Duration cannot be negative.")

    hours = val * TIME_TO_HOURS[src]
    exponent = Decimal("10") ** -decimal_places
    return hours.quantize(exponent, rounding=ROUND_HALF_EVEN)


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
