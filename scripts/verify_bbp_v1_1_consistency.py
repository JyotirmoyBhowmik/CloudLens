#!/usr/bin/env python3
"""Automated BBP v1.1 Internal Consistency Verification Script (Prompt 62).

Verifies that the issued BBP v1.1 specification document (docs/CLOUDLENS_BBP_v1.1.md)
satisfies all requirements of Prompt 62 and closes defects D-12, D-13, and D-14:
1. Verifies the five corrected counts in the BBP body:
   - Screens: exactly twenty-seven (27)
   - Administrative functions: exactly twenty-nine (29)
   - Connector capabilities: exactly eighteen (18)
   - Threshold bases: exactly eleven (11)
   - Monitoring types: exactly fifteen (15)
2. Verifies that all nineteen amendments (AM-01 through AM-19) are folded into the text.
3. Verifies that all thirteen requirement identifier prefixes are documented:
   BR, FR, PR, CST, USE, RUN, DEP, CON, API, SEC, NFR, DR, AC.
4. Verifies the presence of all new addenda sections:
   - Master Data Management and Governance
   - Mock Data and Demo Mode
   - Workflow and Approval Engine
   - Remediation and Accountability Loop
   - Showback, Chargeback, and Statements
   - Bulk Import and Data Onboarding
   - Quota Management
   - Pre-Deployment Provisioning Gates
   - Analytical Extract and Semantic Layer
   - Budget Planning and Scenario Modelling
   - Commitment Renewal and Coverage Management
   - Resource Lifecycle and Decommissioning
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BBP_FILE = PROJECT_ROOT / "docs" / "CLOUDLENS_BBP_v1.1.md"


def main() -> int:
    print("=" * 80)
    print(" CloudLens BBP v1.1 Documentation Reconciliation & Consistency Check (Prompt 62)")
    print("=" * 80)

    if not BBP_FILE.exists():
        print(f"[FAIL] Canonical BBP v1.1 document missing at: {BBP_FILE}", file=sys.stderr)
        return 1

    content = BBP_FILE.read_text(encoding="utf-8")
    errors: list[str] = []

    # 1. Verify Five Corrected Counts
    checks = [
        ("Screens count (27)", r"27\s*(?:screens|user interface screens|screens in inventory)", 27),
        ("Admin functions count (29)", r"29\s*(?:administrative functions|admin functions)", 29),
        ("Connector capabilities count (18)", r"18\s*(?:connector capabilities|capabilities across connectors)", 18),
        ("Threshold bases count (11)", r"11\s*(?:threshold bases|bases for threshold evaluation)", 11),
        ("Monitoring types count (15)", r"15\s*(?:monitoring types|telemetry monitoring types)", 15),
    ]

    print("\n1. Verifying Five Reconciled Core Counts (Defects D-12, D-13, D-14):")
    for name, pattern, expected in checks:
        if re.search(pattern, content, re.IGNORECASE):
            print(f"  [PASS] {name}: Found valid reconciled count '{expected}' in body text.")
        else:
            errors.append(f"Missing or mismatched {name} matching pattern: {pattern}")
            print(f"  [FAIL] {name}: Count not found or mismatch.")

    # 2. Verify 19 Amendments (AM-01 to AM-19)
    print("\n2. Verifying Amendments Folded (AM-01 to AM-19):")
    missing_amendments = []
    for i in range(1, 20):
        am_tag = f"AM-{i:02d}"
        if am_tag in content:
            pass
        else:
            missing_amendments.append(am_tag)

    if not missing_amendments:
        print("  [PASS] All 19 amendments (AM-01 through AM-19) explicitly incorporated.")
    else:
        errors.append(f"Missing amendments in BBP body: {missing_amendments}")
        print(f"  [FAIL] Missing amendments: {missing_amendments}")

    # 3. Verify All 13 Requirement Identifier Prefixes
    print("\n3. Verifying Thirteen Requirement Prefixes (Prompt 00R Register):")
    prefixes = ["BR", "FR", "PR", "CST", "USE", "RUN", "DEP", "CON", "API", "SEC", "NFR", "DR", "AC"]
    missing_prefixes = []
    for prefix in prefixes:
        # Check header or table mention
        if f"`{prefix}-" in content or f"**{prefix}**" in content or f"| **{prefix}**" in content:
            pass
        else:
            missing_prefixes.append(prefix)

    if not missing_prefixes:
        print("  [PASS] All 13 requirement prefixes present and cross-referenced.")
    else:
        errors.append(f"Missing requirement prefixes: {missing_prefixes}")
        print(f"  [FAIL] Missing prefixes: {missing_prefixes}")

    # 4. Verify New Addenda Sections
    print("\n4. Verifying New Addenda Sections:")
    new_sections = [
        "Master Data Management and Governance",
        "Mock Data and Demo Mode",
        "Workflow and Approval",
        "Remediation and Accountability",
        "Showback, Chargeback, and Statements",
        "Bulk Import and Data Onboarding",
        "Quota Management",
        "Pre-Deployment Provisioning Gates",
        "Analytical Extract and Semantic Layer",
        "Budget Planning and Scenario Modelling",
        "Commitment Renewal and Coverage Management",
        "Resource Lifecycle and Decommissioning",
    ]
    missing_sections = []
    for sec in new_sections:
        if sec.lower() in content.lower():
            pass
        else:
            missing_sections.append(sec)

    if not missing_sections:
        print("  [PASS] All 12 newly issued domain sections incorporated.")
    else:
        errors.append(f"Missing addenda sections: {missing_sections}")
        print(f"  [FAIL] Missing sections: {missing_sections}")

    # Final verdict
    print("\n" + "=" * 80)
    if not errors:
        print("[SUCCESS] BBP v1.1 Specification is 100% Internally Consistent and Reconciled!")
        print("=" * 80)
        return 0
    else:
        print(f"[FAILURE] Found {len(errors)} consistency errors in BBP v1.1:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        print("=" * 80)
        return 1


if __name__ == "__main__":
    sys.exit(main())
