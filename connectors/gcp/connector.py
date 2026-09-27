"""Google Cloud Platform (GCP) Cloud Connector (Prompt 18 / BBP Section 14.4 & 15.4).

Implements all seventeen canonical connector contract capabilities while preserving
GCP-native semantics end-to-end:
1. Workload Identity Federation (keyless OIDC, RFC 7523) as recommended path;
   service account key JSON only as audited exception with mandatory 90-day rotation;
   API key for public catalog interface only. Strictly prohibits interactive passwords and personal tokens.
2. Dual representation of resource hierarchy (organizations -> folders -> projects) and billing
   hierarchy (billingAccounts), preserving folder nesting in canonical scope paths.
   Billing accounts are never conflated as parents or children of folders.
3. Resource inventory via Cloud Asset Inventory with normalization for camelCase/snake_case and
   handling of null values in frequently changing fields.
4. Export-first BigQuery Cloud Billing export (Detailed usage, Standard usage, Pricing, FOCUS).
   Tracks and surfaces running BigQuery query cost ($5.00/TB on-demand, 10MB minimum).
5. Cloud Billing Catalog API public rates and account-specific contract pricing with contract precedence.
6. Non-authoritative Cloud Billing Budgets (is_authoritative = False) with strict prohibition on
   silent chargeable Pub/Sub notification creation.
7. Coarse Cloud Monitoring aggregates (hourly PT1H / daily P1D rollups), rejecting sub-minute intervals.
8. Label collection with explicit source tier recorded (LABEL_SOURCE_PROJECT vs LABEL_SOURCE_RESOURCE).
9. Dynamic runtime probe of Cloud Asset Inventory RELATIONSHIP content type, declared as PARTIAL.
"""

from __future__ import annotations

import logging
from typing import Any

from connectors.contract.base import BaseCloudConnector
from connectors.contract.models import (
    AuthResult,
    HealthStatusResult,
    PagedResult,
    PaginationParams,
    PermissionValidationResult,
    ProviderMetadataResult,
)
from connectors.gcp.auth import GCPAuthService
from connectors.gcp.budgets import GCPBudgetService
from connectors.gcp.cost import GCPCostService
from connectors.gcp.hierarchy import GCPHierarchyService
from connectors.gcp.inventory import GCPInventoryService
from connectors.gcp.metrics import GCPMetricsService
from connectors.gcp.models import (
    GCPAuthMethod,
    GCPBigQueryExportType,
    GCPBigQueryQueryCost,
    GCPPriceQuote,
    GCPRelationshipProbeResult,
)
from connectors.gcp.pricing import GCPPricingService
from connectors.gcp.relationships import GCPRelationshipService
from connectors.gcp.tags import GCPTagService
from domain.models.enums import ConnectorCapability, ProviderType

logger = logging.getLogger(__name__)

GCP_BILLING_EXPORT_HISTORY_WARNING = (
    "Cloud Billing export is NOT retrospective. Export history begins strictly at enablement; "
    "prior consumption cannot be backfilled from BigQuery export."
)


