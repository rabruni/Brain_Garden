#!/usr/bin/env python3
"""Remediate orphan files by organizing them into packages.

This script helps organize orphan files into logical packages for installation.

Usage:
    # See what needs to be done
    python3 scripts/remediate_orphans.py --plan

    # Create staging packages for orphans
    python3 scripts/remediate_orphans.py --execute

    # Verify after remediation
    python3 scripts/agent_check.py --orphans
"""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).parent.parent

# Package groupings for orphans
PACKAGE_GROUPS = {
    "PKG-SHELL-001": {
        "spec_id": "SPEC-SHELL-001",
        "framework_id": "FMWK-SHELL-001",
        "patterns": [
            "modules/shell/",
            "frameworks/FMWK-SHELL-001",
            "specs/SPEC-SHELL-001/",
            "tests/test_shell",
            "scripts/shell.py",
        ],
        "description": "Universal Shell for Control Plane",
    },
    "PKG-CHAT-001": {
        "spec_id": "SPEC-CHAT-001",
        "framework_id": "FMWK-CHAT-001",
        "patterns": [
            "modules/chat_interface/",
            "frameworks/FMWK-CHAT-001",
            "specs/SPEC-CHAT-001/",
            "tests/test_chat",
            "scripts/chat.py",
            "schemas/chat_",
        ],
        "description": "Chat Interface for Control Plane",
    },
    "PKG-BASELINE-UPDATE": {
        "spec_id": None,  # Will be added to baseline
        "patterns": [
            "docs/ADMIN_AGENT_SCRIPT_REF.md",
            "docs/AGENT_OPERATIONS_GUIDE.md",
            "docs/CROSSCUTTING.md",
            "modules/admin_agent/tools.py",
            "scripts/agent_check.py",
            "scripts/remediate_orphans.py",
            "tests/test_prompt_tracking.py",
        ],
        "description": "Files to add to baseline package",
    },
}


def find_orphans() -> List[str]:
    """Find orphan files."""
    result = subprocess.run(
        [sys.executable, "scripts/agent_check.py", "--orphans", "--json"],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    if result.returncode == 0:
        return []  # No orphans

    try:
        data = json.loads(result.stdout)
        return data.get("orphans", [])
    except:
        return []


def classify_orphan(path: str) -> str:
    """Determine which package group an orphan belongs to."""
    for pkg_id, config in PACKAGE_GROUPS.items():
        for pattern in config["patterns"]:
            if path.startswith(pattern) or pattern in path:
                return pkg_id
    return "UNKNOWN"


def plan_remediation(orphans: List[str]) -> Dict[str, List[str]]:
    """Group orphans by target package."""
    groups = {pkg_id: [] for pkg_id in PACKAGE_GROUPS}
    groups["UNKNOWN"] = []

    for orphan in orphans:
        pkg_id = classify_orphan(orphan)
        groups[pkg_id].append(orphan)

    return groups


def print_plan(groups: Dict[str, List[str]]):
    """Print the remediation plan."""
    print("=" * 60)
    print("ORPHAN REMEDIATION PLAN")
    print("=" * 60)

    total = sum(len(files) for files in groups.values())
    print(f"\nTotal orphans: {total}\n")

    for pkg_id, files in groups.items():
        if not files:
            continue

        config = PACKAGE_GROUPS.get(pkg_id, {})
        desc = config.get("description", "Unknown files")

        print(f"\n{'─' * 50}")
        print(f"📦 {pkg_id}")
        print(f"   {desc}")
        print(f"   Files: {len(files)}")
        print()

        for f in sorted(files):
            print(f"     • {f}")

        if pkg_id == "PKG-BASELINE-UPDATE":
            print()
            print("   Action: Regenerate baseline manifest to include these files")
            print("   Command:")
            print("     python3 scripts/generate_baseline_manifest.py --plane ho3")
        elif pkg_id != "UNKNOWN" and config.get("spec_id"):
            print()
            print(f"   Spec: {config.get('spec_id')}")
            print(f"   Framework: {config.get('framework_id')}")
            print("   Action: Create package in _staging/, preflight, install")
            print("   Commands:")
            print(f"     1. mkdir -p _staging/{pkg_id}")
            print(f"     2. # Copy files maintaining directory structure")
            print(f"     3. python3 scripts/pkgutil.py preflight {pkg_id} --src _staging/{pkg_id}")
            print(f"     4. python3 scripts/pkgutil.py stage {pkg_id} --src _staging/{pkg_id}")
            print(f"     5. CONTROL_PLANE_ALLOW_UNSIGNED=1 python3 scripts/package_install.py \\")
            print(f"          --archive _staging/{pkg_id}.tar.gz --id {pkg_id}")

    if groups.get("UNKNOWN"):
        print()
        print("⚠️  UNKNOWN files need manual classification.")
        print("   Either add them to an existing package group or create a new one.")


def create_staging_package(pkg_id: str, files: List[str], config: dict) -> bool:
    """Create a staging package for the given files."""
    staging_dir = ROOT / "_staging" / pkg_id

    if staging_dir.exists():
        print(f"  Warning: {staging_dir} already exists, skipping")
        return False

    staging_dir.mkdir(parents=True)

    # Copy files maintaining structure
    for file_path in files:
        src = ROOT / file_path
        if not src.exists():
            print(f"  Warning: {file_path} not found, skipping")
            continue

        dest = staging_dir / file_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)

    # Create manifest.json
    manifest = {
        "package_id": pkg_id,
        "schema_version": "1.2",
        "version": "1.0.0",
        "spec_id": config.get("spec_id", "SPEC-CORE-001"),
        "plane_id": "ho3",
        "package_type": "module",
        "assets": [],
        "dependencies": ["PKG-BASELINE-HO3-000"],
        "metadata": {
            "description": config.get("description", ""),
            "created_by": "remediate_orphans.py",
        }
    }

    # Add assets (hashes computed by preflight)
    for file_path in files:
        manifest["assets"].append({
            "path": file_path,
            "sha256": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
            "classification": classify_asset(file_path),
        })

    manifest_path = staging_dir / "manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"  Created staging package at {staging_dir}")
    return True


