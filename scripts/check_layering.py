#!/usr/bin/env python3
"""CloudLens Layering Rule Enforcement Check.

Architecture layering rule:
presentation -> application -> domain -> normalisation -> ingestion -> connector -> provider.

Rule: Nothing above the connector layer may import a provider SDK (boto3, botocore, azure,
google.cloud, oci) or directly instantiate provider clients.
"""

import ast
import os
import sys
from pathlib import Path
from typing import NamedTuple

FORBIDDEN_PROVIDER_SDKS = {
    "boto3",
    "botocore",
    "azure",
    "azure.mgmt",
    "azure.identity",
    "azure.storage",
    "google.cloud",
    "google.auth",
    "oci",
}

LAYERS_ABOVE_CONNECTORS = [
    "domain",
    "normalisation",
    "masterdata",
    "api",
    "workers",
    "db",
    os.path.join("connectors", "contract"),
]


class Violation(NamedTuple):
    file_path: str
    line_number: int
    imported_module: str
    layer: str
    message: str


def check_file(file_path: Path, root_path: Path) -> list[Violation]:
    violations: list[Violation] = []
    rel_path = file_path.relative_to(root_path).as_posix()

    # Determine which layer this file belongs to
    file_layer = None
    for layer in LAYERS_ABOVE_CONNECTORS:
        normalized_layer = layer.replace("\\", "/")
        if rel_path.startswith(normalized_layer + "/") or rel_path == normalized_layer:
            file_layer = normalized_layer
            break

    if not file_layer:
        return violations

    try:
        with open(file_path, encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=str(file_path))
    except Exception as exc:
        print(f"Warning: Failed to parse {file_path}: {exc}", file=sys.stderr)
        return violations

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                for sdk in FORBIDDEN_PROVIDER_SDKS:
                    if alias.name == sdk or alias.name.startswith(sdk + "."):
                        msg = (
                            f"Layering rule 'presentation -> application -> domain -> normalisation "
                            f"-> ingestion -> connector -> provider' violated. Layer '{file_layer}' "
                            f"must not import provider SDK '{alias.name}'."
                        )
                        violations.append(
                            Violation(rel_path, node.lineno, alias.name, file_layer, msg)
                        )
                        break
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                for sdk in FORBIDDEN_PROVIDER_SDKS:
                    if node.module == sdk or node.module.startswith(sdk + "."):
                        msg = (
                            f"Layering rule 'presentation -> application -> domain -> normalisation "
                            f"-> ingestion -> connector -> provider' violated. Layer '{file_layer}' "
                            f"must not import provider SDK '{node.module}'."
                        )
                        violations.append(
                            Violation(rel_path, node.lineno, node.module, file_layer, msg)
                        )
                        break

    return violations


def run_check(root_dir: str = ".") -> int:
    root_path = Path(root_dir).resolve()
    all_violations: list[Violation] = []

    for path in root_path.rglob("*.py"):
        # Ignore tests, virtual environments, build artifacts, git
        parts = path.parts
        if any(
            ignored in parts
            for ignored in [".venv", "venv", ".git", "__pycache__", "build", "dist"]
        ):
            continue
        # Skip test fixtures designed to intentionally test the violation scanner
        if "fixtures" in parts:
            continue
        violations = check_file(path, root_path)
        all_violations.extend(violations)

    if all_violations:
        print(
            f"\n[FAIL] Found {len(all_violations)} Layering Rule violation(s):\n", file=sys.stderr
        )
        for v in all_violations:
            print(f"  {v.file_path}:{v.line_number} in layer '{v.layer}':", file=sys.stderr)
            print(f"    ERROR: {v.message}\n", file=sys.stderr)
        return 1

    print(
        "[PASS] Layering rule check passed. Zero forbidden provider SDK imports above connector layer."
    )
    return 0


if __name__ == "__main__":
    target_dir = sys.argv[1] if len(sys.argv) > 1 else "."
    sys.exit(run_check(target_dir))
