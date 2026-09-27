"""Unit Tests for Thirteen-Step Onboarding Wizard Service (Prompt 15 Items 100-103).

Enforces:
- Prompt 15 Item 100: 13-step wizard lifecycle with save-and-resume across sessions.
- Prompt 15 Item 101: Permission reference in Step 2 before credentials requested in Step 3.
- Prompt 15 Item 102: Permission pre-flight and degradation reporting ("Not Supported", not zero).
- Prompt 15 Item 103: Pre-completion estimates (resources, duration, metrics, cost).
- Security Constraint: Verbatim provider error on validation failure without credential persistence.
"""

from __future__ import annotations

import pytest

from connectors.contract.lifecycle import connector_lifecycle_manager
from connectors.wizard.service import OnboardingWizardService
from domain.credentials.permissions import PermissionReferenceService
from domain.models.enums import (
    ConnectorLifecycleState,
    ProviderType,
    SyncJobStatus,
    WizardStep,
)
from domain.models.exceptions import (
    CredentialValidationFailedException,
    InvalidWizardStepException,
)
from domain.tenant.context import TenantContext
from domain.wizard.repository import WizardRepository


@pytest.fixture
def tenant_context() -> TenantContext:
    return TenantContext(
        tenant_id="tenant-wiz-test-01",
        user_id="usr-cloud-admin",
        roles=["TENANT_ADMIN"],
        correlation_id="corr-wiz-test-001",
    )


@pytest.fixture
def wizard_service() -> OnboardingWizardService:
    return OnboardingWizardService(wizard_repo=WizardRepository())


# ==============================================================================
# 1. 13-Step Progression & Save-and-Resume (Item 100)
# ==============================================================================


@pytest.mark.asyncio
async def test_wizard_session_start_and_save_and_resume(
    wizard_service: OnboardingWizardService, tenant_context: TenantContext
):
    """Item 100: Session begins at Step 1, saves step progress, and resumes seamlessly."""
    session = wizard_service.start_session(user_id="usr-cloud-admin", tenant_context=tenant_context)
    assert session.current_step == WizardStep.SELECT_PROVIDER
    assert session.status == "IN_PROGRESS"
    session_id = session.id

    # Step 1: Select Provider
    session = await wizard_service.save_step(
        session_id=session_id,
        step=WizardStep.SELECT_PROVIDER,
        step_payload={"provider": "aws"},
        tenant_context=tenant_context,
    )
    assert session.current_step == WizardStep.SELECT_CONNECTION_METHOD
    assert session.provider == ProviderType.AWS
    assert WizardStep.SELECT_PROVIDER in session.completed_steps

    # Step 2: Select Connection Method
    session = await wizard_service.save_step(
        session_id=session_id,
        step=WizardStep.SELECT_CONNECTION_METHOD,
        step_payload={"connection_method": "role_delegation"},
        tenant_context=tenant_context,
    )
    assert session.current_step == WizardStep.ENTER_CREDENTIALS
    assert session.connection_method == "role_delegation"

    # Simulate disconnect and state restoration from database
    reloaded_session = wizard_service.get_session(
        session_id=session_id, tenant_context=tenant_context
    )
    assert reloaded_session.id == session_id
    assert reloaded_session.current_step == WizardStep.ENTER_CREDENTIALS
    assert reloaded_session.provider == ProviderType.AWS
    assert reloaded_session.connection_method == "role_delegation"


@pytest.mark.asyncio
async def test_wizard_invalid_step_transition_rejected(
    wizard_service: OnboardingWizardService, tenant_context: TenantContext
):
    """Item 100: Skipping steps or jumping forward out of order is strictly rejected."""
    session = wizard_service.start_session(user_id="usr-jump-test", tenant_context=tenant_context)
    # Attempting to jump directly from Step 1 to Step 6 (DISCOVER_SCOPES)
    with pytest.raises(InvalidWizardStepException):
        await wizard_service.save_step(
            session_id=session.id,
            step=WizardStep.DISCOVER_SCOPES,
            step_payload={},
            tenant_context=tenant_context,
        )


# ==============================================================================
# 2. Permission Reference in Step 2 Before Credentials (Item 101)
# ==============================================================================


