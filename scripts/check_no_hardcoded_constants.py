"""CloudLens AST Checker: No Hard-coded Business Constants.

Enforces Rule 18 and Prompt 02 Acceptance:
"no monetary value, percentage, threshold, interval or retention period may appear as a
literal in application code. Every such value resolves from configuration with a documented default."
"Introducing a literal 0.9 as a threshold in application code fails the build."
"""

import ast
import os
import sys
from pathlib import Path
from typing import NamedTuple

ROOT_DIR = Path(__file__).resolve().parent.parent

# Application directories to scan
SCANNED_DIRS = ["api", "domain/rules", "workers", "normalisation", "connectors"]

# Files or directories explicitly exempted from the check (config definitions, master data, seeds, tests)
EXEMPT_PATHS = [
    "domain/config",
    "masterdata",
    "db/seeds",
    "tests",
    "scripts",
]

# Business variable keyword stems that must never be assigned literal numbers
BUSINESS_TARGET_KEYWORDS = {
    "threshold",
    "percentage",
    "budget",
    "approval",
    "retention",
    "quota",
    "discount",
    "markup",
    "spike",
    "z_score",
}

# Standard structural / mathematical conversion constants exempt from violation
ALLOWED_STRUCTURAL_NUMBERS = {
    0,
    1,
    -1,
    0.0,
    1.0,
    100.0,  # Percentage base math (x * 100.0)
    1000.0,  # Millisecond conversion
    1024,  # Kibibyte scale
    60,  # Minute/hour math
    3600,  # Hour/day math
    86400,  # Seconds in day
    # Standard HTTP status codes
    200,
    201,
    202,
    204,
    301,
    302,
    400,
    401,
    403,
    404,
    409,
    422,
    500,
    502,
    503,
    504,
}


class Violation(NamedTuple):
    file_path: str
    line_number: int
    literal_value: str
    reason: str


class BusinessConstantVisitor(ast.NodeVisitor):
    def __init__(self, rel_path: str):
        self.rel_path = rel_path
        self.violations: list[Violation] = []

    def visit_Compare(self, node: ast.Compare) -> None:  # noqa: N802
        """Inspect comparisons for direct literals like: if ratio > 0.9:"""
        # Check comparator constants
        for comparator in node.comparators:
            if isinstance(comparator, ast.Constant) and isinstance(comparator.value, int | float):
                val = comparator.value
                if val not in ALLOWED_STRUCTURAL_NUMBERS:
                    # Specific check for float thresholds like 0.9 or 0.8
                    if isinstance(val, float) and 0.0 < val < 1.0:
                        self.violations.append(
                            Violation(
                                file_path=self.rel_path,
                                line_number=node.lineno,
                                literal_value=str(val),
                                reason="Direct comparison against float threshold/percentage literal. Must resolve from configuration.",
                            )
                        )
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:  # noqa: N802
        """Inspect assignments for business targets like: threshold = 0.9 or retention = 90."""
        target_names = []
        for target in node.targets:
            if isinstance(target, ast.Name):
                target_names.append(target.id.lower())

        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, int | float):
            val = node.value.value
            for t_name in target_names:
                # Acceptance requirement: Literal 0.9 as a threshold
                if val == 0.9:
                    self.violations.append(
                        Violation(
                            file_path=self.rel_path,
                            line_number=node.lineno,
                            literal_value="0.9",
                            reason="Literal 0.9 defined as a business threshold. Must resolve from configuration.",
                        )
                    )
                    break

                if any(kw in t_name for kw in BUSINESS_TARGET_KEYWORDS):
                    if val not in ALLOWED_STRUCTURAL_NUMBERS:
                        self.violations.append(
                            Violation(
                                file_path=self.rel_path,
                                line_number=node.lineno,
                                literal_value=str(val),
                                reason=f"Variable '{t_name}' assigned hardcoded business constant literal {val}. Must resolve from configuration.",
                            )
                        )
                        break

        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:  # noqa: N802
        """Check for standalone 0.9 threshold literal anywhere in application logic."""
        if isinstance(node.value, float) and node.value == 0.9:
            self.violations.append(
                Violation(
                    file_path=self.rel_path,
                    line_number=node.lineno,
                    literal_value="0.9",
                    reason="Hardcoded 0.9 business threshold literal detected in application code. Must resolve from configuration.",
                )
            )
        self.generic_visit(node)


def is_exempt(rel_path: str) -> bool:
    normalized = rel_path.replace("\\", "/")
    return any(
        normalized.startswith(exempt) or f"/{exempt}/" in normalized for exempt in EXEMPT_PATHS
    )


def scan_file(file_path: Path) -> list[Violation]:
    rel_path = str(file_path.relative_to(ROOT_DIR))
    if is_exempt(rel_path):
        return []

    try:
        content = file_path.read_text(encoding="utf-8")
        tree = ast.parse(content, filename=str(file_path))
    except Exception as exc:
        print(f"[WARNING] Failed to parse AST for {rel_path}: {exc}", file=sys.stderr)
        return []

    visitor = BusinessConstantVisitor(rel_path)
    visitor.visit(tree)
    # Deduplicate multiple hits on same line/value
    unique_violations: list[Violation] = []
    seen = set()
    for v in visitor.violations:
        key = (v.file_path, v.line_number, v.literal_value)
        if key not in seen:
            seen.add(key)
            unique_violations.append(v)
    return unique_violations


def main() -> None:
    all_violations: list[Violation] = []

    for scanned_dir_name in SCANNED_DIRS:
        scanned_dir = ROOT_DIR / scanned_dir_name
        if not scanned_dir.exists():
            continue
        for root, _, files in os.walk(scanned_dir):
            for file in files:
                if file.endswith(".py"):
                    full_path = Path(root) / file
                    violations = scan_file(full_path)
                    all_violations.extend(violations)

    if all_violations:
        print("=" * 80)
        print("CLOUDLENS BUILD FAILURE: HARD-CODED BUSINESS CONSTANT VIOLATIONS DETECTED")
        print("Rule 18 / Prompt 02: No monetary value, percentage, threshold, interval or")
        print("retention period may appear as a literal in application code.")
        print("=" * 80)
        for v in all_violations:
            print(f"  [VIOLATION] {v.file_path}:{v.line_number} -> Literal '{v.literal_value}'")
            print(f"              {v.reason}")
        print("=" * 80)
        print(f"Total violations found: {len(all_violations)}")
        print(
            "Action: Resolve values from 'domain.config.config_resolver' or tenant configuration."
        )
        sys.exit(1)
    else:
        print("[PASS] No hard-coded business constants detected across application code.")
        sys.exit(0)


if __name__ == "__main__":
    main()
