"""OCI Domain Models, Enums, and Invariants (Prompt 19 / BBP Section 14.5 & 15.4).

Enforces:
- Instance / Resource Principals and API Signing Key (RSA PEM + Key Fingerprint tracking) authentication.
- Strict prohibition of interactive user passwords.
- Strict compartment tree depth preservation (mapping to GROUP and SUB_GROUP) with compartmentDepth cost query support.
- Non-retroactive tag attribution disclosure and modeling.
- Distinct modeling of free-form, namespaced defined, and cost-tracking tags.
- Non-authoritative OCI Budgets with ACTUAL/FORECAST and ABSOLUTE/PERCENTAGE alert rules.
- Explicit disclosure of lack of dynamic public SKU API parity in OCI pricing.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator

from domain.models.exceptions import DomainModelException


class OCIAuthMethod(StrEnum):
    """Supported OCI authentication mechanisms per BBP Section 14.5."""

    INSTANCE_PRINCIPAL = "INSTANCE_PRINCIPAL"  # Recommended for OCI-hosted deployment
    RESOURCE_PRINCIPAL = "RESOURCE_PRINCIPAL"  # Functions, Container Instances
    API_KEY = "API_KEY"  # IAM User with 2048/4096-bit RSA PEM key & fingerprint
    API_SIGNING_KEY = "API_KEY"  # Alias for API_KEY
    FEDERATED = "FEDERATED"  # Identity Domains / SAML 2.0 / OIDC
    FEDERATED_IDENTITY = "FEDERATED"  # Alias for FEDERATED


class OCIAuthenticationException(DomainModelException):
    """Raised when OCI credential validation or security invariants fail."""

    def __init__(self, message: str, error_code: str = "OCI_AUTH_ERROR") -> None:
        super().__init__(message, error_code=error_code)


class OCICredentials(BaseModel):
    """OCI authentication credentials enforcing least-privilege invariants."""

    tenancy_id: str = Field(
        default="ocid1.tenancy.oc1..aaaaaaaademo123456789",
        description="Tenancy OCID (e.g. ocid1.tenancy.oc1..)",
    )
    user_id: str | None = Field(
        default="ocid1.user.oc1..aaaaaaaademo987654321",
        description="IAM User OCID for API signing key authentication",
    )
    fingerprint: str | None = Field(
        default="20:3b:97:13:55:1c:5b:0d:d3:37:d8:50:4e:c5:3a:26",
        description="Public API signing key MD5 fingerprint",
    )
    private_key_pem: str | None = Field(
        default="-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA0...[REDACTED]...==\n-----END RSA PRIVATE KEY-----",
        description="RSA private key in PEM format",
    )
    region: str = Field(default="us-ashburn-1", description="OCI home or target region")
    auth_method: OCIAuthMethod = Field(
        default=OCIAuthMethod.API_KEY,
        description="Authentication mechanism",
    )
    key_created_days_ago: int = Field(
        default=15,
        ge=0,
        description="Age of API signing key in days for rotation tracking",
    )
    identity_domain_id: str | None = Field(
        default=None,
        description="OCI Identity Domain ID for federated authentication",
    )
    federation_token: str | None = Field(
        default=None,
        description="JWT federation token for federated principal",
    )
    # Strictly prohibited credentials
    user_password: str | None = Field(
        default=None,
        description="Strictly forbidden interactive console password",
    )
    user_interactive_token: str | None = Field(
        default=None,
        description="Strictly forbidden interactive personal web token",
    )

    @model_validator(mode="before")
    @classmethod
    def _normalize_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "tenancy_ocid" in data and "tenancy_id" not in data:
                data["tenancy_id"] = data["tenancy_ocid"]
            if "user_ocid" in data and "user_id" not in data:
                data["user_id"] = data["user_ocid"]
        return data

    def validate_security_invariants(self) -> None:
        """Enforces enterprise security policies (SEC-012, SEC-016)."""
        if self.user_password is not None or self.user_interactive_token is not None:
            raise OCIAuthenticationException(
                "Interactive user console passwords and personal web tokens are strictly prohibited. "
                "Console passwords are never permitted. Use Instance Principals or an IAM User with an API Signing Key.",
                error_code="FORBIDDEN_USER_CREDENTIALS",
            )
        if self.auth_method in (OCIAuthMethod.API_KEY, OCIAuthMethod.API_SIGNING_KEY):
            if not self.user_id or not self.fingerprint or not self.private_key_pem:
                raise OCIAuthenticationException(
                    "API_KEY authentication requires user_id, fingerprint, and private_key_pem.",
                    error_code="MISSING_API_KEY_CREDENTIALS",
                )


class OCITagRecord(BaseModel):
    """Resource tag distinguishing free-form, defined namespaced, and cost-tracking tags."""

    resource_id: str = Field(..., description="Target OCI resource OCID")
    tag_type: str = Field(..., description="FREE_FORM, DEFINED, or COST_TRACKING")
    namespace: str | None = Field(default=None, description="Tag namespace (defined tags only)")
    key: str = Field(..., description="Tag key")
    value: str = Field(..., description="Tag value")
    canonical_key: str = Field(..., description="Normalized key format (e.g. Namespace.Key or Key)")
    is_cost_tracking: bool = Field(
        default=False,
        description="Whether this tag is designated as a cost-tracking tag in the tenancy (max 10)",
    )
    associated_at: str = Field(
        default="2026-09-01T00:00:00Z",
        description="Timestamp when tag was associated with resource",
    )
    is_retroactive_attribution: bool = Field(
        default=False,
        description="Always False: OCI tag-based cost attribution applies strictly from time of association",
    )


class OCICostRecord(BaseModel):
    """Normalized OCI cost record from Usage API or delivered usage report CSV."""

    tenant_id: str = Field(..., description="Tenancy OCID")
    compartment_id: str = Field(..., description="Compartment OCID")
    compartment_name: str = Field(..., description="Compartment display name")
    compartment_depth: int = Field(default=1, ge=1, description="Nesting depth in compartment tree")
    service: str = Field(..., description="OCI service name (e.g. compute, blockstorage)")
    resource_id: str = Field(..., description="Resource OCID")
    description: str = Field(..., description="Product SKU description")
    region: str = Field(default="us-ashburn-1", description="OCI region")
    availability_domain: str | None = Field(default=None, description="Availability Domain")
    start_time: str = Field(..., description="Usage start ISO timestamp")
    end_time: str = Field(..., description="Usage end ISO timestamp")
    billed_quantity: float = Field(..., ge=0.0, description="Usage volume")
    pricing_unit: str = Field(..., description="Unit of measure")
    cost: float = Field(..., description="Billed cost (supports negative adjustments/credits)")
    currency: str = Field(default="USD", description="Billing currency")
    defined_tags: dict[str, dict[str, str]] = Field(
        default_factory=dict, description="Namespaced defined tags"
    )
    freeform_tags: dict[str, str] = Field(
        default_factory=dict, description="Free-form unstructured tags"
    )
    normalized_tags: dict[str, str] = Field(
        default_factory=dict, description="Flattened canonical tags (Namespace.Key = Value)"
    )
    is_correction: bool = Field(
        default=False, description="Whether line item is an adjustment/correction"
    )
    tag_attribution_note: str | None = Field(
        default=None,
        description="Explicit note when cost precedes tag association timestamp",
    )


class OCIResourceRecord(BaseModel):
    """Resource discovered via OCI Search service and service-specific APIs."""

    resource_id: str = Field(..., description="Resource OCID")
    display_name: str = Field(..., description="User-friendly resource display name")
    resource_type: str = Field(..., description="OCI resource type (e.g. Instance, Volume)")
    compartment_id: str = Field(..., description="Owning compartment OCID")
    lifecycle_state: str = Field(default="AVAILABLE", description="Lifecycle state")
    region: str = Field(default="us-ashburn-1", description="OCI region")
    service_category: str = Field(..., description="Standardized FinOps service category")
    defined_tags: dict[str, dict[str, str]] = Field(
        default_factory=dict, description="Namespaced defined tags"
    )
    freeform_tags: dict[str, str] = Field(default_factory=dict, description="Free-form tags")
    properties: dict[str, Any] = Field(
        default_factory=dict, description="Shape, memory, OCPUs, attached volumes"
    )


class OCIBudgetRecord(BaseModel):
    """OCI native budget with alert rules."""

    budget_id: str = Field(..., description="Budget OCID")
    display_name: str = Field(..., description="Budget display name")
    target_type: str = Field(default="COMPARTMENT", description="COMPARTMENT or TAG")
    target_id: str = Field(..., description="Target compartment OCID or tag match")
    amount: float = Field(..., ge=0.0, description="Monthly budget limit amount")
    current_spend: float = Field(default=0.0, ge=0.0, description="Tracked spend")
    forecasted_spend: float = Field(default=0.0, ge=0.0, description="Forecasted spend")
    alert_rules: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Alert rules mapping type (ACTUAL/FORECAST) and threshold (ABSOLUTE/PERCENTAGE)",
    )
    is_authoritative: bool = Field(
        default=False,
        description="OCI budgets are read for comparison only; CloudLens master budgets remain authoritative.",
    )


class OCIPriceQuote(BaseModel):
    """Price quote for an OCI product SKU."""

    part_number: str = Field(..., description="OCI part number or SKU")
    service: str = Field(..., description="Service name")
    description: str = Field(..., description="Part description")
    metric_unit: str = Field(..., description="Unit of measure (e.g. OCPU-Hours, Gigabyte-Months)")
    list_price: float = Field(..., ge=0.0, description="Public list rate")
    contract_price: float | None = Field(
        default=None, description="Negotiated Universal Credits (UCC) rate"
    )
    effective_price: float = Field(..., description="Resolved price after contract precedence")
    currency: str = Field(default="USD", description="Currency code")
    is_contract_rate: bool = Field(
        default=False, description="Whether resolved rate is UCC contract"
    )
    pricing_source: str = Field(default="oci_static_rate_card", description="Pricing source")
    has_dynamic_api_parity: bool = Field(
        default=False,
        description="Explicitly discloses that OCI does not offer dynamic public SKU query API parity",
    )


class OCIRelationshipRecord(BaseModel):
    """Structural relationship between two OCI resources."""

    source_id: str = Field(..., description="Source resource OCID")
    target_id: str = Field(..., description="Target resource OCID")
    relationship_type: str = Field(..., description="Relationship type")
    is_structural_only: bool = Field(
        default=True,
        description="Declared as MINIMAL / PARTIAL: packet-level network flows are not evaluated",
    )
    is_partial: bool = Field(
        default=True,
        description="Declared capability status: PARTIAL",
    )


KNOWN_OCI_TYPE_MAPPINGS = {
    "Instance": "COMPUTE",
    "Volume": "STORAGE",
    "Bucket": "STORAGE",
    "AutonomousDatabase": "DATABASE",
    "Vcn": "NETWORKING",
    "Subnet": "NETWORKING",
    "User": "SECURITY_IDENTITY",
}

# Regex for OCI OCID validation: ocid1.<resource-type>.<realm>.<region>.<unique-id>
_RE_OCI_OCID = re.compile(r"^ocid1\.[a-z0-9_\-]+\.[a-z0-9_\-]*\.[a-z0-9_\-]*\.[a-z0-9_\-]+$")


def is_valid_ocid(ocid: str) -> bool:
    """Validates OCI OCID format."""
    return bool(_RE_OCI_OCID.match(ocid.strip()))
