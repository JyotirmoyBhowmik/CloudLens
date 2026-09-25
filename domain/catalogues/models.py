"""Domain Models and DTOs for Enterprise Master Catalogues.

Enforces Prompt 07:
- Five versioned catalogues: Service & ServiceCategory, ResourceType, Unit, Metric, PricingDimension.
- Dimensionality, aggregation methods, default monitoring types.
- Effective-dating and catalogue versioning.
- Unknown-entry gap models and reporting.
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Dimensionality(str, Enum):
    """Physical and structural dimensions for canonical units."""

    DIGITAL_STORAGE = "DIGITAL_STORAGE"
    DATA_RATE = "DATA_RATE"
    TIME = "TIME"
    TIME_STORAGE = "TIME_STORAGE"
    COMPUTE_CAPACITY = "COMPUTE_CAPACITY"
    COUNT = "COUNT"
    PERCENTAGE = "PERCENTAGE"
    CURRENCY = "CURRENCY"


class AggregationMethod(str, Enum):
    """Mathematical aggregation methods for metrics and pricing dimensions."""

    SUM = "sum"
    AVERAGE = "average"
    MAX = "max"
    LAST = "last"


class CatalogueType(str, Enum):
    """Class of master catalogue."""

    SERVICE = "SERVICE"
    RESOURCE_TYPE = "RESOURCE_TYPE"
    METRIC = "METRIC"
    UNIT = "UNIT"
    PRICING_DIMENSION = "PRICING_DIMENSION"


class GapStatus(str, Enum):
    """Lifecycle state of an unmapped catalogue entry."""

    OPEN = "OPEN"
    RESOLVED = "RESOLVED"
    IGNORED = "IGNORED"


DEFAULT_CATALOGUE_EPOCH = datetime(2000, 1, 1, 0, 0, 0)


# ==============================================================================
# 1. Service Category & Service DTOs
# ==============================================================================


class ServiceCategoryDTO(BaseModel):
    code: str
    name: str
    description: str | None = None
    is_focus_standard: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ServiceDTO(BaseModel):
    id: str
    provider: str
    service_code: str
    name: str
    category: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ServiceMappingDTO(BaseModel):
    id: str
    service_id: str
    provider: str
    native_service_name: str
    version: int = 1
    effective_from: datetime = Field(default=DEFAULT_CATALOGUE_EPOCH)
    effective_to: datetime | None = None
    is_active: bool = True


class ServiceResolutionResult(BaseModel):
    service_code: str
    service_name: str
    category: str
    provider: str
    is_unclassified: bool = False
    native_service_name: str


# ==============================================================================
# 2. Resource Type DTOs
# ==============================================================================


class ResourceTypeDTO(BaseModel):
    id: str
    provider: str
    service_id: str
    native_type_name: str
    canonical_type: str
    service_category: str = "OTHER"
    default_monitoring_type: str = "UNKNOWN"
    version: int = 1
    effective_from: datetime = Field(default=DEFAULT_CATALOGUE_EPOCH)
    effective_to: datetime | None = None
    is_active: bool = True


class ResourceTypeResolutionResult(BaseModel):
    provider: str
    native_type_name: str
    canonical_type: str
    default_monitoring_type: str
    service_category: str
    is_unclassified: bool = False


# ==============================================================================
# 3. Unit Catalogue DTOs
# ==============================================================================


class UnitDTO(BaseModel):
    symbol: str
    name: str
    dimensionality: str
    base_unit: str
    scale_factor_to_base: Decimal
    offset_to_base: Decimal = Decimal("0")
    version: int = 1
    effective_from: datetime = Field(default=DEFAULT_CATALOGUE_EPOCH)
    effective_to: datetime | None = None
    is_active: bool = True


# ==============================================================================
# 4. Metric Catalogue DTOs
# ==============================================================================


class MetricDTO(BaseModel):
    code: str
    display_name: str
    unit_symbol: str
    aggregation_method: str
    applicable_monitoring_types: list[str] = Field(default_factory=list)
    description: str | None = None
    version: int = 1
    effective_from: datetime = Field(default=DEFAULT_CATALOGUE_EPOCH)
    effective_to: datetime | None = None
    is_active: bool = True


# ==============================================================================
# 5. Pricing Dimension Catalogue DTOs
# ==============================================================================


class PricingDimensionDTO(BaseModel):
    code: str
    name: str
    category: str
    unit_symbol: str
    aggregation_method: str
    default_threshold_basis: str
    applicability_rules: dict[str, Any] = Field(default_factory=dict)
    is_custom_escape_hatch: bool = False
    provider_code: str | None = None
    example_services: str | None = None
    notes: str | None = None
    version: int = 1
    effective_from: datetime = Field(default=DEFAULT_CATALOGUE_EPOCH)
    effective_to: datetime | None = None
    is_active: bool = True


# ==============================================================================
# 6. Catalogue Gap & Unknown Entry DTOs
# ==============================================================================


class CatalogueGapDTO(BaseModel):
    id: str
    tenant_id: str | None = None
    catalogue_type: str
    provider: str
    native_identifier: str
    status: str = "OPEN"
    occurrence_count: int = 1
    first_seen_at: datetime = Field(default_factory=datetime.utcnow)
    last_seen_at: datetime = Field(default_factory=datetime.utcnow)
    context_payload: dict[str, Any] = Field(default_factory=dict)
    resolution_notes: str | None = None
    resolved_by: str | None = None
    resolved_at: datetime | None = None


class CatalogueGapReport(BaseModel):
    total_gaps: int
    open_gaps: int
    gaps_by_type: dict[str, int]
    gaps_by_provider: dict[str, int]
    items: list[CatalogueGapDTO]
