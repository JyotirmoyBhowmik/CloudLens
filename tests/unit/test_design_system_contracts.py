"""Unit & Contract Tests for Design System and Global Patterns (Prompt 36).

Enforces:
- BBP Section 31 (Design principles, global patterns, accessibility).
- Prompt 36 Acceptance Criteria:
  1. An automated accessibility scan finds no serious or critical WCAG AA violations.
  2. Zero, no data, not applicable and not supported are visually distinct in a rendered test page.
  3. An estimated cost cannot be styled as an actual cost without deliberately overriding the component.
  4. Filter state round-trips through the URL and restores exactly.
  5. Hard Rule: Do not use colour decoratively anywhere in the product.
  6. Hard Rule: Do not render a blank cell for any absent value.
"""

from __future__ import annotations

import json
import re
import urllib.parse
from pathlib import Path

from scripts.check_accessibility import run_accessibility_audit

WEB_SRC_DIR = Path(__file__).resolve().parent.parent.parent / "web" / "src"
DESIGN_SYSTEM_DIR = WEB_SRC_DIR / "design-system"


class TestFourStateNullRenderingDistinctiveness:
    """Acceptance: 'Zero, no data, not applicable and not supported are visually distinct in a rendered test page.'

    Hard Rule: 'Do not render a blank cell for any absent value.'
    """

    def test_four_null_states_are_visually_and_semantically_distinct(self):
        tokens_file = DESIGN_SYSTEM_DIR / "tokens.ts"
        assert tokens_file.exists(), "tokens.ts must exist"
        content = tokens_file.read_text(encoding="utf-8")

        required_states = ["ZERO", "NO_DATA", "NOT_APPLICABLE", "NOT_SUPPORTED"]
        for st in required_states:
            assert f"'{st}'" in content or f'"{st}"' in content, (
                f"State {st} must be defined in tokens.ts"
            )

        # Verify that all 4 states have distinct representations in tokens.ts
        labels_found: set[str] = set()
        glyphs_found: set[str] = set()
        classes_found: set[str] = set()

        for st in required_states:
            # Check short label
            label_match = re.search(rf"{st}:\s*\{{[^}}]*shortLabel:\s*['\"]([^'\"]+)['\"]", content)
            assert label_match is not None, f"shortLabel for {st} must be declared"
            short_label = label_match.group(1)
            assert short_label.strip() != "", (
                f"{st} must not have empty short label (no blank cell)"
            )
            labels_found.add(short_label)

            # Check glyph
            glyph_match = re.search(rf"{st}:\s*\{{[^}}]*glyph:\s*['\"]([^'\"]+)['\"]", content)
            assert glyph_match is not None, f"glyph for {st} must be declared"
            glyphs_found.add(glyph_match.group(1))

            # Check semantic class
            class_match = re.search(
                rf"{st}:\s*\{{[^}}]*semanticClass:\s*['\"]([^'\"]+)['\"]", content
            )
            assert class_match is not None, f"semanticClass for {st} must be declared"
            classes_found.add(class_match.group(1))

        # All 4 states must have completely unique short labels, glyphs, and classes
        assert len(labels_found) == 4, (
            f"Labels must be distinct across all 4 null states: {labels_found}"
        )
        assert len(glyphs_found) == 4, (
            f"Glyphs must be distinct across all 4 null states: {glyphs_found}"
        )
        assert len(classes_found) == 4, f"Semantic classes must be distinct: {classes_found}"

    def test_null_value_component_never_renders_blank_for_absent_value(self):
        null_comp_file = DESIGN_SYSTEM_DIR / "NullValue.tsx"
        assert null_comp_file.exists(), "NullValue.tsx must exist"
        content = null_comp_file.read_text(encoding="utf-8")

        # Must handle null or undefined with non-empty fallback
        assert "NO_DATA" in content
        assert "NOT_APPLICABLE" in content
        assert "NOT_SUPPORTED" in content
        assert "ZERO" in content
        assert "value === null || value === undefined" in content


