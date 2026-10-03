"""Pre-Checks Engine: Quota Headroom (Prompt 54) & Dependency Chain Cost (Prompt 33).

Enforces:
- Quota headroom pre-check flagging if proposed deployment consumes headroom below
  warning threshold (<20% or hard limit breach) before approval is committed.
- Dependency and shared-service pre-check deriving downstream infrastructure
  (e.g., compute server implies ALB, NAT gateway, telemetry, automated backup, shared services)
  to compute full application chain cost and chain multiplier.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from domain.provisioning.models import (
    DependencyComponentCost,
    DependencyPreCheckResult,
    QuotaPreCheckResult,
)
from domain.rules.monetary import round_currency

logger = logging.getLogger(__name__)


class QuotaPreCheckEngine:
    """Pre-check evaluating cloud quota headroom and limit breaches (Prompt 54)."""

    def evaluate_quota(
        self,
        provider: str,
        service: str,
        region: str,
        requested_units: Decimal = Decimal("2.0"),
        current_consumed: Decimal | None = None,
        limit_units: Decimal | None = None,
        quota_name: str | None = None,
        quota_code: str | None = None,
    ) -> QuotaPreCheckResult:
        """Evaluates whether proposed deployment exceeds quota or drops headroom below 20%."""
        prov = provider.strip().lower()
        svc = service.strip().lower()

        # Defaults based on standard cloud quotas if not explicitly provided
        if limit_units is None or current_consumed is None:
            if "ec2" in svc or "virtual machines" in svc or "compute" in svc:
                q_name = quota_name or f"{provider.upper()} Standard vCPU Limit ({region})"
                q_code = quota_code or f"L-{prov}-compute-vcpu"
                limit = Decimal("64.0")
                consumed = Decimal("44.0")
            elif "database" in svc or "rds" in svc:
                q_name = (
                    quota_name or f"{provider.upper()} Relational Database Instances ({region})"
                )
                q_code = quota_code or f"L-{prov}-db-instances"
                limit = Decimal("40.0")
                consumed = Decimal("32.0")
            else:
                q_name = quota_name or f"{provider.upper()} {service} Standard Quota ({region})"
                q_code = quota_code or f"L-{prov}-{svc[:8]}-std"
                limit = Decimal("50.0")
                consumed = Decimal("35.0")
        else:
            q_name = quota_name or f"{provider.upper()} {service} Limit ({region})"
            q_code = quota_code or f"L-{prov}-{svc[:8]}"
            limit = limit_units
            consumed = current_consumed

        req = requested_units
        projected = consumed + req

        # Headroom calculations
        current_headroom_units = max(Decimal("0.0"), limit - consumed)
        current_headroom_pct = (
            round_currency((current_headroom_units / limit) * Decimal("100.00"))
            if limit > Decimal("0.0")
            else Decimal("0.00")
        )

        projected_headroom_units = max(Decimal("0.0"), limit - projected)
        projected_headroom_pct = (
            round_currency((projected_headroom_units / limit) * Decimal("100.00"))
            if limit > Decimal("0.0")
            else Decimal("0.00")
        )

        is_blocked = projected > limit
        headroom_warning = is_blocked or (projected_headroom_pct < Decimal("20.00"))

        if is_blocked:
            msg = (
                f"QUOTA BREACH DETECTED: Proposed deployment requires {req:.1f} units, "
                f"projecting total usage to {projected:.1f} which exceeds limit of {limit:.1f} {q_name}. "
                f"A quota increase request is required before deployment."
            )
        elif headroom_warning:
            msg = (
                f"QUOTA HEADROOM WARNING: Available headroom will drop to {projected_headroom_pct:.1f}% "
                f"({projected_headroom_units:.1f} units remaining of {limit:.1f}), below the 20% safe buffer threshold."
            )
        else:
            msg = (
                f"Quota headroom is healthy: {projected_headroom_pct:.1f}% available "
                f"({projected_headroom_units:.1f} units remaining of {limit:.1f})."
            )

        return QuotaPreCheckResult(
            is_blocked=is_blocked,
            headroom_warning=headroom_warning,
            current_headroom_pct=current_headroom_pct,
            projected_headroom_pct=projected_headroom_pct,
            quota_name=q_name,
            quota_code=q_code,
            consumed_units=consumed,
            limit_units=limit,
            projected_units=projected,
            message=msg,
        )


class DependencyPreCheckEngine:
    """Pre-check deriving downstream and shared services to compute total chain cost (Prompt 33)."""

    def evaluate_dependencies(
        self,
        provider: str,
        service: str,
        primary_monthly_cost: Decimal,
        options: dict[str, Any] | None = None,
    ) -> DependencyPreCheckResult:
        """Derives implicit dependencies (ALB, NAT gateway, backup, telemetry) and shared services."""
        opts = options or {}
        svc_lower = service.strip().lower()
        prov_upper = provider.strip().upper()

        inferred: list[DependencyComponentCost] = []

        if "ec2" in svc_lower or "virtual machines" in svc_lower or "compute" in svc_lower:
            storage_gb = Decimal(str(opts.get("storage_gb", 100)))
            # Standard gp3 / premium SSD ~ $0.08 / GB-mo
            ebs_cost = round_currency(storage_gb * Decimal("0.08"))
            inferred.append(
                DependencyComponentCost(
                    service_name=f"{prov_upper} Attached Block Storage ({storage_gb} GB gp3)",
                    category="Storage",
                    estimated_monthly_cost=ebs_cost,
                    basis="Required boot/root volume for compute instance",
                )
            )

            # Application Load Balancer
            if opts.get("include_load_balancer", True):
                inferred.append(
                    DependencyComponentCost(
                        service_name=f"{prov_upper} Application Load Balancer",
                        category="Network",
                        estimated_monthly_cost=Decimal("22.50"),
                        basis="Ingress traffic distribution and health check management",
                    )
                )

            # NAT Gateway / Egress
            if opts.get("include_nat_gateway", True):
                inferred.append(
                    DependencyComponentCost(
                        service_name=f"{prov_upper} Managed NAT Gateway",
                        category="Network",
                        estimated_monthly_cost=Decimal("32.40"),
                        basis="Outbound internet connectivity for private subnet compute",
                    )
                )

            # Automated Snapshot & Backup
            inferred.append(
                DependencyComponentCost(
                    service_name=f"{prov_upper} Automated Backup & Snapshots",
                    category="Backup",
                    estimated_monthly_cost=Decimal("12.00"),
                    basis="Daily snapshot retention policy (30-day retention)",
                )
            )

        elif "rds" in svc_lower or "database" in svc_lower or "sql" in svc_lower:
            inferred.append(
                DependencyComponentCost(
                    service_name=f"{prov_upper} High-Availability Standby Replica",
                    category="Database",
                    estimated_monthly_cost=round_currency(primary_monthly_cost * Decimal("0.85")),
                    basis="Multi-AZ automated failover standby",
                )
            )
            inferred.append(
                DependencyComponentCost(
                    service_name=f"{prov_upper} Point-in-Time Database Backup",
                    category="Backup",
                    estimated_monthly_cost=Decimal("25.00"),
                    basis="Continuous WAL archiving with 35-day retention window",
                )
            )
        else:
            inferred.append(
                DependencyComponentCost(
                    service_name=f"{prov_upper} Centralized Observability & Logging",
                    category="Management",
                    estimated_monthly_cost=Decimal("15.00"),
                    basis="Platform log aggregation and metric collection",
                )
            )

        # Shared service apportionment (security monitoring, transit gateway, identity)
        shared_apportionment = round_currency(
            max(Decimal("15.00"), round_currency(primary_monthly_cost * Decimal("0.05")))
        )

        inferred_sum = sum((c.estimated_monthly_cost for c in inferred), Decimal("0.00"))
        total_chain_cost = round_currency(
            primary_monthly_cost + inferred_sum + shared_apportionment
        )

        if primary_monthly_cost > Decimal("0.00"):
            chain_multiplier = round_currency(total_chain_cost / primary_monthly_cost)
        else:
            chain_multiplier = Decimal("1.00")

        return DependencyPreCheckResult(
            primary_monthly_cost=round_currency(primary_monthly_cost),
            inferred_dependencies=inferred,
            total_chain_monthly_cost=total_chain_cost,
            shared_service_apportionment=shared_apportionment,
            chain_multiplier=chain_multiplier,
        )
