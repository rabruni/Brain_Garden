#!/usr/bin/env python3
"""
Install Baseline Package for Control Plane v2

Installs the baseline package that claims ownership of all existing
governed files in HO3. This is the first step to seal the plane.

BINDING CONSTRAINTS (from CP-IMPL-001):
- HO3-only scope: operates in HO3 governance context
- Pre-seal: baseline install is the single bootstrap exception
- Post-seal: requires Work Order with type=baseline_refresh
- Ledger is Memory: writes INSTALL_STARTED → INSTALLED | INSTALL_FAILED to L-PACKAGE
- Turn isolation: verifies only declared inputs from manifest metadata
- Receipts are proof; ledger is truth spine

Usage:
    # Pre-seal (first time)
    python3 scripts/install_baseline.py --plane ho3

    # Post-seal (refresh) - requires Work Order
    python3 scripts/install_baseline.py --plane ho3 --work-order WO-20260202-001
"""

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Resolve paths relative to Control_Plane_v2 root
SCRIPT_DIR = Path(__file__).resolve().parent
CONTROL_PLANE_ROOT = SCRIPT_DIR.parent

# Add lib to path for imports
sys.path.insert(0, str(CONTROL_PLANE_ROOT))

from kernel.ledger_client import LedgerClient, LedgerEntry, TierContext


# === Constants ===
L_PACKAGE_LEDGER = CONTROL_PLANE_ROOT / "ledger" / "packages.jsonl"
SEAL_FILE = CONTROL_PLANE_ROOT / "config" / "seal.json"


class InstallError(Exception):
    """Baseline installation error."""
    pass


class SealedPlaneError(InstallError):
    """Plane is sealed and no valid Work Order provided."""
    pass


class WorkOrderError(InstallError):
    """Work Order validation error."""
    pass


class HashMismatchError(InstallError):
    """File hash does not match manifest."""
    pass


class MissingFileError(InstallError):
    """File declared in manifest does not exist."""
    pass


class DeclaredInputsViolation(InstallError):
    """Manifest metadata does not match current governed_roots.json."""
    pass


def is_sealed() -> bool:
    """Check if plane is sealed."""
    if not SEAL_FILE.exists():
        return False
    try:
        seal = json.loads(SEAL_FILE.read_text())
        return seal.get("sealed", False)
    except Exception:
        return False


def validate_work_order(work_order_id: str) -> dict:
    """
    Validate Work Order exists and has type=baseline_refresh.

    Returns the Work Order dict if valid.
    Raises WorkOrderError if invalid.
    """
    # Look for WO file in standard location
    wo_path = CONTROL_PLANE_ROOT / "work_orders" / "ho3" / f"{work_order_id}.json"

    if not wo_path.exists():
        raise WorkOrderError(f"Work Order not found: {wo_path}")

    try:
        wo = json.loads(wo_path.read_text())
    except Exception as e:
        raise WorkOrderError(f"Invalid Work Order JSON: {e}")

    # Validate type
    wo_type = wo.get("type")
    if wo_type != "baseline_refresh":
        raise WorkOrderError(
            f"Work Order type must be 'baseline_refresh', got '{wo_type}'"
        )

    # Validate status (must be approved)
    status = wo.get("status")
    if status not in ("APPROVED", "approved"):
        raise WorkOrderError(
            f"Work Order must be APPROVED, got '{status}'"
        )

    return wo


def load_baseline_manifest(plane: str) -> dict:
    """Load baseline manifest from packages_store."""
    package_id = f"PKG-BASELINE-{plane.upper()}-000"
    manifest_path = CONTROL_PLANE_ROOT / "packages_store" / package_id / "manifest.json"

    if not manifest_path.exists():
        raise InstallError(
            f"Baseline manifest not found: {manifest_path}\n"
            f"Run: python3 scripts/generate_baseline_manifest.py --plane {plane} --output packages_store/{package_id}/"
        )

    return json.loads(manifest_path.read_text())


def verify_declared_inputs(manifest: dict, plane: str) -> None:
    """
    Verify manifest metadata matches current governed_roots.json.

    This enforces turn isolation: the manifest declares what inputs
    it was generated from, and we verify those inputs still match.
    """
    metadata = manifest.get("metadata", {})
    declared_roots = set(metadata.get("scan_roots", []))
    declared_exclusions = set(metadata.get("exclusion_patterns", []))

    # Load current governed_roots.json
    config_path = CONTROL_PLANE_ROOT / "config" / "governed_roots.json"
    if not config_path.exists():
        raise DeclaredInputsViolation(f"governed_roots.json not found: {config_path}")

    current_config = json.loads(config_path.read_text())
    current_roots = set(current_config.get("governed_roots", []))
    current_exclusions = set(current_config.get("excluded_patterns", []))

    # Compare
    if declared_roots != current_roots:
        raise DeclaredInputsViolation(
            f"scan_roots mismatch:\n"
            f"  manifest: {sorted(declared_roots)}\n"
            f"  current:  {sorted(current_roots)}"
        )

    if declared_exclusions != current_exclusions:
        raise DeclaredInputsViolation(
            f"exclusion_patterns mismatch:\n"
            f"  manifest: {sorted(declared_exclusions)}\n"
            f"  current:  {sorted(current_exclusions)}"
        )


