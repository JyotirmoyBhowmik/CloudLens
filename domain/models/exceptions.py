"""Domain Exceptions for Canonical Domain Models."""

from __future__ import annotations

from typing import Any


class DomainModelException(Exception):
    """Base exception for all domain model violations."""

    def __init__(self, message: str, error_code: str = "DOMAIN_ERROR") -> None:
        super().__init__(message)
        self.message = message
        self.error_code = error_code


class MeasureNullForbiddenException(DomainModelException):
    """Raised when a bare null (None) is provided for a measure instead of an explicit MeasureNullState."""

    def __init__(self, field_name: str = "measure") -> None:
        super().__init__(
            f"Bare null (None) is strictly forbidden for measure '{field_name}'. "
            "You must supply a valid numeric value or an explicit MeasureNullState "
            "(NO_COST, NO_DATA, NOT_APPLICABLE, NOT_SUPPORTED) per BBP Section 15.3.",
            error_code="MEASURE_BARE_NULL_FORBIDDEN",
        )


class MeasureAbsentException(DomainModelException):
    """Raised when accessing .value on an absent measure without providing a fallback."""

    def __init__(self, null_state: str) -> None:
        super().__init__(
            f"Cannot retrieve numeric value from absent measure in state '{null_state}'. "
            "Use .is_present() or .value_or(default).",
            error_code="MEASURE_VALUE_ABSENT",
        )


class InvalidScopeHierarchyException(DomainModelException):
    """Raised when an invalid scope relationship or circular reference is detected."""

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="INVALID_SCOPE_HIERARCHY")


class HistoricalAttributionException(DomainModelException):
    """Raised when point-in-time scope resolution fails."""

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="HISTORICAL_ATTRIBUTION_ERROR")


class CatalogueException(DomainModelException):
    """Base exception for master catalogue violations."""

    def __init__(self, message: str, error_code: str = "CATALOGUE_ERROR") -> None:
        super().__init__(message, error_code=error_code)


class UnitConversionError(CatalogueException):
    """Raised when unit conversion fails or unit is unsupported."""

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="UNIT_CONVERSION_ERROR")


class IncompatibleUnitError(CatalogueException):
    """Raised when attempting to convert across incompatible dimensionalities."""

    def __init__(self, from_unit: str, to_unit: str, from_dim: str, to_dim: str) -> None:
        super().__init__(
            f"Cannot convert '{from_unit}' ({from_dim}) to '{to_unit}' ({to_dim}): incompatible dimensionalities.",
            error_code="INCOMPATIBLE_UNIT_DIMENSIONALITY",
        )


class CatalogueVersioningError(CatalogueException):
    """Raised when catalogue versioning invariants are violated."""

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="CATALOGUE_VERSIONING_ERROR")


class MasterDataException(DomainModelException):
    """Base exception for Master Data Management violations."""

    def __init__(self, message: str, error_code: str = "MASTER_DATA_ERROR") -> None:
        super().__init__(message, error_code=error_code)


class MasterNotRegisteredException(MasterDataException):
    """Raised when operating on a master type not declared in the manifest."""

    def __init__(self, master_type: str) -> None:
        super().__init__(
            f"Master type '{master_type}' is not registered in the system manifest. Nothing may be a master outside the registry.",
            error_code="MASTER_NOT_REGISTERED",
        )


class ReferenceIntegrityBlockedException(MasterDataException):
    """Raised when attempting to delete or deactivate a master value that is currently in use."""

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="REFERENCE_INTEGRITY_BLOCKED")


class CannotDeleteSystemMasterException(MasterDataException):
    """Raised when attempting to delete a shipped system master record."""

    def __init__(self, code: str) -> None:
        super().__init__(
            f"Cannot delete system master value '{code}': shipped system master records cannot be deleted.",
            error_code="CANNOT_DELETE_SYSTEM_MASTER",
        )


class MasterDataApprovalException(MasterDataException):
    """Raised when invalid workflow state transition occurs during master data approval."""

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="MASTER_DATA_APPROVAL_ERROR")


class BootstrapException(DomainModelException):
    """Base exception for system bootstrap violations."""

    def __init__(self, message: str, error_code: str = "BOOTSTRAP_ERROR") -> None:
        super().__init__(message, error_code=error_code)


class SystemAlreadyInitialisedException(BootstrapException):
    """Raised when re-running bootstrap against an already initialized system."""

    def __init__(self, message: str = "System is already initialized.") -> None:
        super().__init__(message, error_code="SYSTEM_ALREADY_INITIALIZED")


class BootstrapIntegrityException(BootstrapException):
    """Raised when bootstrap prerequisites, seed counts, or invariants fail validation."""

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="BOOTSTRAP_INTEGRITY_VIOLATION")


class AttributionException(DomainModelException):
    """Base exception for tag normalisation, ownership resolution, and cost allocation."""

    def __init__(self, message: str, error_code: str = "ATTRIBUTION_ERROR") -> None:
        super().__init__(message, error_code=error_code)


class UnresolvedOwnershipException(AttributionException):
    """Raised when ownership cannot be resolved and strict governance exception is triggered (Prompt 08 Item 56)."""

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="UNRESOLVED_OWNERSHIP")


class AllocationRuleException(AttributionException):
    """Raised when an allocation rule violation occurs."""

    def __init__(self, message: str, error_code: str = "ALLOCATION_RULE_ERROR") -> None:
        super().__init__(message, error_code=error_code)


class InvalidSplitRuleException(AllocationRuleException):
    """Raised when a split allocation rule does not sum to exactly 100% (Prompt 08 Item 57)."""

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="INVALID_SPLIT_RULE_PERCENTAGE")


class CuratedFieldOverwriteException(AttributionException):
    """Raised when re-discovery attempts to overwrite a protected curated field without explicit authorization (Prompt 08 Item 59)."""

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="CURATED_FIELD_OVERWRITE_FORBIDDEN")


class InvalidTagConventionException(AttributionException):
    """Raised when a tag normalization key convention or separator policy is invalid."""

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="INVALID_TAG_CONVENTION")


class DemoModeSafetyException(DomainModelException):
    """Raised when an operation violates Demo Mode safety interlocks (Prompt 47 Item 30)."""

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="DEMO_MODE_SAFETY_VIOLATION")


# ==============================================================================
# Identity, Authentication, and Session Exceptions (Prompt 10)
# ==============================================================================


class IdentityException(DomainModelException):
    """Base exception for identity, authentication, and session violations (Prompt 10)."""

    def __init__(self, message: str, error_code: str = "IDENTITY_ERROR") -> None:
        super().__init__(message, error_code=error_code)


class NoMappedRoleException(IdentityException):
    """Raised when a user's IdP groups map to no role (Prompt 10 Item 69).

    Never defaults to a role; access is denied and an administrator alert is raised.
    """

    def __init__(
        self,
        message: str = "User possesses no mapped platform roles from identity provider groups. Access strictly denied.",
    ) -> None:
        super().__init__(message, error_code="NO_MAPPED_ROLE")


class BreakGlassLimitExceededException(IdentityException):
    """Raised when attempting to provision more break-glass accounts than allowed (Prompt 10 Item 65)."""

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="BREAK_GLASS_LIMIT_EXCEEDED")


class BreakGlassAuthFailedException(IdentityException):
    """Raised when break-glass credentials or mandatory MFA verification fails (Prompt 10 Item 65)."""

    def __init__(
        self,
        message: str = "Break-glass authentication failed: invalid credentials or MFA challenge.",
    ) -> None:
        super().__init__(message, error_code="BREAK_GLASS_AUTH_FAILED")


class TokenRevokedException(IdentityException):
    """Raised when presenting a revoked token or accessing with a disabled user (Prompt 10 Item 66)."""

    def __init__(self, message: str = "Authentication token has been revoked.") -> None:
        super().__init__(message, error_code="TOKEN_REVOKED")


class TokenExpiredException(IdentityException):
    """Raised when an authentication or step-up token has expired (Prompt 10 Item 66)."""

    def __init__(self, message: str = "Authentication token has expired.") -> None:
        super().__init__(message, error_code="TOKEN_EXPIRED")


class TokenInvalidException(IdentityException):
    """Raised when token signature, structure, or claims are invalid (Prompt 10 Item 66)."""

    def __init__(self, message: str = "Invalid authentication token signature or payload.") -> None:
        super().__init__(message, error_code="TOKEN_INVALID")


class SessionExpiredException(IdentityException):
    """Raised when session absolute lifetime or idle timeout is exceeded (Prompt 10 Item 66)."""

    def __init__(
        self,
        message: str = "User session has expired due to inactivity or absolute lifetime limit.",
    ) -> None:
        super().__init__(message, error_code="SESSION_EXPIRED")


class UserDisabledException(IdentityException):
    """Raised when disabled user attempts to access the platform (Prompt 10 Item 66)."""

    def __init__(
        self, message: str = "User account has been disabled. All sessions and tokens revoked."
    ) -> None:
        super().__init__(message, error_code="USER_DISABLED")


