#!/usr/bin/env python3
"""
integrity_check.py - Registry Integrity Verification (SCRIPT-014)

Two-pass validation + Merkle root for cryptographic verification of all
registered artifacts. Detects invalid hashes, missing files, and orphans.

Philosophy: Trust but verify. Governance is only as good as its enforcement.

Usage:
    python3 scripts/integrity_check.py --verify
    python3 scripts/integrity_check.py --update-hashes
    python3 scripts/integrity_check.py --orphans
    python3 scripts/integrity_check.py --json
    python3 scripts/integrity_check.py --root /path/to/plane

Exit codes:
    0 = All verified, no issues
    1 = Issues found (mismatch, missing, orphans)
    2 = Error
"""

import argparse
import csv
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, TYPE_CHECKING

# Add parent to path for lib imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.paths import CONTROL_PLANE, REGISTRIES_DIR
from lib.plane import get_current_plane, PlaneContext
from lib.merkle import hash_file, merkle_root


# Module-level state for plane-aware operation
_plane: Optional[PlaneContext] = None
_plane_root: Path = CONTROL_PLANE
_registries_dir: Path = REGISTRIES_DIR


def set_plane_context(plane: Optional[PlaneContext]) -> None:
    """Set the plane context for all operations."""
    global _plane, _plane_root, _registries_dir
    _plane = plane
    if plane is not None:
        _plane_root = plane.root
        _registries_dir = plane.root / "registries"
    else:
        _plane_root = CONTROL_PLANE
        _registries_dir = REGISTRIES_DIR

# =============================================================================
# Configuration
# =============================================================================

# Directories to scan for orphan detection
ARTIFACT_DIRS = [
    "frameworks",
    "scripts",
    "lib",
    "prompts",
    "modules",
    "specs",
]

# File patterns to include in orphan detection
ARTIFACT_EXTENSIONS = {".py", ".md", ".csv", ".json", ".yaml", ".yml"}

# Directories/files to exclude from orphan detection
ORPHAN_EXCLUSIONS = {
    "__pycache__",
    ".git",
    ".pytest_cache",
    "node_modules",
    "__init__.py",  # Allow init files without registration
}


# =============================================================================
# Data Structures
# =============================================================================

@dataclass
class IntegrityResult:
    """Result of integrity verification."""
    valid: List[str] = field(default_factory=list)       # IDs with matching hashes
    invalid: List[Tuple[str, str, str]] = field(default_factory=list)  # (ID, expected, actual)
    missing: List[Tuple[str, str]] = field(default_factory=list)       # (ID, path)
    no_hash: List[str] = field(default_factory=list)     # IDs without content_hash
    orphans: List[str] = field(default_factory=list)     # Paths not in registry
    chain_errors: List[Tuple[str, str, str]] = field(default_factory=list)  # (ID, link_type, target)
    merkle_root: str = ""

    @property
    def is_healthy(self) -> bool:
        return not self.invalid and not self.missing and not self.chain_errors

    @property
    def total_verified(self) -> int:
        return len(self.valid)

    @property
    def total_issues(self) -> int:
        return len(self.invalid) + len(self.missing)


# =============================================================================
# Registry Operations
# =============================================================================

