"""Pre-Flight Credential Validation & Fingerprint Engine (Prompt 12 Item 78).

Enforces:
- SEC-008 & SEC-011: Strict validation prior to persisting credential material anywhere.
- SEC-012: Strict read-only enforcement. Writing or mutating permissions are rejected.
- SEC-017: Error sanitization: validation failures never leak credential material.
"""

import hashlib
import re
import uuid
from datetime import UTC, datetime
from typing import Any

from domain.models.enums import CredentialType, ProviderType
from domain.models.exceptions import CredentialValidationException

# Regex patterns for validation
AWS_ROLE_ARN_REGEX = re.compile(r"^arn:aws:iam::\d{12}:role/[\w+=,.@-]+$")
AWS_ACCESS_KEY_REGEX = re.compile(
    r"^(?:A3T[A-Z0-9]|AKIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA|ASIA)[A-Z0-9]{16}$"
)
GCP_SA_EMAIL_REGEX = re.compile(r"^[\w\-]+@[\w\-]+\.iam\.gserviceaccount\.com$")
OCI_OCID_TENANCY_REGEX = re.compile(r"^ocid1\.tenancy\.oc1\..+$")
OCI_OCID_USER_REGEX = re.compile(r"^ocid1\.user\.oc1\..+$")
OCI_FINGERPRINT_REGEX = re.compile(r"^([0-9a-fA-F]{2}:){15}[0-9a-fA-F]{2}$")

# Disallowed write/mutation permission indicators across providers
FORBIDDEN_WRITE_KEYWORDS = {
    "write",
    "modify",
    "create",
    "delete",
    "update",
    "put",
    "admin",
    "contributor",
    "owner",
    "editor",
    "manage",
}


def compute_fingerprint(
    provider: ProviderType,
    credential_type: CredentialType,
    secret_payload: dict[str, Any],
    metadata: dict[str, Any] | None = None,
) -> str:
    """Computes a deterministic, non-reversible SHA-256 fingerprint for a credential profile."""
    meta = metadata or {}
    source_identifier: str = ""

    if provider == ProviderType.AWS:
        if credential_type == CredentialType.ROLE_ARN:
            role_arn = secret_payload.get("role_arn") or meta.get("role_arn", "")
            ext_id = secret_payload.get("external_id") or meta.get("external_id", "")
            source_identifier = f"aws-role:{role_arn}:{ext_id}"
        else:
            key_id = secret_payload.get("aws_access_key_id") or meta.get("aws_access_key_id", "")
            source_identifier = f"aws-key:{key_id}"

    elif provider == ProviderType.AZURE:
        tenant_id = secret_payload.get("azure_tenant_id") or meta.get("azure_tenant_id", "")
        client_id = secret_payload.get("azure_client_id") or meta.get("azure_client_id", "")
        source_identifier = f"azure-sp:{tenant_id}:{client_id}"

    elif provider == ProviderType.GCP:
        sa_email = secret_payload.get("client_email") or meta.get("client_email", "")
        key_id = secret_payload.get("private_key_id") or meta.get("private_key_id", "")
        source_identifier = f"gcp-sa:{sa_email}:{key_id}"

    elif provider == ProviderType.OCI:
        tenancy = secret_payload.get("tenancy_ocid") or meta.get("tenancy_ocid", "")
        user_ocid = secret_payload.get("user_ocid") or meta.get("user_ocid", "")
        fp = secret_payload.get("fingerprint") or meta.get("fingerprint", "")
        source_identifier = f"oci-key:{tenancy}:{user_ocid}:{fp}"

    else:
        # Canonical or Simulator
        raw_key = secret_payload.get("key_id", "") or str(meta)
        source_identifier = f"generic:{provider.value}:{raw_key}"

    digest = hashlib.sha256(source_identifier.encode("utf-8")).hexdigest()
    return f"SHA256:{digest[:32]}"


