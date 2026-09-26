"""Authoritative Credential Lifecycle and Secret Management Service (Prompt 12).

Enforces:
- SEC-008 & SEC-009: Secret store integration with reference-only database storage.
  Credential material is written directly to the dedicated SecretStore; application
  entities hold only an opaque reference URI and non-sensitive metadata.
- SEC-010 & SEC-011: Complete credential lifecycle with zero-downtime rotation.
  Validates new credential before persisting and retiring old; active sync runs continue.
- SEC-013: Expiry tracking and alerting at 30, 14, and 3 days.
- SEC-014 & SEC-015: Credential profiles shareable across connectors within a tenant and NEVER across tenants.
- SEC-017: Negative controls - zero credential material reachable through API, logs, exports, or errors.
"""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from domain.credentials.models import (
    CredentialProfile,
    CredentialProfileResponse,
    ExpiryAlert,
)
from domain.credentials.store import SecretStore, get_secret_store
from domain.credentials.validation import CredentialValidator, compute_fingerprint
from domain.models.enums import (
    AlertSeverity,
    AlertStatus,
    CredentialType,
    ProviderType,
    RotationState,
)
from domain.models.exceptions import (
    CredentialExpiredException,
    CredentialNotFoundException,
    CredentialRevokedException,
    CrossTenantCredentialAccessException,
)
from domain.models.governance import Alert, AuditEvent

logger = logging.getLogger(__name__)

# Expiry threshold milestones in days (Item 79)
EXPIRY_THRESHOLDS = [30, 14, 3, 0]