def read_control_plane_registry() -> Tuple[List[Dict[str, str]], List[str]]:
    """Read control_plane_registry.csv and return rows + fieldnames."""
    registry_path = _registries_dir / "control_plane_registry.csv"
    if not registry_path.exists():
        return [], []

    with open(registry_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        rows = list(reader)

    return rows, fieldnames


def write_control_plane_registry(rows: List[Dict[str, str]], fieldnames: List[str]) -> None:
    """Write control_plane_registry.csv with updated content."""
    registry_path = _registries_dir / "control_plane_registry.csv"

    with open(registry_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def get_registered_paths() -> Set[str]:
    """Get all artifact_path values from control_plane_registry, including child registries."""
    rows, _ = read_control_plane_registry()
    paths = set()

    def add_path(p: str):
        if not p:
            return
        paths.add(p.lstrip("/"))

    # Collect top-level artifact paths
    for row in rows:
        add_path(row.get("artifact_path", "").strip())

    # If a row points to a child registry (pack/shaper/etc.), include its entries
    for row in rows:
        etype = row.get("entity_type", "").strip().lower()
        art = row.get("artifact_path", "").strip().lstrip("/")
        if etype in {"pack", "registry"} and art.endswith("registry.csv"):
            child_path = _plane_root / art
            if child_path.is_file():
                try:
                    with child_path.open(newline="", encoding="utf-8") as f:
                        for crow in csv.DictReader(f):
                            add_path(crow.get("artifact_path", "").strip())
                except Exception:
                    continue

    return paths


def read_specs_registry() -> List[Dict[str, str]]:
    """Read specs_registry.csv and return rows."""
    specs_path = _registries_dir / "specs_registry.csv"
    if not specs_path.exists():
        return []

    with open(specs_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


# =============================================================================
# Pass 1: Registry -> Filesystem
# =============================================================================

def verify_registry_hashes() -> IntegrityResult:
    """
    Pass 1: For each registered artifact, verify file hash matches stored hash.

    Returns:
        IntegrityResult with valid, invalid, missing, and no_hash lists
    """
    result = IntegrityResult()
    rows, _ = read_control_plane_registry()
    all_hashes = []

    for row in rows:
        item_id = row.get("id", "")
        artifact_path = row.get("artifact_path", "").strip()
        stored_hash = row.get("content_hash", "").strip()

        if not artifact_path:
            continue

        # Resolve full path
        full_path = _plane_root / artifact_path.lstrip("/")

        # Check if file exists
        if not full_path.exists():
            result.missing.append((item_id, artifact_path))
            continue

        # Handle directory artifacts (modules)
        if full_path.is_dir():
            # For directories, we hash the concatenation of all file hashes
            dir_hashes = []
            for file_path in sorted(full_path.rglob("*")):
                if file_path.is_file() and not any(ex in str(file_path) for ex in ORPHAN_EXCLUSIONS):
                    try:
                        dir_hashes.append(hash_file(file_path))
                    except (PermissionError, OSError):
                        pass
            actual_hash = merkle_root(dir_hashes) if dir_hashes else ""
        else:
            # Compute actual hash
            try:
                actual_hash = hash_file(full_path)
            except (PermissionError, OSError) as e:
                result.missing.append((item_id, f"{artifact_path} (error: {e})"))
                continue

        # Collect hash for Merkle root
        if actual_hash:
            all_hashes.append(actual_hash)

        # Check if stored hash exists
        if not stored_hash:
            result.no_hash.append(item_id)
            continue

        # Verify hash matches
        if actual_hash.lower() == stored_hash.lower():
            result.valid.append(item_id)
        else:
            result.invalid.append((item_id, stored_hash, actual_hash))

    # Compute overall Merkle root
    result.merkle_root = merkle_root(sorted(all_hashes))

    return result


# =============================================================================
# Pass 2: Filesystem -> Registry
# =============================================================================

def find_orphans() -> List[str]:
    """
    Pass 2: Scan artifact directories for files not in any registry.

    Returns:
        List of orphaned file paths (relative to plane root)
    """
    registered_paths = get_registered_paths()
    orphans = []

    for dir_name in ARTIFACT_DIRS:
        dir_path = _plane_root / dir_name
        if not dir_path.exists():
            continue

        for file_path in dir_path.rglob("*"):
            # Skip excluded items
            if any(ex in file_path.parts for ex in ORPHAN_EXCLUSIONS):
                continue

            # Skip directories
            if file_path.is_dir():
                continue

            # Skip non-artifact extensions
            if file_path.suffix.lower() not in ARTIFACT_EXTENSIONS:
                continue

            # Check if registered
            rel_path = str(file_path.relative_to(_plane_root))
            if rel_path not in registered_paths and f"/{rel_path}" not in registered_paths:
                orphans.append(rel_path)

    return sorted(orphans)


# =============================================================================
# Pass 3: Chain Link Validation
# =============================================================================

def verify_chain_links() -> List[Tuple[str, str, str]]:
    """
    Pass 3: Verify all structural links in the artifact chain.

    Validates:
    - Artifact -> Spec (source_spec_id)
    - Spec -> Framework (complies_with)
    - Framework -> Framework (dependencies)
    - All linked paths exist on disk

    Returns:
        List of (id, link_type, broken_target) tuples for broken links
    """
    errors = []

    # Load registries once
    artifacts, _ = read_control_plane_registry()
    specs = read_specs_registry()

    # Build lookup dicts (O(1) lookups)
    artifacts_by_id = {row['id']: row for row in artifacts}
    # specs_registry uses 'spec_id' field, not 'id'
    specs_by_id = {row.get('spec_id', row.get('id', '')): row for row in specs}

    # 1. Verify artifact -> spec links
    for row in artifacts:
        item_id = row.get('id', '')
        source_spec = row.get('source_spec_id', '').strip()

        if source_spec:
            # Check spec exists in specs_registry
            if source_spec not in specs_by_id:
                errors.append((item_id, 'source_spec_id', source_spec))
            else:
                # Check spec directory exists on disk (specs are directories, not files)
                spec = specs_by_id[source_spec]
                spec_id_val = spec.get('spec_id', spec.get('id', ''))
                spec_path = _plane_root / "specs" / spec_id_val / "manifest.yaml"
                if not spec_path.exists():
                    # Also check if it's an old-style spec (just YAML file)
                    alt_path = _plane_root / "specs" / f"{spec_id_val}.yaml"
                    if not alt_path.exists():
                        errors.append((item_id, 'source_spec_path', str(spec_path)))

    # 2. Verify spec -> framework links
    for spec in specs:
        spec_id = spec.get('spec_id', spec.get('id', ''))
        # specs_registry uses 'framework_id', not 'complies_with'
        complies_with = spec.get('framework_id', spec.get('complies_with', '')).strip()

        if complies_with:
            for fmwk_id in complies_with.split(','):
                fmwk_id = fmwk_id.strip()
                if fmwk_id:
                    # Check framework exists in control_plane_registry
                    if fmwk_id not in artifacts_by_id:
                        errors.append((spec_id, 'complies_with', fmwk_id))
                    else:
                        # Check framework path exists on disk
                        fmwk = artifacts_by_id[fmwk_id]
                        fmwk_path = _plane_root / fmwk.get('artifact_path', '').lstrip('/')
                        if not fmwk_path.exists():
                            errors.append((spec_id, 'framework_path', str(fmwk_path)))

        # 3. Verify spec -> artifacts_created links
        created = spec.get('artifacts_created', '').strip()
        if created:
            for art_id in created.split(','):
                art_id = art_id.strip()
                if art_id and art_id not in artifacts_by_id:
                    errors.append((spec_id, 'artifacts_created', art_id))

    # 4. Verify framework -> framework links (dependencies)
    for row in artifacts:
        if row.get('entity_type') != 'framework':
            continue

        item_id = row.get('id', '')
        deps = row.get('dependencies', '').strip()

        if deps:
            for dep_id in deps.split(','):
                dep_id = dep_id.strip().strip('"')
                # Only check framework dependencies (skip LIB-*, etc.)
                if dep_id.startswith('FMWK-'):
                    if dep_id not in artifacts_by_id:
                        errors.append((item_id, 'dependency', dep_id))

    return errors


# =============================================================================
# Hash Update
# =============================================================================

def update_registry_hashes() -> int:
    """
    Update content_hash column in control_plane_registry.csv.

    Returns:
        Number of hashes updated
    """
    rows, fieldnames = read_control_plane_registry()

    # Ensure content_hash column exists
    if "content_hash" not in fieldnames:
        # Insert before 'config' if it exists, otherwise at end
        if "config" in fieldnames:
            idx = fieldnames.index("config")
            fieldnames.insert(idx, "content_hash")
        else:
            fieldnames.append("content_hash")

    updated_count = 0

    for row in rows:
        artifact_path = row.get("artifact_path", "").strip()
        if not artifact_path:
            row["content_hash"] = ""
            continue

        full_path = _plane_root / artifact_path.lstrip("/")

        if not full_path.exists():
            row["content_hash"] = ""
            continue

        # Handle directory artifacts
        if full_path.is_dir():
            dir_hashes = []
            for file_path in sorted(full_path.rglob("*")):
                if file_path.is_file() and not any(ex in str(file_path) for ex in ORPHAN_EXCLUSIONS):
                    try:
                        dir_hashes.append(hash_file(file_path))
                    except (PermissionError, OSError):
                        pass
            new_hash = merkle_root(dir_hashes) if dir_hashes else ""
        else:
            try:
                new_hash = hash_file(full_path)
            except (PermissionError, OSError):
                new_hash = ""

        old_hash = row.get("content_hash", "")
        if new_hash != old_hash:
            updated_count += 1

        row["content_hash"] = new_hash

    write_control_plane_registry(rows, fieldnames)
    return updated_count


# =============================================================================
# Output Formatters
# =============================================================================

def format_report(result: IntegrityResult, orphans: List[str], show_orphans: bool = True) -> str:
    """Format human-readable integrity report."""
    lines = []
    lines.append("")
    lines.append("REGISTRY INTEGRITY CHECK")
    lines.append("=" * 66)
    lines.append("")

    # Summary
    status = "HEALTHY" if result.is_healthy else "ISSUES FOUND"
    lines.append(f"Status: {status}")
    lines.append(f"Verified: {result.total_verified} artifacts")
    lines.append(f"Merkle Root: {result.merkle_root[:16]}..." if result.merkle_root else "Merkle Root: (none)")
    lines.append("")

    # Issues
    if result.invalid:
        lines.append(f"HASH MISMATCHES ({len(result.invalid)}):")
        for item_id, expected, actual in result.invalid[:10]:
            lines.append(f"  - {item_id}: expected {expected[:12]}... got {actual[:12]}...")
        if len(result.invalid) > 10:
            lines.append(f"  ... and {len(result.invalid) - 10} more")
        lines.append("")

    if result.missing:
        lines.append(f"MISSING FILES ({len(result.missing)}):")
        for item_id, path in result.missing[:10]:
            lines.append(f"  - {item_id}: {path}")
        if len(result.missing) > 10:
            lines.append(f"  ... and {len(result.missing) - 10} more")
        lines.append("")

    if result.no_hash:
        lines.append(f"NO STORED HASH ({len(result.no_hash)}):")
        for item_id in result.no_hash[:10]:
            lines.append(f"  - {item_id}")
        if len(result.no_hash) > 10:
            lines.append(f"  ... and {len(result.no_hash) - 10} more")
        lines.append("")

    if show_orphans and orphans:
        lines.append(f"ORPHANED FILES ({len(orphans)}):")
        for path in orphans[:15]:
            lines.append(f"  - {path}")
        if len(orphans) > 15:
            lines.append(f"  ... and {len(orphans) - 15} more")
        lines.append("")

    if result.chain_errors:
        lines.append(f"CHAIN LINK ERRORS ({len(result.chain_errors)}):")
        for item_id, link_type, target in result.chain_errors[:15]:
            lines.append(f"  - {item_id}: {link_type} -> {target}")
        if len(result.chain_errors) > 15:
            lines.append(f"  ... and {len(result.chain_errors) - 15} more")
        lines.append("")

    if result.is_healthy and not orphans and not result.chain_errors:
        lines.append("All registered artifacts verified successfully.")

    lines.append("")
    return "\n".join(lines)


def format_json(result: IntegrityResult, orphans: List[str]) -> str:
    """Format JSON output."""
    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "healthy": result.is_healthy,
        "merkle_root": result.merkle_root,
        "verified_count": result.total_verified,
        "valid": result.valid,
        "invalid": [{"id": i, "expected": e, "actual": a} for i, e, a in result.invalid],
        "missing": [{"id": i, "path": p} for i, p in result.missing],
        "no_hash": result.no_hash,
        "chain_errors": [{"id": i, "link_type": t, "target": g} for i, t, g in result.chain_errors],
        "chain_error_count": len(result.chain_errors),
        "orphans": orphans,
        "orphan_count": len(orphans),
    }
    return json.dumps(output, indent=2)


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Registry integrity verification with Merkle tree support."
    )
    parser.add_argument(
        "--verify", "-v",
        action="store_true",
        help="Verify registry hashes against filesystem (Pass 1)"
    )
    parser.add_argument(
        "--orphans", "-o",
        action="store_true",
        help="Find orphaned files not in registry (Pass 2)"
    )
    parser.add_argument(
        "--chain", "-c",
        action="store_true",
        help="Verify chain links: artifact->spec->framework (Pass 3)"
    )
    parser.add_argument(
        "--update-hashes", "-u",
        action="store_true",
        help="Update content_hash column in registry"
    )
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output JSON instead of formatted text"
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Only output summary line"
    )
    parser.add_argument(
        "--root",
        type=Path,
        help="Plane root path (for multi-plane operation)"
    )

    args = parser.parse_args()

    # Set plane context
    plane_root = args.root.resolve() if args.root else None
    plane = get_current_plane(plane_root)
    set_plane_context(plane)

    # Default to --verify if no action specified
    if not any([args.verify, args.orphans, args.chain, args.update_hashes]):
        args.verify = True
        args.orphans = True
        args.chain = True

    try:
        # Update hashes if requested
        if args.update_hashes:
            updated = update_registry_hashes()
            if not args.json:
                print(f"Updated {updated} content hashes in registry.")
            return 0

        # Run verification
        result = IntegrityResult()
        orphans = []

        if args.verify:
            result = verify_registry_hashes()

        if args.orphans:
            orphans = find_orphans()

        if args.chain:
            result.chain_errors = verify_chain_links()

        # Output
        if args.json:
            print(format_json(result, orphans))
        elif args.quiet:
            status = "OK" if result.is_healthy and not orphans else "ISSUES"
            print(f"Integrity: {status} | Verified: {result.total_verified} | Orphans: {len(orphans)} | Chain: {len(result.chain_errors)} errors")
        else:
            print(format_report(result, orphans, show_orphans=args.orphans))

        # Exit code
        if result.invalid or result.missing or result.chain_errors:
            return 1
        return 0

    except Exception as e:
        if args.json:
            print(json.dumps({"error": str(e)}))
        else:
            print(f"Error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
