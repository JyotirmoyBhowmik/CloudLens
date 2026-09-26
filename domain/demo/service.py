"""CloudLens Demo Mode Service & Safety Interlock Manager (Prompt 47 Items 30-32).

Enforces:
- Hard safety rules (Item 30):
  1. Demo Mode cannot be enabled on a tenant that has any live connector.
  2. A live connector cannot be added to a Demo Mode tenant.
  3. Switching a tenant out of Demo Mode requires purging simulated data with explicit confirmation
     and recording an immutable AuditEvent.
  4. Persistent banner on every screen and mandatory watermark on every export/report.
- One-command demo reset: purge, reseed, and reload in a single action (Item 31).
- Seven named demo scenarios loadable in one click (Item 32).
"""

import logging
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from domain.config.tenant_settings import (
    TenantSettingsStore,
    tenant_settings_store,
)
from domain.demo.models import (
    DEMO_BANNER_TEXT,
    EXPORT_WATERMARK,
    DemoModeStatus,
    DemoResetResult,
    DemoScenario,
    DemoScenarioInfo,
)
from domain.models.exceptions import DemoModeSafetyException
from domain.models.governance import AuditEvent
from domain.synthetic.mock_generator import (
    DeterministicMockEstateGenerator,
    DeterministicMockEstateResult,
)

logger = logging.getLogger(__name__)

SCENARIO_DEFINITIONS: dict[DemoScenario, DemoScenarioInfo] = {
    DemoScenario.MONTH_END_REVIEW: DemoScenarioInfo(
        scenario=DemoScenario.MONTH_END_REVIEW,
        title="Month-End Close & Year-over-Year Trend Review",
        description="Presents 13 consecutive months of historical spend with seasonal Q4 holiday surges and month-end batch peaks.",
        focus_story="Demonstrates financial reporting, YoY comparisons, seasonal forecasting, and month-end close accuracy.",
        key_metrics={"historical_months": 13, "dominant_services_pct": 82.5, "q4_surge_pct": 30.0},
    ),
    DemoScenario.BUDGET_BREACH_INVESTIGATION: DemoScenarioInfo(
        scenario=DemoScenario.BUDGET_BREACH_INVESTIGATION,
        title="Budget Overrun & Root-Cause Allocation Investigation",
        description="Highlights Retail Banking operating budget exceeding 125% allocation into the CRITICAL alert band.",
        focus_story="Demonstrates budget threshold alerting, team notification dispatch, and resource-level cost drilldown.",
        key_metrics={
            "breached_scope": "Retail Banking Production",
            "consumption_pct": 125.0,
            "severity": "CRITICAL",
        },
    ),
    DemoScenario.UNEXPECTED_COST_INCREASE: DemoScenarioInfo(
        scenario=DemoScenario.UNEXPECTED_COST_INCREASE,
        title="Sudden Cost Doubling Anomaly Detection",
        description="Surfaces an analytics database cluster that doubled in daily spend ($1,450 vs $350 baseline).",
        focus_story="Demonstrates automated statistical anomaly detection, day-over-day spike alerting, and root-cause tracing.",
        key_metrics={
            "spike_multiplier": 2.5,
            "daily_spike_amount": 1450.00,
            "status": "INVESTIGATING",
        },
    ),
    DemoScenario.GOVERNANCE_CLEANUP: DemoScenarioInfo(
        scenario=DemoScenario.GOVERNANCE_CLEANUP,
        title="Governance Debt, Unowned Clusters & Orphaned Storage Clean-Up",
        description="Surfaces unowned resource clusters, orphaned 2TB unattached disks, and dev workloads running over weekends.",
        focus_story="Demonstrates tag governance enforcement, ownership resolution fallback rules, and automated rightsizing recommendations.",
        key_metrics={"orphaned_disks": 1, "unowned_resources": 5, "weekend_idle_hosts": 4},
    ),
    DemoScenario.ONBOARDING_NEW_PROVIDER: DemoScenarioInfo(
        scenario=DemoScenario.ONBOARDING_NEW_PROVIDER,
        title="Multi-Cloud Unification & New Provider Simulator Onboarding",
        description="Onboards the OCI simulator profile alongside AWS, Azure, and GCP, verifying canonical hierarchy mapping.",
        focus_story="Demonstrates provider-agnostic canonical scope tree integration and seamless multi-cloud portfolio views.",
        key_metrics={
            "providers_active": 4,
            "oci_subgroups_supported": True,
            "conformance_kit_passed": True,
        },
    ),
    DemoScenario.RECONCILIATION_VARIANCE: DemoScenarioInfo(
        scenario=DemoScenario.RECONCILIATION_VARIANCE,
        title="Invoice vs. Metered Telemetry Reconciliation Variance",
        description="Contrasts an acceptable 0.04% minor rounding variance against an unacceptable 4.80% unallocated invoice discrepancy.",
        focus_story="Demonstrates financial integrity gates, tolerance thresholds, and automated exception ticketing.",
        key_metrics={
            "acceptable_tolerance_pct": 0.5,
            "discrepancy_observed_pct": 4.80,
            "action_required": True,
        },
    ),
    DemoScenario.FREE_TIER_EXHAUSTION: DemoScenarioInfo(
        scenario=DemoScenario.FREE_TIER_EXHAUSTION,
        title="Free-Tier Allowance Exhaustion & Proactive Cost Warning",
        description="Tracks serverless function invocation volume reaching 960,000 of 1,000,000 monthly free tier requests (96%).",
        focus_story="Demonstrates free-tier allowance monitoring, burn rate alerting, and transition to on-demand pricing.",
        key_metrics={
            "free_tier_allowance": 1000000,
            "current_usage": 960000,
            "consumption_pct": 96.0,
        },
    ),
}


