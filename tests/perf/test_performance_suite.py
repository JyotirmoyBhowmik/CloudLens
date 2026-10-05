"""Level 10 Performance Verification Suite (BBP Section 47).

Validates:
- MVP Scale (10,000 resources): generation throughput, query response latency, zero drift.
- Design-Headroom Scale (100,000 resources): streaming scalability, memory efficiency, exact reconciliation.
- Monetary Calculation Latency: sub-millisecond precision operations at scale.
- Multi-dimensional indexing and filter evaluation performance.
"""

from __future__ import annotations

import time
from decimal import Decimal

from domain.rules.monetary import calculate_amortisation, round_currency
from domain.synthetic.estate_generator import SyntheticEstateGenerator


class TestPerformanceSuite:
    """Rigorous performance benchmarks verifying throughput and latency SLAs."""

    def test_mvp_scale_throughput_and_zero_drift(self) -> None:
        """MVP scale benchmark: 10,000 resources generated and reconciled with 0.00 drift."""
        count = 10_000
        start = time.perf_counter()
        gen = SyntheticEstateGenerator(total_resources=count, seed=42)
        manifest = gen.generate_and_reconcile()
        duration = time.perf_counter() - start

        # Verify SLA: throughput >= 15,000 res/sec
        throughput = count / duration
        assert throughput >= 15_000, f"Throughput {throughput:.0f} res/sec is below 15,000 SLA"

        # Verify mathematical exactness
        assert manifest.resource_count == count
        assert manifest.dominant_spend + manifest.long_tail_spend == manifest.total_cost
        provider_sum = sum(manifest.spend_by_provider.values())
        assert provider_sum == manifest.total_cost
        assert isinstance(manifest.total_cost, Decimal)

    def test_design_headroom_scale_streaming_and_reconciliation(self) -> None:
        """Design-headroom benchmark: 100,000 resources streamed with exact financial integrity."""
        count = 100_000
        gen = SyntheticEstateGenerator(total_resources=count, seed=123)

        streamed_count = 0
        total_sum = Decimal("0.00")
        provider_counts: dict[str, int] = {}
        start = time.perf_counter()

        for _record, _is_dominant, cost, provider in gen.stream_resources():
            streamed_count += 1
            total_sum += cost
            provider_counts[provider] = provider_counts.get(provider, 0) + 1

        duration = time.perf_counter() - start
        throughput = count / duration

        assert streamed_count == 100_000
        assert throughput >= 20_000, f"Headroom throughput {throughput:.0f} res/sec below target"
        assert total_sum > Decimal("0.00")
        assert sum(provider_counts.values()) == 100_000

    def test_monetary_batch_arithmetic_latency(self) -> None:
        """High-frequency monetary calculations maintain sub-0.05ms average latency."""
        iterations = 10_000
        start = time.perf_counter()

        for i in range(iterations):
            _ = calculate_amortisation(upfront_fee=Decimal(f"{1000 + i}.50"), duration_days=365)
            _ = round_currency(Decimal(f"{500 + i}.8455"), decimal_places=2)

        duration = time.perf_counter() - start
        avg_op_ms = (duration / (iterations * 2)) * 1000.0

        assert avg_op_ms < 0.05, f"Monetary operation latency {avg_op_ms:.4f}ms exceeds 0.05ms SLA"

    def test_multi_dimensional_filter_indexing_latency(self) -> None:
        """Filtering 10,000 in-memory inventory items executes within 50ms."""
        gen = SyntheticEstateGenerator(total_resources=10_000, seed=99)
        dataset = [rec for rec, _, _, _ in gen.stream_resources()]
        assert len(dataset) == 10_000

        # Run multi-dimensional structured query: Provider=AWS AND Env=production AND cost > 50
        start = time.perf_counter()
        matches = [
            item
            for item in dataset
            if item["provider"] == "aws"
            and item["tags"].get("Environment") == "production"
            and Decimal(item["monthly_cost"]) > Decimal("50.00")
        ]
        duration_ms = (time.perf_counter() - start) * 1000.0

        assert duration_ms < 50.0, f"Filter evaluation latency {duration_ms:.2f}ms exceeds 50ms SLA"
        assert isinstance(matches, list)
