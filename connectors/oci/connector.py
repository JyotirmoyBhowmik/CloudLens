"""Oracle Cloud Infrastructure (OCI) Connector Skeleton."""

from __future__ import annotations

from typing import Any

from connectors.contract.base import BaseCloudConnector
from connectors.contract.models import (
    HealthStatusResult,
    PagedResult,
    PaginationParams,
    PermissionValidationResult,
)
from domain.models.enums import ConnectorCapability


class OCIConnector(BaseCloudConnector):
    """OCI connector skeleton implementing BaseCloudConnector."""

    def default_capabilities(self) -> set[ConnectorCapability]:
        return {
            ConnectorCapability.VALIDATE_PERMISSIONS,
            ConnectorCapability.HEALTH_STATUS,
            ConnectorCapability.DISCOVER_HIERARCHY,
            ConnectorCapability.DISCOVER_RESOURCES,
        }

    @property
    def provider_name(self) -> str:
        return "oci"

    async def validate_permissions(self) -> PermissionValidationResult:
        self._assert_declared(ConnectorCapability.VALIDATE_PERMISSIONS)
        return PermissionValidationResult(
            valid=True,
            provider="oci",
            capabilities=[c.value for c in self.declared_capabilities],
        )

    async def health_status(self) -> HealthStatusResult:
        self._assert_declared(ConnectorCapability.HEALTH_STATUS)
        return HealthStatusResult(healthy=True, latency_ms=2.0, details={"provider": "oci"})

    async def discover_hierarchy(
        self,
        pagination: PaginationParams | None = None,
    ) -> PagedResult[dict[str, Any]]:
        self._assert_declared(ConnectorCapability.DISCOVER_HIERARCHY)
        _ = pagination
        return PagedResult(items=[], continuation_token=None, is_truncated=False, total_records=0)

    async def discover_resources(
        self,
        scope_id: str = "root",
        pagination: PaginationParams | None = None,
    ) -> PagedResult[dict[str, Any]]:
        self._assert_declared(ConnectorCapability.DISCOVER_RESOURCES)
        _ = (scope_id, pagination)
        return PagedResult(items=[], continuation_token=None, is_truncated=False, total_records=0)
