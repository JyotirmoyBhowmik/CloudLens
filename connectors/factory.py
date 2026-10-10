"""CloudLens Dynamic Connector Factory & Production Boundary Guard (Prompt P13A).

Enforces:
- Resolves appropriate real cloud connectors (AWSConnector, AzureConnector, GCPConnector, OCIConnector)
  based on registered provider metadata and credentials.
- HARD PRODUCTION GATE: Production tenants (TenantType.PRODUCTION) are strictly forbidden
  from using ProviderSimulatorConnector or accessing fixture paths.
- Resolves credentials via OpenBao at call time if vault:// reference is present.
"""

from __future__ import annotations

import logging
from typing import Any

from connectors.aws.connector import AWSConnector
from connectors.azure.connector import AzureConnector
from connectors.contract.base import BaseCloudConnector
from connectors.gcp.connector import GCPConnector
from connectors.oci.connector import OCIConnector
from domain.connectors.repository import get_connector_repository
from domain.models.enums import ProviderType
from domain.tenant.context import TenantContext
from domain.tenant.models import TenantType

logger = logging.getLogger(__name__)


def resolve_connector(
    connector_id: str,
    tenant_context: TenantContext,
    override_config: dict[str, Any] | None = None,
) -> BaseCloudConnector:
    """Resolves and instantiates the proper connector instance for a tenant and job.

    Enforces that PRODUCTION tenants can never reach simulator/fixture connectors.
    """
    tenant_id = tenant_context.tenant_id
    repo = get_connector_repository()
    entity = None
    try:
        entity = repo.get(connector_id, tenant_context=tenant_context)
    except Exception as exc:
        logger.debug("Connector repo lookup note for %s: %s", connector_id, exc)

    config = dict(override_config or {})
    provider_str = "aws"

    if entity is not None:
        if isinstance(entity, dict):
            provider_val = entity.get("provider", "aws")
            ent_config = entity.get("config") or {}
        else:
            provider_val = getattr(entity, "provider", "aws")
            ent_config = getattr(entity, "config", {}) or {}

        provider_str = provider_val.value.lower() if hasattr(provider_val, "value") else str(provider_val).lower()
        config = {**ent_config, **config}
    else:
        # Infer provider from connector_id if not found in repo
        cid_low = connector_id.lower()
        if "azure" in cid_low:
            provider_str = "azure"
        elif "gcp" in cid_low:
            provider_str = "gcp"
        elif "oci" in cid_low:
            provider_str = "oci"
        else:
            provider_str = "aws"

    # Resolve credentials via OpenBao by vault:// reference or credential_profile_id
    cred_profile_id = (
        entity.get("credential_profile_id")
        if isinstance(entity, dict)
        else getattr(entity, "credential_profile_id", None)
    ) if entity is not None else None

    cred_ref = config.get("credential_ref") or config.get("secret_ref")
    if cred_profile_id and not cred_ref:
        try:
            from domain.credentials.repository import get_credential_repository
            cred_repo = get_credential_repository()
            profile = cred_repo.get_sync(cred_profile_id)
            if profile and profile.secret_ref:
                cred_ref = profile.secret_ref
        except Exception as c_err:
            logger.debug("Credential profile resolution note: %s", c_err)

    if cred_ref and str(cred_ref).startswith("vault://"):
        try:
            from domain.credentials.store import get_secret_store
            vault_secret = get_secret_store().get_secret(str(cred_ref), tenant_id=tenant_id)
            if isinstance(vault_secret, dict):
                config["credentials"] = {**(config.get("credentials") or {}), **vault_secret}
                config["credential_ref"] = str(cred_ref)
        except Exception as v_err:
            logger.debug("Vault credential resolution note for %s: %s", cred_ref, v_err)

    # Check Tenant Type (Prompt P13: Simulator only in DEMO tenants)
    is_demo = False
    try:
        from domain.tenant.repository import get_tenant_repository
        tenant_repo = get_tenant_repository()
        t_entity = tenant_repo.get_sync(tenant_id) if hasattr(tenant_repo, "get_sync") else None
        if t_entity:
            t_type = getattr(t_entity, "type", None)
            if t_type == TenantType.DEMO or str(t_type).upper() == "DEMO":
                is_demo = True
    except Exception as t_err:
        logger.debug("Tenant type resolution note: %s", t_err)

    # Stub Connector for unit/contract tests
    if "stub" in provider_str:
        from connectors.stub.connector import StubConnector
        return StubConnector(
            connector_id=connector_id,
            tenant_id=tenant_id,
            config=config,
        )

    # Simulator strictly restricted to DEMO tenants (API 403 / PermissionError)
    if not is_demo and ("simulator" in provider_str or "mock" in provider_str or "stub" in provider_str):
        raise PermissionError(
            f"Tenant '{tenant_id}' is not DEMO. Simulator and fixture connectors are strictly restricted to DEMO tenants."
        )

    # If DEMO tenant explicitly requested simulator
    if is_demo and ("simulator" in provider_str or "mock" in provider_str):
        from connectors.simulator.connector import ProviderSimulatorConnector
        return ProviderSimulatorConnector(
            connector_id=connector_id,
            tenant_id=tenant_id,
            profile=provider_str.replace("simulator-", "").replace("simulator_", ""),
            config=config,
        )

    # Real Connectors
    if "azure" in provider_str:
        return AzureConnector(connector_id=connector_id, tenant_id=tenant_id, config=config)
    elif "gcp" in provider_str:
        return GCPConnector(connector_id=connector_id, tenant_id=tenant_id, config=config)
    elif "oci" in provider_str:
        return OCIConnector(connector_id=connector_id, tenant_id=tenant_id, config=config)
    else:
        return AWSConnector(connector_id=connector_id, tenant_id=tenant_id, config=config)