class DemoModeService:
    """Enterprise Demo Mode Orchestrator & Safety Interlock Manager."""

    def __init__(
        self,
        tenant_store: TenantSettingsStore | None = None,
        generator: DeterministicMockEstateGenerator | None = None,
    ) -> None:
        self._tenant_store = tenant_store or tenant_settings_store
        self._generator = generator or DeterministicMockEstateGenerator(seed=42)
        # In-memory storage of connectors per tenant: tenant_id -> list of connector info
        self._tenant_connectors: dict[str, list[dict[str, Any]]] = {}
        # In-memory storage of active simulated estates: tenant_id -> DeterministicMockEstateResult
        self._tenant_estates: dict[str, DeterministicMockEstateResult] = {}
        # Audit event trail for compliance
        self._audit_events: list[AuditEvent] = []

    # ----------------------------------------------------------------------
    # Connector Safety Tracking & Interlocks
    # ----------------------------------------------------------------------

    def get_connectors(self, tenant_id: str) -> list[dict[str, Any]]:
        """Returns all registered connectors for the given tenant."""
        return list(self._tenant_connectors.get(tenant_id, []))

    def register_connector(
        self,
        tenant_id: str,
        connector_id: str,
        provider_name: str,
        is_live: bool = True,
    ) -> None:
        """Registers a connector, enforcing Safety Interlock 2.

        Safety Rule: A live connector cannot be added to a Demo Mode tenant.
        """
        settings = self._tenant_store.get(tenant_id)
        if settings.is_demo_mode and is_live:
            raise DemoModeSafetyException(
                f"Cannot attach live cloud connector '{connector_id}' ({provider_name}) to tenant '{tenant_id}' "
                "operating in Demo Mode. Safety interlock triggered to prevent simulated data contamination."
            )

        connectors = self._tenant_connectors.setdefault(tenant_id, [])
        # Remove any existing registration with same ID
        self._tenant_connectors[tenant_id] = [
            c for c in connectors if c["connector_id"] != connector_id
        ]
        self._tenant_connectors[tenant_id].append(
            {
                "connector_id": connector_id,
                "provider_name": provider_name,
                "is_live": is_live,
                "registered_at": datetime.now(UTC),
            }
        )

    def remove_connector(self, tenant_id: str, connector_id: str) -> None:
        """Removes a connector registration."""
        connectors = self._tenant_connectors.get(tenant_id, [])
        self._tenant_connectors[tenant_id] = [
            c for c in connectors if c["connector_id"] != connector_id
        ]

    def has_live_connectors(self, tenant_id: str) -> bool:
        """Returns True if the tenant has at least one active live cloud connector."""
        connectors = self.get_connectors(tenant_id)
        return any(c.get("is_live", False) for c in connectors)

    # ----------------------------------------------------------------------
    # Demo Mode Lifecycle & Interlocks
    # ----------------------------------------------------------------------

    def get_status(self, tenant_id: str) -> DemoModeStatus:
        """Returns current Demo Mode posture, safety status, and active scenario."""
        settings = self._tenant_store.get(tenant_id)
        estate = self._tenant_estates.get(tenant_id)
        has_live = self.has_live_connectors(tenant_id)

        return DemoModeStatus(
            is_demo_mode=settings.is_demo_mode,
            tenant_id=tenant_id,
            active_scenario=settings.demo_scenario,
            banner_message=DEMO_BANNER_TEXT if settings.is_demo_mode else None,
            watermark=EXPORT_WATERMARK,
            has_live_connectors=has_live,
            can_attach_live_connector=not settings.is_demo_mode,
            simulated_resources_count=len(estate.resources) if estate else 0,
            simulated_cost_facts_count=len(estate.cost_facts) if estate else 0,
        )

    def enable_demo_mode(
        self,
        tenant_id: str,
        scenario: DemoScenario | str = DemoScenario.MONTH_END_REVIEW,
        actor_id: str = "admin@cloudlens.internal",
    ) -> DemoModeStatus:
        """Enables Demo Mode on a tenant, enforcing Safety Interlock 1.

        Safety Rule: Demo Mode cannot be enabled on a tenant that has any live connector.
        """
        if self.has_live_connectors(tenant_id):
            raise DemoModeSafetyException(
                f"Cannot enable Demo Mode on tenant '{tenant_id}': active live cloud connectors are connected. "
                "Safety interlock triggered to prevent live financial accounts from receiving simulated data."
            )

        scenario_val = scenario.value if isinstance(scenario, DemoScenario) else str(scenario)

        # Update tenant configuration
        self._tenant_store.update(
            tenant_id,
            {
                "is_demo_mode": True,
                "demo_scenario": scenario_val,
            },
        )

        # Generate deterministic mock estate if not present
        if tenant_id not in self._tenant_estates:
            estate = self._generator.generate(tenant_id=tenant_id)
            self._tenant_estates[tenant_id] = estate

        # Record immutable audit event
        audit_event = AuditEvent(
            id=f"aud-{uuid.uuid4().hex[:12]}",
            tenant_id=tenant_id,
            actor_id=actor_id,
            action="DEMO_MODE_ENABLED",
            entity_type="TenantSettings",
            entity_id=tenant_id,
            payload_after={"is_demo_mode": True, "scenario": scenario_val},
            timestamp=datetime.now(UTC),
            correlation_id=str(uuid.uuid4()),
        )
        self._audit_events.append(audit_event)

        logger.info("Demo Mode enabled on tenant '%s' with scenario '%s'.", tenant_id, scenario_val)
        return self.get_status(tenant_id)

    def disable_demo_mode(
        self,
        tenant_id: str,
        confirm_purge: bool = False,
        actor_id: str = "admin@cloudlens.internal",
    ) -> DemoModeStatus:
        """Disables Demo Mode and purges simulated data, enforcing Safety Interlock 3.

        Safety Rule: Switching a tenant out of Demo Mode requires purging simulated data
        with an explicit confirmation and an audit record.
        """
        if not confirm_purge:
            raise DemoModeSafetyException(
                f"Switching tenant '{tenant_id}' out of Demo Mode requires explicit confirmation to purge "
                "all simulated data (confirm_purge=True). Refusing unconfirmed deactivation."
            )

        # Purge simulated estate data
        purged_estate = self._tenant_estates.pop(tenant_id, None)
        purged_count = (
            (len(purged_estate.resources) + len(purged_estate.cost_facts)) if purged_estate else 0
        )

        # Update tenant settings
        self._tenant_store.update(
            tenant_id,
            {
                "is_demo_mode": False,
                "demo_scenario": None,
            },
        )

        # Write immutable audit record
        audit_event = AuditEvent(
            id=f"aud-{uuid.uuid4().hex[:12]}",
            tenant_id=tenant_id,
            actor_id=actor_id,
            action="DEMO_MODE_DISABLED_AND_PURGED",
            entity_type="TenantSettings",
            entity_id=tenant_id,
            payload_before={"is_demo_mode": True, "purged_records": purged_count},
            payload_after={"is_demo_mode": False},
            timestamp=datetime.now(UTC),
            correlation_id=str(uuid.uuid4()),
        )
        self._audit_events.append(audit_event)

        logger.info(
            "Demo Mode disabled on tenant '%s'; purged %d simulated records.",
            tenant_id,
            purged_count,
        )
        return self.get_status(tenant_id)

    # ----------------------------------------------------------------------
    # One-Command Demo Reset & Scenario Loading (Items 31 & 32)
    # ----------------------------------------------------------------------

    def reset_demo(
        self,
        tenant_id: str = "T-DEMO",
        scenario: DemoScenario | str = DemoScenario.MONTH_END_REVIEW,
        seed: int = 42,
    ) -> DemoResetResult:
        """Purges, reseeds, and reloads the demonstration estate in a single action (Item 31)."""
        start = time.perf_counter()
        scenario_val = scenario.value if isinstance(scenario, DemoScenario) else str(scenario)

        # 1. Purge existing simulated records
        old_estate = self._tenant_estates.pop(tenant_id, None)
        purged_count = (len(old_estate.resources) + len(old_estate.cost_facts)) if old_estate else 0

        # 2. Reseed deterministically
        generator = DeterministicMockEstateGenerator(seed=seed)
        new_estate = generator.generate(tenant_id=tenant_id)
        self._tenant_estates[tenant_id] = new_estate

        # 3. Ensure Demo Mode enabled and scenario recorded
        self._tenant_store.update(
            tenant_id,
            {
                "is_demo_mode": True,
                "demo_scenario": scenario_val,
            },
        )

        elapsed = time.perf_counter() - start

        # 4. Audit record
        audit_event = AuditEvent(
            id=f"aud-{uuid.uuid4().hex[:12]}",
            tenant_id=tenant_id,
            actor_id="system-demo-reset",
            action="DEMO_ESTATE_RESET",
            entity_type="DeterministicMockEstate",
            entity_id=tenant_id,
            payload_after={
                "scenario": scenario_val,
                "manifest_hash": new_estate.manifest.sha256_hash,
                "resources_count": len(new_estate.resources),
                "cost_facts_count": len(new_estate.cost_facts),
            },
            timestamp=datetime.now(UTC),
            correlation_id=str(uuid.uuid4()),
        )
        self._audit_events.append(audit_event)

        logger.info(
            "Demo reset completed for tenant '%s' in %.4fs (manifest: %s)",
            tenant_id,
            elapsed,
            new_estate.manifest.sha256_hash,
        )

        return DemoResetResult(
            tenant_id=tenant_id,
            scenario=scenario_val,
            status="COMPLETED",
            purged_records=purged_count,
            reseeded_resources=len(new_estate.resources),
            reseeded_cost_facts=len(new_estate.cost_facts),
            elapsed_seconds=round(elapsed, 4),
            manifest_hash=new_estate.manifest.sha256_hash,
            reset_at=datetime.now(UTC),
        )

    def load_scenario(
        self,
        tenant_id: str,
        scenario: DemoScenario | str,
    ) -> DemoScenarioInfo:
        """Loads a named demo scenario in one action (Item 32)."""
        sc_enum = scenario if isinstance(scenario, DemoScenario) else DemoScenario(scenario)
        sc_info = SCENARIO_DEFINITIONS.get(sc_enum)
        if not sc_info:
            raise ValueError(f"Unknown demo scenario: '{scenario}'")

        # Ensure demo mode active with selected scenario
        self.enable_demo_mode(tenant_id=tenant_id, scenario=sc_enum)
        return sc_info

    def get_scenarios(self) -> list[DemoScenarioInfo]:
        """Returns metadata for all 7 named demonstration scenarios."""
        return list(SCENARIO_DEFINITIONS.values())

    def get_estate(self, tenant_id: str) -> DeterministicMockEstateResult | None:
        """Retrieves active mock estate for the tenant."""
        return self._tenant_estates.get(tenant_id)

    def get_audit_trail(self, tenant_id: str | None = None) -> list[AuditEvent]:
        """Returns compliance audit events recorded by DemoModeService."""
        if tenant_id:
            return [ev for ev in self._audit_events if ev.tenant_id == tenant_id]
        return list(self._audit_events)

    # ----------------------------------------------------------------------
    # Watermark Enforcement on Exports & Reports (Item 30)
    # ----------------------------------------------------------------------

    def apply_watermark(self, content: Any, tenant_id: str, format: str = "json") -> Any:
        """Applies mandatory demonstration watermark if tenant is operating in Demo Mode."""
        settings = self._tenant_store.get(tenant_id)
        if not settings.is_demo_mode:
            return content

        if isinstance(content, dict):
            watermarked_dict = dict(content)
            watermarked_dict["_watermark"] = EXPORT_WATERMARK
            watermarked_dict["_demo_mode"] = True
            return watermarked_dict
        elif isinstance(content, str):
            if format.lower() == "csv":
                return f"# WATERMARK: {EXPORT_WATERMARK}\n" + content
            return content
        elif isinstance(content, list):
            # For list of records, add watermark header element
            return [{"_watermark": EXPORT_WATERMARK, "_demo_mode": True}] + content

        return content


# Singleton service instance
_demo_mode_service = DemoModeService()


def get_demo_mode_service() -> DemoModeService:
    """Returns the shared DemoModeService singleton."""
    return _demo_mode_service
