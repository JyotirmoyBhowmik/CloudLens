"""Tag Normalisation Domain Models and Policy Enums.

Enforces Prompt 08 Item 54:
"Implement tag normalisation: configurable key convention (case and separator policy),
original key retained, OCI defined-tag namespace retained separately, and the
source level recorded (resource, resource group, subscription, compartment, project)."
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from domain.models.enums import ScopeRole


class TagSourceLevel(StrEnum):
    """Hierarchy level where a tag originated or was inherited from."""

    RESOURCE = "RESOURCE"
    RESOURCE_GROUP = "RESOURCE_GROUP"
    SUBSCRIPTION = "SUBSCRIPTION"
    COMPARTMENT = "COMPARTMENT"
    PROJECT = "PROJECT"
    BILLING_ACCOUNT = ScopeRole.BILLING_ACCOUNT.value
    TENANT = ScopeRole.TENANT.value


class TagCasePolicy(StrEnum):
    """Configurable casing convention for normalized tag keys."""

    LOWER = "lower"
    UPPER = "upper"
    CAMEL = "camel"
    SNAKE = "snake"
    KEBAB = "kebab"
    PRESERVE = "preserve"


class TagSeparatorPolicy(StrEnum):
    """Configurable delimiter convention for multi-word tag keys."""

    HYPHEN = "hyphen"  # '-'
    UNDERSCORE = "underscore"  # '_'
    DOT = "dot"  # '.'
    PRESERVE = "preserve"


class TagKeyConvention(BaseModel):
    """Configurable key convention specifying case and separator policies."""

    model_config = ConfigDict(frozen=True)

    case_policy: TagCasePolicy = Field(
        default=TagCasePolicy.LOWER,
        description="Target case convention (e.g. lower, upper, camel, kebab, snake, preserve)",
    )
    separator_policy: TagSeparatorPolicy = Field(
        default=TagSeparatorPolicy.HYPHEN,
        description="Target separator convention (e.g. hyphen, underscore, dot, preserve)",
    )
    strip_whitespace: bool = Field(
        default=True,
        description="Whether to strip leading/trailing whitespace",
    )
    remove_special_characters: bool = Field(
        default=True,
        description="Whether to strip non-alphanumeric separator noise",
    )


class RawTagInput(BaseModel):
    """Ingested raw tag payload from cloud providers before normalization."""

    key: str = Field(..., min_length=1, description="Raw tag key string")
    value: str = Field(default="", description="Raw tag value string")
    source_level: TagSourceLevel = Field(
        default=TagSourceLevel.RESOURCE,
        description="Origin source level in hierarchy",
    )
    namespace: str | None = Field(
        default=None,
        description="Explicit OCI defined-tag namespace if provided separately",
    )
    inherited: bool = Field(
        default=False,
        description="Whether tag was inherited from parent scope",
    )


class NormalizedTag(BaseModel):
    """Normalized tag entity with original key and OCI namespace preserved."""

    original_key: str = Field(
        ...,
        description="Verbatim original key as supplied by provider",
    )
    normalized_key: str = Field(
        ...,
        description="Standardized key adhering to configured convention",
    )
    value: str = Field(
        default="",
        description="Tag value string",
    )
    source_level: TagSourceLevel = Field(
        ...,
        description="Origin source level (resource, resource group, subscription, compartment, project)",
    )
    namespace: str | None = Field(
        default=None,
        description="OCI defined-tag namespace retained separately",
    )
    inherited: bool = Field(
        default=False,
        description="Whether tag was inherited from parent scope hierarchy",
    )
