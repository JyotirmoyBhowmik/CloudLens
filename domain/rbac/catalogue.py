"""RBAC Permission Catalogue and Built-in Roles Registry (Prompt 11 Item 70, 73).

Implements:
- Permission catalogue as data.
- Nine built-in roles:
  1. Super Admin (GLOBAL_ADMIN)
  2. Platform Admin (TENANT_ADMIN)
  3. Cloud Administrator (CLOUD_ARCHITECT)
  4. FinOps Administrator (FINOPS_ADMIN)
  5. Finance User (FINOPS_ANALYST)
  6. IT Operations User (TENANT_USER)
  7. Application Owner (DEVELOPER)
  8. Read Only User (FINOPS_VIEWER)
  9. Auditor (SECURITY_AUDITOR)
- Custom roles composed from the same catalogue.
- Separation of financial detail (charge lines, rates) from cost totals permission (Item 73).
"""

from typing import Any

from domain.models.enums import SystemRole
from domain.models.exceptions import CustomRoleInvalidException
from domain.rbac.models import Permission, RoleDefinition

# Canonical Permission Definitions
CANONICAL_PERMISSIONS: list[dict[str, Any]] = [
    {
        "code": "config:read",
        "display_name": "Read System Configuration",
        "description": "View system-level configuration parameters.",
        "domain": "config",
        "action": "read",
    },
    {
        "code": "config:write",
        "display_name": "Modify System Configuration",
        "description": "Update system-level configuration parameters.",
        "domain": "config",
        "action": "write",
    },
    {
        "code": "features:read",
        "display_name": "Read Feature Flags",
        "description": "View active platform and tenant feature toggles.",
        "domain": "features",
        "action": "read",
    },
    {
        "code": "features:toggle",
        "display_name": "Toggle Feature Flags",
        "description": "Enable, disable, or adjust rollout percentage of feature flags.",
        "domain": "features",
        "action": "toggle",
    },
    {
        "code": "tenants:settings:read",
        "display_name": "Read Tenant Settings",
        "description": "View tenant-level preferences, calendars, and thresholds.",
        "domain": "tenants",
        "action": "read",
    },
    {
        "code": "tenants:settings:write",
        "display_name": "Modify Tenant Settings",
        "description": "Update tenant-level preferences, calendars, and retention profiles.",
        "domain": "tenants",
        "action": "write",
    },
    {
        "code": "billing:read",
        "display_name": "Read Billing & Cost Data",
        "description": "View aggregate spend, historical costs, and trend charts.",
        "domain": "billing",
        "action": "read",
    },
    {
        "code": "billing:export",
        "display_name": "Export Billing Data",
        "description": "Download and export raw or aggregated billing datasets.",
        "domain": "billing",
        "action": "export",
    },
    {
        "code": "cost:totals:read",
        "display_name": "Read Cost Totals",
        "description": "View cost totals and aggregates without granular unit rates (Prompt 11 Item 73).",
        "domain": "billing",
        "action": "read_totals",
    },
    {
        "code": "financial:detail:read",
        "display_name": "Read Financial Detail & Rates",
        "description": "View granular charge lines, negotiated rates, and unit price details (Prompt 11 Item 73).",
        "domain": "pricing",
        "action": "read_detail",
    },
    {
        "code": "pricing:read",
        "display_name": "Read Pricing & Dimensions",
        "description": "View list prices, dimensions, and FOCUS classifications.",
        "domain": "pricing",
        "action": "read",
    },
    {
        "code": "pricing:write",
        "display_name": "Modify Pricing & Dimensions",
        "description": "Register custom escape hatch dimensions or pricing rules.",
        "domain": "pricing",
        "action": "write",
    },
    {
        "code": "rate_cards:read",
        "display_name": "Read Rate Cards",
        "description": "View contracted rates and negotiated discount structures.",
        "domain": "rate_cards",
        "action": "read",
    },
    {
        "code": "rate_cards:write",
        "display_name": "Modify Rate Cards",
        "description": "Create and update negotiated enterprise rate cards.",
        "domain": "rate_cards",
        "action": "write",
    },
    {
        "code": "budgets:read",
        "display_name": "Read Budgets",
        "description": "View allocated scope budgets, periods, and burn rates.",
        "domain": "budgets",
        "action": "read",
    },
    {
        "code": "budgets:write",
        "display_name": "Modify Budgets",
        "description": "Define and adjust scope-level budgets and allocations.",
        "domain": "budgets",
        "action": "write",
    },
    {
        "code": "budgets:approve",
        "display_name": "Approve Budgets",
        "description": "Approve threshold overrides and emergency budget elevations.",
        "domain": "budgets",
        "action": "approve",
    },
    {
        "code": "thresholds:read",
        "display_name": "Read Thresholds",
        "description": "View configured threshold bands and alert rules.",
        "domain": "thresholds",
        "action": "read",
    },
    {
        "code": "thresholds:write",
        "display_name": "Modify Thresholds",
        "description": "Define and adjust anomaly and consumption threshold bands.",
        "domain": "thresholds",
        "action": "write",
    },
    {
        "code": "inventory:read",
        "display_name": "Read Resource Inventory",
        "description": "View discovered multi-cloud resources and hierarchies.",
        "domain": "inventory",
        "action": "read",
    },
    {
        "code": "inventory:export",
        "display_name": "Export Resource Inventory",
        "description": "Export inventory records and dependency trees.",
        "domain": "inventory",
        "action": "export",
    },
    {
        "code": "inventory:write",
        "display_name": "Manage Resource Inventory",
        "description": "Update tags, ownership attribution, and metadata.",
        "domain": "inventory",
        "action": "write",
    },
    {
        "code": "connectors:read",
        "display_name": "Read Connectors",
        "description": "View cloud provider connector statuses and sync schedules.",
        "domain": "connectors",
        "action": "read",
    },
    {
        "code": "connectors:write",
        "display_name": "Configure Connectors",
        "description": "Register, modify, or delete cloud provider connectors.",
        "domain": "connectors",
        "action": "write",
    },
    {
        "code": "connectors:sync",
        "display_name": "Trigger Connector Sync",
        "description": "Manually trigger on-demand synchronization for a connector.",
        "domain": "connectors",
        "action": "sync",
    },
    {
        "code": "connectors:validate",
        "display_name": "Validate Connector Credentials",
        "description": "Run pre-flight permission validation against provider credentials.",
        "domain": "connectors",
        "action": "validate",
    },
    {
        "code": "governance:read",
        "display_name": "Read Governance Policies",
        "description": "Inspect policy definitions and rule evaluation results.",
        "domain": "governance",
        "action": "read",
    },
    {
        "code": "governance:write",
        "display_name": "Modify Governance Policies",
        "description": "Create, enable, or disable FinOps governance policies.",
        "domain": "governance",
        "action": "write",
    },
    {
        "code": "policies:evaluate",
        "display_name": "Evaluate Policies",
        "description": "Simulate and trigger policy evaluation runs across resources.",
        "domain": "governance",
        "action": "evaluate",
    },
    {
        "code": "audit:read",
        "display_name": "Read Audit Trail",
        "description": "Inspect append-only system and security audit logs.",
        "domain": "audit",
        "action": "read",
    },
    {
        "code": "audit:export",
        "display_name": "Export Audit Logs",
        "description": "Export signed audit trail events for compliance review.",
        "domain": "audit",
        "action": "export",
    },
    {
        "code": "reports:read",
        "display_name": "Read Reports",
        "description": "View pre-generated cost, usage, and variance reports.",
        "domain": "reports",
        "action": "read",
    },
    {
        "code": "reports:generate",
        "display_name": "Generate Reports",
        "description": "Trigger ad-hoc financial and operational report generation.",
        "domain": "reports",
        "action": "generate",
    },
    {
        "code": "reports:export",
        "display_name": "Export Reports",
        "description": "Download generated reports in CSV, PDF, or Parquet format.",
        "domain": "reports",
        "action": "export",
    },
    {
        "code": "users:read",
        "display_name": "Read Users",
        "description": "List users, role assignments, and scope grants.",
        "domain": "users",
        "action": "read",
    },
    {
        "code": "users:write",
        "display_name": "Modify Users",
        "description": "Create users, assign roles, and configure scope grants.",
        "domain": "users",
        "action": "write",
    },
    {
        "code": "roles:read",
        "display_name": "Read Roles",
        "description": "View role definitions and permission matrices.",
        "domain": "roles",
        "action": "read",
    },
    {
        "code": "roles:write",
        "display_name": "Modify Roles",
        "description": "Create or update custom RBAC roles and permission sets.",
        "domain": "roles",
        "action": "write",
    },
    {
        "code": "masterdata:read",
        "display_name": "Read Master Data",
        "description": "View reference catalogues and master data records.",
        "domain": "masterdata",
        "action": "read",
    },
    {
        "code": "masterdata:write",
        "display_name": "Modify Master Data",
        "description": "Create draft master data records and initiate change requests.",
        "domain": "masterdata",
        "action": "write",
    },
    {
        "code": "masterdata:approve",
        "display_name": "Approve Master Data",
        "description": "Review and approve/reject master data changes.",
        "domain": "masterdata",
        "action": "approve",
    },
    {
        "code": "quotas:read",
        "display_name": "Read Cloud Quotas",
        "description": "View quota consumption, limits, and headroom tracking.",
        "domain": "quotas",
        "action": "read",
    },
    {
        "code": "quotas:write",
        "display_name": "Manage Cloud Quotas",
        "description": "Configure quota alert thresholds and target buffer headroom.",
        "domain": "quotas",
        "action": "write",
    },
    {
        "code": "credentials:create",
        "display_name": "Create High-Risk Credentials",
        "description": "Create break-glass accounts, machine clients, or API tokens.",
        "domain": "identity",
        "action": "create",
    },
    {
        "code": "overrides:apply",
        "display_name": "Apply Governance Overrides",
        "description": "Suppress or override policy violation gates.",
        "domain": "governance",
        "action": "apply_override",
    },
]

