"""CloudLens Credential Lifecycle and Secret Management Domain Package (Prompt 12)."""

from domain.credentials.models import (
    CredentialCreateRequest,
    CredentialProfile,
    CredentialProfileResponse,
    CredentialRotateRequest,
    ExpiryAlert,
)
from domain.credentials.permissions import (
    AWS_PERMISSIONS,
    AZURE_PERMISSIONS,
    GCP_PERMISSIONS,
    OCI_PERMISSIONS,
    LeastPrivilegeRequirement,
    PermissionReferenceService,
    ProviderPermissionReference,
)
from domain.credentials.service import (
    CredentialService,
    get_credential_service,
    reset_credential_service,
)
from domain.credentials.store import (
    InMemorySecretStore,
    SecretStore,
    VaultSecretStore,
    get_secret_store,
    reset_secret_store,
)
from domain.credentials.validation import (
    CredentialValidator,
    compute_fingerprint,
)

__all__ = [
    # Models & DTOs
    "CredentialProfile",
    "CredentialProfileResponse",
    "CredentialCreateRequest",
    "CredentialRotateRequest",
    "ExpiryAlert",
    # Secret Store
    "SecretStore",
    "InMemorySecretStore",
    "VaultSecretStore",
    "get_secret_store",
    "reset_secret_store",
    # Validation & Fingerprint
    "CredentialValidator",
    "compute_fingerprint",
    # Service
    "CredentialService",
    "get_credential_service",
    "reset_credential_service",
    # Permissions Reference (Item 81)
    "LeastPrivilegeRequirement",
    "ProviderPermissionReference",
    "PermissionReferenceService",
    "AWS_PERMISSIONS",
    "AZURE_PERMISSIONS",
    "GCP_PERMISSIONS",
    "OCI_PERMISSIONS",
]