class UserNotProvisionedException(IdentityException):
    """Raised when user signs in via SSO but JIT provisioning is disabled and user is not pre-provisioned (Prompt 10 Item 64)."""

    def __init__(
        self,
        message: str = "User account is not pre-provisioned and Just-In-Time provisioning is disabled.",
    ) -> None:
        super().__init__(message, error_code="USER_NOT_PROVISIONED")


class StepUpRequiredException(IdentityException):
    """Raised when high-risk action requires step-up authentication proof (Prompt 10 Item 68)."""

    def __init__(self, action: str, message: str | None = None) -> None:
        msg = message or f"Step-up authentication required for action: '{action}'."
        super().__init__(msg, error_code="STEP_UP_REQUIRED")
        self.action = action


class MachineClientAuthFailedException(IdentityException):
    """Raised when machine client authentication fails (Prompt 10 Item 67)."""

    def __init__(
        self, message: str = "Machine client credentials invalid, expired, or client inactive."
    ) -> None:
        super().__init__(message, error_code="MACHINE_CLIENT_AUTH_FAILED")


class SuperuserException(IdentityException):
    """Base exception for platform superuser governance violations (Prompt 49B)."""

    def __init__(self, message: str, error_code: str = "SUPERUSER_ERROR") -> None:
        super().__init__(message, error_code=error_code)


class SuperuserImmutableException(SuperuserException):
    """Raised when attempting to delete, downgrade, disable MFA, or un-audit the platform superuser (Prompt 49B Item 17)."""

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="SUPERUSER_IMMUTABLE_VIOLATION")


class SuperuserActivationException(SuperuserException):
    """Raised when superuser credential activation fails (Prompt 49B Item 17)."""

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="SUPERUSER_ACTIVATION_FAILED")


class SuperuserRoutineUseException(SuperuserException):
    """Raised when superuser is used for routine operations exceeding delegation limits (Prompt 49B Item 19)."""

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="SUPERUSER_ROUTINE_USE_EXCEEDED")


class RBACException(DomainModelException):
    """Base exception for RBAC and scope authorization failures (Prompt 11)."""

    def __init__(self, message: str, error_code: str = "RBAC_ERROR") -> None:
        super().__init__(message, error_code=error_code)


class PermissionDeniedException(RBACException):
    """Raised when principal lacks a required permission for an action (Prompt 11 Item 70)."""

    def __init__(self, permission: str, message: str | None = None) -> None:
        msg = message or f"Permission denied: Principal lacks required permission '{permission}'."
        super().__init__(msg, error_code="PERMISSION_DENIED")
        self.permission = permission


class ScopeAccessDeniedException(RBACException):
    """Raised when resource access is denied by scope grants or explicit deny (Prompt 11 Item 71-72)."""

    def __init__(
        self, resource_id: str | None, dimension: str | None, message: str | None = None
    ) -> None:
        target = f"resource '{resource_id}'" if resource_id else "requested entity"
        dim = f" on dimension '{dimension}'" if dimension else ""
        msg = message or f"Access to {target} is denied by scope grant policy{dim}."
        super().__init__(msg, error_code="SCOPE_ACCESS_DENIED")
        self.resource_id = resource_id
        self.dimension = dimension


class CustomRoleInvalidException(RBACException):
    """Raised when creating a custom role with invalid or uncatalogued permissions (Prompt 11 Item 70)."""

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="CUSTOM_ROLE_INVALID")


class FinancialDetailAccessDeniedException(RBACException):
    """Raised when user attempts to access raw unit rates or financial details without permission (Prompt 11 Item 73)."""

    def __init__(
        self, message: str = "Access to financial rates and charge line details is restricted."
    ) -> None:
        super().__init__(message, error_code="FINANCIAL_DETAIL_ACCESS_DENIED")


# ==============================================================================
# Secret Management and Credential Lifecycle Exceptions (Prompt 12)
# ==============================================================================


class CredentialException(DomainModelException):
    """Base exception for secret management and credential lifecycle violations (Prompt 12)."""

    def __init__(self, message: str, error_code: str = "CREDENTIAL_ERROR") -> None:
        super().__init__(message, error_code=error_code)


class CredentialValidationException(CredentialException):
    """Raised when provider credential fails pre-flight validation (Prompt 12 Item 78)."""

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="CREDENTIAL_VALIDATION_FAILED")


class CredentialNotFoundException(CredentialException):
    """Raised when requested credential profile does not exist."""

    def __init__(self, profile_id: str, tenant_id: str | None = None) -> None:
        msg = f"Credential profile '{profile_id}' not found" + (
            f" for tenant '{tenant_id}'." if tenant_id else "."
        )
        super().__init__(msg, error_code="CREDENTIAL_NOT_FOUND")
        self.profile_id = profile_id
        self.tenant_id = tenant_id


class CredentialExpiredException(CredentialException):
    """Raised when attempting to execute operations with an expired credential (Prompt 12 Item 79)."""

    def __init__(self, profile_id: str, message: str | None = None) -> None:
        msg = message or f"Credential profile '{profile_id}' has expired and cannot be used."
        super().__init__(msg, error_code="CREDENTIAL_EXPIRED")
        self.profile_id = profile_id


class CredentialRevokedException(CredentialException):
    """Raised when attempting to use a revoked credential profile (Prompt 12 Item 78)."""

    def __init__(self, profile_id: str, message: str | None = None) -> None:
        msg = message or f"Credential profile '{profile_id}' has been revoked."
        super().__init__(msg, error_code="CREDENTIAL_REVOKED")
        self.profile_id = profile_id


class CrossTenantCredentialAccessException(CredentialException):
    """Raised when attempting to access or bind a credential profile across tenant boundaries (Prompt 12 Item 80)."""

    def __init__(self, profile_id: str, caller_tenant_id: str, owner_tenant_id: str) -> None:
        msg = (
            f"Security violation: Tenant '{caller_tenant_id}' attempted to access credential profile "
            f"'{profile_id}' owned by tenant '{owner_tenant_id}'. Cross-tenant credential sharing is strictly prohibited."
        )
        super().__init__(msg, error_code="CROSS_TENANT_CREDENTIAL_ACCESS_DENIED")
        self.profile_id = profile_id
        self.caller_tenant_id = caller_tenant_id
        self.owner_tenant_id = owner_tenant_id


class SecretStoreUnavailableException(CredentialException):
    """Raised when the dedicated secret store backend cannot be reached or fails (Prompt 12 Item 77)."""

    def __init__(self, message: str = "Secret store backend is unavailable.") -> None:
        super().__init__(message, error_code="SECRET_STORE_UNAVAILABLE")


class CredentialRotationInProgressException(CredentialException):
    """Raised when an operation conflicts with an ongoing credential rotation."""

    def __init__(self, profile_id: str) -> None:
        super().__init__(
            f"Credential profile '{profile_id}' is already undergoing rotation.",
            error_code="CREDENTIAL_ROTATION_IN_PROGRESS",
        )
        self.profile_id = profile_id


class TenantContextException(DomainModelException):
    """Base exception for tenant scoping and isolation violations (Prompt 13)."""

    def __init__(self, message: str, error_code: str = "TENANT_CONTEXT_ERROR") -> None:
        super().__init__(message, error_code=error_code)


class MissingTenantContextException(TenantContextException):
    """Raised when repository or service queries are executed without valid tenant context (Prompt 13 Item 84)."""

    def __init__(
        self,
        message: str = "Tenant context is mandatory for data access and cannot be missing or empty.",
    ) -> None:
        super().__init__(message, error_code="MISSING_TENANT_CONTEXT")


class CrossTenantAccessForbiddenException(TenantContextException):
    """Raised when an authenticated caller attempts to reach or manipulate another tenant's data (Prompt 13 Item 83)."""

    def __init__(
        self,
        message: str = "Cross-tenant access forbidden: parameter or identity mismatch with tenant boundary.",
    ) -> None:
        super().__init__(message, error_code="CROSS_TENANT_ACCESS_FORBIDDEN")


class CrossTenantStorageAccessException(TenantContextException):
    """Raised when object storage access attempts cross-tenant directory access (Prompt 13 Item 85)."""

    def __init__(
        self,
        message: str = "Cross-tenant storage access denied: path must be strictly within tenant prefix.",
    ) -> None:
        super().__init__(message, error_code="CROSS_TENANT_STORAGE_ACCESS_DENIED")


class InvalidStoragePathException(TenantContextException):
    """Raised when object storage key contains forbidden directory traversal sequences."""

    def __init__(
        self,
        message: str = "Invalid object storage path: directory traversal or leading slash forbidden.",
    ) -> None:
        super().__init__(message, error_code="INVALID_STORAGE_PATH")


