#!/usr/bin/env python3
"""
cp_inspect.py - Read-only Control Plane inspection and reporting.

Provides read-only status reporting for Control Plane health:
- status: Single plane status report
- chain-status: Multi-plane chain status report
- packages: List installed packages
- receipts: List install receipts
- policies: List and validate policies
- integrity: Run integrity checks

Per Plane-Aware Package System design - all operations are READ-ONLY.

Usage:
    python3 scripts/cp_inspect.py status [--root /path] [--json]
    python3 scripts/cp_inspect.py chain-status [--json]
    python3 scripts/cp_inspect.py packages [--root /path]
    python3 scripts/cp_inspect.py receipts [--root /path]
    python3 scripts/cp_inspect.py policies [--root /path]
    python3 scripts/cp_inspect.py integrity [--root /path]
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add repo root for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kernel.paths import CONTROL_PLANE
from kernel.plane import (
    PlaneContext,
    PlaneType,
    get_current_plane,
    load_chain_config,
    get_all_plane_names,
)
from kernel.packages import sha256_file

# Try to import yaml
try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


@dataclass
class PlaneStatus:
    """Status information for a single plane."""
    plane_name: str
    plane_type: str
    root: str
    status: str = "unknown"
    packages: Dict[str, Any] = field(default_factory=dict)
    contracts: Dict[str, Any] = field(default_factory=dict)
    integrity: Dict[str, Any] = field(default_factory=dict)
    ledger: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary matching cp_status.json schema."""
        return {
            "schema_version": "1.0",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "plane": {
                "name": self.plane_name,
                "type": self.plane_type,
                "root": self.root,
            },
            "status": self.status,
            "packages": self.packages,
            "contracts": self.contracts,
            "integrity": self.integrity,
            "ledger": self.ledger,
            "warnings": self.warnings,
            "errors": self.errors,
        }


def load_yaml_file(path: Path) -> Optional[Dict[str, Any]]:
    """Load a YAML or JSON file."""
    if path.suffix == ".json":
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None

    if not HAS_YAML:
        return None

    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except (yaml.YAMLError, IOError):
        return None


def get_installed_packages(plane: PlaneContext) -> List[Dict[str, Any]]:
    """Get list of installed packages from receipts."""
    packages = []

    receipts_dir = plane.receipts_dir
    if not receipts_dir.exists():
        return packages

    for pkg_dir in sorted(receipts_dir.iterdir()):
        if not pkg_dir.is_dir():
            continue

        receipt_path = pkg_dir / "receipt.json"
        if not receipt_path.exists():
            continue

        try:
            with open(receipt_path, "r", encoding="utf-8") as f:
                receipt = json.load(f)

            # Filter by plane root
            receipt_root = receipt.get("plane_root", "")
            if receipt_root and Path(receipt_root).resolve() != plane.root.resolve():
                continue

            packages.append({
                "id": receipt.get("id", pkg_dir.name),
                "version": receipt.get("version", "unknown"),
                "tier": receipt.get("tier", ""),
                "installed_at": receipt.get("installed_at", ""),
                "has_receipt": True,
                "tainted": receipt.get("tainted", False),
            })
        except (json.JSONDecodeError, IOError):
            packages.append({
                "id": pkg_dir.name,
                "has_receipt": False,
                "error": "Could not read receipt",
            })

    return packages


