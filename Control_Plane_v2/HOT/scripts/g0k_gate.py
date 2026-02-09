#!/usr/bin/env python3
"""
G0K KERNEL_PARITY Gate Implementation

Verifies that kernel packages are identical across all tiers.
This gate ensures no kernel drift occurs between HO3, HO2, and HO1.

MANIFEST-FIRST APPROACH (R2):
1. Check manifest exists on each tier
2. Compare manifest hashes across tiers
3. Optionally verify files match manifests (--verify-files)

BINDING CONSTRAINTS (Phase 4):
- Kernel manifests MUST be identical across all tiers
- Parity check runs BEFORE G2 in gate sequence (G0K → G2 → ...)
- Any Work Order modifying kernel files MUST fail unless kernel_upgrade WO type

Usage:
    python3 scripts/g0k_gate.py [--verify-files] [--json]

Phase 4 Implementation: AC-K4 (parity gate), AC-K6 (kernel modification guard)
"""

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

# Resolve paths relative to Control_Plane_v2 root
SCRIPT_DIR = Path(__file__).resolve().parent
CONTROL_PLANE_ROOT = SCRIPT_DIR.parent

# Add lib to path for imports
sys.path.insert(0, str(CONTROL_PLANE_ROOT))


# === Tier Configuration ===

CP_ROOT = CONTROL_PLANE_ROOT.parent  # Control_Plane_v2/
TIER_CONFIG = {
    "HO3": {
        "plane_root": CP_ROOT / "HO3",
        "installed_path": CP_ROOT / "HO3" / "installed",
    },
    "HO2": {
        "plane_root": CP_ROOT / "HO2",
        "installed_path": CP_ROOT / "HO2" / "installed",
    },
    "HO1": {
        "plane_root": CP_ROOT / "HO1",
        "installed_path": CP_ROOT / "HO1" / "installed",
    },
}

KERNEL_PACKAGE_ID = "PKG-KERNEL-001"


@dataclass
class G0KResult:
    """Result of G0K gate check."""
    passed: bool
    message: str
    manifest_hashes: Dict[str, Optional[str]] = field(default_factory=dict)
    missing_tiers: List[str] = field(default_factory=list)
    mismatched_tiers: List[str] = field(default_factory=list)
    file_verification: Optional[Dict] = None

    def to_dict(self) -> dict:
        return {
            "gate": "G0K",
            "passed": self.passed,
            "message": self.message,
            "manifest_hashes": self.manifest_hashes,
            "missing_tiers": self.missing_tiers,
            "mismatched_tiers": self.mismatched_tiers,
            "file_verification": self.file_verification,
        }


def load_kernel_files_config() -> List[str]:
    """Load kernel file list from config."""
    config_path = CONTROL_PLANE_ROOT / "config" / "kernel_files.json"
    if not config_path.exists():
        return []
    config = json.loads(config_path.read_text())
    return config.get("files", [])


def compute_manifest_hash(manifest: dict) -> str:
    """Compute hash from manifest assets for parity comparison."""
    assets_json = json.dumps(manifest.get("assets", []), sort_keys=True, separators=(",", ":"))
    return f"sha256:{hashlib.sha256(assets_json.encode()).hexdigest()}"


def compute_file_hash(file_path: Path) -> Optional[str]:
    """Compute SHA-256 hash of file."""
    if not file_path.exists():
        return None
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return f"sha256:{sha256.hexdigest()}"


def load_tier_manifest(tier: str) -> Optional[dict]:
    """Load kernel manifest from a tier."""
    config = TIER_CONFIG[tier]
    manifest_path = config["installed_path"] / KERNEL_PACKAGE_ID / "manifest.json"
    if not manifest_path.exists():
        return None
    try:
        return json.loads(manifest_path.read_text())
    except (json.JSONDecodeError, IOError):
        return None


def verify_manifest_files(tier: str, manifest: dict) -> Dict[str, dict]:
    """Verify files on disk match manifest hashes."""
    results = {}
    config = TIER_CONFIG[tier]

    for asset in manifest.get("assets", []):
        rel_path = asset["path"]
        expected_hash = asset["sha256"]

        # Files use CP-root-relative paths (e.g. HOT/kernel/cursor.py)
        file_path = CP_ROOT / rel_path

        actual_hash = compute_file_hash(file_path)

        if actual_hash is None:
            results[rel_path] = {
                "status": "MISSING",
                "expected": expected_hash,
                "actual": None,
            }
        elif actual_hash != expected_hash:
            results[rel_path] = {
                "status": "HASH_MISMATCH",
                "expected": expected_hash,
                "actual": actual_hash,
            }
        else:
            results[rel_path] = {
                "status": "OK",
                "hash": actual_hash,
            }

    return results


