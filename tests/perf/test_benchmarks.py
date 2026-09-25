"""Performance & Throughput Benchmark Tests."""

import time
from decimal import Decimal

from domain.config import config_resolver
from domain.rules.monetary import calculate_amortisation, round_currency
from domain.synthetic import SyntheticEstateGenerator


def test_synthetic_generator_throughput_benchmark():
    """Verify synthetic estate generator exceeds 20,000 resources per second."""
    count = 10000
    start = time.perf_counter()
    gen = SyntheticEstateGenerator(total_resources=count, seed=42)
    manifest = gen.generate_and_reconcile()
    duration = time.perf_counter() - start

    assert manifest.resource_count == count
    throughput = count / duration
    assert throughput > 20000, f"Throughput {throughput:.0f} res/sec is below 20,000 SLA!"


def test_monetary_arithmetic_latency_benchmark():
    """Verify monetary calculation latency is under 0.05ms per operation."""
    iterations = 5000
    start = time.perf_counter()
    for _ in range(iterations):
        _ = calculate_amortisation(Decimal("1234.56"), 365)
        _ = round_currency(Decimal("9876.54321"), 2)
    duration = time.perf_counter() - start

    avg_ms = (duration / iterations) * 1000.0
    assert avg_ms < 0.1, f"Average calculation latency {avg_ms:.4f}ms exceeds threshold!"


def test_configuration_resolution_latency_benchmark():
    """Verify configuration resolution is under 1ms per lookup."""
    iterations = 1000
    start = time.perf_counter()
    for _ in range(iterations):
        _ = config_resolver.get_effective_value("database.pool_size")
    duration = time.perf_counter() - start

    avg_ms = (duration / iterations) * 1000.0
    assert avg_ms < 1.0, f"Average config lookup latency {avg_ms:.4f}ms exceeds threshold!"
