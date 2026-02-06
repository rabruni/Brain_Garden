#!/usr/bin/env python3
"""Agent pre-write validation and guidance.

This script helps AI agents verify they're following governance rules
BEFORE writing files. Designed to be called before any file operation.

Usage:
    # Check if a path is writable by agents
    python3 scripts/agent_check.py --path lib/myfile.py

    # Check multiple paths
    python3 scripts/agent_check.py --path lib/a.py --path modules/b/__init__.py

    # Get full status report
    python3 scripts/agent_check.py --status

    # Find orphan files
    python3 scripts/agent_check.py --orphans

    # JSON output for programmatic use
    python3 scripts/agent_check.py --path lib/foo.py --json
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

# Resolve paths
SCRIPT_DIR = Path(__file__).parent
ROOT = SCRIPT_DIR.parent

# Add lib to path
sys.path.insert(0, str(ROOT / "lib"))
sys.path.insert(0, str(ROOT))


# Governed roots where agents MUST NOT write directly
GOVERNED_ROOTS = [
    "lib/",
    "modules/",
    "scripts/",
    "frameworks/",
    "specs/",
    "registries/",
    "schemas/",
    "tests/",
    "docs/",
    "gates/",
    "policies/",
]

# Always forbidden (even for package install)
FORBIDDEN_ROOTS = [
    "installed/",
    "config/seal.json",
    "ledger/",  # append-only, not direct write
]

# Derived files (generated, not orphans)
DERIVED_FILES = [
    "registries/file_ownership.csv",
    "registries/packages_state.csv",
    "registries/compiled/file_ownership.json",
    "registries/compiled/packages.json",
]

# Agent-writable areas
AGENT_WRITABLE = [
    "_staging/",
    "_external_quarantine/",
    "tmp/",
]


def classify_path(path: str) -> dict:
    """Classify a path for agent write permissions.

    Returns:
        dict with:
            - path: the input path
            - classification: GOVERNED | FORBIDDEN | AGENT_WRITABLE | UNKNOWN
            - can_write: bool
            - reason: why
            - suggestion: what to do instead
    """
    path_obj = Path(path)

    # Normalize path
    if path_obj.is_absolute():
        try:
            path = str(path_obj.relative_to(ROOT))
        except ValueError:
            return {
                "path": path,
                "classification": "EXTERNAL",
                "can_write": False,
                "reason": "Path is outside Control Plane root",
                "suggestion": "Use paths relative to Control_Plane_v2/",
            }

    # Check forbidden first
    for forbidden in FORBIDDEN_ROOTS:
        if path.startswith(forbidden):
            return {
                "path": path,
                "classification": "FORBIDDEN",
                "can_write": False,
                "reason": f"Path {forbidden} is system-managed and NEVER writable by agents",
                "suggestion": "These paths are managed by the package manager or ledger system only",
            }

    # Check agent-writable
    for writable in AGENT_WRITABLE:
        if path.startswith(writable):
            return {
                "path": path,
                "classification": "AGENT_WRITABLE",
                "can_write": True,
                "reason": f"Path is in agent workspace {writable}",
                "suggestion": "Write here, then package and install via pkgutil",
            }

    # Check governed roots
    for governed in GOVERNED_ROOTS:
        if path.startswith(governed):
            return {
                "path": path,
                "classification": "GOVERNED",
                "can_write": False,
                "reason": f"Path {governed} is governed by packages",
                "suggestion": f"Create package in _staging/PKG-XXX/, add {path} to it, then install",
            }

    # Unknown - could be root-level file
    return {
        "path": path,
        "classification": "UNKNOWN",
        "can_write": False,
        "reason": "Path is at repository root or unrecognized location",
        "suggestion": "Check if this should be in a governed root or _staging/",
    }


def get_file_owner(path: str) -> Optional[str]:
    """Get the package that owns a file, if any."""
    ownership_file = ROOT / "registries" / "file_ownership.csv"
    if not ownership_file.exists():
        return None

    with open(ownership_file, "r") as f:
        for line in f:
            if line.startswith(path + ","):
                parts = line.strip().split(",")
                if len(parts) >= 2:
                    return parts[1]
    return None


def find_orphans() -> list:
    """Find files in governed roots that have no package owner."""
    orphans = []

    ownership_file = ROOT / "registries" / "file_ownership.csv"
    owned_files = set()

    if ownership_file.exists():
        with open(ownership_file, "r") as f:
            for line in f:
                if line.strip() and not line.startswith("file_path"):
                    parts = line.strip().split(",")
                    if parts:
                        owned_files.add(parts[0])

    # Scan governed roots
    for governed in GOVERNED_ROOTS:
        governed_path = ROOT / governed.rstrip("/")
        if not governed_path.exists():
            continue

        for file_path in governed_path.rglob("*"):
            if file_path.is_file():
                # Skip __pycache__ and other noise
                if "__pycache__" in str(file_path):
                    continue
                if file_path.suffix == ".pyc":
                    continue

                rel_path = str(file_path.relative_to(ROOT))
                # Skip derived files
                if rel_path in DERIVED_FILES:
                    continue
                if rel_path not in owned_files:
                    orphans.append(rel_path)

    return sorted(orphans)


def get_status() -> dict:
    """Get overall governance status."""
    orphans = find_orphans()

    # Count owned files
    ownership_file = ROOT / "registries" / "file_ownership.csv"
    owned_count = 0
    if ownership_file.exists():
        with open(ownership_file, "r") as f:
            owned_count = sum(1 for line in f if line.strip() and not line.startswith("file_path"))

    # Check seal status
    seal_file = ROOT / "config" / "seal.json"
    sealed = False
    if seal_file.exists():
        try:
            seal_data = json.loads(seal_file.read_text())
            sealed = seal_data.get("sealed", False)
        except:
            pass

    # Count installed packages
    installed_dir = ROOT / "installed"
    installed_packages = []
    if installed_dir.exists():
        for pkg_dir in installed_dir.iterdir():
            if pkg_dir.is_dir() and (pkg_dir / "receipt.json").exists():
                installed_packages.append(pkg_dir.name)

    return {
        "sealed": sealed,
        "owned_files": owned_count,
        "orphan_files": len(orphans),
        "installed_packages": len(installed_packages),
        "packages": installed_packages,
        "governance_health": "HEALTHY" if len(orphans) == 0 else "ORPHANS_DETECTED",
        "agent_guidance": {
            "can_write_to": AGENT_WRITABLE,
            "must_package_for": GOVERNED_ROOTS,
            "never_touch": FORBIDDEN_ROOTS,
        }
    }


def print_result(result: dict, as_json: bool = False):
    """Print result in human or JSON format."""
    if as_json:
        print(json.dumps(result, indent=2))
    else:
        if "can_write" in result:
            symbol = "✓" if result["can_write"] else "✗"
            print(f"{symbol} {result['path']}")
            print(f"  Classification: {result['classification']}")
            print(f"  Can Write: {result['can_write']}")
            print(f"  Reason: {result['reason']}")
            print(f"  Suggestion: {result['suggestion']}")

            # Add owner info if governed
            if result["classification"] == "GOVERNED":
                owner = get_file_owner(result["path"])
                if owner:
                    print(f"  Current Owner: {owner}")
                else:
                    print(f"  Current Owner: NONE (orphan)")
        elif "governance_health" in result:
            print("=== Control Plane Governance Status ===")
            print(f"Sealed: {result['sealed']}")
            print(f"Owned Files: {result['owned_files']}")
            print(f"Orphan Files: {result['orphan_files']}")
            print(f"Installed Packages: {result['installed_packages']}")
            print(f"Health: {result['governance_health']}")
            print()
            print("Agent Workspace (WRITE OK):")
            for path in result["agent_guidance"]["can_write_to"]:
                print(f"  ✓ {path}")
            print()
            print("Governed (PACKAGE REQUIRED):")
            for path in result["agent_guidance"]["must_package_for"]:
                print(f"  📦 {path}")
            print()
            print("Forbidden (NEVER WRITE):")
            for path in result["agent_guidance"]["never_touch"]:
                print(f"  ✗ {path}")


def main():
    parser = argparse.ArgumentParser(
        description="Agent pre-write validation for Control Plane governance",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Check if you can write to a path
    python3 scripts/agent_check.py --path lib/myfile.py

    # Get governance status
    python3 scripts/agent_check.py --status

    # Find orphan files
    python3 scripts/agent_check.py --orphans

    # JSON output
    python3 scripts/agent_check.py --path lib/foo.py --json
""")

    parser.add_argument("--path", action="append", help="Path(s) to check")
    parser.add_argument("--status", action="store_true", help="Show governance status")
    parser.add_argument("--orphans", action="store_true", help="List orphan files")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    # Default to status if no arguments
    if not args.path and not args.status and not args.orphans:
        args.status = True

    if args.status:
        status = get_status()
        print_result(status, args.json)
        sys.exit(0 if status["governance_health"] == "HEALTHY" else 1)

    if args.orphans:
        orphans = find_orphans()
        if args.json:
            print(json.dumps({"orphans": orphans, "count": len(orphans)}, indent=2))
        else:
            if orphans:
                print(f"Found {len(orphans)} orphan files:")
                for orphan in orphans:
                    print(f"  ⚠ {orphan}")
                print()
                print("To fix, either:")
                print("  1. Package them: pkgutil init PKG-XXX, add files, install")
                print("  2. Quarantine them: scripts/quarantine_orphans.py")
                print("  3. Add to baseline: scripts/generate_baseline_manifest.py")
            else:
                print("✓ No orphan files found")
        sys.exit(1 if orphans else 0)

    if args.path:
        all_writable = True
        results = []

        for path in args.path:
            result = classify_path(path)
            results.append(result)
            if not result["can_write"]:
                all_writable = False

        if args.json:
            print(json.dumps({"checks": results}, indent=2))
        else:
            for result in results:
                print_result(result, False)
                print()

        sys.exit(0 if all_writable else 1)


if __name__ == "__main__":
    main()
