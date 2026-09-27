"""CloudLens Stub / Simulator Connector (Prompt 14 Item 90 / Acceptance).

Enforces:
- Declares only three capabilities: HEALTH_STATUS, DISCOVER_HIERARCHY, DISCOVER_RESOURCES.
- Passes the Conformance Test Kit cleanly while platform never invokes the other fourteen.
"""

from __future__ import annotations

from typing import Any

from connectors.contract.base import BaseCloudConnector
from connectors.contract.models import (
    HealthStatusResult,
    PagedResult,
    PaginationParams,
)
from domain.models.enums import ConnectorCapability


class StubConnector(BaseCloudConnector):
    """Provider-agnostic stub connector declaring exactly three capabilities."""

    def default_capabilities(self) -> set[ConnectorCapability]:
        """Acceptance requirement: stub connector declares only three capabilities."""
        return {
            ConnectorCapability.HEALTH_STATUS,
            ConnectorCapability.DISCOVER_HIERARCHY,
            ConnectorCapability.DISCOVER_RESOURCES,
        }

    @property
    def provider_name(self) -> str:
        return "stub"

    async def health_status(self) -> HealthStatusResult:
        """Health status capability implementation."""
        self._assert_declared(ConnectorCapability.HEALTH_STATUS)
        return HealthStatusResult(
            healthy=True,
            latency_ms=1.5,
            details={"mode": "stub", "status": "operational"},
        )

    async def discover_hierarchy(
        self,
        pagination: PaginationParams | None = None,
    ) -> PagedResult[dict[str, Any]]:
        """Hierarchy discovery capability implementation."""
        self._assert_declared(ConnectorCapability.DISCOVER_HIERARCHY)
        _ = pagination
        items = [
            {
                "id": "stub-root",
                "name": "Synthetic Root Group",
                "type": "organization",
                "children": [],
            }
        ]
        return PagedResult(
            items=items, continuation_token=None, is_truncated=False, total_records=len(items)
        )

    async def discover_resources(
        self,
        scope_id: str = "root",
        pagination: PaginationParams | None = None,
    ) -> PagedResult[dict[str, Any]]:
        """Resource discovery capability implementation."""
        self._assert_declared(ConnectorCapability.DISCOVER_RESOURCES)
        _ = (scope_id, pagination)
        items: list[dict[str, Any]] = [
            {
                "id": f"res-stub-{scope_id}-01",
                "name": "stub-vm-01",
                "type": "compute",
                "scope_id": scope_id,
            }
        ]
        return PagedResult(
            items=items, continuation_token=None, is_truncated=False, total_records=len(items)
        )

    # Backwards-compatibility
    async def validate_credentials(self) -> dict[str, Any]:
        return {
            "valid": True,
            "provider": "stub",
            "capabilities": [c.value for c in self.declared_capabilities],
        }

    async def test_connection(self) -> bool:
        res = await self.health_status()
        return res.healthy
