#!/usr/bin/env python3
"""
seal_guard.py - Pre/post-flight validation for package operations.

Implements the seal guard pattern:
- Preflight: Validate before installation (tier deps, policy, integrity)
- Postflight: Validate after installation (receipts, drift detection)
- Quarantine: Mark packages as TAINTED when violations detected

Per Plane-Aware Package System design.

Usage:
    python3 scripts/seal_guard.py preflight --archive PKG.tar.gz [--root /path]
    python3 scripts/seal_guard.py postflight --id PKG-T0-001 [--root /path]
    python3 scripts/seal_guard.py drift-check [--root /path]
    python3 scripts/seal_guard.py quarantine --id PKG-T0-001 --reason "..." [--root /path]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tarfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

# Add repo root for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.paths import CONTROL_PLANE
from lib.plane import (
    PlaneContext,
    get_current_plane,
    validate_target_plane,
    validate_external_interface_direction,
    PlaneTargetMismatch,
    CrossPlaneViolation,
)
from lib.packages import sha256_file


# Try to import yaml for policy files
try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


@dataclass
class SealGuardResult:
    """Result of a seal guard check."""
    passed: bool
    checks: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    quarantined: bool = False
    taint_reason: Optional[str] = None

    def add_check(self, name: str, passed: bool, message: str, **details):
        """Add a check result."""
        self.checks.append({
            "name": name,
            "passed": passed,
            "message": message,
            **details
        })
        if not passed:
            self.passed = False
            self.errors.append(f"{name}: {message}")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "passed": self.passed,
            "checks": self.checks,
            "errors": self.errors,
            "warnings": self.warnings,
            "quarantined": self.quarantined,
            "taint_reason": self.taint_reason,
        }


def load_manifest_from_archive(archive_path: Path) -> Optional[Dict[str, Any]]:
    """Extract and load manifest.json from archive."""
    try:
        with tarfile.open(archive_path, "r:gz") as tf:
            # Look for manifest.json
            for member in tf.getmembers():
                if member.name.endswith("manifest.json"):
                    f = tf.extractfile(member)
                    if f:
                        return json.load(f)
    except (tarfile.TarError, json.JSONDecodeError, IOError):
        return None
    return None


def load_receipt(pkg_id: str, plane: PlaneContext) -> Optional[Dict[str, Any]]:
    """Load install receipt for a package."""
    receipt_path = plane.receipts_dir / pkg_id / "receipt.json"
    if not receipt_path.exists():
        return None
    try:
        with open(receipt_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def load_policy(policy_name: str, plane: PlaneContext) -> Optional[Dict[str, Any]]:
    """Load a policy file."""
    policies_dir = plane.root / "policies"

    # Try YAML first, then JSON
    for ext in [".yaml", ".yml", ".json"]:
        policy_path = policies_dir / f"{policy_name}{ext}"
        if policy_path.exists():
            try:
                if ext == ".json":
                    with open(policy_path, "r", encoding="utf-8") as f:
                        return json.load(f)
                elif HAS_YAML:
                    with open(policy_path, "r", encoding="utf-8") as f:
                        return yaml.safe_load(f)
            except (json.JSONDecodeError, IOError):
                continue
            except yaml.YAMLError:
                continue
    return None


def check_tier_deps(manifest: Dict[str, Any]) -> tuple[bool, List[str]]:
    """Validate tier dependency constraints."""
    errors = []
    tier_order = {"G0": 0, "T0": 1, "T1": 2, "T2": 3, "T3": 4}

    pkg_tier = manifest.get("tier", "")
    deps = manifest.get("deps", [])

    if pkg_tier not in tier_order:
        errors.append(f"Unknown tier: {pkg_tier}")
        return False, errors

    pkg_order = tier_order[pkg_tier]

    # Genesis zero-deps check
    if pkg_tier == "G0" and deps:
        errors.append("Genesis (G0) packages cannot have dependencies")
        return False, errors

    for dep_id in deps:
        parts = dep_id.split("-")
        if len(parts) >= 2:
            dep_tier = parts[1]
            if dep_tier in tier_order:
                if tier_order[dep_tier] > pkg_order:
                    errors.append(f"Tier violation: {pkg_tier} cannot depend on {dep_tier} ({dep_id})")

    return len(errors) == 0, errors


def check_plane_target(manifest: Dict[str, Any], plane: PlaneContext) -> tuple[bool, List[str]]:
    """Validate target_plane matches current plane."""
    errors = []

    target_plane = manifest.get("target_plane", "any")

    if not validate_target_plane(target_plane, plane):
        errors.append(
            f"Package targets plane '{target_plane}' but current plane is '{plane.name}'"
        )
        return False, errors

    return True, errors


def check_external_interfaces(manifest: Dict[str, Any], plane: PlaneContext) -> tuple[bool, List[str]]:
    """Validate external interface direction rules."""
    errors = []

    external_interfaces = manifest.get("external_interfaces", [])

    for iface in external_interfaces:
        source_plane = iface.get("source_plane", "")
        iface_name = iface.get("name", "unknown")

        if not validate_external_interface_direction(plane, source_plane):
            errors.append(
                f"Interface '{iface_name}' from plane '{source_plane}' cannot be "
                f"referenced by plane '{plane.name}' (direction violation)"
            )

    return len(errors) == 0, errors


def check_install_policy(manifest: Dict[str, Any], plane: PlaneContext, env: str) -> tuple[bool, List[str], List[str]]:
    """Check if installation is allowed by policy."""
    errors = []
    warnings = []

    policy = load_policy("install_policy", plane)
    if policy is None:
        warnings.append("No install policy found - allowing installation")
        return True, errors, warnings

    pkg_tier = manifest.get("tier", "")

    # Check plane restrictions
    plane_restrictions = policy.get("plane_restrictions", {})
    if plane.name in plane_restrictions:
        restrictions = plane_restrictions[plane.name]

        # Check allowed tiers
        allowed_tiers = restrictions.get("allowed_tiers", [])
        if allowed_tiers and pkg_tier not in allowed_tiers:
            errors.append(
                f"Tier {pkg_tier} not allowed in plane '{plane.name}' "
                f"(allowed: {allowed_tiers})"
            )

    # Check environment overrides
    env_overrides = policy.get("environment_overrides", {})
    if env in env_overrides:
        overrides = env_overrides[env]

        # Check strict mode
        if overrides.get("strict_mode") and not manifest.get("signature"):
            errors.append(f"Strict mode in {env}: signature required")

    return len(errors) == 0, errors, warnings


def check_attention_policy(plane: PlaneContext) -> tuple[bool, List[str], List[str]]:
    """Validate attention policy if present."""
    errors = []
    warnings = []

    policy = load_policy("attention_default", plane)
    if policy is None:
        # Attention policy is optional
        return True, errors, warnings

    # Basic validation
    if "rules" not in policy:
        errors.append("Attention policy missing 'rules' section")

    if "schema_version" not in policy:
        warnings.append("Attention policy missing schema_version")

    return len(errors) == 0, errors, warnings


def preflight_check(
    archive_path: Path,
    plane: PlaneContext,
    env: str = "dev",
    strict: bool = False,
) -> SealGuardResult:
    """Run preflight checks before installation.

    Checks:
    1. Archive exists and is readable
    2. Manifest is valid
    3. Tier dependencies are valid
    4. Target plane matches current plane
    5. External interface directions are valid
    6. Install policy allows operation
    7. Attention policy is valid (if strict)
    """
    result = SealGuardResult(passed=True)

    # Check 1: Archive exists
    if not archive_path.exists():
        result.add_check("archive_exists", False, f"Archive not found: {archive_path}")
        return result
    result.add_check("archive_exists", True, "Archive exists")

    # Check 2: Load manifest
    manifest = load_manifest_from_archive(archive_path)
    if manifest is None:
        result.add_check("manifest_valid", False, "Could not load manifest.json from archive")
        return result
    result.add_check("manifest_valid", True, "Manifest loaded successfully")

    pkg_id = manifest.get("id", "unknown")

    # Check 3: Tier dependencies
    tier_ok, tier_errors = check_tier_deps(manifest)
    if tier_ok:
        result.add_check("tier_deps", True, "Tier dependencies valid")
    else:
        result.add_check("tier_deps", False, "; ".join(tier_errors))

    # Check 4: Target plane
    plane_ok, plane_errors = check_plane_target(manifest, plane)
    if plane_ok:
        result.add_check("target_plane", True, f"Target plane compatible with '{plane.name}'")
    else:
        result.add_check("target_plane", False, "; ".join(plane_errors))

    # Check 5: External interfaces
    iface_ok, iface_errors = check_external_interfaces(manifest, plane)
    if iface_ok:
        result.add_check("external_interfaces", True, "External interface directions valid")
    else:
        result.add_check("external_interfaces", False, "; ".join(iface_errors))

    # Check 6: Install policy
    policy_ok, policy_errors, policy_warnings = check_install_policy(manifest, plane, env)
    result.warnings.extend(policy_warnings)
    if policy_ok:
        result.add_check("install_policy", True, "Install policy check passed")
    else:
        result.add_check("install_policy", False, "; ".join(policy_errors))

    # Check 7: Attention policy (only in strict mode)
    if strict:
        att_ok, att_errors, att_warnings = check_attention_policy(plane)
        result.warnings.extend(att_warnings)
        if att_ok:
            result.add_check("attention_policy", True, "Attention policy valid")
        else:
            result.add_check("attention_policy", False, "; ".join(att_errors))

    return result


def postflight_check(
    pkg_id: str,
    plane: PlaneContext,
) -> SealGuardResult:
    """Run postflight checks after installation.

    Checks:
    1. Receipt exists
    2. Receipt matches current plane
    3. Installed files exist and match hashes
    """
    result = SealGuardResult(passed=True)

    # Check 1: Receipt exists
    receipt = load_receipt(pkg_id, plane)
    if receipt is None:
        result.add_check("receipt_exists", False, f"No receipt found for {pkg_id}")
        return result
    result.add_check("receipt_exists", True, "Receipt found")

    # Check 2: Receipt plane matches
    receipt_plane = receipt.get("plane_name", "")
    receipt_root = receipt.get("plane_root", "")

    if receipt_plane and receipt_plane != plane.name:
        result.add_check(
            "receipt_plane_match",
            False,
            f"Receipt plane '{receipt_plane}' doesn't match current plane '{plane.name}'"
        )
    elif receipt_root and Path(receipt_root).resolve() != plane.root.resolve():
        result.add_check(
            "receipt_plane_match",
            False,
            f"Receipt root doesn't match current plane root"
        )
    else:
        result.add_check("receipt_plane_match", True, "Receipt plane matches")

    # Check 3: File integrity
    files = receipt.get("files", [])
    files_ok = True
    missing_files = []
    hash_mismatches = []

    for file_entry in files:
        file_path = file_entry.get("path", "")
        expected_hash = file_entry.get("sha256", "")

        full_path = plane.root / file_path
        if not full_path.exists():
            files_ok = False
            missing_files.append(file_path)
            continue

        if expected_hash:
            actual_hash = sha256_file(full_path)
            if actual_hash != expected_hash:
                files_ok = False
                hash_mismatches.append(file_path)

    if files_ok:
        result.add_check("file_integrity", True, f"All {len(files)} files verified")
    else:
        msg_parts = []
        if missing_files:
            msg_parts.append(f"missing: {missing_files[:3]}")
        if hash_mismatches:
            msg_parts.append(f"hash mismatch: {hash_mismatches[:3]}")
        result.add_check("file_integrity", False, "; ".join(msg_parts))

    return result


def drift_check(plane: PlaneContext) -> SealGuardResult:
    """Check for drift in installed packages.

    Compares installed files against receipts for this plane.
    Only considers receipts that match the current plane_root.
    """
    result = SealGuardResult(passed=True)

    receipts_dir = plane.receipts_dir
    if not receipts_dir.exists():
        result.warnings.append("No receipts directory found")
        return result

    packages_checked = 0
    packages_with_drift = []

    for pkg_dir in receipts_dir.iterdir():
        if not pkg_dir.is_dir():
            continue

        receipt_path = pkg_dir / "receipt.json"
        if not receipt_path.exists():
            continue

        try:
            with open(receipt_path, "r", encoding="utf-8") as f:
                receipt = json.load(f)
        except (json.JSONDecodeError, IOError):
            result.warnings.append(f"Could not read receipt: {receipt_path}")
            continue

        # Filter by plane_root
        receipt_root = receipt.get("plane_root", "")
        if receipt_root and Path(receipt_root).resolve() != plane.root.resolve():
            continue  # Skip receipts from other planes

        packages_checked += 1
        pkg_id = receipt.get("id", pkg_dir.name)

        # Check each file
        has_drift = False
        for file_entry in receipt.get("files", []):
            file_path = file_entry.get("path", "")
            expected_hash = file_entry.get("sha256", "")

            full_path = plane.root / file_path
            if not full_path.exists():
                has_drift = True
                break

            if expected_hash:
                actual_hash = sha256_file(full_path)
                if actual_hash != expected_hash:
                    has_drift = True
                    break

        if has_drift:
            packages_with_drift.append(pkg_id)

    if packages_with_drift:
        result.add_check(
            "drift_detection",
            False,
            f"Drift detected in {len(packages_with_drift)} packages: {packages_with_drift[:5]}"
        )
    else:
        result.add_check(
            "drift_detection",
            True,
            f"No drift detected in {packages_checked} packages"
        )

    return result


def quarantine_package(
    pkg_id: str,
    reason: str,
    plane: PlaneContext,
) -> SealGuardResult:
    """Mark a package as TAINTED/quarantined."""
    result = SealGuardResult(passed=True)

    receipt = load_receipt(pkg_id, plane)
    if receipt is None:
        result.add_check("quarantine", False, f"No receipt found for {pkg_id}")
        return result

    # Update receipt with taint info
    receipt["tainted"] = True
    receipt["taint_reason"] = reason
    receipt["tainted_at"] = datetime.now(timezone.utc).isoformat()

    receipt_path = plane.receipts_dir / pkg_id / "receipt.json"
    try:
        with open(receipt_path, "w", encoding="utf-8") as f:
            json.dump(receipt, f, indent=2)

        result.add_check("quarantine", True, f"Package {pkg_id} marked as TAINTED")
        result.quarantined = True
        result.taint_reason = reason

        # Log to ledger
        try:
            from lib.ledger_client import LedgerClient, LedgerEntry
            ledger = LedgerClient()
            ledger.write(LedgerEntry(
                event_type="package_quarantine",
                submission_id=pkg_id,
                decision="TAINTED",
                reason=reason,
                metadata={
                    "plane": plane.name,
                    "plane_root": str(plane.root),
                },
            ))
        except Exception as e:
            result.warnings.append(f"Could not log to ledger: {e}")

    except IOError as e:
        result.add_check("quarantine", False, f"Failed to update receipt: {e}")

    return result


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Seal Guard - Pre/post-flight validation for package operations"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Preflight command
    preflight_parser = subparsers.add_parser("preflight", help="Run preflight checks")
    preflight_parser.add_argument("--archive", required=True, type=Path, help="Archive to check")
    preflight_parser.add_argument("--root", type=Path, help="Plane root path")
    preflight_parser.add_argument("--env", default="dev", help="Environment (dev/staging/prod)")
    preflight_parser.add_argument("--strict", action="store_true", help="Enable strict checks")
    preflight_parser.add_argument("--json", action="store_true", help="JSON output")

    # Postflight command
    postflight_parser = subparsers.add_parser("postflight", help="Run postflight checks")
    postflight_parser.add_argument("--id", required=True, help="Package ID")
    postflight_parser.add_argument("--root", type=Path, help="Plane root path")
    postflight_parser.add_argument("--json", action="store_true", help="JSON output")

    # Drift check command
    drift_parser = subparsers.add_parser("drift-check", help="Check for drift")
    drift_parser.add_argument("--root", type=Path, help="Plane root path")
    drift_parser.add_argument("--json", action="store_true", help="JSON output")

    # Quarantine command
    quarantine_parser = subparsers.add_parser("quarantine", help="Quarantine a package")
    quarantine_parser.add_argument("--id", required=True, help="Package ID")
    quarantine_parser.add_argument("--reason", required=True, help="Quarantine reason")
    quarantine_parser.add_argument("--root", type=Path, help="Plane root path")
    quarantine_parser.add_argument("--json", action="store_true", help="JSON output")

    args = parser.parse_args()

    # Resolve plane
    root = args.root.resolve() if args.root else None
    plane = get_current_plane(root)

    # Execute command
    if args.command == "preflight":
        archive_path = args.archive
        if not archive_path.is_absolute():
            archive_path = Path.cwd() / archive_path

        result = preflight_check(
            archive_path=archive_path,
            plane=plane,
            env=args.env,
            strict=args.strict,
        )

    elif args.command == "postflight":
        result = postflight_check(
            pkg_id=args.id,
            plane=plane,
        )

    elif args.command == "drift-check":
        result = drift_check(plane)

    elif args.command == "quarantine":
        result = quarantine_package(
            pkg_id=args.id,
            reason=args.reason,
            plane=plane,
        )

    else:
        parser.print_help()
        return 1

    # Output results
    if args.json:
        output = result.to_dict()
        output["plane"] = {
            "name": plane.name,
            "type": plane.plane_type.value,
            "root": str(plane.root),
        }
        print(json.dumps(output, indent=2))
    else:
        print(f"Seal Guard: {args.command}")
        print(f"Plane: {plane.name} ({plane.plane_type.value})")
        print(f"Root: {plane.root}")
        print()

        for check in result.checks:
            status = "PASS" if check["passed"] else "FAIL"
            print(f"  [{status}] {check['name']}: {check['message']}")

        if result.warnings:
            print("\nWarnings:")
            for w in result.warnings:
                print(f"  - {w}")

        if result.errors:
            print("\nErrors:")
            for e in result.errors:
                print(f"  - {e}")

        print()
        if result.passed:
            print("OK: All checks passed")
        else:
            print("FAIL: Some checks failed")

    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(main())