def test_permission_reference_rendered_before_credentials():
    """Item 101: Renders least-privilege permission policy before credentials are requested."""
    ref_aws = PermissionReferenceService.get_reference(ProviderType.AWS)
    assert ref_aws.provider == ProviderType.AWS
    assert "role" in ref_aws.primary_auth_mechanism.lower()
    assert len(ref_aws.capabilities) >= 5

    # Verify minimum permissions for resource and cost discovery
    res_cap = next(c for c in ref_aws.capabilities if "Inventory" in c.capability_name)
    assert "tag:GetResources" in res_cap.minimum_permissions
    assert "ce:GetCostAndUsage" not in res_cap.minimum_permissions

    cost_cap = next(c for c in ref_aws.capabilities if "Cost" in c.capability_name)
    assert "ce:GetCostAndUsage" in cost_cap.minimum_permissions


# ==============================================================================
# 3. Credential Validation & Zero Persistence on Failure (Item 100 / Security)
# ==============================================================================


@pytest.mark.asyncio
async def test_credential_validation_failure_never_persists_credentials(
    wizard_service: OnboardingWizardService, tenant_context: TenantContext
):
    """Item 100 & SEC: If validation fails, error is verbatim and credentials are NEVER persisted."""
    session = wizard_service.start_session(user_id="usr-fail-test", tenant_context=tenant_context)
    await wizard_service.save_step(
        session_id=session.id,
        step=WizardStep.SELECT_PROVIDER,
        step_payload={"provider": "aws"},
        tenant_context=tenant_context,
    )
    await wizard_service.save_step(
        session_id=session.id,
        step=WizardStep.SELECT_CONNECTION_METHOD,
        step_payload={"connection_method": "role_delegation"},
        tenant_context=tenant_context,
    )

    invalid_credentials = {
        "role_arn": "arn:aws:iam::123456789012:role/NonExistentRole",
        "external_id": "bad-ext-id",
    }

    # Step 4: Validate Credentials fails
    with pytest.raises(CredentialValidationFailedException) as exc_info:
        await wizard_service.validate_credentials_step(
            session_id=session.id,
            credentials_payload=invalid_credentials,
            tenant_context=tenant_context,
        )

    # Verbatim error present
    assert (
        "rejected" in exc_info.value.verbatim_error.lower()
        or "failed" in exc_info.value.verbatim_error.lower()
    )

    # Verify session has NOT advanced and has NOT saved sensitive credentials
    refreshed = wizard_service.get_session(session.id, tenant_context=tenant_context)
    assert refreshed.current_step == WizardStep.ENTER_CREDENTIALS
    assert "_staged_credentials" not in refreshed.wizard_data


# ==============================================================================
# 4. Permission Pre-flight & Degradation ("Not Supported", not zero) (Item 102)
# ==============================================================================


@pytest.mark.asyncio
async def test_permission_degradation_renders_not_supported(
    wizard_service: OnboardingWizardService, tenant_context: TenantContext
):
    """Item 102: Missing permissions report consequences and render as 'Not Supported', NOT zero."""
    session = wizard_service.start_session(
        user_id="usr-degrade-test", tenant_context=tenant_context
    )
    await wizard_service.save_step(
        session_id=session.id,
        step=WizardStep.SELECT_PROVIDER,
        step_payload={"provider": "aws"},
        tenant_context=tenant_context,
    )
    await wizard_service.save_step(
        session_id=session.id,
        step=WizardStep.SELECT_CONNECTION_METHOD,
        step_payload={"connection_method": "role_delegation"},
        tenant_context=tenant_context,
    )
    await wizard_service.validate_credentials_step(
        session_id=session.id,
        credentials_payload={
            "role_arn": "arn:aws:iam::123456789012:role/ValidRole",
            "external_id": "ext-123",
        },
        tenant_context=tenant_context,
    )

    # Step 5: Evaluate with missing cost permissions
    simulated_missing = ["ce:GetCostAndUsage", "ce:GetCostAndUsageWithResources"]
    reports = await wizard_service.validate_permissions_step(
        session_id=session.id,
        simulate_missing_permissions=simulated_missing,
        tenant_context=tenant_context,
    )

    cost_reports = [r for r in reports if r.permission in simulated_missing]
    assert len(cost_reports) == 2
    for cr in cost_reports:
        assert cr.present is False
        # Constraint: unavailable capabilities render as "Not Supported", NOT zero
        assert cr.status_display == "Not Supported"
        assert len(cr.consequence_if_missing) > 0


# ==============================================================================
# 5. Pre-Completion Estimates in Step 12 (Item 103)
# ==============================================================================


