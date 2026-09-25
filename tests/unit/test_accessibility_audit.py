"""Unit tests for WCAG 2.1 AA Accessibility Audit script."""

import tempfile
from pathlib import Path

from scripts.check_accessibility import (
    check_component_accessibility,
    check_html_accessibility,
    run_accessibility_audit,
)


def test_production_web_passes_accessibility_audit():
    """Verify production web application passes WCAG 2.1 AA accessibility audit."""
    assert run_accessibility_audit() is True


def test_html_accessibility_violations_detected():
    """Verify HTML accessibility validator flags missing lang and forbidden viewport flags."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        bad_html = Path(tmp_dir) / "index.html"
        bad_html.write_text(
            "<html><head><meta name='viewport' content='user-scalable=no'></head><body></body></html>"
        )

        violations = check_html_accessibility(bad_html)
        assert len(violations) >= 2
        assert any("lang" in v for v in violations)
        assert any("user-scalable" in v for v in violations)
        assert any("title" in v for v in violations)


def test_component_accessibility_violations_detected():
    """Verify component validator flags missing alt on images and unlabelled buttons."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        bad_comp = Path(tmp_dir) / "Button.tsx"
        bad_comp.write_text(
            """
            export function BadComponent() {
                return (
                    <div>
                        <img src="/logo.png" />
                        <button><svg /></button>
                    </div>
                );
            }
            """
        )

        violations = check_component_accessibility(bad_comp)
        assert len(violations) == 2
        assert any("img" in v for v in violations)
        assert any("button" in v for v in violations)
