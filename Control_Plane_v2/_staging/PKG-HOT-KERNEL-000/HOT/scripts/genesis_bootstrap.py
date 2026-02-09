#!/usr/bin/env python3
"""
genesis_bootstrap.py - Self-contained bootstrapper for Genesis packages.

NO lib/ imports. All stdlib. Can install packages when lib/ is empty.

This is the minimal installer that works BEFORE any lib/ modules exist.
It is used to install the Genesis (G0) tier packages that form the
foundation of the package system.

Per FMWK-PKG-001: Package Standard v1.0

Usage:
    python3 scripts/genesis_bootstrap.py \\
        --seed seed_registry.json \\
        --archive PKG-G0-001.tar.gz \\
        [--verify-only] [--force]

Environment:
    CONTROL_PLANE_ROOT: Override root (default: parent of scripts/)
    CONTROL_PLANE_SIGNING_KEY: HMAC key for signature verification
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Version of this bootstrapper
BOOTSTRAP_VERSION = "1.0.0"


def sha256_file(path: Path) -> str:
    """Compute SHA-256 hash of a file.

    Args:
        path: Path to file

    Returns:
        Lowercase hex digest
    """
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    """Compute SHA-256 hash of bytes."""
    return hashlib.sha256(data).hexdigest()


def verify_hmac_signature(archive_digest: str, expected_sig: str, key: str) -> bool:
    """Verify HMAC-SHA256 signature of archive digest.

    Args:
        archive_digest: SHA256 hex digest of archive
        expected_sig: Expected HMAC signature
        key: HMAC key

    Returns:
        True if signature matches
    """
    computed = hmac.new(
        key.encode("utf-8"),
        archive_digest.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(computed, expected_sig)


def get_control_plane_root() -> Path:
    """Get Control Plane root directory.

    Checks environment variable first, then uses script location.
    """
    env_root = os.getenv("CONTROL_PLANE_ROOT")
    if env_root:
        return Path(env_root).resolve()
    return Path(__file__).resolve().parent.parent


def load_seed_registry(seed_path: Path) -> Dict[str, Any]:
    """Load seed registry from JSON file.

    Args:
        seed_path: Path to seed_registry.json

    Returns:
        Parsed seed registry dict

    Raises:
        ValueError: If registry is invalid
    """
    with open(seed_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Validate structure
    if "schema_version" not in data:
        raise ValueError("Seed registry missing schema_version")
    if data["schema_version"] != "1.0":
        raise ValueError(f"Unsupported schema version: {data['schema_version']}")
    if "packages" not in data or not isinstance(data["packages"], list):
        raise ValueError("Seed registry missing packages array")

    return data


def find_package_entry(seed: Dict[str, Any], pkg_id: str) -> Optional[Dict[str, Any]]:
    """Find package entry in seed registry.

    Args:
        seed: Seed registry dict
        pkg_id: Package ID to find

    Returns:
        Package entry dict or None
    """
    for entry in seed.get("packages", []):
        if entry.get("id") == pkg_id:
            return entry
    return None


def write_install_receipt(
    pkg_id: str,
    version: str,
    archive_path: Path,
    files: List[str],
    root: Path,
    installer: str = "genesis_bootstrap"
) -> Path:
    """Write install receipt to installed/<pkg-id>/receipt.json.

    Args:
        pkg_id: Package ID
        version: Package version
        archive_path: Path to source archive
        files: List of installed file paths (relative to root)
        root: Control Plane root
        installer: Name of installer used

    Returns:
        Path to receipt file
    """
    receipt_dir = root / "installed" / pkg_id
    receipt_dir.mkdir(parents=True, exist_ok=True)

    # Compute file hashes
    file_entries = []
    for f in files:
        file_path = root / f
        if file_path.exists() and file_path.is_file():
            file_entries.append({
                "path": f,
                "sha256": sha256_file(file_path)
            })

    receipt = {
        "id": pkg_id,
        "version": version,
        "archive": str(archive_path),
        "archive_digest": sha256_file(archive_path),
        "installed_at": datetime.now(timezone.utc).isoformat(),
        "installer": installer,
        "bootstrap_version": BOOTSTRAP_VERSION,
        "files": file_entries
    }

    receipt_path = receipt_dir / "receipt.json"
    with open(receipt_path, "w", encoding="utf-8") as f:
        json.dump(receipt, f, indent=2)

    return receipt_path


def list_archive_files(archive: Path, root: Path) -> List[str]:
    """List files that will be extracted from archive.

    Args:
        archive: Path to tarball
        root: Target extraction root

    Returns:
        List of relative file paths
    """
    files = []
    with tarfile.open(archive, "r:gz") as tar:
        for member in tar.getmembers():
            if member.isfile():
                # Normalize path (remove ./ prefix if present)
                name = member.name
                if name.startswith("./"):
                    name = name[2:]
                if name and not name.startswith(".."):
                    files.append(name)
    return files


def verify_package(
    archive: Path,
    seed_entry: Dict[str, Any],
    signing_key: Optional[str] = None
) -> Tuple[bool, List[str]]:
    """Verify package archive against seed registry entry.

    Args:
        archive: Path to archive
        seed_entry: Seed registry entry for package
        signing_key: Optional HMAC signing key

    Returns:
        Tuple of (success, list of issues)
    """
    issues = []

    # Verify digest
    expected_digest = seed_entry.get("digest", "")
    if expected_digest:
        actual = sha256_file(archive)
        if actual != expected_digest:
            issues.append(
                f"Digest mismatch: expected={expected_digest[:16]}... "
                f"actual={actual[:16]}..."
            )

    # Verify signature (if key available and signature present)
    sig = seed_entry.get("signature", "")
    if sig:
        if signing_key:
            digest = seed_entry.get("digest") or sha256_file(archive)
            if not verify_hmac_signature(digest, sig, signing_key):
                issues.append("Signature verification failed")
        else:
            issues.append("WARN: Signature present but no key provided")

    return len([i for i in issues if not i.startswith("WARN")]) == 0, issues


def extract_archive(
    archive: Path,
    root: Path,
    force: bool = False
) -> Tuple[bool, List[str]]:
    """Extract archive to Control Plane root.

    Args:
        archive: Path to tarball
        root: Target extraction root
        force: Overwrite existing files if True

    Returns:
        Tuple of (success, list of extracted paths)
    """
    files = []

    with tarfile.open(archive, "r:gz") as tar:
        for member in tar.getmembers():
            # Security: prevent path traversal
            if member.name.startswith("/") or ".." in member.name:
                continue

            # Normalize path
            name = member.name
            if name.startswith("./"):
                name = name[2:]
            if not name:
                continue

            target = root / name

            # Check if target exists
            if target.exists() and not force:
                return False, [f"Target exists: {target} (use --force)"]

            files.append(name)

        # Extract all
        tar.extractall(root)

    return True, files


def install_package(
    archive: Path,
    seed_entry: Dict[str, Any],
    root: Path,
    force: bool = False,
    verify_only: bool = False
) -> int:
    """Install a package from archive.

    Args:
        archive: Path to archive
        seed_entry: Seed registry entry
        root: Control Plane root
        force: Overwrite existing files
        verify_only: Only verify, don't install

    Returns:
        Exit code (0=success, 1=failure)
    """
    pkg_id = seed_entry.get("id", "unknown")
    version = seed_entry.get("version", "0.0.0")
    tier = seed_entry.get("tier", "?")

    print(f"Package: {pkg_id} v{version} ({tier})")
    print(f"  Archive: {archive}")

    # Get signing key from environment
    signing_key = os.getenv("CONTROL_PLANE_SIGNING_KEY")

    # Verify package
    print("  Verifying...")
    valid, issues = verify_package(archive, seed_entry, signing_key)

    for issue in issues:
        if issue.startswith("WARN"):
            print(f"  {issue}")
        else:
            print(f"  ERROR: {issue}")

    if not valid:
        if not force:
            print("  FAIL: Verification failed")
            return 1
        print("  (continuing due to --force)")

    if verify_only:
        if valid:
            print("  VERIFY OK")
            return 0
        print("  VERIFY FAIL")
        return 1

    # Check tier for Genesis constraint (I5-GENESIS-ZERO)
    if tier == "G0":
        deps = seed_entry.get("deps", [])
        if deps:
            print(f"  ERROR: Genesis package has dependencies: {deps}")
            print("  Violates I5-GENESIS-ZERO: Genesis packages must have ZERO deps")
            if not force:
                return 1
            print("  (continuing due to --force)")

    # Extract archive
    print("  Extracting...")
    success, files = extract_archive(archive, root, force)

    if not success:
        print(f"  ERROR: {files[0]}")
        return 1

    print(f"  Extracted {len(files)} files")

    # Write install receipt
    print("  Writing receipt...")
    receipt_path = write_install_receipt(
        pkg_id=pkg_id,
        version=version,
        archive_path=archive,
        files=files,
        root=root,
        installer="genesis_bootstrap"
    )
    print(f"  Receipt: {receipt_path}")

    print(f"  OK: {pkg_id} installed")
    return 0


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Self-contained bootstrapper for Genesis packages",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Install a Genesis package
    python3 scripts/genesis_bootstrap.py \\
        --seed packages_store/seed_registry.json \\
        --archive packages_store/PKG-G0-001_paths.tar.gz

    # Verify without installing
    python3 scripts/genesis_bootstrap.py \\
        --seed packages_store/seed_registry.json \\
        --archive packages_store/PKG-G0-001_paths.tar.gz \\
        --verify-only

    # Force overwrite existing files
    python3 scripts/genesis_bootstrap.py \\
        --seed packages_store/seed_registry.json \\
        --archive packages_store/PKG-G0-001_paths.tar.gz \\
        --force

Environment Variables:
    CONTROL_PLANE_ROOT          Override Control Plane root directory
    CONTROL_PLANE_SIGNING_KEY   HMAC key for signature verification
"""
    )

    parser.add_argument(
        "--seed",
        required=True,
        help="Path to seed registry JSON file"
    )
    parser.add_argument(
        "--archive",
        required=True,
        help="Path to package archive (.tar.gz)"
    )
    parser.add_argument(
        "--id",
        help="Package ID (optional, inferred from archive name)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing files"
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Only verify package, don't install"
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="Show bootstrapper version"
    )

    args = parser.parse_args()

    if args.version:
        print(f"genesis_bootstrap.py v{BOOTSTRAP_VERSION}")
        return 0

    # Get Control Plane root
    root = get_control_plane_root()
    print(f"Control Plane: {root}")

    # Load seed registry
    seed_path = Path(args.seed)
    if not seed_path.is_absolute():
        seed_path = root / seed_path

    if not seed_path.exists():
        print(f"ERROR: Seed registry not found: {seed_path}")
        return 1

    try:
        seed = load_seed_registry(seed_path)
    except (json.JSONDecodeError, ValueError) as e:
        print(f"ERROR: Invalid seed registry: {e}")
        return 1

    # Resolve archive path
    archive = Path(args.archive)
    if not archive.is_absolute():
        archive = root / archive

    archive = archive.resolve()

    if not archive.exists():
        print(f"ERROR: Archive not found: {archive}")
        return 1

    # Determine package ID
    if args.id:
        pkg_id = args.id
    else:
        # Infer from archive name (e.g., PKG-G0-001_paths.tar.gz -> PKG-G0-001)
        name = archive.stem  # removes .gz
        if name.endswith(".tar"):
            name = name[:-4]  # removes .tar
        pkg_id = name.split("_")[0]

    # Find package in seed registry
    entry = find_package_entry(seed, pkg_id)
    if entry is None:
        print(f"ERROR: Package {pkg_id} not in seed registry")
        print(f"  Available: {[p['id'] for p in seed.get('packages', [])]}")
        return 1

    # Install package
    return install_package(
        archive=archive,
        seed_entry=entry,
        root=root,
        force=args.force,
        verify_only=args.verify_only
    )


if __name__ == "__main__":
    raise SystemExit(main())
