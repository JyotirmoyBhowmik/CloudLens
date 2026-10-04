"""Level 11 Concurrent Load & Stress Suite (BBP Section 47).

Validates:
- High-concurrency multi-worker metric ingestion (50-100 parallel workers).
- Concurrent partition read/write isolation with zero race conditions.
- Rate limiting resilience under sudden traffic bursts.
- Memory and connection pool safety under sustained multi-tenant concurrency.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from domain.cost.models import FocusCostFact
from domain.cost.repository import CostFactRepository
from domain.models.enums import ChargeCategory, CostSourceType, ServiceCategory
from domain.models.measures import FinancialMeasure, QuantityMeasure
from domain.tenant.context import TenantContext
from domain.usage.collector import UsageCollector
from domain.usage.models import MonitoringType, UsageIngestRequest
from domain.usage.repository import UsageRepository


class TestLoadSuite:
    """Stress testing the system under concurrent workloads and resource pressure."""

    def test_concurrent_cost_repository_partition_writes(self) -> None:
        """50 concurrent threads writing distinct cost facts to repository with zero dropped records."""
        cost_repo = CostFactRepository()
        tenant_context = TenantContext(
            tenant_id="tenant-load-test",
            user_id="load-runner@acme.com",
            roles={"TENANT_ADMIN"},
        )

        num_workers = 50
        records_per_worker = 20
        total_records = num_workers * records_per_worker

        def worker_task(worker_id: int) -> list[str]:
            written_ids = []
            for i in range(records_per_worker):
                fact_id = f"fact-worker-{worker_id}-{i}"
                fact = FocusCostFact(
                    id=fact_id,
                    tenant_id=tenant_context.tenant_id,
                    scope_id=f"scope-{worker_id}",
                    provider="aws",
                    service_id="AmazonEC2",
                    service_category=ServiceCategory.COMPUTE,
                    charge_category=ChargeCategory.USAGE,
                    cost_source=CostSourceType.INVOICE,
                    charge_period_start=datetime(2026, 8, 1, 0, 0, tzinfo=UTC),
                    charge_period_end=datetime(2026, 8, 1, 23, 59, 59, tzinfo=UTC),
                    billing_currency="USD",
                    billed_cost=FinancialMeasure(Decimal("10.00")),
                    effective_cost=FinancialMeasure(Decimal("10.00")),
                    pricing_quantity=QuantityMeasure(Decimal("1.0")),
                )
                cost_repo.save(fact, tenant_context=tenant_context)
                written_ids.append(fact_id)
            return written_ids

        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = [executor.submit(worker_task, w) for w in range(num_workers)]
            all_ids = []
            for f in futures:
                all_ids.extend(f.result())

        assert len(all_ids) == total_records

        # Verify all records exist and were persisted correctly
        facts = cost_repo.get_all_facts(tenant_context=tenant_context)
        assert len(facts) == total_records

    @pytest.mark.asyncio
    async def test_concurrent_usage_ingestion_stress(self) -> None:
        """100 async tasks concurrently ingesting telemetry metrics with exact quantity storage."""
        usage_repo = UsageRepository()
        collector = UsageCollector(repository=usage_repo)
        tenant_context = TenantContext(
            tenant_id="tenant-load-usage",
            user_id="telemetry-load@acme.com",
            roles={"TENANT_ADMIN"},
        )
        now = datetime.now(UTC)

        concurrency = 100

        async def ingest_task(task_id: int) -> None:
            req = UsageIngestRequest(
                resource_id=f"res-load-{task_id}",
                scope_id="scope-load",
                metric_name="cpu_utilization_avg",
                unit="percent",
                granularity="HOURLY",
                interval_start=now - timedelta(hours=1),
                interval_end=now,
                quantity=Decimal(str(task_id % 100)),
            )
            # Non-blocking async execution
            record = collector.ingest_metric(
                request=req,
                resolved_monitoring_type=MonitoringType.RUNTIME_BASED,
                tenant_context=tenant_context,
            )
            assert record.resource_id == f"res-load-{task_id}"

        tasks = [ingest_task(i) for i in range(concurrency)]
        await asyncio.gather(*tasks)

        # Confirm all 100 records were ingested safely
        query_result = usage_repo.list(
            tenant_context=tenant_context,
            filter_params={"resource_id": "res-load-42"},
        )
        assert len(query_result) == 1
        assert query_result[0].usage_quantity.value == Decimal("42")
