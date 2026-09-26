"""Enumeration Bridge & Master Registry Bidirectional Synchronizer (Prompt 48 Item 36).

Enforces:
1. Every enumeration in code must be validated against its registered master.
2. Code and master can never diverge silently.
3. A master value added without a corresponding code path fails the build.
4. A code path referencing a value absent from a master fails the build.
5. Test code is NOT exempt from enumeration bridge verification.
"""

import sys
from enum import Enum
from typing import Any, cast

from pydantic import BaseModel, Field

from domain.models.enums import (
    ChargeCategory,
    PolicySeverity,
    PricingStatus,
    ProviderCapability,
    ProviderType,
    RuntimeStatus,
    ServiceCategory,
    SystemRole,
)
from domain.models.exceptions import MasterDataException
from masterdata.models import MasterDataRecord
from masterdata.service import MasterDataService, get_master_data_service


class EnumMasterBinding(BaseModel):
    """Binding specification connecting a Python Enum class to a registered master."""

    enum_name: str
    master_type: str
    case_sensitive: bool = False
    code_transformer: str = "identity"  # 'identity', 'upper', 'lower'


class EnumBridgeValidationResult(BaseModel):
    """Report detailing bidirectional parity between code enums and master data."""

    is_valid: bool
    total_bindings_checked: int
    total_violations: int
    violations: list[str] = Field(default_factory=list)
    binding_summaries: dict[str, dict[str, Any]] = Field(default_factory=dict)


# Canonical registry of code enums bound to master data types
DEFAULT_ENUM_BINDINGS: dict[type[Enum], str] = {
    ProviderType: "CLOUD_PROVIDER",
    ServiceCategory: "SERVICE_CATEGORY",
    RuntimeStatus: "RUNTIME_STATUS",
    PricingStatus: "PRICING_STATUS",
    ChargeCategory: "CHARGE_CATEGORY",
    PolicySeverity: "POLICY_SEVERITY",
    SystemRole: "ROLE",
    ProviderCapability: "PROVIDER_CAPABILITY",
}


def _normalize(val: str, case_sensitive: bool = False) -> str:
    return val.strip() if case_sensitive else val.strip().upper()


class EnumerationBridge:
    """Validates bidirectional conformity between Python Enum declarations and master records."""

    def __init__(
        self,
        master_service: MasterDataService | None = None,
        bindings: dict[Any, str] | None = None,
    ) -> None:
        self._master_service = master_service or get_master_data_service()
        self._bindings = bindings or DEFAULT_ENUM_BINDINGS

    def validate(self, raise_on_failure: bool = False) -> EnumBridgeValidationResult:
        """Executes full bidirectional verification.

        Acceptance: Adding a value to a master without a code path, or referencing
        a value absent from a master, both fail the build.
        """
        violations: list[str] = []
        summaries: dict[str, dict[str, Any]] = {}

        for enum_cls, master_type in self._bindings.items():
            enum_name = enum_cls.__name__

            # 1. Fetch active records from master data
            try:
                master_records: list[MasterDataRecord] = self._master_service.list_records(
                    master_type
                )
            except Exception as e:
                msg = f"Failed to retrieve master data for '{master_type}': {e}"
                violations.append(msg)
                summaries[enum_name] = {"error": msg}
                continue

            master_codes_raw = {r.code for r in master_records if r.is_active}
            master_codes_normalized = {_normalize(c): c for c in master_codes_raw}

            # 2. Extract enum values from code
            enum_values_raw = {str(member.value) for member in enum_cls}
            enum_values_normalized = {_normalize(v): v for v in enum_values_raw}

            # 3. Check for master values missing in code path
            missing_in_code_norm = set(master_codes_normalized.keys()) - set(
                enum_values_normalized.keys()
            )
            for norm_key in sorted(missing_in_code_norm):
                orig_code = master_codes_normalized[norm_key]
                violations.append(
                    f"Master value '{orig_code}' added to master '{master_type}' without corresponding code path in {enum_name}."
                )

            # 4. Check for code path referencing values absent from master
            missing_in_master_norm = set(enum_values_normalized.keys()) - set(
                master_codes_normalized.keys()
            )
            for norm_key in sorted(missing_in_master_norm):
                orig_val = enum_values_normalized[norm_key]
                violations.append(
                    f"Code path in {enum_name} references value '{orig_val}' absent from master '{master_type}'."
                )

            summaries[enum_name] = {
                "master_type": master_type,
                "master_records_count": len(master_codes_raw),
                "enum_members_count": len(enum_values_raw),
                "missing_in_code": [master_codes_normalized[k] for k in missing_in_code_norm],
                "missing_in_master": [enum_values_normalized[k] for k in missing_in_master_norm],
                "is_in_sync": len(missing_in_code_norm) == 0 and len(missing_in_master_norm) == 0,
            }

        is_valid = len(violations) == 0
        result = EnumBridgeValidationResult(
            is_valid=is_valid,
            total_bindings_checked=len(self._bindings),
            total_violations=len(violations),
            violations=violations,
            binding_summaries=summaries,
        )

        if not is_valid and raise_on_failure:
            error_details = "\n  - " + "\n  - ".join(violations)
            raise MasterDataException(
                f"Enumeration Bridge validation failed with {len(violations)} divergence(s):{error_details}"
            )

        return result

    def generate_enum_from_master(
        self,
        master_type: str,
        enum_name: str | None = None,
    ) -> type[Enum]:
        """Synthesizes a dynamic Python Enum directly from the current master data state."""
        records = self._master_service.list_records(master_type)
        name = enum_name or f"Dynamic{master_type.replace('_', ' ').title().replace(' ', '')}"
        members: dict[str, str] = {}
        for r in records:
            if r.is_active:
                member_key = r.code.upper().replace("-", "_").replace(".", "_").replace(" ", "_")
                members[member_key] = r.code
        return cast(type[Enum], Enum(name, members))


def verify_enumeration_bridge(master_service: MasterDataService | None = None) -> bool:
    """CLI / Gate entrypoint for enumeration bridge build verification."""
    bridge = EnumerationBridge(master_service=master_service)
    res = bridge.validate(raise_on_failure=False)
    if not res.is_valid:
        print("=" * 80, file=sys.stderr)
        print("CLOUDLENS BUILD FAILURE: ENUMERATION BRIDGE DIVERGENCE DETECTED", file=sys.stderr)
        print(
            "Enforces Prompt 48 Item 36: Code enums and master data must never diverge.",
            file=sys.stderr,
        )
        print("=" * 80, file=sys.stderr)
        for v in res.violations:
            print(f"  [DIVERGENCE] {v}", file=sys.stderr)
        print("=" * 80, file=sys.stderr)
        return False
    print(
        f"[PASS] Enumeration Bridge: All {res.total_bindings_checked} bound enums are 100% in sync with registered masters."
    )
    return True


if __name__ == "__main__":
    success = verify_enumeration_bridge()
    sys.exit(0 if success else 1)
