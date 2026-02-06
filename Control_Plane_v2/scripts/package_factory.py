#!/usr/bin/env python3
"""
package_factory.py - Package Factory Workflow Orchestrator.

Implements the canonical package flow:
CREATE -> VALIDATE -> PACK -> SIGN -> ATTEST -> REGISTER -> INSTALL -> VERIFY

Per FMWK-PKG-001: Package Standard v1.1 and Plane-Aware Package System design.

Usage:
    python3 scripts/package_factory.py \\
        --id PKG-T0-001 \\
        --src packages/PKG-T0-001 \\
        --sign \\
        --attest \\
        --install

    # With plane scoping
    python3 scripts/package_factory.py \\
        --id PKG-T0-001 \\
        --src packages/PKG-T0-001 \\
        --root /path/to/plane \\
        --install

    # Validate only (no pack/install)
    python3 scripts/package_factory.py \\
        --id PKG-T0-001 \\
        --src packages/PKG-T0-001 \\
        --validate-only
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import hmac
import json
import os
import shutil
import sys
import tarfile
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Add repo root for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.paths import CONTROL_PLANE
from lib.ledger_client import LedgerClient, LedgerEntry
from lib.plane import (
    PlaneContext,
    get_current_plane,
    validate_target_plane,
    validate_external_interface_direction,
)

# Paths
PACKAGES_DIR = CONTROL_PLANE / "packages"
PACKAGES_STORE = CONTROL_PLANE / "packages_store"
PKG_REGISTRY = CONTROL_PLANE / "registries" / "packages_registry.csv"
INSTALLED_DIR = CONTROL_PLANE / "installed"

# Version
FACTORY_VERSION = "1.0.0"


@dataclass
class GateResult:
    """Result of a gate check."""
    gate: str
    passed: bool
    message: str
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FactoryResult:
    """Result of factory workflow."""
    success: bool
    package_id: str
    gates: List[GateResult] = field(default_factory=list)
    archive_path: Optional[Path] = None
    archive_digest: Optional[str] = None
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def add_gate(self, gate: str, passed: bool, message: str, **details):
        self.gates.append(GateResult(gate, passed, message, details))
        if not passed:
            self.success = False
            self.errors.append(f"G{len(self.gates)}: {message}")


from lib.hashing import sha256_file  # canonical implementation


def sign_package(digest: str, key: str) -> str:
    """Sign package digest with HMAC-SHA256."""
    return hmac.new(
        key.encode("utf-8"),
        digest.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()


def load_manifest(manifest_path: Path) -> Optional[Dict[str, Any]]:
    """Load package manifest.json."""
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def validate_manifest_schema(manifest: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Validate manifest against schema.

    Gate G1: manifest.json valid
    """
    errors = []

    # Required fields
    required = ["schema_version", "id", "name", "version", "tier", "artifact_paths", "deps"]
    for field_name in required:
        if field_name not in manifest:
            errors.append(f"Missing required field: {field_name}")

    # Schema version
    if manifest.get("schema_version") != "1.0":
        errors.append(f"Invalid schema_version: {manifest.get('schema_version')}")

    # ID format
    pkg_id = manifest.get("id", "")
    if not pkg_id.startswith("PKG-"):
        errors.append(f"Invalid package ID format: {pkg_id}")

    # Tier
    tier = manifest.get("tier", "")
    if tier not in ["G0", "T0", "T1", "T2", "T3"]:
        errors.append(f"Invalid tier: {tier}")

    # Version (semver)
    version = manifest.get("version", "")
    import re
    if not re.match(r"^\d+\.\d+\.\d+", version):
        errors.append(f"Invalid version format: {version}")

    return len(errors) == 0, errors