class AuditStreamException(DomainModelException):
    """Base exception for append-only audit stream violations (Prompt 13 Item 86)."""

    def __init__(self, message: str, error_code: str = "AUDIT_STREAM_ERROR") -> None:
        super().__init__(message, error_code=error_code)


class AuditTamperForbiddenException(AuditStreamException):
    """Raised when any user, including Super Admin, attempts to update or delete audit records (Prompt 13 Item 86)."""

    def __init__(
        self,
        message: str = "Audit records are immutable and append-only. Modification or deletion is strictly forbidden (SEC-015). This attempt has been audited.",
    ) -> None:
        super().__init__(message, error_code="AUDIT_TAMPER_FORBIDDEN")


class AuditRecordNotFoundException(AuditStreamException):
    """Raised when an audit record is not found."""

    def __init__(self, event_id: str) -> None:
        super().__init__(
            f"Audit event '{event_id}' not found.", error_code="AUDIT_RECORD_NOT_FOUND"
        )
        self.event_id = event_id


class OverrideException(DomainModelException):
    """Base exception for operational override violations (Prompt 13 Item 87)."""

    def __init__(self, message: str, error_code: str = "OVERRIDE_ERROR") -> None:
        super().__init__(message, error_code=error_code)


class OverrideValidationException(OverrideException):
    """Raised when an override record fails validation of any of the 8 mandatory attributes (Prompt 13 Item 87)."""

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="OVERRIDE_VALIDATION_FAILED")


class PermanentOverrideNotAllowedException(OverrideException):
    """Raised when attempting to create a permanent override without explicit configuration and approval."""

    def __init__(
        self,
        message: str = "Permanent overrides are forbidden without explicit configuration and approved governance reference.",
    ) -> None:
        super().__init__(message, error_code="PERMANENT_OVERRIDE_NOT_ALLOWED")


class OverrideNotFoundException(OverrideException):
    """Raised when the requested override record does not exist."""

    def __init__(self, override_id: str) -> None:
        super().__init__(
            f"Override record '{override_id}' not found.", error_code="OVERRIDE_NOT_FOUND"
        )
        self.override_id = override_id


# ==============================================================================
# Connector & Capability Exceptions (Prompt 14 / BBP Section 26)
# ==============================================================================


class ConnectorException(DomainModelException):
    """Base exception for all connector and provider integration failures."""

    def __init__(self, message: str, error_code: str = "CONNECTOR_ERROR") -> None:
        super().__init__(message, error_code=error_code)


class UndeclaredCapabilityException(ConnectorException):
    """Raised when the platform or client attempts to invoke an undeclared capability."""

    def __init__(self, connector_id: str, capability: str) -> None:
        super().__init__(
            f"Connector '{connector_id}' has not declared capability '{capability}'. "
            "Platform must never invoke undeclared capabilities (Prompt 14 Item 90).",
            error_code="UNDECLARED_CAPABILITY",
        )
        self.connector_id = connector_id
        self.capability = capability


class CapabilityNotSupportedException(ConnectorException):
    """Raised when a connector or provider does not support an operation."""

    def __init__(self, provider: str, capability: str) -> None:
        super().__init__(
            f"Provider '{provider}' does not support capability '{capability}'.",
            error_code="CAPABILITY_NOT_SUPPORTED",
        )
        self.provider = provider
        self.capability = capability


class CapabilityDegradedException(ConnectorException):
    """Raised when attempting to execute a capability currently in DEGRADED or FAILED health."""

    def __init__(self, connector_id: str, capability: str, reason: str) -> None:
        super().__init__(
            f"Capability '{capability}' on connector '{connector_id}' is degraded: {reason}",
            error_code="CAPABILITY_DEGRADED",
        )
        self.connector_id = connector_id
        self.capability = capability
        self.reason = reason


class InvalidConnectorStateTransitionException(ConnectorException):
    """Raised when an invalid lifecycle state transition is attempted."""

    def __init__(self, current_state: str, attempted_state: str) -> None:
        super().__init__(
            f"Invalid connector transition from '{current_state}' to '{attempted_state}'.",
            error_code="INVALID_CONNECTOR_STATE_TRANSITION",
        )
        self.current_state = current_state
        self.attempted_state = attempted_state


class RateLimitExceededException(ConnectorException):
    """Raised when a connector request exceeds token bucket rate limits."""

    def __init__(self, connector_id: str, retry_after: float | None = None) -> None:
        msg = f"Rate limit exceeded for connector '{connector_id}'."
        if retry_after is not None:
            msg += f" Retry after {retry_after:.2f} seconds."
        super().__init__(msg, error_code="RATE_LIMIT_EXCEEDED")
        self.connector_id = connector_id
        self.retry_after = retry_after


class CircuitBreakerOpenException(ConnectorException):
    """Raised when a capability call is rejected because the circuit breaker is OPEN."""

    def __init__(self, connector_id: str, capability: str, recovery_time_seconds: float) -> None:
        super().__init__(
            f"Circuit breaker is OPEN for capability '{capability}' on connector '{connector_id}'. "
            f"Failing fast. Retry in {recovery_time_seconds:.1f}s.",
            error_code="CIRCUIT_BREAKER_OPEN",
        )
        self.connector_id = connector_id
        self.capability = capability
        self.recovery_time_seconds = recovery_time_seconds


class PaginationCheckpointException(ConnectorException):
    """Raised when checkpoint persistence or resumption fails."""

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="PAGINATION_CHECKPOINT_ERROR")


class QuotaExhaustedException(ConnectorException):
    """Raised when hourly API quota for a connector is exhausted."""

    def __init__(self, connector_id: str, hourly_limit: int, resets_at_iso: str) -> None:
        super().__init__(
            f"Hourly quota of {hourly_limit} requests exhausted for connector '{connector_id}'. "
            f"Quota resets at {resets_at_iso}.",
            error_code="QUOTA_EXHAUSTED",
        )
        self.connector_id = connector_id
        self.hourly_limit = hourly_limit
        self.resets_at_iso = resets_at_iso


class RawLandingException(ConnectorException):
    """Raised when landing immutable raw payload to object storage fails."""

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="RAW_LANDING_ERROR")


class ProviderRawErrorException(ConnectorException):
    """Surfaces verbatim provider errors alongside human-readable explanations (Prompt 14 constraint)."""

    def __init__(
        self,
        provider: str,
        capability: str,
        verbatim_error: str,
        plain_language_explanation: str,
        status_code: int | None = None,
    ) -> None:
        super().__init__(
            f"[{provider}:{capability}] Provider error: {verbatim_error} | "
            f"Explanation: {plain_language_explanation}",
            error_code="PROVIDER_RAW_ERROR",
        )
        self.provider = provider
        self.capability = capability
        self.verbatim_error = verbatim_error
        self.plain_language_explanation = plain_language_explanation
        self.status_code = status_code


# ==============================================================================
# Sync Orchestration, Wizard, and Diagnostics Exceptions (Prompt 15)
# ==============================================================================


class SyncJobException(ConnectorException):
    """Base exception for synchronization orchestration and execution errors (Prompt 15)."""

    def __init__(self, message: str, error_code: str = "SYNC_JOB_ERROR") -> None:
        super().__init__(message, error_code=error_code)


class SyncJobExecutionException(SyncJobException):
    """Raised when an active sync run fails fatally across all scopes."""

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="SYNC_JOB_EXECUTION_FAILED")


class SyncJobNotFoundException(SyncJobException):
    """Raised when looking up an unknown sync job identifier."""

    def __init__(self, job_id: str) -> None:
        super().__init__(f"Sync job '{job_id}' not found.", error_code="SYNC_JOB_NOT_FOUND")
        self.job_id = job_id


class IdempotentSyncSkippedException(SyncJobException):
    """Raised when an identical sync job has already completed and duplicate execution is prevented."""

    def __init__(self, idempotency_key: str) -> None:
        super().__init__(
            f"Sync job with idempotency key '{idempotency_key}' already completed. Skipped duplicate run.",
            error_code="IDEMPOTENT_SYNC_SKIPPED",
        )
        self.idempotency_key = idempotency_key


class QuarantineException(SyncJobException):
    """Raised when data fails integrity or schema checks and is sent to dead-letter quarantine."""

    def __init__(self, message: str, reason: str) -> None:
        super().__init__(f"Data quarantined ({reason}): {message}", error_code="DATA_QUARANTINED")
        self.reason = reason


class DataValidationException(SyncJobException):
    """Raised when raw or transformed provider records fail validation rules."""

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="DATA_VALIDATION_ERROR")


class InvalidScheduleIntervalException(SyncJobException):
    """Raised when a connector schedule interval violates bounding rules."""

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="INVALID_SCHEDULE_INTERVAL")


class WizardException(ConnectorException):
    """Base exception for onboarding wizard workflow violations (Prompt 15)."""

    def __init__(self, message: str, error_code: str = "WIZARD_ERROR") -> None:
        super().__init__(message, error_code=error_code)


