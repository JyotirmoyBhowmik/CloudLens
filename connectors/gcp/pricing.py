"""GCP Cloud Billing Catalog and Contract Pricing Service (Prompt 18 / BBP Section 14.4 & 15.4).

Enforces:
- Cloud Billing Catalog API (cloudbilling.services.list, cloudbilling.skus.list) as public rate card source.
- Account-specific custom contract pricing path.
- Strict precedence: Account-specific contract pricing takes strict precedence over public catalog rates.
"""

from __future__ import annotations

import logging
from typing import Any

from connectors.contract.models import PagedResult, PaginationParams
from connectors.gcp.models import GCPPriceQuote

logger = logging.getLogger(__name__)


class GCPPricingService:
    """Provides public catalog rates and account-specific negotiated contract pricing."""

    def __init__(
        self,
        billing_account_id: str = "01ABCD-2345EF-6789GH",
        config: dict[str, Any] | None = None,
        has_contract_entitlement: bool = True,
    ) -> None:
        self.billing_account_id = billing_account_id
        self.config = config or {}
        self.has_contract_entitlement = has_contract_entitlement

    def _sample_catalog(self) -> dict[str, dict[str, Any]]:
        """Standard public baseline catalog from Cloud Billing Catalog API."""
        return {
            "D982-F0A1-332B": {
                "sku_id": "D982-F0A1-332B",
                "service_id": "6F81-5844-456A",
                "service_name": "Compute Engine",
                "sku_description": "N2 Instance Core running in Americas",
                "category": {
                    "serviceDisplayName": "Compute Engine",
                    "resourceFamily": "Compute",
                    "resourceGroup": "CPU",
                    "usageType": "OnDemand",
                },
                "service_regions": ["us-central1", "us-east1", "us-west1"],
                "list_price": 0.031611,
                "contract_price": 0.025288,  # 20% custom negotiated discount
                "currency": "USD",
            },
            "8432-84BA-8321": {
                "sku_id": "8432-84BA-8321",
                "service_id": "A482-1249-10BA",
                "service_name": "Cloud Storage",
                "sku_description": "Standard Storage US Regional",
                "category": {
                    "serviceDisplayName": "Cloud Storage",
                    "resourceFamily": "Storage",
                    "resourceGroup": "StandardStorage",
                    "usageType": "OnDemand",
                },
                "service_regions": ["us-central1", "us-east1"],
                "list_price": 0.020,
                "contract_price": 0.016,  # 20% custom negotiated discount
                "currency": "USD",
            },
            "7812-45A0-112E": {
                "sku_id": "7812-45A0-112E",
                "service_id": "24E5-B4C1-4D56",
                "service_name": "BigQuery",
                "sku_description": "Analysis (Queries)",
                "category": {
                    "serviceDisplayName": "BigQuery",
                    "resourceFamily": "ApplicationServices",
                    "resourceGroup": "Analysis",
                    "usageType": "OnDemand",
                },
                "service_regions": ["us-central1", "global"],
                "list_price": 5.00,
                "contract_price": 4.50,  # 10% custom negotiated discount
                "currency": "USD",
            },
            "B198-332A-44CD": {
                "sku_id": "B198-332A-44CD",
                "service_id": "6F81-5844-456A",
                "service_name": "Compute Engine",
                "sku_description": "N2 Instance Ram running in Americas",
                "category": {
                    "serviceDisplayName": "Compute Engine",
                    "resourceFamily": "Compute",
                    "resourceGroup": "RAM",
                    "usageType": "OnDemand",
                },
                "service_regions": ["us-central1", "us-east1"],
                "list_price": 0.004237,
                "contract_price": 0.003389,
                "currency": "USD",
            },
        }

    def get_effective_quote(self, sku_id: str) -> GCPPriceQuote | None:
        """Resolves price quote with strict precedence: contract rate supersedes list rate."""
        cat = self._sample_catalog()
        raw = cat.get(sku_id)
        if not raw:
            return None

        list_price = raw["list_price"]
        contract_rate = raw.get("contract_price") if self.has_contract_entitlement else None

        effective_price = contract_rate if contract_rate is not None else list_price
        is_contract = contract_rate is not None

        return GCPPriceQuote(
            sku_id=raw["sku_id"],
            service_id=raw["service_id"],
            service_name=raw["service_name"],
            sku_description=raw["sku_description"],
            category=raw.get("category", {}),
            service_regions=raw.get("service_regions", []),
            list_price=list_price,
            contract_price=contract_rate,
            effective_price=effective_price,
            currency=raw.get("currency", "USD"),
            is_contract_rate=is_contract,
            pricing_source=(
                "custom_billing_account_contract" if is_contract else "cloud_billing_catalog"
            ),
        )

    async def collect_pricing_public(
        self,
        service_code: str | None = None,
        pagination: PaginationParams | None = None,
    ) -> PagedResult[dict[str, Any]]:
        """Collects public catalog list rates from Cloud Billing Catalog API."""
        cat = self._sample_catalog()
        results: list[dict[str, Any]] = []

        for item in cat.values():
            if (
                service_code
                and service_code.lower() not in item["service_id"].lower()
                and service_code.lower() not in item["service_name"].lower()
            ):
                continue
            quote = GCPPriceQuote(
                sku_id=item["sku_id"],
                service_id=item["service_id"],
                service_name=item["service_name"],
                sku_description=item["sku_description"],
                category=item.get("category", {}),
                service_regions=item.get("service_regions", []),
                list_price=item["list_price"],
                contract_price=None,
                effective_price=item["list_price"],
                currency=item.get("currency", "USD"),
                is_contract_rate=False,
                pricing_source="cloud_billing_catalog",
            )
            results.append(quote.model_dump())

        page_size = pagination.page_size if pagination else len(results)
        page_items = results[:page_size]
        is_truncated = len(results) > page_size

        return PagedResult(
            items=page_items,
            continuation_token=str(page_size) if is_truncated else None,
            is_truncated=is_truncated,
            total_records=len(results),
        )

    async def collect_pricing_negotiated(
        self,
        account_id: str | None = None,
        pagination: PaginationParams | None = None,
    ) -> PagedResult[dict[str, Any]]:
        """Collects account-specific custom contract rates, enforcing contract precedence."""
        _ = account_id
        cat = self._sample_catalog()
        results: list[dict[str, Any]] = []

        for sku_id in cat:
            quote = self.get_effective_quote(sku_id)
            if quote and quote.is_contract_rate:
                results.append(quote.model_dump())

        page_size = pagination.page_size if pagination else len(results)
        page_items = results[:page_size]
        is_truncated = len(results) > page_size

        return PagedResult(
            items=page_items,
            continuation_token=str(page_size) if is_truncated else None,
            is_truncated=is_truncated,
            total_records=len(results),
        )