# Canonical Nine Built-in Roles (Prompt 11 Item 70)
# Maps technical SystemRole to canonical title, description, and permission grant
BUILT_IN_ROLES: dict[str, dict[str, Any]] = {
    # 1. Super Admin
    SystemRole.GLOBAL_ADMIN.value: {
        "display_name": "Super Admin",
        "description": "Full platform-wide administrative authority across all tenants and subsystems.",
        "max_scope": "PLATFORM",
        "requires_mfa": True,
        "allowed_permissions": [p["code"] for p in CANONICAL_PERMISSIONS],
    },
    # 2. Platform Admin
    SystemRole.TENANT_ADMIN.value: {
        "display_name": "Platform Admin",
        "description": "Administrative authority within the tenant boundary (settings, users, connectors, policies).",
        "max_scope": "TENANT",
        "requires_mfa": True,
        "allowed_permissions": [
            "config:read",
            "features:read",
            "tenants:settings:read",
            "tenants:settings:write",
            "billing:read",
            "billing:export",
            "cost:totals:read",
            "financial:detail:read",
            "connectors:read",
            "connectors:write",
            "connectors:sync",
            "connectors:validate",
            "inventory:read",
            "inventory:export",
            "inventory:write",
            "budgets:read",
            "budgets:write",
            "budgets:approve",
            "thresholds:read",
            "thresholds:write",
            "governance:read",
            "governance:write",
            "policies:evaluate",
            "reports:read",
            "reports:generate",
            "reports:export",
            "users:read",
            "users:write",
            "roles:read",
            "masterdata:read",
            "quotas:read",
            "quotas:write",
            "credentials:create",
            "overrides:apply",
            "audit:read",
            "audit:export",
        ],
    },
    # 3. Cloud Administrator
    SystemRole.CLOUD_ARCHITECT.value: {
        "display_name": "Cloud Administrator",
        "description": "Infrastructure topology, resource inventory, connectors, quotas, and architecture gates.",
        "max_scope": "SCOPE",
        "requires_mfa": False,
        "allowed_permissions": [
            "config:read",
            "inventory:read",
            "inventory:export",
            "inventory:write",
            "connectors:read",
            "thresholds:read",
            "governance:read",
            "policies:evaluate",
            "quotas:read",
            "billing:read",
            "cost:totals:read",
            "reports:read",
        ],
    },
    # 4. FinOps Administrator
    SystemRole.FINOPS_ADMIN.value: {
        "display_name": "FinOps Administrator",
        "description": "Management of FinOps budgets, thresholds, rate cards, commitments, and cost allocations.",
        "max_scope": "TENANT",
        "requires_mfa": True,
        "allowed_permissions": [
            "config:read",
            "features:read",
            "tenants:settings:read",
            "tenants:settings:write",
            "billing:read",
            "billing:export",
            "cost:totals:read",
            "financial:detail:read",
            "pricing:read",
            "pricing:write",
            "rate_cards:read",
            "rate_cards:write",
            "budgets:read",
            "budgets:write",
            "budgets:approve",
            "thresholds:read",
            "thresholds:write",
            "governance:read",
            "governance:write",
            "policies:evaluate",
            "inventory:read",
            "reports:read",
            "reports:generate",
            "reports:export",
            "masterdata:read",
            "quotas:read",
            "overrides:apply",
        ],
    },
    # 5. Finance User
    SystemRole.FINOPS_ANALYST.value: {
        "display_name": "Finance User",
        "description": "FinOps analytics, cost modeling, rate analysis, anomaly investigation, and report generation.",
        "max_scope": "SCOPE",
        "requires_mfa": False,
        "allowed_permissions": [
            "config:read",
            "features:read",
            "tenants:settings:read",
            "billing:read",
            "billing:export",
            "cost:totals:read",
            "financial:detail:read",
            "pricing:read",
            "rate_cards:read",
            "budgets:read",
            "thresholds:read",
            "inventory:read",
            "reports:read",
            "reports:generate",
            "reports:export",
            "masterdata:read",
            "quotas:read",
        ],
    },
    # 6. IT Operations User
    SystemRole.TENANT_USER.value: {
        "display_name": "IT Operations User",
        "description": "Scope-bounded visibility into technical infrastructure and cost totals without rates (Item 73).",
        "max_scope": "SCOPE",
        "requires_mfa": False,
        "allowed_permissions": [
            "tenants:settings:read",
            "billing:read",
            "cost:totals:read",
            "inventory:read",
            "reports:read",
        ],
    },
    # 7. Application Owner
    SystemRole.DEVELOPER.value: {
        "display_name": "Application Owner",
        "description": "Scope-bounded visibility into application resources, unit economics, team metrics, and budgets.",
        "max_scope": "SCOPE",
        "requires_mfa": False,
        "allowed_permissions": [
            "inventory:read",
            "billing:read",
            "cost:totals:read",
            "budgets:read",
            "thresholds:read",
            "reports:read",
        ],
    },
    # 8. Read Only User
    SystemRole.FINOPS_VIEWER.value: {
        "display_name": "Read Only User",
        "description": "Read-only access to billing data, budgets, and executive financial dashboards.",
        "max_scope": "SCOPE",
        "requires_mfa": False,
        "allowed_permissions": [
            "config:read",
            "features:read",
            "tenants:settings:read",
            "billing:read",
            "cost:totals:read",
            "reports:read",
            "quotas:read",
        ],
    },
    # 9. Auditor
    SystemRole.SECURITY_AUDITOR.value: {
        "display_name": "Auditor",
        "description": "Audit trail inspection, access reviews, compliance reporting, and policy verification.",
        "max_scope": "TENANT",
        "requires_mfa": False,
        "allowed_permissions": [
            "audit:read",
            "audit:export",
            "governance:read",
            "inventory:read",
            "roles:read",
            "users:read",
            "reports:read",
            "reports:export",
        ],
    },
}

