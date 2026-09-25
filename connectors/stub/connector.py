"""CloudLens Stub / Simulator Connector Skeleton."""

from typing import Any

from connectors.contract.base import BaseCloudConnector


class StubConnector(BaseCloudConnector):
    """Provider-agnostic stub connector for testing and offline demo mode."""

    @property
    def provider_name(self) -> str:
        return "stub"

    async def validate_credentials(self) -> dict[str, Any]:
        return {"valid": True, "provider": "stub", "capabilities": ["all"]}

    async def test_connection(self) -> bool:
        return True

    async def discover_hierarchy(self) -> list[dict[str, Any]]:
        return [
            {
                "id": "stub-root",
                "name": "Synthetic Root Group",
                "type": "organization",
                "children": [],
            }
        ]

    async def discover_resources(self, scope_id: str) -> list[dict[str, Any]]:
        _ = scope_id
        return []