class InvalidWizardStepException(WizardException):
    """Raised when an onboarding wizard step transition is illegal or out of sequence."""

    def __init__(self, current_step: str, requested_step: str) -> None:
        super().__init__(
            f"Cannot advance wizard step from '{current_step}' to '{requested_step}'.",
            error_code="INVALID_WIZARD_STEP",
        )
        self.current_step = current_step
        self.requested_step = requested_step


class WizardSessionNotFoundException(WizardException):
    """Raised when looking up an unknown onboarding wizard session identifier."""

    def __init__(self, session_id: str) -> None:
        super().__init__(
            f"Wizard session '{session_id}' not found.", error_code="WIZARD_SESSION_NOT_FOUND"
        )
        self.session_id = session_id


class CredentialValidationFailedException(WizardException):
    """Raised when connector credentials fail pre-flight validation (Item 100/101)."""

    def __init__(self, verbatim_error: str, provider: str) -> None:
        super().__init__(
            f"Credential validation failed for {provider}: {verbatim_error}",
            error_code="CREDENTIAL_VALIDATION_FAILED",
        )
        self.verbatim_error = verbatim_error
        self.provider = provider


class ConnectorDegradedException(ConnectorException):
    """Raised when an operation cannot be fulfilled because connector or capability is degraded."""

    def __init__(self, connector_id: str, capability: str, reason: str) -> None:
        super().__init__(
            f"Capability '{capability}' on connector '{connector_id}' is degraded: {reason}",
            error_code="CONNECTOR_DEGRADED",
        )
        self.connector_id = connector_id
        self.capability = capability
        self.reason = reason


class AlertDeliveryFailedException(WizardException):
    """Raised when all alert delivery channels fail during onboarding verification (Prompt 15B Item 24)."""

    def __init__(
        self,
        message: str = "Alert delivery test failed across all configured channels.",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, error_code="ALERT_DELIVERY_FAILED")
        self.details = details or {}


class FirstSyncNotFoundException(WizardException):
    """Raised when first synchronization progress record is not found (Prompt 15B Item 21)."""

    def __init__(self, identifier: str) -> None:
        super().__init__(
            f"First synchronization progress for '{identifier}' not found.",
            error_code="FIRST_SYNC_NOT_FOUND",
        )
        self.identifier = identifier


class PricingException(DomainModelException):
    """Base exception for all pricing catalogue violations (Prompt 20 / Rule 2.2)."""

    def __init__(self, message: str, error_code: str = "PRICING_ERROR") -> None:
        super().__init__(message, error_code=error_code)


class PricingRecordNotFoundException(PricingException):
    """Raised when a pricing record cannot be found for given criteria and effective date."""

    def __init__(
        self,
        provider: str,
        sku: str,
        region: str | None = None,
        date_str: str | None = None,
    ) -> None:
        super().__init__(
            f"No effective pricing record found for provider='{provider}', sku='{sku}', "
            f"region='{region or 'any'}' on date='{date_str or 'current'}'.",
            error_code="PRICING_RECORD_NOT_FOUND",
        )
        self.provider = provider
        self.sku = sku
        self.region = region
        self.date_str = date_str


class PricingSCDConflictException(PricingException):
    """Raised when an illegal slowly changing dimension operation is attempted."""

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="PRICING_SCD_CONFLICT")


class InvalidPricingTierException(PricingException):
    """Raised when tier brackets are invalid (e.g. non-monotonic, negative)."""

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="INVALID_PRICING_TIER")


class InvalidFreeAllowanceException(PricingException):
    """Raised when free allowance structure is invalid or modeled as a boolean."""

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="INVALID_FREE_ALLOWANCE")


class UndefendedFreeStatusException(PricingException):
    """Raised when a FREE pricing status or statement is attempted without defensible conditions (Prompt 21 Item 159)."""

    def __init__(
        self,
        message: str = "A bare 'FREE' status or statement is strictly prohibited without explicit conditions.",
    ) -> None:
        super().__init__(message, error_code="UNDEFENDED_FREE_STATUS")


class IncompatibleCostTypeError(PricingException, TypeError):
    """Raised when incompatible cost source types (e.g. ActualCost and EstimatedCost) are accidentally added or blended (Prompt 21 Item 161)."""

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="INCOMPATIBLE_COST_TYPE")


class MissingTraceabilityException(PricingException):
    """Raised when a pricing or cost statement is generated without source reference or effective date (Prompt 21 Item 162)."""

    def __init__(
        self,
        message: str = "Pricing and cost statements strictly require a source reference and effective date.",
    ) -> None:
        super().__init__(message, error_code="MISSING_TRACEABILITY")


# ==============================================================================
# Cost Ingestion and Normalisation Exceptions (Prompt 22)
# ==============================================================================


class CostException(DomainModelException):
    """Base exception for all cost ingestion and FOCUS normalisation violations (Prompt 22)."""

    def __init__(self, message: str, error_code: str = "COST_ERROR") -> None:
        super().__init__(message, error_code=error_code)


class UnknownSchemaVersionException(CostException):
    """Raised when an unknown dataset schema version is encountered during ingestion (Prompt 22 Item 7).

    STRICT: Halts ingestion and alerts connector. Never guesses a mapping.
    """

    def __init__(self, provider: str, schema_version: str) -> None:
        super().__init__(
            f"Unknown or unsupported billing dataset schema version '{schema_version}' for provider '{provider}'. "
            "Ingestion halted to prevent corrupted cost facts. Guessing a mapping is strictly prohibited.",
            error_code="UNKNOWN_SCHEMA_VERSION",
        )
        self.provider = provider
        self.schema_version = schema_version


class RestatementException(CostException):
    """Raised when a restatement operation fails validation or consistency checks."""

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="RESTATEMENT_ERROR")


class CurrencyConversionException(CostException):
    """Raised when an effective exchange rate cannot be found for query-time conversion."""

    def __init__(self, from_currency: str, to_currency: str, as_of_date: str) -> None:
        super().__init__(
            f"No effective exchange rate found from '{from_currency}' to '{to_currency}' as of '{as_of_date}'.",
            error_code="CURRENCY_CONVERSION_ERROR",
        )
        self.from_currency = from_currency
        self.to_currency = to_currency
        self.as_of_date = as_of_date


# ==============================================================================
# Cost Calculation and Estimation Exceptions (Prompt 23)
# ==============================================================================


class CostCalculationException(CostException):
    """Base exception for cost calculation and pre-deployment estimation violations (Prompt 23)."""

    def __init__(self, message: str, error_code: str = "COST_CALCULATION_ERROR") -> None:
        super().__init__(message, error_code=error_code)


class PricingUnavailableException(CostCalculationException):
    """Raised when pricing cannot be resolved for a requested service/SKU and a strict quote is required."""

    def __init__(self, provider: str, service: str, region: str, reason: str | None = None) -> None:
        msg = f"Pricing unavailable for provider='{provider}', service='{service}', region='{region}'."
        if reason:
            msg += f" Reason: {reason}"
        super().__init__(msg, error_code="PRICING_UNAVAILABLE")
        self.provider = provider
        self.service = service
        self.region = region
        self.reason = reason


class InvalidAssumptionException(CostCalculationException):
    """Raised when user-defined or platform estimation assumptions are invalid."""

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="INVALID_ASSUMPTION")


# ==============================================================================
# Cost Reconciliation Exceptions (Prompt 24)
# ==============================================================================


class ReconciliationException(CostException):
    """Base exception for cost reconciliation and tolerance violations (Prompt 24)."""

    def __init__(self, message: str, error_code: str = "RECONCILIATION_ERROR") -> None:
        super().__init__(message, error_code=error_code)


class ReconciliationReportNotFoundException(ReconciliationException):
    """Raised when a reconciliation report cannot be found."""

    def __init__(self, report_id: str) -> None:
        super().__init__(
            f"Reconciliation report '{report_id}' was not found.",
            error_code="RECONCILIATION_REPORT_NOT_FOUND",
        )
        self.report_id = report_id


class ReconciliationInvestigationNotFoundException(ReconciliationException):
    """Raised when a reconciliation investigation item cannot be found."""

    def __init__(self, item_id: str) -> None:
        super().__init__(
            f"Reconciliation investigation item '{item_id}' was not found.",
            error_code="RECONCILIATION_INVESTIGATION_NOT_FOUND",
        )
        self.item_id = item_id


class ReconciliationPeriodNotClosedException(ReconciliationException):
    """Raised when attempting to execute authoritative reconciliation before period close and finalisation lag."""

    def __init__(self, billing_period: str, provider: str, finalisation_date: str) -> None:
        super().__init__(
            f"Billing period '{billing_period}' for provider '{provider}' is not yet finalized. "
            f"Authoritative finalisation lag requires waiting until '{finalisation_date}'.",
            error_code="RECONCILIATION_PERIOD_NOT_CLOSED",
        )
        self.billing_period = billing_period
        self.provider = provider
        self.finalisation_date = finalisation_date


