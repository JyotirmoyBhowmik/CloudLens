"""CloudLens Domain Master Catalogues Package.

Exposes versioned catalogues, unit conversion services, and gap reporting.
"""

from domain.catalogues.models import (
    AggregationMethod,
    CatalogueGapDTO,
    CatalogueGapReport,
    CatalogueType,
    Dimensionality,
    GapStatus,
    MetricDTO,
    PricingDimensionDTO,
    ResourceTypeDTO,
    ResourceTypeResolutionResult,
    ServiceCategoryDTO,
    ServiceDTO,
    ServiceMappingDTO,
    ServiceResolutionResult,
    UnitDTO,
)
from domain.catalogues.repository import CatalogueRepository
from domain.catalogues.service import CatalogueService
from domain.catalogues.unit_service import UnitConversionService

__all__ = [
    "AggregationMethod",
    "CatalogueGapDTO",
    "CatalogueGapReport",
    "CatalogueRepository",
    "CatalogueService",
    "CatalogueType",
    "Dimensionality",
    "GapStatus",
    "MetricDTO",
    "PricingDimensionDTO",
    "ResourceTypeDTO",
    "ResourceTypeResolutionResult",
    "ServiceCategoryDTO",
    "ServiceDTO",
    "ServiceMappingDTO",
    "ServiceResolutionResult",
    "UnitConversionService",
    "UnitDTO",
]
