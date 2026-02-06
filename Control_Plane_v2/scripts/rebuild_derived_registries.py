#!/usr/bin/env python3
"""
Rebuild Derived Registries from Ledger + Manifests

Rebuilds derived state registries (file_ownership.csv, packages_state.csv)
from the L-PACKAGE ledger and installed manifests.

BINDING CONSTRAINTS (from CP-IMPL-001):
- HO3-only scope: operates in HO3 governance context
- Two-class registry model:
  - DERIVED STATE: rebuilt from ledger+manifests (this script)
  - CURATED GOVERNANCE: never touched by this script
- No last-write-wins: ownership conflicts FAIL (not overwrite)
- Ledger is Memory: ledger is truth, manifests are proof

Derived registries:
- registries/file_ownership.csv
- registries/packages_state.csv
- registries/compiled/packages.json
- registries/compiled/file_ownership.json

Curated registries (NEVER touched):
- registries/control_plane_registry.csv
- registries/specs_registry.csv
- registries/frameworks_registry.csv

Usage:
    # Rebuild all derived registries
    python3 scripts/rebuild_derived_registries.py --plane ho3

    # Verify without writing
    python3 scripts/rebuild_derived_registries.py --plane ho3 --verify

    # Show diff
    python3 scripts/rebuild_derived_registries.py --plane ho3 --diff
"""

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Resolve paths relative to Control_Plane_v2 root
SCRIPT_DIR = Path(__file__).resolve().parent
CONTROL_PLANE_ROOT = SCRIPT_DIR.parent


# === Registry Definitions ===
DERIVED_REGISTRIES = [
    "registries/file_ownership.csv",
    "registries/packages_state.csv",
    "registries/compiled/packages.json",
    "registries/compiled/file_ownership.json",
]

CURATED_REGISTRIES = [
    "registries/control_plane_registry.csv",
    "registries/specs_registry.csv",
    "registries/frameworks_registry.csv",
]


class RebuildError(Exception):
    """Registry rebuild error."""
    pass


class OwnershipConflictError(RebuildError):
    """Two packages claim the same file without upgrade policy."""
    pass


