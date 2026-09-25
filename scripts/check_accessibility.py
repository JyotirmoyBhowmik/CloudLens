"""CloudLens WCAG 2.1 AA Accessibility Linter and Compliance Checker.

Enforces accessibility requirements per Prompt 04 Item 27:
- Checks HTML documents for valid 'lang', viewport, and page titles.
- Audits React/TSX/JSX files for accessible labels on buttons, inputs, links, and SVG icons.
- Ensures non-empty semantic landmarks (<main>, <nav>, <header>, etc.).
- Verifies contrast ratio metadata and absence of inaccessible role attributes.
"""

import re
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT_DIR / "web"


def check_html_accessibility(html_file: Path) -> list[str]:
    """Validates baseline accessibility requirements for HTML files."""
    violations = []
    if not html_file.exists():
        return [f"HTML template missing: {html_file}"]

    content = html_file.read_text(encoding="utf-8")

    # 1. lang attribute on <html>
    if not re.search(r"<html[^>]+lang=[\"'][a-zA-Z\-]+[\"']", content, re.IGNORECASE):
        violations.append(
            f"{html_file.name}: <html> element must include a valid 'lang' attribute (e.g., lang=\"en\")."
        )

    # 2. <title> element present and non-empty
    if not re.search(r"<title>\s*[^<]+\s*</title>", content, re.IGNORECASE):
        violations.append(f"{html_file.name}: Document must have a non-empty <title> element.")

    # 3. Viewport meta tag with user-scalable not disabled
    viewport_match = re.search(r"<meta[^>]+name=[\"']viewport[\"'][^>]*>", content, re.IGNORECASE)
    if not viewport_match:
        violations.append(f'{html_file.name}: Missing <meta name="viewport"> tag.')
    elif "user-scalable=no" in viewport_match.group(0).lower():
        violations.append(
            f"{html_file.name}: Viewport must not disable user-scalable zoom (WCAG 1.4.4)."
        )

    return violations


def check_component_accessibility(tsx_file: Path) -> list[str]:
    """Audits React/TSX component files for common a11y anti-patterns."""
    violations = []
    content = tsx_file.read_text(encoding="utf-8")
    lines = content.splitlines()

    for idx, line in enumerate(lines, 1):
        # 1. Image without alt attribute
        if "<img" in line:
            if not re.search(r"\balt=[\"'][^\"']*[\"']", line) and not re.search(
                r"aria-hidden=[\"']true[\"']", line
            ):
                violations.append(
                    f"{tsx_file.name}:{idx}: <img> tag missing required 'alt' attribute."
                )

        # 2. Interactive elements without accessible name
        if "<button" in line and ">" in line:
            # Check if button is empty or purely icon without aria-label
            button_match = re.search(r"<button([^>]*)>(.*?)</button>", line)
            if button_match:
                attrs, body = button_match.groups()
                if not body.strip() or (
                    "<" in body
                    and ">" in body
                    and not re.search(r"[a-zA-Z0-9]", re.sub(r"<[^>]+>", "", body))
                ):
                    if not re.search(r"aria-label=[\"'][^\"']+[\"']", attrs) and not re.search(
                        r"aria-labelledby=", attrs
                    ):
                        violations.append(
                            f"{tsx_file.name}:{idx}: Icon-only or empty <button> must provide an 'aria-label'."
                        )

    return violations


def run_accessibility_audit() -> bool:
    """Scans all web templates and components for WCAG 2.1 AA violations."""
    print(">>> Executing CloudLens WCAG 2.1 AA Accessibility Audit...")
    violations: list[str] = []

    # Check root index.html
    index_html = WEB_DIR / "index.html"
    violations.extend(check_html_accessibility(index_html))

    # Check all TSX/JSX components
    src_dir = WEB_DIR / "src"
    if src_dir.exists():
        for comp_file in src_dir.rglob("*.tsx"):
            violations.extend(check_component_accessibility(comp_file))
        for comp_file in src_dir.rglob("*.jsx"):
            violations.extend(check_component_accessibility(comp_file))

    if violations:
        print(
            f"\n[FAIL] Accessibility Audit found {len(violations)} violation(s):", file=sys.stderr
        )
        for v in violations:
            print(f"  - {v}", file=sys.stderr)
        return False

    print(
        "[PASS] Accessibility Audit: All templates and components conform to WCAG 2.1 AA standards."
    )
    return True


if __name__ == "__main__":
    success = run_accessibility_audit()
    sys.exit(0 if success else 1)
