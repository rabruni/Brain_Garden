#!/usr/bin/env python3
"""
package_install.py - Install a package into Control Plane v2.

Phase 1B Implementation (CP-IMPL-001):
- Workspace+atomic execution: extract to temp, validate, then atomic copy
- Two-phase ledger: INSTALL_STARTED → INSTALLED | INSTALL_FAILED
- Gate enforcement: G0A+G1+G5 fail-closed pre-commit
- Receipts to installed/<pkg>/; files to pristine roots

BINDING CONSTRAINTS:
- HO3-only scope for Phase 1
- Hash format: sha256:<64hex> everywhere
- Ledger is Memory: INSTALL_STARTED → INSTALLED | INSTALL_FAILED
- No last-write-wins: ownership conflicts = FAIL
- Pristine roots are install destinations; installed/<pkg>/ is receipts only

Usage:
    python3 scripts/package_install.py --archive PATH --id PKG-ID [--force] [--root /path]

    # Dry run (validate only)
    python3 scripts/package_install.py --archive PATH --id PKG-ID --dry-run
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.paths import CONTROL_PLANE
from lib.plane import (
    PlaneContext,
    get_current_plane,
    validate_target_plane,
    validate_external_interface_direction,
)
from lib.install_auth import InstallerClaims, require_authorization
from lib.packages import unpack, verify, sha256_file
from lib.auth import get_provider
from lib import authz
from lib.package_audit import PackageContext, log_package_event
from lib.pristine import (
    InstallModeContext,
    assert_write_allowed,
    assert_inside_control_plane,
    OutsideBoundaryViolation,
    WriteMode,
)
from lib.signing import (
    has_signature,
    verify_detached,
    SignatureMissing,
    SignatureVerificationFailed,
)
from lib.provenance import (
    has_attestation,
    verify_attestation,
    log_attestation_waiver,
    AttestationMissing,
    AttestationVerificationFailed,
    AttestationDigestMismatch,
)
from lib.ledger_client import LedgerClient, LedgerEntry, TierContext
# Import shared preflight validators (single source of truth)
from lib.preflight import (
    PackageDeclarationValidator,
    ChainValidator,
    OwnershipValidator,
    SignatureValidator,
    load_file_ownership as preflight_load_file_ownership,
    compute_sha256 as preflight_compute_sha256,
)


# === Constants ===
PKG_REG = CONTROL_PLANE / "registries" / "packages_registry.csv"
L_PACKAGE_LEDGER = CONTROL_PLANE / "ledger" / "packages.jsonl"
FILE_OWNERSHIP_CSV = CONTROL_PLANE / "registries" / "file_ownership.csv"


class InstallError(Exception):
    """Package installation error."""
    pass


class GateFailure(InstallError):
    """Gate check failed (fail-closed)."""
    pass


class OwnershipConflict(InstallError):
    """File ownership conflict (no last-write-wins)."""
    pass


class HashMismatch(InstallError):
    """File hash does not match manifest."""
    pass


from lib.hashing import compute_sha256  # canonical implementation


def compute_manifest_hash(manifest: dict) -> str:
    """Compute deterministic hash of manifest, EXCLUDING metadata block."""
    hashable = {k: v for k, v in manifest.items() if k != "metadata"}
    canonical = json.dumps(hashable, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def load_manifest_from_archive(archive_path: Path) -> dict | None:
    """Extract and load manifest.json from archive."""
    try:
        with tarfile.open(archive_path, "r:gz") as tf:
            for member in tf.getmembers():
                if member.name.endswith("manifest.json"):
                    f = tf.extractfile(member)
                    if f:
                        return json.load(f)
    except (tarfile.TarError, json.JSONDecodeError, IOError):
        return None
    return None


def load_file_ownership() -> Dict[str, dict]:
    """Load file ownership registry as dict keyed by file_path.

    Uses shared lib/preflight.py implementation for consistency.
    """
    return preflight_load_file_ownership(CONTROL_PLANE)


def get_ledger_client() -> LedgerClient:
    """Get ledger client for L-PACKAGE in HO3 context."""
    tier_context = TierContext(
        tier="HO3",
        plane_root=CONTROL_PLANE,
    )
    return LedgerClient(
        ledger_path=L_PACKAGE_LEDGER,
        tier_context=tier_context,
    )


def write_ledger_entry(
    event_type: str,
    package_id: str,
    manifest_hash: Optional[str] = None,
    error: Optional[str] = None,
    work_order_id: Optional[str] = None,
    assets_count: Optional[int] = None,
    package_type: Optional[str] = None,
    plane_id: str = "ho3",
) -> str:
    """
    Write L-PACKAGE ledger entry.

    Returns entry ID.
    """
    client = get_ledger_client()

    metadata = {
        "package_type": package_type or "standard",
        "plane_id": plane_id,
        "ledger_type": "L-PACKAGE",
    }

    if manifest_hash:
        metadata["manifest_hash"] = manifest_hash
    if error:
        metadata["error"] = error
    if work_order_id:
        metadata["work_order_id"] = work_order_id
    if assets_count is not None:
        metadata["assets_count"] = assets_count

    entry = LedgerEntry(
        event_type=event_type,
        submission_id=package_id,
        decision=event_type,
        reason=f"Package {event_type.lower().replace('_', ' ')}",
        metadata=metadata,
    )

    entry_id = client.write(entry)
    client.flush()

    return entry_id


# =============================================================================
# Gate Implementations (using shared lib/preflight.py validators)
# =============================================================================

# Shared validator instances
_g0a_validator = PackageDeclarationValidator()
_g1_validator = ChainValidator(CONTROL_PLANE)
_ownership_validator = OwnershipValidator()
_g5_validator = SignatureValidator()


def check_g0a_package_declaration(
    manifest: dict,
    workspace_files: Dict[str, Path]
) -> Tuple[bool, List[str]]:
    """
    G0A: PACKAGE DECLARATION - Verify package is internally consistent.

    Uses shared lib/preflight.py validator for consistency with pkgutil preflight.

    Returns (passed, errors)
    """
    result = _g0a_validator.validate(manifest, workspace_files)
    # Prepend "G0A: " to errors for backward compatibility with existing code
    errors = [f"G0A: {e}" if not e.startswith("G0A") else e for e in result.errors]
    return result.passed, errors


def check_g1_chain(manifest: dict, plane_root: Path, strict: bool = True) -> Tuple[bool, List[str]]:
    """
    G1: CHAIN - Verify package dependencies exist.

    Uses shared lib/preflight.py validator for consistency with pkgutil preflight.

    Args:
        manifest: Package manifest dict
        plane_root: Path to plane root
        strict: If True (default), require spec_id. Set False for isolated testing.

    Returns (passed, errors)
    """
    validator = ChainValidator(plane_root, strict=strict)
    result = validator.validate(manifest)
    errors = [f"G1: {e}" if not e.startswith("G1") else e for e in result.errors]
    return result.passed, errors


def check_g5_signature(
    archive_path: Path,
    manifest: dict,
    allow_unsigned: bool = False
) -> Tuple[bool, List[str]]:
    """
    G5: SIGNATURE - Verify package signature.

    Uses shared lib/preflight.py validator for consistency with pkgutil preflight.

    Returns (passed, errors)
    """
    result = _g5_validator.validate(archive_path, manifest, allow_unsigned)
    errors = [f"G5: {e}" if not e.startswith("G5") else e for e in result.errors]
    return result.passed, errors


def check_ownership_conflicts(
    manifest: dict,
    existing_ownership: Dict[str, dict],
    package_id: str,
    plane_root: Optional[Path] = None,
) -> Tuple[bool, List[str]]:
    """
    Check for ownership conflicts (no last-write-wins).

    Uses shared lib/preflight.py validator for consistency with pkgutil preflight.
    Dependency-aware: declared dependencies allow ownership transfers.

    Returns (passed, errors)
    """
    result = _ownership_validator.validate(manifest, existing_ownership, package_id, plane_root)
    return result.passed, result.errors


# =============================================================================
# Installation Functions
# =============================================================================

def extract_to_workspace(archive_path: Path, workspace_dir: Path) -> Dict[str, Path]:
    """
    Extract archive to isolated workspace.

    Returns dict mapping relative paths to workspace paths.
    """
    with tarfile.open(archive_path, "r:gz") as tar:
        tar.extractall(workspace_dir)

    # Build file map (skip manifest/signature files)
    workspace_files = {}
    for file_path in workspace_dir.rglob('*'):
        if file_path.is_dir():
            continue

        rel_path = file_path.relative_to(workspace_dir)
        parts = rel_path.parts

        # Skip package wrapper directory if present
        if len(parts) > 1 and parts[0].startswith('PKG-'):
            rel_path = Path(*parts[1:])

        # Skip metadata files
        if rel_path.name in ('manifest.json', 'signature.json', 'checksums.sha256'):
            continue

        workspace_files[str(rel_path)] = file_path

    return workspace_files


def atomic_copy_files(
    workspace_files: Dict[str, Path],
    dest_root: Path,
    force: bool = False
) -> List[Path]:
    """
    Atomically copy files from workspace to destination.

    Uses temporary files + rename for atomicity.
    Returns list of installed paths.
    """
    installed = []

    for rel_path, workspace_path in workspace_files.items():
        dest_path = dest_root / rel_path

        # Check for existing files
        if dest_path.exists() and not force:
            raise InstallError(f"Target exists: {dest_path} (use --force to overwrite)")

        # Create parent directories
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        # Atomic copy: write to temp then rename
        temp_path = dest_path.with_suffix(dest_path.suffix + '.tmp')
        try:
            shutil.copy2(workspace_path, temp_path)
            temp_path.rename(dest_path)
            installed.append(dest_path)
        except Exception as e:
            # Clean up temp file if exists
            if temp_path.exists():
                temp_path.unlink()
            raise InstallError(f"Failed to install {rel_path}: {e}") from e

    return installed


def write_receipt(
    package_id: str,
    manifest: dict,
    archive_path: Path,
    installed_files: List[Path],
    plane_root: Path,
    work_order_id: Optional[str] = None,
) -> Path:
    """
    Write installation receipt to installed/<pkg_id>/.

    Returns receipt path.
    """
    receipt_dir = plane_root / "installed" / package_id
    receipt_dir.mkdir(parents=True, exist_ok=True)

    manifest_hash = compute_manifest_hash(manifest)

    # Build file list with hashes
    file_entries = []
    for file_path in installed_files:
        if file_path.exists() and file_path.is_file():
            file_entries.append({
                "path": str(file_path.relative_to(plane_root)),
                "sha256": compute_sha256(file_path)
            })

    receipt = {
        "package_id": package_id,
        "origin": "BUILDER" if manifest.get("package_type") == "baseline" else "INSTALLER",
        "package_type": manifest.get("package_type", "standard"),
        "plane_id": "ho3",  # Phase 1 is HO3-only
        "installed_at": datetime.now(timezone.utc).isoformat(),
        "manifest_hash": manifest_hash,
        "archive_hash": compute_sha256(archive_path),
        "assets_count": len(file_entries),
        "work_order_id": work_order_id,
        "schema_version": manifest.get("schema_version", "1.0"),
        "version": manifest.get("version", "0.0.0"),
        "receipt_version": "1.0",
        "files": file_entries,
    }

    receipt_path = receipt_dir / "receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2))

    # Also copy manifest for reference
    manifest_path = receipt_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))

    return receipt_path


def install_package(
    archive_path: Path,
    package_id: str,
    plane_root: Path,
    force: bool = False,
    dry_run: bool = False,
    work_order_id: Optional[str] = None,
    allow_unsigned: bool = False,
    allow_unattested: bool = False,
    actor: str = "",
) -> dict:
    """
    Install a package with full gate enforcement.

    Phase 1B workflow:
    1. Write INSTALL_STARTED to ledger
    2. Extract to isolated workspace
    3. Validate G0A (package declaration)
    4. Validate G1 (chain)
    5. Validate G5 (signature)
    6. Check ownership conflicts
    7. Atomic copy to pristine roots
    8. Write receipt to installed/<pkg>/
    9. Write INSTALLED to ledger

    On any failure:
    - Write INSTALL_FAILED to ledger
    - Clean up workspace
    - Raise exception

    Args:
        archive_path: Path to package archive
        package_id: Package ID
        plane_root: Path to plane root
        force: Allow overwriting existing files
        dry_run: Validate only, don't install
        work_order_id: Work Order ID (if applicable)
        allow_unsigned: Allow unsigned packages
        allow_unattested: Allow unattested packages
        actor: Actor/user ID for audit

    Returns:
        Result dict with status and details
    """
    # Load manifest first
    manifest = load_manifest_from_archive(archive_path)
    if manifest is None:
        raise InstallError(f"Could not load manifest from archive: {archive_path}")

    manifest_hash = compute_manifest_hash(manifest)
    package_type = manifest.get('package_type', 'standard')

    # Write INSTALL_STARTED to ledger
    write_ledger_entry(
        event_type="INSTALL_STARTED",
        package_id=package_id,
        work_order_id=work_order_id,
        package_type=package_type,
    )
    print(f"[install] Wrote INSTALL_STARTED to L-PACKAGE", file=sys.stderr)

    workspace_dir = None
    try:
        # Create isolated workspace
        workspace_dir = Path(tempfile.mkdtemp(prefix=f"cp-install-{package_id}-"))
        print(f"[install] Workspace: {workspace_dir}", file=sys.stderr)

        # Extract to workspace
        workspace_files = extract_to_workspace(archive_path, workspace_dir)
        print(f"[install] Extracted {len(workspace_files)} files to workspace", file=sys.stderr)

        # === GATE G0A: Package Declaration ===
        print(f"[install] Running G0A (package declaration)...", file=sys.stderr)
        g0a_passed, g0a_errors = check_g0a_package_declaration(manifest, workspace_files)
        if not g0a_passed:
            error_msg = "G0A FAILED:\n" + "\n".join(g0a_errors[:10])
            raise GateFailure(error_msg)
        print(f"[install] G0A PASSED", file=sys.stderr)

        # === GATE G1: Chain ===
        print(f"[install] Running G1 (chain)...", file=sys.stderr)
        g1_passed, g1_errors = check_g1_chain(manifest, plane_root)
        if not g1_passed:
            error_msg = "G1 FAILED:\n" + "\n".join(g1_errors[:10])
            raise GateFailure(error_msg)
        print(f"[install] G1 PASSED", file=sys.stderr)

        # === GATE G5: Signature ===
        print(f"[install] Running G5 (signature)...", file=sys.stderr)
        g5_passed, g5_errors = check_g5_signature(archive_path, manifest, allow_unsigned)
        if g5_passed:
            print(f"[install] G5 PASSED", file=sys.stderr)
        elif allow_unsigned:
            print(f"[install] G5 WAIVED (unsigned allowed)", file=sys.stderr)
        else:
            raise GateFailure("G5 FAILED:\n" + "\n".join(g5_errors[:10]))

        # Check attestation
        if has_attestation(archive_path):
            try:
                valid, att = verify_attestation(archive_path)
                print(f"[install] Attestation verified: {att.builder.tool}", file=sys.stderr)
            except (AttestationVerificationFailed, AttestationDigestMismatch) as e:
                raise GateFailure(f"Attestation verification failed: {e}")
        elif not allow_unattested:
            raise GateFailure("Package missing attestation (set CONTROL_PLANE_ALLOW_UNATTESTED=1 to allow)")
        else:
            print(f"[install] Attestation waived", file=sys.stderr)

        # === Check Ownership Conflicts ===
        print(f"[install] Checking ownership conflicts...", file=sys.stderr)
        existing_ownership = load_file_ownership()
        ownership_passed, ownership_errors = check_ownership_conflicts(
            manifest, existing_ownership, package_id, plane_root
        )
        if not ownership_passed:
            error_msg = "OWNERSHIP CONFLICT:\n" + "\n".join(ownership_errors[:10])
            raise OwnershipConflict(error_msg)
        print(f"[install] No ownership conflicts", file=sys.stderr)

        if dry_run:
            print(f"\n[install] DRY RUN - validation passed, no files copied", file=sys.stderr)
            return {
                "success": True,
                "dry_run": True,
                "package_id": package_id,
                "manifest_hash": manifest_hash,
                "assets_count": len(workspace_files),
            }

        # === Atomic Copy to Pristine Roots ===
        print(f"[install] Copying files to {plane_root}...", file=sys.stderr)
        with InstallModeContext():
            # Verify each target path is allowed
            for rel_path in workspace_files:
                target = plane_root / rel_path
                assert_write_allowed(target, mode=WriteMode.INSTALL)

            installed_files = atomic_copy_files(workspace_files, plane_root, force)

        print(f"[install] Installed {len(installed_files)} files", file=sys.stderr)

        # Write receipt to installed/<pkg>/
        receipt_path = write_receipt(
            package_id=package_id,
            manifest=manifest,
            archive_path=archive_path,
            installed_files=installed_files,
            plane_root=plane_root,
            work_order_id=work_order_id,
        )
        print(f"[install] Receipt: {receipt_path}", file=sys.stderr)

        # Write INSTALLED to ledger
        write_ledger_entry(
            event_type="INSTALLED",
            package_id=package_id,
            manifest_hash=manifest_hash,
            work_order_id=work_order_id,
            assets_count=len(installed_files),
            package_type=package_type,
        )
        print(f"[install] Wrote INSTALLED to L-PACKAGE", file=sys.stderr)

        return {
            "success": True,
            "package_id": package_id,
            "manifest_hash": manifest_hash,
            "assets_count": len(installed_files),
            "receipt_path": str(receipt_path),
            "version": manifest.get("version", "0.0.0"),
        }

    except (GateFailure, OwnershipConflict, InstallError) as e:
        # Write INSTALL_FAILED to ledger
        write_ledger_entry(
            event_type="INSTALL_FAILED",
            package_id=package_id,
            error=str(e)[:500],
            work_order_id=work_order_id,
            package_type=package_type,
        )
        raise

    except Exception as e:
        # Write INSTALL_FAILED for unexpected errors
        write_ledger_entry(
            event_type="INSTALL_FAILED",
            package_id=package_id,
            error=f"Unexpected: {str(e)[:400]}",
            work_order_id=work_order_id,
            package_type=package_type,
        )
        raise InstallError(f"Unexpected error: {e}") from e

    finally:
        # Clean up workspace
        if workspace_dir and workspace_dir.exists():
            shutil.rmtree(workspace_dir, ignore_errors=True)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Install a package into Control Plane v2",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Phase 1B Implementation (CP-IMPL-001):
- Workspace+atomic: Extract to temp, validate gates, then atomic copy
- Two-phase ledger: INSTALL_STARTED → INSTALLED | INSTALL_FAILED
- Gate enforcement: G0A (declaration) + G1 (chain) + G5 (signature) fail-closed
- Receipts: installed/<pkg>/receipt.json

Examples:
    # Install a package
    python3 scripts/package_install.py --archive packages_store/PKG-TEST.tar.gz --id PKG-TEST

    # Dry run (validate only)
    python3 scripts/package_install.py --archive packages_store/PKG-TEST.tar.gz --id PKG-TEST --dry-run

    # Force reinstall (overwrite existing)
    python3 scripts/package_install.py --archive packages_store/PKG-TEST.tar.gz --id PKG-TEST --force
"""
    )
    ap.add_argument("--archive", required=True, type=Path, help="Package archive path")
    ap.add_argument("--id", required=True, dest="package_id", help="Package ID")
    ap.add_argument("--force", action="store_true", help="Overwrite existing files")
    ap.add_argument("--dry-run", action="store_true", help="Validate only, don't install")
    ap.add_argument("--root", type=Path, help="Plane root path (defaults to CONTROL_PLANE)")
    ap.add_argument("--work-order", dest="work_order", help="Work Order ID")
    ap.add_argument("--actor", help="Actor/user ID for audit", default="")
    ap.add_argument("--token", help="Auth token (optional)")
    ap.add_argument("--json", action="store_true", help="Output result as JSON")
    ap.add_argument("--dev", action="store_true",
        help="Dev mode: bypass auth, signatures, attestation")
    args = ap.parse_args()

    # Resolve plane root
    plane_root = args.root.resolve() if args.root else CONTROL_PLANE

    # Get environment settings
    allow_unsigned = os.getenv("CONTROL_PLANE_ALLOW_UNSIGNED", "0") == "1"
    allow_unattested = os.getenv("CONTROL_PLANE_ALLOW_UNATTESTED", "0") == "1"

    # AuthZ
    if args.dev:
        print("[install] DEV MODE — auth, signature, and attestation checks bypassed", file=sys.stderr)
        allow_unsigned = True
        allow_unattested = True
        identity = None
    else:
        try:
            identity = get_provider().authenticate(args.token or os.getenv("CONTROL_PLANE_TOKEN"))
            authz.require(identity, "install")
        except Exception as e:
            print(f"Authorization failed: {e}", file=sys.stderr)
            return 1

    # Validate archive exists
    archive = args.archive.resolve()
    if not archive.exists():
        print(f"Archive not found: {archive}", file=sys.stderr)
        return 1

    try:
        result = install_package(
            archive_path=archive,
            package_id=args.package_id,
            plane_root=plane_root,
            force=args.force,
            dry_run=args.dry_run,
            work_order_id=args.work_order,
            allow_unsigned=allow_unsigned,
            allow_unattested=allow_unattested,
            actor=args.actor or (identity.user if identity else "dev"),
        )

        if args.json:
            print(json.dumps(result, indent=2))
        else:
            if result.get("dry_run"):
                print(f"\nDry run passed!")
            else:
                print(f"\nPackage installed successfully!")
            print(f"  Package ID:    {result['package_id']}")
            print(f"  Manifest Hash: {result['manifest_hash']}")
            print(f"  Assets:        {result['assets_count']}")
            if result.get("receipt_path"):
                print(f"  Receipt:       {result['receipt_path']}")
            print(f"\nNext: run `python3 scripts/rebuild_derived_registries.py --plane ho3` to update file ownership")

        return 0

    except GateFailure as e:
        print(f"\nGATE FAILURE (fail-closed):", file=sys.stderr)
        print(str(e), file=sys.stderr)
        return 2

    except OwnershipConflict as e:
        print(f"\nOWNERSHIP CONFLICT (no last-write-wins):", file=sys.stderr)
        print(str(e), file=sys.stderr)
        return 3

    except InstallError as e:
        print(f"\nINSTALL ERROR:", file=sys.stderr)
        print(str(e), file=sys.stderr)
        return 1

    except Exception as e:
        print(f"\nUNEXPECTED ERROR:", file=sys.stderr)
        print(str(e), file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 99


if __name__ == "__main__":
    raise SystemExit(main())
