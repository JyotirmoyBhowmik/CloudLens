"""Catalogue Repository Interface & In-Memory / Database Implementation.

Enforces Prompt 07:
- Isolated repository layer for the five versioned master catalogues and gap items.
- Point-in-time effective date queries (`as_of`).
"""

import uuid
from datetime import datetime
from typing import Any

from domain.catalogues.models import (
    CatalogueGapDTO,
    GapStatus,
    MetricDTO,
    PricingDimensionDTO,
    ResourceTypeDTO,
    ServiceCategoryDTO,
    ServiceDTO,
    ServiceMappingDTO,
    UnitDTO,
)
from domain.catalogues.seeds import (
    SEED_METRICS,
    SEED_PRICING_DIMENSIONS,
    SEED_RESOURCE_TYPES,
    SEED_SERVICE_CATEGORIES,
    SEED_SERVICE_MAPPINGS,
    SEED_SERVICES,
    SEED_UNITS,
)


class CatalogueRepository:
    """In-memory catalogue repository initialized with canonical seed data."""

    def __init__(self, load_seeds: bool = True) -> None:
        self._categories: dict[str, ServiceCategoryDTO] = {}
        self._services: dict[str, ServiceDTO] = {}
        self._service_mappings: list[ServiceMappingDTO] = []
        self._resource_types: list[ResourceTypeDTO] = []
        self._units: dict[str, list[UnitDTO]] = {}  # symbol -> list of versioned entries
        self._metrics: dict[str, list[MetricDTO]] = {}  # code -> list of versioned entries
        self._pricing_dimensions: dict[
            str, list[PricingDimensionDTO]
        ] = {}  # code -> list of versioned entries
        self._gaps: dict[str, CatalogueGapDTO] = {}

        if load_seeds:
            self._load_seeds()

    def _load_seeds(self) -> None:
        for cat in SEED_SERVICE_CATEGORIES:
            self._categories[cat.code] = cat.model_copy()
        for svc in SEED_SERVICES:
            self._services[svc.id] = svc.model_copy()
        for smap in SEED_SERVICE_MAPPINGS:
            self._service_mappings.append(smap.model_copy())
        for rt in SEED_RESOURCE_TYPES:
            self._resource_types.append(rt.model_copy())
        for unit in SEED_UNITS:
            self._units.setdefault(unit.symbol.lower(), []).append(unit.model_copy())
        for metric in SEED_METRICS:
            self._metrics.setdefault(metric.code, []).append(metric.model_copy())
        for dim in SEED_PRICING_DIMENSIONS:
            self._pricing_dimensions.setdefault(dim.code, []).append(dim.model_copy())

    # --------------------------------------------------------------------------
    # Service Categories & Services
    # --------------------------------------------------------------------------

    def add_service_category(self, cat: ServiceCategoryDTO) -> ServiceCategoryDTO:
        self._categories[cat.code] = cat
        return cat

    def list_service_categories(self) -> list[ServiceCategoryDTO]:
        return list(self._categories.values())

    def add_service(self, svc: ServiceDTO) -> ServiceDTO:
        self._services[svc.id] = svc
        return svc

    def get_service(self, service_id: str) -> ServiceDTO | None:
        return self._services.get(service_id)

    def list_services(self) -> list[ServiceDTO]:
        return list(self._services.values())

    def add_service_mapping(self, mapping: ServiceMappingDTO) -> ServiceMappingDTO:
        self._service_mappings.append(mapping)
        return mapping

    def find_service_mapping(
        self, provider: str, native_service_name: str, as_of: datetime | None = None
    ) -> ServiceMappingDTO | None:
        p_norm = provider.strip().lower()
        n_norm = native_service_name.strip().lower()
        target_time = as_of or datetime.utcnow()

        for sm in self._service_mappings:
            if sm.provider.lower() == p_norm and sm.native_service_name.lower() == n_norm:
                if sm.effective_from <= target_time and (
                    sm.effective_to is None or sm.effective_to > target_time
                ):
                    return sm
        return None

    # --------------------------------------------------------------------------
    # Resource Types
    # --------------------------------------------------------------------------

    def add_resource_type(self, rt: ResourceTypeDTO) -> ResourceTypeDTO:
        self._resource_types.append(rt)
        return rt

    def list_resource_types(self, provider: str | None = None) -> list[ResourceTypeDTO]:
        if provider:
            p_norm = provider.strip().lower()
            return [rt for rt in self._resource_types if rt.provider.lower() == p_norm]
        return list(self._resource_types)

    def find_resource_type(
        self, provider: str, native_type_name: str, as_of: datetime | None = None
    ) -> ResourceTypeDTO | None:
        p_norm = provider.strip().lower()
        n_norm = native_type_name.strip().lower()
        target_time = as_of or datetime.utcnow()

        for rt in self._resource_types:
            if rt.provider.lower() == p_norm and rt.native_type_name.lower() == n_norm:
                if rt.effective_from <= target_time and (
                    rt.effective_to is None or rt.effective_to > target_time
                ):
                    return rt
        return None

    # --------------------------------------------------------------------------
    # Units
    # --------------------------------------------------------------------------

    def add_unit(self, unit: UnitDTO) -> UnitDTO:
        sym_key = unit.symbol.strip().lower()
        entries = self._units.setdefault(sym_key, [])
        entries.append(unit)
        return unit

    def get_unit(self, symbol: str, as_of: datetime | None = None) -> UnitDTO | None:
        sym_key = symbol.strip().lower()
        entries = self._units.get(sym_key, [])
        if not entries:
            return None
        target_time = as_of or datetime.utcnow()
        for u in entries:
            if u.effective_from <= target_time and (
                u.effective_to is None or u.effective_to > target_time
            ):
                return u
        # Fall back to latest if none effective
        return entries[-1]

    def list_units(self) -> list[UnitDTO]:
        result = []
        for entries in self._units.values():
            if entries:
                result.append(entries[-1])
        return result

    # --------------------------------------------------------------------------
    # Metrics
    # --------------------------------------------------------------------------

    def add_metric(self, metric: MetricDTO) -> MetricDTO:
        entries = self._metrics.setdefault(metric.code, [])
        entries.append(metric)
        return metric

    def get_metric(self, code: str, as_of: datetime | None = None) -> MetricDTO | None:
        entries = self._metrics.get(code, [])
        if not entries:
            return None
        target_time = as_of or datetime.utcnow()
        for m in entries:
            if m.effective_from <= target_time and (
                m.effective_to is None or m.effective_to > target_time
            ):
                return m
        return entries[-1]

    def list_metrics(self) -> list[MetricDTO]:
        return [entries[-1] for entries in self._metrics.values() if entries]

    # --------------------------------------------------------------------------
    # Pricing Dimensions
    # --------------------------------------------------------------------------

    def add_pricing_dimension(self, dim: PricingDimensionDTO) -> PricingDimensionDTO:
        entries = self._pricing_dimensions.setdefault(dim.code, [])
        entries.append(dim)
        return dim

    def get_pricing_dimension(
        self, code: str, as_of: datetime | None = None
    ) -> PricingDimensionDTO | None:
        entries = self._pricing_dimensions.get(code, [])
        if not entries:
            return None
        target_time = as_of or datetime.utcnow()
        for d in entries:
            if d.effective_from <= target_time and (
                d.effective_to is None or d.effective_to > target_time
            ):
                return d
        return entries[-1]

    def list_pricing_dimensions(self, provider: str | None = None) -> list[PricingDimensionDTO]:
        results = [entries[-1] for entries in self._pricing_dimensions.values() if entries]
        if provider:
            p_norm = provider.strip().lower()
            return [
                d
                for d in results
                if not d.is_custom_escape_hatch
                or (d.provider_code and d.provider_code.lower() == p_norm)
            ]
        return results

    # --------------------------------------------------------------------------
    # Catalogue Gaps
    # --------------------------------------------------------------------------

    def record_gap(
        self,
        catalogue_type: str,
        provider: str,
        native_identifier: str,
        context: dict[str, Any] | None = None,
        tenant_id: str | None = None,
    ) -> CatalogueGapDTO:
        # Check if an open gap already exists for this entity
        for existing in self._gaps.values():
            if (
                existing.status == GapStatus.OPEN
                and existing.catalogue_type == catalogue_type
                and existing.provider.lower() == provider.lower()
                and existing.native_identifier.lower() == native_identifier.lower()
            ):
                existing.occurrence_count += 1
                existing.last_seen_at = datetime.utcnow()
                if context:
                    existing.context_payload.update(context)
                return existing

        gap_id = f"gap-{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()
        new_gap = CatalogueGapDTO(
            id=gap_id,
            tenant_id=tenant_id,
            catalogue_type=catalogue_type,
            provider=provider,
            native_identifier=native_identifier,
            status=GapStatus.OPEN,
            occurrence_count=1,
            first_seen_at=now,
            last_seen_at=now,
            context_payload=context or {},
        )
        self._gaps[gap_id] = new_gap
        return new_gap

    def list_gaps(
        self,
        status: str | None = None,
        catalogue_type: str | None = None,
        provider: str | None = None,
    ) -> list[CatalogueGapDTO]:
        items = list(self._gaps.values())
        if status:
            items = [g for g in items if g.status.upper() == status.upper()]
        if catalogue_type:
            items = [g for g in items if g.catalogue_type.upper() == catalogue_type.upper()]
        if provider:
            items = [g for g in items if g.provider.lower() == provider.lower()]
        return sorted(items, key=lambda g: g.last_seen_at, reverse=True)

    def resolve_gap(self, gap_id: str, resolution_notes: str, resolved_by: str) -> CatalogueGapDTO:
        gap = self._gaps.get(gap_id)
        if not gap:
            raise KeyError(f"Catalogue gap '{gap_id}' not found.")
        gap.status = GapStatus.RESOLVED
        gap.resolution_notes = resolution_notes
        gap.resolved_by = resolved_by
        gap.resolved_at = datetime.utcnow()
        return gap