class ReconciliationAdjustmentForbiddenException(ReconciliationException):
    """Raised when an attempt is made to adjust ingested cost facts to force reconciliation.

    STRICT: Negative constraint in Prompt 24: 'Do not adjust ingested cost data to force a match.'
    """

    def __init__(self, cost_fact_id: str) -> None:
        super().__init__(
            f"Adjustment of cost fact '{cost_fact_id}' to force reconciliation match is strictly prohibited. "
            "Ingested cost data must remain authoritative and immutable.",
            error_code="RECONCILIATION_ADJUSTMENT_FORBIDDEN",
        )
        self.cost_fact_id = cost_fact_id


# ==============================================================================
# Usage & Metric Collection Exceptions (Prompt 25 / BBP Section 19)
# ==============================================================================


class UsageException(DomainModelException):
    """Base domain exception for usage collection and monitoring violations."""

    def __init__(self, message: str, error_code: str = "USAGE_ERROR") -> None:
        super().__init__(message, error_code=error_code)


class SubHourlyCollectionForbiddenException(UsageException):
    """Raised when an attempt is made to configure or collect telemetry at sub-hourly granularity.

    STRICT: Negative constraint in Prompt 25: 'Do not implement sub-hourly collection.'
    """

    def __init__(self, granularity: str | int) -> None:
        super().__init__(
            f"Sub-hourly usage collection ('{granularity}') is strictly prohibited. "
            "CloudLens enforces coarse-grained usage collection (hourly or daily) to prevent "
            "excessive provider API call costs and avoid becoming an operational monitoring platform.",
            error_code="SUB_HOURLY_COLLECTION_FORBIDDEN",
        )
        self.granularity = granularity


class MetricNotApplicableException(UsageException):
    """Raised when attempting to collect or ingest a metric not permitted for the resource's monitoring type.

    STRICT: Negative constraint in Prompt 25: 'Do not collect metrics a monitoring type does not require.'
    """

    def __init__(
        self, metric_name: str, monitoring_type: str, resource_id: str | None = None
    ) -> None:
        target_info = f" on resource '{resource_id}'" if resource_id else ""
        super().__init__(
            f"Metric '{metric_name}' is not permitted for monitoring type '{monitoring_type}'{target_info}. "
            "Cardinality discipline restricts collection strictly to metrics required by the monitoring type.",
            error_code="METRIC_NOT_APPLICABLE",
        )
        self.metric_name = metric_name
        self.monitoring_type = monitoring_type
        self.resource_id = resource_id


class InterpolationLabelRequiredException(UsageException):
    """Raised when attempting to interpolate a telemetry gap without an explicit label.

    STRICT: Negative constraint in Prompt 25: 'Do not interpolate a gap without labelling it.'
    """

    def __init__(self) -> None:
        super().__init__(
            "Interpolation of telemetry gaps must be explicitly labeled. "
            "Silent gap interpolation is forbidden per Prompt 25 cardinality and truth discipline.",
            error_code="INTERPOLATION_LABEL_REQUIRED",
        )


class ExpectationNotFoundException(UsageException):
    """Raised when a usage expectation cannot be found."""

    def __init__(self, expectation_id: str) -> None:
        super().__init__(
            f"Usage expectation '{expectation_id}' was not found.",
            error_code="EXPECTATION_NOT_FOUND",
        )
        self.expectation_id = expectation_id


class MonitoringTypeNotFoundException(UsageException):
    """Raised when an unknown monitoring type is referenced."""

    def __init__(self, monitoring_type: str) -> None:
        super().__init__(
            f"Monitoring type '{monitoring_type}' is invalid or unknown. "
            "Supported types are MT-01 through MT-15.",
            error_code="MONITORING_TYPE_NOT_FOUND",
        )
        self.monitoring_type = monitoring_type


# ==============================================================================
# Runtime Model and Schedule Adherence Exceptions (Prompt 26)
# ==============================================================================


class RuntimeException(DomainModelException):
    """Base exception for runtime model, schedule adherence, and exemption operations (Prompt 26)."""

    def __init__(self, message: str, error_code: str = "RUNTIME_ERROR") -> None:
        super().__init__(message, error_code=error_code)


class ScheduleNotFoundException(RuntimeException):
    """Raised when an operational runtime schedule cannot be found."""

    def __init__(self, schedule_id: str) -> None:
        super().__init__(
            f"Runtime schedule '{schedule_id}' was not found.",
            error_code="SCHEDULE_NOT_FOUND",
        )
        self.schedule_id = schedule_id


class ExemptionNotFoundException(RuntimeException):
    """Raised when a runtime exemption cannot be found."""

    def __init__(self, exemption_id: str) -> None:
        super().__init__(
            f"Runtime exemption '{exemption_id}' was not found.",
            error_code="EXEMPTION_NOT_FOUND",
        )
        self.exemption_id = exemption_id


class InvalidScheduleException(RuntimeException):
    """Raised when a schedule specification has invalid parameters."""

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="INVALID_SCHEDULE")


class ExemptionReasonTooShortException(RuntimeException):
    """Raised when an exemption reason is below the mandatory minimum length (>= 20 chars)."""

    def __init__(self, length: int, min_length: int = 20) -> None:
        super().__init__(
            f"Exemption justification must be at least {min_length} characters (provided {length}). "
            "Mandatory audit discipline requires substantive business rationale.",
            error_code="EXEMPTION_REASON_TOO_SHORT",
        )


class ExemptionExpiredException(RuntimeException):
    """Raised when attempting to activate or apply an expired exemption."""

    def __init__(self, exemption_id: str) -> None:
        super().__init__(
            f"Runtime exemption '{exemption_id}' has expired and cannot be applied.",
            error_code="EXEMPTION_EXPIRED",
        )
        self.exemption_id = exemption_id


class ScheduleBreachValuationException(RuntimeException):
    """Raised when a schedule breach is generated without a valid monetary valuation.

    Prompt 26 Negative Constraint: 'Do not raise a schedule exception without a monetary value.'
    """

    def __init__(self, resource_id: str) -> None:
        super().__init__(
            f"Schedule breach for resource '{resource_id}' cannot be computed without a monetary valuation. "
            "Every schedule exception must carry a defensible monetary value.",
            error_code="SCHEDULE_BREACH_VALUATION_MISSING",
        )
        self.resource_id = resource_id


class IdleDetectionDisabledException(RuntimeException):
    """Raised when idle detection is invoked while the feature flag is disabled.

    Prompt 26 Negative Constraint: 'Do not enable idle detection in MVP.'
    """

    def __init__(self) -> None:
        super().__init__(
            "Idle and underutilisation detection is a Phase 2 feature and is disabled in MVP.",
            error_code="IDLE_DETECTION_DISABLED",
        )


class RuntimeStateNonComplianceException(RuntimeException):
    """Raised when an invalid runtime state compliance or color rendering is attempted.

    Prompt 26 Strict Rule: 'Enforce that Unknown and No Data are never rendered as compliant and never coloured green.'
    """

    def __init__(self, state: str, detail: str) -> None:
        super().__init__(
            f"Runtime state '{state}' violation: {detail}. "
            "Unknown and No Data must never be rendered as compliant and never coloured green.",
            error_code="RUNTIME_STATE_NON_COMPLIANCE",
        )


# ==============================================================================
# Threshold Engine Exceptions (Prompt 27)
# ==============================================================================


class ThresholdException(DomainModelException):
    """Base exception for threshold engine, evaluation, and anti-flapping (Prompt 27)."""

    def __init__(self, message: str, error_code: str = "THRESHOLD_ERROR") -> None:
        super().__init__(message, error_code=error_code)


class ThresholdRuleNotFoundException(ThresholdException):
    """Raised when a referenced threshold rule cannot be found."""

    def __init__(self, rule_id: str) -> None:
        super().__init__(
            f"Threshold rule '{rule_id}' was not found.",
            error_code="THRESHOLD_RULE_NOT_FOUND",
        )
        self.rule_id = rule_id


class InvalidThresholdBandsException(ThresholdException):
    """Raised when threshold band definitions fail contiguity or overlap validation."""

    def __init__(self, message: str, error_code: str = "INVALID_THRESHOLD_BANDS") -> None:
        super().__init__(message, error_code=error_code)


class BandOverlapException(InvalidThresholdBandsException):
    """Raised when threshold bands overlap.

    Prompt 27 Rule: 'Bands are contiguous and non-overlapping, rejected at save time if not.'
    """

    def __init__(self, band1_name: str, band2_name: str, detail: str) -> None:
        super().__init__(
            f"Threshold bands '{band1_name}' and '{band2_name}' overlap: {detail}. "
            "Bands must be strictly non-overlapping and contiguous.",
            error_code="BAND_OVERLAP_DETECTED",
        )


