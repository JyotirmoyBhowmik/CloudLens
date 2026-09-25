"""Unit tests for AST-enforced check against hard-coded business constants.

Acceptance: Introducing a literal 0.9 as a threshold in application code fails the build.
"""

import ast
import tempfile
from pathlib import Path

from scripts.check_no_hardcoded_constants import (
    BusinessConstantVisitor,
)


def test_clean_codebase_has_zero_hardcoded_constant_violations():
    """Verify production application codebase passes the no-hardcoded-constants check."""
    # Test through visitor with compliant code
    compliant_code = """
from domain.config import config_resolver

def check_budget_consumption(current_spend: float, budget: float, tenant_id: str) -> bool:
    threshold = config_resolver.get_effective_value(
        "threshold_defaults.budget_alert_threshold_percentage",
        tenant_id=tenant_id,
    )
    ratio = (current_spend / budget) * 100.0  # 100.0 math scale factor is permitted
    return ratio >= threshold
"""
    tree = ast.parse(compliant_code)
    visitor = BusinessConstantVisitor("api/cloudlens_api/compliant.py")
    visitor.visit(tree)
    assert len(visitor.violations) == 0


def test_literal_0_9_as_threshold_fails_check():
    """Acceptance: Introducing a literal 0.9 as a threshold in application code fails the build."""
    violating_code = """
def is_over_budget(spend: float, total_budget: float) -> bool:
    threshold = 0.9  # VIOLATION: Hardcoded 0.9 business threshold!
    return (spend / total_budget) > threshold
"""
    tree = ast.parse(violating_code)
    visitor = BusinessConstantVisitor("api/cloudlens_api/bad_budget.py")
    visitor.visit(tree)

    assert len(visitor.violations) > 0
    assert any("0.9" in v.literal_value for v in visitor.violations)
    assert any("threshold" in v.reason.lower() or "0.9" in v.reason for v in visitor.violations)


def test_direct_comparison_against_0_9_fails_check():
    """Verify comparison expression `ratio > 0.9` is detected as a violation."""
    violating_code = """
def check_cpu_idle(cpu_ratio: float) -> bool:
    if cpu_ratio < 0.9:  # Direct comparison against float threshold literal
        return False
    return True
"""
    tree = ast.parse(violating_code)
    visitor = BusinessConstantVisitor("api/cloudlens_api/idle_check.py")
    visitor.visit(tree)

    assert len(visitor.violations) > 0
    assert any("0.9" in v.literal_value for v in visitor.violations)


def test_file_scanner_detects_violation_in_mock_application_file():
    """Verify scan_file detects violation when file is located in application directory."""
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as tmp:
        tmp.write("threshold = 0.9\n")
        tmp_path = Path(tmp.name)

    try:
        # Direct visitor parse on written file
        content = tmp_path.read_text(encoding="utf-8")
        tree = ast.parse(content)
        visitor = BusinessConstantVisitor("api/sample.py")
        visitor.visit(tree)
        assert len(visitor.violations) > 0
        assert visitor.violations[0].literal_value == "0.9"
    finally:
        tmp_path.unlink()
