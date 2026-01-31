#!/usr/bin/env python3
"""
ledger_repair.py - Ledger chain repair and verification tool.

Provides tools to diagnose and repair broken ledger chains (P5):
- --verify-only: Report chain status without making changes
- --truncate-to-last-valid: Keep valid prefix, drop broken tail
- --reset: Clear ledger entirely (requires CONFIRM_RESET=YES)

Per SPEC-025: Ledger Chain Integrity

Usage:
    python3 scripts/ledger_repair.py --verify-only
    python3 scripts/ledger_repair.py --truncate-to-last-valid
    CONFIRM_RESET=YES python3 scripts/ledger_repair.py --reset
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.ledger_client import (
    LedgerClient,
    LedgerEntry,
    DEFAULT_LEDGER_PATH,
    SEGMENT_INDEX_PATH,
    INDEX_DIR,
    _compute_entry_hash,
)


def find_last_valid_entry() -> Tuple[Optional[Path], int, str, List[str]]:
    """Walk the ledger chain and find the last valid entry.

    Returns:
        Tuple of (segment_path, line_number, last_valid_hash, issues)
        - segment_path: Path to segment containing last valid entry (None if empty)
        - line_number: 0-indexed line number of last valid entry (-1 if none)
        - last_valid_hash: entry_hash of last valid entry ("" if none)
        - issues: List of issues found during verification
    """
    client = LedgerClient()
    segments = client._list_segments()

    issues: List[str] = []
    last_valid_segment: Optional[Path] = None
    last_valid_line: int = -1
    prev_hash: str = ""

    for seg in segments:
        if not seg.exists():
            continue

        with open(seg, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f):
                line = line.strip()
                if not line:
                    continue

                try:
                    entry = LedgerEntry.from_json(line)
                except (json.JSONDecodeError, TypeError) as e:
                    issues.append(f"FAIL: Malformed JSON at {seg.name}:{line_num} - {e}")
                    break

                # Legacy entries (no hash) - warn but continue
                if not entry.entry_hash:
                    issues.append(f"WARN: Legacy entry {entry.id} at {seg.name}:{line_num}")
                    prev_hash = ""
                    last_valid_segment = seg
                    last_valid_line = line_num
                    continue

                # Verify entry_hash
                expected_hash = _compute_entry_hash(asdict(entry))
                if entry.entry_hash != expected_hash:
                    issues.append(
                        f"FAIL: Hash mismatch at {seg.name}:{line_num} "
                        f"(entry {entry.id})"
                    )
                    break

                # Verify chain link
                if entry.previous_hash != prev_hash:
                    issues.append(
                        f"FAIL: Chain broken at {seg.name}:{line_num} "
                        f"(entry {entry.id}, expected prev={prev_hash[:8]}..., "
                        f"got {entry.previous_hash[:8] if entry.previous_hash else 'empty'}...)"
                    )
                    break

                # Entry is valid
                prev_hash = entry.entry_hash
                last_valid_segment = seg
                last_valid_line = line_num

    return (last_valid_segment, last_valid_line, prev_hash, issues)


def truncate_to_valid() -> Tuple[int, int]:
    """Truncate ledger to last valid entry.

    Returns:
        Tuple of (kept_count, removed_count)
    """
    segment, line_num, last_hash, issues = find_last_valid_entry()

    if segment is None or line_num < 0:
        print("No valid entries found. Use --reset to clear ledger.")
        return (0, 0)

    client = LedgerClient()
    segments = client._list_segments()

    kept = 0
    removed = 0
    found_segment = False

    for seg in segments:
        if seg == segment:
            found_segment = True
            # Truncate this segment to line_num (inclusive)
            with open(seg, "r", encoding="utf-8") as f:
                lines = f.readlines()

            kept_lines = lines[: line_num + 1]
            removed_in_segment = len(lines) - len(kept_lines)

            with open(seg, "w", encoding="utf-8") as f:
                f.writelines(kept_lines)

            kept += len(kept_lines)
            removed += removed_in_segment

        elif found_segment:
            # Remove all segments after the truncation point
            with open(seg, "r", encoding="utf-8") as f:
                removed += sum(1 for line in f if line.strip())
            seg.unlink()

        else:
            # Segments before truncation point - keep fully
            with open(seg, "r", encoding="utf-8") as f:
                kept += sum(1 for line in f if line.strip())

    return (kept, removed)


def reset_ledger() -> None:
    """Reset ledger to empty state with backup.

    Requires CONFIRM_RESET=YES environment variable.
    """
    if os.environ.get("CONFIRM_RESET") != "YES":
        print("ERROR: Set CONFIRM_RESET=YES to confirm ledger reset")
        sys.exit(1)

    client = LedgerClient()
    segments = client._list_segments()

    # Create backup
    backup_ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup_dir = DEFAULT_LEDGER_PATH.parent / f"backup-{backup_ts}"
    backup_dir.mkdir(parents=True, exist_ok=True)

    print(f"Creating backup in: {backup_dir}")

    for seg in segments:
        if seg.exists():
            shutil.copy2(seg, backup_dir / seg.name)
            seg.unlink()

    # Backup and clear index files
    if SEGMENT_INDEX_PATH.exists():
        shutil.copy2(SEGMENT_INDEX_PATH, backup_dir / SEGMENT_INDEX_PATH.name)
        SEGMENT_INDEX_PATH.write_text("")

    if INDEX_DIR.exists():
        for idx_file in INDEX_DIR.glob("*.json"):
            shutil.copy2(idx_file, backup_dir / idx_file.name)
            idx_file.unlink()

    # Recreate empty base ledger
    DEFAULT_LEDGER_PATH.touch()

    print(f"Ledger reset. Backup at: {backup_dir}")


def verify_only() -> bool:
    """Verify ledger chain and report status.

    Returns:
        True if chain is valid, False otherwise
    """
    client = LedgerClient()
    valid, issues = client.verify_chain()

    if not issues:
        print("Ledger chain: VALID")
        print(f"Total entries: {client.count()}")
        return True

    print("Ledger chain issues:")
    for issue in issues:
        print(f"  {issue}")

    fail_count = sum(1 for i in issues if i.startswith("FAIL"))
    warn_count = sum(1 for i in issues if i.startswith("WARN"))

    print()
    print(f"FAIL: {fail_count}, WARN: {warn_count}")

    if valid:
        print("Chain: VALID (warnings only)")
    else:
        print("Chain: INVALID")

        # Find last valid for recovery info
        seg, line, _, _ = find_last_valid_entry()
        if seg:
            print(f"Last valid entry: {seg.name}:{line}")
            print("Run with --truncate-to-last-valid to repair")

    return valid


def main():
    parser = argparse.ArgumentParser(
        description="Ledger chain repair and verification tool"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--verify-only",
        action="store_true",
        help="Report chain status without making changes",
    )
    group.add_argument(
        "--truncate-to-last-valid",
        action="store_true",
        help="Keep valid prefix, drop broken tail",
    )
    group.add_argument(
        "--reset",
        action="store_true",
        help="Clear ledger entirely (requires CONFIRM_RESET=YES)",
    )

    args = parser.parse_args()

    if args.verify_only:
        valid = verify_only()
        sys.exit(0 if valid else 1)

    elif args.truncate_to_last_valid:
        print("Truncating ledger to last valid entry...")
        kept, removed = truncate_to_valid()
        print(f"Kept: {kept} entries, Removed: {removed} entries")

        # Verify after truncation
        print()
        print("Verifying repaired chain...")
        valid = verify_only()
        sys.exit(0 if valid else 1)

    elif args.reset:
        reset_ledger()
        sys.exit(0)


if __name__ == "__main__":
    main()
