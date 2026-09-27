"""Microsoft Azure Domain Models, Enums, and Scope-Form Matrix (Prompt 16 / BBP Section 14.2 & 15.4).

Enforces:
- Enterprise Agreement (EA), Microsoft Customer Agreement (MCA), Microsoft Partner Agreement (MPA), and Direct agreement types.
- Automatic agreement-type detection and scope-form validation with explicit mismatch diagnostics.
- Entra ID authentication credentials (certificate, workload identity, managed identity, client secret); user passwords strictly prohibited.
- Azure Resource Graph eventual consistency freshness indicator with documented latency caveat.
- Unsupported subscription offer category detection (capability gap handling).
- Multi-tier tag models recording native tier levels.
- Retail vs negotiated Price Sheet pricing precedence.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from domain.models.enums import ScopeRole
from domain.models.exceptions import DomainModelException


class AzureAgreementType(StrEnum):
    """Azure billing agreement types per BBP Section 14.2 & 15.4."""

    EA = "EA"  # Enterprise Agreement
    MCA = "MCA"  # Microsoft Customer Agreement
    MPA = "MPA"  # Microsoft Partner Agreement
    DIRECT = "DIRECT"  # Web Direct / Modern Direct Pay-As-You-Go


class AzureScopeType(StrEnum):
    """Azure Resource and Billing scope types."""

    BILLING_ACCOUNT = ScopeRole.BILLING_ACCOUNT.value
    BILLING_PROFILE = "BILLING_PROFILE"
    INVOICE_SECTION = "INVOICE_SECTION"
    DEPARTMENT = "DEPARTMENT"
    ENROLLMENT_ACCOUNT = "ENROLLMENT_ACCOUNT"
    CUSTOMER = "CUSTOMER"
    MANAGEMENT_GROUP = "MANAGEMENT_GROUP"
    SUBSCRIPTION = "SUBSCRIPTION"
    RESOURCE_GROUP = "RESOURCE_GROUP"


class AzureAuthMethod(StrEnum):
    """Allowed Azure authentication methods (ROPC/passwords strictly prohibited)."""

    CERTIFICATE = "CERTIFICATE"  # Entra ID App with Certificate (Recommended)
    WORKLOAD_IDENTITY = "WORKLOAD_IDENTITY"  # OIDC / Federated Token
    MANAGED_IDENTITY = "MANAGED_IDENTITY"  # Azure IMDS endpoint
    CLIENT_SECRET = "CLIENT_SECRET"  # Audited secret with rotation policy


class AzureTagLevel(StrEnum):
    """Native scope levels where tags are discovered in Azure."""

    RESOURCE = "resource"
    RESOURCE_GROUP = "resource_group"
    SUBSCRIPTION = "subscription"


class AzureSubscriptionOffer(StrEnum):
    """Recognized Azure subscription offer IDs for capability gap detection."""

    FREE_TRIAL = "MS-AZR-0044P"
    SPONSORED = "MS-AZR-0143P"
    MSDN_DEV_TEST = "MS-AZR-0029P"
    PAY_AS_YOU_GO = "MS-AZR-0003P"
    ENTERPRISE = "MS-AZR-0017P"
    MCA_MODERN = "MS-AZR-0017G"


# Offers that do not support Cost Management bulk exports or query APIs
UNSUPPORTED_OFFER_IDS = {
    AzureSubscriptionOffer.FREE_TRIAL.value,
    AzureSubscriptionOffer.SPONSORED.value,
    AzureSubscriptionOffer.MSDN_DEV_TEST.value,
}


def is_unsupported_cost_offer(offer_id: str | None) -> bool:
    """Returns True if the Azure subscription offer does not support Cost Management APIs."""
    if not offer_id:
        return False
    return offer_id.strip().upper() in {o.upper() for o in UNSUPPORTED_OFFER_IDS}


class AzureScopeMismatchException(DomainModelException):
    """Raised when an agreement type does not match the requested Cost Management scope form."""

    def __init__(
        self,
        agreement_type: AzureAgreementType | str,
        scope_uri: str,
        reason: str,
    ) -> None:
        super().__init__(
            f"Azure Cost Management scope mismatch: Agreement type '{agreement_type}' cannot be "
            f"used with scope form '{scope_uri}'. Reason: {reason}",
            error_code="AZURE_SCOPE_MISMATCH",
        )
        self.agreement_type = str(agreement_type)
        self.scope_uri = scope_uri
        self.reason = reason


class AzureAuthenticationException(DomainModelException):
    """Raised when Azure authentication handshake or credential validation fails."""

    def __init__(self, message: str, error_code: str = "AZURE_AUTH_ERROR") -> None:
        super().__init__(message, error_code=error_code)


class AzureCredentials(BaseModel):
    """Azure authentication credential payload enforcing least-privilege invariants."""

    tenant_id: str = Field(..., description="Entra ID Directory (tenant) ID GUID")
    client_id: str = Field(..., description="Application (client) ID GUID")
    auth_method: AzureAuthMethod = Field(
        default=AzureAuthMethod.CERTIFICATE,
        description="Authentication mechanism",
    )
    # Certificate configuration (Recommended)
    certificate_thumbprint: str | None = Field(
        default=None,
        description="X.509 Certificate thumbprint / SHA-1 hash",
    )
    certificate_pem: str | None = Field(
        default=None,
        description="PEM-encoded private key and certificate",
    )
    # Workload identity configuration (OIDC)
    federated_token_path: str | None = Field(
        default=None,
        description="File path or token string for workload identity assertion",
    )
    # Audited client secret (Restricted)
    client_secret: str | None = Field(
        default=None,
        description="Application client secret string",
    )
    # Target subscription / management group scope
    subscription_id: str | None = Field(
        default=None,
        description="Primary target Azure subscription GUID",
    )
    management_group_id: str | None = Field(
        default=None,
        description="Target root or intermediate management group ID",
    )
    # Explicit rejection of user passwords
    user_password: str | None = Field(
        default=None,
        description="Strictly forbidden interactive password (must remain null)",
    )

    def validate_security_invariants(self) -> None:
        """Enforces enterprise security baselines (SEC-012, SEC-016)."""
        if self.user_password is not None:
            raise AzureAuthenticationException(
                "Interactive user account passwords (ROPC) are strictly forbidden in CloudLens. "
                "Use Entra ID Service Principal with Certificate or Workload Identity Federation.",
                error_code="FORBIDDEN_USER_PASSWORD",
            )
        if self.auth_method == AzureAuthMethod.CERTIFICATE:
            if not self.certificate_pem and not self.certificate_thumbprint:
                raise AzureAuthenticationException(
                    "Certificate authentication requires certificate_pem or certificate_thumbprint.",
                    error_code="MISSING_CERTIFICATE_CONFIG",
                )
        elif self.auth_method == AzureAuthMethod.CLIENT_SECRET:
            if not self.client_secret:
                raise AzureAuthenticationException(
                    "Client secret authentication requires client_secret.",
                    error_code="MISSING_CLIENT_SECRET",
                )


class AzureFreshnessIndicator(BaseModel):
    """Resource Graph eventual consistency freshness indicator with documented latency caveat."""

    is_strongly_consistent: bool = Field(
        default=False,
        description="Azure Resource Graph is eventually consistent and cannot guarantee strong consistency.",
    )
    indexing_latency_caveat: bool = Field(
        default=True,
        description="Surfaces the official Azure documented caveat that Resource Graph has indexing latency.",
    )
    last_synced_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp when Resource Graph was last queried.",
    )
    caveat_message: str = Field(
        default=(
            "Azure Resource Graph data is indexed asynchronously via ARM events. "
            "Resource states and properties may lag portal actions by minutes to hours under platform backpressure. "
            "Inventory records are eventually consistent."
        ),
        description="Human-readable explanation of eventual consistency caveat.",
    )


class AzureTagRecord(BaseModel):
    """Multi-tier tag record preserving native scope tier without artificial inheritance."""

    resource_id: str = Field(
        ..., description="Full ARM resource, resource group, or subscription ID"
    )
    tag_level: AzureTagLevel = Field(..., description="Native tier where tag was defined")
    key: str = Field(..., description="Tag key")
    value: str = Field(default="", description="Tag value")


class AzurePriceQuote(BaseModel):
    """Unified pricing quote handling retail baseline and negotiated Price Sheet precedence."""

    meter_id: str = Field(..., description="Azure meter GUID")
    service_name: str = Field(..., description="Azure service family (e.g. Virtual Machines)")
    sku_name: str = Field(..., description="SKU designation (e.g. D4s v5)")
    retail_price: float = Field(
        ..., ge=0.0, description="Public retail rate in reference currency (USD)"
    )
    retail_currency: str = Field(default="USD", description="Retail currency (always USD)")
    negotiated_price: float | None = Field(
        default=None,
        ge=0.0,
        description="Enterprise negotiated Price Sheet rate when entitled",
    )
    negotiated_currency: str | None = Field(
        default=None,
        description="Billing currency for negotiated rate",
    )
    is_retail: bool = Field(
        default=True,
        description="Whether effective price reflects public retail rates",
    )
    is_negotiated: bool = Field(
        default=False,
        description="Whether effective price reflects enterprise negotiated Price Sheet",
    )
    effective_price: float = Field(
        ...,
        ge=0.0,
        description="Final applicable rate obeying Price Sheet precedence over retail",
    )
    effective_currency: str = Field(
        default="USD",
        description="Currency code for effective price",
    )
    pricing_source: str = Field(
        ...,
        description="Source of effective price: 'price_sheet' or 'retail_prices'",
    )


class AzureCostRecord(BaseModel):
    """Normalized intermediate cost record from Azure export or query."""

    scope_uri: str = Field(..., description="ARM scope of the cost record")
    subscription_id: str = Field(..., description="Azure subscription ID")
    resource_id: str = Field(default="", description="Target resource ID")
    resource_name: str = Field(default="", description="Resource display name")
    resource_group: str = Field(default="", description="Resource group name")
    meter_category: str = Field(..., description="Service category")
    meter_sub_category: str = Field(default="", description="Sub-category")
    meter_name: str = Field(..., description="Meter name")
    charge_type: str = Field(default="Usage", description="Charge type (Usage, Purchase, Credit)")
    pricing_model: str = Field(default="OnDemand", description="Pricing model")
    quantity: float = Field(default=0.0, ge=0.0, description="Consumed quantity")
    unit_of_measure: str = Field(default="1 Hour", description="Unit of measurement")
    effective_price: float = Field(default=0.0, ge=0.0, description="Unit rate")
    cost_in_billing_currency: float = Field(..., ge=0.0, description="Billed cost")
    billing_currency: str = Field(default="USD", description="Billing currency")
    usage_date: str = Field(..., description="Usage timestamp ISO string")
    tags: dict[str, str] = Field(default_factory=dict, description="Resource tags")
    is_estimated: bool = Field(default=False, description="Whether cost was query-estimated")


class AzureBudgetRecord(BaseModel):
    """Cost Management budget definition read for comparison only (never authoritative)."""

    budget_name: str = Field(..., description="Budget name in Azure")
    scope_uri: str = Field(..., description="ARM scope of the budget")
    amount: float = Field(..., ge=0.0, description="Budget amount limit")
    time_grain: str = Field(
        default="Monthly", description="Time window (Monthly, Quarterly, Annually)"
    )
    time_period_start: str = Field(..., description="Budget start date")
    time_period_end: str | None = Field(default=None, description="Budget end date")
    current_spend: float = Field(default=0.0, ge=0.0, description="Current spend tracked by Azure")
    is_authoritative: bool = Field(
        default=False,
        description="Azure native budgets are read for comparison only; CloudLens native budgets remain authoritative.",
    )


class AzureRelationshipRecord(BaseModel):
    """Structural resource relationship derived from Azure Resource Graph."""

    source_id: str = Field(..., description="Source resource ID (e.g. VM)")
    target_id: str = Field(..., description="Target resource ID (e.g. NIC or Disk)")
    relationship_type: str = Field(
        ...,
        description="Structural relation (NETWORK_INTERFACE, OS_DISK, DATA_DISK, MANAGED_BY, PARENT)",
    )
    is_structural_only: bool = Field(
        default=True,
        description="Structural relationships only; dynamic flow routing is not evaluated.",
    )


# ==============================================================================
# Agreement Detection & Scope-Form Matrix Logic
# ==============================================================================

# Regex patterns for Azure scope validation
_RE_SUBSCRIPTION = re.compile(r"^/subscriptions/[a-f0-9\-]+$", re.IGNORECASE)
_RE_MANAGEMENT_GROUP = re.compile(
    r"^/providers/Microsoft\.Management/managementGroups/[^/]+$", re.IGNORECASE
)
_RE_RESOURCE_GROUP = re.compile(r"^/subscriptions/[a-f0-9\-]+/resourceGroups/[^/]+$", re.IGNORECASE)

# EA Scope Patterns
_RE_EA_BILLING_ACCOUNT = re.compile(
    r"^/providers/Microsoft\.Billing/billingAccounts/\d+$", re.IGNORECASE
)
_RE_EA_DEPARTMENT = re.compile(
    r"^/providers/Microsoft\.Billing/billingAccounts/\d+/departments/\d+$", re.IGNORECASE
)
_RE_EA_ENROLLMENT_ACCOUNT = re.compile(
    r"^/providers/Microsoft\.Billing/billingAccounts/\d+/enrollmentAccounts/\d+$", re.IGNORECASE
)

# MCA Scope Patterns (Billing Account is GUID)
_RE_MCA_BILLING_ACCOUNT = re.compile(
    r"^/providers/Microsoft\.Billing/billingAccounts/[a-f0-9\-]+:[a-f0-9\-]+(_[a-f0-9\-]+)?$",
    re.IGNORECASE,
)
_RE_MCA_BILLING_PROFILE = re.compile(
    r"^/providers/Microsoft\.Billing/billingAccounts/[^/]+/billingProfiles/[^/]+$", re.IGNORECASE
)
_RE_MCA_INVOICE_SECTION = re.compile(
    r"^/providers/Microsoft\.Billing/billingAccounts/[^/]+/billingProfiles/[^/]+/invoiceSections/[^/]+$",
    re.IGNORECASE,
)

# MPA Scope Patterns
_RE_MPA_CUSTOMER = re.compile(
    r"^/providers/Microsoft\.Billing/billingAccounts/[^/]+/customers/[^/]+$", re.IGNORECASE
)


def detect_agreement_type(
    scope_uri: str,
    billing_account_id: str | None = None,
) -> AzureAgreementType:
    """Detects Azure billing agreement type (EA, MCA, MPA, DIRECT) from scope URI or billing account format."""
    normalized_scope = (scope_uri or "").strip()
    account_id = (billing_account_id or "").strip()

    # 1. Inspect explicit billing account identifier if supplied
    if account_id:
        if account_id.isdigit():
            return AzureAgreementType.EA
        if ":" in account_id or "-" in account_id:
            return AzureAgreementType.MCA

    # 2. Inspect Scope URI path elements
    scope_lower = normalized_scope.lower()
    if "/enrollmentaccounts/" in scope_lower or "/departments/" in scope_lower:
        return AzureAgreementType.EA
    if "/billingprofiles/" in scope_lower or "/invoicesections/" in scope_lower:
        return AzureAgreementType.MCA
    if "/customers/" in scope_lower:
        return AzureAgreementType.MPA

    # 3. Inspect billingAccounts segment in scope URI
    if "/providers/microsoft.billing/billingaccounts/" in scope_lower:
        parts = normalized_scope.split("/")
        for idx, part in enumerate(parts):
            if part.lower() == "billingaccounts" and idx + 1 < len(parts):
                account_val = parts[idx + 1]
                if account_val.isdigit():
                    return AzureAgreementType.EA
                return AzureAgreementType.MCA

    # 4. Standard subscription or resource group without billing account defaults to DIRECT
    if _RE_SUBSCRIPTION.match(normalized_scope) or _RE_RESOURCE_GROUP.match(normalized_scope):
        return AzureAgreementType.DIRECT

    # 5. Management Group default
    if _RE_MANAGEMENT_GROUP.match(normalized_scope):
        return AzureAgreementType.EA  # Common enterprise default

    return AzureAgreementType.DIRECT


def validate_scope_for_agreement(
    agreement_type: AzureAgreementType,
    scope_uri: str,
) -> None:
    """Validates that a scope URI matches the structural constraints of the agreement type.

    Throws explicit AzureScopeMismatchException when an invalid combination is detected.
    """
    normalized = (scope_uri or "").strip()
    lower = normalized.lower()

    # Universal scopes valid across agreements (except DIRECT which cannot use Management Groups for billing)
    if _RE_SUBSCRIPTION.match(normalized):
        return

    if _RE_RESOURCE_GROUP.match(normalized):
        if agreement_type in {
            AzureAgreementType.EA,
            AzureAgreementType.MCA,
            AzureAgreementType.MPA,
        }:
            # Resource groups are valid ARM scopes, but enterprise billing queries are preferred at subscription or billing account
            return
        if agreement_type == AzureAgreementType.DIRECT:
            return

    if _RE_MANAGEMENT_GROUP.match(normalized):
        if agreement_type == AzureAgreementType.DIRECT:
            raise AzureScopeMismatchException(
                agreement_type=agreement_type,
                scope_uri=normalized,
                reason="Direct Pay-As-You-Go agreements do not support Management Group billing scopes.",
            )
        return

    # EA-Specific Rules
    if agreement_type == AzureAgreementType.EA:
        if "/billingprofiles/" in lower:
            raise AzureScopeMismatchException(
                agreement_type=agreement_type,
                scope_uri=normalized,
                reason="Scope contains 'billingProfiles', which is valid only for Microsoft Customer Agreements (MCA), not Enterprise Agreements (EA).",
            )
        if "/invoicesections/" in lower:
            raise AzureScopeMismatchException(
                agreement_type=agreement_type,
                scope_uri=normalized,
                reason="Scope contains 'invoiceSections', which is valid only for Microsoft Customer Agreements (MCA), not Enterprise Agreements (EA).",
            )
        if "/customers/" in lower:
            raise AzureScopeMismatchException(
                agreement_type=agreement_type,
                scope_uri=normalized,
                reason="Scope contains 'customers', which is valid only for Microsoft Partner Agreements (MPA), not Enterprise Agreements (EA).",
            )
        if (
            _RE_EA_BILLING_ACCOUNT.match(normalized)
            or _RE_EA_DEPARTMENT.match(normalized)
            or _RE_EA_ENROLLMENT_ACCOUNT.match(normalized)
        ):
            return
        # If it's a generic billingAccounts with non-numeric ID
        if "/providers/microsoft.billing/billingaccounts/" in lower:
            raise AzureScopeMismatchException(
                agreement_type=agreement_type,
                scope_uri=normalized,
                reason="Enterprise Agreement (EA) requires a numeric enrollment number for billingAccounts, not a GUID or formatted string.",
            )

    # MCA-Specific Rules
    elif agreement_type == AzureAgreementType.MCA:
        if "/enrollmentaccounts/" in lower:
            raise AzureScopeMismatchException(
                agreement_type=agreement_type,
                scope_uri=normalized,
                reason="Scope contains 'enrollmentAccounts', which is valid only for Enterprise Agreements (EA), not Microsoft Customer Agreements (MCA).",
            )
        if "/departments/" in lower:
            raise AzureScopeMismatchException(
                agreement_type=agreement_type,
                scope_uri=normalized,
                reason="Scope contains 'departments', which is valid only for Enterprise Agreements (EA), not Microsoft Customer Agreements (MCA).",
            )
        if "/customers/" in lower:
            raise AzureScopeMismatchException(
                agreement_type=agreement_type,
                scope_uri=normalized,
                reason="Scope contains 'customers', which is valid only for Microsoft Partner Agreements (MPA), not Microsoft Customer Agreements (MCA).",
            )
        if (
            _RE_MCA_BILLING_ACCOUNT.match(normalized)
            or _RE_MCA_BILLING_PROFILE.match(normalized)
            or _RE_MCA_INVOICE_SECTION.match(normalized)
        ):
            return

    # MPA-Specific Rules
    elif agreement_type == AzureAgreementType.MPA:
        if "/departments/" in lower or "/enrollmentaccounts/" in lower:
            raise AzureScopeMismatchException(
                agreement_type=agreement_type,
                scope_uri=normalized,
                reason="Scope contains EA-specific departments or enrollmentAccounts, invalid for Microsoft Partner Agreements (MPA).",
            )
        if _RE_MPA_CUSTOMER.match(normalized):
            return

    # DIRECT-Specific Rules
    elif agreement_type == AzureAgreementType.DIRECT:
        if "/providers/microsoft.billing/billingaccounts" in lower:
            raise AzureScopeMismatchException(
                agreement_type=agreement_type,
                scope_uri=normalized,
                reason="Direct Pay-As-You-Go agreements do not expose enterprise billingAccount scopes. Use subscription or resourceGroup scope.",
            )

    # If nothing matched and didn't fail specifically
    return
