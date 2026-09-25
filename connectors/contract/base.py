"""CloudLens Connector Contract - Shared Base Interface.

All provider connectors implement this common contract.
"""

from abc import ABC, abstractmethod
from typing import Any


class BaseCloudConnector(ABC):
    """Abstract base class for all cloud provider connectors."""

    def __init__(self, connector_id: str, tenant_id: str, config: dict[str, Any]):
        self.connector_id = connector_id
        self.tenant_id = tenant_id
        self.config = config

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Provider identifier string (e.g. azure, aws, gcp, oci, stub)."""
        pass

    @abstractmethod
    async def validate_credentials(self) -> dict[str, Any]:
        """Pre-flight permission validation to report available capabilities."""
        pass

    @abstractmethod
    async def test_connection(self) -> bool:
        """Health check probe against cloud provider management endpoints."""
        pass

    @abstractmethod
    async def discover_hierarchy(self) -> list[dict[str, Any]]:
        """Discover native organization and account hierarchy."""
        pass

    @abstractmethod
    async def discover_resources(self, scope_id: str) -> list[dict[str, Any]]:
        """Enumerate cloud resources within given scope."""
        pass
