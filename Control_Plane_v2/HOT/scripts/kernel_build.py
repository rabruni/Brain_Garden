#!/usr/bin/env python3
"""
Kernel Package Builder

Builds PKG-KERNEL-001 from the kernel file definitions.
The kernel package contains shared system code that must be identical across all tiers.

Usage:
    python3 scripts/kernel_build.py [--output DIR] [--dry-run] [--show-hash]

Outputs:
    packages_store/PKG-KERNEL-001/
    ├── manifest.json    # Kernel manifest with file hashes
    └── files/           # Copies of kernel files

Phase 4 Implementation: AC-K1 (deterministic build)
"""

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add parent for lib imports
SCRIPT_DIR = Path(__file__).resolve().parent
CONTROL_PLANE_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(CONTROL_PLANE_ROOT))


def compute_file_hash(file_path: Path) -> str:
    """Compute SHA-256 hash of file in sha256:<hex> format."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return f"sha256:{sha256.hexdigest()}"


def load_kernel_definition(plane_root: Path) -> dict:
    """Load kernel file definitions from config."""
    config_path = plane_root / "config" / "kernel_files.json"
    if not config_path.exists():
        raise FileNotFoundError(f"Kernel definition not found: {config_path}")
    return json.loads(config_path.read_text())


def build_kernel_manifest(plane_root: Path, kernel_def: dict) -> dict:
    """Build kernel manifest with file hashes."""
    assets = []
    missing_files = []

    for rel_path in sorted(kernel_def["files"]):
        file_path = plane_root / rel_path
        if not file_path.exists():
            missing_files.append(rel_path)
            continue

        file_hash = compute_file_hash(file_path)
        assets.append({
            "path": rel_path,
            "sha256": file_hash
        })

    if missing_files:
        raise FileNotFoundError(f"Missing kernel files: {missing_files}")

    # Compute manifest hash from sorted canonical JSON of assets
    assets_json = json.dumps(assets, sort_keys=True, separators=(",", ":"))
    manifest_hash = f"sha256:{hashlib.sha256(assets_json.encode()).hexdigest()}"

    manifest = {
        "package_id": kernel_def["package_id"],
        "package_type": kernel_def["package_type"],
        "version": "1.0.0",
        "schema_version": "1.0",
        "assets": assets,
        "assets_count": len(assets),
        "manifest_hash": manifest_hash,
        "metadata": {
            "built_at": datetime.now(timezone.utc).isoformat(),
            "source_plane": "ho3",
            "immutable_across_tiers": kernel_def["constraints"]["immutable_across_tiers"],
            "parity_gate": kernel_def["constraints"]["requires_parity_gate"]
        }
    }

    return manifest


def write_kernel_package(
    plane_root: Path,
    manifest: dict,
    output_dir: Path,
    dry_run: bool = False
) -> Path:
    """Write kernel package to output directory."""
    pkg_dir = output_dir / manifest["package_id"]

    if dry_run:
        print(f"[DRY-RUN] Would create: {pkg_dir}")
        return pkg_dir

    # Create package directory
    pkg_dir.mkdir(parents=True, exist_ok=True)
    files_dir = pkg_dir / "files"
    files_dir.mkdir(exist_ok=True)

    # Write manifest
    manifest_path = pkg_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

    # Copy kernel files
    for asset in manifest["assets"]:
        src = plane_root / asset["path"]
        dst = files_dir / asset["path"]
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    return pkg_dir


def main():
    parser = argparse.ArgumentParser(description="Build kernel package")
    parser.add_argument("--output", type=Path, default=None,
                       help="Output directory (default: packages_store/)")
    parser.add_argument("--dry-run", action="store_true",
                       help="Show what would be built without writing")
    parser.add_argument("--show-hash", action="store_true",
                       help="Show manifest hash")
    parser.add_argument("--json", action="store_true",
                       help="Output JSON manifest")
    args = parser.parse_args()

    plane_root = CONTROL_PLANE_ROOT
    output_dir = args.output or (plane_root / "packages_store")

    try:
        # Load kernel definition
        kernel_def = load_kernel_definition(plane_root)

        # Build manifest
        manifest = build_kernel_manifest(plane_root, kernel_def)

        if args.json:
            print(json.dumps(manifest, indent=2))
            return 0

        if args.show_hash:
            print(f"manifest_hash={manifest['manifest_hash']}")

        # Write package
        pkg_dir = write_kernel_package(plane_root, manifest, output_dir, args.dry_run)

        if not args.dry_run:
            print(f"Kernel package built: {pkg_dir}")
            print(f"  Package ID: {manifest['package_id']}")
            print(f"  Assets: {manifest['assets_count']}")
            print(f"  Manifest hash: {manifest['manifest_hash']}")

        return 0

    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
