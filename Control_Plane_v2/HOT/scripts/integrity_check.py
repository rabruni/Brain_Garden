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

from kernel.paths import CONTROL_PLANE, REGISTRIES_DIR
from kernel.plane import get_current_plane, PlaneContext
from kernel.merkle import hash_file, merkle_root


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

# Frozen set for O(1) membership tests in path component checks
_ORPHAN_EXCLUSIONS_FROZEN = frozenset(ORPHAN_EXCLUSIONS)


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
# IntegrityChecker Class
# =============================================================================

class IntegrityChecker:
    """Encapsulates integrity check state and operations.

    Replaces the former module-level global state (_plane_root, _registries_dir).
    """

    def __init__(self, plane: Optional[PlaneContext] = None):
        if plane is not None:
            self.root = plane.root
        else:
            self.root = CONTROL_PLANE
        self.registries_dir = self.root / "registries"

    # -----------------------------------------------------------------
    # Registry I/O
    # -----------------------------------------------------------------

    def read_control_plane_registry(self) -> Tuple[List[Dict[str, str]], List[str]]:
        """Read control_plane_registry.csv and return rows + fieldnames."""
        registry_path = self.registries_dir / "control_plane_registry.csv"
        if not registry_path.exists():
            return [], []

        with open(registry_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames or []
            rows = list(reader)

        return rows, fieldnames

    def write_control_plane_registry(self, rows: List[Dict[str, str]], fieldnames: List[str]) -> None:
        """Write control_plane_registry.csv with updated content."""
        registry_path = self.registries_dir / "control_plane_registry.csv"

        with open(registry_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def get_registered_paths(self) -> Set[str]:
        """Get all artifact_path values from control_plane_registry, including child registries."""
        rows, _ = self.read_control_plane_registry()
        paths = set()

        def add_path(p: str):
            if not p:
                return
            paths.add(p.lstrip("/"))

        for row in rows:
            add_path(row.get("artifact_path", "").strip())

        for row in rows:
            etype = row.get("entity_type", "").strip().lower()
            art = row.get("artifact_path", "").strip().lstrip("/")
            if etype in {"pack", "registry"} and art.endswith("registry.csv"):
                child_path = self.root / art
                if child_path.is_file():
                    try:
                        with child_path.open(newline="", encoding="utf-8") as f:
                            for crow in csv.DictReader(f):
                                add_path(crow.get("artifact_path", "").strip())
                    except Exception:
                        continue

        return paths

    def read_specs_registry(self) -> List[Dict[str, str]]:
        """Read specs_registry.csv and return rows."""
        specs_path = self.registries_dir / "specs_registry.csv"
        if not specs_path.exists():
            return []

        with open(specs_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            return list(reader)

    # -----------------------------------------------------------------
    # Pass 1: Registry -> Filesystem
    # -----------------------------------------------------------------

    def _is_excluded(self, file_path: Path) -> bool:
        """Check if any path component matches exclusion set (O(1) per component)."""
        return bool(_ORPHAN_EXCLUSIONS_FROZEN.intersection(file_path.parts))

    def verify_registry_hashes(self) -> IntegrityResult:
        """Pass 1: For each registered artifact, verify file hash matches stored hash."""
        result = IntegrityResult()
        rows, _ = self.read_control_plane_registry()
        all_hashes = []

        for row in rows:
            item_id = row.get("id", "")
            artifact_path = row.get("artifact_path", "").strip()
            stored_hash = row.get("content_hash", "").strip()

            if not artifact_path:
                continue

            full_path = self.root / artifact_path.lstrip("/")

            if not full_path.exists():
                result.missing.append((item_id, artifact_path))
                continue

            if full_path.is_dir():
                dir_hashes = []
                for file_path in sorted(full_path.rglob("*")):
                    if file_path.is_file() and not self._is_excluded(file_path):
                        try:
                            dir_hashes.append(hash_file(file_path))
                        except (PermissionError, OSError):
                            pass
                actual_hash = merkle_root(dir_hashes) if dir_hashes else ""
            else:
                try:
                    actual_hash = hash_file(full_path)
                except (PermissionError, OSError) as e:
                    result.missing.append((item_id, f"{artifact_path} (error: {e})"))
                    continue

            if actual_hash:
                all_hashes.append(actual_hash)

            if not stored_hash:
                result.no_hash.append(item_id)
                continue

            if actual_hash.lower() == stored_hash.lower():
                result.valid.append(item_id)
            else:
                result.invalid.append((item_id, stored_hash, actual_hash))

        result.merkle_root = merkle_root(sorted(all_hashes))
        return result

    # -----------------------------------------------------------------
    # Pass 2: Filesystem -> Registry
    # -----------------------------------------------------------------

    def find_orphans(self) -> List[str]:
        """Pass 2: Scan artifact directories for files not in any registry."""
        registered_paths = self.get_registered_paths()
        orphans = []

        for dir_name in ARTIFACT_DIRS:
            dir_path = self.root / dir_name
            if not dir_path.exists():
                continue

            for file_path in dir_path.rglob("*"):
                if self._is_excluded(file_path):
                    continue
                if file_path.is_dir():
                    continue
                if file_path.suffix.lower() not in ARTIFACT_EXTENSIONS:
                    continue

                rel_path = str(file_path.relative_to(self.root))
                if rel_path not in registered_paths and f"/{rel_path}" not in registered_paths:
                    orphans.append(rel_path)

        return sorted(orphans)

    # -----------------------------------------------------------------
    # Pass 3: Chain Link Validation
    # -----------------------------------------------------------------

    def verify_chain_links(self) -> List[Tuple[str, str, str]]:
        """Pass 3: Verify all structural links in the artifact chain."""
        errors = []

        artifacts, _ = self.read_control_plane_registry()
        specs = self.read_specs_registry()

        artifacts_by_id = {row['id']: row for row in artifacts}
        specs_by_id = {row.get('spec_id', row.get('id', '')): row for row in specs}

        # 1. Verify artifact -> spec links
        for row in artifacts:
            item_id = row.get('id', '')
            source_spec = row.get('source_spec_id', '').strip()

            if source_spec:
                if source_spec not in specs_by_id:
                    errors.append((item_id, 'source_spec_id', source_spec))
                else:
                    spec = specs_by_id[source_spec]
                    spec_id_val = spec.get('spec_id', spec.get('id', ''))
                    spec_path = self.root / "specs" / spec_id_val / "manifest.yaml"
                    if not spec_path.exists():
                        alt_path = self.root / "specs" / f"{spec_id_val}.yaml"
                        if not alt_path.exists():
                            errors.append((item_id, 'source_spec_path', str(spec_path)))

        # 2. Verify spec -> framework links
        for spec in specs:
            spec_id = spec.get('spec_id', spec.get('id', ''))
            complies_with = spec.get('framework_id', spec.get('complies_with', '')).strip()

            if complies_with:
                for fmwk_id in complies_with.split(','):
                    fmwk_id = fmwk_id.strip()
                    if fmwk_id:
                        if fmwk_id not in artifacts_by_id:
                            errors.append((spec_id, 'complies_with', fmwk_id))
                        else:
                            fmwk = artifacts_by_id[fmwk_id]
                            fmwk_path = self.root / fmwk.get('artifact_path', '').lstrip('/')
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
                    if dep_id.startswith('FMWK-'):
                        if dep_id not in artifacts_by_id:
                            errors.append((item_id, 'dependency', dep_id))

        return errors

    # -----------------------------------------------------------------
    # Hash Update
    # -----------------------------------------------------------------

    def update_registry_hashes(self) -> int:
        """Update content_hash column in control_plane_registry.csv."""
        rows, fieldnames = self.read_control_plane_registry()

        if "content_hash" not in fieldnames:
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

            full_path = self.root / artifact_path.lstrip("/")

            if not full_path.exists():
                row["content_hash"] = ""
                continue

            if full_path.is_dir():
                dir_hashes = []
                for file_path in sorted(full_path.rglob("*")):
                    if file_path.is_file() and not self._is_excluded(file_path):
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

        self.write_control_plane_registry(rows, fieldnames)
        return updated_count


# =============================================================================
# Backward-Compatible Module-Level Functions
# =============================================================================

# Module-level state for backward compatibility
_checker: Optional[IntegrityChecker] = None


def set_plane_context(plane: Optional[PlaneContext]) -> None:
    """Set the plane context for all module-level operations."""
    global _checker
    _checker = IntegrityChecker(plane)


def _get_checker() -> IntegrityChecker:
    """Get the current IntegrityChecker instance."""
    global _checker
    if _checker is None:
        _checker = IntegrityChecker()
    return _checker


def read_control_plane_registry() -> Tuple[List[Dict[str, str]], List[str]]:
    return _get_checker().read_control_plane_registry()

def write_control_plane_registry(rows: List[Dict[str, str]], fieldnames: List[str]) -> None:
    _get_checker().write_control_plane_registry(rows, fieldnames)

def get_registered_paths() -> Set[str]:
    return _get_checker().get_registered_paths()

def read_specs_registry() -> List[Dict[str, str]]:
    return _get_checker().read_specs_registry()

def verify_registry_hashes() -> IntegrityResult:
    return _get_checker().verify_registry_hashes()

def find_orphans() -> List[str]:
    return _get_checker().find_orphans()

def verify_chain_links() -> List[Tuple[str, str, str]]:
    return _get_checker().verify_chain_links()

def update_registry_hashes() -> int:
    return _get_checker().update_registry_hashes()


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
    checker = IntegrityChecker(plane)

    # Also set module-level state for backward compat
    set_plane_context(plane)

    # Default to --verify if no action specified
    if not any([args.verify, args.orphans, args.chain, args.update_hashes]):
        args.verify = True
        args.orphans = True
        args.chain = True

    try:
        # Update hashes if requested
        if args.update_hashes:
            updated = checker.update_registry_hashes()
            if not args.json:
                print(f"Updated {updated} content hashes in registry.")
            return 0

        # Run verification
        result = IntegrityResult()
        orphans = []

        if args.verify:
            result = checker.verify_registry_hashes()

        if args.orphans:
            orphans = checker.find_orphans()

        if args.chain:
            result.chain_errors = checker.verify_chain_links()

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
