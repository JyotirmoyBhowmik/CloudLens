"""CloudLens Layered Configuration Model - Layers & Provenance Schema.

Implements the three-tier configuration hierarchy:
BUILTIN_DEFAULT -> ENVIRONMENT -> TENANT (Database)
with strict layer provenance tracking and secret masking.
"""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ConfigLayer(StrEnum):
    """Configuration layer hierarchy. Later layers override earlier layers."""

    BUILTIN_DEFAULT = "builtin_default"
    ENVIRONMENT = "environment"
    TENANT = "tenant"


class SettingMetadata(BaseModel):
    """Metadata describing a configuration setting."""

    key: str = Field(description="Dotted setting key, e.g. 'database.pool_size'")
    description: str = Field(description="Documentation of purpose and constraints")
    data_type: str = Field(description="Data type name, e.g. 'int', 'str', 'float', 'bool'")
    is_secret: bool = Field(
        default=False, description="Whether this setting contains sensitive credentials"
    )


class ConfigProvenance(BaseModel):
    """Full provenance record for an effective configuration value."""

    key: str = Field(description="Dotted configuration key")
    effective_value: Any = Field(description="Current effective value after layer overrides")
    layer: ConfigLayer = Field(description="Layer that supplied the effective value")
    description: str = Field(description="Setting documentation")
    is_secret: bool = Field(
        default=False, description="Whether this setting contains sensitive secrets"
    )
    data_type: str = Field(description="Python type name")
    tenant_id: str | None = Field(default=None, description="Tenant ID if resolved at tenant scope")
    raw_unmasked_value: Any = Field(
        default=None,
        exclude=True,
        description="Internal unmasked value for authorized execution only (never exposed)",
    )
