"""Enterprise Master Catalogue Service.

Enforces Prompt 07:
- Five versioned catalogues: Service, ResourceType, Unit, Metric, PricingDimension.
- Administration interfaces at the service layer.
- Effective-dating and catalogue versioning.
- Unknown-entry workflow: an unmapped service, type, metric, unit or dimension raises
  a catalogue gap item for an administrator, and processing continues.
- Unmapped types are stored as Unclassified with the native type retained and surfaced in a report.
- Provider-specific dimension escape hatch.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from domain.catalogues.models import (
    CatalogueGapDTO,
    CatalogueGapReport,
    CatalogueType,
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
from domain.catalogues.unit_service import UnitConversionService
from domain.models.exceptions import CatalogueVersioningError


class CatalogueService:
    """Unified Service Layer managing Enterprise Master Catalogues, Versioning, and Gap Workflows."""

    def __init__(self, repository: CatalogueRepository | None = None) -> None:
        self._repo = repository or CatalogueRepository(load_seeds=True)
        self._unit_service = UnitConversionService(self._repo)

    @property
    def repository(self) -> CatalogueRepository:
        return self._repo

    @property
    def units(self) -> UnitConversionService:
        return self._unit_service

    # ==========================================================================
    # 1. Service Category & Service Administration
    # ==========================================================================

    def create_service_category(
        self,
        code: str,
        name: str,
        description: str | None = None,
        is_focus_standard: bool = True,
    ) -> ServiceCategoryDTO:
        cat = ServiceCategoryDTO(
            code=code.strip().upper(),
            name=name,
            description=description,
            is_focus_standard=is_focus_standard,
        )
        return self._repo.add_service_category(cat)

    def list_service_categories(self) -> list[ServiceCategoryDTO]:
        return self._repo.list_service_categories()

    def create_service(
        self,
        service_id: str,
        provider: str,
        service_code: str,
        name: str,
        category: str,
    ) -> ServiceDTO:
        svc = ServiceDTO(
            id=service_id,
            provider=provider.strip().lower(),
            service_code=service_code,
            name=name,
            category=category.strip().upper(),
        )
        return self._repo.add_service(svc)

    def add_service_mapping(
        self,
        service_id: str,
        provider: str,
        native_service_name: str,
        effective_from: datetime | None = None,
        effective_to: datetime | None = None,
    ) -> ServiceMappingDTO:
        mapping_id = f"smap-{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()
        smap = ServiceMappingDTO(
            id=mapping_id,
            service_id=service_id,
            provider=provider.strip().lower(),
            native_service_name=native_service_name,
            version=1,
            effective_from=effective_from or now,
            effective_to=effective_to,
            is_active=True,
        )
        return self._repo.add_service_mapping(smap)

    def resolve_service(
        self,
        provider: str,
        native_service_name: str,
        as_of: datetime | None = None,
        tenant_id: str | None = None,
    ) -> ServiceResolutionResult:
        """Resolves a provider-native service string to canonical service details.

        If unmapped, triggers unknown-entry workflow, registers an admin gap item,
        and returns an Unclassified result with native name retained.
        """
        mapping = self._repo.find_service_mapping(provider, native_service_name, as_of=as_of)
        if mapping:
            canonical_svc = self._repo.get_service(mapping.service_id)
            if canonical_svc:
                return ServiceResolutionResult(
                    service_code=canonical_svc.service_code,
                    service_name=canonical_svc.name,
                    category=canonical_svc.category,
                    provider=provider,
                    is_unclassified=False,
                    native_service_name=native_service_name,
                )

        # Unknown-entry workflow: record gap and continue with Unclassified
        self._repo.record_gap(
            catalogue_type=CatalogueType.SERVICE,
            provider=provider,
            native_identifier=native_service_name,
            context={"attempted_resolution_at": (as_of or datetime.utcnow()).isoformat()},
            tenant_id=tenant_id,
        )
        return ServiceResolutionResult(
            service_code="Unclassified",
            service_name="Unclassified Service",
            category="OTHER",
            provider=provider,
            is_unclassified=True,
            native_service_name=native_service_name,
        )

    # ==========================================================================
    # 2. ResourceType Administration & Unknown-Entry Resolution
    # ==========================================================================

    def add_resource_type(
        self,
        resource_type_id: str,
        provider: str,
        service_id: str,
        native_type_name: str,
        canonical_type: str,
        service_category: str = "OTHER",
        default_monitoring_type: str = "UNKNOWN",
        effective_from: datetime | None = None,
        effective_to: datetime | None = None,
    ) -> ResourceTypeDTO:
        now = datetime.utcnow()
        rt = ResourceTypeDTO(
            id=resource_type_id,
            provider=provider.strip().lower(),
            service_id=service_id,
            native_type_name=native_type_name,
            canonical_type=canonical_type,
            service_category=service_category,
            default_monitoring_type=default_monitoring_type,
            version=1,
            effective_from=effective_from or now,
            effective_to=effective_to,
            is_active=True,
        )
        return self._repo.add_resource_type(rt)

    def list_resource_types(self, provider: str | None = None) -> list[ResourceTypeDTO]:
        return self._repo.list_resource_types(provider=provider)

    def resolve_resource_type(
        self,
        provider: str,
        native_type_name: str,
        as_of: datetime | None = None,
        tenant_id: str | None = None,
    ) -> ResourceTypeResolutionResult:
        """Resolves a provider-native type string to canonical type and monitoring type.

        If unmapped:
        - Stored/returned as 'Unclassified'
        - Native type retained verbatim
        - Surfaced in Catalogue Gap report for administrators
        - Processing continues (never dropped)
        """
        rt = self._repo.find_resource_type(provider, native_type_name, as_of=as_of)
        if rt:
            return ResourceTypeResolutionResult(
                provider=provider,
                native_type_name=native_type_name,
                canonical_type=rt.canonical_type,
                default_monitoring_type=rt.default_monitoring_type,
                service_category=rt.service_category,
                is_unclassified=False,
            )

        # Unmapped: record gap item and return Unclassified
        self._repo.record_gap(
            catalogue_type=CatalogueType.RESOURCE_TYPE,
            provider=provider,
            native_identifier=native_type_name,
            context={"attempted_resolution_at": (as_of or datetime.utcnow()).isoformat()},
            tenant_id=tenant_id,
        )
        return ResourceTypeResolutionResult(
            provider=provider,
            native_type_name=native_type_name,
            canonical_type="Unclassified",
            default_monitoring_type="UNKNOWN",
            service_category="OTHER",
            is_unclassified=True,
        )

    # ==========================================================================
    # 3. Unit Administration & Conversions
    # ==========================================================================

    def add_unit(
        self,
        symbol: str,
        name: str,
        dimensionality: str,
        base_unit: str,
        scale_factor_to_base: Decimal | float | str,
        offset_to_base: Decimal | float | str = Decimal("0"),
        effective_from: datetime | None = None,
        effective_to: datetime | None = None,
    ) -> UnitDTO:
        now = datetime.utcnow()
        unit = UnitDTO(
            symbol=symbol,
            name=name,
            dimensionality=dimensionality,
            base_unit=base_unit,
            scale_factor_to_base=Decimal(str(scale_factor_to_base)),
            offset_to_base=Decimal(str(offset_to_base)),
            version=1,
            effective_from=effective_from or now,
            effective_to=effective_to,
            is_active=True,
        )
        return self._repo.add_unit(unit)

    def get_unit(self, symbol: str, as_of: datetime | None = None) -> UnitDTO | None:
        return self._repo.get_unit(symbol, as_of=as_of)

    def list_units(self) -> list[UnitDTO]:
        return self._repo.list_units()

    def convert_unit(
        self,
        value: Decimal | float | str | int,
        from_unit: str,
        to_unit: str,
        duration_hours: Decimal | float | str | int | None = None,
        decimal_places: int | None = 4,
        as_of: datetime | None = None,
    ) -> Decimal:
        return self._unit_service.convert(
            value=value,
            from_unit=from_unit,
            to_unit=to_unit,
            duration_hours=duration_hours,
            decimal_places=decimal_places,
            as_of=as_of,
        )

    # ==========================================================================
    # 4. Metric Catalogue Administration
    # ==========================================================================

    def add_metric(
        self,
        code: str,
        display_name: str,
        unit_symbol: str,
        aggregation_method: str,
        applicable_monitoring_types: list[str] | None = None,
        description: str | None = None,
        effective_from: datetime | None = None,
        effective_to: datetime | None = None,
    ) -> MetricDTO:
        now = datetime.utcnow()
        metric = MetricDTO(
            code=code,
            display_name=display_name,
            unit_symbol=unit_symbol,
            aggregation_method=aggregation_method,
            applicable_monitoring_types=applicable_monitoring_types or [],
            description=description,
            version=1,
            effective_from=effective_from or now,
            effective_to=effective_to,
            is_active=True,
        )
        return self._repo.add_metric(metric)

    def get_metric(self, code: str, as_of: datetime | None = None) -> MetricDTO | None:
        metric = self._repo.get_metric(code, as_of=as_of)
        if not metric:
            self._repo.record_gap(
                catalogue_type=CatalogueType.METRIC,
                provider="canonical",
                native_identifier=code,
            )
        return metric

    def list_metrics(self) -> list[MetricDTO]:
        return self._repo.list_metrics()

    # ==========================================================================
    # 5. Pricing Dimension Catalogue Administration & Escape Hatch
    # ==========================================================================

    def add_pricing_dimension(
        self,
        code: str,
        name: str,
        category: str,
        unit_symbol: str,
        aggregation_method: str,
        default_threshold_basis: str,
        applicability_rules: dict[str, Any] | None = None,
        is_custom_escape_hatch: bool = False,
        provider_code: str | None = None,
        example_services: str | None = None,
        notes: str | None = None,
        effective_from: datetime | None = None,
        effective_to: datetime | None = None,
    ) -> PricingDimensionDTO:
        now = datetime.utcnow()
        dim = PricingDimensionDTO(
            code=code,
            name=name,
            category=category,
            unit_symbol=unit_symbol,
            aggregation_method=aggregation_method,
            default_threshold_basis=default_threshold_basis,
            applicability_rules=applicability_rules or {},
            is_custom_escape_hatch=is_custom_escape_hatch,
            provider_code=provider_code,
            example_services=example_services,
            notes=notes,
            version=1,
            effective_from=effective_from or now,
            effective_to=effective_to,
            is_active=True,
        )
        return self._repo.add_pricing_dimension(dim)

    def get_pricing_dimension(
        self, code: str, as_of: datetime | None = None
    ) -> PricingDimensionDTO | None:
        dim = self._repo.get_pricing_dimension(code, as_of=as_of)
        if not dim:
            self._repo.record_gap(
                catalogue_type=CatalogueType.PRICING_DIMENSION,
                provider="canonical",
                native_identifier=code,
            )
        return dim

    def list_pricing_dimensions(self, provider: str | None = None) -> list[PricingDimensionDTO]:
        return self._repo.list_pricing_dimensions(provider=provider)

    def add_provider_escape_hatch_dimension(
        self,
        code: str,
        name: str,
        provider: str,
        unit_symbol: str,
        aggregation_method: str,
        default_threshold_basis: str,
        applicability_rules: dict[str, Any] | None = None,
        example_services: str | None = None,
        notes: str | None = None,
    ) -> PricingDimensionDTO:
        """Registers a provider-specific custom billing dimension via the escape hatch."""
        return self.add_pricing_dimension(
            code=code,
            name=name,
            category="Provider-Specific Escape Hatch",
            unit_symbol=unit_symbol,
            aggregation_method=aggregation_method,
            default_threshold_basis=default_threshold_basis,
            applicability_rules=applicability_rules or {"provider": provider.lower()},
            is_custom_escape_hatch=True,
            provider_code=provider.lower(),
            example_services=example_services,
            notes=notes or f"Provider-specific dimension escape hatch for {provider.upper()}.",
        )

    # ==========================================================================
    # 6. Catalogue Versioning & Historical Reproducibility
    # ==========================================================================

    def create_resource_type_version(
        self,
        provider: str,
        native_type_name: str,
        new_canonical_type: str,
        new_monitoring_type: str,
        effective_at: datetime | None = None,
    ) -> ResourceTypeDTO:
        """Creates a new version of a resource type mapping, preserving the historical mapping."""
        transition_time = effective_at or datetime.utcnow()
        current = self._repo.find_resource_type(provider, native_type_name)
        if not current:
            raise CatalogueVersioningError(
                f"Cannot version non-existent resource type '{provider}:{native_type_name}'."
            )

        # Close current version
        current.effective_to = transition_time
        current.is_active = False

        # Create new version
        new_version = ResourceTypeDTO(
            id=f"rt-{uuid.uuid4().hex[:12]}",
            provider=current.provider,
            service_id=current.service_id,
            native_type_name=current.native_type_name,
            canonical_type=new_canonical_type,
            service_category=current.service_category,
            default_monitoring_type=new_monitoring_type,
            version=current.version + 1,
            effective_from=transition_time,
            effective_to=None,
            is_active=True,
        )
        return self._repo.add_resource_type(new_version)

    # ==========================================================================
    # 7. Catalogue Gap Reporting & Workflow
    # ==========================================================================

    def get_gap_report(self, status: str = "OPEN") -> CatalogueGapReport:
        """Returns structured report of all unmapped entries logged across ingestion."""
        gaps = self._repo.list_gaps(status=status)
        by_type: dict[str, int] = {}
        by_provider: dict[str, int] = {}

        for g in gaps:
            by_type[g.catalogue_type] = by_type.get(g.catalogue_type, 0) + 1
            by_provider[g.provider] = by_provider.get(g.provider, 0) + 1

        all_gaps = self._repo.list_gaps(status=None)
        return CatalogueGapReport(
            total_gaps=len(all_gaps),
            open_gaps=len(gaps)
            if status == "OPEN"
            else len([g for g in all_gaps if g.status == GapStatus.OPEN]),
            gaps_by_type=by_type,
            gaps_by_provider=by_provider,
            items=gaps,
        )

    def resolve_gap(
        self,
        gap_id: str,
        resolution_notes: str,
        resolved_by: str,
    ) -> CatalogueGapDTO:
        """Marks a catalogue gap item as resolved by an administrator."""
        return self._repo.resolve_gap(
            gap_id=gap_id,
            resolution_notes=resolution_notes,
            resolved_by=resolved_by,
        )
