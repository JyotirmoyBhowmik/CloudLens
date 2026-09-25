"""RBAC Permission Matrix Tests for CloudLens Roles."""

from typing import NamedTuple


class RolePermission(NamedTuple):
    role: str
    allowed_permissions: set[str]


# Canonical RBAC Matrix
ROLE_PERMISSIONS: dict[str, set[str]] = {
    "GlobalAdmin": {
        "config:read",
        "config:write",
        "features:read",
        "features:toggle",
        "tenants:settings:read",
        "tenants:settings:write",
        "billing:read",
        "billing:export",
    },
    "FinOpsAdmin": {
        "config:read",
        "features:read",
        "tenants:settings:read",
        "tenants:settings:write",
        "billing:read",
        "billing:export",
    },
    "FinOpsViewer": {
        "config:read",
        "features:read",
        "tenants:settings:read",
        "billing:read",
    },
    "TenantUser": {
        "tenants:settings:read",
        "billing:read",
    },
}


def check_permission(role: str, permission: str) -> bool:
    """Evaluates whether role possesses specified permission."""
    perms = ROLE_PERMISSIONS.get(role, set())
    return permission in perms


def test_global_admin_has_full_authority():
    """Verify GlobalAdmin possesses administrative and toggle privileges."""
    admin_perms = ROLE_PERMISSIONS["GlobalAdmin"]
    assert "features:toggle" in admin_perms
    assert "config:write" in admin_perms
    assert "tenants:settings:write" in admin_perms


def test_finops_viewer_cannot_modify_settings():
    """Verify FinOpsViewer is restricted from write/mutation actions."""
    assert check_permission("FinOpsViewer", "config:read") is True
    assert check_permission("FinOpsViewer", "billing:read") is True
    assert check_permission("FinOpsViewer", "config:write") is False
    assert check_permission("FinOpsViewer", "features:toggle") is False
    assert check_permission("FinOpsViewer", "tenants:settings:write") is False


def test_tenant_user_isolated_from_global_config():
    """Verify standard TenantUser cannot view or touch global platform config."""
    assert check_permission("TenantUser", "config:read") is False
    assert check_permission("TenantUser", "features:toggle") is False
    assert check_permission("TenantUser", "billing:read") is True
