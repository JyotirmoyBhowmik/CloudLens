"""Dataset Schema Version Guard (Prompt 22 Item 7 & Acceptance).

Enforces:
- Schema validation before ingestion begins.
- Halts the job and raises UnknownSchemaVersionException on unrecognized schemas.
- STRICT PROHIBITION: Never guess a mapping for an unrecognised schema.
"""

from __future__ import annotations

import logging
from typing import Final

from domain.models.exceptions import UnknownSchemaVersionException

logger = logging.getLogger(__name__)

# Canonical dictionary of supported billing dataset schema versions per cloud provider
SUPPORTED_PROVIDER_SCHEMAS: Final[dict[str, set[str]]] = {
    "aws": {
        "aws_cur_2_0",  # BCM Data Exports CUR 2.0 (Parquet / Gzip)
        "aws_focus_1_0",  # AWS native FOCUS 1.0 export
        "aws_cost_explorer_v1",  # Interactive fallback validation schema
    },
    "azure": {
        "azure_cost_details_focus_1_0",  # Azure Cost Management FOCUS 1.0 dataset
        "azure_cost_details_v2",  # Azure EA / MCA Cost Details API v2 (Amortized / Actual)
    },
    "gcp": {
        "gcp_billing_export_resource_v1",  # BigQuery detailed usage with resources
        "gcp_billing_focus_1_0",  # BigQuery FOCUS 1.0 export
        "gcp_billing_export_v1",  # BigQuery standard usage export
    },
    "oci": {
        "oci_cost_report_v1",  # OCI Cost and Usage Reports (v1 CSV/Gzip)
        "oci_focus_1_0",  # OCI native FOCUS 1.0 dataset
    },
}


class SchemaVersionGuard:
    """Validates incoming billing dataset schema version against authoritative provider registers."""

    @classmethod
    def validate_schema(cls, provider: str, schema_version: str) -> None:
        """Validates that schema_version is formally supported for provider.

        STRICT PROHIBITION: If unknown, halts immediately. Never guesses a mapping.
        """
        p = provider.strip().lower()
        s = schema_version.strip().lower()

        if p not in SUPPORTED_PROVIDER_SCHEMAS:
            logger.error(
                "Ingestion halted: Unknown provider '%s' with schema '%s'. Guessing forbidden.",
                provider,
                schema_version,
            )
            raise UnknownSchemaVersionException(provider=provider, schema_version=schema_version)

        allowed_schemas = SUPPORTED_PROVIDER_SCHEMAS[p]
        if s not in allowed_schemas:
            logger.critical(
                "SECURITY/INTEGRITY ALERT: Encountered unrecognised schema version '%s' for provider '%s'. "
                "Supported versions: %s. Pipeline halted to prevent corrupted cost records.",
                schema_version,
                provider,
                sorted(allowed_schemas),
            )
            raise UnknownSchemaVersionException(provider=provider, schema_version=schema_version)

        logger.info("Schema validation passed: provider='%s', schema='%s'", p, s)

    @classmethod
    def is_supported(cls, provider: str, schema_version: str) -> bool:
        """Returns True if the provider and schema version pair is formally supported."""
        p = provider.strip().lower()
        s = schema_version.strip().lower()
        return p in SUPPORTED_PROVIDER_SCHEMAS and s in SUPPORTED_PROVIDER_SCHEMAS[p]

    @classmethod
    def is_focus_native(cls, schema_version: str) -> bool:
        """Returns True if the dataset schema is already in native FOCUS 1.0 format."""
        s = schema_version.strip().lower()
        return "focus_1_0" in s