from kernel.hashing import compute_sha256  # canonical implementation


def verify_all_files(manifest: dict) -> list[str]:
    """
    Verify all files in manifest exist with matching hashes.

    Returns list of errors (empty if all good).
    """
    errors = []

    for asset in manifest.get("assets", []):
        path = CONTROL_PLANE_ROOT / asset["path"]

        if not path.exists():
            errors.append(f"MISSING: {asset['path']}")
            continue

        actual_hash = compute_sha256(path)
        expected_hash = asset["sha256"]

        if actual_hash != expected_hash:
            errors.append(
                f"HASH_MISMATCH: {asset['path']}\n"
                f"  expected: {expected_hash}\n"
                f"  actual:   {actual_hash}"
            )

    return errors


def compute_manifest_hash(manifest: dict) -> str:
    """Compute manifest hash excluding metadata block."""
    hashable = {k: v for k, v in manifest.items() if k != "metadata"}
    canonical = json.dumps(hashable, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def get_ledger_client() -> LedgerClient:
    """Get ledger client for L-PACKAGE in HO3 context."""
    tier_context = TierContext(
        tier="HO3",
        plane_root=CONTROL_PLANE_ROOT,
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
) -> str:
    """
    Write L-PACKAGE ledger entry.

    Returns entry ID.
    """
    client = get_ledger_client()

    metadata = {
        "package_type": "baseline",
        "plane_id": "ho3",
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
        reason=f"Baseline package {event_type.lower().replace('_', ' ')}",
        metadata=metadata,
    )

    entry_id = client.write(entry)
    client.flush()

    return entry_id


def write_receipt(manifest: dict, work_order_id: Optional[str] = None) -> Path:
    """
    Write installation receipt to installed/<pkg_id>/.

    Returns receipt path.
    """
    package_id = manifest["package_id"]
    receipt_dir = CONTROL_PLANE_ROOT / "installed" / package_id
    receipt_dir.mkdir(parents=True, exist_ok=True)

    manifest_hash = compute_manifest_hash(manifest)

    receipt = {
        "package_id": package_id,
        "origin": "BUILDER",
        "package_type": "baseline",
        "plane_id": "ho3",
        "installed_at": datetime.now(timezone.utc).isoformat(),
        "manifest_hash": manifest_hash,
        "assets_count": len(manifest.get("assets", [])),
        "work_order_id": work_order_id,
        "receipt_version": "1.0",
    }

    receipt_path = receipt_dir / "receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2))

    # Also copy manifest for reference
    manifest_path = receipt_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))

    return receipt_path


def write_seal(package_id: str) -> Path:
    """
    Write seal marker to config/seal.json.

    Returns seal file path.
    """
    seal = {
        "sealed": True,
        "sealed_at": datetime.now(timezone.utc).isoformat(),
        "sealed_by": package_id,
        "seal_version": "1.0",
        "notes": "Plane sealed after baseline installation. All subsequent changes require Work Orders.",
    }

    SEAL_FILE.parent.mkdir(parents=True, exist_ok=True)
    SEAL_FILE.write_text(json.dumps(seal, indent=2))

    return SEAL_FILE


