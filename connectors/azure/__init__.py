"""Microsoft Azure Connector Package (Prompt 16 / BBP Section 14.2 & 15.4)."""

from connectors.azure.auth import AzureAuthService
from connectors.azure.budgets import AzureBudgetService
from connectors.azure.connector import AzureConnector
from connectors.azure.cost import AzureCostService
from connectors.azure.hierarchy import AzureHierarchyService
from connectors.azure.inventory import AzureInventoryService
from connectors.azure.metrics import AzureMetricIntervalForbiddenException, AzureMetricsService
from connectors.azure.models import (
    AzureAgreementType,
    AzureAuthenticationException,
    AzureAuthMethod,
    AzureBudgetRecord,
    AzureCostRecord,
    AzureCredentials,
    AzureFreshnessIndicator,
    AzurePriceQuote,
    AzureRelationshipRecord,
    AzureScopeMismatchException,
    AzureScopeType,
    AzureSubscriptionOffer,
    AzureTagLevel,
    AzureTagRecord,
    detect_agreement_type,
    is_unsupported_cost_offer,
    validate_scope_for_agreement,
)
from connectors.azure.pricing import AzurePricingService
from connectors.azure.relationships import AzureRelationshipService
from connectors.azure.tags import AzureTagService

__all__ = [
    "AzureAgreementType",
    "AzureAuthenticationException",
    "AzureAuthMethod",
    "AzureAuthService",
    "AzureBudgetRecord",
    "AzureBudgetService",
    "AzureConnector",
    "AzureCostRecord",
    "AzureCostService",
    "AzureCredentials",
    "AzureFreshnessIndicator",
    "AzureHierarchyService",
    "AzureInventoryService",
    "AzureMetricIntervalForbiddenException",
    "AzureMetricsService",
    "AzurePriceQuote",
    "AzurePricingService",
    "AzureRelationshipRecord",
    "AzureRelationshipService",
    "AzureScopeMismatchException",
    "AzureScopeType",
    "AzureSubscriptionOffer",
    "AzureTagLevel",
    "AzureTagRecord",
    "AzureTagService",
    "detect_agreement_type",
    "is_unsupported_cost_offer",
    "validate_scope_for_agreement",
]