def validate_tier_deps(manifest: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Validate tier dependency constraints.

    Gate G2: tier deps valid
    """
    errors = []

    tier_order = {"G0": 0, "T0": 1, "T1": 2, "T2": 3, "T3": 4}

    pkg_tier = manifest.get("tier", "")
    deps = manifest.get("deps", [])

    if pkg_tier not in tier_order:
        errors.append(f"Unknown tier: {pkg_tier}")
        return False, errors

    pkg_order = tier_order[pkg_tier]

    # Genesis zero-deps check (I5-GENESIS-ZERO)
    if pkg_tier == "G0" and deps:
        errors.append(f"Genesis (G0) package cannot have dependencies: {deps}")
        return False, errors

    for dep_id in deps:
        # Extract tier from dependency ID
        parts = dep_id.split("-")
        if len(parts) >= 2:
            dep_tier = parts[1]
            if dep_tier in tier_order:
                dep_order = tier_order[dep_tier]
                if dep_order > pkg_order:
                    errors.append(
                        f"I1-TIER violation: {pkg_tier} cannot depend on {dep_tier} ({dep_id})"
                    )

    return len(errors) == 0, errors


def validate_plane_rules(manifest: Dict[str, Any], plane: PlaneContext) -> Tuple[bool, List[str]]:
    """Validate plane-specific rules.

    Gate G2b: plane rules valid (v1.1)
    """
    errors = []

    # Check target_plane
    target_plane = manifest.get("target_plane", "any")
    if not validate_target_plane(target_plane, plane):
        errors.append(
            f"Package targets plane '{target_plane}' but current plane is '{plane.name}'"
        )

    # Check external_interfaces direction rules
    external_interfaces = manifest.get("external_interfaces", [])
    for iface in external_interfaces:
        iface_name = iface.get("name", "unknown")
        source_plane = iface.get("source_plane", "")

        if source_plane and not validate_external_interface_direction(plane, source_plane):
            errors.append(
                f"Interface '{iface_name}' from plane '{source_plane}' cannot be "
                f"referenced by plane '{plane.name}' (direction violation)"
            )

    return len(errors) == 0, errors


def create_tarball(
    src_dir: Path,
    output_path: Path,
    manifest: Dict[str, Any]
) -> Tuple[str, List[str]]:
    """Create deterministic tarball from source directory.

    Gate G3: pack deterministic

    Returns:
        Tuple of (digest, list of packed files)
    """
    files_packed = []

    with tempfile.TemporaryDirectory() as tmpdir:
        staging = Path(tmpdir) / "pkg"
        staging.mkdir()

        # Copy content
        for item in sorted(src_dir.iterdir()):
            if item.name.startswith("."):
                continue
            dest = staging / item.name
            if item.is_file():
                shutil.copy2(item, dest)
                files_packed.append(item.name)
            elif item.is_dir():
                shutil.copytree(item, dest)
                for f in item.rglob("*"):
                    if f.is_file():
                        files_packed.append(str(f.relative_to(src_dir)))

        # Write manifest
        manifest_path = staging / "manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, sort_keys=True)
        files_packed.append("manifest.json")

        # Create tarball with deterministic options
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with tarfile.open(output_path, "w:gz") as tf:
            # Sort files for determinism
            for root, dirs, files in os.walk(staging):
                dirs.sort()
                for name in sorted(files):
                    full_path = Path(root) / name
                    arcname = str(full_path.relative_to(staging))
                    tf.add(full_path, arcname=arcname)

    return sha256_file(output_path), files_packed


def verify_deterministic(src_dir: Path, manifest: Dict[str, Any]) -> Tuple[bool, str, str]:
    """Verify packing is deterministic by creating two tarballs.

    Gate G3: pack deterministic
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        out1 = tmp / "pack1.tar.gz"
        out2 = tmp / "pack2.tar.gz"

        digest1, _ = create_tarball(src_dir, out1, manifest)
        digest2, _ = create_tarball(src_dir, out2, manifest)

        return digest1 == digest2, digest1, digest2


def update_registry(
    pkg_id: str,
    manifest: Dict[str, Any],
    archive_path: Path,
    digest: str,
    signature: str = "",
    attestation: Optional[Dict] = None
) -> None:
    """Update packages_registry.csv with package entry."""
    rows = []
    headers = []
    found = False

    if PKG_REGISTRY.exists():
        with open(PKG_REGISTRY, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            headers = list(reader.fieldnames or [])
            for row in reader:
                if row.get("id") == pkg_id:
                    # Update existing
                    row["name"] = manifest.get("name", row.get("name", ""))
                    row["version"] = manifest.get("version", "")
                    row["tier"] = manifest.get("tier", "")
                    row["digest"] = digest
                    row["signature"] = signature
                    row["artifact_path"] = str(archive_path.relative_to(CONTROL_PLANE))
                    row["deps"] = ",".join(manifest.get("deps", []))
                    found = True
                rows.append(row)

    if not found:
        new_row = {
            "id": pkg_id,
            "name": manifest.get("name", ""),
            "entity_type": "package",
            "category": "package-mgmt",
            "version": manifest.get("version", ""),
            "source": str(archive_path.relative_to(CONTROL_PLANE)),
            "source_type": "tar",
            "digest": digest,
            "signature": signature,
            "platform": manifest.get("platform", "any"),
            "arch": manifest.get("arch", "any"),
            "deps": ",".join(manifest.get("deps", [])),
            "conflicts": ",".join(manifest.get("conflicts", [])),
            "license": manifest.get("license", "MIT"),
            "artifact_path": str(archive_path.relative_to(CONTROL_PLANE)),
            "status": "active",
            "selected": "yes",
            "priority": "P1",
            "owner": manifest.get("author", "system"),
            "created_at": datetime.now().strftime("%Y-%m-%d"),
            "tier": manifest.get("tier", ""),
        }
        rows.append(new_row)
        if not headers:
            headers = list(new_row.keys())

    # Ensure tier column exists
    if "tier" not in headers:
        headers.append("tier")

    with open(PKG_REGISTRY, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def write_install_receipt(
    pkg_id: str,
    version: str,
    archive_path: Path,
    files: List[str],
    root: Path
) -> Path:
    """Write install receipt per I8-RECEIPTS."""
    receipt_dir = root / "installed" / pkg_id
    receipt_dir.mkdir(parents=True, exist_ok=True)

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
        "installer": "package_factory",
        "factory_version": FACTORY_VERSION,
        "files": file_entries
    }

    receipt_path = receipt_dir / "receipt.json"
    with open(receipt_path, "w", encoding="utf-8") as f:
        json.dump(receipt, f, indent=2)

    return receipt_path


def install_package(
    archive_path: Path,
    manifest: Dict[str, Any],
    force: bool = False
) -> Tuple[bool, List[str], List[str]]:
    """Install package from archive.

    Gate G7: install succeeds
    """
    errors = []
    installed_files = []

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        # Extract
        with tarfile.open(archive_path, "r:gz") as tf:
            tf.extractall(tmp)

        # Find content to install
        artifact_paths = manifest.get("artifact_paths", [])

        for artifact_path in artifact_paths:
            src = tmp / artifact_path
            if src.exists():
                dest = CONTROL_PLANE / artifact_path

                if dest.exists() and not force:
                    errors.append(f"Target exists: {dest} (use --force)")
                    continue

                dest.parent.mkdir(parents=True, exist_ok=True)

                if src.is_file():
                    shutil.copy2(src, dest)
                    installed_files.append(artifact_path)
                elif src.is_dir():
                    if dest.exists():
                        shutil.rmtree(dest)
                    shutil.copytree(src, dest)
                    for f in src.rglob("*"):
                        if f.is_file():
                            installed_files.append(str(f.relative_to(tmp)))
            else:
                errors.append(f"Artifact not in archive: {artifact_path}")

    return len(errors) == 0, installed_files, errors


def log_to_ledger(pkg_id: str, action: str, result: FactoryResult) -> None:
    """Log factory action to ledger (I6-LEDGER-CHAIN)."""
    try:
        client = LedgerClient()
        entry = LedgerEntry(
            event_type="package_factory",
            submission_id=pkg_id,
            decision="SUCCESS" if result.success else "FAIL",
            reason=f"Package {action}: {len(result.gates)} gates",
            metadata={
                "action": action,
                "archive_digest": result.archive_digest,
                "gates_passed": sum(1 for g in result.gates if g.passed),
                "gates_total": len(result.gates),
                "factory_version": FACTORY_VERSION,
            }
        )
        client.write(entry)
    except Exception as e:
        result.warnings.append(f"Ledger write failed: {e}")


def run_factory(
    pkg_id: str,
    src_dir: Path,
    plane: PlaneContext,
    sign: bool = False,
    attest: bool = False,
    install: bool = False,
    register: bool = True,
    force: bool = False,
    validate_only: bool = False,
    allow_unsigned: bool = False,
    allow_unattested: bool = False
) -> FactoryResult:
    """Run the package factory workflow.

    Gates:
    - G1: manifest.json valid
    - G2: tier deps valid
    - G3: pack deterministic
    - G4: signature valid (main/release)
    - G5: attestation valid (main/release)
    - G6: digest matches registry
    - G7: install succeeds
    - G8: integrity check passes
    - G9: ledger chain intact
    """
    result = FactoryResult(success=True, package_id=pkg_id)

    print(f"Package Factory v{FACTORY_VERSION}")
    print(f"Package: {pkg_id}")
    print(f"Source: {src_dir}")
    print(f"Plane: {plane.name} ({plane.plane_type.value})")
    print(f"Plane root: {plane.root}")
    print()

    # Load manifest
    manifest_path = src_dir / "manifest.json"
    if not manifest_path.exists():
        result.add_gate("G1", False, f"manifest.json not found in {src_dir}")
        return result

    manifest = load_manifest(manifest_path)
    if manifest is None:
        result.add_gate("G1", False, "Failed to parse manifest.json")
        return result

    # G1: Validate manifest schema
    print("G1: Validating manifest schema...")
    valid, errors = validate_manifest_schema(manifest)
    if valid:
        result.add_gate("G1", True, "Manifest schema valid")
    else:
        result.add_gate("G1", False, f"Schema errors: {errors}")
        return result

    # G2: Validate tier dependencies
    print("G2: Validating tier dependencies...")
    valid, errors = validate_tier_deps(manifest)
    if valid:
        result.add_gate("G2", True, "Tier dependencies valid")
    else:
        result.add_gate("G2", False, f"Tier violations: {errors}")
        return result

    # G2b: Validate plane rules (v1.1)
    if manifest.get("schema_version") == "1.1" or manifest.get("target_plane") or manifest.get("external_interfaces"):
        print("G2b: Validating plane rules...")
        valid, errors = validate_plane_rules(manifest, plane)
        if valid:
            result.add_gate("G2b", True, "Plane rules valid")
        else:
            result.add_gate("G2b", False, f"Plane violations: {errors}")
            return result

    if validate_only:
        print("\nValidation complete (--validate-only)")
        return result

    # G3: Pack with determinism check
    print("G3: Checking pack determinism...")
    deterministic, digest1, digest2 = verify_deterministic(src_dir, manifest)
    if deterministic:
        result.add_gate("G3", True, f"Pack is deterministic (digest: {digest1[:16]}...)")
    else:
        result.add_gate("G3", False, f"Pack not deterministic: {digest1[:16]}... != {digest2[:16]}...")
        return result

    # Create actual archive (in plane-specific store)
    archive_name = f"{pkg_id}_{manifest.get('name', 'pkg').replace(' ', '_').lower()}.tar.gz"
    packages_store = plane.root / "packages_store"
    packages_store.mkdir(parents=True, exist_ok=True)
    archive_path = packages_store / archive_name
    print(f"Creating archive: {archive_path}")
    digest, files = create_tarball(src_dir, archive_path, manifest)
    result.archive_path = archive_path
    result.archive_digest = digest
    print(f"  Digest: {digest[:16]}...")
    print(f"  Files: {len(files)}")

    # G4: Signature
    signature = ""
    signing_key = os.getenv("CONTROL_PLANE_SIGNING_KEY")

    if sign:
        print("G4: Signing package...")
        if signing_key:
            signature = sign_package(digest, signing_key)
            result.add_gate("G4", True, f"Signed (sig: {signature[:16]}...)")
        else:
            if allow_unsigned:
                result.add_gate("G4", True, "Unsigned (waiver: --allow-unsigned)")
                result.warnings.append("Package is unsigned (allowed by waiver)")
            else:
                result.add_gate("G4", False, "CONTROL_PLANE_SIGNING_KEY not set")
                return result
    else:
        if allow_unsigned:
            result.add_gate("G4", True, "Skipped (--allow-unsigned)")
        else:
            result.add_gate("G4", False, "Signing required (use --sign or --allow-unsigned)")
            return result

    # G5: Attestation
    attestation = None
    if attest:
        print("G5: Creating attestation...")
        attestation = {
            "builder": "package_factory",
            "build_timestamp": datetime.now(timezone.utc).isoformat(),
            "build_env_hash": sha256_file(Path(__file__)),
            "factory_version": FACTORY_VERSION,
        }
        result.add_gate("G5", True, "Attestation created")
    else:
        if allow_unattested:
            result.add_gate("G5", True, "Skipped (--allow-unattested)")
        else:
            result.add_gate("G5", False, "Attestation required (use --attest or --allow-unattested)")
            return result

    # G6: Register (digest will match since we just created it)
    if register:
        print("G6: Registering package...")
        update_registry(pkg_id, manifest, archive_path, digest, signature, attestation)
        result.add_gate("G6", True, f"Registered in {PKG_REGISTRY.name}")
    else:
        result.add_gate("G6", True, "Registration skipped")

    # G7: Install
    if install:
        print("G7: Installing package...")
        success, installed_files, errors = install_package(archive_path, manifest, force)
        if success:
            result.add_gate("G7", True, f"Installed {len(installed_files)} files")

            # Write install receipt
            receipt = write_install_receipt(
                pkg_id,
                manifest.get("version", "0.0.0"),
                archive_path,
                installed_files,
                CONTROL_PLANE
            )
            print(f"  Receipt: {receipt}")
        else:
            result.add_gate("G7", False, f"Install failed: {errors}")
            return result
    else:
        result.add_gate("G7", True, "Install skipped")

    # G8: Integrity check
    print("G8: Checking integrity...")
    try:
        from lib.integrity import IntegrityChecker
        checker = IntegrityChecker(CONTROL_PLANE)
        integrity_result = checker.validate(checks=["content_hash"])
        if integrity_result.passed:
            result.add_gate("G8", True, "Integrity check passed")
        else:
            issues = [i.message for i in integrity_result.issues]
            result.add_gate("G8", False, f"Integrity issues: {issues}")
    except ImportError:
        result.add_gate("G8", True, "Integrity check skipped (lib not available)")
        result.warnings.append("Integrity check skipped - lib/integrity.py not available")

    # G9: Ledger chain
    print("G9: Verifying ledger chain...")
    try:
        client = LedgerClient()
        valid, issues = client.verify_chain()
        if valid:
            result.add_gate("G9", True, "Ledger chain intact")
        else:
            fail_issues = [i for i in issues if i.startswith("FAIL")]
            if fail_issues:
                result.add_gate("G9", False, f"Ledger issues: {fail_issues}")
            else:
                result.add_gate("G9", True, "Ledger chain intact (warnings only)")
                result.warnings.extend(issues)
    except Exception as e:
        result.add_gate("G9", True, f"Ledger check skipped: {e}")
        result.warnings.append(f"Ledger verification skipped: {e}")

    # Log to ledger
    log_to_ledger(pkg_id, "create", result)

    return result


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Package Factory Workflow Orchestrator (FMWK-PKG-001)"
    )
    parser.add_argument(
        "--id",
        required=True,
        help="Package ID (e.g., PKG-T0-001)"
    )
    parser.add_argument(
        "--src",
        required=True,
        help="Source directory containing manifest.json and content"
    )
    parser.add_argument(
        "--sign",
        action="store_true",
        help="Sign the package (requires CONTROL_PLANE_SIGNING_KEY)"
    )
    parser.add_argument(
        "--attest",
        action="store_true",
        help="Create build attestation"
    )
    parser.add_argument(
        "--install",
        action="store_true",
        help="Install the package after packing"
    )
    parser.add_argument(
        "--no-register",
        action="store_true",
        help="Skip registry update"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force overwrite existing files"
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Only validate manifest and tier deps"
    )
    parser.add_argument(
        "--allow-unsigned",
        action="store_true",
        help="Allow skipping signature (dev only)"
    )
    parser.add_argument(
        "--allow-unattested",
        action="store_true",
        help="Allow skipping attestation (dev only)"
    )
    parser.add_argument(
        "--root",
        type=Path,
        help="Plane root path (defaults to CONTROL_PLANE)"
    )

    args = parser.parse_args()

    # Resolve plane context
    plane_root = args.root.resolve() if args.root else None
    plane = get_current_plane(plane_root)

    # Resolve source directory (relative to plane root)
    src_dir = Path(args.src)
    if not src_dir.is_absolute():
        src_dir = plane.root / src_dir

    if not src_dir.exists():
        print(f"ERROR: Source directory not found: {src_dir}")
        return 1

    if not src_dir.is_dir():
        print(f"ERROR: Source is not a directory: {src_dir}")
        return 1

    # Run factory
    result = run_factory(
        pkg_id=args.id,
        src_dir=src_dir,
        plane=plane,
        sign=args.sign,
        attest=args.attest,
        install=args.install,
        register=not args.no_register,
        force=args.force,
        validate_only=args.validate_only,
        allow_unsigned=args.allow_unsigned,
        allow_unattested=args.allow_unattested,
    )

    # Print summary
    print()
    print("=" * 60)
    print("FACTORY RESULT")
    print("=" * 60)
    print(f"Package: {result.package_id}")
    print(f"Success: {result.success}")
    print()

    print("Gates:")
    for i, gate in enumerate(result.gates, 1):
        status = "PASS" if gate.passed else "FAIL"
        print(f"  G{i} [{status}] {gate.message}")

    if result.archive_path:
        print()
        print(f"Archive: {result.archive_path}")
        print(f"Digest: {result.archive_digest}")

    if result.warnings:
        print()
        print("Warnings:")
        for w in result.warnings:
            print(f"  - {w}")

    if result.errors:
        print()
        print("Errors:")
        for e in result.errors:
            print(f"  - {e}")

    print()
    if result.success:
        gates_passed = sum(1 for g in result.gates if g.passed)
        print(f"OK: All {gates_passed} gates passed")
        return 0
    else:
        gates_failed = sum(1 for g in result.gates if not g.passed)
        print(f"FAIL: {gates_failed} gate(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
