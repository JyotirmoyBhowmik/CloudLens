"""In-memory fake repository for FOCUS Cost Facts (Prompt P06)."""

from __future__ import annotations

import builtins
import logging
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from domain.cost.models import (
    CostAggregateNode,
    CostRestatementRecord,
    FocusCostFact,
)
from domain.models.enums import ChargeCategory
from domain.models.exceptions import (
    FinancialDetailAccessDeniedException,
)
from domain.tenant.context import TenantContext
from domain.tenant.repository import TenantAwareRepository

logger = logging.getLogger(__name__)


class InMemoryCostFactRepository(TenantAwareRepository[FocusCostFact]):
    """In-memory and transactional repository for FOCUS cost facts with partition lifecycle."""

    is_in_memory: bool = True

    def __init__(self) -> None:
        # Key: (tenant_id, billing_period) -> list[FocusCostFact]
        self._partitions: dict[tuple[str, str], builtins.list[FocusCostFact]] = defaultdict(list)
        # Historical snapshots of superseded partitions for restatement retention
        # Key: (tenant_id, billing_period, version) -> list[FocusCostFact]
        self._historical_partitions: dict[tuple[str, str, int], builtins.list[FocusCostFact]] = {}
        # Restatement audit records
        self._restatements: dict[str, CostRestatementRecord] = {}

    def get(self, entity_id: str, *, tenant_context: TenantContext) -> FocusCostFact | None:
        self._validate_tenant_context(tenant_context)
        tid = tenant_context.tenant_id

        for (t, _), facts in self._partitions.items():
            if t == tid:
                for f in facts:
                    if f.id == entity_id:
                        return f
        return None

    def list(
        self,
        *,
        tenant_context: TenantContext,
        filter_params: Any = None,
        limit: int = 50,
        offset: int = 0,
    ) -> builtins.list[FocusCostFact]:
        self._validate_tenant_context(tenant_context)
        tid = tenant_context.tenant_id

        results: builtins.list[FocusCostFact] = []
        for (t, period), facts in self._partitions.items():
            if t == tid:
                candidate_facts = facts
                if isinstance(filter_params, dict):
                    if (
                        "billing_period" in filter_params
                        and filter_params["billing_period"] != period
                    ):
                        continue
                    if "service_id" in filter_params and filter_params["service_id"]:
                        candidate_facts = [
                            f
                            for f in candidate_facts
                            if f.service_id == filter_params["service_id"]
                        ]
                    if "provider" in filter_params and filter_params["provider"]:
                        candidate_facts = [
                            f for f in candidate_facts if f.provider == filter_params["provider"]
                        ]
                results.extend(candidate_facts)

        return results[offset : offset + limit]

    def get_all_facts(
        self,
        *,
        tenant_context: TenantContext,
        billing_period: str | None = None,
        scope_id: str | None = None,
    ) -> builtins.list[FocusCostFact]:
        self._validate_tenant_context(tenant_context)
        tid = tenant_context.tenant_id
        results: builtins.list[FocusCostFact] = []
        for (t, period), facts in self._partitions.items():
            if t == tid:
                if billing_period is not None and period != billing_period:
                    continue
                if scope_id is not None:
                    results.extend([f for f in facts if f.scope_id == scope_id])
                else:
                    results.extend(facts)
        return results

    def save(self, entity: FocusCostFact, *, tenant_context: TenantContext) -> FocusCostFact:
        self._validate_tenant_context(tenant_context)
        tid = tenant_context.tenant_id
        period = (
            entity.billing_period_start.strftime("%Y-%m")
            if entity.billing_period_start
            else entity.charge_period_start.strftime("%Y-%m")
        )
        key = (tid, period)

        facts = self._partitions[key]
        for i, existing in enumerate(facts):
            if existing.id == entity.id:
                facts[i] = entity
                return entity

        facts.append(entity)
        return entity

    def delete(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        self._validate_tenant_context(tenant_context)
        tid = tenant_context.tenant_id

        for (t, _), facts in self._partitions.items():
            if t == tid:
                for i, f in enumerate(facts):
                    if f.id == entity_id:
                        facts.pop(i)
                        return True
        return False

    def exists(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        return self.get(entity_id, tenant_context=tenant_context) is not None

    def replace_partition_atomic(
        self,
        billing_period: str,
        facts: builtins.list[FocusCostFact],
        *,
        tenant_context: TenantContext,
    ) -> tuple[int, CostRestatementRecord | None]:
        self._validate_tenant_context(tenant_context)
        tid = tenant_context.tenant_id
        key = (tid, billing_period)
        now = datetime.now(UTC)

        existing_facts = self._partitions.get(key, [])
        is_reingestion = len(existing_facts) > 0

        restatement_record: CostRestatementRecord | None = None

        if is_reingestion:
            orig_billed = sum(
                (f.billed_cost.value for f in existing_facts if f.billed_cost.is_present),
                Decimal("0.0"),
            )
            orig_effective = sum(
                (f.effective_cost.value for f in existing_facts if f.effective_cost.is_present),
                Decimal("0.0"),
            )

            new_billed = sum(
                (f.billed_cost.value for f in facts if f.billed_cost.is_present), Decimal("0.0")
            )
            new_effective = sum(
                (f.effective_cost.value for f in facts if f.effective_cost.is_present),
                Decimal("0.0"),
            )

            billed_delta = new_billed - orig_billed
            effective_delta = new_effective - orig_effective

            if billed_delta != Decimal("0.0") or effective_delta != Decimal("0.0"):
                current_version = max((f.restatement_version for f in existing_facts), default=1)
                new_version = current_version + 1

                self._historical_partitions[(tid, billing_period, current_version)] = list(
                    existing_facts
                )

                provider = facts[0].provider if facts else "unknown"
                updated_facts: list[FocusCostFact] = []
                for f in facts:
                    prior_line = next(
                        (
                            ef
                            for ef in existing_facts
                            if ef.id == f.id or ef.resource_id == f.resource_id
                        ),
                        None,
                    )
                    prior_b = prior_line.billed_cost if prior_line else None
                    prior_e = prior_line.effective_cost if prior_line else None

                    updated_facts.append(
                        f.model_copy(
                            update={
                                "is_restated": True,
                                "restatement_version": new_version,
                                "restatement_detected_at": now,
                                "prior_billed_cost": prior_b,
                                "prior_effective_cost": prior_e,
                                "restatement_reason": f"Provider retroactive restatement in period {billing_period}",
                            }
                        )
                    )
                facts = updated_facts

                restatement_record = CostRestatementRecord(
                    id=f"restatement-{tid}-{billing_period}-{uuid.uuid4().hex[:8]}",
                    tenant_id=tid,
                    provider=provider,
                    billing_period=billing_period,
                    detected_at=now,
                    original_billed_total=round(orig_billed, 2),
                    restated_billed_total=round(new_billed, 2),
                    billed_delta=round(billed_delta, 2),
                    original_effective_total=round(orig_effective, 2),
                    restated_effective_total=round(new_effective, 2),
                    effective_delta=round(effective_delta, 2),
                    affected_row_count=len(facts),
                    notes=f"Restatement detected for {billing_period}: Billed delta {billed_delta:+.2f}, Effective delta {effective_delta:+.2f}",
                )
                self._restatements[restatement_record.id] = restatement_record

        self._partitions[key] = list(facts)
        return len(facts), restatement_record

    def list_restatements(
        self,
        *,
        tenant_context: TenantContext,
        provider: str | None = None,
    ) -> builtins.list[CostRestatementRecord]:
        self._validate_tenant_context(tenant_context)
        tid = tenant_context.tenant_id

        return [
            rec
            for rec in self._restatements.values()
            if rec.tenant_id == tid and (provider is None or rec.provider == provider.lower())
        ]

    def get_historical_partition(
        self,
        billing_period: str,
        version: int,
        *,
        tenant_context: TenantContext,
    ) -> builtins.list[FocusCostFact]:
        self._validate_tenant_context(tenant_context)
        tid = tenant_context.tenant_id
        return list(self._historical_partitions.get((tid, billing_period, version), []))

    def get_period_totals(
        self,
        billing_period: str,
        *,
        tenant_context: TenantContext,
    ) -> dict[str, Decimal]:
        self._validate_tenant_context(tenant_context)
        tid = tenant_context.tenant_id
        facts = self._partitions.get((tid, billing_period), [])

        billed = sum(
            (f.billed_cost.value for f in facts if f.billed_cost.is_present), Decimal("0.0")
        )
        effective = sum(
            (f.effective_cost.value for f in facts if f.effective_cost.is_present), Decimal("0.0")
        )

        return {
            "billed_cost": round(billed, 2),
            "effective_cost": round(effective, 2),
            "row_count": Decimal(len(facts)),
        }

    def drill_down(
        self,
        *,
        tenant_context: TenantContext,
        scope_id: str | None = None,
        service_id: str | None = None,
        charge_category: ChargeCategory | None = None,
        billing_period: str | None = None,
        has_financial_permission: bool = True,
    ) -> CostAggregateNode:
        self._validate_tenant_context(tenant_context)
        tid = tenant_context.tenant_id

        all_facts: list[FocusCostFact] = []
        for (t, period), facts in self._partitions.items():
            if t == tid:
                if billing_period is None or period == billing_period:
                    all_facts.extend(facts)

        filtered_facts = all_facts
        if scope_id:
            filtered_facts = [f for f in filtered_facts if f.scope_id == scope_id]
        if service_id:
            filtered_facts = [f for f in filtered_facts if f.service_id == service_id]
        if charge_category:
            filtered_facts = [f for f in filtered_facts if f.charge_category == charge_category]

        if scope_id is None:
            scopes_grouped: dict[str, list[FocusCostFact]] = defaultdict(list)
            for f in filtered_facts:
                scopes_grouped[f.scope_id].append(f)

            children: list[CostAggregateNode] = []
            for sc_id, s_facts in scopes_grouped.items():
                b_sum = sum(
                    (f.billed_cost.value for f in s_facts if f.billed_cost.is_present),
                    Decimal("0.0"),
                )
                e_sum = sum(
                    (f.effective_cost.value for f in s_facts if f.effective_cost.is_present),
                    Decimal("0.0"),
                )
                children.append(
                    CostAggregateNode(
                        dimension_name="Scope",
                        dimension_value=sc_id,
                        level=1,
                        billed_cost=round(b_sum, 2),
                        effective_cost=round(e_sum, 2),
                        child_count=len({f.service_id for f in s_facts}),
                    )
                )

            total_b = sum((c.billed_cost for c in children), Decimal("0.0"))
            total_e = sum((c.effective_cost for c in children), Decimal("0.0"))
            return CostAggregateNode(
                dimension_name="Tenant",
                dimension_value=tid,
                level=1,
                billed_cost=round(total_b, 2),
                effective_cost=round(total_e, 2),
                child_count=len(children),
                children=children,
            )

        elif service_id is None:
            services_grouped: dict[str, list[FocusCostFact]] = defaultdict(list)
            for f in filtered_facts:
                services_grouped[f.service_id].append(f)

            children = []
            for svc_id, s_facts in services_grouped.items():
                b_sum = sum(
                    (f.billed_cost.value for f in s_facts if f.billed_cost.is_present),
                    Decimal("0.0"),
                )
                e_sum = sum(
                    (f.effective_cost.value for f in s_facts if f.effective_cost.is_present),
                    Decimal("0.0"),
                )
                children.append(
                    CostAggregateNode(
                        dimension_name="Service",
                        dimension_value=svc_id,
                        level=2,
                        billed_cost=round(b_sum, 2),
                        effective_cost=round(e_sum, 2),
                        child_count=len({f.charge_category for f in s_facts}),
                    )
                )

            total_b = sum((c.billed_cost for c in children), Decimal("0.0"))
            total_e = sum((c.effective_cost for c in children), Decimal("0.0"))
            return CostAggregateNode(
                dimension_name="Scope",
                dimension_value=scope_id,
                level=2,
                billed_cost=round(total_b, 2),
                effective_cost=round(total_e, 2),
                child_count=len(children),
                children=children,
            )

        elif charge_category is None:
            cats_grouped: dict[str, list[FocusCostFact]] = defaultdict(list)
            for f in filtered_facts:
                cats_grouped[f.charge_category.value].append(f)

            children = []
            for cat_str, s_facts in cats_grouped.items():
                b_sum = sum(
                    (f.billed_cost.value for f in s_facts if f.billed_cost.is_present),
                    Decimal("0.0"),
                )
                e_sum = sum(
                    (f.effective_cost.value for f in s_facts if f.effective_cost.is_present),
                    Decimal("0.0"),
                )
                children.append(
                    CostAggregateNode(
                        dimension_name="ChargeCategory",
                        dimension_value=cat_str,
                        level=3,
                        billed_cost=round(b_sum, 2),
                        effective_cost=round(e_sum, 2),
                        child_count=len(s_facts),
                    )
                )

            total_b = sum((c.billed_cost for c in children), Decimal("0.0"))
            total_e = sum((c.effective_cost for c in children), Decimal("0.0"))
            return CostAggregateNode(
                dimension_name="Service",
                dimension_value=service_id,
                level=3,
                billed_cost=round(total_b, 2),
                effective_cost=round(total_e, 2),
                child_count=len(children),
                children=children,
            )

        else:
            if not has_financial_permission:
                raise FinancialDetailAccessDeniedException(
                    "Access to raw line-item charge details is restricted by RBAC policy."
                )

            b_sum = sum(
                (f.billed_cost.value for f in filtered_facts if f.billed_cost.is_present),
                Decimal("0.0"),
            )
            e_sum = sum(
                (f.effective_cost.value for f in filtered_facts if f.effective_cost.is_present),
                Decimal("0.0"),
            )

            return CostAggregateNode(
                dimension_name="ChargeLine",
                dimension_value=f"{scope_id}:{service_id}:{charge_category.value}",
                level=4,
                billed_cost=round(b_sum, 2),
                effective_cost=round(e_sum, 2),
                child_count=len(filtered_facts),
                charge_lines=filtered_facts,
            )
