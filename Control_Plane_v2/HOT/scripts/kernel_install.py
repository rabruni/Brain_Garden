#!/usr/bin/env python3
"""
Kernel Package Installer

Installs PKG-KERNEL-001 to all tiers (HO3, HO2, HO1).
The kernel package contains shared system code that must be identical across all tiers.

BINDING CONSTRAINTS (Phase 4):
- Kernel must be installed to ALL tiers in a single operation
- Each tier gets identical manifest (parity requirement for G0K)
- Uses canonical ledger framework for KERNEL_INSTALL events (R1)
- Writes to tier-specific ledgers: ledger/kernel.jsonl (HO3),
  planes/ho2/ledger/kernel.jsonl (HO2), planes/ho1/ledger/kernel.jsonl (HO1)

Usage:
    python3 scripts/kernel_install.py [--dry-run]

Phase 4 Implementation: AC-K2 (replicated manifest), AC-K3 (ledger events)
"""

import argparse
import hashlib
import json
import shutil
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


# === Tier Configuration ===

TIER_CONFIG = {
    "HO3": {
        "plane_root": CONTROL_PLANE_ROOT,
        "installed_path": CONTROL_PLANE_ROOT / "installed",
        "ledger_path": CONTROL_PLANE_ROOT / "ledger" / "kernel.jsonl",
    },
    "HO2": {
        "plane_root": CONTROL_PLANE_ROOT / "planes" / "ho2",
        "installed_path": CONTROL_PLANE_ROOT / "planes" / "ho2" / "installed",
        "ledger_path": CONTROL_PLANE_ROOT / "planes" / "ho2" / "ledger" / "kernel.jsonl",
    },
    "HO1": {
        "plane_root": CONTROL_PLANE_ROOT / "planes" / "ho1",
        "installed_path": CONTROL_PLANE_ROOT / "planes" / "ho1" / "installed",
        "ledger_path": CONTROL_PLANE_ROOT / "planes" / "ho1" / "ledger" / "kernel.jsonl",
    },
}


class KernelInstallError(Exception):
    """Kernel installation error."""
    pass


class ManifestNotFoundError(KernelInstallError):
    """Kernel manifest not found."""
    pass


def load_kernel_manifest() -> dict:
    """Load kernel manifest from packages_store."""
    manifest_path = CONTROL_PLANE_ROOT / "packages_store" / "PKG-KERNEL-001" / "manifest.json"
    if not manifest_path.exists():
        raise ManifestNotFoundError(
            f"Kernel manifest not found: {manifest_path}\n"
            "Run: python3 scripts/kernel_build.py"
        )
    return json.loads(manifest_path.read_text())


def compute_manifest_hash(manifest: dict) -> str:
    """Compute manifest hash from assets for parity verification."""
    # Use only assets for hash (excluding metadata which may differ)
    assets_json = json.dumps(manifest.get("assets", []), sort_keys=True, separators=(",", ":"))
    return f"sha256:{hashlib.sha256(assets_json.encode()).hexdigest()}"


def get_ledger_client(tier: str) -> LedgerClient:
    """Get ledger client for kernel ledger in specified tier."""
    config = TIER_CONFIG[tier]
    tier_context = TierContext(
        tier=tier,
        plane_root=config["plane_root"],
    )
    # Ensure ledger directory exists
    config["ledger_path"].parent.mkdir(parents=True, exist_ok=True)
    return LedgerClient(
        ledger_path=config["ledger_path"],
        tier_context=tier_context,
    )


def write_kernel_install_event(
    tier: str,
    package_id: str,
    manifest_hash: str,
    assets_count: int,
    event_type: str = "KERNEL_INSTALLED",
    error: Optional[str] = None,
) -> str:
    """
    Write KERNEL_INSTALL event to tier's kernel ledger.

    Returns entry ID.
    """
    client = get_ledger_client(tier)

    metadata = {
        "package_type": "kernel",
        "plane_id": tier.lower(),
        "ledger_type": "L-KERNEL",
        "manifest_hash": manifest_hash,
        "assets_count": assets_count,
        "replicated_to": list(TIER_CONFIG.keys()),
    }

    if error:
        metadata["error"] = error

    entry = LedgerEntry(
        event_type=event_type,
        submission_id=package_id,
        decision=event_type,
        reason=f"Kernel package {event_type.lower().replace('_', ' ')} on {tier}",
        metadata=metadata,
    )

    entry_id = client.write(entry)
    client.flush()

    return entry_id


