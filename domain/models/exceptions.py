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