def check_kernel_in_wo_scope(wo: dict) -> bool:
    """
    Check if a Work Order modifies kernel files.

    Per AC-K6: Any WO modifying kernel files MUST fail unless kernel_upgrade type.
    """
    kernel_files = set(load_kernel_files_config())
    if not kernel_files:
        return False

    wo_files = set(wo.get("scope", {}).get("allowed_files", []))
    overlap = kernel_files & wo_files

    return len(overlap) > 0


def run_g0k_gate(
    verify_files: bool = False,
    wo: Optional[dict] = None,
) -> G0KResult:
    """
    Run G0K KERNEL_PARITY gate.

    Args:
        verify_files: If True, also verify files match manifest hashes
        wo: Optional Work Order to check for kernel file modifications

    Returns:
        G0KResult with pass/fail status and details
    """
    manifest_hashes: Dict[str, Optional[str]] = {}
    missing_tiers: List[str] = []
    mismatched_tiers: List[str] = []
    file_verification = None

    # Step 1: Check if kernel file modification is in WO scope (AC-K6)
    if wo is not None:
        wo_type = wo.get("type", "")
        if check_kernel_in_wo_scope(wo) and wo_type != "kernel_upgrade":
            return G0KResult(
                passed=False,
                message=f"Work Order modifies kernel files but type is '{wo_type}', not 'kernel_upgrade'. "
                       "Kernel files can only be modified via formal kernel upgrade path.",
                manifest_hashes=manifest_hashes,
            )

    # Step 2: Check manifest exists on each tier
    for tier in TIER_CONFIG.keys():
        manifest = load_tier_manifest(tier)
        if manifest is None:
            manifest_hashes[tier] = None
            missing_tiers.append(tier)
        else:
            manifest_hashes[tier] = compute_manifest_hash(manifest)

    # If any tier missing, fail
    if missing_tiers:
        return G0KResult(
            passed=False,
            message=f"Kernel manifest missing on tiers: {missing_tiers}. "
                   "Run: python3 scripts/kernel_install.py",
            manifest_hashes=manifest_hashes,
            missing_tiers=missing_tiers,
        )

    # Step 3: Compare manifest hashes across tiers
    reference_hash = manifest_hashes["HO3"]
    for tier, tier_hash in manifest_hashes.items():
        if tier_hash != reference_hash:
            mismatched_tiers.append(tier)

    if mismatched_tiers:
        return G0KResult(
            passed=False,
            message=f"Kernel parity violation: manifest hashes differ on tiers {mismatched_tiers}. "
                   f"Reference (HO3): {reference_hash}",
            manifest_hashes=manifest_hashes,
            mismatched_tiers=mismatched_tiers,
        )

    # Step 4: Optionally verify files match manifest
    if verify_files:
        ho3_manifest = load_tier_manifest("HO3")
        if ho3_manifest:
            file_results = verify_manifest_files("HO3", ho3_manifest)
            failures = {k: v for k, v in file_results.items() if v["status"] != "OK"}

            file_verification = {
                "total_files": len(file_results),
                "ok_count": len([v for v in file_results.values() if v["status"] == "OK"]),
                "failures": failures,
            }

            if failures:
                return G0KResult(
                    passed=False,
                    message=f"Kernel file verification failed: {len(failures)} files do not match manifest",
                    manifest_hashes=manifest_hashes,
                    file_verification=file_verification,
                )

    return G0KResult(
        passed=True,
        message=f"G0K KERNEL_PARITY: All {len(TIER_CONFIG)} tiers have identical kernel manifest "
               f"(hash: {reference_hash})",
        manifest_hashes=manifest_hashes,
        file_verification=file_verification,
    )


def main():
    parser = argparse.ArgumentParser(description="G0K KERNEL_PARITY gate")
    parser.add_argument("--verify-files", action="store_true",
                       help="Also verify files match manifest hashes")
    parser.add_argument("--json", action="store_true",
                       help="Output JSON result")
    parser.add_argument("--enforce", action="store_true",
                       help="Exit with code 1 on failure")
    args = parser.parse_args()

    result = run_g0k_gate(verify_files=args.verify_files)

    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        status = "PASS" if result.passed else "FAIL"
        print(f"G0K KERNEL_PARITY: {status}")
        print(f"  {result.message}")

        if result.manifest_hashes:
            print("\n  Manifest hashes:")
            for tier, h in result.manifest_hashes.items():
                print(f"    {tier}: {h or 'MISSING'}")

        if result.file_verification:
            fv = result.file_verification
            print(f"\n  File verification: {fv['ok_count']}/{fv['total_files']} OK")
            if fv.get("failures"):
                for path, info in fv["failures"].items():
                    print(f"    {info['status']}: {path}")

    if args.enforce and not result.passed:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
