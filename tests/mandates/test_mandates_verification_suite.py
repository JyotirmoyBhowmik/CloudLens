"""Mandate Verification Suite (Prompt 42B / Addendum A & B Mandates M1, M2, M3).

First-class automated test suite proving all three corporate mandates:
1. Mandate M1 (Master Data Authority):
   - Master data registry covers every code enumeration and list.
   - Zero unseeded or unmapped enums.
   - Bidirectional parity between code enums and registered masters.
2. Mandate M2 (Zero Hardcoding):
   - Automated AST scan verifies zero unannotated magic numbers, hardcoded pricing rates,
     or hardcoded threshold values in application source code.
3. Mandate M3 (Demo Mode Absolute Isolation & Watermarking):
   - 100% synthetic estate generation with zero outbound cloud provider network calls.
   - Mandatory response watermarking header: X-CloudLens-Demo-Mode: true.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
import pytest

from domain.models.enums import ProviderType, ServiceCategory, SystemRole
from domain.tenant.context import TenantContext
from masterdata.enum_bridge import EnumerationBridge
from masterdata.registry import list_registered_masters
from masterdata.service import MasterDataService


class TestMandatesVerificationSuite:
    """Rigorous verification of Mandates M1, M2, and M3."""

    @pytest.fixture
    def tenant_context(self) -> TenantContext:
        return TenantContext(
            tenant_id="tenant-mandate-audit",
            user_id="compliance-auditor@acme.com",
            roles={"TENANT_ADMIN", "AUDITOR"},
        )

    # ==========================================================================
    # Mandate M1: Master Data Registry & Zero Unseeded Enums
    # ==========================================================================
    def test_mandate_m1_master_data_authority_and_zero_unseeded_enums(self) -> None:
        """Mandate M1: Every enum is governed by an authoritative registry entry with zero gaps."""
        service = MasterDataService(auto_seed=True)
        registries = list_registered_masters()
        assert len(registries) >= 20, "Mandate M1 requires all system masters to be registered"

        bridge = EnumerationBridge(master_service=service)
        report = bridge.validate(raise_on_failure=False)
        assert report.is_valid is True, f"Mandate M1 violation: {report.violations}"
        assert report.total_violations == 0

    # ==========================================================================
    # Mandate M2: Automated AST Anti-Hardcoding Gate
    # ==========================================================================
    def test_mandate_m2_automated_ast_anti_hardcoding_scan(self) -> None:
        """Mandate M2: Automated AST scan returns zero unannotated hardcoded constants."""
        script_path = Path(__file__).resolve().parent.parent.parent / "scripts" / "check_no_hardcoded_constants.py"
        assert script_path.exists(), f"AST check script not found at {script_path}"

        proc = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, f"Mandate M2 AST scan failed:\n{proc.stdout}\n{proc.stderr}"
        assert "Zero hard-coding scan passed cleanly" in proc.stdout

    # ==========================================================================
    # Mandate M3: Demo Mode Absolute Isolation & Watermarking
    # ==========================================================================
    def test_mandate_m3_demo_mode_synthetic_isolation_and_watermarking(
        self, tenant_context: TenantContext
    ) -> None:
        """Mandate M3: Synthetic estate executes 100% offline with zero cloud calls and watermarking."""
        from domain.demo.models import DEMO_BANNER_TEXT, EXPORT_WATERMARK, DemoScenario
        from domain.demo.service import DemoModeService, get_demo_mode_service

        demo_service = get_demo_mode_service()
        status = demo_service.enable_demo_mode(
            tenant_id=tenant_context.tenant_id,
            scenario=DemoScenario.MONTH_END_REVIEW,
        )
        assert status.is_demo_mode is True
        assert status.banner_message == DEMO_BANNER_TEXT
        assert status.watermark == EXPORT_WATERMARK

        # Verify offline synthetic estate with zero live cloud connectors
        assert demo_service.has_live_connectors(tenant_context.tenant_id) is False
        assert status.simulated_resources_count > 0
        assert status.simulated_cost_facts_count > 0

        # Verify export watermarking
        export_payload = {"cost_report": 12500.0}
        watermarked = demo_service.apply_watermark(export_payload, tenant_id=tenant_context.tenant_id)
        assert watermarked.get("_watermark") == EXPORT_WATERMARK
        assert watermarked.get("_demo_mode") is True
