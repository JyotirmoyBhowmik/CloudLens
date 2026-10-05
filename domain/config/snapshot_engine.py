"""Configuration Snapshot and Promotion Engine (Prompt R-FEAT / IMP-09).

Enables zero-touch environment promotion (DEV -> UAT -> PROD):
1. Exports all master data seeds and configuration as a single canonical, versioned JSON bundle with SHA-256 integrity seal.
2. Computes granular semantic diffs between two configuration snapshots.
3. Imports and validates snapshot bundles into target environments without manual re-keying.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from masterdata.improvement_features import get_feature_config

logger = logging.getLogger("cloudlens.domain.config.snapshot")


class ConfigSnapshotEngine:
    """Engine for exporting, diffing, and importing platform configuration bundles."""

    def __init__(self, seeds_dir: Path | None = None) -> None:
        self._seeds_dir = seeds_dir or (
            Path(__file__).resolve().parent.parent.parent / "masterdata" / "seeds"
        )
        self._config = get_feature_config("IMP_09_CONFIG_SNAPSHOT")
        self._schema_version = self._config.get("bundle_schema_version", "1.0.0")

    def export_snapshot(
        self,
        environment: str = "DEV",
        version_label: str = "1.0.0",
    ) -> dict[str, Any]:
        """Collects all master data seeds and platform settings into a single canonical snapshot."""
        masters: dict[str, Any] = {}

        if self._seeds_dir.exists():
            for seed_file in sorted(self._seeds_dir.glob("*.json")):
                master_key = seed_file.stem
                try:
                    with open(seed_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    masters[master_key] = data
                except Exception as exc:
                    logger.warning("Could not read seed file %s: %s", seed_file, exc)

        payload_to_hash = json.dumps(masters, sort_keys=True)
        bundle_hash = hashlib.sha256(payload_to_hash.encode("utf-8")).hexdigest()

        snapshot = {
            "schema_version": self._schema_version,
            "version_label": version_label,
            "environment": environment,
            "created_at": datetime.now(UTC).isoformat(),
            "bundle_sha256": bundle_hash,
            "masters_count": len(masters),
            "masters": masters,
        }
        return snapshot

    def diff_snapshots(
        self,
        snapshot_a: dict[str, Any],
        snapshot_b: dict[str, Any],
    ) -> dict[str, Any]:
        """Calculates granular differences between two configuration snapshot bundles."""
        masters_a = snapshot_a.get("masters", {})
        masters_b = snapshot_b.get("masters", {})

        all_keys = sorted(set(masters_a.keys()) | set(masters_b.keys()))
        added_masters: list[str] = []
        removed_masters: list[str] = []
        modified_masters: dict[str, Any] = {}

        for k in all_keys:
            if k not in masters_a:
                added_masters.append(k)
            elif k not in masters_b:
                removed_masters.append(k)
            else:
                data_a = json.dumps(masters_a[k], sort_keys=True)
                data_b = json.dumps(masters_b[k], sort_keys=True)
                if data_a != data_b:
                    # Count items in each
                    len_a = len(masters_a[k]) if isinstance(masters_a[k], list) else 1
                    len_b = len(masters_b[k]) if isinstance(masters_b[k], list) else 1
                    modified_masters[k] = {
                        "records_before": len_a,
                        "records_after": len_b,
                        "delta": len_b - len_a,
                    }

        total_diffs = len(added_masters) + len(removed_masters) + len(modified_masters)

        return {
            "has_differences": total_diffs > 0,
            "total_differences_count": total_diffs,
            "source_env": snapshot_a.get("environment", "SOURCE"),
            "target_env": snapshot_b.get("environment", "TARGET"),
            "added_masters": added_masters,
            "removed_masters": removed_masters,
            "modified_masters": modified_masters,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    def import_snapshot(
        self,
        snapshot: dict[str, Any],
        dry_run: bool = False,
        target_dir: Path | None = None,
    ) -> dict[str, Any]:
        """Validates and imports a snapshot bundle into the target environment."""
        masters = snapshot.get("masters", {})
        if not masters:
            raise ValueError("Invalid configuration snapshot: 'masters' payload is empty.")

        # Verify hash
        expected_hash = snapshot.get("bundle_sha256")
        actual_hash = hashlib.sha256(json.dumps(masters, sort_keys=True).encode("utf-8")).hexdigest()
        if expected_hash and expected_hash != actual_hash:
            raise ValueError(f"Snapshot integrity error: hash mismatch ({expected_hash} != {actual_hash})")

        destination_dir = target_dir or self._seeds_dir
        imported_files: list[str] = []

        if not dry_run:
            destination_dir.mkdir(parents=True, exist_ok=True)
            for master_name, records in masters.items():
                target_file = destination_dir / f"{master_name}.json"
                with open(target_file, "w", encoding="utf-8") as f:
                    json.dump(records, f, indent=2)
                imported_files.append(master_name)

        return {
            "status": "VALIDATED" if dry_run else "IMPORTED",
            "dry_run": dry_run,
            "schema_version": snapshot.get("schema_version"),
            "imported_masters_count": len(masters),
            "imported_files": imported_files if not dry_run else list(masters.keys()),
            "bundle_sha256": actual_hash,
            "timestamp": datetime.now(UTC).isoformat(),
        }


_SNAPSHOT_ENGINE_INSTANCE = ConfigSnapshotEngine()


def get_config_snapshot_engine() -> ConfigSnapshotEngine:
    """Returns singleton configuration snapshot engine instance."""
    return _SNAPSHOT_ENGINE_INSTANCE
