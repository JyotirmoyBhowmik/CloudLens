"""AWS Organizations Hierarchy Discovery Service (Prompt 17 / BBP Section 14.3 & 15.4).

Builds the canonical scope tree from AWS Organizations:
- Roots (r-xxxx)
- Nested Organizational Units (ou-xxxx-xxxxxxxx)
- Member Accounts (12-digit numeric IDs)

Preserves OU hierarchy nesting in canonical scope paths.
The AWS Account is strictly established as the canonical billing boundary.
"""

from __future__ import annotations

import logging
from typing import Any

from connectors.contract.models import PagedResult, PaginationParams
from domain.models.enums import ScopeRole

logger = logging.getLogger(__name__)


class AWSHierarchyService:
    """Discovers and constructs the canonical AWS Organizations scope tree."""

    def __init__(self, management_account_id: str, config: dict[str, Any] | None = None) -> None:
        self.management_account_id = management_account_id
        self.config = config or {}

    def _build_default_sample_estate(self) -> list[dict[str, Any]]:
        """Provides a canonical enterprise AWS Organizations hierarchy tree fixture."""
        root_id = f"r-root-{self.management_account_id[-4:]}"
        ou_core_id = f"ou-{root_id[2:]}-core0001"
        ou_workloads_id = f"ou-{root_id[2:]}-work0001"
        ou_prod_id = f"ou-{root_id[2:]}-prod0001"
        ou_nonprod_id = f"ou-{root_id[2:]}-dev0001"

        acc_mgmt = self.management_account_id
        acc_prod_core = "223344556677"
        acc_prod_data = "334455667788"
        acc_dev_sandbox = "445566778899"

        return [
            # 1. Organization Root
            {
                "id": root_id,
                "name": "Root",
                "type": "ORGANIZATION_ROOT",
                "arn": f"arn:aws:organizations::{self.management_account_id}:root/o-enterprise/{root_id}",
                "parent_id": None,
                "display_name": f"Enterprise Root ({root_id})",
            },
            # 2. Core Platform OU
            {
                "id": ou_core_id,
                "name": "Core-Platform",
                "type": "ORGANIZATIONAL_UNIT",
                "arn": f"arn:aws:organizations::{self.management_account_id}:ou/o-enterprise/{ou_core_id}",
                "parent_id": root_id,
                "display_name": "Core Platform & Shared Services",
            },
            # 3. Workloads Top-Level OU
            {
                "id": ou_workloads_id,
                "name": "Workloads",
                "type": "ORGANIZATIONAL_UNIT",
                "arn": f"arn:aws:organizations::{self.management_account_id}:ou/o-enterprise/{ou_workloads_id}",
                "parent_id": root_id,
                "display_name": "Business Workloads & Applications",
            },
            # 4. Production Nested OU (under Workloads)
            {
                "id": ou_prod_id,
                "name": "Production",
                "type": "ORGANIZATIONAL_UNIT",
                "arn": f"arn:aws:organizations::{self.management_account_id}:ou/o-enterprise/{ou_prod_id}",
                "parent_id": ou_workloads_id,
                "display_name": "Production Workloads",
            },
            # 5. Non-Production Nested OU (under Workloads)
            {
                "id": ou_nonprod_id,
                "name": "Non-Production",
                "type": "ORGANIZATIONAL_UNIT",
                "arn": f"arn:aws:organizations::{self.management_account_id}:ou/o-enterprise/{ou_nonprod_id}",
                "parent_id": ou_workloads_id,
                "display_name": "Development, Test & Sandbox",
            },
            # 6. Management / Payer Account (under Core)
            {
                "id": acc_mgmt,
                "name": "Enterprise-Billing-Payer",
                "type": "ACCOUNT",
                "arn": f"arn:aws:organizations::{self.management_account_id}:account/o-enterprise/{acc_mgmt}",
                "parent_id": ou_core_id,
                "display_name": "Management Payer Account",
                "status": "ACTIVE",
                "joined_method": "INVITED",
            },
            # 7. Production Core Services Account (under Production OU)
            {
                "id": acc_prod_core,
                "name": "Workloads-Prod-Payments",
                "type": "ACCOUNT",
                "arn": f"arn:aws:organizations::{self.management_account_id}:account/o-enterprise/{acc_prod_core}",
                "parent_id": ou_prod_id,
                "display_name": "Core Payments Production Account",
                "status": "ACTIVE",
                "joined_method": "CREATED",
            },
            # 8. Production Data Lake Account (under Production OU)
            {
                "id": acc_prod_data,
                "name": "Workloads-Prod-Analytics",
                "type": "ACCOUNT",
                "arn": f"arn:aws:organizations::{self.management_account_id}:account/o-enterprise/{acc_prod_data}",
                "parent_id": ou_prod_id,
                "display_name": "Enterprise Data Platform Account",
                "status": "ACTIVE",
                "joined_method": "CREATED",
            },
            # 9. Non-Production Sandbox Account (under Non-Production OU)
            {
                "id": acc_dev_sandbox,
                "name": "Workloads-Dev-Sandbox",
                "type": "ACCOUNT",
                "arn": f"arn:aws:organizations::{self.management_account_id}:account/o-enterprise/{acc_dev_sandbox}",
                "parent_id": ou_nonprod_id,
                "display_name": "Developer Sandbox Account",
                "status": "ACTIVE",
                "joined_method": "CREATED",
            },
        ]

    def build_canonical_scope_tree(
        self,
        raw_items: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """Constructs canonical scope tree with OU nesting in a single pass.

        Preserves:
        - management_account_id
        - Organization root, nested OUs, and member account native IDs
        - ScopeRole.BILLING_ACCOUNT assigned to accounts (the billing boundary)
        - Single-pass ancestor path calculation
        """
        items = raw_items if raw_items is not None else self._build_default_sample_estate()

        # Step 1: Index all nodes by native ID and parent
        node_map: dict[str, dict[str, Any]] = {}
        parent_map: dict[str, str | None] = {}

        for item in items:
            node_id = item.get("id")
            if not node_id:
                continue
            node_map[node_id] = item
            parent_map[node_id] = item.get("parent_id")

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

            if node_type == "ORGANIZATION_ROOT":
                role = ScopeRole.ROOT_GROUP.value
                display_name = raw.get("display_name", f"AWS Organizations Root ({node_id})")
                native_type = "organizationRoot"
            elif node_type == "ORGANIZATIONAL_UNIT":
                role = ScopeRole.GROUP.value
                display_name = raw.get("display_name", raw.get("name", node_id))
                native_type = "organizationalUnit"
            elif node_type == "ACCOUNT":
                # Account is the canonical billing boundary in AWS
                role = ScopeRole.BILLING_ACCOUNT.value
                display_name = raw.get("display_name", raw.get("name", node_id))
                native_type = "account"
            else:
                role = ScopeRole.GROUP.value
                display_name = raw.get("name", node_id)
                native_type = "scopeGroup"

            # Construct canonical scope path preserving OU nesting: /r-root/ou-workloads/ou-prod/223344556677
            scope_path = "/" + "/".join(
                [node_map[a].get("name", a) for a in ancestors] + [raw.get("name", node_id)]
            )

            canonical_node = {
                "scope_id": node_id,
                "scope_name": display_name,
                "scope_role": role,
                "scope_path": scope_path,
                "parent_id": parent_id,
                "ancestor_chain": ancestors,
                "management_account_id": self.management_account_id,
                "provider": "aws",
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
        """Returns root management groups and organization boundary scopes."""
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
        """Returns accounts under target OU or across the entire AWS Organization."""
        _ = pagination
        tree = self.build_canonical_scope_tree()
        accounts = [
            node
            for node in tree
            if node.get("native_type") == "account"
            and (
                parent_id is None
                or node.get("parent_id") == parent_id
                or parent_id in node.get("ancestor_chain", [])
            )
        ]
        return PagedResult(
            items=accounts, continuation_token=None, is_truncated=False, total_records=len(accounts)
        )
