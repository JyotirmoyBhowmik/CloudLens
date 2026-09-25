"""Oracle Cloud Infrastructure (OCI) Connector Skeleton."""

from typing import Any

from connectors.contract.base import BaseCloudConnector


class OCIConnector(BaseCloudConnector):
    """OCI connector skeleton implementing BaseCloudConnector."""

    @property
    def provider_name(self) -> str:
        return "oci"

    async def validate_credentials(self) -> dict[str, Any]:
        return {"valid": True, "provider": "oci", "capabilities": []}

    async def test_connection(self) -> bool:
        return True

    async def discover_hierarchy(self) -> list[dict[str, Any]]:
        return []

    async def discover_resources(self, scope_id: str) -> list[dict[str, Any]]:
        _ = scope_id
        return []
