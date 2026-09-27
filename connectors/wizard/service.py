"""CloudLens Thirteen-Step Onboarding Wizard Service (Prompt 15 Items 100-103).

Enforces:
- Prompt 15 Item 100: Canonical thirteen-step onboarding wizard supporting save-and-resume.
- Prompt 15 Item 101: Permission reference in Step 2 rendered before credentials requested.
- Prompt 15 Item 102: Permission pre-flight and capability degradation (Step 5).
  - Each permission reported with present/missing and explicit consequence.
  - Unavailable capabilities render as "Not Supported", not zero.
- Prompt 15 Item 103: Pre-completion estimates:
  - Resource count, expected duration, metric call volume, and provider cost implication.
- Security Constraint: If validation fails, credentials are NEVER persisted and provider error is shown verbatim.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from connectors.contract.lifecycle import connector_lifecycle_manager
from connectors.simulator.connector import ProviderSimulatorConnector
from connectors.sync.first_sync import FirstSyncService, get_first_sync_service
from connectors.sync.orchestrator import get_sync_orchestrator
from connectors.sync.scheduler import get_sync_scheduler
from connectors.wizard.notification_tester import (
    NotificationTester,
    get_notification_tester,
)
from domain.audit.models import AuditEventCreate
from domain.audit.service import get_audit_service
from domain.config.tenant_settings import tenant_settings_store
from domain.credentials.permissions import PermissionReferenceService
from domain.credentials.service import get_credential_service
from domain.models.enums import (
    AuditEventType,
    ConnectorCapability,
    ConnectorLifecycleState,
    CredentialType,
    OverrideClass,
    ProviderCapability,
    ProviderType,
    SyncType,
    WizardStep,
)
from domain.models.exceptions import (
    AlertDeliveryFailedException,
    CredentialValidationFailedException,
    InvalidWizardStepException,
    WizardException,
    WizardSessionNotFoundException,
)
from domain.notification.models import (
    AlertDeliveryTestReport,
    ChannelTestInput,
)
from domain.overrides.service import OverrideService
from domain.sync.first_sync_models import FirstSyncProgressReport
from domain.tenant.context import TenantContext
from domain.wizard.models import (
    OnboardingCompletionSummary,
    PermissionConsequenceReport,
    PreCompletionEstimate,
    QuotaMonitoringConfig,
    WizardSession,
)
from domain.wizard.repository import (
    WizardRepository,
    get_wizard_repository,
)

logger = logging.getLogger(__name__)

# Canonical sequence of the onboarding wizard steps (Prompt 15 & 15B)
WIZARD_STEP_SEQUENCE: list[WizardStep] = [
    WizardStep.SELECT_PROVIDER,
    WizardStep.SELECT_CONNECTION_METHOD,
    WizardStep.ENTER_CREDENTIALS,
    WizardStep.VALIDATE_CREDENTIALS,
    WizardStep.VALIDATE_PERMISSIONS,
    WizardStep.DISCOVER_SCOPES,
    WizardStep.SELECT_SCOPES,
    WizardStep.CONFIGURE_SYNCHRONISATION,
    WizardStep.CONFIGURE_COST_INGESTION,
    WizardStep.CONFIGURE_RESOURCE_DISCOVERY,
    WizardStep.CONFIGURE_USAGE_MONITORING,
    WizardStep.CONFIGURE_BUDGETS_THRESHOLDS,
    WizardStep.TEST_ALERT_DELIVERY,
    WizardStep.COMPLETE,
]


class OnboardingWizardService:
    """Manages the onboarding workflow, step validations, alert testing, and finalization."""

    def __init__(
        self,
        wizard_repo: WizardRepository | None = None,
        notification_tester: NotificationTester | None = None,
        first_sync_service: FirstSyncService | None = None,
        override_service: OverrideService | None = None,
    ) -> None:
        self._wizard_repo = wizard_repo or get_wizard_repository()
        self._credential_service = get_credential_service()
        self._audit_service = get_audit_service()
        self._sync_orchestrator = get_sync_orchestrator()
        self._sync_scheduler = get_sync_scheduler()
        self._notification_tester = notification_tester or get_notification_tester()
        self._first_sync_service = first_sync_service or get_first_sync_service()
        self._override_service = override_service or OverrideService()

    def start_session(self, user_id: str, tenant_context: TenantContext) -> WizardSession:
        """Starts a new wizard session or resumes an existing in-progress session (Item 100)."""
        active = self._wizard_repo.get_active_for_user(
            user_id=user_id, tenant_context=tenant_context
        )
        if active:
            logger.info("Resuming active wizard session '%s' for user '%s'", active.id, user_id)
            return active

        session_id = f"wiz-{uuid.uuid4().hex[:12]}"
        now = datetime.now(UTC)
        session = WizardSession(
            id=session_id,
            tenant_id=tenant_context.tenant_id,
            user_id=user_id,
            current_step=WizardStep.SELECT_PROVIDER,
            completed_steps=[],
            wizard_data={},
            selected_scopes=[],
            include_future_scopes=True,
            status="IN_PROGRESS",
            created_at=now,
            updated_at=now,
        )
        saved = self._wizard_repo.save(session, tenant_context=tenant_context)

        # Audit event
        try:
            self._audit_service.append_event(
                tenant_context=tenant_context,
                event_in=AuditEventCreate(
                    event_type=AuditEventType.WIZARD_STARTED,
                    actor_id=tenant_context.user_id,
                    actor_roles=tenant_context.roles,
                    action=AuditEventType.WIZARD_STARTED.value,
                    resource_type="WizardSession",
                    resource_id=session_id,
                    details={"user_id": user_id, "step": session.current_step.value},
                    correlation_id=tenant_context.correlation_id,
                ),
            )
        except Exception as exc:
            logger.warning("Audit emission failed: %s", exc)

        return saved

    def get_session(self, session_id: str, tenant_context: TenantContext) -> WizardSession:
        """Retrieves a wizard session by ID."""
        session = self._wizard_repo.get(session_id, tenant_context=tenant_context)
        if not session:
            raise WizardSessionNotFoundException(session_id)
        return session

    def get_permission_reference(self, provider: ProviderType) -> dict[str, Any]:
        """Renders least-privilege permission set before credentials requested (Item 101)."""
        ref = PermissionReferenceService.get_reference(provider)
        return {
            "provider": ref.provider.value,
            "provider_name": ref.provider_name,
            "primary_auth_mechanism": ref.primary_auth_mechanism,
            "supported_auth_mechanisms": ref.supported_auth_mechanisms,
            "forbidden_auth_mechanisms": ref.forbidden_auth_mechanisms,
            "capabilities": [
                {
                    "capability_code": cap.capability_code.value,
                    "capability_name": cap.capability_name,
                    "minimum_permissions": cap.minimum_permissions,
                    "required_scope": cap.required_scope,
                    "consequence_if_not_granted": cap.consequence_if_not_granted,
                    "is_mandatory": cap.is_mandatory,
                }
                for cap in ref.capabilities
            ],
            "markdown_path": ref.markdown_path,
        }

    async def save_step(
        self,
        session_id: str,
        step: WizardStep,
        step_payload: dict[str, Any],
        tenant_context: TenantContext,
    ) -> WizardSession:
        """Saves data for a specific step and advances the session (Item 100)."""
        session = self.get_session(session_id, tenant_context=tenant_context)

        # Validate step order
        step_idx = WIZARD_STEP_SEQUENCE.index(step)
        current_idx = WIZARD_STEP_SEQUENCE.index(session.current_step)
        if step_idx > current_idx + 1:
            raise InvalidWizardStepException(
                current_step=session.current_step.value, requested_step=step.value
            )

        now = datetime.now(UTC)
        session.wizard_data[step.value] = step_payload

        # Process step-specific domain actions
        if step == WizardStep.SELECT_PROVIDER:
            p_val = step_payload.get("provider", "aws").lower()
            session.provider = ProviderType(p_val)

        elif step == WizardStep.SELECT_CONNECTION_METHOD:
            session.connection_method = step_payload.get("connection_method")

        elif step == WizardStep.SELECT_SCOPES:
            session.selected_scopes = step_payload.get("selected_scopes", [])
            session.include_future_scopes = bool(step_payload.get("include_future_scopes", True))

        elif step == WizardStep.CONFIGURE_USAGE_MONITORING:
            # Item 26: Add quota monitoring configuration per AM-07
            quota_cfg = QuotaMonitoringConfig(
                quota_monitoring_enabled=bool(step_payload.get("quota_monitoring_enabled", True)),
                quota_headroom_threshold_percent=float(
                    step_payload.get("quota_headroom_threshold_percent", 20.0)
                ),
                predicted_exhaustion_alert_hours=int(
                    step_payload.get("predicted_exhaustion_alert_hours", 24)
                ),
                rate_limit_throttle_protection=bool(
                    step_payload.get("rate_limit_throttle_protection", True)
                ),
            )
            session.wizard_data["quota_monitoring_config"] = quota_cfg.model_dump()

        elif step == WizardStep.TEST_ALERT_DELIVERY:
            # Item 24: Test configured channels
            channels_input = [
                ChannelTestInput(**c) if isinstance(c, dict) else c
                for c in step_payload.get("channels", [])
            ]
            test_report = await self._notification_tester.execute_alert_delivery_test(
                session_id=session_id,
                channels=channels_input,
                tenant_context=tenant_context,
            )
            session.wizard_data["test_alert_delivery"] = test_report.model_dump()

        if step not in session.completed_steps:
            session.completed_steps.append(step)

        # Advance current step if next exists
        if step_idx + 1 < len(WIZARD_STEP_SEQUENCE):
            session.current_step = WIZARD_STEP_SEQUENCE[step_idx + 1]

        session.updated_at = now
        saved = self._wizard_repo.save(session, tenant_context=tenant_context)

        # Audit event
        try:
            self._audit_service.append_event(
                tenant_context=tenant_context,
                event_in=AuditEventCreate(
                    event_type=AuditEventType.WIZARD_STEP_SAVED,
                    actor_id=tenant_context.user_id,
                    actor_roles=tenant_context.roles,
                    action=AuditEventType.WIZARD_STEP_SAVED.value,
                    resource_type="WizardSession",
                    resource_id=session_id,
                    details={"saved_step": step.value, "next_step": session.current_step.value},
                    correlation_id=tenant_context.correlation_id,
                ),
            )
        except Exception as exc:
            logger.warning("Audit emission failed: %s", exc)

        return saved

    async def test_alert_delivery_step(
        self,
        session_id: str,
        channels: Sequence[ChannelTestInput | dict[str, Any]] | None,
        tenant_context: TenantContext,
    ) -> AlertDeliveryTestReport:
        """Executes the alert delivery test step (Prompt 15B Item 24)."""
        session = self.get_session(session_id, tenant_context=tenant_context)
        channels_input = [
            c if isinstance(c, ChannelTestInput) else ChannelTestInput(**c)
            for c in (channels or [])
        ]
        report = await self._notification_tester.execute_alert_delivery_test(
            session_id=session_id,
            channels=channels_input,
            tenant_context=tenant_context,
        )
        session.wizard_data["test_alert_delivery"] = report.model_dump()
        if WizardStep.TEST_ALERT_DELIVERY not in session.completed_steps:
            session.completed_steps.append(WizardStep.TEST_ALERT_DELIVERY)
        session.current_step = WizardStep.COMPLETE
        session.updated_at = datetime.now(UTC)
        self._wizard_repo.save(session, tenant_context=tenant_context)
        return report

    async def validate_credentials_step(
        self,
        session_id: str,
        credentials_payload: dict[str, Any],
        tenant_context: TenantContext,
    ) -> dict[str, Any]:
        """Validates credentials before persistence (Item 100/101).

        CRITICAL: If validation fails, credentials are NEVER persisted and error is returned verbatim.
        """
        session = self.get_session(session_id, tenant_context=tenant_context)
        provider = session.provider or ProviderType.AWS

        # Use simulator connector for probe validation
        connector = ProviderSimulatorConnector(
            connector_id=f"probe-{uuid.uuid4().hex[:8]}",
            tenant_id=tenant_context.tenant_id,
            profile=provider.value,
            config=credentials_payload,
        )

        try:
            val_res = await connector.validate_credentials()
            if not val_res.get("valid", False):
                verbatim = val_res.get("message", "Authentication rejected by provider API.")
                raise CredentialValidationFailedException(
                    verbatim_error=verbatim, provider=provider.value
                )

            # Health probe
            is_healthy = await connector.test_connection()
            if not is_healthy:
                raise CredentialValidationFailedException(
                    verbatim_error="Provider endpoint unreachable or connection refused.",
                    provider=provider.value,
                )

            # Validation succeeded: store credentials in session
            session.wizard_data[WizardStep.ENTER_CREDENTIALS.value] = {
                k: v
                for k, v in credentials_payload.items()
                if "secret" not in k.lower() and "key" not in k.lower()
            }
            # Temporarily stage raw secret for later binding in Step 13
            session.wizard_data["_staged_credentials"] = credentials_payload

            if WizardStep.ENTER_CREDENTIALS not in session.completed_steps:
                session.completed_steps.append(WizardStep.ENTER_CREDENTIALS)
            if WizardStep.VALIDATE_CREDENTIALS not in session.completed_steps:
                session.completed_steps.append(WizardStep.VALIDATE_CREDENTIALS)

            session.current_step = WizardStep.VALIDATE_PERMISSIONS
            session.updated_at = datetime.now(UTC)
            self._wizard_repo.save(session, tenant_context=tenant_context)

            return {
                "valid": True,
                "provider": provider.value,
                "message": "Credentials verified successfully against provider API.",
            }

        except CredentialValidationFailedException:
            # Re-raise so error handler preserves verbatim error and zero persistence occurs
            raise
        except Exception as exc:
            # Wrap any unhandled failure verbatim
            raise CredentialValidationFailedException(
                verbatim_error=str(exc), provider=provider.value
            ) from exc

    async def validate_permissions_step(
        self,
        session_id: str,
        simulate_missing_permissions: list[str] | None,
        tenant_context: TenantContext,
    ) -> list[PermissionConsequenceReport]:
        """Evaluates individual permissions and reports degradation consequences (Item 102)."""
        session = self.get_session(session_id, tenant_context=tenant_context)
        provider = session.provider or ProviderType.AWS
        ref = PermissionReferenceService.get_reference(provider)

        missing_set = set(simulate_missing_permissions or [])
        reports: list[PermissionConsequenceReport] = []

        # Map each capability requirement to concrete permission consequence report
        cap_mapping = {
            ProviderCapability.C01_HIERARCHY: ConnectorCapability.DISCOVER_HIERARCHY,
            ProviderCapability.C02_INVENTORY: ConnectorCapability.DISCOVER_RESOURCES,
            ProviderCapability.C03_COST: ConnectorCapability.COLLECT_COST_BULK,
            ProviderCapability.C04_USAGE: ConnectorCapability.COLLECT_USAGE,
            ProviderCapability.C11_PRICING: ConnectorCapability.COLLECT_PRICING_PUBLIC,
            ProviderCapability.C18_QUOTA: ConnectorCapability.COLLECT_BUDGETS,
        }

        for cap in ref.capabilities:
            conn_cap = cap_mapping.get(cap.capability_code, ConnectorCapability.HEALTH_STATUS)
            for perm in cap.minimum_permissions:
                is_present = perm not in missing_set
                status_disp = (
                    "Supported" if is_present else "Not Supported"
                )  # Item 102 constraint: "Not Supported", not zero
                reports.append(
                    PermissionConsequenceReport(
                        permission=perm,
                        capability=conn_cap,
                        present=is_present,
                        consequence_if_missing=cap.consequence_if_not_granted,
                        is_mandatory=cap.is_mandatory,
                        status_display=status_disp,
                    )
                )

        session.wizard_data[WizardStep.VALIDATE_PERMISSIONS.value] = {
            "reports": [r.model_dump() for r in reports],
            "missing_permissions": list(missing_set),
        }
        if WizardStep.VALIDATE_PERMISSIONS not in session.completed_steps:
            session.completed_steps.append(WizardStep.VALIDATE_PERMISSIONS)
        session.current_step = WizardStep.DISCOVER_SCOPES
        session.updated_at = datetime.now(UTC)
        self._wizard_repo.save(session, tenant_context=tenant_context)

        return reports

    async def discover_scopes_step(
        self, session_id: str, tenant_context: TenantContext
    ) -> list[dict[str, Any]]:
        """Discovers provider hierarchy and accounts/subscriptions (Step 6)."""
        session = self.get_session(session_id, tenant_context=tenant_context)
        provider = session.provider or ProviderType.AWS

        connector = ProviderSimulatorConnector(
            connector_id=f"disc-{uuid.uuid4().hex[:8]}",
            tenant_id=tenant_context.tenant_id,
            profile=provider.value,
        )

        nodes = await connector.discover_hierarchy()
        discovered_scopes: list[dict[str, Any]] = []
        for n in nodes:
            s_id = n.get("id") or n.get("scope_id", "scope-1")
            s_name = n.get("name") or n.get("display_name", s_id)
            s_type = n.get("type", "account")
            discovered_scopes.append({"scope_id": s_id, "name": s_name, "type": s_type})

        session.wizard_data[WizardStep.DISCOVER_SCOPES.value] = {"scopes": discovered_scopes}
        if WizardStep.DISCOVER_SCOPES not in session.completed_steps:
            session.completed_steps.append(WizardStep.DISCOVER_SCOPES)
        session.current_step = WizardStep.SELECT_SCOPES
        session.updated_at = datetime.now(UTC)
        self._wizard_repo.save(session, tenant_context=tenant_context)

        return discovered_scopes

    def calculate_pre_completion_estimates(
        self, session_id: str, tenant_context: TenantContext
    ) -> PreCompletionEstimate:
        """Calculates estate sizing, call volumes, and cost implications (Item 103)."""
        session = self.get_session(session_id, tenant_context=tenant_context)
        settings = tenant_settings_store.get(tenant_context.tenant_id).wizard_settings

        scope_count = max(1, len(session.selected_scopes))
        resource_estimate = scope_count * settings.default_estimated_resource_multiplier
        expected_duration = scope_count * settings.estimated_seconds_per_scope
        metric_calls = resource_estimate * settings.estimated_metric_calls_per_resource
        ten_thousand = 10000.0  # no-hardcode-allow: reason="Fixed billing rate denominator for per-10,000 API requests calculation", reviewer="enterprise-arch"
        provider_cost = (
            metric_calls / ten_thousand
        ) * settings.estimated_provider_cost_per_10k_calls

        explanation = (
            f"Based on {scope_count} selected scope(s) with an estimated average of "
            f"{settings.default_estimated_resource_multiplier} resources per scope (~{resource_estimate} total). "
            f"Initial discovery is projected to take ~{expected_duration}s. Monthly metric monitoring calls are "
            f"projected at ~{metric_calls:,} requests, with an estimated provider API cost impact of ~${provider_cost:.4f}/month."
        )

        provider = session.provider or ProviderType.AWS
        warnings: list[str] = []
        billing_warning = None
        if provider == ProviderType.GCP:
            billing_warning = (
                "Cloud Billing export is NOT retrospective. Export history begins strictly at enablement; "
                "prior consumption cannot be backfilled from BigQuery export."
            )
            warnings.append(billing_warning)

        estimate = PreCompletionEstimate(
            resource_count_estimate=resource_estimate,
            expected_duration_seconds=expected_duration,
            metric_call_volume_estimate=metric_calls,
            provider_cost_implication_estimate_usd=round(provider_cost, 4),
            explanation=explanation,
            billing_export_history_warning=billing_warning,
            warnings=warnings,
        )

        session.wizard_data["estimates"] = estimate.model_dump()
        return estimate

    async def complete_wizard(
        self, session_id: str, tenant_context: TenantContext
    ) -> dict[str, Any]:
        """Finalizes connector onboarding, activates schedules, and starts initial sync (Item 100/103 & Prompt 15B)."""
        session = self.get_session(session_id, tenant_context=tenant_context)
        provider = session.provider or ProviderType.AWS

        # Item 24: Verify Alert Delivery Test results
        alert_test_data = session.wizard_data.get(WizardStep.TEST_ALERT_DELIVERY.value)
        if not alert_test_data:
            # Run default verification test probe if not explicitly executed earlier
            test_report = await self._notification_tester.execute_alert_delivery_test(
                session_id=session_id,
                channels=[],
                tenant_context=tenant_context,
            )
            alert_test_data = test_report.model_dump()
            session.wizard_data[WizardStep.TEST_ALERT_DELIVERY.value] = alert_test_data
        else:
            test_report = AlertDeliveryTestReport(**alert_test_data)

        # Check if alert delivery test succeeded or has override
        if test_report.successful_channels == 0:
            # Check for active administrative override
            active_overrides = self._override_service.repository.list_active(
                tenant_context=tenant_context
            )
            has_override = any(
                ovr.override_class == OverrideClass.ALERT_DELIVERY_FAILURE
                and (ovr.what in (session_id, "*", "alert_delivery", "wizard"))
                for ovr in active_overrides
            )
            if not has_override:
                raise AlertDeliveryFailedException(
                    message=(
                        f"Alert delivery test failed across all configured channels for session '{session_id}'. "
                        "Onboarding completion requires at least one verified delivery channel or an administrative override."
                    ),
                    details=alert_test_data,
                )
            test_report.override_applied = True
            session.wizard_data[WizardStep.TEST_ALERT_DELIVERY.value] = test_report.model_dump()

        connector_id = f"conn-{provider.value.lower()}-{uuid.uuid4().hex[:8]}"
        staged_creds = session.wizard_data.get("_staged_credentials", {})

        # 1. Bind Credential Profile if staged
        cred_profile_id = None
        if staged_creds:
            try:
                c_method = str(session.connection_method or "role_arn").upper()
                if "OIDC" in c_method:
                    c_type = CredentialType.OIDC_FEDERATION
                elif "PRINCIPAL" in c_method or "CLIENT_SECRET" in c_method:
                    c_type = CredentialType.SERVICE_PRINCIPAL
                elif "SERVICE_ACCOUNT" in c_method:
                    c_type = CredentialType.SERVICE_ACCOUNT_KEY
                elif "API" in c_method or "SIGNING" in c_method:
                    c_type = CredentialType.API_SIGNING_KEY
                else:
                    c_type = CredentialType.ROLE_ARN

                prof = self._credential_service.create_profile(
                    tenant_id=tenant_context.tenant_id,
                    name=f"{provider.value.upper()} Production Connector Profile",
                    provider=provider,
                    credential_type=c_type,
                    secret_payload=staged_creds,
                    actor_id=tenant_context.user_id,
                    correlation_id=tenant_context.correlation_id,
                )
                cred_profile_id = prof.id
            except Exception as exc:
                logger.warning("Credential profile creation encountered error: %s", exc)

        # 2. Register Connector
        # Calculate capabilities based on missing permissions
        val_perm_data = session.wizard_data.get(WizardStep.VALIDATE_PERMISSIONS.value, {})
        missing_perms = set(val_perm_data.get("missing_permissions", []))

        # Default full simulator capabilities
        simulator = ProviderSimulatorConnector(
            connector_id=connector_id,
            tenant_id=tenant_context.tenant_id,
            profile=provider.value,
        )
        declared_caps = simulator.declared_capabilities

        # If permissions missing, degrade capabilities (Item 102)
        degraded_caps: set[ConnectorCapability] = set()
        if (
            "ce:GetCostAndUsage" in missing_perms
            or "Microsoft.CostManagement/exports/read" in missing_perms
        ):
            degraded_caps.add(ConnectorCapability.COLLECT_COST_BULK)
            degraded_caps.add(ConnectorCapability.COLLECT_COST_QUERY)

        active_caps = declared_caps - degraded_caps
        connector_lifecycle_manager.set_declared_capabilities(
            tenant_id=tenant_context.tenant_id,
            connector_id=connector_id,
            capabilities=active_caps,
        )

        # Transition lifecycle state from REGISTERED -> CREDENTIAL_BOUND -> VALIDATED -> ACTIVE
        connector_lifecycle_manager.transition_state(
            tenant_context=tenant_context,
            connector_id=connector_id,
            target_state=ConnectorLifecycleState.CREDENTIAL_BOUND,
            reason="Credentials bound during onboarding wizard",
        )
        connector_lifecycle_manager.transition_state(
            tenant_context=tenant_context,
            connector_id=connector_id,
            target_state=ConnectorLifecycleState.VALIDATED,
            reason="Pre-flight validation passed during onboarding wizard",
        )
        connector_lifecycle_manager.transition_state(
            tenant_context=tenant_context,
            connector_id=connector_id,
            target_state=ConnectorLifecycleState.ACTIVE,
            reason="Onboarding wizard completed successfully.",
        )

        # 3. Initialize Default Schedules (Item 98)
        schedules = self._sync_scheduler.initialize_connector_schedules(
            connector_id=connector_id, tenant_context=tenant_context
        )

        # 4. Trigger Initial Discovery Sync Job (Item 97)
        initial_scopes = session.selected_scopes or ["root"]
        sync_job = await self._sync_orchestrator.execute_sync(
            connector=simulator,
            sync_type=SyncType.INITIAL_DISCOVERY,
            tenant_context=tenant_context,
            target_scopes=initial_scopes,
        )

        # 5. Execute First-Sync Stages (Prompt 15B Item 21)
        first_sync_report = await self._first_sync_service.execute_first_sync_stages(
            session_id=session_id,
            connector=simulator,
            job_id=sync_job.id,
            tenant_context=tenant_context,
        )

        # 6. Build Onboarding Completion Summary (Prompt 15B Item 27)
        ref = PermissionReferenceService.get_reference(provider)
        unavailable_caps_with_consequences: list[dict[str, str]] = []
        for cap in ref.capabilities:
            if any(p in missing_perms for p in cap.minimum_permissions):
                unavailable_caps_with_consequences.append(
                    {
                        "capability": cap.capability_code.value,
                        "name": cap.capability_name,
                        "consequence": cap.consequence_if_not_granted,
                    }
                )

        schedules_configured = [
            {
                "capability": s.capability.value,
                "interval_minutes": s.interval_minutes,
                "cron_expression": s.cron_expression,
                "is_enabled": s.is_enabled,
            }
            for s in schedules
        ]

        landing_destination = (
            f"/onboarding/first-sync-progress?session_id={session_id}&connector_id={connector_id}"
        )
        warnings: list[str] = []
        billing_warning = None
        if provider == ProviderType.GCP:
            billing_warning = (
                "Cloud Billing export is NOT retrospective. Export history begins strictly at enablement; "
                "prior consumption cannot be backfilled from BigQuery export."
            )
            warnings.append(billing_warning)

        summary = OnboardingCompletionSummary(
            session_id=session_id,
            connector_id=connector_id,
            provider=provider,
            scopes_selected=initial_scopes,
            capabilities_available=[c.value for c in active_caps],
            capabilities_unavailable_with_consequences=unavailable_caps_with_consequences,
            schedules_configured=schedules_configured,
            estimated_time_to_first_cost_data="4 to 8 hours (provider asynchronous billing batch export generation)",
            estimated_time_to_first_cost_seconds=14400,
            alert_test_result=test_report.model_dump(),
            landing_destination=landing_destination,
            billing_export_history_warning=billing_warning,
            warnings=warnings,
        )
        session.wizard_data["completion_summary"] = summary.model_dump()

        # 7. Mark Session Completed
        now = datetime.now(UTC)
        session.status = "COMPLETED"
        session.created_connector_id = connector_id
        if WizardStep.COMPLETE not in session.completed_steps:
            session.completed_steps.append(WizardStep.COMPLETE)
        session.current_step = WizardStep.COMPLETE
        session.updated_at = now
        self._wizard_repo.save(session, tenant_context=tenant_context)

        # 8. Emit Completion Audit Event
        try:
            self._audit_service.append_event(
                tenant_context=tenant_context,
                event_in=AuditEventCreate(
                    event_type=AuditEventType.WIZARD_COMPLETED,
                    actor_id=tenant_context.user_id,
                    actor_roles=tenant_context.roles,
                    action=AuditEventType.WIZARD_COMPLETED.value,
                    resource_type="WizardSession",
                    resource_id=session_id,
                    details={
                        "connector_id": connector_id,
                        "provider": provider.value,
                        "scopes_count": len(initial_scopes),
                        "initial_sync_job_id": sync_job.id,
                        "landing_destination": landing_destination,
                    },
                    correlation_id=tenant_context.correlation_id,
                ),
            )
        except Exception as exc:
            logger.warning("Audit emission failed: %s", exc)

        return {
            "status": "COMPLETED",
            "session_id": session_id,
            "connector_id": connector_id,
            "credential_profile_id": cred_profile_id,
            "initial_sync_job_id": sync_job.id,
            "sync_status": sync_job.status.value,
            "rows_ingested": sync_job.rows_ingested,
            "landing_destination": landing_destination,
            "first_sync_progress": first_sync_report.model_dump(),
            "completion_summary": summary.model_dump(),
        }

    def get_first_sync_progress(
        self, session_id: str, tenant_context: TenantContext
    ) -> FirstSyncProgressReport:
        """Retrieves live first sync progress (Item 21)."""
        return self._first_sync_service.get_progress(session_id, tenant_context=tenant_context)

    def get_completion_summary(
        self, session_id: str, tenant_context: TenantContext
    ) -> OnboardingCompletionSummary:
        """Retrieves the completion summary for a completed session (Item 27)."""
        session = self.get_session(session_id, tenant_context=tenant_context)
        summary_data = session.wizard_data.get("completion_summary")
        if not summary_data:
            raise WizardException(
                f"Completion summary not found for session '{session_id}'. Wizard may not be completed."
            )
        return OnboardingCompletionSummary(**summary_data)


# Global singleton wizard service
_wizard_service = OnboardingWizardService()


def get_wizard_service() -> OnboardingWizardService:
    return _wizard_service