def get_expected_packages(plane: PlaneContext) -> List[str]:
    """Get list of expected packages from registry."""
    expected = []

    registry_path = plane.root / "registries" / "packages_registry.csv"
    if not registry_path.exists():
        return expected

    try:
        with open(registry_path, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                pkg_id = row.get("id", "").strip()
                status = row.get("status", "").strip().lower()
                if pkg_id and status in ("active", "installed", ""):
                    expected.append(pkg_id)
    except IOError:
        pass

    return expected


def check_file_integrity(plane: PlaneContext) -> Dict[str, Any]:
    """Check file integrity for all receipts."""
    result = {
        "files_checked": 0,
        "files_ok": 0,
        "files_missing": 0,
        "files_modified": 0,
        "issues": [],
    }

    receipts_dir = plane.receipts_dir
    if not receipts_dir.exists():
        return result

    for pkg_dir in receipts_dir.iterdir():
        if not pkg_dir.is_dir():
            continue

        receipt_path = pkg_dir / "receipt.json"
        if not receipt_path.exists():
            continue

        try:
            with open(receipt_path, "r", encoding="utf-8") as f:
                receipt = json.load(f)

            # Filter by plane root
            receipt_root = receipt.get("plane_root", "")
            if receipt_root and Path(receipt_root).resolve() != plane.root.resolve():
                continue

            for file_entry in receipt.get("files", []):
                result["files_checked"] += 1
                file_path = file_entry.get("path", "")
                expected_hash = file_entry.get("sha256", "")

                full_path = plane.root / file_path
                if not full_path.exists():
                    result["files_missing"] += 1
                    result["issues"].append({
                        "severity": "error",
                        "check": "content_hash",
                        "message": f"File missing: {file_path}",
                        "path": file_path,
                    })
                elif expected_hash:
                    actual_hash = sha256_file(full_path)
                    if actual_hash != expected_hash:
                        result["files_modified"] += 1
                        result["issues"].append({
                            "severity": "warning",
                            "check": "content_hash",
                            "message": f"File modified: {file_path}",
                            "path": file_path,
                        })
                    else:
                        result["files_ok"] += 1
                else:
                    result["files_ok"] += 1

        except (json.JSONDecodeError, IOError):
            continue

    return result


def validate_policy(policy_name: str, policy_type: str, plane: PlaneContext) -> Dict[str, Any]:
    """Validate a policy file."""
    result = {
        "present": False,
        "version": None,
        "valid": False,
        "validation_errors": [],
    }

    policies_dir = plane.root / "policies"

    # Find policy file
    policy_path = None
    for ext in [".yaml", ".yml", ".json"]:
        candidate = policies_dir / f"{policy_name}{ext}"
        if candidate.exists():
            policy_path = candidate
            break

    if policy_path is None:
        return result

    result["present"] = True

    policy = load_yaml_file(policy_path)
    if policy is None:
        result["validation_errors"].append("Failed to parse policy file")
        return result

    result["version"] = policy.get("version", "unknown")

    # Basic validation
    if "schema_version" not in policy:
        result["validation_errors"].append("Missing schema_version")

    if "policy_type" not in policy:
        result["validation_errors"].append("Missing policy_type")
    elif policy["policy_type"] != policy_type:
        result["validation_errors"].append(
            f"Wrong policy_type: expected {policy_type}, got {policy['policy_type']}"
        )

    if "rules" not in policy:
        result["validation_errors"].append("Missing rules section")

    result["valid"] = len(result["validation_errors"]) == 0
    return result


def get_ledger_info(plane: PlaneContext) -> Dict[str, Any]:
    """Get ledger information."""
    result = {
        "entry_count": 0,
        "last_entry_at": None,
        "chain_valid": None,
    }

    ledger_dir = plane.ledger_dir
    if not ledger_dir.exists():
        return result

    # Count entries
    ledger_file = ledger_dir / "ledger.jsonl"
    if ledger_file.exists():
        try:
            with open(ledger_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        result["entry_count"] += 1
                        try:
                            entry = json.loads(line)
                            result["last_entry_at"] = entry.get("timestamp")
                        except json.JSONDecodeError:
                            pass
        except IOError:
            pass

    # Verify chain (basic check)
    try:
        from kernel.ledger_client import LedgerClient
        ledger = LedgerClient()
        valid, _ = ledger.verify_chain()
        result["chain_valid"] = valid
    except Exception:
        pass

    return result


def get_plane_status(plane: PlaneContext) -> PlaneStatus:
    """Get comprehensive status for a plane."""
    status = PlaneStatus(
        plane_name=plane.name,
        plane_type=plane.plane_type.value,
        root=str(plane.root),
    )

    # Check packages
    installed = get_installed_packages(plane)
    expected = get_expected_packages(plane)
    installed_ids = {p["id"] for p in installed if "id" in p}

    missing = [pkg_id for pkg_id in expected if pkg_id not in installed_ids]
    unexpected = [p["id"] for p in installed if p.get("id") not in expected and "id" in p]
    tainted = [p["id"] for p in installed if p.get("tainted")]

    status.packages = {
        "installed": installed,
        "expected": expected,
        "missing": missing,
        "unexpected": unexpected,
        "tainted": tainted,
        "drift_detected": len(missing) > 0 or len(unexpected) > 0,
    }

    # Check contracts/policies
    status.contracts = {
        "attention_policy": validate_policy("attention_default", "attention", plane),
        "install_policy": validate_policy("install_policy", "install", plane),
    }

    # Check integrity
    integrity_result = check_file_integrity(plane)
    status.integrity = {
        "registry_sync": len(missing) == 0 and len(unexpected) == 0,
        "content_hashes_valid": integrity_result["files_modified"] == 0,
        "merkle_root_valid": None,  # Would need merkle.py integration
        "ledger_chain_intact": None,  # Filled in below
        "issues": integrity_result["issues"][:10],  # Limit issues
    }

    # Check ledger
    ledger_info = get_ledger_info(plane)
    status.ledger = ledger_info
    status.integrity["ledger_chain_intact"] = ledger_info.get("chain_valid")

    # Determine overall status
    if status.errors:
        status.status = "unhealthy"
    elif status.packages.get("drift_detected") or integrity_result["files_modified"] > 0:
        status.status = "degraded"
    elif tainted:
        status.status = "degraded"
        status.warnings.append(f"Tainted packages: {tainted}")
    elif missing:
        status.status = "degraded"
        status.warnings.append(f"Missing packages: {missing}")
    else:
        status.status = "healthy"

    return status


def cmd_status(args) -> int:
    """Status command - single plane status."""
    root = args.root.resolve() if args.root else None
    plane = get_current_plane(root)

    status = get_plane_status(plane)

    if args.json:
        print(json.dumps(status.to_dict(), indent=2))
    else:
        print(f"Control Plane Status")
        print(f"====================")
        print(f"Plane: {status.plane_name} ({status.plane_type})")
        print(f"Root: {status.root}")
        print(f"Status: {status.status.upper()}")
        print()

        print("Packages:")
        print(f"  Installed: {len(status.packages.get('installed', []))}")
        print(f"  Expected: {len(status.packages.get('expected', []))}")
        if status.packages.get("missing"):
            print(f"  Missing: {status.packages['missing']}")
        if status.packages.get("tainted"):
            print(f"  Tainted: {status.packages['tainted']}")
        print()

        print("Contracts:")
        for name, info in status.contracts.items():
            present = "present" if info.get("present") else "missing"
            valid = "valid" if info.get("valid") else "invalid"
            print(f"  {name}: {present}, {valid}")
        print()

        print("Integrity:")
        print(f"  Registry sync: {status.integrity.get('registry_sync')}")
        print(f"  Content hashes: {status.integrity.get('content_hashes_valid')}")
        print(f"  Ledger chain: {status.integrity.get('ledger_chain_intact')}")

        if status.warnings:
            print("\nWarnings:")
            for w in status.warnings:
                print(f"  - {w}")

        if status.errors:
            print("\nErrors:")
            for e in status.errors:
                print(f"  - {e}")

    return 0 if status.status == "healthy" else 1


def cmd_chain_status(args) -> int:
    """Chain status command - all planes."""
    planes = load_chain_config()

    chain_status = {
        "schema_version": "1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "planes": [],
        "summary": {
            "total": len(planes),
            "healthy": 0,
            "degraded": 0,
            "unhealthy": 0,
        },
    }

    for plane in planes:
        status = get_plane_status(plane)
        chain_status["planes"].append(status.to_dict())

        if status.status == "healthy":
            chain_status["summary"]["healthy"] += 1
        elif status.status == "degraded":
            chain_status["summary"]["degraded"] += 1
        else:
            chain_status["summary"]["unhealthy"] += 1

    if args.json:
        print(json.dumps(chain_status, indent=2))
    else:
        print("Control Plane Chain Status")
        print("==========================")
        print()

        for plane_status in chain_status["planes"]:
            plane_info = plane_status["plane"]
            status = plane_status["status"]
            print(f"[{status.upper():10}] {plane_info['name']} ({plane_info['type']})")
            print(f"             Root: {plane_info['root']}")

            pkgs = plane_status.get("packages", {})
            installed = len(pkgs.get("installed", []))
            missing = len(pkgs.get("missing", []))
            tainted = len(pkgs.get("tainted", []))
            print(f"             Packages: {installed} installed, {missing} missing, {tainted} tainted")
            print()

        print("Summary:")
        print(f"  Total planes: {chain_status['summary']['total']}")
        print(f"  Healthy: {chain_status['summary']['healthy']}")
        print(f"  Degraded: {chain_status['summary']['degraded']}")
        print(f"  Unhealthy: {chain_status['summary']['unhealthy']}")

    unhealthy = chain_status["summary"]["unhealthy"]
    return 0 if unhealthy == 0 else 1


def cmd_packages(args) -> int:
    """List installed packages."""
    root = args.root.resolve() if args.root else None
    plane = get_current_plane(root)

    packages = get_installed_packages(plane)

    if args.json:
        print(json.dumps(packages, indent=2))
    else:
        print(f"Installed Packages ({plane.name})")
        print("=" * 50)
        for pkg in packages:
            status = ""
            if pkg.get("tainted"):
                status = " [TAINTED]"
            elif pkg.get("error"):
                status = " [ERROR]"
            print(f"  {pkg.get('id', 'unknown'):20} v{pkg.get('version', '?'):10}{status}")

    return 0


def cmd_receipts(args) -> int:
    """List install receipts."""
    root = args.root.resolve() if args.root else None
    plane = get_current_plane(root)

    receipts = []
    receipts_dir = plane.receipts_dir

    if receipts_dir.exists():
        for pkg_dir in sorted(receipts_dir.iterdir()):
            if not pkg_dir.is_dir():
                continue
            receipt_path = pkg_dir / "receipt.json"
            if receipt_path.exists():
                try:
                    with open(receipt_path, "r", encoding="utf-8") as f:
                        receipt = json.load(f)
                        receipts.append(receipt)
                except (json.JSONDecodeError, IOError):
                    receipts.append({"id": pkg_dir.name, "error": "unreadable"})

    if args.json:
        print(json.dumps(receipts, indent=2))
    else:
        print(f"Install Receipts ({plane.name})")
        print("=" * 50)
        for receipt in receipts:
            pkg_id = receipt.get("id", "unknown")
            version = receipt.get("version", "?")
            installed_at = receipt.get("installed_at", "?")
            files = len(receipt.get("files", []))
            print(f"  {pkg_id}: v{version}, {files} files, installed {installed_at[:10] if len(installed_at) > 10 else installed_at}")

    return 0


def cmd_policies(args) -> int:
    """List and validate policies."""
    root = args.root.resolve() if args.root else None
    plane = get_current_plane(root)

    policies_dir = plane.root / "policies"
    policies = []

    if policies_dir.exists():
        for f in sorted(policies_dir.iterdir()):
            if f.suffix in (".yaml", ".yml", ".json"):
                policy = load_yaml_file(f)
                if policy:
                    policies.append({
                        "file": f.name,
                        "policy_id": policy.get("policy_id", ""),
                        "policy_type": policy.get("policy_type", ""),
                        "version": policy.get("version", ""),
                        "rules": len(policy.get("rules", [])),
                    })
                else:
                    policies.append({
                        "file": f.name,
                        "error": "Could not parse",
                    })

    if args.json:
        print(json.dumps(policies, indent=2))
    else:
        print(f"Policies ({plane.name})")
        print("=" * 50)
        for pol in policies:
            if "error" in pol:
                print(f"  {pol['file']}: ERROR - {pol['error']}")
            else:
                print(f"  {pol['file']}: {pol['policy_id']} ({pol['policy_type']}) v{pol['version']}, {pol['rules']} rules")

    return 0


def cmd_integrity(args) -> int:
    """Run integrity checks."""
    root = args.root.resolve() if args.root else None
    plane = get_current_plane(root)

    integrity = check_file_integrity(plane)
    ledger = get_ledger_info(plane)

    result = {
        "plane": plane.name,
        "files": integrity,
        "ledger": ledger,
    }

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Integrity Check ({plane.name})")
        print("=" * 50)
        print()
        print("File Integrity:")
        print(f"  Files checked: {integrity['files_checked']}")
        print(f"  Files OK: {integrity['files_ok']}")
        print(f"  Files missing: {integrity['files_missing']}")
        print(f"  Files modified: {integrity['files_modified']}")

        if integrity["issues"]:
            print("\n  Issues:")
            for issue in integrity["issues"][:10]:
                print(f"    [{issue['severity'].upper()}] {issue['message']}")

        print()
        print("Ledger:")
        print(f"  Entry count: {ledger['entry_count']}")
        print(f"  Last entry: {ledger['last_entry_at']}")
        print(f"  Chain valid: {ledger['chain_valid']}")

    has_issues = integrity["files_missing"] > 0 or integrity["files_modified"] > 0
    return 1 if has_issues else 0


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Control Plane Inspection Tool (read-only)"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Status command
    status_parser = subparsers.add_parser("status", help="Show plane status")
    status_parser.add_argument("--root", type=Path, help="Plane root path")
    status_parser.add_argument("--json", action="store_true", help="JSON output")

    # Chain status command
    chain_parser = subparsers.add_parser("chain-status", help="Show all plane statuses")
    chain_parser.add_argument("--json", action="store_true", help="JSON output")

    # Packages command
    packages_parser = subparsers.add_parser("packages", help="List installed packages")
    packages_parser.add_argument("--root", type=Path, help="Plane root path")
    packages_parser.add_argument("--json", action="store_true", help="JSON output")

    # Receipts command
    receipts_parser = subparsers.add_parser("receipts", help="List install receipts")
    receipts_parser.add_argument("--root", type=Path, help="Plane root path")
    receipts_parser.add_argument("--json", action="store_true", help="JSON output")

    # Policies command
    policies_parser = subparsers.add_parser("policies", help="List policies")
    policies_parser.add_argument("--root", type=Path, help="Plane root path")
    policies_parser.add_argument("--json", action="store_true", help="JSON output")

    # Integrity command
    integrity_parser = subparsers.add_parser("integrity", help="Run integrity checks")
    integrity_parser.add_argument("--root", type=Path, help="Plane root path")
    integrity_parser.add_argument("--json", action="store_true", help="JSON output")

    args = parser.parse_args()

    # Dispatch to command handler
    handlers = {
        "status": cmd_status,
        "chain-status": cmd_chain_status,
        "packages": cmd_packages,
        "receipts": cmd_receipts,
        "policies": cmd_policies,
        "integrity": cmd_integrity,
    }

    handler = handlers.get(args.command)
    if handler:
        return handler(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
