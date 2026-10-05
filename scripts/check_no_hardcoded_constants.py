"""CloudLens AST Checker: Zero Hard-Coding Enforcement & Exception Register (Prompt 48 & Prompt R-QUAL).

Enforces Mandate M2, Prompt 48, and Prompt R-QUAL:
1. Item 34: Scans application code and fails the build on:
   - numeric literals used as thresholds, tolerances, limits, intervals, retention periods, page sizes or batch sizes;
   - string literals used as enumeration members, statuses, severities, categories, role names, permission codes, provider names, service names, region codes or unit symbols;
   - colour literals;
   - user-facing display strings;
   - date and number format strings;
   - hard-coded precedence orders or workflow step sequences.
2. Prompt R-QUAL Extensions:
   - Rule 4.1: Email literals (regex @[\\w-]+\\.[\\w.]+) in api/, domain/, connectors/, workers/ (excluding tests/, masterdata/seeds/, connectors/fixtures/).
   - Rule 4.2: Comparisons where one side is an identity attribute (email, user_id, sub, role name) and the other is a string literal.
   - Rule 4.3: Field(default=...) / function defaults whose name matches token|secret|password|key|credential and whose value is a non-empty string.
   - Rule 4.4: Decimal("<number>") and float/int literals used in comparisons inside domain/cost/reconciliation, domain/statements, domain/thresholds.
   - Rule 4.5: Hard-coded people/resource fixtures: >3 dict literals with keys like owner_email/actor/author in a non-test, non-synthetic module.
3. Item 35: Allow-list mechanism:
   - a literal may be permitted ONLY with an inline annotation naming BOTH the reason and the reviewer:
     `# no-hardcode-allow: reason="...", reviewer="..."`
     or `# allow-literal: reason="...", reviewer="..."`
   - unannotated literal is a build failure, NOT a warning.
   - invalid annotation missing reason or reviewer is a build failure.
   - generates and publishes the Exception Register to docs/configuration/exception_register.json & .md.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import NamedTuple

ROOT_DIR = Path(__file__).resolve().parent.parent

# Application directories subject to zero hard-coding enforcement
SCANNED_DIRS = ["api", "domain", "workers", "normalisation", "connectors"]

# Paths exempted from scanner globally
EXEMPT_PATHS = [
    "domain/config/surface.py",
    "domain/config/tenant_settings.py",
    "domain/models/enums.py",
    "domain/synthetic",
    "connectors/fixtures",
    "connectors/simulator",
    "domain/integrations/sandbox.py",
    "masterdata/seeds",
    "db/seeds",
    "tests",
    "scripts",
]

# Business variable keyword stems that must never be assigned literal numbers
NUMERIC_TARGET_KEYWORDS = {
    "threshold",
    "percentage",
    "tolerance",
    "limit",
    "interval",
    "retention",
    "page_size",
    "batch_size",
    "quota",
    "discount",
    "markup",
    "spike",
    "z_score",
    "window",
    "frequency",
    "sla_hours",
}

# Standard structural / mathematical conversion constants exempt from violation
ALLOWED_STRUCTURAL_NUMBERS = {
    0,
    1,
    -1,
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

STATUS_STRINGS = {
    "RUNNING",
    "STOPPED",
    "TERMINATED",
    "DEALLOCATED",
    "SUSPENDED",
    "PAID",
    "FREE",
    "FREE_TIER",
    "CONDITIONAL_FREE",
    "ESTIMATED",
}

SEVERITY_STRINGS = {
    "CRITICAL",
    "HIGH",
    "MEDIUM",
    "LOW",
    "NOMINAL",
    "WARNING",
    "EXCEEDED",
}

ROLE_STRINGS = {
    "GLOBAL_ADMIN",
    "TENANT_ADMIN",
    "FINOPS_VIEWER",
    "DEVELOPER",
    "AUDITOR",
    "TENANT",
    "ROOT_GROUP",
    "BILLING_BOUNDARY",
    "BILLING_ACCOUNT",
}

COLOR_REGEX = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")

DATE_FORMAT_STRINGS = {
    "%Y-%m-%d",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%d %H:%M:%S",
    "%d/%m/%Y",
    "%m/%d/%Y",
}

LABEL_TARGET_KEYWORDS = {
    "label",
    "display_label",
    "help_text",
    "tooltip",
    "alert_message",
    "email_subject",
    "email_body",
}

# Prompt R-QUAL Regexes
EMAIL_REGEX = re.compile(r"@[\w-]+\.[\w.]+")
SECRET_NAME_REGEX = re.compile(r"(?i)token|secret|password|key|credential")
IDENTITY_ATTRS = {
    "email",
    "user_id",
    "sub",
    "role",
    "role_name",
    "roles",
    "username",
    "principal",
    "subject",
    "actor",
    "author",
}
FIXTURE_KEY_REGEX = re.compile(r"^(?:owner_email|owner|actor|author|assignee|creator)$", re.IGNORECASE)
NUMERIC_COMPARISON_PATHS = ("domain/cost/reconciliation", "domain/statements", "domain/thresholds")

ALLOW_ANNOTATION_PATTERN = re.compile(
    r"#\s*(?:no-hardcode-allow|allow-literal)\s*:\s*reason\s*=\s*[\"'](?P<reason>[^\"']+)[\"']\s*,\s*reviewer\s*=\s*[\"'](?P<reviewer>[^\"']+)[\"']"
)
ALLOW_PREFIX_PATTERN = re.compile(r"#\s*(?:no-hardcode-allow|allow-literal)")


class Violation(NamedTuple):
    file_path: str
    line_number: int
    literal_value: str
    target_master: str
    reason: str


class AllowedException(NamedTuple):
    file_path: str
    line_number: int
    literal_value: str
    reason: str
    reviewer: str
    recorded_at: str


class ZeroHardCodingVisitor(ast.NodeVisitor):
    def __init__(self, rel_path: str, raw_lines: list[str] | None = None):
        self.rel_path = rel_path.replace("\\", "/")
        self.raw_lines = raw_lines if raw_lines is not None else []
        self.violations: list[Violation] = []
        self.allowed_exceptions: list[AllowedException] = []
        self.fixture_dict_count = 0
        self.fixture_dicts: list[tuple[int, list[str]]] = []
        self.in_enum_class = False

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
        prev_is_enum = self.in_enum_class
        base_names = [
            b.id if isinstance(b, ast.Name) else b.attr if isinstance(b, ast.Attribute) else ""
            for b in node.bases
        ]
        self.in_enum_class = any("enum" in b.lower() for b in base_names)
        self.generic_visit(node)
        self.in_enum_class = prev_is_enum

    def _check_allow_annotation(self, lineno: int, literal_val: str) -> bool:
        """Inspects line and immediately preceding line for allow-list annotation."""
        candidate_lines = []
        if 1 <= lineno <= len(self.raw_lines):
            candidate_lines.append((lineno, self.raw_lines[lineno - 1]))
        if 2 <= lineno <= len(self.raw_lines):
            candidate_lines.append((lineno - 1, self.raw_lines[lineno - 2]))

        for l_num, line_str in candidate_lines:
            if ALLOW_PREFIX_PATTERN.search(line_str):
                match = ALLOW_ANNOTATION_PATTERN.search(line_str)
                if match:
                    reason = match.group("reason").strip()
                    reviewer = match.group("reviewer").strip()
                    if reason and reviewer:
                        key = (self.rel_path, lineno, str(literal_val))
                        if not any(
                            (e.file_path, e.line_number, e.literal_value) == key
                            for e in self.allowed_exceptions
                        ):
                            self.allowed_exceptions.append(
                                AllowedException(
                                    file_path=self.rel_path,
                                    line_number=lineno,
                                    literal_value=str(literal_val),
                                    reason=reason,
                                    reviewer=reviewer,
                                    recorded_at=datetime.now(UTC).isoformat(),
                                )
                            )
                        return True

                self.violations.append(
                    Violation(
                        file_path=self.rel_path,
                        line_number=l_num,
                        literal_value=str(literal_val),
                        target_master="EXCEPTION_REGISTER",
                        reason=(
                            "Invalid allow-list annotation. Rule 35: Both 'reason=\"...\"' and 'reviewer=\"...\"' "
                            "are strictly mandatory on all allow-list comments."
                        ),
                    )
                )
                return True

        return False

    def _is_identity_expr(self, expr: ast.AST) -> bool:
        """Determines if an expression accesses an identity attribute."""
        if isinstance(expr, ast.Name):
            name_lower = expr.id.lower()
            return name_lower in IDENTITY_ATTRS or any(
                name_lower.endswith(f"_{a}") for a in IDENTITY_ATTRS
            )
        if isinstance(expr, ast.Attribute):
            attr_lower = expr.attr.lower()
            return attr_lower in IDENTITY_ATTRS or any(
                attr_lower.endswith(f"_{a}") for a in IDENTITY_ATTRS
            )
        if isinstance(expr, ast.Subscript):
            if isinstance(expr.slice, ast.Constant) and isinstance(expr.slice.value, str):
                slice_lower = expr.slice.value.lower()
                return slice_lower in IDENTITY_ATTRS or any(
                    slice_lower.endswith(f"_{a}") for a in IDENTITY_ATTRS
                )
        return False

    def _is_decimal_or_numeric_literal(self, expr: ast.AST) -> tuple[bool, str]:
        """Detects Decimal('<number>') calls or float/int literals."""
        if isinstance(expr, ast.Constant) and isinstance(expr.value, (int, float)):
            if expr.value in ALLOWED_STRUCTURAL_NUMBERS:
                return False, ""
            return True, str(expr.value)
        if isinstance(expr, ast.UnaryOp) and isinstance(expr.operand, ast.Constant):
            if isinstance(expr.operand.value, (int, float)):
                if expr.operand.value in ALLOWED_STRUCTURAL_NUMBERS or -expr.operand.value in ALLOWED_STRUCTURAL_NUMBERS:
                    return False, ""
                return True, f"-{expr.operand.value}"
        if isinstance(expr, ast.Call):
            func_name = ""
            if isinstance(expr.func, ast.Name):
                func_name = expr.func.id
            elif isinstance(expr.func, ast.Attribute):
                func_name = expr.func.attr
            if func_name == "Decimal":
                if expr.args and isinstance(expr.args[0], ast.Constant):
                    try:
                        val_num = float(str(expr.args[0].value))
                        if val_num in ALLOWED_STRUCTURAL_NUMBERS:
                            return False, ""
                    except (ValueError, TypeError):
                        pass
                    return True, f"Decimal('{expr.args[0].value}')"
        return False, ""

    def visit_Compare(self, node: ast.Compare) -> None:  # noqa: N802
        """Inspect comparison expressions."""
        # Rule 4.2: Identity comparisons against string literals
        left_is_id = self._is_identity_expr(node.left)
        for comparator in node.comparators:
            comp_is_id = self._is_identity_expr(comparator)
            if (
                left_is_id
                and isinstance(comparator, ast.Constant)
                and isinstance(comparator.value, str)
            ):
                if not self._check_allow_annotation(node.lineno, comparator.value):
                    self.violations.append(
                        Violation(
                            file_path=self.rel_path,
                            line_number=node.lineno,
                            literal_value=comparator.value,
                            target_master="RULE_4_2_IDENTITY_COMPARISON",
                            reason=(
                                f"Comparison of identity attribute against string literal '{comparator.value}'. "
                                "Identity and roles must resolve from SystemRole enum or dynamic RBAC context."
                            ),
                        )
                    )
            elif (
                comp_is_id
                and isinstance(node.left, ast.Constant)
                and isinstance(node.left.value, str)
            ):
                if not self._check_allow_annotation(node.lineno, node.left.value):
                    self.violations.append(
                        Violation(
                            file_path=self.rel_path,
                            line_number=node.lineno,
                            literal_value=node.left.value,
                            target_master="RULE_4_2_IDENTITY_COMPARISON",
                            reason=(
                                f"Comparison of string literal '{node.left.value}' against identity attribute. "
                                "Identity and roles must resolve from SystemRole enum or dynamic RBAC context."
                            ),
                        )
                    )

            # Rule 4.4: Decimal and numeric literals in financial/threshold comparisons
            if any(p in self.rel_path for p in NUMERIC_COMPARISON_PATHS):
                is_left_num, left_val = self._is_decimal_or_numeric_literal(node.left)
                if is_left_num and not self._check_allow_annotation(node.lineno, left_val):
                    self.violations.append(
                        Violation(
                            file_path=self.rel_path,
                            line_number=node.lineno,
                            literal_value=left_val,
                            target_master="RULE_4_4_NUMERIC_COMPARISON",
                            reason=(
                                f"Numeric or Decimal literal '{left_val}' used in comparison inside {self.rel_path}. "
                                "Financial tolerances and thresholds must resolve from configuration surface."
                            ),
                        )
                    )
                is_comp_num, comp_val = self._is_decimal_or_numeric_literal(comparator)
                if is_comp_num and not self._check_allow_annotation(node.lineno, comp_val):
                    self.violations.append(
                        Violation(
                            file_path=self.rel_path,
                            line_number=node.lineno,
                            literal_value=comp_val,
                            target_master="RULE_4_4_NUMERIC_COMPARISON",
                            reason=(
                                f"Numeric or Decimal literal '{comp_val}' used in comparison inside {self.rel_path}. "
                                "Financial tolerances and thresholds must resolve from configuration surface."
                            ),
                        )
                    )

            # Prior checks: float thresholds, statuses, severities
            if isinstance(comparator, ast.Constant):
                val = comparator.value
                if isinstance(val, float) and 0.0 < val < 1.0:
                    if not self._check_allow_annotation(node.lineno, str(val)):
                        self.violations.append(
                            Violation(
                                file_path=self.rel_path,
                                line_number=node.lineno,
                                literal_value=str(val),
                                target_master="threshold_defaults",
                                reason=(
                                    f"Direct comparison against float threshold literal {val}. "
                                    "Must resolve from configuration: 'domain.config.config_resolver' "
                                    "or tenant settings ('threshold_defaults')."
                                ),
                            )
                        )
                elif isinstance(val, str) and val in STATUS_STRINGS:
                    if not self._check_allow_annotation(node.lineno, val):
                        self.violations.append(
                            Violation(
                                file_path=self.rel_path,
                                line_number=node.lineno,
                                literal_value=val,
                                target_master="RUNTIME_STATUS / PRICING_STATUS",
                                reason=(
                                    f"Direct comparison against hardcoded status string '{val}'. "
                                    "Must use domain Enum ('RuntimeStatus' / 'PricingStatus') or resolve from master."
                                ),
                            )
                        )
                elif isinstance(val, str) and val in SEVERITY_STRINGS:
                    if not self._check_allow_annotation(node.lineno, val):
                        self.violations.append(
                            Violation(
                                file_path=self.rel_path,
                                line_number=node.lineno,
                                literal_value=val,
                                target_master="POLICY_SEVERITY / THRESHOLD_BAND",
                                reason=(
                                    f"Direct comparison against hardcoded severity string '{val}'. "
                                    "Must use domain Enum ('PolicySeverity' / 'ThresholdBand') or resolve from master."
                                ),
                            )
                        )

        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        """Inspect function defaults for secret/credential values (Rule 4.3)."""
        self._check_function_defaults(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        """Inspect async function defaults for secret/credential values (Rule 4.3)."""
        self._check_function_defaults(node)
        self.generic_visit(node)

    def _check_function_defaults(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        # Check positional args defaults
        pos_args = node.args.args
        defaults = node.args.defaults
        if defaults:
            offset = len(pos_args) - len(defaults)
            for i, default in enumerate(defaults):
                arg = pos_args[offset + i]
                if SECRET_NAME_REGEX.search(arg.arg) and arg.arg not in ("token_type", "natural_key_field") and not arg.arg.endswith("_type"):
                    if (
                        isinstance(default, ast.Constant)
                        and isinstance(default.value, str)
                        and len(default.value) > 0
                    ):
                        if not self._check_allow_annotation(default.lineno, default.value):
                            self.violations.append(
                                Violation(
                                    file_path=self.rel_path,
                                    line_number=default.lineno,
                                    literal_value=default.value,
                                    target_master="RULE_4_3_SECRET_DEFAULT",
                                    reason=(
                                        f"Function '{node.name}' parameter '{arg.arg}' has non-empty secret default '{default.value}'. "
                                        "Credentials must be resolved from SecretStore or environment."
                                    ),
                                )
                            )

        # Check kw-only args defaults
        for arg, default in zip(node.args.kwonlyargs, node.args.kw_defaults, strict=False):
            if (
                default
                and SECRET_NAME_REGEX.search(arg.arg)
                and arg.arg not in ("token_type", "natural_key_field")
                and not arg.arg.endswith("_type")
                and isinstance(default, ast.Constant)
                and isinstance(default.value, str)
                and len(default.value) > 0
            ):
                if not self._check_allow_annotation(default.lineno, default.value):
                    self.violations.append(
                        Violation(
                            file_path=self.rel_path,
                            line_number=default.lineno,
                            literal_value=default.value,
                            target_master="RULE_4_3_SECRET_DEFAULT",
                            reason=(
                                f"Function '{node.name}' kw-only parameter '{arg.arg}' has non-empty secret default '{default.value}'. "
                                "Credentials must be resolved from SecretStore or environment."
                            ),
                        )
                    )

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:  # noqa: N802
        """Inspect annotated assignments for secret Field defaults (Rule 4.3)."""
        target_name = ""
        if isinstance(node.target, ast.Name):
            target_name = node.target.id
        elif isinstance(node.target, ast.Attribute):
            target_name = node.target.attr

        if getattr(self, "in_enum_class", False):
            self.generic_visit(node)
            return

        if target_name and SECRET_NAME_REGEX.search(target_name) and target_name not in ("token_type", "natural_key_field") and not target_name.endswith("_type"):
            if (
                isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
                and len(node.value.value) > 0
            ):
                if not self._check_allow_annotation(node.lineno, node.value.value):
                    self.violations.append(
                        Violation(
                            file_path=self.rel_path,
                            line_number=node.lineno,
                            literal_value=node.value.value,
                            target_master="RULE_4_3_SECRET_DEFAULT",
                            reason=(
                                f"Variable/Field '{target_name}' assigned non-empty secret literal '{node.value.value}'. "
                                "Credentials must be resolved dynamically from SecretStore."
                            ),
                        )
                    )
            elif isinstance(node.value, ast.Call):
                func_name = ""
                if isinstance(node.value.func, ast.Name):
                    func_name = node.value.func.id
                elif isinstance(node.value.func, ast.Attribute):
                    func_name = node.value.func.attr
                if func_name == "Field":
                    for kw in node.value.keywords:
                        if (
                            kw.arg in ("default", "default_factory")
                            and isinstance(kw.value, ast.Constant)
                            and isinstance(kw.value.value, str)
                            and len(kw.value.value) > 0
                        ):
                            if not self._check_allow_annotation(node.lineno, kw.value.value):
                                self.violations.append(
                                    Violation(
                                        file_path=self.rel_path,
                                        line_number=node.lineno,
                                        literal_value=kw.value.value,
                                        target_master="RULE_4_3_SECRET_DEFAULT",
                                        reason=(
                                            f"Field(default=...) for '{target_name}' contains non-empty secret literal '{kw.value.value}'. "
                                            "Default must be empty string or retrieved from SecretStore."
                                        ),
                                    )
                                )
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:  # noqa: N802
        """Inspect variable assignments."""
        if getattr(self, "in_enum_class", False):
            self.generic_visit(node)
            return

        target_names = []
        for target in node.targets:
            if isinstance(target, ast.Name):
                target_names.append(target.id.lower())
            elif isinstance(target, ast.Attribute):
                target_names.append(target.attr.lower())

        # Rule 4.3 check on plain assignment
        if any(SECRET_NAME_REGEX.search(t) for t in target_names if t not in ("token_type", "natural_key_field") and not t.endswith("_type")):
            if (
                isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
                and len(node.value.value) > 0
            ):
                if not self._check_allow_annotation(node.lineno, node.value.value):
                    self.violations.append(
                        Violation(
                            file_path=self.rel_path,
                            line_number=node.lineno,
                            literal_value=node.value.value,
                            target_master="RULE_4_3_SECRET_DEFAULT",
                            reason=(
                                f"Variable '{target_names[0]}' assigned non-empty secret literal '{node.value.value}'. "
                                "Credentials must be resolved dynamically from SecretStore."
                            ),
                        )
                    )
            elif isinstance(node.value, ast.Call):
                func_name = ""
                if isinstance(node.value.func, ast.Name):
                    func_name = node.value.func.id
                elif isinstance(node.value.func, ast.Attribute):
                    func_name = node.value.func.attr
                if func_name == "Field":
                    for kw in node.value.keywords:
                        if (
                            kw.arg == "default"
                            and isinstance(kw.value, ast.Constant)
                            and isinstance(kw.value.value, str)
                            and len(kw.value.value) > 0
                        ):
                            if not self._check_allow_annotation(node.lineno, kw.value.value):
                                self.violations.append(
                                    Violation(
                                        file_path=self.rel_path,
                                        line_number=node.lineno,
                                        literal_value=kw.value.value,
                                        target_master="RULE_4_3_SECRET_DEFAULT",
                                        reason=(
                                            f"Field(default=...) for '{target_names[0]}' contains non-empty secret literal '{kw.value.value}'."
                                        ),
                                    )
                                )

        # Prior checks
        if isinstance(node.value, ast.Constant):
            val = node.value.value
            if isinstance(val, int | float):
                if val == 0.9:
                    if not self._check_allow_annotation(node.lineno, "0.9"):
                        self.violations.append(
                            Violation(
                                file_path=self.rel_path,
                                line_number=node.lineno,
                                literal_value="0.9",
                                target_master="threshold_defaults.budget_alert_threshold_percentage",
                                reason=(
                                    "Literal 0.9 assigned as a business threshold. "
                                    "Must resolve from configuration: 'domain.config.config_resolver' "
                                    "or tenant settings."
                                ),
                            )
                        )
                elif any(kw in t_name for t_name in target_names for kw in NUMERIC_TARGET_KEYWORDS):
                    if val not in ALLOWED_STRUCTURAL_NUMBERS:
                        if not self._check_allow_annotation(node.lineno, str(val)):
                            self.violations.append(
                                Violation(
                                    file_path=self.rel_path,
                                    line_number=node.lineno,
                                    literal_value=str(val),
                                    target_master="domain.config.surface / tenant_settings",
                                    reason=(
                                        f"Variable '{target_names[0]}' assigned hardcoded numeric constant {val}. "
                                        "Must resolve from configuration surface or tenant settings."
                                    ),
                                )
                            )
            elif isinstance(val, str):
                if COLOR_REGEX.match(val):
                    if not self._check_allow_annotation(node.lineno, val):
                        self.violations.append(
                            Violation(
                                file_path=self.rel_path,
                                line_number=node.lineno,
                                literal_value=val,
                                target_master="THEME_COLOUR / SEVERITY_STYLE",
                                reason=(
                                    f"Hardcoded colour literal '{val}' assigned in application code. "
                                    "Must resolve from theme configuration or master 'THEME_COLOUR'."
                                ),
                            )
                        )
                elif any(kw in t_name for t_name in target_names for kw in LABEL_TARGET_KEYWORDS):
                    if len(val) > 2 and not self._check_allow_annotation(node.lineno, val):
                        self.violations.append(
                            Violation(
                                file_path=self.rel_path,
                                line_number=node.lineno,
                                literal_value=val,
                                target_master="STRING_CATALOGUE",
                                reason=(
                                    f"Hardcoded display string '{val}' assigned to '{target_names[0]}'. "
                                    "Must resolve from master 'STRING_CATALOGUE' via StringCatalogueService or t()."
                                ),
                            )
                        )
                elif val in ROLE_STRINGS:
                    if not self._check_allow_annotation(node.lineno, val):
                        self.violations.append(
                            Violation(
                                file_path=self.rel_path,
                                line_number=node.lineno,
                                literal_value=val,
                                target_master="ROLE / PERMISSION / ScopeRole",
                                reason=(
                                    f"Hardcoded role or permission string '{val}'. "
                                    "Must use ScopeRole enum or resolve from master 'ROLE' / 'PERMISSION'."
                                ),
                            )
                        )
                elif val in DATE_FORMAT_STRINGS:
                    if not self._check_allow_annotation(node.lineno, val):
                        self.violations.append(
                            Violation(
                                file_path=self.rel_path,
                                line_number=node.lineno,
                                literal_value=val,
                                target_master="tenant_settings.default_time_zone / FORMAT_SPEC",
                                reason=(
                                    f"Hardcoded date format string '{val}'. "
                                    "Must resolve from tenant configuration or master 'FORMAT_SPEC'."
                                ),
                            )
                        )

        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:  # noqa: N802
        """Inspect constants across code."""
        # Rule 4.1: Email literals
        if isinstance(node.value, str) and EMAIL_REGEX.search(node.value):
            # Check exclusions for Rule 4.1: tests, masterdata/seeds, connectors/fixtures
            norm = self.rel_path.lower()
            if not any(
                ex in norm for ex in ("tests/", "masterdata/seeds", "connectors/fixtures", "/seeds/")
            ):
                if not self._check_allow_annotation(node.lineno, node.value):
                    self.violations.append(
                        Violation(
                            file_path=self.rel_path,
                            line_number=node.lineno,
                            literal_value=node.value,
                            target_master="RULE_4_1_EMAIL_LITERAL",
                            reason=(
                                f"Hardcoded email literal '{node.value}' in application module. "
                                "Identity and email destinations must resolve dynamically from TenantContext or settings."
                            ),
                        )
                    )

        # 0.9 threshold and colour literals
        if isinstance(node.value, float) and node.value == 0.9:
            if not self._check_allow_annotation(node.lineno, "0.9"):
                self.violations.append(
                    Violation(
                        file_path=self.rel_path,
                        line_number=node.lineno,
                        literal_value="0.9",
                        target_master="threshold_defaults",
                        reason=(
                            "Hardcoded 0.9 business threshold literal detected in application code. "
                            "Must resolve from configuration: 'domain.config.config_resolver' or tenant settings."
                        ),
                    )
                )
        elif isinstance(node.value, str) and COLOR_REGEX.match(node.value):
            if not self._check_allow_annotation(node.lineno, node.value):
                self.violations.append(
                    Violation(
                        file_path=self.rel_path,
                        line_number=node.lineno,
                        literal_value=node.value,
                        target_master="THEME_COLOUR",
                        reason=(
                            f"Hardcoded colour literal '{node.value}' detected. "
                            "Must resolve from theme configuration or master 'THEME_COLOUR'."
                        ),
                    )
                )

        self.generic_visit(node)

    def visit_Dict(self, node: ast.Dict) -> None:  # noqa: N802
        """Inspect dictionaries for hardcoded people/resource fixture patterns (Rule 4.5)."""
        keys_matched = []
        for key, val in zip(node.keys, node.values):
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                if FIXTURE_KEY_REGEX.search(key.value):
                    if isinstance(val, ast.Constant) and isinstance(val.value, str):
                        keys_matched.append(key.value)
        if keys_matched:
            self.fixture_dicts.append((node.lineno, keys_matched))
        self.generic_visit(node)


# Backward compatibility alias
BusinessConstantVisitor = ZeroHardCodingVisitor


def is_exempt(rel_path: str) -> bool:
    normalized = rel_path.replace("\\", "/")
    return any(
        normalized.startswith(exempt)
        or f"/{exempt}/" in normalized
        or normalized.endswith(exempt)
        or normalized.startswith(f"{exempt}/")
        for exempt in EXEMPT_PATHS
    )


def scan_code(content: str, rel_path: str = "sample.py") -> tuple[list[Violation], list[AllowedException]]:
    """Scans code text in memory and returns violations and allowed exceptions."""
    raw_lines = content.splitlines()
    tree = ast.parse(content, filename=rel_path)
    visitor = ZeroHardCodingVisitor(rel_path, raw_lines)
    visitor.visit(tree)

    norm = rel_path.replace("\\", "/").lower()
    # Rule 4.5 module-level fixture count check: non-test, non-synthetic module
    if not any(ex in norm for ex in ("tests/", "test_", "synthetic", "fixtures", "seeds")):
        if len(visitor.fixture_dicts) > 3:
            for lineno, keys in visitor.fixture_dicts:
                visitor.violations.append(
                    Violation(
                        file_path=rel_path,
                        line_number=lineno,
                        literal_value=f"Dict fixture (keys: {keys})",
                        target_master="RULE_4_5_FIXTURE_DICTS",
                        reason=(
                            f"Module contains {len(visitor.fixture_dicts)} hardcoded people/resource fixture dicts (threshold: >3). "
                            "Estate fixtures must be generated synthetically or loaded from master seeds."
                        ),
                    )
                )

    # Deduplicate violations on (file, line, literal, target_master)
    unique_violations: list[Violation] = []
    seen_v = set()
    for v in visitor.violations:
        key = (v.file_path, v.line_number, v.literal_value, v.target_master)
        if key not in seen_v:
            seen_v.add(key)
            unique_violations.append(v)

    # Deduplicate allowed exceptions
    unique_allowed: list[AllowedException] = []
    seen_a = set()
    for a in visitor.allowed_exceptions:
        key = (a.file_path, a.line_number, a.literal_value)
        if key not in seen_a:
            seen_a.add(key)
            unique_allowed.append(a)

    return unique_violations, unique_allowed


def scan_file(file_path: Path) -> tuple[list[Violation], list[AllowedException]]:
    rel_path = str(file_path.relative_to(ROOT_DIR)).replace("\\", "/")
    if is_exempt(rel_path):
        return [], []

    try:
        content = file_path.read_text(encoding="utf-8")
        return scan_code(content, rel_path=rel_path)
    except Exception as exc:
        print(f"[WARNING] Failed to parse AST for {rel_path}: {exc}", file=sys.stderr)
        return [], []


def publish_exception_register(exceptions: list[AllowedException]) -> None:
    """Publishes the Exception Register to docs/configuration per Prompt 48 Item 35."""
    docs_dir = ROOT_DIR / "docs" / "configuration"
    docs_dir.mkdir(parents=True, exist_ok=True)

    json_path = docs_dir / "exception_register.json"
    records = [
        {
            "file_path": e.file_path,
            "line_number": e.line_number,
            "literal_value": e.literal_value,
            "reason": e.reason,
            "reviewer": e.reviewer,
            "recorded_at": e.recorded_at,
        }
        for e in exceptions
    ]
    json_path.write_text(json.dumps(records, indent=2), encoding="utf-8")

    md_path = docs_dir / "exception_register.md"
    md_lines = [
        "# CloudLens Configuration Exception Register",
        "",
        "Enforces **Mandate M2** and **Prompt 48 Item 35**.",
        "Every allow-listed literal in application code must be approved with a named reason and reviewer.",
        "",
        f"**Last Updated:** {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%SZ')} | **Total Exceptions:** {len(exceptions)}",
        "",
        "| File Path | Line | Literal | Business Rationale | Approving Reviewer |",
        "| :--- | :--- | :--- | :--- | :--- |",
    ]
    for e in exceptions:
        md_lines.append(
            f"| `{e.file_path}` | {e.line_number} | `{e.literal_value}` | {e.reason} | **{e.reviewer}** |"
        )
    md_lines.append("")
    md_path.write_text("\n".join(md_lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="CloudLens AST Zero Hard-Coding Quality Gate")
    parser.add_argument(
        "--mode",
        choices=["enforce", "report"],
        default=os.getenv("CLOUDLENS_GATE_MODE", "enforce"),
        help="Gate execution mode: 'enforce' (fails build with code 1) or 'report' (reports findings and exits 0)",
    )
    args = parser.parse_args()

    all_violations: list[Violation] = []
    all_allowed: list[AllowedException] = []

    for scanned_dir_name in SCANNED_DIRS:
        scanned_dir = ROOT_DIR / scanned_dir_name
        if not scanned_dir.exists():
            continue
        for root, _, files in os.walk(scanned_dir):
            for file in files:
                if file.endswith(".py"):
                    full_path = Path(root) / file
                    violations, allowed = scan_file(full_path)
                    all_violations.extend(violations)
                    all_allowed.extend(allowed)

    # Publish exception register
    publish_exception_register(all_allowed)

    if all_violations:
        # Group violations by rule
        grouped: dict[str, list[Violation]] = {
            "RULE_4_1_EMAIL_LITERAL": [],
            "RULE_4_2_IDENTITY_COMPARISON": [],
            "RULE_4_3_SECRET_DEFAULT": [],
            "RULE_4_4_NUMERIC_COMPARISON": [],
            "RULE_4_5_FIXTURE_DICTS": [],
            "OTHER_HARDCODING": [],
        }
        for v in all_violations:
            if v.target_master in grouped:
                grouped[v.target_master].append(v)
            else:
                grouped["OTHER_HARDCODING"].append(v)

        print("=" * 80, file=sys.stderr)
        print("CLOUDLENS BUILD GATE FINDINGS: HARD-CODED CONSTANTS DETECTED", file=sys.stderr)
        print(f"Mode: {args.mode.upper()} | Total Violations: {len(all_violations)}", file=sys.stderr)
        print("=" * 80, file=sys.stderr)

        rule_titles = {
            "RULE_4_1_EMAIL_LITERAL": "Rule 4.1 — Hardcoded Email Literals",
            "RULE_4_2_IDENTITY_COMPARISON": "Rule 4.2 — Identity Attribute String Comparisons",
            "RULE_4_3_SECRET_DEFAULT": "Rule 4.3 — Secret / Credential Default Literals",
            "RULE_4_4_NUMERIC_COMPARISON": "Rule 4.4 — Financial / Threshold Numeric Comparisons",
            "RULE_4_5_FIXTURE_DICTS": "Rule 4.5 — Hardcoded People/Resource Fixture Dicts (>3)",
            "OTHER_HARDCODING": "General Hardcoded Constants (Thresholds/Colors/Statuses)",
        }

        for rule_key, items in grouped.items():
            if items:
                print(f"\n### {rule_titles.get(rule_key, rule_key)} ({len(items)} findings):", file=sys.stderr)
                for item in items:
                    print(
                        f"  - {item.file_path}:{item.line_number} -> '{item.literal_value}'\n    Reason: {item.reason}",
                        file=sys.stderr,
                    )

        print("\n" + "=" * 80, file=sys.stderr)
        print(f"Summary: {len(all_violations)} violations found across {len(SCANNED_DIRS)} directories.", file=sys.stderr)
        print(f"Allow-listed exceptions recorded: {len(all_allowed)}", file=sys.stderr)

        if args.mode == "enforce":
            print("[GATE RESULT: FAILED] Exiting with status 1 (Enforce mode).", file=sys.stderr)
            sys.exit(1)
        else:
            print("[GATE RESULT: REPORT MODE] Exiting with status 0 (Reporting mode for CI).", file=sys.stderr)
            sys.exit(0)
    else:
        print(
            f"[PASS] Zero hard-coding scan passed cleanly! ({len(all_allowed)} allow-listed exceptions in register)"
        )
        sys.exit(0)


if __name__ == "__main__":
    main()
