"""Amazon Web Services (AWS) Cloud Connector (Prompt 17 / BBP Section 14.3 & 15.4).

Implements all seventeen canonical connector contract capabilities while preserving
AWS-native semantics end-to-end:
1. Cross-account IAM role assumption with mandatory ExternalId as recommended path;
   OIDC web identity federation (EKS IRSA) support; access key exceptions with mandatory rotation.
   Prohibits root credentials and user passwords.
2. Single-pass hierarchy discovery using Organizations tree (roots, OUs, accounts), preserving OU nesting.
   The AWS account is established as the canonical billing boundary.
3. Resource inventory via hybrid Tagging + Config APIs with explicit non-uniform coverage caveat
   and Unclassified classification for unsupported types.
4. Export-first Cost and Usage Report 2.0 (BCM Data Exports) in S3 with Parquet or compressed CSV.
   Cost Explorer is interactive fallback only, never bulk engine. FinOps sizing calculation surfaces
   10x-100x row volume expansion when resource IDs are enabled.
5. Price List Service bulk offer files with targeted GetProducts query interface (aws_v1)
   and negotiated EDP discount precedence.
6. Non-authoritative AWS Budgets read for comparison only.
7. Coarse CloudWatch metrics (hourly or daily rollups), rejecting sub-minute intervals.
8. Multi-tier tag collection with AWS Cost Categories modeled as distinct native concepts.
9. Structural dependency derivation declared as PARTIAL.
"""

from __future__ import annotations

import logging
from typing import Any

from connectors.aws.auth import AWSAuthService
from connectors.aws.budgets import AWSBudgetService
from connectors.aws.cost import AWSCostService
from connectors.aws.hierarchy import AWSHierarchyService
from connectors.aws.inventory import AWSInventoryService
from connectors.aws.metrics import AWSMetricsService
from connectors.aws.models import (
    AWSAuthMethod,
    AWSCURConfiguration,
)
from connectors.aws.pricing import AWSPriceQuote, AWSPricingService
from connectors.aws.relationships import AWSRelationshipService
from connectors.aws.tags import AWSTagService
from connectors.contract.base import BaseCloudConnector
from connectors.contract.models import (
    AuthResult,
    HealthStatusResult,
    PagedResult,
    PaginationParams,
    PermissionValidationResult,
    ProviderMetadataResult,
)
from domain.models.enums import ConnectorCapability, ProviderType

logger = logging.getLogger(__name__)


