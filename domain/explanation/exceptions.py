from domain.models.exceptions import DomainModelException


class ExplanationNotFoundException(DomainModelException):
    """Raised when an explanation suite or panel cannot be found for a resource or SKU."""

    def __init__(self, resource_or_sku: str, panel_type: str | None = None) -> None:
        msg = (
            f"Explanation panel '{panel_type}' not found for '{resource_or_sku}'."
            if panel_type
            else f"Explanation suite not found for resource or SKU '{resource_or_sku}'."
        )
        super().__init__(msg, error_code="EXPLANATION_NOT_FOUND")
        self.resource_or_sku = resource_or_sku
        self.panel_type = panel_type


class MissingExplanationPayloadException(DomainModelException):
    """Raised when a pricing or cost component attempts to render without an attached explanation payload."""

    def __init__(self, metric_name: str, component_name: str | None = None) -> None:
        target = f" in {component_name}" if component_name else ""
        super().__init__(
            f"Mechanical violation: Cost value for '{metric_name}'{target} is missing mandatory explanation payload.",
            error_code="MISSING_EXPLANATION_PAYLOAD",
        )
        self.metric_name = metric_name
        self.component_name = component_name


class StalePricingDataException(DomainModelException):
    """Raised when pricing data is stale and accessed in a strict evaluation context."""

    def __init__(self, sku: str, age_hours: float, threshold_hours: float) -> None:
        super().__init__(
            f"Pricing data for SKU '{sku}' is stale ({age_hours:.1f}h old; threshold is {threshold_hours:.1f}h).",
            error_code="STALE_PRICING_DATA",
        )
        self.sku = sku
        self.age_hours = age_hours
        self.threshold_hours = threshold_hours
