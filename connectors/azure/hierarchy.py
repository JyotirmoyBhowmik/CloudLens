"""Azure Hierarchy Discovery Service (Prompt 16 / BBP Section 14.2 & 15.4).

Builds the canonical scope tree from the Azure Management Group hierarchy and subscription-to-management-group
ancestry, using ancestor chains to construct scope paths in a single pass.
Preserves tenant, management group, and subscription native identifiers and types.
"""

from __future__ import annotations

import logging
from typing import Any

from connectors.contract.models import PagedResult, PaginationParams
from domain.models.enums import ScopeRole

logger = logging.getLogger(__name__)


class AzureHierarchyService:
    """Discovers and constructs the canonical Azure scope tree in a single pass."""

    def __init__(self, tenant_id: str, config: dict[str, Any] | None = None) -> None:
        self.tenant_id = tenant_id
        self.config = config or {}

    def _build_default_sample_estate(self) -> list[dict[str, Any]]:
        """Provides a canonical enterprise hierarchy tree fixture when live ARM calls are simulated."""
        root_mg_id = f"/providers/Microsoft.Management/managementGroups/{self.tenant_id}"
        core_mg_id = f"/providers/Microsoft.Management/managementGroups/mg-core-{self.tenant_id}"
        workloads_mg_id = (
            f"/providers/Microsoft.Management/managementGroups/mg-workloads-{self.tenant_id}"
        )
        prod_mg_id = f"/providers/Microsoft.Management/managementGroups/mg-prod-{self.tenant_id}"
        nonprod_mg_id = (
            f"/providers/Microsoft.Management/managementGroups/mg-nonprod-{self.tenant_id}"
        )

        sub_prod_1 = "sub-prod-0001"
        sub_prod_2 = "sub-prod-0002"
        sub_nonprod_1 = "sub-dev-0001"

        return [
            # 1. Tenant Root Management Group
            {
                "id": root_mg_id,
                "name": self.tenant_id,
                "type": "Microsoft.Management/managementGroups",
                "properties": {
                    "displayName": f"Tenant Root Group ({self.tenant_id})",
                    "details": {"parent": None},
                    "children": [{"id": core_mg_id}, {"id": workloads_mg_id}],
                },
            },
            # 2. Core Platform Management Group
            {
                "id": core_mg_id,
                "name": f"mg-core-{self.tenant_id}",
                "type": "Microsoft.Management/managementGroups",
                "properties": {
                    "displayName": "Platform Core",
                    "details": {"parent": {"id": root_mg_id}},
                    "children": [],
                },
            },
            # 3. Workloads Management Group
            {
                "id": workloads_mg_id,
                "name": f"mg-workloads-{self.tenant_id}",
                "type": "Microsoft.Management/managementGroups",
                "properties": {
                    "displayName": "Workloads & Applications",
                    "details": {"parent": {"id": root_mg_id}},
                    "children": [{"id": prod_mg_id}, {"id": nonprod_mg_id}],
                },
            },
            # 4. Production Management Group
            {
                "id": prod_mg_id,
                "name": f"mg-prod-{self.tenant_id}",
                "type": "Microsoft.Management/managementGroups",
                "properties": {
                    "displayName": "Production Workloads",
                    "details": {"parent": {"id": workloads_mg_id}},
                    "children": [
                        {
                            "id": f"/subscriptions/{sub_prod_1}",
                            "type": "/subscriptions",
                            "displayName": "Enterprise Core Production",
                        },
                        {
                            "id": f"/subscriptions/{sub_prod_2}",
                            "type": "/subscriptions",
                            "displayName": "Enterprise Data Platform",
                        },
                    ],
                },
            },
            # 5. Non-Production Management Group
            {
                "id": nonprod_mg_id,
                "name": f"mg-nonprod-{self.tenant_id}",
                "type": "Microsoft.Management/managementGroups",
                "properties": {
                    "displayName": "Development & Test",
                    "details": {"parent": {"id": workloads_mg_id}},
                    "children": [
                        {
                            "id": f"/subscriptions/{sub_nonprod_1}",
                            "type": "/subscriptions",
                            "displayName": "Sandbox & Dev",
                        }
                    ],
                },
            },
            # 6. Subscriptions
            {
                "id": f"/subscriptions/{sub_prod_1}",
                "subscriptionId": sub_prod_1,
                "displayName": "Enterprise Core Production",
                "state": "Enabled",
                "parent_id": prod_mg_id,
                "type": "Microsoft.Resources/subscriptions",
                "offer_id": "MS-AZR-0017P",  # Enterprise Agreement
            },
            {
                "id": f"/subscriptions/{sub_prod_2}",
                "subscriptionId": sub_prod_2,
                "displayName": "Enterprise Data Platform",
                "state": "Enabled",
                "parent_id": prod_mg_id,
                "type": "Microsoft.Resources/subscriptions",
                "offer_id": "MS-AZR-0017P",
            },
            {
                "id": f"/subscriptions/{sub_nonprod_1}",
                "subscriptionId": sub_nonprod_1,
                "displayName": "Sandbox & Dev",
                "state": "Enabled",
                "parent_id": nonprod_mg_id,
                "type": "Microsoft.Resources/subscriptions",
                "offer_id": "MS-AZR-0029P",  # MSDN / Dev-Test (unsupported for export)
            },
        ]

    def build_canonical_scope_tree(
        self,
        raw_items: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """Constructs canonical scope tree with ancestor chains in a single pass.

        Preserves:
        - tenant_id
        - management group native identifiers and display names
        - subscription native identifiers and display names
        - single-pass ancestor path calculation
        """
        items = raw_items if raw_items is not None else self._build_default_sample_estate()

        # Step 1: Index all nodes by native ID and resolve parent relationships
        node_map: dict[str, dict[str, Any]] = {}
        parent_map: dict[str, str | None] = {}

        for item in items:
            node_id = item.get("id")
            if not node_id:
                continue
            node_map[node_id] = item

            # Management group parent
            if item.get("type") == "Microsoft.Management/managementGroups":
                parent_info = item.get("properties", {}).get("details", {}).get("parent")
                parent_map[node_id] = parent_info.get("id") if parent_info else None
            # Subscription parent
            elif "parent_id" in item:
                parent_map[node_id] = item["parent_id"]
            else:
                parent_map[node_id] = None

        # Step 2: Memoized single-pass ancestor chain builder
        ancestor_chains: dict[str, list[str]] = {}

        def get_ancestors(nid: str) -> list[str]:
            if nid in ancestor_chains:
                return ancestor_chains[nid]
            pid = parent_map.get(nid)
            if not pid or pid not in node_map or pid == nid:
                ancestor_chains[nid] = []
                return []
            chain = get_ancestors(pid) + [pid]
            ancestor_chains[nid] = chain
            return chain

        for nid in node_map:
            get_ancestors(nid)

        # Step 3: Emit canonical scope tree nodes
        canonical_tree: list[dict[str, Any]] = []

        for node_id, raw in node_map.items():
            ancestors = ancestor_chains.get(node_id, [])
            parent_id = parent_map.get(node_id)
            node_type = raw.get("type", "")

            if node_type == "Microsoft.Management/managementGroups":
                # Check if it's the root management group
                is_root = parent_id is None
                role = ScopeRole.ROOT_GROUP.value if is_root else ScopeRole.GROUP.value
                display_name = raw.get("properties", {}).get(
                    "displayName", raw.get("name", node_id)
                )
                native_type = "managementGroup"
            elif "subscriptions" in node_type.lower():
                role = (
                    ScopeRole.BILLING_ACCOUNT.value
                )  # Subscriptions serve as primary billing boundaries
                display_name = raw.get("displayName", raw.get("subscriptionId", node_id))
                native_type = "subscription"
            else:
                role = ScopeRole.GROUP.value
                display_name = raw.get("name", node_id)
                native_type = "resourceGroup"

            # Construct scope path from ancestor chain
            scope_path = "/" + "/".join(
                [node_map[a].get("name", a.split("/")[-1]) for a in ancestors]
                + [raw.get("name", node_id.split("/")[-1])]
            )

            canonical_node = {
                "scope_id": node_id,
                "scope_name": display_name,
                "scope_role": role,
                "scope_path": scope_path,
                "parent_id": parent_id,
                "ancestor_chain": ancestors,
                "tenant_id": self.tenant_id,
                "provider": "azure",
                "native_id": node_id,
                "native_type": native_type,
                "native_details": raw,
            }
            canonical_tree.append(canonical_node)

        return canonical_tree

    async def discover_hierarchy(
        self,
        pagination: PaginationParams | None = None,
    ) -> PagedResult[dict[str, Any]]:
        """Returns the canonical scope tree wrapped in a PagedResult."""
        tree = self.build_canonical_scope_tree()
        page_size = pagination.page_size if pagination else len(tree)
        page_items = tree[:page_size]
        is_truncated = len(tree) > page_size

        return PagedResult(
            items=page_items,
            continuation_token=str(page_size) if is_truncated else None,
            is_truncated=is_truncated,
            total_records=len(tree),
        )

    async def discover_organizations(
        self,
        pagination: PaginationParams | None = None,
    ) -> PagedResult[dict[str, Any]]:
        """Returns root management groups and tenant boundary scopes."""
        _ = pagination
        tree = self.build_canonical_scope_tree()
        orgs = [node for node in tree if node.get("parent_id") is None]
        return PagedResult(
            items=orgs, continuation_token=None, is_truncated=False, total_records=len(orgs)
        )

    async def discover_accounts(
        self,
        parent_id: str | None = None,
        pagination: PaginationParams | None = None,
    ) -> PagedResult[dict[str, Any]]:
        """Returns subscriptions under target management group scope or across the estate."""
        _ = pagination
        tree = self.build_canonical_scope_tree()
        subs = [
            node
            for node in tree
            if node.get("native_type") == "subscription"
            and (
                parent_id is None
                or node.get("parent_id") == parent_id
                or parent_id in node.get("ancestor_chain", [])
            )
        ]
        return PagedResult(
            items=subs, continuation_token=None, is_truncated=False, total_records=len(subs)
        )