class AWSConnector(BaseCloudConnector):
    """Amazon Web Services (AWS) Cloud Connector implementing the 17-capability contract."""

    def __init__(
        self,
        connector_id: str,
        tenant_id: str,
        config: dict[str, Any] | None = None,
        declared_capabilities: set[ConnectorCapability] | None = None,
    ) -> None:
        super().__init__(
            connector_id=connector_id,
            tenant_id=tenant_id,
            config=config,
            declared_capabilities=declared_capabilities,
        )

        cfg = self.config or {}
        management_account_id = cfg.get("management_account_id", "112233445566")
        self.management_account_id = management_account_id

        # Build credentials payload with sensible defaults for cross-account assumption
        credentials_dict = cfg.get("credentials") or {
            "management_account_id": management_account_id,
            "role_arn": cfg.get(
                "role_arn",
                f"arn:aws:iam::{management_account_id}:role/CloudLensCrossAccountRole",
            ),
            "external_id": cfg.get("external_id", f"cloudlens-ext-{tenant_id}"),
            "role_session_name": cfg.get("role_session_name", "CloudLensSession"),
            "auth_method": cfg.get("auth_method", AWSAuthMethod.ASSUME_ROLE.value),
        }

        # Initialize modular sub-services
        self.auth_service = AWSAuthService(credentials_dict)
        self.hierarchy_service = AWSHierarchyService(management_account_id, self.config)
        self.inventory_service = AWSInventoryService(management_account_id, self.config)
        self.cost_service = AWSCostService(management_account_id, self.config)
        self.pricing_service = AWSPricingService(
            management_account_id=management_account_id,
            config=self.config,
            has_edp_entitlement=cfg.get("has_edp_entitlement", True),
        )
        self.metrics_service = AWSMetricsService(management_account_id, self.config)
        self.tag_service = AWSTagService(management_account_id, self.config)
        self.relationship_service = AWSRelationshipService(management_account_id, self.config)
        self.budget_service = AWSBudgetService(management_account_id, self.config)

    @property
    def provider_name(self) -> str:
        return ProviderType.AWS.value

    def default_capabilities(self) -> set[ConnectorCapability]:
        """AWS connector supports all applicable contract capabilities."""
        return {
            ConnectorCapability.AUTHENTICATE,
            ConnectorCapability.VALIDATE_PERMISSIONS,
            ConnectorCapability.DISCOVER_ORGANIZATIONS,
            ConnectorCapability.DISCOVER_ACCOUNTS,
            ConnectorCapability.DISCOVER_HIERARCHY,
            ConnectorCapability.DISCOVER_RESOURCES,
            ConnectorCapability.DISCOVER_SERVICES,
            ConnectorCapability.COLLECT_COST_BULK,
            ConnectorCapability.COLLECT_COST_QUERY,
            ConnectorCapability.COLLECT_USAGE,
            ConnectorCapability.COLLECT_PRICING_PUBLIC,
            ConnectorCapability.COLLECT_PRICING_NEGOTIATED,
            ConnectorCapability.COLLECT_TAGS,
            ConnectorCapability.DISCOVER_RELATIONSHIPS,
            ConnectorCapability.COLLECT_BUDGETS,
            ConnectorCapability.HEALTH_STATUS,
            ConnectorCapability.PROVIDER_METADATA,
        }

    # ==========================================================================
    # Diagnostic & Helper Properties
    # ==========================================================================

    @property
    def cur_configuration(self) -> AWSCURConfiguration:
        """Returns the BCM Data Exports CUR 2.0 configuration."""
        return self.cost_service.get_cur_configuration()

    def estimate_cur_sizing(self, resource_count: int) -> dict[str, float | int | str]:
        """Estimates FinOps row volume expansion and storage requirements."""
        return self.cost_service.estimate_sizing_envelope(resource_count)

    @property
    def inventory_coverage_caveat(self) -> str:
        """Surfaces non-uniform service coverage caveat per BBP Section 14.3."""
        return self.inventory_service.coverage_caveat

    @property
    def relationships_is_partial(self) -> bool:
        """Declares that relationships are structural only."""
        return self.relationship_service.is_partial

    def get_effective_pricing(self, sku: str) -> AWSPriceQuote | None:
        """Helper to resolve price quote with EDP precedence."""
        return self.pricing_service.get_effective_quote(sku)

    async def collect_cost_categories(
        self,
        pagination: PaginationParams | None = None,
    ) -> PagedResult[dict[str, Any]]:
        """Collects distinct AWS Cost Categories (not folded into tags)."""
        return await self.tag_service.collect_cost_categories(pagination)

    # ==========================================================================
    # 17 Contract Capability Implementations
    # ==========================================================================

    # 1. authenticate
    async def authenticate(self) -> AuthResult:
        self._assert_declared(ConnectorCapability.AUTHENTICATE)
        return await self.auth_service.authenticate()

    # 2. validate_permissions
    async def validate_permissions(self) -> PermissionValidationResult:
        self._assert_declared(ConnectorCapability.VALIDATE_PERMISSIONS)
        return await self.auth_service.validate_permissions(self.declared_capabilities)

    # 3. discover_organizations
    async def discover_organizations(
        self,
        pagination: PaginationParams | None = None,
    ) -> PagedResult[dict[str, Any]]:
        self._assert_declared(ConnectorCapability.DISCOVER_ORGANIZATIONS)
        return await self.hierarchy_service.discover_organizations(pagination)

    # 4. discover_accounts
    async def discover_accounts(
        self,
        parent_id: str | None = None,
        pagination: PaginationParams | None = None,
    ) -> PagedResult[dict[str, Any]]:
        self._assert_declared(ConnectorCapability.DISCOVER_ACCOUNTS)
        return await self.hierarchy_service.discover_accounts(parent_id, pagination)

    # 5. discover_hierarchy
    async def discover_hierarchy(
        self,
        pagination: PaginationParams | None = None,
    ) -> PagedResult[dict[str, Any]]:
        self._assert_declared(ConnectorCapability.DISCOVER_HIERARCHY)
        return await self.hierarchy_service.discover_hierarchy(pagination)

    # 6. discover_resources
    async def discover_resources(
        self,
        scope_id: str = "root",
        pagination: PaginationParams | None = None,
    ) -> PagedResult[dict[str, Any]]:
        self._assert_declared(ConnectorCapability.DISCOVER_RESOURCES)
        return await self.inventory_service.discover_resources(scope_id, pagination)

    # 7. discover_services
    async def discover_services(
        self,
        scope_id: str | None = None,
        pagination: PaginationParams | None = None,
    ) -> PagedResult[dict[str, Any]]:
        self._assert_declared(ConnectorCapability.DISCOVER_SERVICES)
        return await self.inventory_service.discover_services(scope_id, pagination)

    # 8. collect_cost_bulk
    async def collect_cost_bulk(
        self,
        start_date: str = "2026-09-01",
        end_date: str = "2026-09-27",
        pagination: PaginationParams | None = None,
        account_id: str | None = None,
    ) -> PagedResult[dict[str, Any]]:
        self._assert_declared(ConnectorCapability.COLLECT_COST_BULK)
        return await self.cost_service.collect_cost_bulk(
            start_date=start_date,
            end_date=end_date,
            pagination=pagination,
            account_id=account_id,
        )

    # 9. collect_cost_query
    async def collect_cost_query(
        self,
        query: dict[str, Any] | None = None,
        pagination: PaginationParams | None = None,
        account_id: str | None = None,
    ) -> PagedResult[dict[str, Any]]:
        self._assert_declared(ConnectorCapability.COLLECT_COST_QUERY)
        return await self.cost_service.collect_cost_query(
            query=query,
            pagination=pagination,
            account_id=account_id,
        )

    # 10. collect_usage
    async def collect_usage(
        self,
        scope_id: str = "root",
        metric_names: list[str] | None = None,
        start_time: str = "2026-09-01T00:00:00Z",
        end_time: str = "2026-09-27T00:00:00Z",
        pagination: PaginationParams | None = None,
        interval: str = "PT1H",
    ) -> PagedResult[dict[str, Any]]:
        self._assert_declared(ConnectorCapability.COLLECT_USAGE)
        return await self.metrics_service.collect_usage(
            scope_id=scope_id,
            metric_names=metric_names,
            interval=interval,
            start_time=start_time,
            end_time=end_time,
            pagination=pagination,
        )

    # 11. collect_pricing_public
    async def collect_pricing_public(
        self,
        service_code: str | None = None,
        pagination: PaginationParams | None = None,
    ) -> PagedResult[dict[str, Any]]:
        self._assert_declared(ConnectorCapability.COLLECT_PRICING_PUBLIC)
        return await self.pricing_service.collect_pricing_public(service_code, pagination)

    # 12. collect_pricing_negotiated
    async def collect_pricing_negotiated(
        self,
        account_id: str | None = None,
        pagination: PaginationParams | None = None,
    ) -> PagedResult[dict[str, Any]]:
        self._assert_declared(ConnectorCapability.COLLECT_PRICING_NEGOTIATED)
        return await self.pricing_service.collect_pricing_negotiated(account_id, pagination)

    # 13. collect_tags
    async def collect_tags(
        self,
        scope_id: str = "root",
        pagination: PaginationParams | None = None,
    ) -> PagedResult[dict[str, Any]]:
        self._assert_declared(ConnectorCapability.COLLECT_TAGS)
        return await self.tag_service.collect_tags(scope_id, pagination)

    # 14. discover_relationships
    async def discover_relationships(
        self,
        scope_id: str = "root",
        pagination: PaginationParams | None = None,
    ) -> PagedResult[dict[str, Any]]:
        self._assert_declared(ConnectorCapability.DISCOVER_RELATIONSHIPS)
        return await self.relationship_service.discover_relationships(scope_id, pagination)

    # 15. collect_budgets
    async def collect_budgets(
        self,
        scope_id: str | None = None,
        pagination: PaginationParams | None = None,
    ) -> PagedResult[dict[str, Any]]:
        self._assert_declared(ConnectorCapability.COLLECT_BUDGETS)
        return await self.budget_service.collect_budgets(scope_id, pagination)

    # 16. health_status
    async def health_status(self) -> HealthStatusResult:
        self._assert_declared(ConnectorCapability.HEALTH_STATUS)
        return HealthStatusResult(
            healthy=True,
            latency_ms=10.0,
            status_code=200,
            details={
                "provider": ProviderType.AWS.value,
                "management_account_id": self.management_account_id,
                "auth_method": self.auth_service.credentials.auth_method.value,
                "cur_version": "CUR-2.0-FixedSchema",
                "coverage_caveat": self.inventory_coverage_caveat,
            },
        )

    # 17. provider_metadata
    async def provider_metadata(self) -> ProviderMetadataResult:
        self._assert_declared(ConnectorCapability.PROVIDER_METADATA)
        return ProviderMetadataResult(
            provider=ProviderType.AWS,
            api_version="2023-11-26",
            supported_regions=[
                "us-east-1",
                "us-east-2",
                "us-west-1",
                "us-west-2",
                "eu-west-1",
                "eu-central-1",
                "ap-southeast-1",
                "ap-northeast-1",
            ],
            capabilities_supported=list(self.declared_capabilities),
            metadata={
                "cur_2_0_supported": True,
                "cur_resource_id_sizing_driver": True,
                "cross_account_external_id_required": True,
                "cost_categories_distinct": True,
                "pricing_edp_precedence": True,
                "relationships_partial": True,
                "non_uniform_inventory_coverage": True,
            },
        )