class CredentialValidator:
    """Validates provider credentials against structural standards and least-privilege baselines."""

    @classmethod
    def validate(
        cls,
        provider: ProviderType,
        credential_type: CredentialType,
        secret_payload: dict[str, Any],
        metadata: dict[str, Any] | None = None,
        expires_at: datetime | None = None,
    ) -> bool:
        """Executes full pre-flight validation.

        Raises CredentialValidationException on failure without leaking any credential material.
        """
        if not secret_payload:
            raise CredentialValidationException("Credential secret payload cannot be empty.")

        # Check explicit expiration timestamp if provided
        if expires_at and expires_at <= datetime.now(UTC):
            raise CredentialValidationException(
                f"Credential expiration date '{expires_at.isoformat()}' is in the past. "
                "Expired credentials cannot be registered or rotated."
            )

        meta = metadata or {}

        if provider == ProviderType.AWS:
            cls._validate_aws(credential_type, secret_payload, meta)
        elif provider == ProviderType.AZURE:
            cls._validate_azure(credential_type, secret_payload, meta)
        elif provider == ProviderType.GCP:
            cls._validate_gcp(credential_type, secret_payload, meta)
        elif provider == ProviderType.OCI:
            cls._validate_oci(credential_type, secret_payload, meta)
        elif provider == ProviderType.CANONICAL:
            cls._validate_canonical(secret_payload)
        else:
            raise CredentialValidationException(
                f"Unsupported provider for credential validation: '{provider.value}'."
            )

        return True

    @classmethod
    def _validate_aws(
        cls,
        credential_type: CredentialType,
        payload: dict[str, Any],
        meta: dict[str, Any],
    ) -> None:
        if credential_type == CredentialType.ROLE_ARN:
            role_arn = str(payload.get("role_arn") or meta.get("role_arn") or "").strip()
            if not role_arn:
                raise CredentialValidationException(
                    "AWS Role ARN is required for ROLE_ARN credential type."
                )
            if not AWS_ROLE_ARN_REGEX.match(role_arn):
                raise CredentialValidationException(
                    "AWS Role ARN format is invalid. Expected format: 'arn:aws:iam::<account_id>:role/<role_name>'."
                )

            external_id = str(payload.get("external_id") or meta.get("external_id") or "").strip()
            if not external_id or len(external_id) < 8:
                raise CredentialValidationException(
                    "AWS External ID is required and must be at least 8 characters (NIST SP 800-63B / SEC-012)."
                )

        elif credential_type == CredentialType.CLIENT_SECRET:
            access_key_id = str(payload.get("aws_access_key_id") or "").strip()
            secret_key = str(payload.get("aws_secret_access_key") or "").strip()
            if not access_key_id:
                raise CredentialValidationException(
                    "AWS Access Key ID ('aws_access_key_id') is required."
                )
            if not AWS_ACCESS_KEY_REGEX.match(access_key_id):
                raise CredentialValidationException(
                    "AWS Access Key ID format is invalid. Expected standard prefix (e.g. AKIA...) and 20 alphanumeric characters."
                )
            if not secret_key or len(secret_key) < 20:
                raise CredentialValidationException(
                    "AWS Secret Access Key must be at least 20 characters."
                )

        else:
            raise CredentialValidationException(
                f"Unsupported AWS credential type: '{credential_type.value}'. Expected ROLE_ARN or CLIENT_SECRET."
            )

        # Check permissions list if supplied
        requested_actions = payload.get("requested_actions") or meta.get("requested_actions") or []
        cls._assert_no_write_actions(requested_actions)

    @classmethod
    def _validate_azure(
        cls,
        credential_type: CredentialType,
        payload: dict[str, Any],
        meta: dict[str, Any],
    ) -> None:
        tenant_id = str(payload.get("azure_tenant_id") or meta.get("azure_tenant_id") or "").strip()
        client_id = str(payload.get("azure_client_id") or meta.get("azure_client_id") or "").strip()

        if not tenant_id:
            raise CredentialValidationException("Azure Tenant ID ('azure_tenant_id') is required.")
        try:
            uuid.UUID(tenant_id)
        except ValueError as err:
            raise CredentialValidationException(
                "Azure Tenant ID must be a valid UUID format."
            ) from err

        if not client_id:
            raise CredentialValidationException("Azure Client ID ('azure_client_id') is required.")
        try:
            uuid.UUID(client_id)
        except ValueError as err:
            raise CredentialValidationException(
                "Azure Client ID must be a valid UUID format."
            ) from err

        if credential_type == CredentialType.SERVICE_PRINCIPAL:
            client_secret = str(payload.get("client_secret") or "").strip()
            certificate = str(payload.get("certificate_pem") or "").strip()
            if not client_secret and not certificate:
                raise CredentialValidationException(
                    "Azure Service Principal requires either 'client_secret' or 'certificate_pem'."
                )
            if client_secret and len(client_secret) < 16:
                raise CredentialValidationException(
                    "Azure Service Principal client secret must be at least 16 characters."
                )
        else:
            raise CredentialValidationException(
                f"Unsupported Azure credential type: '{credential_type.value}'. Expected SERVICE_PRINCIPAL."
            )

        assigned_roles = payload.get("assigned_roles") or meta.get("assigned_roles") or []
        cls._assert_no_write_actions(assigned_roles)

    @classmethod
    def _validate_gcp(
        cls,
        credential_type: CredentialType,
        payload: dict[str, Any],
        meta: dict[str, Any],
    ) -> None:
        if credential_type != CredentialType.SERVICE_ACCOUNT_KEY:
            raise CredentialValidationException(
                f"Unsupported GCP credential type: '{credential_type.value}'. Expected SERVICE_ACCOUNT_KEY."
            )

        key_type = str(payload.get("type") or "").strip()
        if key_type != "service_account":
            raise CredentialValidationException(
                "GCP Service Account JSON must specify type='service_account'."
            )

        project_id = str(payload.get("project_id") or meta.get("project_id") or "").strip()
        if not project_id:
            raise CredentialValidationException("GCP 'project_id' is required.")

        client_email = str(payload.get("client_email") or meta.get("client_email") or "").strip()
        if not client_email:
            raise CredentialValidationException("GCP 'client_email' is required.")
        if not GCP_SA_EMAIL_REGEX.match(client_email):
            raise CredentialValidationException(
                "GCP 'client_email' format is invalid. Expected format: '<name>@<project>.iam.gserviceaccount.com'."
            )

        private_key = str(payload.get("private_key") or "").strip()
        if not private_key:
            raise CredentialValidationException("GCP 'private_key' is required.")
        if "BEGIN PRIVATE KEY" not in private_key and "BEGIN RSA PRIVATE KEY" not in private_key:
            raise CredentialValidationException(
                "GCP 'private_key' must be valid PEM formatted RSA key."
            )

        assigned_roles = payload.get("assigned_roles") or meta.get("assigned_roles") or []
        cls._assert_no_write_actions(assigned_roles)

    @classmethod
    def _validate_oci(
        cls,
        credential_type: CredentialType,
        payload: dict[str, Any],
        meta: dict[str, Any],
    ) -> None:
        if credential_type != CredentialType.API_SIGNING_KEY:
            raise CredentialValidationException(
                f"Unsupported OCI credential type: '{credential_type.value}'. Expected API_SIGNING_KEY."
            )

        tenancy_ocid = str(payload.get("tenancy_ocid") or meta.get("tenancy_ocid") or "").strip()
        user_ocid = str(payload.get("user_ocid") or meta.get("user_ocid") or "").strip()
        fingerprint = str(payload.get("fingerprint") or meta.get("fingerprint") or "").strip()
        private_key = str(payload.get("private_key") or "").strip()

        if not tenancy_ocid or not OCI_OCID_TENANCY_REGEX.match(tenancy_ocid):
            raise CredentialValidationException(
                "OCI 'tenancy_ocid' is invalid. Expected format starting with 'ocid1.tenancy.oc1..'."
            )
        if not user_ocid or not OCI_OCID_USER_REGEX.match(user_ocid):
            raise CredentialValidationException(
                "OCI 'user_ocid' is invalid. Expected format starting with 'ocid1.user.oc1..'."
            )
        if not fingerprint or not OCI_FINGERPRINT_REGEX.match(fingerprint):
            raise CredentialValidationException(
                "OCI 'fingerprint' format is invalid. Expected 16 colon-separated hex pairs (e.g. 'aa:bb:...')."
            )
        if not private_key or (
            "BEGIN RSA PRIVATE KEY" not in private_key and "BEGIN PRIVATE KEY" not in private_key
        ):
            raise CredentialValidationException(
                "OCI 'private_key' must be valid PEM format RSA key."
            )

        policy_statements = payload.get("policy_statements") or meta.get("policy_statements") or []
        cls._assert_no_write_actions(policy_statements)

    @classmethod
    def _validate_canonical(cls, payload: dict[str, Any]) -> None:
        api_key = str(payload.get("api_key") or payload.get("token") or "").strip()
        if not api_key or len(api_key) < 8:
            raise CredentialValidationException(
                "Canonical simulator credential requires an API key or token of at least 8 characters."
            )

    @classmethod
    def _assert_no_write_actions(cls, actions: list[str]) -> None:
        """Enforces SEC-012: Rejects credentials requesting write, modify, or administrative mutation permissions."""
        for action in actions:
            action_lower = str(action).lower()
            if any(forbidden in action_lower for forbidden in FORBIDDEN_WRITE_KEYWORDS):
                raise CredentialValidationException(
                    f"Security baseline violation: Action or role '{action}' requests write or mutation permissions. "
                    "CloudLens operates strictly on read-only least privilege (SEC-012). Write permissions are forbidden."
                )
