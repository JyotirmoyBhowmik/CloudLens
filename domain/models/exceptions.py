"""Domain Exceptions for Canonical Domain Models."""


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
