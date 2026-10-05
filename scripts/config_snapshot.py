#!/usr/bin/env python3
"""Configuration Snapshot & Promotion CLI Utility (Prompt R-FEAT / IMP-09).

Usage:
    python scripts/config_snapshot.py export --out snapshot_dev.json --env DEV
    python scripts/config_snapshot.py diff snapshot_dev.json snapshot_prod.json
    python scripts/config_snapshot.py import snapshot_dev.json [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from domain.config.snapshot_engine import get_config_snapshot_engine


def main() -> int:
    parser = argparse.ArgumentParser(description="CloudLens Configuration Snapshot & Promotion Tool")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # export
    p_export = subparsers.add_parser("export", help="Export configuration snapshot bundle")
    p_export.add_argument("--out", required=True, help="Output JSON bundle file path")
    p_export.add_argument("--env", default="DEV", help="Source environment label (default: DEV)")
    p_export.add_argument("--version", default="1.0.0", help="Version label (default: 1.0.0)")

    # diff
    p_diff = subparsers.add_parser("diff", help="Diff two configuration snapshots")
    p_diff.add_argument("file_a", help="First snapshot file path")
    p_diff.add_argument("file_b", help="Second snapshot file path")

    # import
    p_import = subparsers.add_parser("import", help="Import snapshot into environment")
    p_import.add_argument("file", help="Snapshot file path to import")
    p_import.add_argument("--dry-run", action="store_true", help="Validate without writing files")

    args = parser.parse_args()
    engine = get_config_snapshot_engine()

    if args.command == "export":
        snapshot = engine.export_snapshot(environment=args.env, version_label=args.version)
        out_path = Path(args.out)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, indent=2)
        print(f"[EXPORT OK] Exported {snapshot['masters_count']} masters to {out_path} (SHA: {snapshot['bundle_sha256'][:16]}...)")
        return 0

    elif args.command == "diff":
        with open(args.file_a, "r", encoding="utf-8") as f:
            snap_a = json.load(f)
        with open(args.file_b, "r", encoding="utf-8") as f:
            snap_b = json.load(f)
        diff_res = engine.diff_snapshots(snap_a, snap_b)
        print(f"============================================================")
        print(f" CONFIGURATION SNAPSHOT SEMANTIC DIFF                       ")
        print(f" Source: {diff_res['source_env']} -> Target: {diff_res['target_env']}")
        print(f" Total Differences: {diff_res['total_differences_count']}  ")
        print(f"============================================================")
        print(json.dumps(diff_res, indent=2))
        return 0

    elif args.command == "import":
        with open(args.file, "r", encoding="utf-8") as f:
            snap = json.load(f)
        res = engine.import_snapshot(snap, dry_run=args.dry_run)
        print(f"[IMPORT {res['status']}] {res['imported_masters_count']} masters processed. Dry-run: {res['dry_run']}")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