# Role Title and Synonym Lookup Map
ROLE_SYNONYMS: dict[str, str] = {
    "super admin": SystemRole.GLOBAL_ADMIN.value,
    "superadmin": SystemRole.GLOBAL_ADMIN.value,
    "global admin": SystemRole.GLOBAL_ADMIN.value,
    "global administrator": SystemRole.GLOBAL_ADMIN.value,
    "global_admin": SystemRole.GLOBAL_ADMIN.value,
    "platform admin": SystemRole.TENANT_ADMIN.value,
    "platform administrator": SystemRole.TENANT_ADMIN.value,
    "tenant admin": SystemRole.TENANT_ADMIN.value,
    "tenant administrator": SystemRole.TENANT_ADMIN.value,
    "tenant_admin": SystemRole.TENANT_ADMIN.value,
    "cloud administrator": SystemRole.CLOUD_ARCHITECT.value,
    "cloud admin": SystemRole.CLOUD_ARCHITECT.value,
    "cloud architect": SystemRole.CLOUD_ARCHITECT.value,
    "cloud_architect": SystemRole.CLOUD_ARCHITECT.value,
    "finops administrator": SystemRole.FINOPS_ADMIN.value,
    "finops admin": SystemRole.FINOPS_ADMIN.value,
    "finops_admin": SystemRole.FINOPS_ADMIN.value,
    "finance user": SystemRole.FINOPS_ANALYST.value,
    "finops analyst": SystemRole.FINOPS_ANALYST.value,
    "finops_analyst": SystemRole.FINOPS_ANALYST.value,
    "it operations user": SystemRole.TENANT_USER.value,
    "it operations": SystemRole.TENANT_USER.value,
    "tenant user": SystemRole.TENANT_USER.value,
    "tenant_user": SystemRole.TENANT_USER.value,
    "application owner": SystemRole.DEVELOPER.value,
    "developer": SystemRole.DEVELOPER.value,
    "read only user": SystemRole.FINOPS_VIEWER.value,
    "read only": SystemRole.FINOPS_VIEWER.value,
    "finops viewer": SystemRole.FINOPS_VIEWER.value,
    "finops_viewer": SystemRole.FINOPS_VIEWER.value,
    "auditor": SystemRole.SECURITY_AUDITOR.value,
    "security auditor": SystemRole.SECURITY_AUDITOR.value,
    "security & compliance auditor": SystemRole.SECURITY_AUDITOR.value,
    "security_auditor": SystemRole.SECURITY_AUDITOR.value,
}


