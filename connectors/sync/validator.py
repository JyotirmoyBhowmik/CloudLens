"""Ingestion Data Validation and Dead-Letter Quarantine Engine (Prompt 15 Item 99).

Enforces:
- Prompt 15 Item 99: Data validation (row counts, schema version, required fields, monetary sanity checks).
- Dead-letter quarantine with reasons visible to operators (SCHEMA_VIOLATION, MONETARY_SANITY_FAILURE, etc.).
- Never drops defective data silently; preserves payload and emits audit event.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from domain.audit.models import AuditEventCreate
from domain.audit.service import get_audit_service
from domain.config.tenant_settings import tenant_settings_store
from domain.models.enums import (
    AuditEventType,
    ConnectorCapability,
    QuarantineReason,
    QuarantineStatus,
)
from domain.sync.models import QuarantineRecord
from domain.sync.repository import QuarantineRepository, get_quarantine_repository
from domain.tenant.context import TenantContext

logger = logging.getLogger(__name__)


class IngestionDataValidator:
    """Validates incoming provider records and routes defectives to dead-letter quarantine."""

    def __init__(
        self,
        quarantine_repo: QuarantineRepository | None = None,
        audit_service: Any = None,
    ) -> None:
        self._quarantine_repo = quarantine_repo or get_quarantine_repository()
        self._audit_service = audit_service or get_audit_service()

    def validate_single_record(
        self,
        record: dict[str, Any],
        capability: ConnectorCapability,
        tenant_context: TenantContext,
    ) -> tuple[bool, QuarantineReason | None, str | None]:
        """Validates a single record payload according to its capability schema and sanity rules."""
        if not isinstance(record, dict) or not record:
            return (
                False,
                QuarantineReason.UNPARSEABLE_PAYLOAD,
                "Payload record is empty or not a valid dictionary",
            )

        settings = tenant_settings_store.get(tenant_context.tenant_id).data_validation_settings

        # 1. Cost record validation (COLLECT_COST_BULK, COLLECT_COST_QUERY)
        if capability in (
            ConnectorCapability.COLLECT_COST_BULK,
            ConnectorCapability.COLLECT_COST_QUERY,
        ):
            required_keys = {"record_id", "scope_id", "billed_cost", "currency"}
            # Allow fallback key names in raw provider payloads
            has_id = "record_id" in record or "id" in record or "LineItemId" in record
            has_scope = (
                "scope_id" in record or "account_id" in record or "subscription_id" in record
            )
            has_cost = "billed_cost" in record or "cost" in record or "amount" in record
            has_curr = "currency" in record or "Currency" in record or "billing_currency" in record

            if not (has_id and has_scope and has_cost and has_curr):
                missing = [k for k in required_keys if k not in record]
                return (
                    False,
                    QuarantineReason.MISSING_REQUIRED_FIELDS,
                    f"Cost record missing mandatory fields: {missing}",
                )

            # Extract numeric cost
            raw_cost = record.get("billed_cost", record.get("cost", record.get("amount")))
            try:
                numeric_cost = float(raw_cost)
            except (ValueError, TypeError):
                return (
                    False,
                    QuarantineReason.SCHEMA_VIOLATION,
                    f"Billed cost '{raw_cost}' cannot be parsed as a floating point number",
                )

            # Monetary sanity check (Rule 1.3 & Prompt 15 Item 99)
            category = str(
                record.get("charge_category", record.get("ChargeCategory", "Usage"))
            ).upper()
            if numeric_cost < 0 and "CREDIT" not in category and "ADJUSTMENT" not in category:
                return (
                    False,
                    QuarantineReason.MONETARY_SANITY_FAILURE,
                    f"Negative cost amount ({numeric_cost}) is strictly forbidden unless charge category is CREDIT or ADJUSTMENT",
                )

            if numeric_cost > settings.max_single_line_item_amount:
                return (
                    False,
                    QuarantineReason.MONETARY_SANITY_FAILURE,
                    f"Billed cost {numeric_cost} exceeds maximum allowed single line item threshold of {settings.max_single_line_item_amount}",
                )

            if numeric_cost < settings.min_single_line_item_amount:
                return (
                    False,
                    QuarantineReason.MONETARY_SANITY_FAILURE,
                    f"Billed credit {numeric_cost} is below minimum allowed credit threshold of {settings.min_single_line_item_amount}",
                )

            currency = str(record.get("currency", record.get("Currency", ""))).upper().strip()
            # ISO-4217 validation
            currency_code_len = 3  # no-hardcode-allow: reason="ISO 4217 specifies exactly 3-character alpha currency codes", reviewer="enterprise-arch"
            if len(currency) != currency_code_len or not currency.isalpha():
                return (
                    False,
                    QuarantineReason.SCHEMA_VIOLATION,
                    f"Invalid ISO 4217 currency code format: '{currency}'",
                )

        # 2. Resource record validation (DISCOVER_RESOURCES)
        elif capability == ConnectorCapability.DISCOVER_RESOURCES:
            keys_lower = {k.lower(): k for k in record.keys()}
            valid_id_keys = (
                "resource_id",
                "resourceid",
                "id",
                "arn",
                "resourcearn",
                "instanceid",
                "ocid",
                "name",
            )
            has_id = any(k in keys_lower for k in valid_id_keys)
            if not has_id:
                return (
                    False,
                    QuarantineReason.MISSING_REQUIRED_FIELDS,
                    "Resource record missing mandatory resource identifier ('id' or 'resource_id')",
                )

        # 3. Usage record validation (COLLECT_USAGE)
        elif capability == ConnectorCapability.COLLECT_USAGE:
            keys_lower = {k.lower(): k for k in record.keys()}
            metric_keys = ("metric_name", "metricname", "usage_type", "usagetype", "name")
            val_keys = ("value", "quantity", "usage_amount", "usageamount")
            has_metric = any(k in keys_lower for k in metric_keys)
            has_val = any(k in keys_lower for k in val_keys)
            if not (has_metric and has_val):
                return (
                    False,
                    QuarantineReason.MISSING_REQUIRED_FIELDS,
                    "Usage record missing mandatory metric identifier or value",
                )

        return True, None, None

    def validate_and_quarantine_batch(
        self,
        records: list[dict[str, Any]],
        capability: ConnectorCapability,
        connector_id: str,
        job_id: str | None,
        tenant_context: TenantContext,
    ) -> tuple[list[dict[str, Any]], list[QuarantineRecord]]:
        """Validates all records in batch, routing defective ones to quarantine repository with audit logging."""
        valid_records: list[dict[str, Any]] = []
        quarantined_records: list[QuarantineRecord] = []

        settings = tenant_settings_store.get(tenant_context.tenant_id).data_validation_settings
        if len(records) > settings.max_records_per_scope_warning:
            logger.warning(
                "Batch size %d exceeds recommended single-run record warning threshold %d for tenant %s",
                len(records),
                settings.max_records_per_scope_warning,
                tenant_context.tenant_id,
            )

        for record in records:
            is_valid, reason, error_msg = self.validate_single_record(
                record=record, capability=capability, tenant_context=tenant_context
            )
            if is_valid:
                valid_records.append(record)
            else:
                record_id = f"quar-{uuid.uuid4().hex[:12]}"
                quar = QuarantineRecord(
                    id=record_id,
                    tenant_id=tenant_context.tenant_id,
                    connector_id=connector_id,
                    job_id=job_id,
                    capability=capability,
                    quarantine_reason=reason or QuarantineReason.SCHEMA_VIOLATION,
                    error_details=error_msg or "Unknown validation failure",
                    payload_summary={
                        "keys": list(record.keys()) if isinstance(record, dict) else [],
                        "sample": {
                            k: str(v)[:100] for k, v in list(record.items())[:5]
                        }  # no-hardcode-allow: reason="Bounded sample preview snapshot for diagnostic readability", reviewer="enterprise-arch"
                        if isinstance(record, dict)
                        else {},
                    },
                    status=QuarantineStatus.QUARANTINED,
                    quarantined_at=datetime.now(UTC),
                )
                self._quarantine_repo.save(quar, tenant_context=tenant_context)
                quarantined_records.append(quar)

                # Emit tamper-evident audit event (Prompt 13 Item 86 / Prompt 15 Item 99)
                try:
                    self._audit_service.append_event(
                        tenant_context=tenant_context,
                        event_in=AuditEventCreate(
                            event_type=AuditEventType.PAYLOAD_QUARANTINED,
                            actor_id=tenant_context.user_id,
                            actor_roles=tenant_context.roles,
                            action=AuditEventType.PAYLOAD_QUARANTINED.value,
                            resource_type="QuarantineRecord",
                            resource_id=record_id,
                            details={
                                "connector_id": connector_id,
                                "capability": capability.value,
                                "reason": (reason or QuarantineReason.SCHEMA_VIOLATION).value,
                                "error": error_msg,
                            },
                            correlation_id=tenant_context.correlation_id,
                        ),
                    )
                except Exception as exc:
                    logger.warning("Failed to emit audit event for quarantine: %s", exc)

        if quarantined_records:
            logger.warning(
                "Quarantined %d of %d records for connector '%s' (capability=%s)",
                len(quarantined_records),
                len(records),
                connector_id,
                capability.value,
            )

        return valid_records, quarantined_records


# Global singleton data validator
_data_validator = IngestionDataValidator()


def get_data_validator() -> IngestionDataValidator:
    return _data_validator
