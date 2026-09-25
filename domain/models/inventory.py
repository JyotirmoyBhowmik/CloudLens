"""Canonical Inventory Entities for Multi-Cloud Governance.

Enforces Prompt 05 Item 32:
"Implement Resource, ResourceType, Service, ServiceCategory, Region, AvailabilityZone,
Tag, Application, Environment, Owner, CostCenter, BusinessUnit, Project."
"""

from pydantic import BaseModel, Field

from domain.models.base import CanonicalEntity
from domain.models.enums import PricingStatus, ProviderType, ServiceCategory


class Tag(BaseModel):
    """Resource metadata tag with inheritance lineage."""

    key: str = Field(..., description="Tag key identifier")
    value: str = Field(..., description="Tag value string")
    inherited: bool = Field(
        default=False, description="Whether tag was inherited from parent scope hierarchy"
    )
    source: str = Field(default="native", description="Tag origin: native, policy, or curated")


class Service(CanonicalEntity):
    """Cloud provider service definition (e.g. EC2, Azure Blob Storage)."""

    provider: ProviderType = Field(..., description="Cloud provider")
    service_code: str = Field(
        ..., description="Provider service code (e.g. AmazonEC2, Microsoft.Storage)"
    )
    name: str = Field(..., description="Human-readable service title")
    category: ServiceCategory = Field(
        default=ServiceCategory.OTHER, description="Canonical service category"
    )


class ResourceType(CanonicalEntity):
    """Specific cloud resource type (e.g. virtual machine, SQL database)."""

    provider: ProviderType = Field(..., description="Cloud provider")
    service_id: str = Field(..., description="Foreign key to Service entity")
    native_type_name: str = Field(
        ..., description="Verbatim provider type string (e.g. AWS::EC2::Instance)"
    )
    canonical_type: str = Field(
        ..., description="Normalized canonical type identifier (e.g. compute/virtual-machine)"
    )
    service_category: ServiceCategory = Field(
        default=ServiceCategory.OTHER, description="Canonical category"
    )


class Region(CanonicalEntity):
    """Geographical cloud region."""

    provider: ProviderType = Field(..., description="Cloud provider")
    native_name: str = Field(
        ..., description="Native provider region name (e.g. us-east-1, eastus)"
    )
    display_name: str = Field(..., description="Human-readable region description")
    geography: str = Field(..., description="Continent or geographic boundary")
    is_multi_az: bool = Field(
        default=True, description="Whether region features multiple availability zones"
    )


class AvailabilityZone(CanonicalEntity):
    """Isolated fault domain within a geographical region."""

    region_id: str = Field(..., description="Foreign key to parent Region entity")
    provider: ProviderType = Field(..., description="Cloud provider")
    native_zone_id: str = Field(..., description="Native provider zone ID (e.g. us-east-1a)")


class Owner(CanonicalEntity):
    """Individual or team accountable for cloud workloads."""

    name: str = Field(..., description="Owner full name")
    email: str = Field(..., description="Contact email address")
    department: str = Field(default="Engineering", description="Organizational department")


class BusinessUnit(CanonicalEntity):
    """High-level enterprise division (e.g. Retail Banking, Infrastructure)."""

    code: str = Field(..., description="Business unit code identifier")
    name: str = Field(..., description="Business unit title")


class CostCenter(CanonicalEntity):
    """Financial accounting allocation cost center."""

    code: str = Field(..., description="Accounting general ledger code (e.g. CC-1042)")
    name: str = Field(..., description="Cost center name")
    business_unit_id: str | None = Field(default=None, description="Parent BusinessUnit ID")


class Project(CanonicalEntity):
    """Initiative or internal project code."""

    code: str = Field(..., description="Project code identifier")
    name: str = Field(..., description="Project name")
    cost_center_id: str | None = Field(default=None, description="Associated CostCenter ID")


class Application(CanonicalEntity):
    """Business software application or service estate."""

    code: str = Field(..., description="Application portfolio ID (APM/CMDB)")
    name: str = Field(..., description="Application name")
    criticality: str = Field(
        default="BUSINESS_CRITICAL", description="MISSION_CRITICAL, BUSINESS_CRITICAL, NON_CRITICAL"
    )
    owner_id: str | None = Field(default=None, description="Accountable Owner ID")


class Environment(CanonicalEntity):
    """Deployment lifecycle environment."""

    name: str = Field(..., description="Environment name (e.g. Production, Staging, QA)")
    category: str = Field(default="PRODUCTION", description="PRODUCTION, NON_PRODUCTION, SANDBOX")


class Resource(CanonicalEntity):
    """Canonical inventory representation of a provisioned multi-cloud resource."""

    tenant_id: str = Field(..., description="Organization tenant ID")
    scope_id: str = Field(
        ..., description="Immediate parent Scope ID (Subscription, Account, Project)"
    )
    native_id: str = Field(..., description="Verbatim provider identifier (ARN, Azure URI, OCID)")
    name: str = Field(..., description="Resource name")
    provider: ProviderType = Field(..., description="Cloud provider")
    service_id: str = Field(..., description="Associated Service ID")
    resource_type_id: str = Field(..., description="Associated ResourceType ID")
    region_id: str = Field(..., description="Associated Region ID")
    availability_zone: str | None = Field(default=None, description="Optional AZ ID")
    pricing_status: PricingStatus = Field(
        default=PricingStatus.PAID, description="Pricing classification"
    )
    tags: list[Tag] = Field(default_factory=list, description="Associated key-value tags")
    application_id: str | None = Field(default=None, description="Mapped Application ID")
    environment_id: str | None = Field(default=None, description="Mapped Environment ID")
    owner_id: str | None = Field(default=None, description="Mapped Owner ID")
    cost_center_id: str | None = Field(default=None, description="Mapped CostCenter ID")
    business_unit_id: str | None = Field(default=None, description="Mapped BusinessUnit ID")
    project_id: str | None = Field(default=None, description="Mapped Project ID")