class PermissionCatalogue:
    """In-memory and master-data-driven registry of platform permissions and roles."""

    def __init__(self) -> None:
        self._permissions: dict[str, Permission] = {}
        self._roles: dict[str, RoleDefinition] = {}
        self._custom_roles: dict[
            tuple[str, str], RoleDefinition
        ] = {}  # (tenant_id, role_code) -> RoleDefinition

        # Populate permissions catalogue
        for p_data in CANONICAL_PERMISSIONS:
            perm = Permission(
                id=f"perm-{p_data['code'].replace(':', '-')}",
                code=p_data["code"],
                display_name=p_data["display_name"],
                description=p_data["description"],
                domain=p_data["domain"],
                action=p_data["action"],
                is_system=True,
            )
            self._permissions[perm.code] = perm

        # Populate built-in roles
        for role_code, r_data in BUILT_IN_ROLES.items():
            role_def = RoleDefinition(
                id=f"role-{role_code.lower()}",
                code=role_code,
                display_name=r_data["display_name"],
                description=r_data["description"],
                is_built_in=True,
                allowed_permissions=r_data["allowed_permissions"],
                tenant_id=None,
                max_scope=r_data["max_scope"],
                requires_mfa=r_data["requires_mfa"],
            )
            self._roles[role_code] = role_def

    def list_permissions(self) -> list[Permission]:
        """Returns all permissions defined in the catalogue."""
        return list(self._permissions.values())

    def get_permission(self, code: str) -> Permission | None:
        """Retrieves permission by code."""
        return self._permissions.get(code)

    def is_valid_permission(self, code: str) -> bool:
        """Checks if a permission code exists in the platform catalogue."""
        return code in self._permissions

    def list_built_in_roles(self) -> list[RoleDefinition]:
        """Returns the nine built-in role definitions."""
        return list(self._roles.values())

    def resolve_role_code(self, role_name_or_code: str) -> str | None:
        """Resolves a role name, title, or code to canonical code."""
        cleaned = role_name_or_code.strip()
        if cleaned in self._roles:
            return cleaned
        lower = cleaned.lower()
        return ROLE_SYNONYMS.get(lower)

    def get_role(
        self, role_code_or_name: str, tenant_id: str | None = None
    ) -> RoleDefinition | None:
        """Retrieves a built-in or tenant-custom role definition."""
        canonical_code = self.resolve_role_code(role_code_or_name)
        if canonical_code and canonical_code in self._roles:
            return self._roles[canonical_code]

        if tenant_id:
            custom_key = (tenant_id, role_code_or_name)
            if custom_key in self._custom_roles:
                return self._custom_roles[custom_key]

        return None

    def register_custom_role(
        self,
        tenant_id: str,
        code: str,
        display_name: str,
        description: str,
        allowed_permissions: list[str],
    ) -> RoleDefinition:
        """Creates a custom role composed from the same catalogue (Prompt 11 Item 70).

        Raises CustomRoleInvalidException if any permission is uncatalogued.
        """
        # Validate that all permissions exist in catalogue
        invalid_perms = [p for p in allowed_permissions if p not in self._permissions]
        if invalid_perms:
            raise CustomRoleInvalidException(
                f"Custom role '{code}' references uncatalogued permissions: {invalid_perms}."
            )

        role_code = code.upper().strip()
        custom_key = (tenant_id, role_code)

        custom_role = RoleDefinition(
            id=f"crole-{tenant_id}-{role_code.lower()}",
            code=role_code,
            display_name=display_name,
            description=description,
            is_built_in=False,
            allowed_permissions=sorted(set(allowed_permissions)),
            tenant_id=tenant_id,
            max_scope="SCOPE",
            requires_mfa=False,
        )
        self._custom_roles[custom_key] = custom_role
        return custom_role

    def list_roles_for_tenant(self, tenant_id: str) -> list[RoleDefinition]:
        """Returns built-in roles plus all custom roles defined on the specified tenant."""
        roles = list(self._roles.values())
        for (tid, _), crole in self._custom_roles.items():
            if tid == tenant_id:
                roles.append(crole)
        return roles


# Global Singleton PermissionCatalogue
_catalogue = PermissionCatalogue()


def get_permission_catalogue() -> PermissionCatalogue:
    """Returns the shared PermissionCatalogue singleton."""
    return _catalogue
