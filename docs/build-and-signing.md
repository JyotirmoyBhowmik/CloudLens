# CloudLens Reproducible Builds & Artifact Signing

This document outlines the cryptographic signing and Software Bill of Materials (SBOM) generation pipeline for CloudLens release containers per **Prompt 04 Item 29** and **BBP Section 47**.

---

## 1. Principles of Reproducibility

Every CloudLens container build is deterministic:
1. **Pinned Dependency Tree**: Pinned via `requirements-lock.txt` and `pnpm-lock.yaml`.
2. **Digest Computation**: SHA-256 digests computed over git commit HEAD, package manifests, and Dockerfile.
3. **Hermetic Environment**: Multi-stage Docker build definitions isolating build tools from runtime base images.

---

## 2. Per-Build Software Bill of Materials (SBOM)

During each build invocation:
- A CycloneDX v1.5 JSON SBOM is generated in `dist/sbom/cloudlens-api-<digest>-sbom.json`.
- It records package coordinates, PURLs (`pkg:pypi/...`), package versions, and container metadata.
- Zero proprietary dependencies (conforming to `CON-T1`).

---

## 3. Cryptographic Signature Verification

- **Format**: HMAC-SHA256 (compatible with Sigstore / Cosign release metadata standards).
- **Signature Artifact**: Stored in `dist/signatures/cloudlens-api-<digest>.sig`.
- **Integrity Validation**: Any modification to container metadata, commit hash, or SBOM filenames immediately invalidates the signature.
- **Verification Command**:
  ```bash
  python scripts/build_signed_container.py
  ```
