"""Domain Models for Thirteen-Step Onboarding Wizard and Pre-Completion Estimates (Prompt 15).

Enforces:
- Prompt 15 Item 100: 13-step onboarding wizard supporting save-and-resume.
- Prompt 15 Item 101: Permission reference before credentials.
- Prompt 15 Item 102: Permission pre-flight and capability degradation.
- Prompt 15 Item 103: Pre-completion estimates.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from domain.models.base import CanonicalEntity
from domain.models.enums import ConnectorCapability, ProviderType, WizardStep


class WizardSession(CanonicalEntity):
    """Thirteen-step onboarding wizard session state for save-and-resume (Prompt 15 Item 100)."""

    tenant_id: str = Field(..., description="Tenant owning the wizard session")
    user_id: str = Field(..., description="Administrator user conducting the onboarding")
    provider: ProviderType | None = Field(default=None, description="Selected cloud provider")
    connection_method: str | None = Field(
        default=None, description="Selected enterprise auth mechanism"
    )
    current_step: WizardStep = Field(
        default=WizardStep.SELECT_PROVIDER, description="Active wizard step"
    )
    completed_steps: list[WizardStep] = Field(
        default_factory=list, description="Ordered list of finalized steps"
    )
    wizard_data: dict[str, Any] = Field(
        default_factory=dict, description="Transient and validated step configuration state"
    )
    selected_scopes: list[str] = Field(
        default_factory=list, description="Scopes chosen for monitoring"
    )
    include_future_scopes: bool = Field(
        default=True, description="Whether newly discovered scopes are automatically ingested"
    )
    status: str = Field(
        default="IN_PROGRESS", description="Lifecycle state (IN_PROGRESS, COMPLETED, ABANDONED)"
    )
    created_connector_id: str | None = Field(
        default=None, description="ID of created connector upon wizard completion"
    )


class PermissionConsequenceReport(BaseModel):
    """Individual permission evaluation report with explicit consequences (Prompt 15 Item 102)."""

    permission: str = Field(..., description="Specific cloud permission / action name")
    capability: ConnectorCapability = Field(..., description="Associated connector capability")
    present: bool = Field(..., description="Whether permission was successfully verified")
    consequence_if_missing: str = Field(
        ..., description="Explicit business/technical impact if permission is missing"
    )
    is_mandatory: bool = Field(
        default=True, description="Whether core platform operation requires this permission"
    )
    status_display: str = Field(
        default="Supported", description="Presentation string ('Supported' or 'Not Supported')"
    )


class PreCompletionEstimate(BaseModel):
    """Pre-completion estate sizing and operational cost estimates (Prompt 15 Item 103)."""

    resource_count_estimate: int = Field(
        ..., description="Estimated cloud resources discovered across chosen scopes"
    )
    expected_duration_seconds: int = Field(
        ..., description="Expected duration for initial discovery synchronization in seconds"
    )
    metric_call_volume_estimate: int = Field(
        ..., description="Projected monthly metrics and telemetry API call volume"
    )
    provider_cost_implication_estimate_usd: float = Field(
        ..., description="Estimated monthly provider API charges in USD"
    )
    explanation: str = Field(
        ..., description="Human-readable breakdown explaining assumptions and calculations"
    )


__all__ = [
    "WizardSession",
    "PermissionConsequenceReport",
    "PreCompletionEstimate",
    "WizardStep",
]
