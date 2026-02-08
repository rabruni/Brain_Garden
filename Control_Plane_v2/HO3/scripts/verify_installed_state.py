#!/usr/bin/env python3
"""
verify_installed_state.py - Compare installed state directories.

Used for pristine rebuild verification to ensure the rebuilt system
matches the pre-drill state.

Per FMWK-PKG-001: Package Standard v1.0 (Phase 3a: Installed State Contract)

Usage:
    python3 scripts/verify_installed_state.py --before /path/to/before --after /path/to/after
    python3 scripts/verify_installed_state.py --current  # Compare current installed/ with checkpoint
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# Add repo root for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "HOT"))

from kernel.paths import CONTROL_PLANE

INSTALLED_DIR = CONTROL_PLANE / "installed"


@dataclass
class StateDifference:
    """A difference between two installed states."""
    category: str  # "missing", "extra", "version", "digest", "files"
    package_id: str
    message: str
    before_value: Optional[str] = None
    after_value: Optional[str] = None


@dataclass
class StateComparisonResult:
    """Result of comparing two installed states."""
    match: bool
    before_count: int
    after_count: int
    differences: List[StateDifference] = field(default_factory=list)

    def add_diff(
        self,
        category: str,
        package_id: str,
        message: str,
        before: str = None,
        after: str = None
    ):
        self.differences.append(StateDifference(
            category=category,
            package_id=package_id,
            message=message,
            before_value=before,
            after_value=after
        ))
        self.match = False


from kernel.hashing import sha256_file  # canonical implementation


def load_receipt(receipt_path: Path) -> Optional[Dict[str, Any]]:
    """Load install receipt from JSON file."""
    try:
        with open(receipt_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def load_installed_state(installed_dir: Path) -> Dict[str, Dict[str, Any]]:
    """Load all install receipts from a directory.

    Args:
        installed_dir: Path to installed/ directory

    Returns:
        Dict mapping package ID to receipt data
    """
    receipts = {}

    if not installed_dir.exists():
        return receipts

    for pkg_dir in installed_dir.iterdir():
        if not pkg_dir.is_dir():
            continue

        receipt_path = pkg_dir / "receipt.json"
        if receipt_path.exists():
            receipt = load_receipt(receipt_path)
            if receipt:
                pkg_id = receipt.get("id", pkg_dir.name)
                receipts[pkg_id] = receipt

    return receipts


def compare_receipts(
    before: Dict[str, Any],
    after: Dict[str, Any],
    pkg_id: str
) -> List[StateDifference]:
    """Compare two receipts for the same package.

    Args:
        before: Receipt from before state
        after: Receipt from after state
        pkg_id: Package ID

    Returns:
        List of differences
    """
    diffs = []

    # Version must match
    before_version = before.get("version", "")
    after_version = after.get("version", "")
    if before_version != after_version:
        diffs.append(StateDifference(
            category="version",
            package_id=pkg_id,
            message=f"Version mismatch",
            before_value=before_version,
            after_value=after_version
        ))

    # Archive digest must match
    before_digest = before.get("archive_digest", "")
    after_digest = after.get("archive_digest", "")
    if before_digest != after_digest:
        diffs.append(StateDifference(
            category="digest",
            package_id=pkg_id,
            message=f"Archive digest mismatch",
            before_value=before_digest[:16] + "..." if before_digest else "",
            after_value=after_digest[:16] + "..." if after_digest else ""
        ))

    # File hashes must match
    before_files = {f["path"]: f.get("sha256", "") for f in before.get("files", [])}
    after_files = {f["path"]: f.get("sha256", "") for f in after.get("files", [])}

    # Check for missing files
    for path in before_files:
        if path not in after_files:
            diffs.append(StateDifference(
                category="files",
                package_id=pkg_id,
                message=f"Missing file: {path}",
                before_value=before_files[path][:16] + "..." if before_files[path] else ""
            ))

    # Check for extra files
    for path in after_files:
        if path not in before_files:
            diffs.append(StateDifference(
                category="files",
                package_id=pkg_id,
                message=f"Extra file: {path}",
                after_value=after_files[path][:16] + "..." if after_files[path] else ""
            ))

    # Check file hash mismatches
    for path in before_files:
        if path in after_files:
            if before_files[path] != after_files[path]:
                diffs.append(StateDifference(
                    category="files",
                    package_id=pkg_id,
                    message=f"File hash mismatch: {path}",
                    before_value=before_files[path][:16] + "..." if before_files[path] else "",
                    after_value=after_files[path][:16] + "..." if after_files[path] else ""
                ))

    return diffs


def compare_installed_state(
    before_dir: Path,
    after_dir: Path
) -> StateComparisonResult:
    """Compare two installed state directories.

    Args:
        before_dir: Path to before installed/ directory
        after_dir: Path to after installed/ directory

    Returns:
        StateComparisonResult with match status and differences
    """
    before_receipts = load_installed_state(before_dir)
    after_receipts = load_installed_state(after_dir)

    result = StateComparisonResult(
        match=True,
        before_count=len(before_receipts),
        after_count=len(after_receipts)
    )

    before_ids = set(before_receipts.keys())
    after_ids = set(after_receipts.keys())

    # Check for missing packages
    for pkg_id in before_ids - after_ids:
        result.add_diff(
            category="missing",
            package_id=pkg_id,
            message=f"Package missing from after state"
        )

    # Check for extra packages
    for pkg_id in after_ids - before_ids:
        result.add_diff(
            category="extra",
            package_id=pkg_id,
            message=f"Extra package in after state"
        )

    # Compare matching packages
    for pkg_id in before_ids & after_ids:
        diffs = compare_receipts(
            before_receipts[pkg_id],
            after_receipts[pkg_id],
            pkg_id
        )
        for diff in diffs:
            result.differences.append(diff)
            result.match = False

    return result


def verify_current_state(checkpoint_path: Optional[Path] = None) -> StateComparisonResult:
    """Verify current installed state against latest checkpoint.

    Args:
        checkpoint_path: Optional explicit checkpoint path

    Returns:
        StateComparisonResult
    """
    if checkpoint_path is None:
        # Find latest checkpoint
        versions_dir = CONTROL_PLANE / "versions"
        if not versions_dir.exists():
            return StateComparisonResult(
                match=False,
                before_count=0,
                after_count=0,
                differences=[StateDifference(
                    category="error",
                    package_id="",
                    message="No checkpoints found in versions/"
                )]
            )

        checkpoints = sorted(versions_dir.iterdir(), reverse=True)
        if not checkpoints:
            return StateComparisonResult(
                match=False,
                before_count=0,
                after_count=0,
                differences=[StateDifference(
                    category="error",
                    package_id="",
                    message="No checkpoints found"
                )]
            )

        checkpoint_path = checkpoints[0] / "installed"

    if not checkpoint_path.exists():
        return StateComparisonResult(
            match=False,
            before_count=0,
            after_count=0,
            differences=[StateDifference(
                category="error",
                package_id="",
                message=f"Checkpoint not found: {checkpoint_path}"
            )]
        )

    return compare_installed_state(checkpoint_path, INSTALLED_DIR)


def print_result(result: StateComparisonResult, verbose: bool = False):
    """Print comparison result."""
    print()
    print("=" * 60)
    print("INSTALLED STATE COMPARISON")
    print("=" * 60)
    print()

    print(f"Before: {result.before_count} packages")
    print(f"After:  {result.after_count} packages")
    print()

    if result.match:
        print("MATCH: States are identical")
        return

    # Group differences by category
    by_category: Dict[str, List[StateDifference]] = {}
    for diff in result.differences:
        by_category.setdefault(diff.category, []).append(diff)

    print(f"MISMATCH: {len(result.differences)} difference(s) found")
    print()

    for category in ["missing", "extra", "version", "digest", "files", "error"]:
        diffs = by_category.get(category, [])
        if not diffs:
            continue

        print(f"{category.upper()}: {len(diffs)} issue(s)")
        for diff in diffs:
            if diff.package_id:
                print(f"  [{diff.package_id}] {diff.message}")
            else:
                print(f"  {diff.message}")

            if verbose and (diff.before_value or diff.after_value):
                if diff.before_value:
                    print(f"    before: {diff.before_value}")
                if diff.after_value:
                    print(f"    after:  {diff.after_value}")
        print()


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Compare installed state directories (FMWK-PKG-001)"
    )
    parser.add_argument(
        "--before",
        help="Path to before installed/ directory"
    )
    parser.add_argument(
        "--after",
        help="Path to after installed/ directory"
    )
    parser.add_argument(
        "--current",
        action="store_true",
        help="Compare current installed/ with latest checkpoint"
    )
    parser.add_argument(
        "--checkpoint",
        help="Explicit checkpoint path to compare against"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed values"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON"
    )

    args = parser.parse_args()

    if args.current:
        checkpoint = Path(args.checkpoint) if args.checkpoint else None
        print(f"Comparing current installed/ with checkpoint...")
        result = verify_current_state(checkpoint)
    elif args.before and args.after:
        before_dir = Path(args.before)
        after_dir = Path(args.after)

        if not before_dir.exists():
            print(f"ERROR: Before directory not found: {before_dir}")
            return 1
        if not after_dir.exists():
            print(f"ERROR: After directory not found: {after_dir}")
            return 1

        print(f"Before: {before_dir}")
        print(f"After:  {after_dir}")
        result = compare_installed_state(before_dir, after_dir)
    else:
        parser.print_help()
        return 1

    if args.json:
        output = {
            "match": result.match,
            "before_count": result.before_count,
            "after_count": result.after_count,
            "differences": [
                {
                    "category": d.category,
                    "package_id": d.package_id,
                    "message": d.message,
                    "before": d.before_value,
                    "after": d.after_value,
                }
                for d in result.differences
            ]
        }
        print(json.dumps(output, indent=2))
    else:
        print_result(result, args.verbose)

    if result.match:
        print()
        print("STATE COMPARISON: OK")
        return 0
    else:
        print()
        print("STATE COMPARISON: MISMATCH")
        return 1


if __name__ == "__main__":
    sys.exit(main())
