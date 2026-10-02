"""CloudLens Connector Contract - Shared Base Interface (Prompt 14 / BBP Section 26).

Enforces:
- Canonical seventeen capabilities (Item 89):
  1. authenticate
  2. validate_permissions
  3. discover_organizations
  4. discover_accounts
  5. discover_hierarchy
  6. discover_resources
  7. discover_services
  8. collect_cost_bulk
  9. collect_cost_query
  10. collect_usage
  11. collect_pricing_public
  12. collect_pricing_negotiated
  13. collect_tags
  14. discover_relationships
  15. collect_budgets
  16. health_status
  17. provider_metadata
- Capability declaration and runtime enforcement (Item 90):
  A connector declares what it supports; the platform must NEVER invoke an undeclared capability.
  Undeclared calls strictly raise UndeclaredCapabilityException.
- Strict backwards compatibility with Prompt 47 test fixtures.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from connectors.contract.models import (
    AuthResult,
    HealthStatusResult,
    PagedResult,
    PaginationParams,
    PermissionValidationResult,
    ProviderMetadataResult,
    QuotaItemRecord,
    QuotaProbeResult,
)
from domain.models.enums import ConnectorCapability, QuotaCoverage
from domain.models.exceptions import UndeclaredCapabilityException

logger = logging.getLogger(__name__)


class BaseCloudConnector(ABC):
    """Abstract base class for all cloud provider connectors implementing the 17-capability contract."""

    def __init__(
        self,
        connector_id: str,
        tenant_id: str,
        config: dict[str, Any] | None = None,
        declared_capabilities: set[ConnectorCapability] | None = None,
    ) -> None:
        self.connector_id = connector_id
        self.tenant_id = tenant_id
        self.config = config or {}
        # Explicit declared capability set (Prompt 14 Item 90)
        self._declared_capabilities = (
            declared_capabilities
            if declared_capabilities is not None
            else self.default_capabilities()
        )

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Provider identifier string (e.g. azure, aws, gcp, oci, stub)."""
        pass

    def default_capabilities(self) -> set[ConnectorCapability]:
        """Default capabilities declared by this connector class if not explicitly passed."""
        return set()

    @property
    def declared_capabilities(self) -> set[ConnectorCapability]:
        """Set of capabilities statically declared and supported by this connector."""
        return set(self._declared_capabilities)

    @property
    def capabilities(self) -> set[ConnectorCapability]:
        """Alias for declared_capabilities."""
        return self.declared_capabilities

    def has_capability(self, capability: ConnectorCapability) -> bool:
        """Checks whether this connector declares the specified capability."""
        return capability in self._declared_capabilities

    def _assert_declared(self, capability: ConnectorCapability) -> None:
        """Guards capability invocation. Fails fast if capability is not declared."""
        if not self.has_capability(capability):
            logger.error(
                "Attempted invocation of undeclared capability '%s' on connector '%s' (%s)",
                capability.value,
                self.connector_id,
                self.provider_name,
            )
            raise UndeclaredCapabilityException(
                connector_id=self.connector_id,
                capability=capability.value,
            )

    # ==========================================================================
    # Canonical Seventeen Capabilities (Prompt 14 Item 89)
    # ==========================================================================

    # 1. authenticate
    async def authenticate(self) -> AuthResult:
        """Performs authentication handshake with provider identity endpoint."""
        self._assert_declared(ConnectorCapability.AUTHENTICATE)
        raise NotImplementedError(
            f"{self.__class__.__name__} declared authenticate but did not implement it."
        )

    # 2. validate_permissions
    async def validate_permissions(self) -> PermissionValidationResult:
        """Executes pre-flight least-privilege permission verification."""
        self._assert_declared(ConnectorCapability.VALIDATE_PERMISSIONS)
        raise NotImplementedError(
            f"{self.__class__.__name__} declared validate_permissions but did not implement it."
        )

    # 3. discover_organizations
    async def discover_organizations(
        self,
        pagination: PaginationParams | None = None,
    ) -> PagedResult[dict[str, Any]]:
        """Discovers top-level management organizations and root enterprise scopes."""
        self._assert_declared(ConnectorCapability.DISCOVER_ORGANIZATIONS)
        _ = pagination
        raise NotImplementedError(
            f"{self.__class__.__name__} declared discover_organizations but did not implement it."
        )

    # 4. discover_accounts
    async def discover_accounts(
        self,
        parent_id: str | None = None,
        pagination: PaginationParams | None = None,
    ) -> PagedResult[dict[str, Any]]:
        """Discovers member accounts, subscriptions, or projects under a parent scope."""
        self._assert_declared(ConnectorCapability.DISCOVER_ACCOUNTS)
        _ = (parent_id, pagination)
        raise NotImplementedError(
            f"{self.__class__.__name__} declared discover_accounts but did not implement it."
        )

    # 5. discover_hierarchy
    async def discover_hierarchy(
        self,
        pagination: PaginationParams | None = None,
    ) -> PagedResult[dict[str, Any]] | list[dict[str, Any]]:
        """Discovers full scope tree hierarchy (management groups, folders, compartments)."""
        self._assert_declared(ConnectorCapability.DISCOVER_HIERARCHY)
        _ = pagination
        raise NotImplementedError(
            f"{self.__class__.__name__} declared discover_hierarchy but did not implement it."
        )

    # 6. discover_resources
    async def discover_resources(
        self,
        scope_id: str = "root",
        pagination: PaginationParams | None = None,
    ) -> PagedResult[dict[str, Any]] | list[dict[str, Any]]:
        """Enumerates cloud infrastructure resources within a given scope."""
        self._assert_declared(ConnectorCapability.DISCOVER_RESOURCES)
        _ = (scope_id, pagination)
        raise NotImplementedError(
            f"{self.__class__.__name__} declared discover_resources but did not implement it."
        )

    # 7. discover_services
    async def discover_services(
        self,
        scope_id: str | None = None,
        pagination: PaginationParams | None = None,
    ) -> PagedResult[dict[str, Any]]:
        """Discovers active cloud service categories enabled in the target estate."""
        self._assert_declared(ConnectorCapability.DISCOVER_SERVICES)
        _ = (scope_id, pagination)
        raise NotImplementedError(
            f"{self.__class__.__name__} declared discover_services but did not implement it."
        )

    # 8. collect_cost_bulk
    async def collect_cost_bulk(
        self,
        start_date: str = "2026-09-01",
        end_date: str = "2026-09-27",
        pagination: PaginationParams | None = None,
    ) -> PagedResult[dict[str, Any]]:
        """Ingests bulk billing datasets (CUR, Cost Management Exports)."""
        self._assert_declared(ConnectorCapability.COLLECT_COST_BULK)
        _ = (start_date, end_date, pagination)
        raise NotImplementedError(
            f"{self.__class__.__name__} declared collect_cost_bulk but did not implement it."
        )

    # 9. collect_cost_query
    async def collect_cost_query(
        self,
        query: dict[str, Any] | None = None,
        pagination: PaginationParams | None = None,
    ) -> PagedResult[dict[str, Any]]:
        """Queries on-demand cost analytics API for targeted date and dimension filters."""
        self._assert_declared(ConnectorCapability.COLLECT_COST_QUERY)
        _ = (query, pagination)
        raise NotImplementedError(
            f"{self.__class__.__name__} declared collect_cost_query but did not implement it."
        )

    # 10. collect_usage
    async def collect_usage(
        self,
        scope_id: str = "root",
        metric_names: list[str] | None = None,
        start_time: str = "2026-09-01",
        end_time: str = "2026-09-27",
        pagination: PaginationParams | None = None,
    ) -> PagedResult[dict[str, Any]]:
        """Ingests operational utilization metrics (CPU, Memory, IOPS)."""
        self._assert_declared(ConnectorCapability.COLLECT_USAGE)
        _ = (scope_id, metric_names, start_time, end_time, pagination)
        raise NotImplementedError(
            f"{self.__class__.__name__} declared collect_usage but did not implement it."
        )

    # 11. collect_pricing_public
    async def collect_pricing_public(
        self,
        service_code: str | None = None,
        pagination: PaginationParams | None = None,
    ) -> PagedResult[dict[str, Any]]:
        """Retrieves public list prices and rate cards for canonical services."""
        self._assert_declared(ConnectorCapability.COLLECT_PRICING_PUBLIC)
        _ = (service_code, pagination)
        raise NotImplementedError(
            f"{self.__class__.__name__} declared collect_pricing_public but did not implement it."
        )

    # 12. collect_pricing_negotiated
    async def collect_pricing_negotiated(
        self,
        account_id: str | None = None,
        pagination: PaginationParams | None = None,
    ) -> PagedResult[dict[str, Any]]:
        """Retrieves enterprise negotiated pricing schedules and custom rate cards."""
        self._assert_declared(ConnectorCapability.COLLECT_PRICING_NEGOTIATED)
        _ = (account_id, pagination)
        raise NotImplementedError(
            f"{self.__class__.__name__} declared collect_pricing_negotiated but did not implement it."
        )

    # 13. collect_tags
    async def collect_tags(
        self,
        scope_id: str = "root",
        pagination: PaginationParams | None = None,
    ) -> PagedResult[dict[str, Any]]:
        """Retrieves tag inventories, tag keys/values, and compliance mappings."""
        self._assert_declared(ConnectorCapability.COLLECT_TAGS)
        _ = (scope_id, pagination)
        raise NotImplementedError(
            f"{self.__class__.__name__} declared collect_tags but did not implement it."
        )

    # 14. discover_relationships
    async def discover_relationships(
        self,
        scope_id: str = "root",
        pagination: PaginationParams | None = None,
    ) -> PagedResult[dict[str, Any]]:
        """Discovers topology dependencies, network bindings, and storage mounts."""
        self._assert_declared(ConnectorCapability.DISCOVER_RELATIONSHIPS)
        _ = (scope_id, pagination)
        raise NotImplementedError(
            f"{self.__class__.__name__} declared discover_relationships but did not implement it."
        )

    # 15. collect_budgets
    async def collect_budgets(
        self,
        scope_id: str | None = None,
        pagination: PaginationParams | None = None,
    ) -> PagedResult[dict[str, Any]]:
        """Ingests native cloud provider budget configurations and threshold alerts."""
        self._assert_declared(ConnectorCapability.COLLECT_BUDGETS)
        _ = (scope_id, pagination)
        raise NotImplementedError(
            f"{self.__class__.__name__} declared collect_budgets but did not implement it."
        )

    # 16. health_status
    async def health_status(self) -> HealthStatusResult:
        """Executes a live health check probe against provider management endpoints."""
        self._assert_declared(ConnectorCapability.HEALTH_STATUS)
        raise NotImplementedError(
            f"{self.__class__.__name__} declared health_status but did not implement it."
        )

    # 17. provider_metadata
    async def provider_metadata(self) -> ProviderMetadataResult:
        """Returns provider system metadata, supported regions, and API capabilities."""
        self._assert_declared(ConnectorCapability.PROVIDER_METADATA)
        raise NotImplementedError(
            f"{self.__class__.__name__} declared provider_metadata but did not implement it."
        )

    # ==========================================================================
    # Backwards-Compatibility Convenience Wrappers
    # ==========================================================================

    async def test_connection(self) -> bool:
        """Health check probe matching Prompt 47 test fixture signature."""
        if self.has_capability(ConnectorCapability.HEALTH_STATUS):
            result = await self.health_status()
            return result.healthy
        return True

    async def validate_credentials(self) -> dict[str, Any]:
        """Permission validation matching Prompt 47 test fixture signature."""
        if self.has_capability(ConnectorCapability.VALIDATE_PERMISSIONS):
            result = await self.validate_permissions()
            return {
                "valid": result.valid,
                "provider": result.provider,
                "capabilities": result.capabilities,
                "missing_permissions": result.missing_permissions,
            }
        return {
            "valid": True,
            "provider": self.provider_name,
            "capabilities": [c.value for c in self.declared_capabilities],
        }

    # ==========================================================================
    # Quota & Service Limits Capability (Prompt 54)
    # ==========================================================================

    def collect_quotas(
        self,
        scope_id: str = "root",
        region: str | None = None,
        pagination: PaginationParams | None = None,
        *,
        tenant_context: Any = None,
    ) -> list[QuotaItemRecord]:
        """Enumerates cloud service limits, capacity constraints, and quota consumption (Prompt 54)."""
        _ = (scope_id, region, pagination, tenant_context)
        return []

    def probe_quota_coverage(
        self,
        scope_id: str = "root",
        *,
        tenant_context: Any = None,
    ) -> QuotaProbeResult:
        """Probes provider quota coverage and reports whether full, partial, or not supported (Prompt 54)."""
        _ = (scope_id, tenant_context)
        return QuotaProbeResult(
            provider=self.provider_name,
            is_supported=False,
            coverage=QuotaCoverage.NOT_SUPPORTED,
            details={"message": "Quota capability not supported by this connector."},
        )