@pytest.mark.asyncio
async def test_pre_completion_estimates(
    wizard_service: OnboardingWizardService, tenant_context: TenantContext
):
    """Item 103: Pre-completion estimates calculate duration, resources, calls, and cost."""
    session = wizard_service.start_session(user_id="usr-est-test", tenant_context=tenant_context)
    session.selected_scopes = ["acc-111", "acc-222", "acc-333"]
    wizard_service._wizard_repo.save(session, tenant_context=tenant_context)

    estimates = wizard_service.calculate_pre_completion_estimates(
        session_id=session.id, tenant_context=tenant_context
    )

    assert estimates.resource_count_estimate > 0
    assert estimates.expected_duration_seconds > 0
    assert estimates.metric_call_volume_estimate > 0
    assert estimates.provider_cost_implication_estimate_usd >= 0
    assert "explanation" in estimates.model_fields


# ==============================================================================
# 6. Complete Wizard (Step 13)
# ==============================================================================


@pytest.mark.asyncio
async def test_complete_wizard_registers_connector_and_starts_sync(
    wizard_service: OnboardingWizardService, tenant_context: TenantContext
):
    """Item 100/103: Step 13 registers active connector, initializes schedules, and runs initial sync."""
    session = wizard_service.start_session(user_id="usr-full-flow", tenant_context=tenant_context)
    session_id = session.id

    # 1. Select provider
    await wizard_service.save_step(
        session_id=session_id,
        step=WizardStep.SELECT_PROVIDER,
        step_payload={"provider": "aws"},
        tenant_context=tenant_context,
    )
    # 2. Select connection method
    await wizard_service.save_step(
        session_id=session_id,
        step=WizardStep.SELECT_CONNECTION_METHOD,
        step_payload={"connection_method": "role_delegation"},
        tenant_context=tenant_context,
    )
    # 3 & 4. Validate credentials
    await wizard_service.validate_credentials_step(
        session_id=session_id,
        credentials_payload={
            "role_arn": "arn:aws:iam::123456789012:role/ProdFinOps",
            "external_id": "ext-prod",
        },
        tenant_context=tenant_context,
    )
    # 5. Validate permissions
    await wizard_service.validate_permissions_step(
        session_id=session_id,
        simulate_missing_permissions=[],
        tenant_context=tenant_context,
    )
    # 6. Discover scopes
    scopes = await wizard_service.discover_scopes_step(
        session_id=session_id, tenant_context=tenant_context
    )
    assert len(scopes) > 0
    # 7. Select scopes
    await wizard_service.save_step(
        session_id=session_id,
        step=WizardStep.SELECT_SCOPES,
        step_payload={
            "selected_scopes": [s["scope_id"] for s in scopes[:2]],
            "include_future_scopes": True,
        },
        tenant_context=tenant_context,
    )
    # 8. Configure synchronisation
    await wizard_service.save_step(
        session_id=session_id,
        step=WizardStep.CONFIGURE_SYNCHRONISATION,
        step_payload={"cadence": "standard"},
        tenant_context=tenant_context,
    )
    # 9. Configure cost ingestion
    await wizard_service.save_step(
        session_id=session_id,
        step=WizardStep.CONFIGURE_COST_INGESTION,
        step_payload={"cost_granularity": "hourly", "lookback_days": 3},
        tenant_context=tenant_context,
    )
    # 10. Configure resource discovery
    await wizard_service.save_step(
        session_id=session_id,
        step=WizardStep.CONFIGURE_RESOURCE_DISCOVERY,
        step_payload={"scan_interval_hours": 6},
        tenant_context=tenant_context,
    )
    # 11. Configure usage monitoring
    await wizard_service.save_step(
        session_id=session_id,
        step=WizardStep.CONFIGURE_USAGE_MONITORING,
        step_payload={"metrics_enabled": True},
        tenant_context=tenant_context,
    )
    # 12. Configure budgets & thresholds
    await wizard_service.save_step(
        session_id=session_id,
        step=WizardStep.CONFIGURE_BUDGETS_THRESHOLDS,
        step_payload={"budget_alerts_enabled": True},
        tenant_context=tenant_context,
    )

    # 13. Complete
    result = await wizard_service.complete_wizard(
        session_id=session_id,
        tenant_context=tenant_context,
    )

    assert result["status"] == "COMPLETED"
    assert result["connector_id"] is not None
    assert result["sync_status"] in (
        SyncJobStatus.COMPLETED.value,
        SyncJobStatus.PARTIAL_SUCCESS.value,
    )
    assert result["rows_ingested"] >= 0

    # Connector must be registered in ACTIVE state
    conn_state = connector_lifecycle_manager.get_state(
        tenant_id=tenant_context.tenant_id, connector_id=result["connector_id"]
    )
    assert conn_state == ConnectorLifecycleState.ACTIVE
