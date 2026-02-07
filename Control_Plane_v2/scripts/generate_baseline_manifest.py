#!/usr/bin/env python3
"""
Generate Baseline Manifest for Control Plane v2

This script scans pristine roots and produces a deterministic baseline package
manifest that claims ownership of all existing governed files.

BINDING CONSTRAINTS (from CP-IMPL-001):
- HO3-only scope: operates in HO3 governance context
- Hash format: sha256:<64hex>
- Deterministic: metadata excluded from manifest_hash
- Turn isolation: records declared inputs (roots, exclusions, hash alg)

Usage:
    python3 scripts/generate_baseline_manifest.py --plane ho3 --output packages_store/PKG-BASELINE-HO3-000/
"""

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from fnmatch import fnmatch
from pathlib import Path
from typing import Optional

# Resolve paths relative to Control_Plane_v2 root
SCRIPT_DIR = Path(__file__).resolve().parent
CONTROL_PLANE_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(CONTROL_PLANE_ROOT))


# === Asset Classification Patterns ===
# Order matters: first match wins
CLASSIFICATION_PATTERNS = [
    (r"^frameworks/.*\.md$", "law_doc"),
    (r"^specs/.*/manifest\.yaml$", "spec_manifest"),
    (r"^specs/.*\.yaml$", "spec_asset"),
    (r"^specs/.*\.json$", "spec_asset"),
    (r"^specs/.*\.md$", "spec_asset"),
    (r"^lib/.*\.py$", "library"),
    (r"^scripts/.*\.py$", "script"),
    (r"^scripts/.*\.sh$", "script"),
    (r"^registries/compiled/.*\.json$", "compiled_registry"),
    (r"^registries/.*\.csv$", "registry"),
    (r"^schemas/.*\.json$", "schema"),
    (r"^scripts/policies/.*\.yaml$", "policy"),
    (r"^scripts/policies/.*\.json$", "policy"),
    (r"^tests/.*\.py$", "test"),
    (r"^docs/.*\.md$", "documentation"),
    (r"^modules/.*\.py$", "module"),
    (r"^modules/.*", "module"),
    (r"^gates/.*\.py$", "gate"),
    (r"^config/.*\.json$", "config"),
    (r"^config/.*\.yaml$", "config"),
]


def classify_asset(rel_path: str) -> str:
    """Classify asset by path pattern. Returns classification string."""
    for pattern, classification in CLASSIFICATION_PATTERNS:
        if re.match(pattern, rel_path):
            return classification
    return "other"


from lib.hashing import compute_sha256  # canonical implementation


def load_governed_roots_config(plane: str) -> dict:
    """Load governed_roots.json for the specified plane."""
    if plane == "ho3":
        config_path = CONTROL_PLANE_ROOT / "config" / "governed_roots.json"
    else:
        config_path = CONTROL_PLANE_ROOT / "planes" / plane / "config" / "governed_roots.json"

    if not config_path.exists():
        raise FileNotFoundError(f"Governed roots config not found: {config_path}")

    return json.loads(config_path.read_text())


def is_excluded(rel_path: str, exclusion_patterns: list[str]) -> bool:
    """Check if path matches any exclusion pattern."""
    for pattern in exclusion_patterns:
        if fnmatch(rel_path, pattern):
            return True
        # Also check if any path component matches
        for part in Path(rel_path).parts:
            if fnmatch(part, pattern.replace("**/", "")):
                return True
    return False


def scan_governed_files(
    plane: str,
    governed_roots: list[str],
    exclusion_patterns: list[str]
) -> list[dict]:
    """
    Scan governed roots and return list of asset entries.

    Returns sorted list for determinism.
    """
    assets = []

    for root in governed_roots:
        root_path = CONTROL_PLANE_ROOT / root
        if not root_path.exists():
            continue

        for file_path in root_path.rglob("*"):
            if not file_path.is_file():
                continue

            rel_path = str(file_path.relative_to(CONTROL_PLANE_ROOT))

            # Check exclusions
            if is_excluded(rel_path, exclusion_patterns):
                continue

            # Skip hidden files
            if any(part.startswith(".") for part in Path(rel_path).parts):
                continue

            # Compute hash and classify
            file_hash = compute_sha256(file_path)
            classification = classify_asset(rel_path)

            assets.append({
                "path": rel_path,
                "sha256": file_hash,
                "classification": classification,
            })

    # Sort by path for determinism
    assets.sort(key=lambda a: a["path"])
    return assets


def build_install_targets(assets: list[dict]) -> list[dict]:
    """
    Build install_targets from assets.

    Groups files by namespace (first path component).
    For baseline, target_id is "baseline" since we claim everything.
    """
    targets = {}

    for asset in assets:
        path = asset["path"]
        parts = Path(path).parts

        if len(parts) < 1:
            continue

        namespace = parts[0].rstrip("/")

        if namespace not in targets:
            targets[namespace] = {
                "namespace": namespace,
                "target_id": "baseline",
                "files": [],
            }

        # File is relative path within namespace
        if len(parts) > 1:
            file_in_namespace = str(Path(*parts[1:]))
        else:
            file_in_namespace = parts[0]

        targets[namespace]["files"].append(file_in_namespace)

    # Sort for determinism
    result = sorted(targets.values(), key=lambda t: t["namespace"])
    for target in result:
        target["files"].sort()

    return result


