"""Pricing Catalogue Repository (Prompt 20 / Track E).

Enforces:
- Slowly Changing Dimension (SCD Type 2) persistence and versioning.
- Point-in-time historical queries without rate overwrites.
- Strict isolation and non-lossy tracking of LIST and CONTRACTED rates.
- Pricing variance change record persistence.
- Unknown-SKU gap reporting and tracking.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from domain.models.exceptions import PricingSCDConflictException
from domain.pricing.models import (
    DiscountInfo,
    FreeAllowance,
    PricingChangeRecord,
    PricingRecord,
    PricingTierModel,
    RateType,
    TierBracket,
    TierStructure,
    UnknownSkuRecord,
)

logger = logging.getLogger(__name__)


class PricingRepository:
    """In-memory SCD Type 2 Pricing Catalogue Repository with multi-cloud seed loading."""

    def __init__(self, load_seed_data: bool = True) -> None:
        # All records keyed by record ID
        self._records: dict[str, PricingRecord] = {}

        # Natural key index: (tenant_id_or_empty, provider, sku, region, dimension, rate_type) -> list[PricingRecord]
        self._natural_index: dict[tuple[str, str, str, str, str, str], list[PricingRecord]] = {}

        # Change audit records
        self._changes: dict[str, PricingChangeRecord] = {}

        # Unknown SKU registry: (tenant_id_or_empty, provider, sku) -> UnknownSkuRecord
        self._unknown_skus: dict[tuple[str, str, str], UnknownSkuRecord] = {}

        if load_seed_data:
            self._load_seed_catalog()

    def _build_key(
        self,
        tenant_id: str | None,
        provider: str,
        sku: str | None,
        region: str,
        dimension: str,
        rate_type: RateType | str,
    ) -> tuple[str, str, str, str, str, str]:
        """Constructs canonical lowercase natural key for indexing."""
        t_id = (tenant_id or "").strip()
        p = provider.strip().lower()
        s = (sku or "").strip().lower()
        r = region.strip().lower()
        d = dimension.strip().upper()
        rt = rate_type.value if isinstance(rate_type, RateType) else str(rate_type).upper()
        return (t_id, p, s, r, d, rt)

    def add_or_update(
        self, record: PricingRecord
    ) -> tuple[PricingRecord, PricingChangeRecord | None]:
        """Ingests a pricing record following SCD Type 2 rules.

        STRICT PROHIBITION: Never overwrite a rate in place!
        If a record already exists with different pricing:
        - The old record is closed by setting effective_to = record.effective_from, is_active = False.
        - The new record is stored with version = old_record.version + 1, effective_to = None, is_active = True.
        - A PricingChangeRecord is created and stored.
        """
        key = self._build_key(
            record.tenant_id,
            record.provider,
            record.service_sku,
            record.region,
            record.pricing_dimension,
            record.rate_type,
        )

        existing_history = self._natural_index.setdefault(key, [])
        active_record = next((r for r in existing_history if r.is_active), None)

        if active_record is None:
            # First version of this SKU / rate type
            stored_record = record.model_copy(
                update={"version": 1, "is_active": True, "effective_to": None}
            )
            self._records[stored_record.id] = stored_record
            existing_history.append(stored_record)
            return stored_record, None

        # Check if rate has actually changed
        is_price_changed = abs(active_record.unit_price - record.unit_price) > 1e-9
        is_tier_changed = active_record.tier != record.tier
        is_allowance_changed = active_record.free_allowance != record.free_allowance

        if not (is_price_changed or is_tier_changed or is_allowance_changed):
            # Price unchanged; idempotently update retrieval timestamp without SCD bump
            refreshed = active_record.model_copy(update={"retrieved_at": record.retrieved_at})
            self._records[refreshed.id] = refreshed
            idx = existing_history.index(active_record)
            existing_history[idx] = refreshed
            return refreshed, None

        # SCD Type 2 Version Progression
        if record.effective_from < active_record.effective_from:
            raise PricingSCDConflictException(
                f"New effective_from ({record.effective_from}) cannot precede active record "
                f"effective_from ({active_record.effective_from}) for SKU '{record.service_sku}'."
            )

        # Close existing active record
        closed_record = active_record.model_copy(
            update={
                "effective_to": record.effective_from,
                "is_active": False,
            }
        )
        self._records[closed_record.id] = closed_record
        idx = existing_history.index(active_record)
        existing_history[idx] = closed_record

        # Insert new record version
        new_record = record.model_copy(
            update={
                "version": closed_record.version + 1,
                "effective_to": None,
                "is_active": True,
            }
        )
        self._records[new_record.id] = new_record
        existing_history.append(new_record)

        # Generate PricingChangeRecord
        abs_diff = round(new_record.unit_price - closed_record.unit_price, 6)
        pct_diff = (
            round((abs_diff / closed_record.unit_price) * 100.0, 4)
            if closed_record.unit_price > 0
            else 0.0
        )
        change_record = PricingChangeRecord(
            tenant_id=record.tenant_id,
            provider=record.provider,
            service=record.service,
            service_sku=record.service_sku,
            region=record.region,
            pricing_dimension=record.pricing_dimension,
            rate_type=record.rate_type,
            old_unit_price=closed_record.unit_price,
            new_unit_price=new_record.unit_price,
            absolute_change=abs_diff,
            percentage_change=pct_diff,
            effective_from=new_record.effective_from,
            source=new_record.source,
            notes=f"SCD Type 2 rate progression v{closed_record.version} -> v{new_record.version}",
        )
        self._changes[change_record.id] = change_record

        logger.info(
            "Pricing change detected for %s SKU %s: %.4f -> %.4f (%+.2f%%)",
            record.provider,
            record.service_sku,
            closed_record.unit_price,
            new_record.unit_price,
            pct_diff,
        )

        return new_record, change_record

    def get_by_id(self, record_id: str) -> PricingRecord | None:
        """Retrieves pricing record by unique ID."""
        return self._records.get(record_id)

    def find_at_date(
        self,
        provider: str,
        sku: str | None,
        region: str,
        dimension: str,
        query_date: datetime,
        rate_type: RateType | None = None,
        tenant_id: str | None = None,
        service: str | None = None,
    ) -> list[PricingRecord]:
        """Finds pricing records effective on a specific historical date (SCD Type 2 lookup)."""
        target_date = query_date if query_date.tzinfo else query_date.replace(tzinfo=UTC)
        p = provider.strip().lower()
        r = region.strip().lower()
        d = dimension.strip().upper()
        s = (sku or "").strip().lower()

        results: list[PricingRecord] = []

        # Iterate all records matching provider and region
        for rec in self._records.values():
            if rec.provider.lower() != p:
                continue
            if rec.region.lower() != r and r != "any" and rec.region.lower() != "global":
                continue
            if rec.pricing_dimension.upper() != d and d != "ALL":
                continue

            if sku and rec.service_sku:
                if rec.service_sku.lower() != s:
                    continue
            elif service and rec.service.lower() != service.lower():
                continue

            if rate_type is not None and rec.rate_type != rate_type:
                continue

            # Tenant isolation: tenant record matches requested tenant, or global matches None
            if tenant_id and rec.tenant_id and rec.tenant_id != tenant_id:
                continue

            if rec.is_effective_on(target_date):
                results.append(rec)

        return results

    def list_catalog(
        self,
        provider: str | None = None,
        service: str | None = None,
        sku: str | None = None,
        region: str | None = None,
        dimension: str | None = None,
        rate_type: RateType | None = None,
        effective_date: datetime | None = None,
        include_historical: bool = False,
        tenant_id: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[PricingRecord], int]:
        """Queries pricing catalogue with dimensional and effective date filters."""
        matched: list[PricingRecord] = []

        for rec in self._records.values():
            if provider and rec.provider.lower() != provider.strip().lower():
                continue
            if service and service.strip().lower() not in rec.service.lower():
                continue
            if sku and rec.service_sku and sku.strip().lower() not in rec.service_sku.lower():
                continue
            if region and region.strip().lower() not in rec.region.lower():
                continue
            if dimension and rec.pricing_dimension.upper() != dimension.strip().upper():
                continue
            if rate_type and rec.rate_type != rate_type:
                continue
            if tenant_id and rec.tenant_id and rec.tenant_id != tenant_id:
                continue

            if effective_date is not None:
                if not rec.is_effective_on(effective_date):
                    continue
            elif not include_historical and not rec.is_active:
                continue

            matched.append(rec)

        matched.sort(
            key=lambda x: (
                x.provider,
                x.service,
                x.service_sku or "",
                x.effective_from,
            ),
            reverse=True,
        )
        total = len(matched)
        start = (page - 1) * page_size
        return matched[start : start + page_size], total

    def list_changes(
        self,
        provider: str | None = None,
        sku: str | None = None,
        since: datetime | None = None,
    ) -> list[PricingChangeRecord]:
        """Lists detected rate change records."""
        results = list(self._changes.values())
        if provider:
            results = [c for c in results if c.provider.lower() == provider.strip().lower()]
        if sku:
            results = [
                c for c in results if c.service_sku and sku.strip().lower() in c.service_sku.lower()
            ]
        if since:
            since_utc = since if since.tzinfo else since.replace(tzinfo=UTC)
            results = [c for c in results if c.detected_at >= since_utc]

        results.sort(key=lambda x: x.detected_at, reverse=True)
        return results

    def record_unknown_sku(
        self,
        provider: str,
        service_sku: str,
        raw_payload: dict[str, Any] | None = None,
        service_hint: str | None = None,
        region_hint: str | None = None,
        tenant_id: str | None = None,
    ) -> UnknownSkuRecord:
        """Records an unknown SKU gap item without failing ingestion."""
        t_id = (tenant_id or "").strip()
        p = provider.strip().lower()
        s = service_sku.strip()
        key = (t_id, p, s)

        existing = self._unknown_skus.get(key)
        now = datetime.now(UTC)

        if existing:
            updated = existing.model_copy(
                update={
                    "occurrence_count": existing.occurrence_count + 1,
                    "last_seen_at": now,
                    "raw_payload": raw_payload or existing.raw_payload,
                }
            )
            self._unknown_skus[key] = updated
            return updated

        new_gap = UnknownSkuRecord(
            tenant_id=tenant_id,
            provider=provider,
            service_sku=service_sku,
            service_hint=service_hint,
            region_hint=region_hint,
            raw_payload=raw_payload or {},
            status="UNRESOLVED",
            occurrence_count=1,
            first_seen_at=now,
            last_seen_at=now,
        )
        self._unknown_skus[key] = new_gap
        return new_gap

    def list_unknown_skus(
        self,
        provider: str | None = None,
        status: str | None = None,
    ) -> list[UnknownSkuRecord]:
        """Lists unrecognised SKU gap records."""
        items = list(self._unknown_skus.values())
        if provider:
            items = [item for item in items if item.provider.lower() == provider.strip().lower()]
        if status:
            items = [item for item in items if item.status.upper() == status.strip().upper()]
        items.sort(key=lambda x: x.occurrence_count, reverse=True)
        return items

    def mark_unknown_sku_resolved(
        self,
        provider: str,
        service_sku: str,
        resolved_pricing_id: str,
        tenant_id: str | None = None,
        notes: str | None = None,
    ) -> UnknownSkuRecord | None:
        """Marks an unknown SKU as resolved once pricing is ingested."""
        t_id = (tenant_id or "").strip()
        key = (t_id, provider.strip().lower(), service_sku.strip())
        existing = self._unknown_skus.get(key)
        if not existing:
            return None
        updated = existing.model_copy(
            update={
                "status": "RESOLVED",
                "resolved_pricing_id": resolved_pricing_id,
                "resolution_notes": notes or f"Resolved to PricingRecord {resolved_pricing_id}",
                "last_seen_at": datetime.now(UTC),
            }
        )
        self._unknown_skus[key] = updated
        return updated

    def _load_seed_catalog(self) -> None:
        """Seeds multi-cloud baseline rates and historical versions for tests and runtime."""
        # 1. Historical AWS EC2 rate from 2024 (SCD Type 2 past version)
        hist_time = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
        mid_time = datetime(2024, 7, 1, 0, 0, 0, tzinfo=UTC)

        past_ec2_list = PricingRecord(
            provider="aws",
            service="AmazonEC2",
            service_sku="AWS-EC2-T3-XLARGE-US-EAST",
            resource_type="virtual_machine",
            region="us-east-1",
            pricing_dimension="DIM-03",  # Per-hour
            unit="Hrs",
            unit_price=0.1800,  # Older higher rate
            currency="USD",
            effective_from=hist_time,
            effective_to=mid_time,
            is_active=False,
            version=1,
            source="aws_price_list_bulk",
            attributes={"instanceType": "t3.xlarge", "operatingSystem": "Linux", "vcpu": 4},
        )
        self._records[past_ec2_list.id] = past_ec2_list
        key_aws_ec2_list = self._build_key(
            None, "aws", "AWS-EC2-T3-XLARGE-US-EAST", "us-east-1", "DIM-03", RateType.LIST
        )
        self._natural_index.setdefault(key_aws_ec2_list, []).append(past_ec2_list)

        # Current AWS EC2 list rate (v2, effective from mid_time)
        curr_ec2_list = PricingRecord(
            provider="aws",
            service="AmazonEC2",
            service_sku="AWS-EC2-T3-XLARGE-US-EAST",
            resource_type="virtual_machine",
            region="us-east-1",
            pricing_dimension="DIM-03",
            unit="Hrs",
            unit_price=0.1664,  # Current retail rate
            currency="USD",
            effective_from=mid_time,
            effective_to=None,
            is_active=True,
            version=2,
            source="aws_price_list_bulk",
            attributes={"instanceType": "t3.xlarge", "operatingSystem": "Linux", "vcpu": 4},
        )
        self._records[curr_ec2_list.id] = curr_ec2_list
        self._natural_index[key_aws_ec2_list].append(curr_ec2_list)

        # AWS EC2 Contracted EDP rate (v1, effective from mid_time)
        curr_ec2_edp = PricingRecord(
            provider="aws",
            service="AmazonEC2",
            service_sku="AWS-EC2-T3-XLARGE-US-EAST",
            resource_type="virtual_machine",
            region="us-east-1",
            pricing_dimension="DIM-03",
            unit="Hrs",
            unit_price=0.1331,  # 20% discount
            currency="USD",
            effective_from=mid_time,
            effective_to=None,
            is_active=True,
            version=1,
            rate_type=RateType.CONTRACTED,
            source="aws_edp_negotiated",
            discount_info=DiscountInfo(
                discount_type="PERCENTAGE",
                discount_percentage=20.0,
                contract_reference="EDP-2024-ENTERPRISE-01",
            ),
            attributes={"instanceType": "t3.xlarge"},
        )
        self._records[curr_ec2_edp.id] = curr_ec2_edp
        key_aws_ec2_edp = self._build_key(
            None, "aws", "AWS-EC2-T3-XLARGE-US-EAST", "us-east-1", "DIM-03", RateType.CONTRACTED
        )
        self._natural_index.setdefault(key_aws_ec2_edp, []).append(curr_ec2_edp)

        # 2. AWS S3 Tiered Storage with Free Allowance (DIM-24, DIM-26)
        s3_tiered_record = PricingRecord(
            provider="aws",
            service="AmazonS3",
            service_sku="AWS-S3-STANDARD-BYTE-HRS",
            resource_type="object_storage",
            region="us-east-1",
            pricing_dimension="DIM-11",  # Per-GB-month
            unit="GB-Mo",
            unit_price=0.023,
            currency="USD",
            free_allowance=FreeAllowance(
                quantity=5.0,  # 5 GB free tier allowance
                unit="GB-Mo",
                reset_period="MONTHLY",
                post_allowance_rate=0.023,
                is_exhaustible=True,
            ),
            tier=TierStructure(
                pricing_model=PricingTierModel.GRADUATED,
                brackets=[
                    TierBracket(
                        tier_start=0.0, tier_end=51200.0, tier_unit_rate=0.023
                    ),  # First 50 TB
                    TierBracket(
                        tier_start=51200.0, tier_end=512000.0, tier_unit_rate=0.022
                    ),  # Next 450 TB
                    TierBracket(
                        tier_start=512000.0, tier_end=None, tier_unit_rate=0.021
                    ),  # Over 500 TB
                ],
            ),
            effective_from=hist_time,
            effective_to=None,
            is_active=True,
            version=1,
            source="aws_price_list_bulk",
            attributes={"storageClass": "Standard"},
        )
        self._records[s3_tiered_record.id] = s3_tiered_record
        key_s3 = self._build_key(
            None, "aws", "AWS-S3-STANDARD-BYTE-HRS", "us-east-1", "DIM-11", RateType.LIST
        )
        self._natural_index.setdefault(key_s3, []).append(s3_tiered_record)

        # S3 Contracted rate
        s3_contracted = PricingRecord(
            provider="aws",
            service="AmazonS3",
            service_sku="AWS-S3-STANDARD-BYTE-HRS",
            resource_type="object_storage",
            region="us-east-1",
            pricing_dimension="DIM-11",
            unit="GB-Mo",
            unit_price=0.0195,  # 15% discount
            currency="USD",
            effective_from=mid_time,
            effective_to=None,
            is_active=True,
            version=1,
            rate_type=RateType.CONTRACTED,
            source="aws_edp_negotiated",
            discount_info=DiscountInfo(
                discount_type="PERCENTAGE",
                discount_percentage=15.0,
                contract_reference="EDP-2024-ENTERPRISE-01",
            ),
        )
        self._records[s3_contracted.id] = s3_contracted
        key_s3_edp = self._build_key(
            None, "aws", "AWS-S3-STANDARD-BYTE-HRS", "us-east-1", "DIM-11", RateType.CONTRACTED
        )
        self._natural_index.setdefault(key_s3_edp, []).append(s3_contracted)

        # 3. Azure Virtual Machine Retail & Contracted Price Sheet
        az_vm_list = PricingRecord(
            provider="azure",
            service="Virtual Machines",
            service_sku="00000000-1111-2222-3333-444444444444",
            resource_type="virtual_machine",
            region="eastus",
            pricing_dimension="DIM-03",
            unit="1 Hour",
            unit_price=0.192,
            currency="USD",
            effective_from=hist_time,
            effective_to=None,
            is_active=True,
            version=1,
            source="azure_retail_prices_api",
            attributes={"skuName": "D4s v5", "meterName": "D4s v5"},
        )
        self._records[az_vm_list.id] = az_vm_list
        key_az_list = self._build_key(
            None,
            "azure",
            "00000000-1111-2222-3333-444444444444",
            "eastus",
            "DIM-03",
            RateType.LIST,
        )
        self._natural_index.setdefault(key_az_list, []).append(az_vm_list)

        az_vm_contracted = PricingRecord(
            provider="azure",
            service="Virtual Machines",
            service_sku="00000000-1111-2222-3333-444444444444",
            resource_type="virtual_machine",
            region="eastus",
            pricing_dimension="DIM-03",
            unit="1 Hour",
            unit_price=0.1536,  # 20% EA discount
            currency="USD",
            effective_from=mid_time,
            effective_to=None,
            is_active=True,
            version=1,
            rate_type=RateType.CONTRACTED,
            source="azure_price_sheet_api",
            discount_info=DiscountInfo(
                discount_type="PERCENTAGE",
                discount_percentage=20.0,
                contract_reference="EA-AZURE-2024",
            ),
        )
        self._records[az_vm_contracted.id] = az_vm_contracted
        key_az_contracted = self._build_key(
            None,
            "azure",
            "00000000-1111-2222-3333-444444444444",
            "eastus",
            "DIM-03",
            RateType.CONTRACTED,
        )
        self._natural_index.setdefault(key_az_contracted, []).append(az_vm_contracted)

        # 4. GCP Compute Engine Retail & Account Contract
        gcp_vm_list = PricingRecord(
            provider="gcp",
            service="Compute Engine",
            service_sku="D982-F0A1-332B",
            resource_type="virtual_machine",
            region="us-central1",
            pricing_dimension="DIM-15",  # Per-vCPU-hour
            unit="h",
            unit_price=0.031611,
            currency="USD",
            effective_from=hist_time,
            effective_to=None,
            is_active=True,
            version=1,
            source="gcp_billing_catalog",
            attributes={"description": "N2 Instance Core running in Americas"},
        )
        self._records[gcp_vm_list.id] = gcp_vm_list
        key_gcp_list = self._build_key(
            None, "gcp", "D982-F0A1-332B", "us-central1", "DIM-15", RateType.LIST
        )
        self._natural_index.setdefault(key_gcp_list, []).append(gcp_vm_list)

        gcp_vm_contracted = PricingRecord(
            provider="gcp",
            service="Compute Engine",
            service_sku="D982-F0A1-332B",
            resource_type="virtual_machine",
            region="us-central1",
            pricing_dimension="DIM-15",
            unit="h",
            unit_price=0.025289,  # 20% discount
            currency="USD",
            effective_from=mid_time,
            effective_to=None,
            is_active=True,
            version=1,
            rate_type=RateType.CONTRACTED,
            source="gcp_contract_pricing",
            discount_info=DiscountInfo(
                discount_type="PERCENTAGE",
                discount_percentage=20.0,
                contract_reference="GCP-CUD-2024",
            ),
        )
        self._records[gcp_vm_contracted.id] = gcp_vm_contracted
        key_gcp_contracted = self._build_key(
            None, "gcp", "D982-F0A1-332B", "us-central1", "DIM-15", RateType.CONTRACTED
        )
        self._natural_index.setdefault(key_gcp_contracted, []).append(gcp_vm_contracted)

        # 5. OCI Compute Retail & Universal Credits Contract (UCC)
        oci_vm_list = PricingRecord(
            provider="oci",
            service="Compute",
            service_sku="B88298",
            resource_type="virtual_machine",
            region="us-ashburn-1",
            pricing_dimension="DIM-14",  # Per-CPU
            unit="OCPU-Hours",
            unit_price=0.025,
            currency="USD",
            effective_from=hist_time,
            effective_to=None,
            is_active=True,
            version=1,
            source="oci_static_rate_card",
            attributes={"displayName": "Compute - Standard - E4 OCPU"},
        )
        self._records[oci_vm_list.id] = oci_vm_list
        key_oci_list = self._build_key(
            None, "oci", "B88298", "us-ashburn-1", "DIM-14", RateType.LIST
        )
        self._natural_index.setdefault(key_oci_list, []).append(oci_vm_list)

        oci_vm_contracted = PricingRecord(
            provider="oci",
            service="Compute",
            service_sku="B88298",
            resource_type="virtual_machine",
            region="us-ashburn-1",
            pricing_dimension="DIM-14",
            unit="OCPU-Hours",
            unit_price=0.020,  # 20% UCC discount
            currency="USD",
            effective_from=mid_time,
            effective_to=None,
            is_active=True,
            version=1,
            rate_type=RateType.CONTRACTED,
            source="oci_ucc_contract",
            discount_info=DiscountInfo(
                discount_type="PERCENTAGE",
                discount_percentage=20.0,
                contract_reference="OCI-UCC-2024",
            ),
        )
        self._records[oci_vm_contracted.id] = oci_vm_contracted
        key_oci_contracted = self._build_key(
            None, "oci", "B88298", "us-ashburn-1", "DIM-14", RateType.CONTRACTED
        )
        self._natural_index.setdefault(key_oci_contracted, []).append(oci_vm_contracted)

        # 6. Multi-Cloud Managed Database, Block Storage, and Network Seeds (Prompt 23)
        # 6a. AWS Seeds
        aws_rds_record = PricingRecord(
            provider="aws",
            service="AmazonRDS",
            service_sku="AWS-RDS-DB-R5-2XLARGE",
            resource_type="database_instance",
            region="us-east-1",
            pricing_dimension="DIM-03",
            unit="Hrs",
            unit_price=0.4800,
            currency="USD",
            effective_from=hist_time,
            source="aws_price_list_bulk",
            attributes={"engine": "PostgreSQL", "instanceType": "db.r5.2xlarge"},
        )
        self._records[aws_rds_record.id] = aws_rds_record
        k_aws_rds = self._build_key(
            None, "aws", "AWS-RDS-DB-R5-2XLARGE", "us-east-1", "DIM-03", RateType.LIST
        )
        self._natural_index.setdefault(k_aws_rds, []).append(aws_rds_record)

        aws_ebs_record = PricingRecord(
            provider="aws",
            service="AmazonEBS",
            service_sku="AWS-EBS-GP3-STORAGE",
            resource_type="block_storage",
            region="us-east-1",
            pricing_dimension="DIM-11",
            unit="GB-Mo",
            unit_price=0.0800,
            currency="USD",
            effective_from=hist_time,
            source="aws_price_list_bulk",
            attributes={"volumeType": "gp3"},
        )
        self._records[aws_ebs_record.id] = aws_ebs_record
        k_aws_ebs = self._build_key(
            None, "aws", "AWS-EBS-GP3-STORAGE", "us-east-1", "DIM-11", RateType.LIST
        )
        self._natural_index.setdefault(k_aws_ebs, []).append(aws_ebs_record)

        aws_egress_record = PricingRecord(
            provider="aws",
            service="AmazonEC2",
            service_sku="AWS-DATA-TRANSFER-OUT-INTERNET",
            resource_type="network_transfer",
            region="us-east-1",
            pricing_dimension="DIM-12",
            unit="GB",
            unit_price=0.0900,
            currency="USD",
            free_allowance=FreeAllowance(
                quantity=100.0,
                unit="GB",
                reset_period="MONTHLY",
                post_allowance_rate=0.0900,
            ),
            effective_from=hist_time,
            source="aws_price_list_bulk",
        )
        self._records[aws_egress_record.id] = aws_egress_record
        k_aws_egress = self._build_key(
            None, "aws", "AWS-DATA-TRANSFER-OUT-INTERNET", "us-east-1", "DIM-12", RateType.LIST
        )
        self._natural_index.setdefault(k_aws_egress, []).append(aws_egress_record)

        aws_ip_record = PricingRecord(
            provider="aws",
            service="AmazonEC2",
            service_sku="AWS-PUBLIC-IPV4-ADDRESS",
            resource_type="ip_address",
            region="us-east-1",
            pricing_dimension="DIM-03",
            unit="Hrs",
            unit_price=0.0050,
            currency="USD",
            effective_from=hist_time,
            source="aws_price_list_bulk",
        )
        self._records[aws_ip_record.id] = aws_ip_record
        k_aws_ip = self._build_key(
            None, "aws", "AWS-PUBLIC-IPV4-ADDRESS", "us-east-1", "DIM-03", RateType.LIST
        )
        self._natural_index.setdefault(k_aws_ip, []).append(aws_ip_record)

        # 6b. Azure Seeds
        az_sql_record = PricingRecord(
            provider="azure",
            service="Azure SQL Database",
            service_sku="AZURE-SQL-GEN5-4VCORE",
            resource_type="database_instance",
            region="eastus",
            pricing_dimension="DIM-03",
            unit="1 Hour",
            unit_price=0.5400,
            currency="USD",
            effective_from=hist_time,
            source="azure_retail_prices_api",
            attributes={"tier": "General Purpose", "compute": "4 vCore Gen5"},
        )
        self._records[az_sql_record.id] = az_sql_record
        k_az_sql = self._build_key(
            None, "azure", "AZURE-SQL-GEN5-4VCORE", "eastus", "DIM-03", RateType.LIST
        )
        self._natural_index.setdefault(k_az_sql, []).append(az_sql_record)

        az_disk_record = PricingRecord(
            provider="azure",
            service="Managed Disks",
            service_sku="AZURE-DISK-PREMIUM-SSD-P10",
            resource_type="block_storage",
            region="eastus",
            pricing_dimension="DIM-11",
            unit="GB-Mo",
            unit_price=0.1000,
            currency="USD",
            effective_from=hist_time,
            source="azure_retail_prices_api",
            attributes={"diskType": "Premium SSD"},
        )
        self._records[az_disk_record.id] = az_disk_record
        k_az_disk = self._build_key(
            None, "azure", "AZURE-DISK-PREMIUM-SSD-P10", "eastus", "DIM-11", RateType.LIST
        )
        self._natural_index.setdefault(k_az_disk, []).append(az_disk_record)

        az_blob_record = PricingRecord(
            provider="azure",
            service="Blob Storage",
            service_sku="AZURE-BLOB-HOT-LRS",
            resource_type="object_storage",
            region="eastus",
            pricing_dimension="DIM-11",
            unit="GB-Mo",
            unit_price=0.0180,
            currency="USD",
            free_allowance=FreeAllowance(
                quantity=5.0,
                unit="GB-Mo",
                reset_period="MONTHLY",
                post_allowance_rate=0.0180,
            ),
            effective_from=hist_time,
            source="azure_retail_prices_api",
            attributes={"accessTier": "Hot", "redundancy": "LRS"},
        )
        self._records[az_blob_record.id] = az_blob_record
        k_az_blob = self._build_key(
            None, "azure", "AZURE-BLOB-HOT-LRS", "eastus", "DIM-11", RateType.LIST
        )
        self._natural_index.setdefault(k_az_blob, []).append(az_blob_record)

        az_egress_record = PricingRecord(
            provider="azure",
            service="Virtual Machines",
            service_sku="AZURE-BANDWIDTH-EGRESS-INTERNET",
            resource_type="network_transfer",
            region="eastus",
            pricing_dimension="DIM-12",
            unit="GB",
            unit_price=0.0870,
            currency="USD",
            free_allowance=FreeAllowance(
                quantity=100.0,
                unit="GB",
                reset_period="MONTHLY",
                post_allowance_rate=0.0870,
            ),
            effective_from=hist_time,
            source="azure_retail_prices_api",
        )
        self._records[az_egress_record.id] = az_egress_record
        k_az_egress = self._build_key(
            None, "azure", "AZURE-BANDWIDTH-EGRESS-INTERNET", "eastus", "DIM-12", RateType.LIST
        )
        self._natural_index.setdefault(k_az_egress, []).append(az_egress_record)

        az_ip_record = PricingRecord(
            provider="azure",
            service="Virtual Machines",
            service_sku="AZURE-PUBLIC-IP-STANDARD",
            resource_type="ip_address",
            region="eastus",
            pricing_dimension="DIM-03",
            unit="1 Hour",
            unit_price=0.0050,
            currency="USD",
            effective_from=hist_time,
            source="azure_retail_prices_api",
        )
        self._records[az_ip_record.id] = az_ip_record
        k_az_ip = self._build_key(
            None, "azure", "AZURE-PUBLIC-IP-STANDARD", "eastus", "DIM-03", RateType.LIST
        )
        self._natural_index.setdefault(k_az_ip, []).append(az_ip_record)

        # 6c. GCP Seeds
        gcp_sql_record = PricingRecord(
            provider="gcp",
            service="Cloud SQL",
            service_sku="GCP-CLOUDSQL-PG-CUSTOM-4-16",
            resource_type="database_instance",
            region="us-central1",
            pricing_dimension="DIM-03",
            unit="h",
            unit_price=0.2600,
            currency="USD",
            effective_from=hist_time,
            source="gcp_billing_catalog",
            attributes={"databaseEngine": "PostgreSQL", "tier": "db-custom-4-16384"},
        )
        self._records[gcp_sql_record.id] = gcp_sql_record
        k_gcp_sql = self._build_key(
            None, "gcp", "GCP-CLOUDSQL-PG-CUSTOM-4-16", "us-central1", "DIM-03", RateType.LIST
        )
        self._natural_index.setdefault(k_gcp_sql, []).append(gcp_sql_record)

        gcp_disk_record = PricingRecord(
            provider="gcp",
            service="Persistent Disk",
            service_sku="GCP-DISK-PD-BALANCED",
            resource_type="block_storage",
            region="us-central1",
            pricing_dimension="DIM-11",
            unit="GB-Mo",
            unit_price=0.1000,
            currency="USD",
            effective_from=hist_time,
            source="gcp_billing_catalog",
            attributes={"diskType": "pd-balanced"},
        )
        self._records[gcp_disk_record.id] = gcp_disk_record
        k_gcp_disk = self._build_key(
            None, "gcp", "GCP-DISK-PD-BALANCED", "us-central1", "DIM-11", RateType.LIST
        )
        self._natural_index.setdefault(k_gcp_disk, []).append(gcp_disk_record)

        gcp_storage_record = PricingRecord(
            provider="gcp",
            service="Cloud Storage",
            service_sku="GCP-STORAGE-STANDARD-REGIONAL",
            resource_type="object_storage",
            region="us-central1",
            pricing_dimension="DIM-11",
            unit="GB-Mo",
            unit_price=0.0200,
            currency="USD",
            free_allowance=FreeAllowance(
                quantity=5.0,
                unit="GB-Mo",
                reset_period="MONTHLY",
                post_allowance_rate=0.0200,
            ),
            effective_from=hist_time,
            source="gcp_billing_catalog",
            attributes={"storageClass": "Standard"},
        )
        self._records[gcp_storage_record.id] = gcp_storage_record
        k_gcp_store = self._build_key(
            None, "gcp", "GCP-STORAGE-STANDARD-REGIONAL", "us-central1", "DIM-11", RateType.LIST
        )
        self._natural_index.setdefault(k_gcp_store, []).append(gcp_storage_record)

        gcp_egress_record = PricingRecord(
            provider="gcp",
            service="Compute Engine",
            service_sku="GCP-NETWORK-INTERNET-EGRESS",
            resource_type="network_transfer",
            region="us-central1",
            pricing_dimension="DIM-12",
            unit="GB",
            unit_price=0.0850,
            currency="USD",
            effective_from=hist_time,
            source="gcp_billing_catalog",
        )
        self._records[gcp_egress_record.id] = gcp_egress_record
        k_gcp_egress = self._build_key(
            None, "gcp", "GCP-NETWORK-INTERNET-EGRESS", "us-central1", "DIM-12", RateType.LIST
        )
        self._natural_index.setdefault(k_gcp_egress, []).append(gcp_egress_record)

        gcp_ip_record = PricingRecord(
            provider="gcp",
            service="Compute Engine",
            service_sku="GCP-NETWORK-STATIC-IP",
            resource_type="ip_address",
            region="us-central1",
            pricing_dimension="DIM-03",
            unit="h",
            unit_price=0.0040,
            currency="USD",
            effective_from=hist_time,
            source="gcp_billing_catalog",
        )
        self._records[gcp_ip_record.id] = gcp_ip_record
        k_gcp_ip = self._build_key(
            None, "gcp", "GCP-NETWORK-STATIC-IP", "us-central1", "DIM-03", RateType.LIST
        )
        self._natural_index.setdefault(k_gcp_ip, []).append(gcp_ip_record)

        # 6d. OCI Seeds
        oci_db_record = PricingRecord(
            provider="oci",
            service="Base Database Service",
            service_sku="OCI-ADB-ECPU",
            resource_type="database_instance",
            region="us-ashburn-1",
            pricing_dimension="DIM-14",
            unit="ECPU-Hours",
            unit_price=0.3360,
            currency="USD",
            effective_from=hist_time,
            source="oci_static_rate_card",
            attributes={"shape": "ECPU"},
        )
        self._records[oci_db_record.id] = oci_db_record
        k_oci_db = self._build_key(
            None, "oci", "OCI-ADB-ECPU", "us-ashburn-1", "DIM-14", RateType.LIST
        )
        self._natural_index.setdefault(k_oci_db, []).append(oci_db_record)

        oci_block_record = PricingRecord(
            provider="oci",
            service="Block Volume",
            service_sku="OCI-BLOCK-STORAGE-BALANCED",
            resource_type="block_storage",
            region="us-ashburn-1",
            pricing_dimension="DIM-11",
            unit="GB-Mo",
            unit_price=0.0425,
            currency="USD",
            effective_from=hist_time,
            source="oci_static_rate_card",
            attributes={"performanceTier": "Balanced"},
        )
        self._records[oci_block_record.id] = oci_block_record
        k_oci_block = self._build_key(
            None, "oci", "OCI-BLOCK-STORAGE-BALANCED", "us-ashburn-1", "DIM-11", RateType.LIST
        )
        self._natural_index.setdefault(k_oci_block, []).append(oci_block_record)

        oci_store_record = PricingRecord(
            provider="oci",
            service="Object Storage",
            service_sku="OCI-OBJECT-STORAGE-STANDARD",
            resource_type="object_storage",
            region="us-ashburn-1",
            pricing_dimension="DIM-11",
            unit="GB-Mo",
            unit_price=0.0255,
            currency="USD",
            free_allowance=FreeAllowance(
                quantity=10.0,
                unit="GB-Mo",
                reset_period="MONTHLY",
                post_allowance_rate=0.0255,
            ),
            effective_from=hist_time,
            source="oci_static_rate_card",
            attributes={"tier": "Standard"},
        )
        self._records[oci_store_record.id] = oci_store_record
        k_oci_store = self._build_key(
            None, "oci", "OCI-OBJECT-STORAGE-STANDARD", "us-ashburn-1", "DIM-11", RateType.LIST
        )
        self._natural_index.setdefault(k_oci_store, []).append(oci_store_record)

        oci_egress_record = PricingRecord(
            provider="oci",
            service="Compute",
            service_sku="OCI-NETWORKING-OUTBOUND-DATA",
            resource_type="network_transfer",
            region="us-ashburn-1",
            pricing_dimension="DIM-12",
            unit="GB",
            unit_price=0.0085,
            currency="USD",
            free_allowance=FreeAllowance(
                quantity=10240.0,  # 10 TB free outbound data transfer per month!
                unit="GB",
                reset_period="MONTHLY",
                post_allowance_rate=0.0085,
            ),
            effective_from=hist_time,
            source="oci_static_rate_card",
        )
        self._records[oci_egress_record.id] = oci_egress_record
        k_oci_egress = self._build_key(
            None, "oci", "OCI-NETWORKING-OUTBOUND-DATA", "us-ashburn-1", "DIM-12", RateType.LIST
        )
        self._natural_index.setdefault(k_oci_egress, []).append(oci_egress_record)

        oci_ip_record = PricingRecord(
            provider="oci",
            service="Compute",
            service_sku="OCI-NETWORKING-RESERVED-PUBLIC-IP",
            resource_type="ip_address",
            region="us-ashburn-1",
            pricing_dimension="DIM-03",
            unit="Hrs",
            unit_price=0.0000,  # OCI includes 1 public IP per instance for free
            currency="USD",
            effective_from=hist_time,
            source="oci_static_rate_card",
        )
        self._records[oci_ip_record.id] = oci_ip_record
        k_oci_ip = self._build_key(
            None,
            "oci",
            "OCI-NETWORKING-RESERVED-PUBLIC-IP",
            "us-ashburn-1",
            "DIM-03",
            RateType.LIST,
        )
        self._natural_index.setdefault(k_oci_ip, []).append(oci_ip_record)
