"""Provider Native Terminology and Vocabulary Registry (Prompt 37).

Enforces:
- Master Brief Section 28 & BBP Section 30: Provider Dashboards in Native Vocabulary.
- Azure: Management Groups, Subscriptions, Resource Groups.
- AWS: Organizations, Organizational Units (OUs), Member Accounts.
- GCP: Organizations, Folders, Projects.
- OCI: Tenancies, Compartments.
- Strict prohibition: Never use generic terms like 'group' or 'account' on a provider dashboard.
"""

from __future__ import annotations

from typing import Final

from pydantic import BaseModel, ConfigDict


class ProviderNativeVocabulary(BaseModel):
    """Authoritative native vocabulary terms for a cloud provider."""

    model_config = ConfigDict(frozen=True)

    provider_id: str
    provider_name: str
    root_entity_name: str
    group_term_singular: str
    group_term_plural: str
    account_term_singular: str
    account_term_plural: str
    resource_container_term: str
    identity_boundary_term: str


PROVIDER_VOCABULARIES: Final[dict[str, ProviderNativeVocabulary]] = {
    "azure": ProviderNativeVocabulary(
        provider_id="azure",
        provider_name="Microsoft Azure",
        root_entity_name="Tenant Root Group",
        group_term_singular="Management Group",
        group_term_plural="Management Groups",
        account_term_singular="Subscription",
        account_term_plural="Subscriptions",
        resource_container_term="Resource Group",
        identity_boundary_term="Microsoft Entra Tenant",
    ),
    "aws": ProviderNativeVocabulary(
        provider_id="aws",
        provider_name="Amazon Web Services",
        root_entity_name="AWS Organization Root",
        group_term_singular="Organizational Unit (OU)",
        group_term_plural="Organizational Units (OUs)",
        account_term_singular="Member Account",
        account_term_plural="Member Accounts",
        resource_container_term="Region / VPC",
        identity_boundary_term="AWS IAM Identity Center",
    ),
    "gcp": ProviderNativeVocabulary(
        provider_id="gcp",
        provider_name="Google Cloud Platform",
        root_entity_name="GCP Organization",
        group_term_singular="Folder",
        group_term_plural="Folders",
        account_term_singular="Project",
        account_term_plural="Projects",
        resource_container_term="Region / Zone",
        identity_boundary_term="Cloud Identity Domain",
    ),
    "oci": ProviderNativeVocabulary(
        provider_id="oci",
        provider_name="Oracle Cloud Infrastructure",
        root_entity_name="Root Compartment (Tenancy)",
        group_term_singular="Compartment",
        group_term_plural="Compartments",
        account_term_singular="Tenancy / Subcompartment",
        account_term_plural="Tenancies & Compartments",
        resource_container_term="Availability Domain",
        identity_boundary_term="OCI Identity & Access Domain",
    ),
}

GENERIC_FORBIDDEN_TERMS: Final[tuple[str, ...]] = (
    "generic group",
    "cloud group",
    "generic account",
    "cloud account",
)


def get_provider_vocabulary(provider: str) -> ProviderNativeVocabulary:
    """Retrieves native vocabulary for provider or raises ValueError."""
    key = provider.lower().strip()
    if key not in PROVIDER_VOCABULARIES:
        raise ValueError(
            f"Unknown provider '{provider}'. Must be one of: {list(PROVIDER_VOCABULARIES.keys())}"
        )
    return PROVIDER_VOCABULARIES[key]


def validate_native_vocabulary(provider: str, text: str) -> bool:
    """Verifies text does not contain forbidden generic terms."""
    _ = provider
    lower_text = text.lower()
    for forbidden in GENERIC_FORBIDDEN_TERMS:
        if forbidden in lower_text:
            return False
    return True