def install_baseline(
    plane: str,
    work_order_id: Optional[str] = None,
    skip_seal: bool = False,
) -> dict:
    """
    Install baseline package for the specified plane.

    Args:
        plane: Target plane (ho3 only in Phase 1)
        work_order_id: Required if plane is sealed
        skip_seal: Don't seal after install (for testing)

    Returns:
        Result dict with status and details
    """
    if plane != "ho3":
        raise InstallError(f"Phase 1 is HO3-only. Got plane={plane}")

    # Check seal status
    sealed = is_sealed()

    if sealed:
        if not work_order_id:
            raise SealedPlaneError(
                "Plane is sealed. Baseline refresh requires Work Order.\n"
                "Use: --work-order WO-YYYYMMDD-NNN"
            )
        # Validate WO
        wo = validate_work_order(work_order_id)
        print(f"[install_baseline] Work Order validated: {work_order_id}", file=sys.stderr)
    else:
        print(f"[install_baseline] Plane is unsealed (bootstrap mode)", file=sys.stderr)

    # Load manifest
    manifest = load_baseline_manifest(plane)
    package_id = manifest["package_id"]
    print(f"[install_baseline] Loaded manifest: {package_id}", file=sys.stderr)

    # Verify declared inputs (turn isolation)
    verify_declared_inputs(manifest, plane)
    print(f"[install_baseline] Declared inputs verified", file=sys.stderr)

    # Write INSTALL_STARTED to L-PACKAGE
    write_ledger_entry(
        event_type="INSTALL_STARTED",
        package_id=package_id,
        work_order_id=work_order_id,
    )
    print(f"[install_baseline] Wrote INSTALL_STARTED to L-PACKAGE", file=sys.stderr)

    try:
        # Verify all files exist with matching hashes
        errors = verify_all_files(manifest)

        if errors:
            error_msg = f"{len(errors)} file verification errors:\n" + "\n".join(errors[:10])
            if len(errors) > 10:
                error_msg += f"\n... and {len(errors) - 10} more"

            # Write INSTALL_FAILED
            write_ledger_entry(
                event_type="INSTALL_FAILED",
                package_id=package_id,
                error=error_msg,
                work_order_id=work_order_id,
            )

            raise InstallError(error_msg)

        print(f"[install_baseline] Verified {len(manifest['assets'])} files", file=sys.stderr)

        # Write receipt
        receipt_path = write_receipt(manifest, work_order_id)
        print(f"[install_baseline] Wrote receipt: {receipt_path}", file=sys.stderr)

        # Write INSTALLED to L-PACKAGE
        manifest_hash = compute_manifest_hash(manifest)
        write_ledger_entry(
            event_type="INSTALLED",
            package_id=package_id,
            manifest_hash=manifest_hash,
            work_order_id=work_order_id,
            assets_count=len(manifest["assets"]),
        )
        print(f"[install_baseline] Wrote INSTALLED to L-PACKAGE", file=sys.stderr)

        # Seal the plane (unless skipped or already sealed)
        if not sealed and not skip_seal:
            seal_path = write_seal(package_id)
            print(f"[install_baseline] Sealed plane: {seal_path}", file=sys.stderr)

        return {
            "success": True,
            "package_id": package_id,
            "manifest_hash": manifest_hash,
            "assets_count": len(manifest["assets"]),
            "sealed": not skip_seal and not sealed,
            "receipt_path": str(receipt_path),
        }

    except InstallError:
        raise
    except Exception as e:
        # Write INSTALL_FAILED for unexpected errors
        write_ledger_entry(
            event_type="INSTALL_FAILED",
            package_id=package_id,
            error=str(e),
            work_order_id=work_order_id,
        )
        raise InstallError(f"Unexpected error: {e}") from e


def main():
    parser = argparse.ArgumentParser(
        description="Install baseline package for Control Plane v2",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Pre-seal (first time bootstrap)
    python3 scripts/install_baseline.py --plane ho3

    # Post-seal (refresh with Work Order)
    python3 scripts/install_baseline.py --plane ho3 --work-order WO-20260202-001

    # Test without sealing
    python3 scripts/install_baseline.py --plane ho3 --skip-seal
"""
    )

    parser.add_argument(
        "--plane",
        required=True,
        choices=["ho3"],  # Phase 1 is HO3-only
        help="Target plane (Phase 1: ho3 only)"
    )

    parser.add_argument(
        "--work-order",
        dest="work_order_id",
        help="Work Order ID (required if plane is sealed)"
    )

    parser.add_argument(
        "--skip-seal",
        action="store_true",
        help="Don't seal plane after install (for testing)"
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="Output result as JSON"
    )

    args = parser.parse_args()

    try:
        result = install_baseline(
            plane=args.plane,
            work_order_id=args.work_order_id,
            skip_seal=args.skip_seal,
        )

        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"\nBaseline installation successful!")
            print(f"  Package ID:    {result['package_id']}")
            print(f"  Manifest Hash: {result['manifest_hash']}")
            print(f"  Assets:        {result['assets_count']}")
            print(f"  Sealed:        {result['sealed']}")
            print(f"  Receipt:       {result['receipt_path']}")

        return 0

    except SealedPlaneError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    except WorkOrderError as e:
        print(f"WORK ORDER ERROR: {e}", file=sys.stderr)
        return 3

    except DeclaredInputsViolation as e:
        print(f"DECLARED INPUTS VIOLATION: {e}", file=sys.stderr)
        print(
            "\nThe manifest was generated with different governed_roots.json inputs.\n"
            "Regenerate the manifest:\n"
            f"  python3 scripts/generate_baseline_manifest.py --plane {args.plane} --output packages_store/PKG-BASELINE-{args.plane.upper()}-000/",
            file=sys.stderr
        )
        return 4

    except InstallError as e:
        print(f"INSTALL ERROR: {e}", file=sys.stderr)
        return 1

    except Exception as e:
        print(f"UNEXPECTED ERROR: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 99


if __name__ == "__main__":
    sys.exit(main())
