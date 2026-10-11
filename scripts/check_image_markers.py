"""CloudLens Quality Gate: AI Image Marker & Provenance Verification.

Enforces Prompt P18 Requirement 1:
CI rejects images with C2PA / trainedAlgorithmicMedia / generative AI markers
in fat/ and docs/. Valid evidence must be real Playwright captures or verified assets.
"""

from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parent.parent

FORBIDDEN_MARKERS = [
    b"c2pa",
    b"C2PA",
    b"jumb",
    b"trainedAlgorithmicMedia",
    b"DALL",
    b"Imagen",
    b"Midjourney",
    b"Stable Diffusion",
    b"Gemini",
]

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


def check_images(target_dirs: list[str]) -> list[str]:
    violations: list[str] = []
    for d in target_dirs:
        dir_path = ROOT_DIR / d
        if not dir_path.is_dir():
            continue
        for img_path in dir_path.rglob("*"):
            if img_path.is_file() and img_path.suffix.lower() in IMAGE_EXTENSIONS:
                content = img_path.read_bytes()
                # Check first 64KB as well as full content if small
                head = content[:65536]
                found_markers = [m.decode("utf-8", errors="ignore") for m in FORBIDDEN_MARKERS if m in head or m in content]
                if found_markers:
                    violations.append(
                        f"{img_path.relative_to(ROOT_DIR)} carries forbidden AI/C2PA markers: {found_markers}"
                    )
    return violations


def main() -> None:
    print(">>> Verifying image provenance and scanning for AI/C2PA markers in fat/ and docs/...")
    violations = check_images(["fat", "docs"])
    if violations:
        print("[FAIL] AI-generation / C2PA marker violations detected in test/evidence images:", file=sys.stderr)
        for v in violations:
            print(f"  - {v}", file=sys.stderr)
        sys.exit(1)
    print("[PASS] No AI-generation or C2PA markers found in fat/ or docs/ images.")
    sys.exit(0)


if __name__ == "__main__":
    main()
