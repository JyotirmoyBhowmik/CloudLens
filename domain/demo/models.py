"""CloudLens Demo Mode Models and Scenarios (Prompt 47 Items 30-32).

Defines:
- DemoScenario: The 7 named demo scenarios loadable in one action.
- DemoModeStatus: Status profile with banner, watermark, and safety interlocks.
- DemoResetResult: Summary of one-command purge and reseed execution.
"""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

EXPORT_WATERMARK = "DEMONSTRATION DATA ONLY - NOT FOR OPERATIONAL USE"
DEMO_BANNER_TEXT = "DEMO MODE ACTIVE — SIMULATED CLOUD ESTATE (NOT FOR OPERATIONAL USE)"


class DemoScenario(StrEnum):
    """Seven named demonstration scenarios loadable in a single click (Prompt 47 Item 32)."""

    MONTH_END_REVIEW = "Month-End Review"
    BUDGET_BREACH_INVESTIGATION = "Budget Breach Investigation"
    UNEXPECTED_COST_INCREASE = "Unexpected Cost Increase"
    GOVERNANCE_CLEANUP = "Governance Clean-Up"
    ONBOARDING_NEW_PROVIDER = "Onboarding a New Provider"
    RECONCILIATION_VARIANCE = "Reconciliation Variance"
    FREE_TIER_EXHAUSTION = "Free-Tier Exhaustion"


class DemoScenarioInfo(BaseModel):
    """Metadata and presentation guidance for a named demo scenario."""

    scenario: DemoScenario = Field(..., description="Scenario identifier")
    title: str = Field(..., description="Human-readable title")
    description: str = Field(..., description="Detailed description of what the scenario showcases")
    focus_story: str = Field(..., description="Executive narrative and key takeaways for presenter")
    key_metrics: dict[str, Any] = Field(
        default_factory=dict, description="Highlighted metric values"
    )


class DemoModeStatus(BaseModel):
    """Runtime Demo Mode status and safety interlock posture (Prompt 47 Item 30)."""

    is_demo_mode: bool = Field(description="True if tenant is operating in simulated Demo Mode")
    tenant_id: str = Field(description="Target tenant identifier")
    active_scenario: str | None = Field(default=None, description="Currently loaded demo scenario")
    banner_message: str | None = Field(
        default=None, description="Persistent banner text for UI display"
    )
    watermark: str = Field(
        default=EXPORT_WATERMARK, description="Mandatory watermark applied to all exports"
    )
    has_live_connectors: bool = Field(
        default=False, description="True if tenant has active live cloud connectors"
    )
    can_attach_live_connector: bool = Field(
        default=False, description="False when in demo mode (safety rule)"
    )
    simulated_resources_count: int = Field(
        default=0, description="Count of active simulated resources"
    )
    simulated_cost_facts_count: int = Field(
        default=0, description="Count of active simulated cost facts"
    )
    last_updated: datetime = Field(default_factory=lambda: datetime.now(UTC))


class DemoResetResult(BaseModel):
    """Summary of one-command purge, reseed, and reload execution (Prompt 47 Item 31)."""

    tenant_id: str = Field(description="Target tenant ID")
    scenario: str = Field(description="Active scenario loaded")
    status: str = Field(default="COMPLETED", description="Reset status")
    purged_records: int = Field(default=0, description="Count of previously stored records purged")
    reseeded_resources: int = Field(default=0, description="Count of newly seeded resources")
    reseeded_cost_facts: int = Field(default=0, description="Count of newly seeded cost facts")
    elapsed_seconds: float = Field(default=0.0, description="Execution duration in seconds")
    manifest_hash: str = Field(description="Cryptographic SHA256 integrity hash of reseeded estate")
    reset_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