class GCPConnector(BaseCloudConnector):
    """Google Cloud Platform (GCP) Cloud Connector implementing the 17-capability contract."""

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
        primary_project_id = cfg.get("project_id", "proj-cloudlens-core")
        self.primary_project_id = primary_project_id
        organization_id = cfg.get("organization_id", "1092837465")
        self.organization_id = organization_id
        billing_account_id = cfg.get("billing_account_id", "01ABCD-2345EF-6789GH")
        self.billing_account_id = billing_account_id

        # Build credentials payload with Workload Identity Federation as recommended default
        credentials_dict = cfg.get("credentials") or {
            "project_id": primary_project_id,
            "auth_method": cfg.get("auth_method", GCPAuthMethod.WORKLOAD_IDENTITY.value),
            "service_account_email": cfg.get(
                "service_account_email",
                f"cloudlens-sa@{primary_project_id}.iam.gserviceaccount.com",
            ),
            "workload_identity_pool": cfg.get(
                "workload_identity_pool",
                f"projects/{organization_id}/locations/global/workloadIdentityPools/cloudlens-pool",
            ),
            "workload_identity_provider": cfg.get(
                "workload_identity_provider",
                "providers/cloudlens-k8s-provider",
            ),
            "service_account_key_json": cfg.get("service_account_key_json"),
            "api_key": cfg.get("api_key"),
        }

        # Initialize modular sub-services
        self.auth_service = GCPAuthService(credentials_dict)
        self.hierarchy_service = GCPHierarchyService(
            primary_project_id=primary_project_id,
            organization_id=organization_id,
            billing_account_id=billing_account_id,
            config=self.config,
        )
        self.inventory_service = GCPInventoryService(
            primary_project_id=primary_project_id,
            config=self.config,
        )
        self.cost_service = GCPCostService(
            billing_account_id=billing_account_id,
            primary_project_id=primary_project_id,
            dataset_name=cfg.get("dataset_name", "billing_export"),
            config=self.config,
        )
        self.pricing_service = GCPPricingService(
            billing_account_id=billing_account_id,
            config=self.config,
            has_contract_entitlement=cfg.get("has_contract_entitlement", True),
        )
        self.metrics_service = GCPMetricsService(
            primary_project_id=primary_project_id,
            config=self.config,
        )
        self.tag_service = GCPTagService(
            primary_project_id=primary_project_id,
            config=self.config,
        )
        self.relationship_service = GCPRelationshipService(
            primary_project_id=primary_project_id,
            config=self.config,
        )
        self.budget_service = GCPBudgetService(
            billing_account_id=billing_account_id,
            config=self.config,
        )

    @property
    def provider_name(self) -> str:
        return ProviderType.GCP.value

    def default_capabilities(self) -> set[ConnectorCapability]:
        """GCP connector supports all seventeen canonical contract capabilities."""
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
    def billing_export_history_warning(self) -> str:
        """Surfaces non-retrospective billing export warning per Prompt 18 / BBP Section 14.4."""
        return GCP_BILLING_EXPORT_HISTORY_WARNING

    @property
    def inventory_coverage_caveat(self) -> str:
        """Surfaces Cloud Asset Inventory export targets and casing caveats."""
        return self.inventory_service.coverage_caveat

    @property
    def bigquery_query_costs(self) -> list[GCPBigQueryQueryCost]:
        """Returns the log of BigQuery query costs incurred during sync runs."""
        return self.cost_service.query_costs

    @property
    def total_bigquery_query_cost_usd(self) -> float:
        """Returns cumulative BigQuery query costs in USD ($5.00/TB on-demand)."""
        return self.cost_service.get_total_query_cost_usd()

    @property
    def relationship_probe_result(self) -> GCPRelationshipProbeResult:
        """Dynamic runtime probe of Cloud Asset Inventory RELATIONSHIP content type."""
        return self.relationship_service.probe_relationship_support()

    @property
    def relationships_is_partial(self) -> bool:
        """Declares that relationships are structural only (PARTIAL)."""
        return self.relationship_service.is_partial

    def get_effective_pricing(self, sku_id: str) -> GCPPriceQuote | None:
        """Helper to resolve price quote with contract rate precedence."""
        return self.pricing_service.get_effective_quote(sku_id)

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
            latency_ms=12.0,
            status_code=200,
            details={
                "provider": ProviderType.GCP.value,
                "project_id": self.primary_project_id,
                "organization_id": self.organization_id,
                "billing_account_id": self.billing_account_id,
                "auth_method": self.auth_service.credentials.auth_method.value,
                "bigquery_export_type": self.cost_service.export_type.value,
                "total_query_cost_usd": self.total_bigquery_query_cost_usd,
                "relationships_status": self.relationship_probe_result.probe_status,
                "relationships_is_partial": self.relationships_is_partial,
            },
        )

    # 17. provider_metadata
    async def provider_metadata(self) -> ProviderMetadataResult:
        self._assert_declared(ConnectorCapability.PROVIDER_METADATA)
        return ProviderMetadataResult(
            provider=ProviderType.GCP,
            api_version="v1",
            supported_regions=[
                "us-central1",
                "us-east1",
                "us-east4",
                "us-west1",
                "us-west2",
                "europe-west1",
                "europe-west3",
                "asia-east1",
                "asia-northeast1",
            ],
            capabilities_supported=list(self.declared_capabilities),
            metadata={
                "workload_identity_federation_recommended": True,
                "dual_hierarchy_separated": True,
                "bigquery_export_types": [e.value for e in GCPBigQueryExportType],
                "bigquery_query_cost_tracked": True,
                "query_rate_per_tb_usd": 5.00,
                "query_min_bytes_billed": 10485760,
                "cloud_asset_inventory_casing_normalized": True,
                "pricing_contract_precedence": True,
                "budgets_non_authoritative": True,
                "budgets_silent_pubsub_prohibited": True,
                "coarse_metrics_only": True,
                "relationships_partial": True,
                "billing_export_history_warning": self.billing_export_history_warning,
            },
        )