class BandDiscontinuityException(InvalidThresholdBandsException):
    """Raised when threshold bands have gaps/holes between boundaries."""

    def __init__(self, band1_name: str, band2_name: str, gap_detail: str) -> None:
        super().__init__(
            f"Discontinuity between band '{band1_name}' and '{band2_name}': {gap_detail}. "
            "Bands must form a contiguous uninterrupted partition.",
            error_code="BAND_DISCONTINUITY_DETECTED",
        )


class ThresholdOverrideNotFoundException(ThresholdException):
    """Raised when a threshold override cannot be found."""

    def __init__(self, override_id: str) -> None:
        super().__init__(
            f"Threshold override '{override_id}' was not found.",
            error_code="THRESHOLD_OVERRIDE_NOT_FOUND",
        )
        self.override_id = override_id


class ThresholdOverrideExpiredException(ThresholdException):
    """Raised when attempting to apply an expired threshold override."""

    def __init__(self, override_id: str) -> None:
        super().__init__(
            f"Threshold override '{override_id}' has expired.",
            error_code="THRESHOLD_OVERRIDE_EXPIRED",
        )
        self.override_id = override_id


class ThresholdOverrideReasonTooShortException(ThresholdException):
    """Raised when an override justification does not satisfy the mandatory length (>= 20 chars)."""

    def __init__(self, length: int, min_length: int = 20) -> None:
        super().__init__(
            f"Threshold override justification must be at least {min_length} characters (provided {length}). "
            "Substantive business rationale is required for auditability.",
            error_code="THRESHOLD_OVERRIDE_REASON_TOO_SHORT",
        )


class ThresholdPreviewDisabledException(ThresholdException):
    """Raised when threshold preview simulation is requested while the feature flag is disabled."""

    def __init__(self) -> None:
        super().__init__(
            "Threshold preview and historical simulation is a Phase 2 capability and is disabled in MVP.",
            error_code="THRESHOLD_PREVIEW_DISABLED",
        )


# ==============================================================================
# Quota & Service Limits Exceptions (Prompt 54)
# ==============================================================================


class QuotaException(DomainModelException):
    """Base exception for quota, service limit, and headroom domain errors."""

    def __init__(self, message: str, error_code: str = "QUOTA_ERROR") -> None:
        super().__init__(message, error_code=error_code)


class QuotaNotFoundException(QuotaException):
    """Raised when a requested cloud quota record is not found."""

    def __init__(self, quota_id: str) -> None:
        super().__init__(
            f"Quota '{quota_id}' was not found.",
            error_code="QUOTA_NOT_FOUND",
        )
        self.quota_id = quota_id


class QuotaNotSupportedException(QuotaException):
    """Raised when attempting an operation on a quota that the provider does not expose programmatically."""

    def __init__(self, quota_code: str, provider: str) -> None:
        super().__init__(
            f"Quota '{quota_code}' is Not Supported by provider '{provider}'. "
            "Unknown provider quotas must render as Not Supported, never as unlimited and never as zero.",
            error_code="QUOTA_NOT_SUPPORTED",
        )
        self.quota_code = quota_code
        self.provider = provider


class QuotaIncreaseRequestNotFoundException(QuotaException):
    """Raised when a quota increase request record cannot be found."""

    def __init__(self, request_id: str) -> None:
        super().__init__(
            f"Quota increase request '{request_id}' was not found.",
            error_code="QUOTA_INCREASE_REQUEST_NOT_FOUND",
        )
        self.request_id = request_id


class InvalidQuotaLimitException(QuotaException):
    """Raised when a manual or ingested quota limit value is invalid."""

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="INVALID_QUOTA_LIMIT")


class ManualQuotaSourceNoteRequiredException(QuotaException):
    """Raised when manually entering a quota limit without the mandatory source note."""

    def __init__(self, message: str | None = None) -> None:
        msg = (
            message
            or "Manually recorded quota limits require a mandatory source note describing origin and authority."
        )
        super().__init__(
            msg,
            error_code="MANUAL_QUOTA_SOURCE_NOTE_REQUIRED",
        )


# ==============================================================================
# Budget Model & Allocation Exceptions (Prompt 28)
# ==============================================================================


class BudgetException(DomainModelException):
    """Base exception for budget model and allocation violations (Prompt 28)."""

    def __init__(self, message: str, error_code: str = "BUDGET_ERROR") -> None:
        super().__init__(message, error_code=error_code)


class BudgetNotFoundException(BudgetException):
    """Raised when the requested budget cannot be found."""

    def __init__(self, budget_id: str) -> None:
        super().__init__(
            f"Budget '{budget_id}' was not found.",
            error_code="BUDGET_NOT_FOUND",
        )
        self.budget_id = budget_id


class BudgetPendingApprovalException(BudgetException):
    """Raised when attempting to activate a budget exceeding the approval limit without approval."""

    def __init__(self, budget_id: str, amount: float, threshold: float) -> None:
        super().__init__(
            f"Budget '{budget_id}' amount ({amount:,.2f}) exceeds the approval threshold ({threshold:,.2f}) "
            "and cannot become active without a recorded formal approval decision.",
            error_code="BUDGET_PENDING_APPROVAL",
        )
        self.budget_id = budget_id
        self.amount = amount
        self.threshold = threshold


class BudgetApprovalNotAllowedException(BudgetException):
    """Raised when approval or rejection cannot be performed on a budget."""

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="BUDGET_APPROVAL_NOT_ALLOWED")


class InvalidBudgetAmountException(BudgetException):
    """Raised when a budget amount is negative or non-positive."""

    def __init__(self, amount: float) -> None:
        super().__init__(
            f"Budget amount must be strictly greater than zero; got {amount}.",
            error_code="INVALID_BUDGET_AMOUNT",
        )
        self.amount = amount


class BudgetTemplateNotFoundException(BudgetException):
    """Raised when the requested budget template does not exist."""

    def __init__(self, template_code: str) -> None:
        super().__init__(
            f"Budget template '{template_code}' was not found.",
            error_code="BUDGET_TEMPLATE_NOT_FOUND",
        )
        self.template_code = template_code


class NativeBudgetReadOnlyException(BudgetException):
    """Raised when attempting to modify, amend, approve, or delete a provider-imported budget."""

    def __init__(self, budget_id: str, provider: str | None = None) -> None:
        super().__init__(
            f"Budget '{budget_id}' is a provider-native budget imported from {provider or 'cloud provider'}. "
            "Native budgets are read-only for comparison and cannot be mutated through CloudLens.",
            error_code="NATIVE_BUDGET_READ_ONLY",
        )
        self.budget_id = budget_id
        self.provider = provider


class InvalidBudgetDatesException(BudgetException):
    """Raised when budget dates are invalid (e.g. expiry before effective)."""

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="INVALID_BUDGET_DATES")


# ==============================================================================
# Forecasting Engine Exceptions (Prompt 29)
# ==============================================================================


class ForecastingException(DomainModelException):
    """Base exception for all forecasting domain errors."""


class InsufficientHistoryException(ForecastingException):
    """Raised when data history is strictly insufficient for a method without fallback."""

    def __init__(self, method: str, required_days: int, actual_days: int) -> None:
        super().__init__(
            f"Forecast method '{method}' requires at least {required_days} days of history; only {actual_days} days provided.",
            error_code="INSUFFICIENT_FORECAST_HISTORY",
        )
        self.method = method
        self.required_days = required_days
        self.actual_days = actual_days


class ForecastNotFoundException(ForecastingException):
    """Raised when a requested forecast entity cannot be located."""

    def __init__(self, forecast_id: str) -> None:
        super().__init__(
            f"Forecast '{forecast_id}' was not found.",
            error_code="FORECAST_NOT_FOUND",
        )
        self.forecast_id = forecast_id


class FeatureFlagDisabledException(ForecastingException):
    """Raised when a Phase 2 forecast method is invoked while its feature flag is disabled."""

    def __init__(self, flag_key: str, method: str) -> None:
        super().__init__(
            f"Phase 2 forecast method '{method}' is disabled because feature flag '{flag_key}' is not active.",
            error_code="FEATURE_FLAG_DISABLED",
        )
        self.flag_key = flag_key
        self.method = method


class ForecastAccuracyEvaluationException(ForecastingException):
    """Raised when an error occurs during milestone accuracy evaluation."""

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="FORECAST_ACCURACY_EVALUATION_ERROR")


# ==============================================================================
# Policy Engine Exceptions (Prompt 30)
# ==============================================================================


class PolicyException(DomainModelException):
    """Base exception for all policy engine domain errors."""


class PolicyNotFoundException(PolicyException):
    """Raised when a requested policy definition cannot be found."""

    def __init__(self, policy_id: str) -> None:
        super().__init__(
            f"Policy '{policy_id}' was not found.",
            error_code="POLICY_NOT_FOUND",
        )
        self.policy_id = policy_id


