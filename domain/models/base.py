"""Canonical Entity Base Models and Provenance Tracking.

Enforces Prompt 05 Item 35:
"Give every canonical entity a provider_native attribute holding the original payload fragment,
and a source/provenance attribute. Normalisation adds structure; it never removes information."
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from domain.models.enums import OriginType


class ProvenanceRecord(BaseModel):
    """Source and provenance metadata for canonical data records."""

    source_system: str = Field(
        ...,
        description="Source connector or system origin (e.g. 'aws-cur', 'azure-ea', 'gcp-billing', 'oci-usage', 'curated')",
    )
    discovered_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp when payload was originally observed from provider API",
    )
    ingested_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp when record was normalized into canonical store",
    )
    correlation_id: str = Field(
        default_factory=lambda: f"corr-{uuid.uuid4().hex[:12]}",
        description="Distributed correlation ID linking ingestion and transform trace spans",
    )
    origin_type: OriginType = Field(
        default=OriginType.DISCOVERED,
        description="Data origin categorization (DISCOVERED, DERIVED, CURATED)",
    )
    survives_rediscovery: bool = Field(
        default=False,
        description="Whether manual curation or enrichments survive subsequent connector syncs",
    )


class CanonicalEntity(BaseModel):
    """Base class for all CloudLens canonical entities.

    Guarantees every entity retains raw provider payloads and full provenance lineage.
    """

    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Canonical globally unique entity identifier",
    )
    provider_native: dict[str, Any] = Field(
        default_factory=dict,
        description="Raw provider payload fragment preserved verbatim without data loss",
    )
    source_provenance: ProvenanceRecord = Field(
        default_factory=lambda: ProvenanceRecord(source_system="canonical"),
        description="Lineage, ingestion correlation, and origin provenance",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Creation timestamp in UTC",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Last update timestamp in UTC",
    )

    model_config = ConfigDict(arbitrary_types_allowed=True)