def compute_manifest_hash(manifest: dict) -> str:
    """
    Compute deterministic hash of manifest, EXCLUDING metadata block.

    This ensures the manifest_hash is stable across regeneration
    even if timestamps change.
    """
    # Create copy without metadata
    hashable = {k: v for k, v in manifest.items() if k != "metadata"}

    # Canonical JSON: sorted keys, compact separators
    canonical = json.dumps(hashable, sort_keys=True, separators=(",", ":"))

    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def generate_baseline_manifest(
    plane: str,
    package_id: Optional[str] = None,
    version: str = "1.0.0",
) -> dict:
    """
    Generate baseline manifest for the specified plane.

    Args:
        plane: Target plane (ho3, ho2, ho1)
        package_id: Package ID (default: PKG-BASELINE-{PLANE}-000)
        version: Package version

    Returns:
        Complete manifest dict
    """
    if plane != "ho3":
        raise ValueError(f"Phase 1 is HO3-only. Got plane={plane}")

    if package_id is None:
        package_id = f"PKG-BASELINE-{plane.upper()}-000"

    # Load governed roots config (declares our inputs)
    config = load_governed_roots_config(plane)
    governed_roots = config.get("governed_roots", [])
    exclusion_patterns = config.get("excluded_patterns", [])

    # Scan files
    assets = scan_governed_files(plane, governed_roots, exclusion_patterns)

    # Build install targets
    install_targets = build_install_targets(assets)

    # Build manifest (metadata is separate and excluded from hash)
    manifest = {
        "package_id": package_id,
        "version": version,
        "plane_id": plane,
        "package_type": "baseline",
        "install_targets": install_targets,
        "assets": assets,
        "dependencies": [],
        # Metadata is EXCLUDED from manifest_hash per binding constraints
        "metadata": {
            # Turn isolation: record declared inputs
            "scan_roots": governed_roots,
            "exclusion_patterns": exclusion_patterns,
            "hash_algorithm": "sha256",
            "hash_format_version": "1.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "generator": "generate_baseline_manifest.py",
            "generator_version": "1.0.0",
            "plane_context": "HO3",
            "notes": "Metadata excluded from manifest_hash for determinism",
        },
    }

    return manifest


def write_manifest(manifest: dict, output_dir: Path) -> Path:
    """Write manifest to output directory. Returns manifest path."""
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = output_dir / "manifest.json"

    # Pretty print for readability
    manifest_json = json.dumps(manifest, indent=2, sort_keys=False)
    manifest_path.write_text(manifest_json)

    return manifest_path


def write_checksums(assets: list[dict], output_dir: Path) -> Path:
    """Write checksums.sha256 file for redundant verification."""
    output_dir.mkdir(parents=True, exist_ok=True)

    checksums_path = output_dir / "checksums.sha256"

    lines = []
    for asset in assets:
        # Format: <hash>  <path> (two spaces, sha256sum compatible)
        # Extract just the hex part
        hash_hex = asset["sha256"].replace("sha256:", "")
        lines.append(f"{hash_hex}  {asset['path']}")

    checksums_path.write_text("\n".join(lines) + "\n")

    return checksums_path


def main():
    parser = argparse.ArgumentParser(
        description="Generate baseline manifest for Control Plane v2",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Generate baseline for HO3
    python3 scripts/generate_baseline_manifest.py --plane ho3 --output packages_store/PKG-BASELINE-HO3-000/

    # Dry run (print to stdout)
    python3 scripts/generate_baseline_manifest.py --plane ho3 --dry-run

    # Verify determinism
    python3 scripts/generate_baseline_manifest.py --plane ho3 --output /tmp/m1
    python3 scripts/generate_baseline_manifest.py --plane ho3 --output /tmp/m2
    diff /tmp/m1/manifest.json /tmp/m2/manifest.json
"""
    )

    parser.add_argument(
        "--plane",
        required=True,
        choices=["ho3"],  # Phase 1 is HO3-only
        help="Target plane (Phase 1: ho3 only)"
    )

    parser.add_argument(
        "--output",
        type=Path,
        help="Output directory for manifest files"
    )

    parser.add_argument(
        "--package-id",
        help="Package ID (default: PKG-BASELINE-{PLANE}-000)"
    )

    parser.add_argument(
        "--version",
        default="1.0.0",
        help="Package version (default: 1.0.0)"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print manifest to stdout instead of writing"
    )

    parser.add_argument(
        "--show-hash",
        action="store_true",
        help="Show manifest_hash after generation"
    )

    args = parser.parse_args()

    # Validate
    if not args.dry_run and not args.output:
        parser.error("--output required unless --dry-run specified")

    # Generate
    print(f"[generate_baseline_manifest] Scanning plane={args.plane}...", file=sys.stderr)

    manifest = generate_baseline_manifest(
        plane=args.plane,
        package_id=args.package_id,
        version=args.version,
    )

    manifest_hash = compute_manifest_hash(manifest)

    print(f"[generate_baseline_manifest] Found {len(manifest['assets'])} assets", file=sys.stderr)
    print(f"[generate_baseline_manifest] manifest_hash={manifest_hash}", file=sys.stderr)

    if args.dry_run:
        print(json.dumps(manifest, indent=2))
    else:
        manifest_path = write_manifest(manifest, args.output)
        checksums_path = write_checksums(manifest["assets"], args.output)

        print(f"[generate_baseline_manifest] Wrote {manifest_path}", file=sys.stderr)
        print(f"[generate_baseline_manifest] Wrote {checksums_path}", file=sys.stderr)

    if args.show_hash:
        print(f"manifest_hash={manifest_hash}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
