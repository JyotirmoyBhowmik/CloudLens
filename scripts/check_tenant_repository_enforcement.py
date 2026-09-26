"""AST Static Analysis Checker: Repository Tenant Context Enforcement (Prompt 13 Item 84).

Enforces:
- "Require a tenant context in every repository method. Make a query without tenant
  context fail at build or test time rather than at runtime."
- Scans all repository classes extending TenantAwareRepository.
- Verifies that every public method requires a TenantContext parameter without a default value.
- Exits with status code 1 on any violation to fail CI/CD build gates mechanically.
"""

import ast
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent


def check_repository_file(file_path: Path) -> list[str]:
    """Inspects a Python repository file using AST for mandatory TenantContext parameters."""
    violations: list[str] = []
    try:
        with open(file_path, encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=str(file_path))
    except Exception as e:
        return [f"Failed to parse {file_path}: {e}"]

    # Identify classes extending TenantAwareRepository
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue

        is_tenant_repo = False
        for base in node.bases:
            base_id = ""
            if isinstance(base, ast.Name):
                base_id = base.id
            elif isinstance(base, ast.Subscript):
                if isinstance(base.value, ast.Name):
                    base_id = base.value.id
            elif isinstance(base, ast.Attribute):
                base_id = base.attr

            if "TenantAwareRepository" in base_id:
                is_tenant_repo = True
                break

        if not is_tenant_repo:
            continue

        # Inspect all functions/methods inside the class
        for item in node.body:
            if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            method_name = item.name
            # Skip private/internal helper methods and dunder methods
            if method_name.startswith("_"):
                continue

            # Check if any argument is annotated with TenantContext
            has_tenant_context = False
            is_required = True

            # Calculate defaults for positional args
            pos_args_without_defaults_count = len(item.args.args) - len(item.args.defaults)

            for idx, arg in enumerate(item.args.args):
                if arg.arg in ("self", "cls"):
                    continue
                type_name = _get_annotation_name(arg.annotation)
                if "TenantContext" in type_name:
                    has_tenant_context = True
                    # Check if it has a default
                    if idx >= pos_args_without_defaults_count:
                        is_required = False

            # Check kwonlyargs
            for idx, arg in enumerate(item.args.kwonlyargs):
                type_name = _get_annotation_name(arg.annotation)
                if "TenantContext" in type_name:
                    has_tenant_context = True
                    # Check if kw_defaults[idx] is None
                    if idx < len(item.args.kw_defaults) and item.args.kw_defaults[idx] is not None:
                        is_required = False

            if not has_tenant_context:
                violations.append(
                    f"{file_path.relative_to(ROOT_DIR)}:{item.lineno}: Method '{node.name}.{method_name}' "
                    f"lacks mandatory 'tenant_context: TenantContext' parameter (Prompt 13 Item 84)."
                )
            elif not is_required:
                violations.append(
                    f"{file_path.relative_to(ROOT_DIR)}:{item.lineno}: Method '{node.name}.{method_name}' "
                    f"makes 'tenant_context' optional. It must be a required parameter without default."
                )

    return violations


def _get_annotation_name(node: ast.AST | None) -> str:
    if node is None:
        return ""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Subscript):
        return _get_annotation_name(node.value)
    return ""


def main() -> int:
    """Scans all repository files in the workspace."""
    repo_files: list[Path] = []
    for root, _, files in os.walk(ROOT_DIR):
        # Skip .venv, node_modules, .git
        rel_root = os.path.relpath(root, ROOT_DIR)
        if any(ignored in rel_root for ignored in (".venv", "node_modules", ".git", "__pycache__")):
            continue
        for file in files:
            if file.endswith("repository.py") or file.endswith("repositories.py"):
                repo_files.append(Path(root) / file)

    all_violations: list[str] = []
    for f in repo_files:
        violations = check_repository_file(f)
        all_violations.extend(violations)

    if all_violations:
        print("\n" + "=" * 80)
        print("BUILD GATE FAILURE: Missing Tenant Context in Repositories (Prompt 13 Item 84)")
        print("=" * 80)
        for v in all_violations:
            print(f"  [X] {v}")
        print("=" * 80 + "\n")
        return 1

    print(
        "[OK] Tenant repository context enforcement: All repository methods require TenantContext."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
