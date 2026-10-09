"""Catalogue SQL Repository Implementation (Prompt P08).

Enforces:
- Pattern P1: SQL Repository with PostgreSQL persistence and RLS compatibility.
- Zero mutable dict singletons in domain layer.
- Thread-safe async execution via db.session.run_async and get_tenant_session.
- Auto-seeding master catalogues into database if empty.
- Full point-in-time effective date queries (`as_of`).
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_tenant_session, run_async, verify_persistence_startup_guard
from domain.catalogues.models import (
    CatalogueGapDTO,
    DEFAULT_CATALOGUE_EPOCH,
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

logger = logging.getLogger("cloudlens.catalogues.repository")


class SqlCatalogueRepository:
    """Production SQL-backed repository for master catalogues and gap items."""

    is_in_memory: bool = False

    def __init__(self, load_seeds: bool = True) -> None:
        if load_seeds:
            run_async(self._ensure_seeds_async())

    async def _ensure_seeds_async(self) -> None:
        """Seeds canonical catalogue items into PostgreSQL if empty."""
        try:
            async with get_tenant_session("system") as sess:
                res = await sess.execute(text("SELECT count(*) FROM service_categories;"))
                count = res.scalar() or 0
                if count > 0:
                    return

                # 1. Categories
                for cat in SEED_SERVICE_CATEGORIES:
                    await sess.execute(
                        text("""
                            INSERT INTO service_categories (code, name, description, is_focus_standard, created_at)
                            VALUES (:code, :name, :description, :is_focus_standard, :created_at)
                            ON CONFLICT (code) DO NOTHING;
                        """),
                        {
                            "code": cat.code,
                            "name": cat.name,
                            "description": cat.description,
                            "is_focus_standard": cat.is_focus_standard,
                            "created_at": cat.created_at,
                        },
                    )

                # 2. Services
                for svc in SEED_SERVICES:
                    await sess.execute(
                        text("""
                            INSERT INTO services (id, provider, service_code, name, category, created_at)
                            VALUES (:id, :provider, :service_code, :name, :category, :created_at)
                            ON CONFLICT (id) DO NOTHING;
                        """),
                        {
                            "id": svc.id,
                            "provider": svc.provider,
                            "service_code": svc.service_code,
                            "name": svc.name,
                            "category": svc.category,
                            "created_at": svc.created_at,
                        },
                    )

                # 3. Service Mappings
                for smap in SEED_SERVICE_MAPPINGS:
                    await sess.execute(
                        text("""
                            INSERT INTO service_mappings (id, service_id, provider, native_service_name, version, effective_from, effective_to, is_active)
                            VALUES (:id, :service_id, :provider, :native_service_name, :version, :effective_from, :effective_to, :is_active)
                            ON CONFLICT (id) DO NOTHING;
                        """),
                        {
                            "id": smap.id,
                            "service_id": smap.service_id,
                            "provider": smap.provider,
                            "native_service_name": smap.native_service_name,
                            "version": smap.version,
                            "effective_from": smap.effective_from,
                            "effective_to": smap.effective_to,
                            "is_active": smap.is_active,
                        },
                    )

                # 4. Resource Types
                for rt in SEED_RESOURCE_TYPES:
                    await sess.execute(
                        text("""
                            INSERT INTO resource_types (id, provider, service_id, native_type_name, canonical_type, service_category, default_monitoring_type, version, effective_from, effective_to, is_active)
                            VALUES (:id, :provider, :service_id, :native_type_name, :canonical_type, :service_category, :default_monitoring_type, :version, :effective_from, :effective_to, :is_active)
                            ON CONFLICT (id) DO NOTHING;
                        """),
                        {
                            "id": rt.id,
                            "provider": rt.provider,
                            "service_id": rt.service_id,
                            "native_type_name": rt.native_type_name,
                            "canonical_type": rt.canonical_type,
                            "service_category": rt.service_category,
                            "default_monitoring_type": rt.default_monitoring_type,
                            "version": rt.version,
                            "effective_from": rt.effective_from,
                            "effective_to": rt.effective_to,
                            "is_active": rt.is_active,
                        },
                    )

                # 5. Units
                for unit in SEED_UNITS:
                    await sess.execute(
                        text("""
                            INSERT INTO unit_catalogue (symbol, name, dimensionality, base_unit, scale_factor_to_base, offset_to_base, version, effective_from, effective_to, is_active)
                            VALUES (:symbol, :name, :dimensionality, :base_unit, :scale_factor_to_base, :offset_to_base, :version, :effective_from, :effective_to, :is_active)
                            ON CONFLICT (symbol) DO NOTHING;
                        """),
                        {
                            "symbol": unit.symbol,
                            "name": unit.name,
                            "dimensionality": unit.dimensionality,
                            "base_unit": unit.base_unit,
                            "scale_factor_to_base": unit.scale_factor_to_base,
                            "offset_to_base": unit.offset_to_base,
                            "version": unit.version,
                            "effective_from": unit.effective_from,
                            "effective_to": unit.effective_to,
                            "is_active": unit.is_active,
                        },
                    )

                # 6. Metrics
                for metric in SEED_METRICS:
                    await sess.execute(
                        text("""
                            INSERT INTO metric_catalogue (code, display_name, unit_symbol, aggregation_method, applicable_monitoring_types, description, version, effective_from, effective_to, is_active)
                            VALUES (:code, :display_name, :unit_symbol, :aggregation_method, :applicable_monitoring_types, :description, :version, :effective_from, :effective_to, :is_active)
                            ON CONFLICT (code) DO NOTHING;
                        """),
                        {
                            "code": metric.code,
                            "display_name": metric.display_name,
                            "unit_symbol": metric.unit_symbol,
                            "aggregation_method": metric.aggregation_method,
                            "applicable_monitoring_types": json.dumps(metric.applicable_monitoring_types),
                            "description": metric.description,
                            "version": metric.version,
                            "effective_from": metric.effective_from,
                            "effective_to": metric.effective_to,
                            "is_active": metric.is_active,
                        },
                    )

                # 7. Pricing Dimensions
                for dim in SEED_PRICING_DIMENSIONS:
                    await sess.execute(
                        text("""
                            INSERT INTO pricing_dimension_catalogue (code, name, category, unit_symbol, aggregation_method, default_threshold_basis, applicability_rules, is_custom_escape_hatch, provider_code, example_services, notes, version, effective_from, effective_to, is_active)
                            VALUES (:code, :name, :category, :unit_symbol, :aggregation_method, :default_threshold_basis, :applicability_rules, :is_custom_escape_hatch, :provider_code, :example_services, :notes, :version, :effective_from, :effective_to, :is_active)
                            ON CONFLICT (code) DO NOTHING;
                        """),
                        {
                            "code": dim.code,
                            "name": dim.name,
                            "category": dim.category,
                            "unit_symbol": dim.unit_symbol,
                            "aggregation_method": dim.aggregation_method,
                            "default_threshold_basis": dim.default_threshold_basis,
                            "applicability_rules": json.dumps(dim.applicability_rules),
                            "is_custom_escape_hatch": dim.is_custom_escape_hatch,
                            "provider_code": dim.provider_code,
                            "example_services": dim.example_services,
                            "notes": dim.notes,
                            "version": dim.version,
                            "effective_from": dim.effective_from,
                            "effective_to": dim.effective_to,
                            "is_active": dim.is_active,
                        },
                    )

                await sess.commit()
        except Exception as e:
            logger.warning(f"Catalogue seed initialization caught exception: {e}")

    # --------------------------------------------------------------------------
    # Service Categories & Services
    # --------------------------------------------------------------------------

    def add_service_category(self, cat: ServiceCategoryDTO) -> ServiceCategoryDTO:
        async def _add():
            async with get_tenant_session("system") as sess:
                await sess.execute(
                    text("""
                        INSERT INTO service_categories (code, name, description, is_focus_standard, created_at)
                        VALUES (:code, :name, :description, :is_focus_standard, :created_at)
                        ON CONFLICT (code) DO UPDATE SET
                            name = EXCLUDED.name,
                            description = EXCLUDED.description,
                            is_focus_standard = EXCLUDED.is_focus_standard;
                    """),
                    {
                        "code": cat.code,
                        "name": cat.name,
                        "description": cat.description,
                        "is_focus_standard": cat.is_focus_standard,
                        "created_at": cat.created_at,
                    },
                )
                await sess.commit()
            return cat

        return run_async(_add())

    def list_service_categories(self) -> list[ServiceCategoryDTO]:
        async def _list():
            async with get_tenant_session("system") as sess:
                res = await sess.execute(text("SELECT code, name, description, is_focus_standard, created_at FROM service_categories ORDER BY code;"))
                return [
                    ServiceCategoryDTO(
                        code=row[0],
                        name=row[1],
                        description=row[2],
                        is_focus_standard=row[3],
                        created_at=row[4],
                    )
                    for row in res.fetchall()
                ]

        return run_async(_list())

    def add_service(self, svc: ServiceDTO) -> ServiceDTO:
        async def _add():
            async with get_tenant_session("system") as sess:
                await sess.execute(
                    text("""
                        INSERT INTO services (id, provider, service_code, name, category, created_at)
                        VALUES (:id, :provider, :service_code, :name, :category, :created_at)
                        ON CONFLICT (id) DO UPDATE SET
                            provider = EXCLUDED.provider,
                            service_code = EXCLUDED.service_code,
                            name = EXCLUDED.name,
                            category = EXCLUDED.category;
                    """),
                    {
                        "id": svc.id,
                        "provider": svc.provider,
                        "service_code": svc.service_code,
                        "name": svc.name,
                        "category": svc.category,
                        "created_at": svc.created_at,
                    },
                )
                await sess.commit()
            return svc

        return run_async(_add())

    def get_service(self, service_id: str) -> ServiceDTO | None:
        async def _get():
            async with get_tenant_session("system") as sess:
                res = await sess.execute(
                    text("SELECT id, provider, service_code, name, category, created_at FROM services WHERE id = :id LIMIT 1;"),
                    {"id": service_id},
                )
                row = res.fetchone()
                if not row:
                    return None
                return ServiceDTO(
                    id=row[0],
                    provider=row[1],
                    service_code=row[2],
                    name=row[3],
                    category=row[4],
                    created_at=row[5],
                )

        return run_async(_get())

    def list_services(self) -> list[ServiceDTO]:
        async def _list():
            async with get_tenant_session("system") as sess:
                res = await sess.execute(text("SELECT id, provider, service_code, name, category, created_at FROM services ORDER BY id;"))
                return [
                    ServiceDTO(
                        id=row[0],
                        provider=row[1],
                        service_code=row[2],
                        name=row[3],
                        category=row[4],
                        created_at=row[5],
                    )
                    for row in res.fetchall()
                ]

        return run_async(_list())

    def add_service_mapping(self, mapping: ServiceMappingDTO) -> ServiceMappingDTO:
        async def _add():
            async with get_tenant_session("system") as sess:
                await sess.execute(
                    text("""
                        INSERT INTO service_mappings (id, service_id, provider, native_service_name, version, effective_from, effective_to, is_active)
                        VALUES (:id, :service_id, :provider, :native_service_name, :version, :effective_from, :effective_to, :is_active)
                        ON CONFLICT (id) DO UPDATE SET
                            service_id = EXCLUDED.service_id,
                            provider = EXCLUDED.provider,
                            native_service_name = EXCLUDED.native_service_name,
                            version = EXCLUDED.version,
                            effective_from = EXCLUDED.effective_from,
                            effective_to = EXCLUDED.effective_to,
                            is_active = EXCLUDED.is_active;
                    """),
                    {
                        "id": mapping.id,
                        "service_id": mapping.service_id,
                        "provider": mapping.provider,
                        "native_service_name": mapping.native_service_name,
                        "version": mapping.version,
                        "effective_from": mapping.effective_from,
                        "effective_to": mapping.effective_to,
                        "is_active": mapping.is_active,
                    },
                )
                await sess.commit()
            return mapping

        return run_async(_add())

    def find_service_mapping(
        self, provider: str, native_service_name: str, as_of: datetime | None = None
    ) -> ServiceMappingDTO | None:
        async def _find():
            target_time = as_of or datetime.now(UTC)
            async with get_tenant_session("system") as sess:
                res = await sess.execute(
                    text("""
                        SELECT id, service_id, provider, native_service_name, version, effective_from, effective_to, is_active
                        FROM service_mappings
                        WHERE lower(provider) = lower(:provider)
                          AND lower(native_service_name) = lower(:name)
                          AND effective_from <= :as_of
                          AND (effective_to IS NULL OR effective_to > :as_of)
                        ORDER BY effective_from DESC
                        LIMIT 1;
                    """),
                    {
                        "provider": provider.strip(),
                        "name": native_service_name.strip(),
                        "as_of": target_time,
                    },
                )
                row = res.fetchone()
                if not row:
                    return None
                return ServiceMappingDTO(
                    id=row[0],
                    service_id=row[1],
                    provider=row[2],
                    native_service_name=row[3],
                    version=row[4],
                    effective_from=row[5],
                    effective_to=row[6],
                    is_active=row[7],
                )

        return run_async(_find())

    # --------------------------------------------------------------------------
    # Resource Types
    # --------------------------------------------------------------------------

    def add_resource_type(self, rt: ResourceTypeDTO) -> ResourceTypeDTO:
        async def _add():
            async with get_tenant_session("system") as sess:
                await sess.execute(
                    text("""
                        INSERT INTO resource_types (id, provider, service_id, native_type_name, canonical_type, service_category, default_monitoring_type, version, effective_from, effective_to, is_active)
                        VALUES (:id, :provider, :service_id, :native_type_name, :canonical_type, :service_category, :default_monitoring_type, :version, :effective_from, :effective_to, :is_active)
                        ON CONFLICT (id) DO UPDATE SET
                            provider = EXCLUDED.provider,
                            service_id = EXCLUDED.service_id,
                            native_type_name = EXCLUDED.native_type_name,
                            canonical_type = EXCLUDED.canonical_type,
                            service_category = EXCLUDED.service_category,
                            default_monitoring_type = EXCLUDED.default_monitoring_type,
                            version = EXCLUDED.version,
                            effective_from = EXCLUDED.effective_from,
                            effective_to = EXCLUDED.effective_to,
                            is_active = EXCLUDED.is_active;
                    """),
                    {
                        "id": rt.id,
                        "provider": rt.provider,
                        "service_id": rt.service_id,
                        "native_type_name": rt.native_type_name,
                        "canonical_type": rt.canonical_type,
                        "service_category": rt.service_category,
                        "default_monitoring_type": rt.default_monitoring_type,
                        "version": rt.version,
                        "effective_from": rt.effective_from,
                        "effective_to": rt.effective_to,
                        "is_active": rt.is_active,
                    },
                )
                await sess.commit()
            return rt

        return run_async(_add())

    def list_resource_types(self, provider: str | None = None) -> list[ResourceTypeDTO]:
        async def _list():
            async with get_tenant_session("system") as sess:
                if provider:
                    res = await sess.execute(
                        text("""
                            SELECT id, provider, service_id, native_type_name, canonical_type, service_category, default_monitoring_type, version, effective_from, effective_to, is_active
                            FROM resource_types
                            WHERE lower(provider) = lower(:provider)
                            ORDER BY native_type_name;
                        """),
                        {"provider": provider.strip()},
                    )
                else:
                    res = await sess.execute(
                        text("""
                            SELECT id, provider, service_id, native_type_name, canonical_type, service_category, default_monitoring_type, version, effective_from, effective_to, is_active
                            FROM resource_types
                            ORDER BY native_type_name;
                        """)
                    )
                return [
                    ResourceTypeDTO(
                        id=row[0],
                        provider=row[1],
                        service_id=row[2],
                        native_type_name=row[3],
                        canonical_type=row[4],
                        service_category=row[5] or "OTHER",
                        default_monitoring_type=row[6] or "UNKNOWN",
                        version=row[7],
                        effective_from=row[8],
                        effective_to=row[9],
                        is_active=row[10],
                    )
                    for row in res.fetchall()
                ]

        return run_async(_list())

    def find_resource_type(
        self, provider: str, native_type_name: str, as_of: datetime | None = None
    ) -> ResourceTypeDTO | None:
        async def _find():
            target_time = as_of or datetime.now(UTC)
            async with get_tenant_session("system") as sess:
                res = await sess.execute(
                    text("""
                        SELECT id, provider, service_id, native_type_name, canonical_type, service_category, default_monitoring_type, version, effective_from, effective_to, is_active
                        FROM resource_types
                        WHERE lower(provider) = lower(:provider)
                          AND lower(native_type_name) = lower(:name)
                          AND effective_from <= :as_of
                          AND (effective_to IS NULL OR effective_to > :as_of)
                        ORDER BY effective_from DESC
                        LIMIT 1;
                    """),
                    {
                        "provider": provider.strip(),
                        "name": native_type_name.strip(),
                        "as_of": target_time,
                    },
                )
                row = res.fetchone()
                if not row:
                    return None
                return ResourceTypeDTO(
                    id=row[0],
                    provider=row[1],
                    service_id=row[2],
                    native_type_name=row[3],
                    canonical_type=row[4],
                    service_category=row[5] or "OTHER",
                    default_monitoring_type=row[6] or "UNKNOWN",
                    version=row[7],
                    effective_from=row[8],
                    effective_to=row[9],
                    is_active=row[10],
                )

        return run_async(_find())

    # --------------------------------------------------------------------------
    # Units
    # --------------------------------------------------------------------------

    def add_unit(self, unit: UnitDTO) -> UnitDTO:
        async def _add():
            async with get_tenant_session("system") as sess:
                await sess.execute(
                    text("""
                        INSERT INTO unit_catalogue (symbol, name, dimensionality, base_unit, scale_factor_to_base, offset_to_base, version, effective_from, effective_to, is_active)
                        VALUES (:symbol, :name, :dimensionality, :base_unit, :scale_factor_to_base, :offset_to_base, :version, :effective_from, :effective_to, :is_active)
                        ON CONFLICT (symbol) DO UPDATE SET
                            name = EXCLUDED.name,
                            dimensionality = EXCLUDED.dimensionality,
                            base_unit = EXCLUDED.base_unit,
                            scale_factor_to_base = EXCLUDED.scale_factor_to_base,
                            offset_to_base = EXCLUDED.offset_to_base,
                            version = EXCLUDED.version,
                            effective_from = EXCLUDED.effective_from,
                            effective_to = EXCLUDED.effective_to,
                            is_active = EXCLUDED.is_active;
                    """),
                    {
                        "symbol": unit.symbol,
                        "name": unit.name,
                        "dimensionality": unit.dimensionality,
                        "base_unit": unit.base_unit,
                        "scale_factor_to_base": unit.scale_factor_to_base,
                        "offset_to_base": unit.offset_to_base,
                        "version": unit.version,
                        "effective_from": unit.effective_from,
                        "effective_to": unit.effective_to,
                        "is_active": unit.is_active,
                    },
                )
                await sess.commit()
            return unit

        return run_async(_add())

    def get_unit(self, symbol: str, as_of: datetime | None = None) -> UnitDTO | None:
        async def _get():
            target_time = as_of or datetime.now(UTC)
            async with get_tenant_session("system") as sess:
                res = await sess.execute(
                    text("""
                        SELECT symbol, name, dimensionality, base_unit, scale_factor_to_base, offset_to_base, version, effective_from, effective_to, is_active
                        FROM unit_catalogue
                        WHERE lower(symbol) = lower(:sym)
                          AND effective_from <= :as_of
                          AND (effective_to IS NULL OR effective_to > :as_of)
                        ORDER BY effective_from DESC
                        LIMIT 1;
                    """),
                    {"sym": symbol.strip(), "as_of": target_time},
                )
                row = res.fetchone()
                if not row:
                    # Fallback to latest
                    res2 = await sess.execute(
                        text("""
                            SELECT symbol, name, dimensionality, base_unit, scale_factor_to_base, offset_to_base, version, effective_from, effective_to, is_active
                            FROM unit_catalogue
                            WHERE lower(symbol) = lower(:sym)
                            ORDER BY version DESC LIMIT 1;
                        """),
                        {"sym": symbol.strip()},
                    )
                    row = res2.fetchone()
                if not row:
                    return None
                return UnitDTO(
                    symbol=row[0],
                    name=row[1],
                    dimensionality=row[2],
                    base_unit=row[3],
                    scale_factor_to_base=Decimal(str(row[4])),
                    offset_to_base=Decimal(str(row[5])),
                    version=row[6],
                    effective_from=row[7],
                    effective_to=row[8],
                    is_active=row[9],
                )

        return run_async(_get())

    def list_units(self) -> list[UnitDTO]:
        async def _list():
            async with get_tenant_session("system") as sess:
                res = await sess.execute(
                    text("""
                        SELECT symbol, name, dimensionality, base_unit, scale_factor_to_base, offset_to_base, version, effective_from, effective_to, is_active
                        FROM unit_catalogue
                        ORDER BY symbol;
                    """)
                )
                return [
                    UnitDTO(
                        symbol=row[0],
                        name=row[1],
                        dimensionality=row[2],
                        base_unit=row[3],
                        scale_factor_to_base=Decimal(str(row[4])),
                        offset_to_base=Decimal(str(row[5])),
                        version=row[6],
                        effective_from=row[7],
                        effective_to=row[8],
                        is_active=row[9],
                    )
                    for row in res.fetchall()
                ]

        return run_async(_list())

    # --------------------------------------------------------------------------
    # Metrics
    # --------------------------------------------------------------------------

    def add_metric(self, metric: MetricDTO) -> MetricDTO:
        async def _add():
            async with get_tenant_session("system") as sess:
                await sess.execute(
                    text("""
                        INSERT INTO metric_catalogue (code, display_name, unit_symbol, aggregation_method, applicable_monitoring_types, description, version, effective_from, effective_to, is_active)
                        VALUES (:code, :display_name, :unit_symbol, :aggregation_method, :applicable_monitoring_types, :description, :version, :effective_from, :effective_to, :is_active)
                        ON CONFLICT (code) DO UPDATE SET
                            display_name = EXCLUDED.display_name,
                            unit_symbol = EXCLUDED.unit_symbol,
                            aggregation_method = EXCLUDED.aggregation_method,
                            applicable_monitoring_types = EXCLUDED.applicable_monitoring_types,
                            description = EXCLUDED.description,
                            version = EXCLUDED.version,
                            effective_from = EXCLUDED.effective_from,
                            effective_to = EXCLUDED.effective_to,
                            is_active = EXCLUDED.is_active;
                    """),
                    {
                        "code": metric.code,
                        "display_name": metric.display_name,
                        "unit_symbol": metric.unit_symbol,
                        "aggregation_method": metric.aggregation_method,
                        "applicable_monitoring_types": json.dumps(metric.applicable_monitoring_types),
                        "description": metric.description,
                        "version": metric.version,
                        "effective_from": metric.effective_from,
                        "effective_to": metric.effective_to,
                        "is_active": metric.is_active,
                    },
                )
                await sess.commit()
            return metric

        return run_async(_add())

    def get_metric(self, code: str, as_of: datetime | None = None) -> MetricDTO | None:
        async def _get():
            target_time = as_of or datetime.now(UTC)
            async with get_tenant_session("system") as sess:
                res = await sess.execute(
                    text("""
                        SELECT code, display_name, unit_symbol, aggregation_method, applicable_monitoring_types, description, version, effective_from, effective_to, is_active
                        FROM metric_catalogue
                        WHERE code = :code
                          AND effective_from <= :as_of
                          AND (effective_to IS NULL OR effective_to > :as_of)
                        ORDER BY effective_from DESC
                        LIMIT 1;
                    """),
                    {"code": code.strip(), "as_of": target_time},
                )
                row = res.fetchone()
                if not row:
                    res2 = await sess.execute(
                        text("""
                            SELECT code, display_name, unit_symbol, aggregation_method, applicable_monitoring_types, description, version, effective_from, effective_to, is_active
                            FROM metric_catalogue
                            WHERE code = :code
                            ORDER BY version DESC LIMIT 1;
                        """),
                        {"code": code.strip()},
                    )
                    row = res2.fetchone()
                if not row:
                    return None
                monitoring_types = row[4]
                if isinstance(monitoring_types, str):
                    monitoring_types = json.loads(monitoring_types)
                elif monitoring_types is None:
                    monitoring_types = []
                return MetricDTO(
                    code=row[0],
                    display_name=row[1],
                    unit_symbol=row[2],
                    aggregation_method=row[3],
                    applicable_monitoring_types=monitoring_types,
                    description=row[5],
                    version=row[6],
                    effective_from=row[7],
                    effective_to=row[8],
                    is_active=row[9],
                )

        return run_async(_get())

    def list_metrics(self) -> list[MetricDTO]:
        async def _list():
            async with get_tenant_session("system") as sess:
                res = await sess.execute(
                    text("""
                        SELECT code, display_name, unit_symbol, aggregation_method, applicable_monitoring_types, description, version, effective_from, effective_to, is_active
                        FROM metric_catalogue
                        ORDER BY code;
                    """)
                )
                results = []
                for row in res.fetchall():
                    m_types = row[4]
                    if isinstance(m_types, str):
                        m_types = json.loads(m_types)
                    elif m_types is None:
                        m_types = []
                    results.append(
                        MetricDTO(
                            code=row[0],
                            display_name=row[1],
                            unit_symbol=row[2],
                            aggregation_method=row[3],
                            applicable_monitoring_types=m_types,
                            description=row[5],
                            version=row[6],
                            effective_from=row[7],
                            effective_to=row[8],
                            is_active=row[9],
                        )
                    )
                return results

        return run_async(_list())

    # --------------------------------------------------------------------------
    # Pricing Dimensions
    # --------------------------------------------------------------------------

    def add_pricing_dimension(self, dim: PricingDimensionDTO) -> PricingDimensionDTO:
        async def _add():
            async with get_tenant_session("system") as sess:
                await sess.execute(
                    text("""
                        INSERT INTO pricing_dimension_catalogue (code, name, category, unit_symbol, aggregation_method, default_threshold_basis, applicability_rules, is_custom_escape_hatch, provider_code, example_services, notes, version, effective_from, effective_to, is_active)
                        VALUES (:code, :name, :category, :unit_symbol, :aggregation_method, :default_threshold_basis, :applicability_rules, :is_custom_escape_hatch, :provider_code, :example_services, :notes, :version, :effective_from, :effective_to, :is_active)
                        ON CONFLICT (code) DO UPDATE SET
                            name = EXCLUDED.name,
                            category = EXCLUDED.category,
                            unit_symbol = EXCLUDED.unit_symbol,
                            aggregation_method = EXCLUDED.aggregation_method,
                            default_threshold_basis = EXCLUDED.default_threshold_basis,
                            applicability_rules = EXCLUDED.applicability_rules,
                            is_custom_escape_hatch = EXCLUDED.is_custom_escape_hatch,
                            provider_code = EXCLUDED.provider_code,
                            example_services = EXCLUDED.example_services,
                            notes = EXCLUDED.notes,
                            version = EXCLUDED.version,
                            effective_from = EXCLUDED.effective_from,
                            effective_to = EXCLUDED.effective_to,
                            is_active = EXCLUDED.is_active;
                    """),
                    {
                        "code": dim.code,
                        "name": dim.name,
                        "category": dim.category,
                        "unit_symbol": dim.unit_symbol,
                        "aggregation_method": dim.aggregation_method,
                        "default_threshold_basis": dim.default_threshold_basis,
                        "applicability_rules": json.dumps(dim.applicability_rules),
                        "is_custom_escape_hatch": dim.is_custom_escape_hatch,
                        "provider_code": dim.provider_code,
                        "example_services": dim.example_services,
                        "notes": dim.notes,
                        "version": dim.version,
                        "effective_from": dim.effective_from,
                        "effective_to": dim.effective_to,
                        "is_active": dim.is_active,
                    },
                )
                await sess.commit()
            return dim

        return run_async(_add())

    def get_pricing_dimension(
        self, code: str, as_of: datetime | None = None
    ) -> PricingDimensionDTO | None:
        async def _get():
            target_time = as_of or datetime.now(UTC)
            async with get_tenant_session("system") as sess:
                res = await sess.execute(
                    text("""
                        SELECT code, name, category, unit_symbol, aggregation_method, default_threshold_basis, applicability_rules, is_custom_escape_hatch, provider_code, example_services, notes, version, effective_from, effective_to, is_active
                        FROM pricing_dimension_catalogue
                        WHERE code = :code
                          AND effective_from <= :as_of
                          AND (effective_to IS NULL OR effective_to > :as_of)
                        ORDER BY effective_from DESC
                        LIMIT 1;
                    """),
                    {"code": code.strip(), "as_of": target_time},
                )
                row = res.fetchone()
                if not row:
                    res2 = await sess.execute(
                        text("""
                            SELECT code, name, category, unit_symbol, aggregation_method, default_threshold_basis, applicability_rules, is_custom_escape_hatch, provider_code, example_services, notes, version, effective_from, effective_to, is_active
                            FROM pricing_dimension_catalogue
                            WHERE code = :code
                            ORDER BY version DESC LIMIT 1;
                        """),
                        {"code": code.strip()},
                    )
                    row = res2.fetchone()
                if not row:
                    return None
                rules = row[6]
                if isinstance(rules, str):
                    rules = json.loads(rules)
                elif rules is None:
                    rules = {}
                return PricingDimensionDTO(
                    code=row[0],
                    name=row[1],
                    category=row[2],
                    unit_symbol=row[3],
                    aggregation_method=row[4],
                    default_threshold_basis=row[5],
                    applicability_rules=rules,
                    is_custom_escape_hatch=row[7],
                    provider_code=row[8],
                    example_services=row[9],
                    notes=row[10],
                    version=row[11],
                    effective_from=row[12],
                    effective_to=row[13],
                    is_active=row[14],
                )

        return run_async(_get())

    def list_pricing_dimensions(self, provider: str | None = None) -> list[PricingDimensionDTO]:
        async def _list():
            async with get_tenant_session("system") as sess:
                res = await sess.execute(
                    text("""
                        SELECT code, name, category, unit_symbol, aggregation_method, default_threshold_basis, applicability_rules, is_custom_escape_hatch, provider_code, example_services, notes, version, effective_from, effective_to, is_active
                        FROM pricing_dimension_catalogue
                        ORDER BY code;
                    """)
                )
                results = []
                p_norm = provider.strip().lower() if provider else None
                for row in res.fetchall():
                    rules = row[6]
                    if isinstance(rules, str):
                        rules = json.loads(rules)
                    elif rules is None:
                        rules = {}
                    dto = PricingDimensionDTO(
                        code=row[0],
                        name=row[1],
                        category=row[2],
                        unit_symbol=row[3],
                        aggregation_method=row[4],
                        default_threshold_basis=row[5],
                        applicability_rules=rules,
                        is_custom_escape_hatch=row[7],
                        provider_code=row[8],
                        example_services=row[9],
                        notes=row[10],
                        version=row[11],
                        effective_from=row[12],
                        effective_to=row[13],
                        is_active=row[14],
                    )
                    if p_norm:
                        if not dto.is_custom_escape_hatch or (
                            dto.provider_code and dto.provider_code.lower() == p_norm
                        ):
                            results.append(dto)
                    else:
                        results.append(dto)
                return results

        return run_async(_list())

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
        async def _record():
            effective_tid = tenant_id or "system"
            async with get_tenant_session(effective_tid) as sess:
                # Find existing open gap
                res = await sess.execute(
                    text("""
                        SELECT id, tenant_id, catalogue_type, provider, native_identifier, status, occurrence_count, first_seen_at, last_seen_at, context_payload, resolution_notes, resolved_by, resolved_at
                        FROM catalogue_gaps
                        WHERE status = 'OPEN'
                          AND catalogue_type = :cat_type
                          AND lower(provider) = lower(:provider)
                          AND lower(native_identifier) = lower(:ident)
                        LIMIT 1;
                    """),
                    {
                        "cat_type": catalogue_type,
                        "provider": provider.strip(),
                        "ident": native_identifier.strip(),
                    },
                )
                row = res.fetchone()
                now = datetime.now(UTC)
                if row:
                    gap_id = row[0]
                    occ = row[6] + 1
                    raw_ctx = row[9]
                    ctx_dict = raw_ctx if isinstance(raw_ctx, dict) else (json.loads(raw_ctx) if raw_ctx else {})
                    if context:
                        ctx_dict.update(context)
                    await sess.execute(
                        text("""
                            UPDATE catalogue_gaps
                            SET occurrence_count = :occ,
                                last_seen_at = :last_seen,
                                context_payload = :ctx
                            WHERE id = :id;
                        """),
                        {"id": gap_id, "occ": occ, "last_seen": now, "ctx": json.dumps(ctx_dict)},
                    )
                    await sess.commit()
                    return CatalogueGapDTO(
                        id=row[0],
                        tenant_id=row[1],
                        catalogue_type=row[2],
                        provider=row[3],
                        native_identifier=row[4],
                        status=row[5],
                        occurrence_count=occ,
                        first_seen_at=row[7],
                        last_seen_at=now,
                        context_payload=ctx_dict,
                        resolution_notes=row[10],
                        resolved_by=row[11],
                        resolved_at=row[12],
                    )

                new_id = f"gap-{uuid.uuid4().hex[:12]}"
                ctx_payload = context or {}
                await sess.execute(
                    text("""
                        INSERT INTO catalogue_gaps (id, tenant_id, catalogue_type, provider, native_identifier, status, occurrence_count, first_seen_at, last_seen_at, context_payload)
                        VALUES (:id, :tenant_id, :cat_type, :provider, :ident, 'OPEN', 1, :first_seen, :last_seen, :ctx);
                    """),
                    {
                        "id": new_id,
                        "tenant_id": tenant_id,
                        "cat_type": catalogue_type,
                        "provider": provider,
                        "ident": native_identifier,
                        "first_seen": now,
                        "last_seen": now,
                        "ctx": json.dumps(ctx_payload),
                    },
                )
                await sess.commit()
                return CatalogueGapDTO(
                    id=new_id,
                    tenant_id=tenant_id,
                    catalogue_type=catalogue_type,
                    provider=provider,
                    native_identifier=native_identifier,
                    status=GapStatus.OPEN,
                    occurrence_count=1,
                    first_seen_at=now,
                    last_seen_at=now,
                    context_payload=ctx_payload,
                )

        return run_async(_record())

    def list_gaps(
        self,
        status: str | None = None,
        catalogue_type: str | None = None,
        provider: str | None = None,
    ) -> list[CatalogueGapDTO]:
        async def _list():
            async with get_tenant_session("system") as sess:
                clauses = ["1=1"]
                params: dict[str, Any] = {}
                if status:
                    clauses.append("upper(status) = :st")
                    params["st"] = status.upper()
                if catalogue_type:
                    clauses.append("upper(catalogue_type) = :ct")
                    params["ct"] = catalogue_type.upper()
                if provider:
                    clauses.append("lower(provider) = :pr")
                    params["pr"] = provider.lower()

                query = f"""
                    SELECT id, tenant_id, catalogue_type, provider, native_identifier, status, occurrence_count, first_seen_at, last_seen_at, context_payload, resolution_notes, resolved_by, resolved_at
                    FROM catalogue_gaps
                    WHERE {' AND '.join(clauses)}
                    ORDER BY last_seen_at DESC;
                """
                res = await sess.execute(text(query), params)
                items = []
                for row in res.fetchall():
                    raw_ctx = row[9]
                    ctx_dict = raw_ctx if isinstance(raw_ctx, dict) else (json.loads(raw_ctx) if raw_ctx else {})
                    items.append(
                        CatalogueGapDTO(
                            id=row[0],
                            tenant_id=row[1],
                            catalogue_type=row[2],
                            provider=row[3],
                            native_identifier=row[4],
                            status=row[5],
                            occurrence_count=row[6],
                            first_seen_at=row[7],
                            last_seen_at=row[8],
                            context_payload=ctx_dict,
                            resolution_notes=row[10],
                            resolved_by=row[11],
                            resolved_at=row[12],
                        )
                    )
                return items

        return run_async(_list())

    def resolve_gap(self, gap_id: str, resolution_notes: str, resolved_by: str) -> CatalogueGapDTO:
        async def _resolve():
            async with get_tenant_session("system") as sess:
                res = await sess.execute(
                    text("""
                        SELECT id, tenant_id, catalogue_type, provider, native_identifier, status, occurrence_count, first_seen_at, last_seen_at, context_payload
                        FROM catalogue_gaps
                        WHERE id = :id;
                    """),
                    {"id": gap_id},
                )
                row = res.fetchone()
                if not row:
                    raise KeyError(f"Catalogue gap '{gap_id}' not found.")
                now = datetime.now(UTC)
                await sess.execute(
                    text("""
                        UPDATE catalogue_gaps
                        SET status = 'RESOLVED',
                            resolution_notes = :notes,
                            resolved_by = :by,
                            resolved_at = :at
                        WHERE id = :id;
                    """),
                    {
                        "id": gap_id,
                        "notes": resolution_notes,
                        "by": resolved_by,
                        "at": now,
                    },
                )
                await sess.commit()
                raw_ctx = row[9]
                ctx_dict = raw_ctx if isinstance(raw_ctx, dict) else (json.loads(raw_ctx) if raw_ctx else {})
                return CatalogueGapDTO(
                    id=row[0],
                    tenant_id=row[1],
                    catalogue_type=row[2],
                    provider=row[3],
                    native_identifier=row[4],
                    status=GapStatus.RESOLVED,
                    occurrence_count=row[6],
                    first_seen_at=row[7],
                    last_seen_at=row[8],
                    context_payload=ctx_dict,
                    resolution_notes=resolution_notes,
                    resolved_by=resolved_by,
                    resolved_at=now,
                )

        return run_async(_resolve())


# Backward compatible alias so instantiations of CatalogueRepository get the SQL implementation
CatalogueRepository = SqlCatalogueRepository

_catalogue_repo_instance: SqlCatalogueRepository | None = None


def get_catalogue_repository() -> SqlCatalogueRepository:
    """Dependency provider with persistence startup guard."""
    global _catalogue_repo_instance
    if _catalogue_repo_instance is None:
        _catalogue_repo_instance = SqlCatalogueRepository(load_seeds=True)
        verify_persistence_startup_guard(_catalogue_repo_instance)
    return _catalogue_repo_instance


def reset_catalogue_repository(repo: Any = None) -> Any:
    """Resets catalogue repository singleton for test isolation."""
    global _catalogue_repo_instance
    _catalogue_repo_instance = repo
    return _catalogue_repo_instance or get_catalogue_repository()
