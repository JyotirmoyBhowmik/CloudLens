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
