"""Comprehensive Unit Tests for Unit Conversions (100% Coverage Target)."""

from decimal import Decimal

import pytest

from normalisation.units.converter import (
    compute_core_hours,
    convert_network_bandwidth,
    convert_storage,
    convert_time_to_hours,
)


def test_convert_storage_binary_multiples():
    """Verify binary byte storage conversions across B, KiB, MiB, GiB, TiB, PiB."""
    # 1024 KiB = 1 MiB
    assert convert_storage(Decimal("1024"), "kib", "mib") == Decimal("1.0000")

    # 1 GiB = 1024 MiB
    assert convert_storage(Decimal("1"), "gib", "mib") == Decimal("1024.0000")

    # 1 TiB = 1024 GiB
    assert convert_storage(Decimal("1"), "tib", "gib") == Decimal("1024.0000")

    # 1 PiB = 1024 TiB
    assert convert_storage(Decimal("1"), "pib", "tib") == Decimal("1024.0000")

    # Bytes to GiB: 1,073,741,824 Bytes = 1 GiB
    assert convert_storage(Decimal("1073741824"), "bytes", "gib") == Decimal("1.0000")


def test_convert_storage_errors():
    """Verify validation errors for unknown units and negative quantities."""
    with pytest.raises(ValueError, match="Unsupported source storage unit"):
        convert_storage(100, "unknown_unit", "gib")

    with pytest.raises(ValueError, match="Unsupported destination storage unit"):
        convert_storage(100, "gib", "unknown_unit")

    with pytest.raises(ValueError, match="cannot be negative"):
        convert_storage(-50, "gib", "mib")


def test_convert_network_bandwidth():
    """Verify network bandwidth conversions between bps, Kbps, Mbps, Gbps."""
    # 1000 Mbps = 1 Gbps
    assert convert_network_bandwidth(Decimal("1000"), "mbps", "gbps") == Decimal("1.0000")

    # 1 Mbps = 1000 Kbps
    assert convert_network_bandwidth(Decimal("1"), "mbps", "kbps") == Decimal("1000.0000")

    # 1000 bps = 1 Kbps
    assert convert_network_bandwidth(Decimal("1000"), "bps", "kbps") == Decimal("1.0000")


def test_convert_network_bandwidth_errors():
    """Verify error handling on invalid units and negative values."""
    with pytest.raises(ValueError, match="Unsupported source network unit"):
        convert_network_bandwidth(10, "invalid", "gbps")

    with pytest.raises(ValueError, match="Unsupported destination network unit"):
        convert_network_bandwidth(10, "gbps", "invalid")

    with pytest.raises(ValueError, match="cannot be negative"):
        convert_network_bandwidth(-10, "mbps", "gbps")


def test_convert_time_to_hours():
    """Verify temporal conversions to canonical billing hours."""
    # 60 minutes = 1 hour
    assert convert_time_to_hours(Decimal("60"), "minutes") == Decimal("1.0000")

    # 3600 seconds = 1 hour
    assert convert_time_to_hours(Decimal("3600"), "seconds") == Decimal("1.0000")

    # 1 day = 24 hours
    assert convert_time_to_hours(Decimal("1"), "day") == Decimal("24.0000")

    # 1 cloud billing month = 730 hours
    assert convert_time_to_hours(Decimal("1"), "month") == Decimal("730.0000")


def test_convert_time_errors():
    """Verify error handling on invalid units and negative durations."""
    with pytest.raises(ValueError, match="Unsupported time unit"):
        convert_time_to_hours(10, "centuries")

    with pytest.raises(ValueError, match="cannot be negative"):
        convert_time_to_hours(-1, "hours")


def test_compute_core_hours():
    """Verify vCPU-hours computation."""
    # 8 vCPUs * 100 hours = 800 core-hours
    assert compute_core_hours(8, Decimal("100")) == Decimal("800.0000")

    # Zero vCPUs or zero hours
    assert compute_core_hours(0, Decimal("100")) == Decimal("0.0000")
    assert compute_core_hours(8, Decimal("0")) == Decimal("0.0000")