def classify_asset(path: str) -> str:
    """Classify an asset by path."""
    if path.startswith("lib/"):
        return "library"
    elif path.startswith("modules/"):
        return "module"
    elif path.startswith("scripts/"):
        return "script"
    elif path.startswith("tests/"):
        return "test"
    elif path.startswith("docs/"):
        return "documentation"
    elif path.startswith("frameworks/"):
        return "framework"
    elif path.startswith("specs/"):
        return "spec"
    elif path.startswith("schemas/"):
        return "schema"
    else:
        return "other"


def execute_remediation(groups: Dict[str, List[str]], dry_run: bool = False):
    """Execute the remediation plan."""
    print("=" * 60)
    print("EXECUTING REMEDIATION" + (" (DRY RUN)" if dry_run else ""))
    print("=" * 60)

    for pkg_id, files in groups.items():
        if not files:
            continue

        if pkg_id == "UNKNOWN":
            print(f"\n⚠️  Skipping {len(files)} UNKNOWN files (need manual classification)")
            continue

        if pkg_id == "PKG-BASELINE-UPDATE":
            print(f"\n📋 {pkg_id}: {len(files)} files")
            print("   These should be added to baseline via generate_baseline_manifest.py")
            continue

        config = PACKAGE_GROUPS.get(pkg_id, {})
        print(f"\n📦 {pkg_id}: {len(files)} files")

        if dry_run:
            print(f"   Would create staging package at _staging/{pkg_id}/")
        else:
            create_staging_package(pkg_id, files, config)

    print()
    if not dry_run:
        print("Next steps:")
        print("  1. Review staged packages in _staging/")
        print("  2. Run preflight on each: python3 scripts/pkgutil.py preflight PKG-XXX --src _staging/PKG-XXX")
        print("  3. Fix any preflight errors")
        print("  4. Stage: python3 scripts/pkgutil.py stage PKG-XXX --src _staging/PKG-XXX")
        print("  5. Install: CONTROL_PLANE_ALLOW_UNSIGNED=1 python3 scripts/package_install.py ...")


def main():
    parser = argparse.ArgumentParser(description="Remediate orphan files")
    parser.add_argument("--plan", action="store_true", help="Show remediation plan")
    parser.add_argument("--execute", action="store_true", help="Execute remediation (create staging packages)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without doing it")

    args = parser.parse_args()

    if not args.plan and not args.execute:
        args.plan = True

    orphans = find_orphans()
    if not orphans:
        print("✓ No orphan files found!")
        return

    groups = plan_remediation(orphans)

    if args.plan:
        print_plan(groups)
    elif args.execute:
        execute_remediation(groups, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
