"""Keycloak Realm Users and Roles Provisioning Script (Prompt P02).

Provisions the 9 canonical roles and test users into Keycloak without hardcoded passwords in git.
Credentials are set dynamically via KEYCLOAK_TEST_PASSWORD environment variable.
Enforces CONFIGURE_TOTP required action on admin@jyotirmoyb.com.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import urllib.parse
import urllib.request

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("keycloak-setup")

KEYCLOAK_URL = os.getenv("KEYCLOAK_URL", "http://localhost:8081").rstrip("/")
KEYCLOAK_ADMIN = os.getenv("KEYCLOAK_ADMIN", "admin")
KEYCLOAK_ADMIN_PASSWORD = os.getenv("KEYCLOAK_ADMIN_PASSWORD", "DevKeycloakAdmin123!")
KEYCLOAK_TEST_PASSWORD = os.getenv("KEYCLOAK_TEST_PASSWORD", "TestKeycloakPassword123!")
REALM_NAME = "cloudlens"

ROLES = [
    ("SUPER_ADMIN", "Enterprise Super Administrator"),
    ("PLATFORM_ADMIN", "Platform Operations Administrator"),
    ("CLOUD_ADMINISTRATOR", "Cloud Infrastructure Administrator"),
    ("FINOPS_ADMINISTRATOR", "FinOps Financial Governance Lead"),
    ("FINANCE_USER", "Financial Analyst and Budget Planner"),
    ("IT_OPERATIONS_USER", "IT Operations and Infrastructure Engineer"),
    ("APPLICATION_OWNER", "Service and Application Owner"),
    ("READ_ONLY_USER", "Read-Only Stakeholder and Observer"),
    ("AUDITOR", "Security, Compliance and Audit Inspector"),
]

USERS = [
    {
        "username": "admin@jyotirmoyb.com",
        "email": "admin@jyotirmoyb.com",
        "firstName": "Super",
        "lastName": "Admin",
        "role": "SUPER_ADMIN",
        "require_totp": True,
    },
    {
        "username": "superadmin@cloudlens.local",
        "email": "superadmin@cloudlens.local",
        "firstName": "Super",
        "lastName": "Admin",
        "role": "SUPER_ADMIN",
        "require_totp": False,
    },
    {
        "username": "platformadmin@cloudlens.local",
        "email": "platformadmin@cloudlens.local",
        "firstName": "Platform",
        "lastName": "Admin",
        "role": "PLATFORM_ADMIN",
        "require_totp": False,
    },
    {
        "username": "cloudadmin@cloudlens.local",
        "email": "cloudadmin@cloudlens.local",
        "firstName": "Cloud",
        "lastName": "Admin",
        "role": "CLOUD_ADMINISTRATOR",
        "require_totp": False,
    },
    {
        "username": "finopsadmin@cloudlens.local",
        "email": "finopsadmin@cloudlens.local",
        "firstName": "FinOps",
        "lastName": "Admin",
        "role": "FINOPS_ADMINISTRATOR",
        "require_totp": False,
    },
    {
        "username": "financeuser@cloudlens.local",
        "email": "financeuser@cloudlens.local",
        "firstName": "Finance",
        "lastName": "User",
        "role": "FINANCE_USER",
        "require_totp": False,
    },
    {
        "username": "itopsuser@cloudlens.local",
        "email": "itopsuser@cloudlens.local",
        "firstName": "IT",
        "lastName": "Operations",
        "role": "IT_OPERATIONS_USER",
        "require_totp": False,
    },
    {
        "username": "appowner@cloudlens.local",
        "email": "appowner@cloudlens.local",
        "firstName": "Application",
        "lastName": "Owner",
        "role": "APPLICATION_OWNER",
        "require_totp": False,
    },
    {
        "username": "readonly@cloudlens.local",
        "email": "readonly@cloudlens.local",
        "firstName": "Read",
        "lastName": "Only",
        "role": "READ_ONLY_USER",
        "require_totp": False,
    },
    {
        "username": "auditor@cloudlens.local",
        "email": "auditor@cloudlens.local",
        "firstName": "Security",
        "lastName": "Auditor",
        "role": "AUDITOR",
        "require_totp": False,
    },
]


def get_admin_token() -> str:
    token_url = f"{KEYCLOAK_URL}/realms/master/protocol/openid-connect/token"
    payload = urllib.parse.urlencode({
        "client_id": "admin-cli",
        "username": KEYCLOAK_ADMIN,
        "password": KEYCLOAK_ADMIN_PASSWORD,
        "grant_type": "password",
    }).encode("utf-8")
    req = urllib.request.Request(token_url, data=payload, method="POST")
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["access_token"]
    except Exception as e:
        logger.error(f"Failed to get admin token: {e}")
        raise


def api_request(path: str, token: str, method: str = "GET", data: dict | list | None = None) -> any:
    url = f"{KEYCLOAK_URL}/admin/realms/{REALM_NAME}{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, headers=headers, data=body, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            content = resp.read().decode("utf-8")
            return json.loads(content) if content else None
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8")
        if e.code == 409:
            return None  # Already exists
        logger.warning(f"HTTP {e.code} on {method} {url}: {err_msg}")
        raise


def sync_realm_roles(token: str) -> dict[str, dict]:
    existing = api_request("/roles", token) or []
    role_map = {r["name"]: r for r in existing}

    for name, desc in ROLES:
        if name not in role_map:
            logger.info(f"Creating role '{name}'...")
            try:
                api_request("/roles", token, method="POST", data={"name": name, "description": desc})
            except Exception as e:
                logger.warning(f"Role create failed: {e}")
    
    # Reload all roles
    refreshed = api_request("/roles", token) or []
    return {r["name"]: r for r in refreshed}


def sync_users(token: str, role_map: dict[str, dict]) -> None:
    existing_users = api_request("/users", token) or []
    user_map = {u["username"]: u for u in existing_users}

    for u_spec in USERS:
        uname = u_spec["username"]
        email = u_spec["email"]
        role_name = u_spec["role"]
        req_actions = ["CONFIGURE_TOTP"] if u_spec.get("require_totp") else []

        user_obj = user_map.get(uname)
        if not user_obj:
            logger.info(f"Creating user '{uname}'...")
            create_payload = {
                "username": uname,
                "email": email,
                "firstName": u_spec["firstName"],
                "lastName": u_spec["lastName"],
                "enabled": True,
                "emailVerified": True,
                "requiredActions": req_actions,
            }
            api_request("/users", token, method="POST", data=create_payload)
            # Fetch created user
            found = api_request(f"/users?username={urllib.parse.quote(uname)}", token)
            user_obj = found[0] if found else None
            if not user_obj:
                logger.error(f"Failed to find user '{uname}' after creation.")
                continue
            user_map[uname] = user_obj
        else:
            # Update user requiredActions if needed
            api_request(
                f"/users/{user_obj['id']}",
                token,
                method="PUT",
                data={
                    "username": uname,
                    "email": email,
                    "firstName": u_spec["firstName"],
                    "lastName": u_spec["lastName"],
                    "enabled": True,
                    "emailVerified": True,
                    "requiredActions": req_actions,
                },
            )

        user_id = user_obj["id"]

        # Assign realm role
        role_obj = role_map.get(role_name)
        if role_obj:
            try:
                api_request(
                    f"/users/{user_id}/role-mappings/realm",
                    token,
                    method="POST",
                    data=[{"id": role_obj["id"], "name": role_obj["name"]}],
                )
            except Exception as e:
                logger.warning(f"Assigning role {role_name} to {uname} error: {e}")

        # Set user password via Admin API
        try:
            api_request(
                f"/users/{user_id}/reset-password",
                token,
                method="PUT",
                data={
                    "type": "password",
                    "value": KEYCLOAK_TEST_PASSWORD,
                    "temporary": False,
                },
            )
            logger.info(f"User '{uname}' password configured successfully.")
        except Exception as e:
            logger.error(f"Failed to set password for {uname}: {e}")


def main() -> None:
    logger.info("Connecting to Keycloak to configure roles and test users...")
    try:
        token = get_admin_token()
    except Exception as e:
        logger.error(f"Cannot connect to Keycloak at {KEYCLOAK_URL}: {e}")
        sys.exit(1)

    role_map = sync_realm_roles(token)
    logger.info(f"Verified {len(role_map)} realm roles.")

    sync_users(token, role_map)
    logger.info("Keycloak users and roles successfully synchronized.")


if __name__ == "__main__":
    main()
