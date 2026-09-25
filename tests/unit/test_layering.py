"""Tests for Layering Rule Enforcement (Prompt 01 Acceptance Criterion).

Verifies:
1. Clean repository passes layering check.
2. An import of a provider SDK from the domain layer fails the build with a clear message.
"""

from pathlib import Path

from scripts.check_layering import check_file, run_check


def test_layering_rule_passes_on_clean_codebase():
    """Verify that current repository has zero layering violations."""
    root_path = Path(__file__).resolve().parent.parent.parent
    result = run_check(str(root_path))
    assert result == 0, "Layering check must pass on clean codebase"


def test_domain_import_of_provider_sdk_fails_with_clear_message(tmp_path):
    """Verify that importing boto3/azure/oci/google from domain layer fails with explicit message."""
    test_root = tmp_path
    domain_dir = test_root / "domain" / "models"
    domain_dir.mkdir(parents=True)

    bad_domain_file = domain_dir / "invalid_resource.py"
    bad_domain_file.write_text(
        "import boto3\nfrom azure.mgmt.compute import ComputeManagementClient\n\nclass Resource:\n    pass\n",
        encoding="utf-8",
    )

    violations = check_file(bad_domain_file, test_root)

    assert len(violations) == 2, "Expected 2 violations (boto3 and azure)"

    # Verify error message clarity
    v1 = violations[0]
    assert v1.imported_module == "boto3"
    assert v1.layer == "domain"
    assert "Layering rule 'presentation -> application -> domain" in v1.message
    assert "must not import provider SDK 'boto3'" in v1.message

    v2 = violations[1]
    assert "azure" in v2.imported_module
    assert v2.layer == "domain"
    assert "must not import provider SDK 'azure.mgmt.compute'" in v2.message


def test_all_top_level_packages_importable():
    """Verify that all monorepo areas are valid, importable Python packages."""
    import api.cloudlens_api
    import connectors.aws
    import connectors.azure
    import connectors.contract
    import connectors.gcp
    import connectors.oci
    import connectors.stub

    assert api.cloudlens_api.app is not None
    assert connectors.contract.BaseCloudConnector is not None
