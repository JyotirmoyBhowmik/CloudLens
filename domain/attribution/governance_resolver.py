"""Governance Resolver for Ownership and Approval Authority (Prompt R-DATA).

Resolves statements recipient, dispute owner, investigator, and analytics OwnerKey
from ownership master data (OWNER_TEAM) and the approval-authority master.
If unresolved, raises GovernanceException. Never silently falls back to hardcoded strings.
"""

from __future__ import annotations

from typing import Any

from domain.models.exceptions import GovernanceException
from masterdata.service import get_master_data_service


def resolve_statements_recipient(tenant_id: str | None = None) -> tuple[str, str]:
    """Resolves accountable statements recipient (owner_id, owner_email) from ownership master data.

    Raises GovernanceException if unresolvable.
    """
    md = get_master_data_service()
    records = md.list_records("OWNER_TEAM", tenant_id=tenant_id)
    # 1. Prefer BUSINESS_OWNER role or OWNER_RETAIL_LEAD
    for r in records:
        role = r.attributes.get("role", "")
        if role == "BUSINESS_OWNER" or r.code == "OWNER_RETAIL_LEAD":  # no-hardcode-allow: reason="Master data OWNER_TEAM role attribute matching", reviewer="Prompt-48-Audit"
            email = r.attributes.get("contact_channels", {}).get("email")
            if email:
                return r.code, email
    # 2. Any active owner with a valid email channel
    for r in records:
        email = r.attributes.get("contact_channels", {}).get("email")
        if email:
            return r.code, email

    raise GovernanceException(
        "Governance Resolution Failure: Unable to resolve statements recipient from ownership master data (OWNER_TEAM). "
        "A valid recipient must be configured in master data or explicitly provided."
    )


def resolve_dispute_investigator(tenant_id: str | None = None) -> str:
    """Resolves dispute investigator email from ownership master data (OWNER_TEAM).

    Raises GovernanceException if unresolvable.
    """
    md = get_master_data_service()
    records = md.list_records("OWNER_TEAM", tenant_id=tenant_id)
    # 1. Prefer APPROVER or TECHNICAL_OWNER / TEAM_FINOPS_ENG / OWNER_FINOPS_ARCH
    for r in records:
        role = r.attributes.get("role", "")
        if role in ("APPROVER", "TECHNICAL_OWNER") or r.code in ("TEAM_FINOPS_ENG", "OWNER_FINOPS_ARCH"):
            email = r.attributes.get("contact_channels", {}).get("email")
            if email:
                return email
    # 2. Fallback to any valid contact channel email in OWNER_TEAM
    for r in records:
        email = r.attributes.get("contact_channels", {}).get("email")
        if email:
            return email

    raise GovernanceException(
        "Governance Resolution Failure: Unable to resolve dispute investigator from ownership master data (OWNER_TEAM). "
        "An investigator must be configured in master data or explicitly assigned."
    )


def resolve_analytics_owner_key(tenant_id: str | None = None) -> str:
    """Resolves fallback OwnerKey/OwnerEmail from ownership master data (OWNER_TEAM).

    Raises GovernanceException if unresolvable.
    """
    md = get_master_data_service()
    records = md.list_records("OWNER_TEAM", tenant_id=tenant_id)
    # 1. Look for TECHNICAL_OWNER, APPROVER, or BUDGET_OWNER
    for r in records:
        role = r.attributes.get("role", "")
        if role in ("TECHNICAL_OWNER", "APPROVER", "BUDGET_OWNER") or r.code in (
            "OWNER_FINOPS_ARCH",
            "TEAM_FINOPS_ENG",
            "OWNER_CLOUD_INFRA",
        ):
            email = r.attributes.get("contact_channels", {}).get("email")
            if email:
                return email
    # 2. Any contact channel email
    for r in records:
        email = r.attributes.get("contact_channels", {}).get("email")
        if email:
            return email

    raise GovernanceException(
        "Governance Resolution Failure: Unable to resolve analytics OwnerKey from ownership master data (OWNER_TEAM). "
        "Resource ownership must be resolved dynamically or configured in master data."
    )