class PolicyValidationException(PolicyException):
    """Raised when a policy definition has invalid conditions, syntax, or attributes."""

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="INVALID_POLICY_DEFINITION")


class InvalidExemptionException(PolicyException):
    """Raised when a policy exemption violates mandatory justification or expiry rules."""

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="INVALID_POLICY_EXEMPTION")


class PolicyConditionEvaluationException(PolicyException):
    """Raised when an unrecoverable runtime evaluation failure occurs."""

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="POLICY_EVALUATION_ERROR")


class DuplicatePolicyException(PolicyException):
    """Raised when creating a policy with an ID that already exists."""

    def __init__(self, policy_id: str) -> None:
        super().__init__(
            f"Policy '{policy_id}' already exists in registry.",
            error_code="DUPLICATE_POLICY",
        )
        self.policy_id = policy_id


# ==============================================================================
# Alerting & Notification Exceptions (Prompt 31)
# ==============================================================================


class AlertException(DomainModelException):
    """Base exception for all alerting domain errors."""


class AlertNotFoundException(AlertException):
    """Raised when an alert entity is not found."""

    def __init__(self, alert_id: str) -> None:
        super().__init__(
            f"Alert '{alert_id}' was not found.",
            error_code="ALERT_NOT_FOUND",
        )
        self.alert_id = alert_id


class MissingAlertEvidenceException(AlertException):
    """Raised when an alert is constructed or dispatched without empirical evidence."""

    def __init__(
        self,
        message: str = "Alert cannot be generated without empirical evidence. Raising an alert without evidence is strictly forbidden.",
    ) -> None:
        super().__init__(
            message,
            error_code="MISSING_ALERT_EVIDENCE",
        )


class ChannelNotSupportedException(AlertException):
    """Raised when an unsupported or forbidden channel (e.g. SMS, Voice) is requested."""

    def __init__(self, channel: str) -> None:
        super().__init__(
            f"Channel '{channel}' is not supported. SMS and Voice channels are strictly forbidden: "
            "CloudLens is a cloud governance and FinOps platform, not an incident response paging system.",
            error_code="CHANNEL_NOT_SUPPORTED",
        )
        self.channel = channel


class DeliveryFailedException(AlertException):
    """Raised when outbound alert delivery fails across all attempts."""

    def __init__(self, channel: str, recipient: str, reason: str) -> None:
        super().__init__(
            f"Failed to deliver alert to recipient '{recipient}' via channel '{channel}': {reason}",
            error_code="ALERT_DELIVERY_FAILED",
        )
        self.channel = channel
        self.recipient = recipient
        self.reason = reason


class ContextualAlertNotFoundException(AlertException):
    """Raised when a contextual inline alert is not found."""

    def __init__(self, alert_id: str) -> None:
        super().__init__(
            f"Contextual alert '{alert_id}' was not found.",
            error_code="CONTEXTUAL_ALERT_NOT_FOUND",
        )
        self.alert_id = alert_id


class InvalidSubscriptionException(AlertException):
    """Raised when an alert subscription rule violates validation constraints."""

    def __init__(self, message: str) -> None:
        super().__init__(
            message,
            error_code="INVALID_ALERT_SUBSCRIPTION",
        )


class AlertValidationException(AlertException):
    """Raised when alert entity validation fails."""

    def __init__(self, message: str) -> None:
        super().__init__(
            message,
            error_code="ALERT_VALIDATION_ERROR",
        )


# ==============================================================================
# Workflow & Approval Engine Exceptions (Prompt 50)
# ==============================================================================


class WorkflowException(DomainModelException):
    """Base exception for all workflow and approval engine errors (Prompt 50)."""

    def __init__(self, message: str, error_code: str = "WORKFLOW_ERROR") -> None:
        super().__init__(message, error_code=error_code)


class WorkflowNotFoundException(WorkflowException):
    """Raised when a requested workflow request does not exist."""

    def __init__(self, request_id: str) -> None:
        super().__init__(
            f"Workflow request '{request_id}' was not found.",
            error_code="WORKFLOW_NOT_FOUND",
        )
        self.request_id = request_id


class WorkflowDefinitionNotFoundException(WorkflowException):
    """Raised when a workflow definition is not found for a request type."""

    def __init__(self, request_type: str) -> None:
        super().__init__(
            f"No workflow definition registered for request type '{request_type}'.",
            error_code="WORKFLOW_DEFINITION_NOT_FOUND",
        )
        self.request_type = request_type


class NoResolvableApproverException(WorkflowException):
    """Governance exception raised when no approver can be resolved (Prompt 50).

    Prevents requests from silently vanishing.
    """

    def __init__(self, request_id: str, stage_name: str, resolution_type: str) -> None:
        super().__init__(
            f"Governance exception: No approver could be resolved for workflow request '{request_id}' "
            f"at stage '{stage_name}' using resolution '{resolution_type}', and fallback exhausted.",
            error_code="NO_RESOLVABLE_APPROVER_EXCEPTION",
        )
        self.request_id = request_id
        self.stage_name = stage_name
        self.resolution_type = resolution_type


class InvalidWorkflowTransitionException(WorkflowException):
    """Raised when an illegal workflow state transition is attempted."""

    def __init__(self, request_id: str, current_state: str, attempted_state: str) -> None:
        super().__init__(
            f"Cannot transition workflow '{request_id}' from state '{current_state}' to '{attempted_state}'.",
            error_code="INVALID_WORKFLOW_TRANSITION",
        )
        self.request_id = request_id
        self.current_state = current_state
        self.attempted_state = attempted_state


class WorkflowApplicationFailedException(WorkflowException):
    """Raised when an approved change fails to apply atomically."""

    def __init__(self, request_id: str, reason: str) -> None:
        super().__init__(
            f"Failed to apply approved change for workflow '{request_id}': {reason}",
            error_code="WORKFLOW_APPLICATION_FAILED",
        )
        self.request_id = request_id
        self.reason = reason


class UnauthorizedApproverException(WorkflowException):
    """Raised when an actor is not authorized to approve the current stage."""

    def __init__(self, request_id: str, actor_id: str, stage_name: str) -> None:
        super().__init__(
            f"Actor '{actor_id}' is not an authorized approver or delegate for request '{request_id}' at stage '{stage_name}'.",
            error_code="UNAUTHORIZED_APPROVER",
        )
        self.request_id = request_id
        self.actor_id = actor_id
        self.stage_name = stage_name


class WorkflowMandatoryCommentException(WorkflowException):
    """Raised when rejecting a request without a mandatory comment."""

    def __init__(self, request_id: str) -> None:
        super().__init__(
            f"A mandatory comment is required when rejecting workflow request '{request_id}'.",
            error_code="WORKFLOW_MANDATORY_COMMENT_REQUIRED",
        )
        self.request_id = request_id


class WorkflowDelegationExpiredException(WorkflowException):
    """Raised when attempting to act on an expired delegation."""

    def __init__(self, delegation_id: str) -> None:
        super().__init__(
            f"Delegation '{delegation_id}' is expired or inactive.",
            error_code="WORKFLOW_DELEGATION_EXPIRED",
        )
        self.delegation_id = delegation_id


class WorkflowAlreadyFinalizedException(WorkflowException):
    """Raised when attempting to modify a finalized workflow request."""

    def __init__(self, request_id: str, state: str) -> None:
        super().__init__(
            f"Workflow request '{request_id}' is already finalized in state '{state}' and cannot be altered.",
            error_code="WORKFLOW_ALREADY_FINALIZED",
        )
        self.request_id = request_id
        self.state = state


# ==============================================================================
# Remediation and Accountability Engine Exceptions (Prompt 51)
# ==============================================================================


class RemediationException(DomainModelException):
    """Base exception for remediation tasks and accountability failures (Prompt 51)."""

    def __init__(self, message: str, error_code: str = "REMEDIATION_ERROR") -> None:
        super().__init__(message, error_code=error_code)


class RemediationTaskNotFoundException(RemediationException):
    """Raised when a requested remediation task does not exist."""

    def __init__(self, task_id: str) -> None:
        super().__init__(
            f"Remediation task '{task_id}' was not found in the current tenant context.",
            error_code="REMEDIATION_TASK_NOT_FOUND",
        )
        self.task_id = task_id


class NoResolvableAssigneeException(RemediationException):
    """Raised when ownership resolution and fallback queues all fail to resolve an assignee."""

    def __init__(self, entity_id: str, details: str = "") -> None:
        super().__init__(
            f"No accountable owner or fallback queue could be resolved for entity '{entity_id}'. {details}",
            error_code="NO_RESOLVABLE_ASSIGNEE",
        )
        self.entity_id = entity_id


