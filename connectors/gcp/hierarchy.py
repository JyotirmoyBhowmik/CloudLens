"""GCP Resource Manager and Cloud Billing Hierarchy Discovery Service (Prompt 18 / BBP Section 14.4 & 15.4).

Builds the canonical scope tree from Google Cloud Resource Manager and Cloud Billing:
- Organizations (organizations/{id})
- Nested Folders (folders/{id})
- Projects (projects/{id} or {project-id})
- Cloud Billing Accounts (billingAccounts/{id})

STRICT ARCHITECTURAL RULE:
The billing hierarchy and the resource hierarchy are distinct and must both be represented
without conflation. Billing accounts are NEVER placed as parents or children of folders.
Instead, projects declare their linked Cloud Billing Account, and billing accounts are
discovered as distinct linked root billing scopes.
"""

from __future__ import annotations

import logging
from typing import Any

from connectors.contract.models import PagedResult, PaginationParams
from connectors.gcp.models import is_valid_gcp_billing_account_id
from domain.models.enums import ScopeRole

logger = logging.getLogger(__name__)


class GCPHierarchyService:
    """Discovers and constructs the canonical GCP scope tree preserving dual hierarchy representation."""

    def __init__(
        self,
        primary_project_id: str = "proj-cloudlens-core",
        organization_id: str = "1092837465",
        billing_account_id: str = "01ABCD-2345EF-6789GH",
        config: dict[str, Any] | None = None,
    ) -> None:
        self.primary_project_id = primary_project_id
        self.organization_id = organization_id
        self.billing_account_id = billing_account_id
        self.config = config or {}

    def _build_default_sample_estate(self) -> list[dict[str, Any]]:
        """Provides a canonical enterprise Google Cloud Resource Manager and Cloud Billing tree."""
        org_id = f"organizations/{self.organization_id}"
        folder_core = "folders/1111222233"
        folder_workloads = "folders/4444555566"
        folder_retail = "folders/9876543210"
        folder_data = "folders/7777888899"

        proj_retail = "proj-retail-banking-prod"
        proj_analytics = "proj-ai-recommendations-analytics"
        proj_network = "proj-shared-vpc-host"
        proj_core = self.primary_project_id

        billing_id = self.billing_account_id
        billing_uri = f"billingAccounts/{billing_id}"

        return [
            # ==================================================================
            # 1. Resource Hierarchy: Organization -> Nested Folders -> Projects
            # ==================================================================
            {
                "id": org_id,
                "name": "enterprise.cloudlens.internal",
                "type": "ORGANIZATION",
                "parent_id": None,
                "display_name": f"CloudLens Global Enterprise ({org_id})",
                "hierarchy_type": "RESOURCE",
            },
            {
                "id": folder_core,
                "name": "core-infrastructure",
                "type": "FOLDER",
                "parent_id": org_id,
                "display_name": "Core Infrastructure & Networking",
                "hierarchy_type": "RESOURCE",
            },
            {
                "id": folder_workloads,
                "name": "workloads",
                "type": "FOLDER",
                "parent_id": org_id,
                "display_name": "Enterprise Business Workloads",
                "hierarchy_type": "RESOURCE",
            },
            {
                "id": folder_retail,
                "name": "retail-banking",
                "type": "FOLDER",
                "parent_id": folder_workloads,
                "display_name": "Retail Banking Applications",
                "hierarchy_type": "RESOURCE",
            },
            {
                "id": folder_data,
                "name": "data-analytics",
                "type": "FOLDER",
                "parent_id": folder_workloads,
                "display_name": "Data Intelligence & Analytics",
                "hierarchy_type": "RESOURCE",
            },
            {
                "id": f"projects/{proj_core}",
                "name": proj_core,
                "type": "PROJECT",
                "parent_id": folder_core,
                "display_name": "CloudLens Core Administration",
                "linked_billing_account": billing_uri,
                "hierarchy_type": "RESOURCE",
            },
            {
                "id": f"projects/{proj_network}",
                "name": proj_network,
                "type": "PROJECT",
                "parent_id": folder_core,
                "display_name": "Shared VPC Network Host",
                "linked_billing_account": billing_uri,
                "hierarchy_type": "RESOURCE",
            },
            {
                "id": f"projects/{proj_retail}",
                "name": proj_retail,
                "type": "PROJECT",
                "parent_id": folder_retail,
                "display_name": "Retail Banking Production",
                "linked_billing_account": billing_uri,
                "hierarchy_type": "RESOURCE",
            },
            {
                "id": f"projects/{proj_analytics}",
                "name": proj_analytics,
                "type": "PROJECT",
                "parent_id": folder_data,
                "display_name": "AI Recommendations Analytics",
                "linked_billing_account": billing_uri,
                "hierarchy_type": "RESOURCE",
            },
            # ==================================================================
            # 2. Billing Hierarchy: Separate Linked Scope Tree (Not folded into folders)
            # ==================================================================
            {
                "id": billing_uri,
                "name": billing_id,
                "type": "BILLING_ACCOUNT",
                "parent_id": None,  # Strictly distinct root; not parented by organization or folder
                "display_name": f"CloudLens Master Enterprise Billing ({billing_id})",
                "hierarchy_type": "BILLING",
                "open": True,
                "linked_projects": [
                    f"projects/{proj_core}",
                    f"projects/{proj_network}",
                    f"projects/{proj_retail}",
                    f"projects/{proj_analytics}",
                ],
            },
        ]

    def build_canonical_scope_tree(
        self, custom_items: list[dict[str, Any]] | None = None
    ) -> list[dict[str, Any]]:
        """Constructs the canonical scope tree preserving dual hierarchy representation and folder nesting.

        Single-pass memoized ancestor traversal ensures O(N) path construction.
        """
        items = custom_items if custom_items is not None else self._build_default_sample_estate()

        node_map: dict[str, dict[str, Any]] = {}
        parent_map: dict[str, str | None] = {}

        for item in items:
            node_id = item.get("id")
            if not node_id:
                continue
            node_map[node_id] = item
            parent_map[node_id] = item.get("parent_id")

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

        canonical_tree: list[dict[str, Any]] = []

        for node_id, raw in node_map.items():
            ancestors = ancestor_chains.get(node_id, [])
            parent_id = parent_map.get(node_id)
            node_type = raw.get("type", "")
            h_type = raw.get("hierarchy_type", "RESOURCE")

            if node_type == "ORGANIZATION":
                role = ScopeRole.ROOT_GROUP.value
                display_name = raw.get("display_name", f"GCP Organization ({node_id})")
                native_type = "organization"
                scope_path = f"/{node_id}"
            elif node_type == "FOLDER":
                role = ScopeRole.GROUP.value
                display_name = raw.get("display_name", raw.get("name", node_id))
                native_type = "folder"
                scope_path = "/" + "/".join(ancestors + [node_id])
            elif node_type == "PROJECT":
                # GCP Project is the resource leaf and runtime billing boundary for services
                role = ScopeRole.BILLING_BOUNDARY.value
                display_name = raw.get("display_name", raw.get("name", node_id))
                native_type = "project"
                scope_path = "/" + "/".join(ancestors + [node_id])
            elif node_type == "BILLING_ACCOUNT":
                # Cloud Billing Account is a distinct linked billing scope
                role = ScopeRole.BILLING_ACCOUNT.value
                display_name = raw.get("display_name", f"Cloud Billing Account ({node_id})")
                native_type = "billingAccount"
                scope_path = f"/{node_id}"
            else:
                role = ScopeRole.GROUP.value
                display_name = raw.get("name", node_id)
                native_type = "scopeGroup"
                scope_path = "/" + "/".join(ancestors + [node_id])

            canonical_node: dict[str, Any] = {
                "scope_id": node_id,
                "scope_name": display_name,
                "scope_role": role,
                "scope_path": scope_path,
                "parent_id": parent_id,
                "ancestor_chain": ancestors,
                "hierarchy_type": h_type,
                "provider": "gcp",
                "native_id": node_id,
                "native_type": native_type,
                "native_details": raw,
            }

            if "linked_billing_account" in raw:
                canonical_node["linked_billing_account_id"] = raw["linked_billing_account"]
            if "linked_projects" in raw:
                canonical_node["linked_projects"] = raw["linked_projects"]

            canonical_tree.append(canonical_node)

        return canonical_tree

    async def discover_hierarchy(
        self,
        pagination: PaginationParams | None = None,
    ) -> PagedResult[dict[str, Any]]:
        """Returns the complete dual hierarchy scope tree wrapped in a PagedResult."""
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
        """Returns organization roots and distinct Cloud Billing Account boundary scopes."""
        _ = pagination
        tree = self.build_canonical_scope_tree()
        roots = [
            node
            for node in tree
            if node.get("parent_id") is None
            or node.get("scope_role")
            in (ScopeRole.ROOT_GROUP.value, ScopeRole.BILLING_ACCOUNT.value)
        ]
        return PagedResult(
            items=roots,
            continuation_token=None,
            is_truncated=False,
            total_records=len(roots),
        )

    async def discover_accounts(
        self,
        parent_id: str | None = None,
        pagination: PaginationParams | None = None,
    ) -> PagedResult[dict[str, Any]]:
        """Returns projects and linked billing accounts with explicit cross-references."""
        _ = pagination
        tree = self.build_canonical_scope_tree()

        if parent_id:
            accounts = [
                node
                for node in tree
                if (
                    node.get("parent_id") == parent_id
                    or parent_id in node.get("ancestor_chain", [])
                )
                and node.get("scope_role")
                in (
                    ScopeRole.BILLING_BOUNDARY.value,
                    ScopeRole.BILLING_ACCOUNT.value,
                )
            ]
        else:
            accounts = [
                node
                for node in tree
                if node.get("scope_role")
                in (
                    ScopeRole.BILLING_BOUNDARY.value,
                    ScopeRole.BILLING_ACCOUNT.value,
                )
            ]

        return PagedResult(
            items=accounts,
            continuation_token=None,
            is_truncated=False,
            total_records=len(accounts),
        )

    def validate_billing_account(self, account_id: str) -> bool:
        """Validates that a billing account identifier conforms to the 18-character hex pattern."""
        clean_id = account_id.replace("billingAccounts/", "").strip()
        return is_valid_gcp_billing_account_id(clean_id)