def install_kernel_to_tier(
    tier: str,
    manifest: dict,
    dry_run: bool = False,
) -> dict:
    """
    Install kernel manifest to a single tier.

    Returns result dict with status and details.
    """
    config = TIER_CONFIG[tier]
    package_id = manifest["package_id"]
    manifest_hash = compute_manifest_hash(manifest)
    assets_count = manifest.get("assets_count", len(manifest.get("assets", [])))

    # Destination for manifest
    installed_dir = config["installed_path"] / package_id
    manifest_path = installed_dir / "manifest.json"

    if dry_run:
        print(f"[DRY-RUN] {tier}: Would install to {installed_dir}")
        return {
            "tier": tier,
            "status": "dry_run",
            "manifest_hash": manifest_hash,
        }

    try:
        # Create installed directory
        installed_dir.mkdir(parents=True, exist_ok=True)

        # Write manifest (same content to all tiers for parity)
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

        # Write receipt
        receipt = {
            "package_id": package_id,
            "package_type": "kernel",
            "tier": tier,
            "installed_at": datetime.now(timezone.utc).isoformat(),
            "manifest_hash": manifest_hash,
            "assets_count": assets_count,
        }
        receipt_path = installed_dir / "receipt.json"
        receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")

        # Write ledger event
        entry_id = write_kernel_install_event(
            tier=tier,
            package_id=package_id,
            manifest_hash=manifest_hash,
            assets_count=assets_count,
        )

        return {
            "tier": tier,
            "status": "installed",
            "manifest_hash": manifest_hash,
            "ledger_entry_id": entry_id,
            "manifest_path": str(manifest_path),
        }

    except Exception as e:
        # Write failure event to ledger
        try:
            entry_id = write_kernel_install_event(
                tier=tier,
                package_id=package_id,
                manifest_hash=manifest_hash,
                assets_count=assets_count,
                event_type="KERNEL_INSTALL_FAILED",
                error=str(e),
            )
        except Exception:
            entry_id = None

        return {
            "tier": tier,
            "status": "failed",
            "error": str(e),
            "ledger_entry_id": entry_id,
        }


def install_kernel(dry_run: bool = False) -> dict:
    """
    Install kernel package to all tiers.

    Returns result dict with status per tier.
    """
    # Load kernel manifest
    manifest = load_kernel_manifest()
    package_id = manifest["package_id"]
    manifest_hash = compute_manifest_hash(manifest)

    print(f"Installing kernel package: {package_id}")
    print(f"  Manifest hash: {manifest_hash}")
    print(f"  Assets: {manifest.get('assets_count', len(manifest.get('assets', [])))}")
    print()

    results = {
        "package_id": package_id,
        "manifest_hash": manifest_hash,
        "tiers": {},
    }

    all_success = True
    for tier in TIER_CONFIG.keys():
        result = install_kernel_to_tier(tier, manifest, dry_run)
        results["tiers"][tier] = result

        status = result["status"]
        if status == "installed":
            print(f"  {tier}: INSTALLED (ledger: {result.get('ledger_entry_id', 'N/A')})")
        elif status == "dry_run":
            print(f"  {tier}: [DRY-RUN]")
        else:
            print(f"  {tier}: FAILED - {result.get('error', 'unknown')}")
            all_success = False

    results["all_success"] = all_success or dry_run
    return results


def main():
    parser = argparse.ArgumentParser(description="Install kernel package to all tiers")
    parser.add_argument("--dry-run", action="store_true",
                       help="Show what would be installed without writing")
    parser.add_argument("--json", action="store_true",
                       help="Output JSON result")
    args = parser.parse_args()

    try:
        results = install_kernel(dry_run=args.dry_run)

        if args.json:
            print(json.dumps(results, indent=2))
            return 0

        print()
        if results["all_success"]:
            print("Kernel package installed to all tiers.")
            print("Run 'python3 scripts/gate_check.py --gate G0K' to verify parity.")
            return 0
        else:
            print("ERROR: Kernel installation failed on some tiers.", file=sys.stderr)
            return 1

    except ManifestNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