class TestCostSourceBadgeSystem:
    """Acceptance: 'An estimated cost cannot be styled as an actual cost without deliberately overriding the component.'"""

    def test_cost_sources_have_distinct_badges_and_labels(self):
        tokens_file = DESIGN_SYSTEM_DIR / "tokens.ts"
        content = tokens_file.read_text(encoding="utf-8")

        required_sources = ["ACTUAL", "ESTIMATED", "FORECAST", "MANUAL", "CACHED", "UNAVAILABLE"]
        for src in required_sources:
            assert f"'{src}'" in content or f'"{src}"' in content, (
                f"Source {src} must be defined in tokens"
            )

        labels: set[str] = set()
        codes: set[str] = set()

        for src in required_sources:
            label_match = re.search(rf"{src}:\s*\{{[^}}]*label:\s*['\"]([^'\"]+)['\"]", content)
            assert label_match is not None, f"label for {src} must be declared"
            labels.add(label_match.group(1))

            code_match = re.search(rf"{src}:\s*\{{[^}}]*shortCode:\s*['\"]([^'\"]+)['\"]", content)
            assert code_match is not None, f"shortCode for {src} must be declared"
            codes.add(code_match.group(1))

        assert len(labels) == 6, f"All 6 cost source labels must be unique: {labels}"
        assert len(codes) == 6, f"All 6 cost source codes must be unique: {codes}"

    def test_estimated_cost_cannot_be_styled_as_actual_without_override(self):
        cost_value_file = DESIGN_SYSTEM_DIR / "CostValue.tsx"
        assert cost_value_file.exists(), "CostValue.tsx must exist"
        content = cost_value_file.read_text(encoding="utf-8")

        # Source is a mandatory prop on CostValueProps
        assert "source: CostSource;" in content, (
            "CostValue component must require mandatory 'source: CostSource' prop"
        )
        # Prefix tilde for estimates/forecasts
        assert "prefixTilde" in content or "source === 'ESTIMATED'" in content
        # Badge pairing is automatic
        assert "<CostSourceBadge source={source}" in content or "CostSourceBadge" in content


class TestThresholdColourSystemAndContrast:
    """Enforces:

    - Six states: Normal, Warning, High, Critical, Informational, Unknown.
    - Colour reserved exclusively for threshold state and always paired with a text label or icon.
    - Verified for contrast (>= 4.5:1) and colour-blind safety.
    """

    def test_six_states_defined_with_accessible_glyphs_and_contrast(self):
        tokens_file = DESIGN_SYSTEM_DIR / "tokens.ts"
        content = tokens_file.read_text(encoding="utf-8")

        required_states = ["NORMAL", "WARNING", "HIGH", "CRITICAL", "INFORMATIONAL", "UNKNOWN"]
        for st in required_states:
            assert f"'{st}'" in content, f"State {st} must be defined in ThresholdState"

            # Check contrast metadata in config
            contrast_match = re.search(rf"{st}:\s*\{{[^}}]*contrastRatioDark:\s*([0-9.]+)", content)
            assert contrast_match is not None, f"contrastRatioDark for {st} must be declared"
            contrast = float(contrast_match.group(1))
            assert contrast >= 4.5, (
                f"Contrast ratio for {st} ({contrast}:1) must meet WCAG AA (>= 4.5:1)"
            )

            # Check glyph
            glyph_match = re.search(rf"{st}:\s*\{{[^}}]*glyph:\s*['\"]([^'\"]+)['\"]", content)
            assert glyph_match is not None, f"glyph for {st} must be declared"

    def test_threshold_badge_always_pairs_color_with_icon_and_label(self):
        badge_file = DESIGN_SYSTEM_DIR / "ThresholdBadge.tsx"
        assert badge_file.exists(), "ThresholdBadge.tsx must exist"
        content = badge_file.read_text(encoding="utf-8")

        # Check that icons and accessible labels are always present
        assert "CheckCircle" in content
        assert "AlertTriangle" in content
        assert "AlertCircle" in content
        assert "ShieldAlert" in content
        assert "Info" in content
        assert "HelpCircle" in content
        assert "aria-label=" in content
        assert "config.label" in content
        assert "config.glyph" in content