class CredentialService:
    """Manages the end-to-end credential lifecycle and secret store reference mapping."""

    def __init__(self, secret_store: SecretStore | None = None) -> None:
        self._secret_store: SecretStore = secret_store or get_secret_store()
        self._profiles: dict[str, CredentialProfile] = {}
        self._alerts: list[Alert] = []
        self._audit_events: list[AuditEvent] = []
        # Deduplication tracker: (profile_id, threshold_days) -> timestamp
        self._alerted_thresholds: dict[tuple[str, int], datetime] = {}

    # ----------------------------------------------------------------------
    # Item 78: Credential Lifecycle - Create with Pre-Flight Validation
    # ----------------------------------------------------------------------

    def create_profile(
        self,
        tenant_id: str,
        name: str,
        provider: ProviderType,
        credential_type: CredentialType,
        secret_payload: dict[str, Any],
        metadata: dict[str, Any] | None = None,
        expires_at: datetime | None = None,
        actor_id: str = "system",
        correlation_id: str | None = None,
    ) -> CredentialProfile:
        """Provisions a new credential profile.

        Acceptance Criteria:
        A credential that fails validation is never persisted anywhere (not in SecretStore, not in DB).
        """
        corr_id = correlation_id or str(uuid.uuid4())
        safe_meta = metadata or {}

        # 1. Pre-flight validation (Fails fast before writing anywhere)
        CredentialValidator.validate(
            provider=provider,
            credential_type=credential_type,
            secret_payload=secret_payload,
            metadata=safe_meta,
            expires_at=expires_at,
        )

        # 2. Compute non-reversible SHA-256 cryptographic fingerprint
        fingerprint = compute_fingerprint(
            provider=provider,
            credential_type=credential_type,
            secret_payload=secret_payload,
            metadata=safe_meta,
        )

        profile_id = f"cred-{provider.value}-{uuid.uuid4().hex[:12]}"

        # 3. Direct write to dedicated secret store (Reference Pattern - Item 77 / SEC-008)
        secret_ref = self._secret_store.store_secret(
            tenant_id=tenant_id,
            profile_id=profile_id,
            version=1,
            secret_data=secret_payload,
        )

        now = datetime.now(UTC)
        profile = CredentialProfile(
            id=profile_id,
            tenant_id=tenant_id,
            name=name,
            provider=provider,
            credential_type=credential_type,
            secret_ref=secret_ref,
            previous_secret_ref=None,
            fingerprint=fingerprint,
            version=1,
            rotation_state=RotationState.ACTIVE,
            expires_at=expires_at,
            created_at=now,
            updated_at=now,
            last_validated_at=now,
            metadata=safe_meta,
        )

        self._profiles[profile_id] = profile

        # 4. Record audit event (Sanitized metadata only - zero secrets)
        self._record_audit_event(
            tenant_id=tenant_id,
            actor_id=actor_id,
            action="CREDENTIAL_PROFILE_CREATED",
            entity_id=profile_id,
            details={
                "name": name,
                "provider": provider.value,
                "credential_type": credential_type.value,
                "fingerprint": fingerprint,
                "secret_ref": secret_ref,
                "expires_at": expires_at.isoformat() if expires_at else None,
            },
            correlation_id=corr_id,
        )

        logger.info(
            "Credential profile provisioned successfully with reference-only storage",
            extra={
                "tenant_id": tenant_id,
                "profile_id": profile_id,
                "provider": provider.value,
                "fingerprint": fingerprint,
                "correlation_id": corr_id,
            },
        )

        return profile

    # ----------------------------------------------------------------------
    # Item 80: Multi-Tenant Scoping & Cross-Connector Sharing
    # ----------------------------------------------------------------------

    def get_profile(self, tenant_id: str, profile_id: str) -> CredentialProfile:
        """Retrieves credential profile enforcing strict tenant isolation (SEC-014)."""
        profile = self._profiles.get(profile_id)
        if not profile:
            raise CredentialNotFoundException(profile_id=profile_id, tenant_id=tenant_id)

        # Enforce strict cross-tenant boundary (SEC-015)
        if profile.tenant_id != tenant_id:
            logger.warning(
                "Cross-tenant credential access violation detected",
                extra={
                    "caller_tenant_id": tenant_id,
                    "target_profile_id": profile_id,
                    "owner_tenant_id": profile.tenant_id,
                },
            )
            raise CrossTenantCredentialAccessException(
                profile_id=profile_id,
                caller_tenant_id=tenant_id,
                owner_tenant_id=profile.tenant_id,
            )

        return profile

    def list_profiles(
        self,
        tenant_id: str,
        provider: ProviderType | None = None,
    ) -> list[CredentialProfile]:
        """Lists all credential profiles belonging strictly to the specified tenant."""
        return [
            p
            for p in self._profiles.values()
            if p.tenant_id == tenant_id and (provider is None or p.provider == provider)
        ]

    def bind_connector(
        self,
        tenant_id: str,
        profile_id: str,
        connector_id: str,
        actor_id: str = "system",
        correlation_id: str | None = None,
    ) -> CredentialProfile:
        """Binds a connector to a credential profile within the same tenant (Item 80)."""
        corr_id = correlation_id or str(uuid.uuid4())
        profile = self.get_profile(tenant_id, profile_id)

        if connector_id not in profile.connectors_bound:
            profile.connectors_bound.append(connector_id)
            profile.updated_at = datetime.now(UTC)

            self._record_audit_event(
                tenant_id=tenant_id,
                actor_id=actor_id,
                action="CREDENTIAL_CONNECTOR_BOUND",
                entity_id=profile_id,
                details={
                    "connector_id": connector_id,
                    "connectors_bound": profile.connectors_bound,
                },
                correlation_id=corr_id,
            )

        return profile

    def unbind_connector(
        self,
        tenant_id: str,
        profile_id: str,
        connector_id: str,
        actor_id: str = "system",
        correlation_id: str | None = None,
    ) -> CredentialProfile:
        """Unbinds a connector from a credential profile."""
        corr_id = correlation_id or str(uuid.uuid4())
        profile = self.get_profile(tenant_id, profile_id)

        if connector_id in profile.connectors_bound:
            profile.connectors_bound.remove(connector_id)
            profile.updated_at = datetime.now(UTC)

            self._record_audit_event(
                tenant_id=tenant_id,
                actor_id=actor_id,
                action="CREDENTIAL_CONNECTOR_UNBOUND",
                entity_id=profile_id,
                details={
                    "connector_id": connector_id,
                    "connectors_bound": profile.connectors_bound,
                },
                correlation_id=corr_id,
            )

        return profile

    # ----------------------------------------------------------------------
    # Runtime Secret Resolution (Used exclusively by connectors during sync)
    # ----------------------------------------------------------------------

    def resolve_secret_for_connector(
        self,
        tenant_id: str,
        profile_id: str,
        connector_id: str,
        prefer_retiring: bool = False,
    ) -> dict[str, Any]:
        """Resolves raw credential material from SecretStore for a connector executing sync.

        Ensures zero-downtime during rotation: in-flight syncs can resolve the retiring secret
        while new syncs resolve the newly validated secret.
        """
        profile = self.get_profile(tenant_id, profile_id)

        logger.debug(
            "Resolving credential secret for connector sync",
            extra={
                "tenant_id": tenant_id,
                "profile_id": profile_id,
                "connector_id": connector_id,
                "prefer_retiring": prefer_retiring,
            },
        )

        # Enforce lifecycle interlocks
        if profile.rotation_state == RotationState.REVOKED:
            raise CredentialRevokedException(profile_id=profile_id)
        if profile.rotation_state == RotationState.EXPIRED:
            raise CredentialExpiredException(profile_id=profile_id)

        # If rotation is in progress and caller requests retiring secret fallback
        target_ref = profile.secret_ref
        if (
            prefer_retiring
            and profile.rotation_state == RotationState.ROTATING
            and profile.previous_secret_ref
        ):
            target_ref = profile.previous_secret_ref

        # Retrieve strictly from dedicated secret store
        return self._secret_store.get_secret(target_ref)

    # ----------------------------------------------------------------------
    # Item 78: Zero-Downtime Credential Rotation
    # ----------------------------------------------------------------------

    def rotate_credential(
        self,
        tenant_id: str,
        profile_id: str,
        new_secret_payload: dict[str, Any],
        new_metadata: dict[str, Any] | None = None,
        new_expires_at: datetime | None = None,
        actor_id: str = "system",
        correlation_id: str | None = None,
    ) -> CredentialProfile:
        """Rotates a credential profile without connector downtime (SEC-010).

        Zero-Downtime Rotation Algorithm:
        1. Validate new credential BEFORE mutating or retiring old.
        2. If invalid, abort immediately; existing credential remains untouched and active.
        3. Write new credential to SecretStore as version (N + 1).
        4. Retain previous_secret_ref so in-flight sync jobs do not fail.
        5. Transition state to ROTATING until finalized.
        """
        corr_id = correlation_id or str(uuid.uuid4())
        profile = self.get_profile(tenant_id, profile_id)

        if profile.rotation_state == RotationState.REVOKED:
            raise CredentialRevokedException(
                profile_id=profile_id,
                message=f"Cannot rotate revoked credential profile '{profile_id}'. Provision a new profile.",
            )

        merged_meta = dict(profile.metadata)
        if new_metadata:
            merged_meta.update(new_metadata)

        effective_expiry = new_expires_at or profile.expires_at

        # Step 1: Pre-flight validation on the NEW credential material
        CredentialValidator.validate(
            provider=profile.provider,
            credential_type=profile.credential_type,
            secret_payload=new_secret_payload,
            metadata=merged_meta,
            expires_at=effective_expiry,
        )

        # Step 2: Compute new fingerprint
        new_fingerprint = compute_fingerprint(
            provider=profile.provider,
            credential_type=profile.credential_type,
            secret_payload=new_secret_payload,
            metadata=merged_meta,
        )

        # Step 3: Write new version directly to SecretStore
        new_version = profile.version + 1
        new_secret_ref = self._secret_store.store_secret(
            tenant_id=tenant_id,
            profile_id=profile_id,
            version=new_version,
            secret_data=new_secret_payload,
        )

        now = datetime.now(UTC)

        # Step 4: Advance revision with dual-reference window (Zero-Downtime Guarantee)
        profile.previous_secret_ref = profile.secret_ref
        profile.secret_ref = new_secret_ref
        profile.fingerprint = new_fingerprint
        profile.version = new_version
        profile.rotation_state = RotationState.ROTATING
        profile.metadata = merged_meta
        profile.expires_at = effective_expiry
        profile.last_rotated_at = now
        profile.last_validated_at = now
        profile.updated_at = now

        self._record_audit_event(
            tenant_id=tenant_id,
            actor_id=actor_id,
            action="CREDENTIAL_ROTATION_INITIATED",
            entity_id=profile_id,
            details={
                "new_version": new_version,
                "new_fingerprint": new_fingerprint,
                "rotation_state": RotationState.ROTATING.value,
                "connectors_affected": profile.connectors_bound,
            },
            correlation_id=corr_id,
        )

        logger.info(
            "Credential profile rotation initiated in zero-downtime state",
            extra={
                "tenant_id": tenant_id,
                "profile_id": profile_id,
                "new_version": new_version,
                "fingerprint": new_fingerprint,
                "correlation_id": corr_id,
            },
        )

        return profile

    def complete_rotation(
        self,
        tenant_id: str,
        profile_id: str,
        purge_previous: bool = False,
        actor_id: str = "system",
        correlation_id: str | None = None,
    ) -> CredentialProfile:
        """Finalizes rotation: confirms active state and optionally retires previous version (SEC-011)."""
        corr_id = correlation_id or str(uuid.uuid4())
        profile = self.get_profile(tenant_id, profile_id)

        if profile.rotation_state != RotationState.ROTATING:
            return profile

        if purge_previous and profile.previous_secret_ref:
            self._secret_store.delete_secret(profile.previous_secret_ref)
            profile.previous_secret_ref = None

        profile.rotation_state = RotationState.ACTIVE
        profile.updated_at = datetime.now(UTC)

        self._record_audit_event(
            tenant_id=tenant_id,
            actor_id=actor_id,
            action="CREDENTIAL_ROTATION_COMPLETED",
            entity_id=profile_id,
            details={"version": profile.version, "rotation_state": RotationState.ACTIVE.value},
            correlation_id=corr_id,
        )

        return profile

    def retire_credential(
        self,
        tenant_id: str,
        profile_id: str,
        actor_id: str = "system",
        correlation_id: str | None = None,
    ) -> CredentialProfile:
        """Transitions credential to RETIRED state."""
        corr_id = correlation_id or str(uuid.uuid4())
        profile = self.get_profile(tenant_id, profile_id)

        profile.rotation_state = RotationState.RETIRED
        profile.updated_at = datetime.now(UTC)

        self._record_audit_event(
            tenant_id=tenant_id,
            actor_id=actor_id,
            action="CREDENTIAL_PROFILE_RETIRED",
            entity_id=profile_id,
            details={"version": profile.version},
            correlation_id=corr_id,
        )

        return profile

    def revoke_credential(
        self,
        tenant_id: str,
        profile_id: str,
        actor_id: str = "security-guard",
        reason: str = "Emergency security revocation",
        correlation_id: str | None = None,
    ) -> CredentialProfile:
        """Emergency revocation: purges secret from SecretStore and disables connectors immediately."""
        corr_id = correlation_id or str(uuid.uuid4())
        profile = self.get_profile(tenant_id, profile_id)

        # 1. Permanently delete secret material from SecretStore
        self._secret_store.delete_secret(profile.secret_ref)
        if profile.previous_secret_ref:
            self._secret_store.delete_secret(profile.previous_secret_ref)

        now = datetime.now(UTC)
        profile.rotation_state = RotationState.REVOKED
        profile.updated_at = now

        # 2. Raise critical security alert
        alert_msg = (
            f"SECURITY ALERT: Credential profile '{profile.name}' ({profile_id}) for provider "
            f"'{profile.provider.value}' was emergency revoked. Reason: {reason}."
        )
        logger.critical(alert_msg)
        alert = Alert(
            id=f"alt-rev-{uuid.uuid4().hex[:8]}",
            tenant_id=tenant_id,
            alert_type="CREDENTIAL_REVOKED_ALERT",
            severity=AlertSeverity.CRITICAL,
            message=alert_msg,
            status=AlertStatus.ACTIVE,
            triggered_at=now,
        )
        self._alerts.append(alert)

        # 3. Audit trail record
        self._record_audit_event(
            tenant_id=tenant_id,
            actor_id=actor_id,
            action="CREDENTIAL_PROFILE_REVOKED",
            entity_id=profile_id,
            details={
                "reason": reason,
                "connectors_disabled": profile.connectors_bound,
                "purged_secret_ref": profile.secret_ref,
            },
            correlation_id=corr_id,
        )

        return profile

    # ----------------------------------------------------------------------
    # Item 79: Expiry Tracking & Alerting (30, 14, 3 days)
    # ----------------------------------------------------------------------

    def check_expiries(
        self,
        current_time: datetime | None = None,
        tenant_id: str | None = None,
    ) -> list[ExpiryAlert]:
        """Scans all credential profiles and fires alerts at 30, 14, 3 days and expiration (SEC-013)."""
        now = current_time or datetime.now(UTC)
        expiry_alerts: list[ExpiryAlert] = []

        target_profiles = [
            p
            for p in self._profiles.values()
            if (tenant_id is None or p.tenant_id == tenant_id)
            and p.rotation_state in (RotationState.ACTIVE, RotationState.ROTATING)
            and p.expires_at is not None
        ]

        for profile in target_profiles:
            assert profile.expires_at is not None
            delta = profile.expires_at - now
            days_remaining = delta.days

            if days_remaining <= 0:
                # Expired! Transition state and fire CRITICAL alert
                profile.rotation_state = RotationState.EXPIRED
                profile.updated_at = now
                msg = (
                    f"CRITICAL: Credential profile '{profile.name}' ({profile.id}) for provider "
                    f"'{profile.provider.value}' has EXPIRED as of {profile.expires_at.isoformat()}. "
                    "Connector syncs will be suspended until rotated."
                )
                logger.critical(msg)
                exp_alert = ExpiryAlert(
                    profile_id=profile.id,
                    tenant_id=profile.tenant_id,
                    profile_name=profile.name,
                    provider=profile.provider,
                    days_remaining=days_remaining,
                    threshold_days=0,
                    severity=AlertSeverity.CRITICAL,
                    message=msg,
                    triggered_at=now,
                )
                expiry_alerts.append(exp_alert)
                self._record_alert(
                    profile.tenant_id, "CREDENTIAL_EXPIRED", AlertSeverity.CRITICAL, msg, now
                )
                continue

            # Determine the tightest applicable threshold milestone: 3, 14, or 30 days
            applicable_threshold = None
            for threshold in [3, 14, 30]:
                if days_remaining <= threshold:
                    applicable_threshold = threshold
                    break

            if applicable_threshold is not None:
                dedup_key = (profile.id, applicable_threshold)
                if dedup_key not in self._alerted_thresholds:
                    severity = (
                        AlertSeverity.CRITICAL
                        if applicable_threshold == 3
                        else AlertSeverity.WARNING
                    )
                    msg = (
                        f"SECURITY ALERT: Credential profile '{profile.name}' ({profile.id}) for provider "
                        f"'{profile.provider.value}' expires in {days_remaining} days (threshold: {applicable_threshold} days). "
                        "Execute credential rotation to prevent connector synchronization downtime."
                    )
                    logger.warning(msg)
                    alert_item = ExpiryAlert(
                        profile_id=profile.id,
                        tenant_id=profile.tenant_id,
                        profile_name=profile.name,
                        provider=profile.provider,
                        days_remaining=days_remaining,
                        threshold_days=applicable_threshold,
                        severity=severity,
                        message=msg,
                        triggered_at=now,
                    )
                    expiry_alerts.append(alert_item)
                    self._alerted_thresholds[dedup_key] = now
                    self._record_alert(
                        profile.tenant_id, "CREDENTIAL_EXPIRY_WARNING", severity, msg, now
                    )

        return expiry_alerts

    # ----------------------------------------------------------------------
    # Item 82: Safe Export (Negative Controls)
    # ----------------------------------------------------------------------

    def export_profiles(self, tenant_id: str) -> list[CredentialProfileResponse]:
        """Produces a strictly sanitized export containing only references and safe metadata."""
        profiles = self.list_profiles(tenant_id)
        return [
            CredentialProfileResponse(
                id=p.id,
                tenant_id=p.tenant_id,
                name=p.name,
                provider=p.provider,
                credential_type=p.credential_type,
                secret_ref=p.secret_ref,
                fingerprint=p.fingerprint,
                version=p.version,
                rotation_state=p.rotation_state,
                expires_at=p.expires_at,
                created_at=p.created_at,
                updated_at=p.updated_at,
                last_validated_at=p.last_validated_at,
                last_rotated_at=p.last_rotated_at,
                connectors_bound=list(p.connectors_bound),
                metadata=dict(p.metadata),
            )
            for p in profiles
        ]

    # ----------------------------------------------------------------------
    # Internal Helpers
    # ----------------------------------------------------------------------

    def _record_alert(
        self,
        tenant_id: str,
        alert_type: str,
        severity: AlertSeverity,
        message: str,
        timestamp: datetime,
    ) -> None:
        alert = Alert(
            id=f"alt-cred-{uuid.uuid4().hex[:8]}",
            tenant_id=tenant_id,
            alert_type=alert_type,
            severity=severity,
            message=message,
            status=AlertStatus.ACTIVE,
            triggered_at=timestamp,
        )
        self._alerts.append(alert)

    def _record_audit_event(
        self,
        tenant_id: str,
        actor_id: str,
        action: str,
        entity_id: str,
        details: dict[str, Any],
        correlation_id: str,
    ) -> None:
        event = AuditEvent(
            id=f"aud-cred-{uuid.uuid4().hex[:8]}",
            tenant_id=tenant_id,
            action=action,
            actor_id=actor_id,
            entity_type="CredentialProfile",
            entity_id=entity_id,
            payload_after=details,
            correlation_id=correlation_id,
            timestamp=datetime.now(UTC),
        )
        self._audit_events.append(event)


# Global singleton credential service
_global_credential_service: CredentialService | None = None


def get_credential_service(secret_store: SecretStore | None = None) -> CredentialService:
    """Returns singleton CredentialService instance."""
    global _global_credential_service
    if _global_credential_service is None:
        _global_credential_service = CredentialService(secret_store=secret_store)
    return _global_credential_service


def reset_credential_service() -> None:
    """Resets singleton for clean test runs."""
    global _global_credential_service
    _global_credential_service = None
