"""Unit tests for Reproducible Build & Signing Gate."""

import json
from pathlib import Path

from scripts.build_signed_container import (
    DEFAULT_DEV_SIGNING_KEY,
    build_and_sign,
    sign_manifest,
    verify_signature,
)


def test_build_and_sign_execution():
    """Verify build artifact record is generated and signature is mathematically valid."""
    record = build_and_sign()

    assert record.build_id.startswith("cloudlens-api-")
    assert len(record.artifact_digest) == 64
    assert Path(record.sbom_path).exists()
    assert Path(record.signature_path).exists()

    # Load and verify signature record
    sig_content = json.loads(Path(record.signature_path).read_text(encoding="utf-8"))
    manifest_bytes = json.dumps(sig_content["manifest"], sort_keys=True).encode("utf-8")
    assert verify_signature(manifest_bytes, sig_content["signature"], DEFAULT_DEV_SIGNING_KEY)


def test_tampered_manifest_fails_signature_verification():
    """Verify that tampering with manifest invalidates the cryptographic signature."""
    manifest = {"service": "cloudlens-api", "version": "1.0.0"}
    manifest_bytes = json.dumps(manifest, sort_keys=True).encode("utf-8")
    sig = sign_manifest(manifest_bytes, DEFAULT_DEV_SIGNING_KEY)

    # Valid
    assert verify_signature(manifest_bytes, sig, DEFAULT_DEV_SIGNING_KEY) is True

    # Tampered manifest
    tampered_bytes = json.dumps(
        {"service": "cloudlens-api", "version": "1.0.1"}, sort_keys=True
    ).encode("utf-8")
    assert verify_signature(tampered_bytes, sig, DEFAULT_DEV_SIGNING_KEY) is False

    # Wrong key
    assert verify_signature(manifest_bytes, sig, "wrong-key") is False