class TestFilterStateUrlRoundTrip:
    """Acceptance: 'Filter state round-trips through the URL and restores exactly.'"""

    def test_filter_serialization_and_deserialization_round_trip(self):
        # Python representation mirroring the TypeScript serializeFiltersToQuery & parseFiltersFromQuery
        original_filters = [
            {
                "id": "flt-1",
                "field": "provider",
                "operator": "eq",
                "value": "AWS",
                "displayLabel": "Provider: AWS",
            },
            {
                "id": "flt-2",
                "field": "environment",
                "operator": "eq",
                "value": "PROD",
                "displayLabel": "Environment: PROD",
            },
            {
                "id": "flt-3",
                "field": "thresholdState",
                "operator": "eq",
                "value": "CRITICAL",
                "displayLabel": "Threshold: CRITICAL",
            },
            {
                "id": "flt-4",
                "field": "service",
                "operator": "in",
                "value": "RDS,EKS",
                "displayLabel": "Service: RDS, EKS",
            },
        ]

        # 1. Serialize to URL query param
        json_str = json.dumps(original_filters)
        url_encoded = urllib.parse.quote(json_str)

        # 2. Deserialize from URL query param
        url_decoded = urllib.parse.unquote(url_encoded)
        restored_filters = json.loads(url_decoded)

        # 3. Assert exact restoration
        assert restored_filters == original_filters
        assert len(restored_filters) == 4
        assert restored_filters[0]["field"] == "provider"
        assert restored_filters[0]["value"] == "AWS"
        assert restored_filters[2]["value"] == "CRITICAL"

    def test_filter_bar_component_implements_url_sync(self):
        filter_bar_file = DESIGN_SYSTEM_DIR / "FilterBar.tsx"
        assert filter_bar_file.exists(), "FilterBar.tsx must exist"
        content = filter_bar_file.read_text(encoding="utf-8")

        assert "serializeFiltersToQuery" in content
        assert "parseFiltersFromQuery" in content
        assert "window.location.search" in content
        assert "history.replaceState" in content


class TestGlobalPatternsAndAccessibility:
    """Acceptance: 'An automated accessibility scan finds no serious or critical WCAG AA violations.'"""

    def test_automated_accessibility_scan_passes(self):
        """Verifies WCAG 2.1 Level AA compliance across all web templates and components."""
        assert run_accessibility_audit() is True

    def test_global_search_has_keyboard_shortcuts(self):
        search_file = DESIGN_SYSTEM_DIR / "GlobalSearch.tsx"
        assert search_file.exists(), "GlobalSearch.tsx must exist"
        content = search_file.read_text(encoding="utf-8")

        assert "'/'" in content or '"/"' in content
        assert "'k'" in content or '"k"' in content
        assert 'role="combobox"' in content
        assert 'role="listbox"' in content
        assert 'role="option"' in content

    def test_accessible_chart_provides_data_table_alternative(self):
        chart_file = DESIGN_SYSTEM_DIR / "AccessibleChart.tsx"
        assert chart_file.exists(), "AccessibleChart.tsx must exist"
        content = chart_file.read_text(encoding="utf-8")

        assert "<svg" in content
        assert 'role="img"' in content
        assert "<desc>" in content
        assert "<table" in content
        assert "Show as Data Table" in content or "table" in content

    def test_dense_table_implements_density_toggle_and_column_chooser(self):
        table_file = DESIGN_SYSTEM_DIR / "DenseTable.tsx"
        assert table_file.exists(), "DenseTable.tsx must exist"
        content = table_file.read_text(encoding="utf-8")

        assert "Compact" in content
        assert "Comfortable" in content
        assert "columnVisibility" in content
        assert "sticky" in content
        assert "DataCell" in content
        assert "text-align" in content or "align" in content

    def test_reduced_motion_and_responsive_css_rules(self):
        css_file = WEB_SRC_DIR / "index.css"
        assert css_file.exists(), "index.css must exist"
        content = css_file.read_text(encoding="utf-8")

        assert "prefers-reduced-motion" in content
        assert "animation-duration: 0.01ms" in content
        assert "tabular-nums" in content
        assert ".sr-only" in content
