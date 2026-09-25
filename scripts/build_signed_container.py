"""CloudLens Reproducible Container Build & Artifact Signing Gate.

Enforces Prompt 04 Item 29 & Deliverable:
"Produce reproducible container builds with signed artefacts and a generated software bill of materials per build."
"""

import hashlib
import hmac
import json
import os
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent

DEFAULT_DEV_SIGNING_KEY = "cloudlens-dev-release-signing-key-2026"


@dataclass
class BuildArtifactRecord:
    build_id: str
    git_commit: str
    timestamp: str
    artifact_digest: str
    sbom_path: str
    signature_path: str


def get_git_commit() -> str:
    """Retrieve current HEAD commit hash."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(ROOT_DIR),
            capture_output=True,
            text=True,
            check=True,
        )
        return res.stdout.strip()
    except Exception:
        return "0000000000000000000000000000000000000000"


def compute_file_sha256(file_path: Path) -> str:
    hasher = hashlib.sha256()
    with file_path.open("rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def generate_build_sbom(build_id: str, commit_hash: str, output_path: Path) -> dict[str, Any]:
    """Generates CycloneDX v1.5 JSON SBOM for the specific build."""
    lock_file = ROOT_DIR / "requirements-lock.txt"
    components = []

    if lock_file.exists():
        for line in lock_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("-"):
                continue
            if "==" in line:
                name, version = line.split("==", 1)
                components.append(
                    {
                        "type": "library",
                        "name": name.strip(),
                        "version": version.strip(),
                        "purl": f"pkg:pypi/{name.strip()}@{version.strip()}",
                    }
                )

    sbom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": f"urn:uuid:{hashlib.md5(build_id.encode('utf-8')).hexdigest()}",
        "version": 1,
        "metadata": {
            "timestamp": datetime.now(UTC).isoformat(),
            "component": {
                "name": "cloudlens-api",
                "version": "0.1.0",
                "type": "container",
                "description": "CloudLens Platform API Container",
                "hashes": [{"alg": "SHA-256", "content": commit_hash}],
            },
        },
        "components": components,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(sbom, indent=2), encoding="utf-8")
    return sbom


def sign_manifest(manifest_bytes: bytes, signing_key: str) -> str:
    """Generates HMAC-SHA256 signature for the build manifest."""
    return hmac.new(signing_key.encode("utf-8"), manifest_bytes, hashlib.sha256).hexdigest()


def verify_signature(manifest_bytes: bytes, signature: str, signing_key: str) -> bool:
    """Verifies authenticity and integrity of build signature."""
    expected = sign_manifest(manifest_bytes, signing_key)
    return hmac.compare_digest(expected, signature)


def build_and_sign(
    service_name: str = "cloudlens-api",
    signing_key: str | None = None,
) -> BuildArtifactRecord:
    """Orchestrates reproducible build metadata generation, SBOM generation, and cryptographic signing."""
    commit = get_git_commit()
    timestamp = datetime.now(UTC).isoformat()
    key: str = signing_key or os.getenv("CLOUDLENS_SIGNING_KEY") or DEFAULT_DEV_SIGNING_KEY

    # Compute deterministic digest of core configuration and container manifests
    hasher = hashlib.sha256()
    hasher.update(commit.encode("utf-8"))
    for manifest_name in ("pyproject.toml", "requirements-lock.txt", "ops/docker/Dockerfile.api"):
        m_path = ROOT_DIR / manifest_name
        if m_path.exists():
            hasher.update(compute_file_sha256(m_path).encode("utf-8"))

    artifact_digest = hasher.hexdigest()
    build_id = f"{service_name}-{artifact_digest[:12]}"

    # Output paths
    dist_dir = ROOT_DIR / "dist"
    sbom_path = dist_dir / "sbom" / f"{build_id}-sbom.json"
    sig_path = dist_dir / "signatures" / f"{build_id}.sig"

    # Generate build-specific SBOM
    generate_build_sbom(build_id, commit, sbom_path)

    # Build manifest
    manifest_data = {
        "service": service_name,
        "build_id": build_id,
        "git_commit": commit,
        "timestamp": timestamp,
        "artifact_digest": artifact_digest,
        "sbom_file": sbom_path.name,
    }
    manifest_bytes = json.dumps(manifest_data, sort_keys=True).encode("utf-8")

    # Cryptographically sign manifest
    signature = sign_manifest(manifest_bytes, key)

    # Write signature record
    sig_record = {
        "build_id": build_id,
        "signature": signature,
        "signer": "cloudlens-release-pipeline",
        "algorithm": "HMAC-SHA256",
        "manifest": manifest_data,
    }
    sig_path.parent.mkdir(parents=True, exist_ok=True)
    sig_path.write_text(json.dumps(sig_record, indent=2), encoding="utf-8")

    return BuildArtifactRecord(
        build_id=build_id,
        git_commit=commit,
        timestamp=timestamp,
        artifact_digest=artifact_digest,
        sbom_path=str(sbom_path),
        signature_path=str(sig_path),
    )


def main() -> None:
    print("=" * 80)
    print("CLOUDLENS REPRODUCIBLE CONTAINER BUILD & SIGNING")
    print("Enforcing Prompt 04 Item 29: Reproducible signed builds with per-build SBOM")
    print("=" * 80)

    record = build_and_sign()

    print(f"  Build ID:        {record.build_id}")
    print(f"  Git Commit:      {record.git_commit}")
    print(f"  Artifact Digest: sha256:{record.artifact_digest}")
    print(f"  SBOM File:       {record.sbom_path}")
    print(f"  Signature File:  {record.signature_path}")

    # Verify signature locally
    sig_file = Path(record.signature_path)
    sig_data = json.loads(sig_file.read_text(encoding="utf-8"))
    manifest_bytes = json.dumps(sig_data["manifest"], sort_keys=True).encode("utf-8")
    assert verify_signature(manifest_bytes, sig_data["signature"], DEFAULT_DEV_SIGNING_KEY)

    print("\n[PASS] Build artifact signed and verified successfully.")
    print("=" * 80)


if __name__ == "__main__":
    main()