def load_ledger_entries(plane: str) -> list[dict]:
    """
    Load all entries from L-PACKAGE ledger in chronological order.

    Returns list of entry dicts.
    """
    ledger_path = CONTROL_PLANE_ROOT / "ledger" / "packages.jsonl"

    if not ledger_path.exists():
        return []

    entries = []
    with open(ledger_path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                entries.append(entry)
            except json.JSONDecodeError as e:
                print(f"WARNING: Invalid JSON at line {line_num}: {e}", file=sys.stderr)

    return entries


def load_installed_manifest(package_id: str) -> Optional[dict]:
    """Load manifest from installed/<pkg_id>/manifest.json."""
    manifest_path = CONTROL_PLANE_ROOT / "installed" / package_id / "manifest.json"

    if not manifest_path.exists():
        return None

    return json.loads(manifest_path.read_text())


def is_upgrade_allowed(current_owner: str, new_owner: str) -> bool:
    """
    Check if ownership transfer is allowed.

    Transfer is permitted when *new_owner* explicitly declares
    *current_owner* as a direct dependency in its installed manifest.
    Only direct (non-transitive) dependencies are honoured.
    """
    new_manifest = load_installed_manifest(new_owner)
    if not new_manifest:
        return False
    declared_deps = new_manifest.get('dependencies', []) or new_manifest.get('deps', [])
    return isinstance(declared_deps, list) and current_owner in declared_deps


def build_ownership_from_ledger(entries: list[dict]) -> tuple[dict, list[dict]]:
    """
    Build file ownership map from ledger entries.

    Returns (ownership_map, conflicts) where:
    - ownership_map: {file_path: {owner_package_id, sha256, classification, installed_at}}
    - conflicts: list of conflict dicts

    Per binding constraints:
    - NO last-write-wins
    - Conflicts are detected and returned, not silently overwritten
    """
    ownership = {}
    conflicts = []
    installed_packages = {}  # package_id -> manifest_hash

    for entry in entries:
        event_type = entry.get("event_type")

        if event_type == "INSTALLED":
            package_id = entry.get("submission_id")
            timestamp = entry.get("timestamp")
            metadata = entry.get("metadata", {})
            manifest_hash = metadata.get("manifest_hash")

            # Load manifest
            manifest = load_installed_manifest(package_id)
            if not manifest:
                print(f"WARNING: No manifest found for {package_id}", file=sys.stderr)
                continue

            installed_packages[package_id] = manifest_hash

            # Claim ownership of all assets
            for asset in manifest.get("assets", []):
                file_path = asset["path"]

                if file_path in ownership:
                    existing = ownership[file_path]
                    if existing["owner_package_id"] != package_id:
                        # Conflict — check if dependency-based transfer is allowed
                        if is_upgrade_allowed(existing["owner_package_id"], package_id):
                            print(
                                f"  Transfer: {file_path} from {existing['owner_package_id']}"
                                f" to {package_id} (dependency)",
                                file=sys.stderr,
                            )
                            # Fall through to update ownership below
                        else:
                            conflicts.append({
                                "file_path": file_path,
                                "current_owner": existing["owner_package_id"],
                                "conflicting_owner": package_id,
                                "current_installed_at": existing["installed_at"],
                                "conflicting_installed_at": timestamp,
                            })
                            continue  # Don't overwrite

                ownership[file_path] = {
                    "file_path": file_path,
                    "owner_package_id": package_id,
                    "sha256": asset.get("sha256", ""),
                    "classification": asset.get("classification", "other"),
                    "installed_at": timestamp,
                }

        elif event_type == "UNINSTALLED":
            package_id = entry.get("submission_id")

            # Remove ownership for all assets owned by this package
            # Load manifest to know what files to release
            manifest = load_installed_manifest(package_id)
            if manifest:
                for asset in manifest.get("assets", []):
                    file_path = asset["path"]
                    if ownership.get(file_path, {}).get("owner_package_id") == package_id:
                        del ownership[file_path]

            if package_id in installed_packages:
                del installed_packages[package_id]

    return ownership, conflicts


def build_packages_state(entries: list[dict]) -> dict:
    """
    Build packages state map from ledger entries.

    Returns {package_id: {status, manifest_hash, installed_at, ...}}
    """
    packages = {}

    for entry in entries:
        event_type = entry.get("event_type")
        package_id = entry.get("submission_id")
        timestamp = entry.get("timestamp")
        metadata = entry.get("metadata", {})

        if event_type == "INSTALLED":
            packages[package_id] = {
                "package_id": package_id,
                "status": "installed",
                "manifest_hash": metadata.get("manifest_hash", ""),
                "package_type": metadata.get("package_type", ""),
                "plane_id": metadata.get("plane_id", "ho3"),
                "assets_count": metadata.get("assets_count", 0),
                "installed_at": timestamp,
            }

        elif event_type == "UNINSTALLED":
            if package_id in packages:
                packages[package_id]["status"] = "uninstalled"
                packages[package_id]["uninstalled_at"] = timestamp

    return packages


def write_file_ownership_csv(ownership: dict, output_path: Path) -> None:
    """Write file_ownership.csv."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = ["file_path", "owner_package_id", "sha256", "classification", "installed_at"]

    # Sort by file_path for determinism
    rows = sorted(ownership.values(), key=lambda r: r["file_path"])

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_packages_state_csv(packages: dict, output_path: Path) -> None:
    """Write packages_state.csv."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = ["package_id", "status", "manifest_hash", "package_type", "plane_id", "assets_count", "installed_at", "uninstalled_at"]

    # Sort by package_id for determinism
    rows = sorted(packages.values(), key=lambda r: r["package_id"])

    # Ensure all fields exist
    for row in rows:
        for field in fieldnames:
            row.setdefault(field, "")

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_compiled_json(data: dict, output_path: Path) -> None:
    """Write compiled JSON registry."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(data, indent=2, sort_keys=True))


def load_existing_registry(path: Path) -> list[dict]:
    """Load existing CSV registry as list of dicts."""
    if not path.exists():
        return []

    rows = []
    with open(path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def compare_registries(
    current: list[dict],
    rebuilt: list[dict],
    key_field: str = "file_path"
) -> dict:
    """
    Compare current and rebuilt registries.

    Returns {matches: bool, added: [], removed: [], changed: []}
    """
    current_by_key = {r[key_field]: r for r in current}
    rebuilt_by_key = {r[key_field]: r for r in rebuilt}

    current_keys = set(current_by_key.keys())
    rebuilt_keys = set(rebuilt_by_key.keys())

    added = sorted(rebuilt_keys - current_keys)
    removed = sorted(current_keys - rebuilt_keys)
    changed = []

    for key in current_keys & rebuilt_keys:
        if current_by_key[key] != rebuilt_by_key[key]:
            changed.append({
                "key": key,
                "current": current_by_key[key],
                "rebuilt": rebuilt_by_key[key],
            })

    return {
        "matches": len(added) == 0 and len(removed) == 0 and len(changed) == 0,
        "added": added,
        "removed": removed,
        "changed": changed,
    }


def rebuild_derived_registries(
    plane: str,
    verify_only: bool = False,
    show_diff: bool = False,
) -> dict:
    """
    Rebuild all derived registries from ledger + manifests.

    Args:
        plane: Target plane (ho3 only in Phase 1)
        verify_only: Compare without writing
        show_diff: Show differences

    Returns:
        Result dict with status and details
    """
    if plane != "ho3":
        raise RebuildError(f"Phase 1 is HO3-only. Got plane={plane}")

    print(f"[rebuild] Loading L-PACKAGE ledger...", file=sys.stderr)
    entries = load_ledger_entries(plane)
    print(f"[rebuild] Found {len(entries)} ledger entries", file=sys.stderr)

    # Build ownership map
    print(f"[rebuild] Building ownership map...", file=sys.stderr)
    ownership, conflicts = build_ownership_from_ledger(entries)
    print(f"[rebuild] Found {len(ownership)} owned files", file=sys.stderr)

    if conflicts:
        print(f"[rebuild] CONFLICTS DETECTED: {len(conflicts)}", file=sys.stderr)
        for c in conflicts[:5]:
            print(f"  {c['file_path']}: {c['current_owner']} vs {c['conflicting_owner']}", file=sys.stderr)
        if len(conflicts) > 5:
            print(f"  ... and {len(conflicts) - 5} more", file=sys.stderr)
        raise OwnershipConflictError(f"{len(conflicts)} ownership conflicts detected")

    # Build packages state
    print(f"[rebuild] Building packages state...", file=sys.stderr)
    packages = build_packages_state(entries)
    print(f"[rebuild] Found {len(packages)} packages", file=sys.stderr)

    # Prepare output paths
    file_ownership_path = CONTROL_PLANE_ROOT / "registries" / "file_ownership.csv"
    packages_state_path = CONTROL_PLANE_ROOT / "registries" / "packages_state.csv"
    compiled_dir = CONTROL_PLANE_ROOT / "registries" / "compiled"

    result = {
        "success": True,
        "plane": plane,
        "files_owned": len(ownership),
        "packages": len(packages),
        "conflicts": len(conflicts),
        "verify_only": verify_only,
    }

    if verify_only or show_diff:
        # Compare with existing
        print(f"[rebuild] Comparing with existing registries...", file=sys.stderr)

        current_ownership = load_existing_registry(file_ownership_path)
        rebuilt_ownership = sorted(ownership.values(), key=lambda r: r["file_path"])

        comparison = compare_registries(
            current_ownership,
            rebuilt_ownership,
            key_field="file_path"
        )

        result["matches"] = comparison["matches"]
        result["added"] = len(comparison["added"])
        result["removed"] = len(comparison["removed"])
        result["changed"] = len(comparison["changed"])

        if show_diff:
            if comparison["added"]:
                print(f"\n=== ADDED ({len(comparison['added'])}) ===", file=sys.stderr)
                for path in comparison["added"][:10]:
                    print(f"  + {path}", file=sys.stderr)
                if len(comparison["added"]) > 10:
                    print(f"  ... and {len(comparison['added']) - 10} more", file=sys.stderr)

            if comparison["removed"]:
                print(f"\n=== REMOVED ({len(comparison['removed'])}) ===", file=sys.stderr)
                for path in comparison["removed"][:10]:
                    print(f"  - {path}", file=sys.stderr)
                if len(comparison["removed"]) > 10:
                    print(f"  ... and {len(comparison['removed']) - 10} more", file=sys.stderr)

            if comparison["changed"]:
                print(f"\n=== CHANGED ({len(comparison['changed'])}) ===", file=sys.stderr)
                for change in comparison["changed"][:5]:
                    print(f"  ~ {change['key']}", file=sys.stderr)
                if len(comparison["changed"]) > 5:
                    print(f"  ... and {len(comparison['changed']) - 5} more", file=sys.stderr)

        if verify_only:
            return result

    # Write derived registries
    print(f"[rebuild] Writing file_ownership.csv...", file=sys.stderr)
    write_file_ownership_csv(ownership, file_ownership_path)

    print(f"[rebuild] Writing packages_state.csv...", file=sys.stderr)
    write_packages_state_csv(packages, packages_state_path)

    print(f"[rebuild] Writing compiled/file_ownership.json...", file=sys.stderr)
    write_compiled_json(
        {"files": list(ownership.values()), "rebuilt_at": datetime.now(timezone.utc).isoformat()},
        compiled_dir / "file_ownership.json"
    )

    print(f"[rebuild] Writing compiled/packages.json...", file=sys.stderr)
    write_compiled_json(
        {"packages": list(packages.values()), "rebuilt_at": datetime.now(timezone.utc).isoformat()},
        compiled_dir / "packages.json"
    )

    result["written"] = [
        str(file_ownership_path),
        str(packages_state_path),
        str(compiled_dir / "file_ownership.json"),
        str(compiled_dir / "packages.json"),
    ]

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Rebuild derived registries from ledger + manifests",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Rebuild all derived registries
    python3 scripts/rebuild_derived_registries.py --plane ho3

    # Verify without writing
    python3 scripts/rebuild_derived_registries.py --plane ho3 --verify

    # Show differences
    python3 scripts/rebuild_derived_registries.py --plane ho3 --diff
"""
    )

    parser.add_argument(
        "--plane",
        required=True,
        choices=["ho3"],  # Phase 1 is HO3-only
        help="Target plane (Phase 1: ho3 only)"
    )

    parser.add_argument(
        "--verify",
        action="store_true",
        help="Compare without writing"
    )

    parser.add_argument(
        "--diff",
        action="store_true",
        help="Show differences"
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="Output result as JSON"
    )

    args = parser.parse_args()

    try:
        result = rebuild_derived_registries(
            plane=args.plane,
            verify_only=args.verify,
            show_diff=args.diff,
        )

        if args.json:
            print(json.dumps(result, indent=2))
        else:
            if args.verify:
                if result.get("matches"):
                    print(f"\nDerived registries MATCH ledger + manifests")
                else:
                    print(f"\nDerived registries DIFFER from ledger + manifests:")
                    print(f"  Added:   {result.get('added', 0)}")
                    print(f"  Removed: {result.get('removed', 0)}")
                    print(f"  Changed: {result.get('changed', 0)}")
            else:
                print(f"\nDerived registries rebuilt:")
                print(f"  Files owned: {result['files_owned']}")
                print(f"  Packages:    {result['packages']}")
                for path in result.get("written", []):
                    print(f"  Wrote: {path}")

        return 0 if result.get("success") else 1

    except OwnershipConflictError as e:
        print(f"OWNERSHIP CONFLICT: {e}", file=sys.stderr)
        return 2

    except RebuildError as e:
        print(f"REBUILD ERROR: {e}", file=sys.stderr)
        return 1

    except Exception as e:
        print(f"UNEXPECTED ERROR: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 99


if __name__ == "__main__":
    sys.exit(main())