class InvalidTaskTransitionException(RemediationException):
    """Raised when attempting an illegal state transition on a remediation task."""

    def __init__(self, task_id: str, from_state: str, to_state: str) -> None:
        super().__init__(
            f"Cannot transition remediation task '{task_id}' from '{from_state}' to '{to_state}'.",
            error_code="INVALID_TASK_TRANSITION",
        )
        self.task_id = task_id
        self.from_state = from_state
        self.to_state = to_state


class MandatoryReasonException(RemediationException):
    """Raised when rejecting, deferring, or overriding a task without a mandatory justification."""

    def __init__(self, action: str) -> None:
        super().__init__(
            f"A mandatory reason code/justification is required to perform '{action}'.",
            error_code="MANDATORY_REASON_REQUIRED",
        )
        self.action = action


class TaskAlreadyClosedException(RemediationException):
    """Raised when attempting to modify an already closed or terminal remediation task."""

    def __init__(self, task_id: str, state: str) -> None:
        super().__init__(
            f"Remediation task '{task_id}' is in terminal state '{state}' and cannot be altered.",
            error_code="TASK_ALREADY_CLOSED",
        )
        self.task_id = task_id
        self.state = state


class VerificationFailedException(RemediationException):
    """Raised when automated condition verification fails for a resolved task."""

    def __init__(self, task_id: str, reason: str) -> None:
        super().__init__(
            f"Automated verification for task '{task_id}' failed: {reason}",
            error_code="VERIFICATION_FAILED",
        )
        self.task_id = task_id
        self.reason = reason


# ==============================================================================
# Dependency & Topology Exceptions (Prompt 32 / BBP Section 24)
# ==============================================================================


class DependencyException(DomainModelException):
    """Base exception for all dependency and topology graph errors."""

    def __init__(self, message: str, error_code: str = "DEPENDENCY_ERROR") -> None:
        super().__init__(message, error_code=error_code)


class DependencyEdgeNotFoundException(DependencyException):
    """Raised when a requested dependency edge does not exist."""

    def __init__(self, edge_id: str) -> None:
        super().__init__(
            f"Dependency edge '{edge_id}' was not found.",
            error_code="DEPENDENCY_EDGE_NOT_FOUND",
        )
        self.edge_id = edge_id


class DependencyConflictException(DependencyException):
    """Raised when a conflict between manual and discovered edges occurs or cannot be reconciled."""

    def __init__(self, conflict_id: str, reason: str) -> None:
        super().__init__(
            f"Dependency conflict '{conflict_id}': {reason}",
            error_code="DEPENDENCY_CONFLICT_ERROR",
        )
        self.conflict_id = conflict_id
        self.reason = reason


class InvalidEdgeReferenceException(DependencyException):
    """Raised when source or target entity reference is malformed or invalid."""

    def __init__(self, ref_str: str, reason: str) -> None:
        super().__init__(
            f"Invalid dependency entity reference '{ref_str}': {reason}",
            error_code="INVALID_EDGE_REFERENCE",
        )
        self.ref_str = ref_str


class CyclicDependencyException(DependencyException):
    """Raised when an illegal dependency cycle is detected during strict acyclic validation."""

    def __init__(self, cycle_path: list[str]) -> None:
        path_str = " -> ".join(cycle_path)
        super().__init__(
            f"Cyclic dependency detected: {path_str}",
            error_code="CYCLIC_DEPENDENCY_DETECTED",
        )
        self.cycle_path = cycle_path


class NamingInferenceRuleException(DependencyException):
    """Raised when a naming convention inference rule is invalid or produces invalid edges."""

    def __init__(self, rule_name: str, reason: str) -> None:
        super().__init__(
            f"Naming inference rule '{rule_name}' error: {reason}",
            error_code="NAMING_INFERENCE_RULE_ERROR",
        )
        self.rule_name = rule_name


class ManualEdgeProtectedException(DependencyException):
    """Raised when a discovered edge attempts to silently overwrite a manual edge."""

    def __init__(self, edge_id: str) -> None:
        super().__init__(
            f"Manual edge '{edge_id}' is protected from automated overwriting. Conflict must be surfaced.",
            error_code="MANUAL_EDGE_PROTECTED",
        )
        self.edge_id = edge_id


# ==============================================================================
# Cost-Aware Topology & Graph Projection Exceptions (Prompt 33)
# ==============================================================================


class TopologyException(DomainModelException):
    """Base domain exception for cost-aware topology and graph projection."""

    def __init__(
        self,
        message: str,
        error_code: str = "TOPOLOGY_ERROR",
        status_code: int = 400,
    ) -> None:
        super().__init__(message, error_code=error_code)
        self.status_code = status_code


class TopologyViewNotFoundException(TopologyException):
    """Raised when an unrecognized or unregistered topology view type is requested."""

    def __init__(self, view_type: str) -> None:
        super().__init__(
            f"Topology view type '{view_type}' not found or not supported.",
            error_code="TOPOLOGY_VIEW_NOT_FOUND",
            status_code=404,
        )
        self.view_type = view_type


class RootNodeNotFoundException(TopologyException):
    """Raised when a required root entity for graph projection cannot be resolved."""

    def __init__(self, entity_id: str, view_type: str) -> None:
        super().__init__(
            f"Root node '{entity_id}' could not be resolved for view '{view_type}'.",
            error_code="ROOT_NODE_NOT_FOUND",
            status_code=404,
        )
        self.entity_id = entity_id
        self.view_type = view_type


class InvalidTraversalDepthException(TopologyException):
    """Raised when traversal depth is out of acceptable bounds."""

    def __init__(self, depth: int, max_allowed: int = 10) -> None:
        super().__init__(
            f"Traversal depth {depth} is invalid. Must be between 1 and {max_allowed}.",
            error_code="INVALID_TRAVERSAL_DEPTH",
            status_code=400,
        )
        self.depth = depth
        self.max_allowed = max_allowed


class GraphExportException(TopologyException):
    """Raised when rendering or exporting a topology graph fails."""

    def __init__(self, format_name: str, reason: str = "") -> None:
        msg = (
            f"Failed to export graph in '{format_name}' format: {reason}"
            if reason
            else f"Failed to export graph in '{format_name}' format."
        )
        super().__init__(
            msg,
            error_code="GRAPH_EXPORT_FAILED",
            status_code=500,
        )
        self.format_name = format_name
        self.reason = reason


class RestrictedNodeAccessException(TopologyException):
    """Raised when direct access to restricted node attributes is attempted without privilege."""

    def __init__(self, node_id: str) -> None:
        super().__init__(
            f"Node '{node_id}' is restricted under caller scope grants and cannot be inspected directly.",
            error_code="RESTRICTED_NODE_ACCESS_DENIED",
            status_code=403,
        )
        self.node_id = node_id


# ==============================================================================
# Reporting & Export Exceptions (Prompt 35 / BBP Section 36)
# ==============================================================================


class ReportingException(DomainModelException):
    """Base exception for reporting and export failures."""

    def __init__(
        self, message: str, error_code: str = "REPORTING_ERROR", status_code: int = 500
    ) -> None:
        super().__init__(message, error_code=error_code)
        self.status_code = status_code


class ReportTemplateNotFoundException(ReportingException):
    """Raised when looking up an unknown report template identifier."""

    def __init__(self, template_id: str) -> None:
        super().__init__(
            f"Report template '{template_id}' was not found.",
            error_code="REPORT_TEMPLATE_NOT_FOUND",
            status_code=404,
        )
        self.template_id = template_id


class UnsupportedReportFormatException(ReportingException):
    """Raised when an export format is not supported for a given report template."""

    def __init__(self, message: str) -> None:
        super().__init__(
            message,
            error_code="UNSUPPORTED_REPORT_FORMAT",
            status_code=400,
        )


class ReportJobNotFoundException(ReportingException):
    """Raised when an asynchronous report export job is not found."""

    def __init__(self, job_id: str) -> None:
        super().__init__(
            f"Report generation job '{job_id}' was not found.",
            error_code="REPORT_JOB_NOT_FOUND",
            status_code=404,
        )
        self.job_id = job_id


class DownloadLinkExpiredException(ReportingException):
    """Raised when accessing a time-limited download link that has expired."""

    def __init__(
        self,
        message: str = "The download link for this report has expired. Please request a new export.",
    ) -> None:
        super().__init__(
            message,
            error_code="DOWNLOAD_LINK_EXPIRED",
            status_code=410,
        )


class InvalidDownloadTokenException(ReportingException):
    """Raised when a download token is missing, invalid, or unauthorized."""

    def __init__(self, message: str = "Invalid or missing download security token.") -> None:
        super().__init__(
            message,
            error_code="INVALID_DOWNLOAD_TOKEN",
            status_code=401,
        )


class FeatureNotEnabledException(ReportingException):
    """Raised when attempting to access a Phase 2 capability whose flag is disabled."""

    def __init__(self, message: str) -> None:
        super().__init__(
            message,
            error_code="FEATURE_NOT_ENABLED",
            status_code=403,
        )
