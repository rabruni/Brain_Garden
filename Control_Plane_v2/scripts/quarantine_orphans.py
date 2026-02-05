#!/usr/bin/env python3
"""
quarantine_orphans.py - Quarantine unregistered files for governance review.

Detects files in governed directories that are not registered in any registry,
moves them to a quarantine area, and logs the event to the ledger.

Per SPEC-025: All artifacts must be registered and tracked.

Usage:
    python3 scripts/quarantine_orphans.py --dry-run     # Preview only
    python3 scripts/quarantine_orphans.py               # Quarantine orphans
    python3 scripts/quarantine_orphans.py --restore QRN-abc123  # Restore from quarantine
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import sys
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Set, Dict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.paths import CONTROL_PLANE
from lib.ledger_client import LedgerClient, LedgerEntry
from lib.merkle import hash_file

# Directories to scan for orphans
GOVERNED_DIRS = [
    "frameworks",
    "scripts",
    "lib",
    "prompts",
    "modules",
    "specs",
    "schemas",
    "policies",
]

# File extensions to check
GOVERNED_EXTENSIONS = {".py", ".md", ".csv", ".json", ".yaml", ".yml", ".txt", ".sh"}

# Directories to exclude
EXCLUDED_DIRS = {"__pycache__", ".git", ".pytest_cache", "node_modules", "__init__.py"}

# Quarantine location
QUARANTINE_DIR = CONTROL_PLANE / "_quarantine"
QUARANTINE_MANIFEST = QUARANTINE_DIR / "manifest.jsonl"

# Registry paths
CONTROL_PLANE_REGISTRY = CONTROL_PLANE / "registries" / "control_plane_registry.csv"


@dataclass
class QuarantineEntry:
    """Record of a quarantined file."""
    id: str
    original_path: str
    quarantine_path: str
    content_hash: str
    file_size: int
    detected_at: str
    reason: str
    status: str  # "quarantined", "restored", "deleted"
    restored_at: Optional[str] = None
    restored_to: Optional[str] = None


def load_registered_paths() -> Set[str]:
    """Load all registered artifact paths from registries."""
    registered = set()

    if CONTROL_PLANE_REGISTRY.exists():
        with open(CONTROL_PLANE_REGISTRY, "r", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                path = row.get("artifact_path", "")
                if path:
                    # Normalize path
                    if path.startswith("/"):
                        path = path[1:]
                    registered.add(path)

    return registered


def find_orphaned_files() -> List[Path]:
    """Find files in governed directories that aren't registered."""
    registered = load_registered_paths()
    orphans = []

    for dir_name in GOVERNED_DIRS:
        dir_path = CONTROL_PLANE / dir_name
        if not dir_path.exists():
            continue

        for file_path in dir_path.rglob("*"):
            # Skip directories
            if file_path.is_dir():
                continue

            # Skip excluded
            if any(excl in file_path.parts for excl in EXCLUDED_DIRS):
                continue

            # Check extension
            if file_path.suffix not in GOVERNED_EXTENSIONS:
                continue

            # Check if registered
            rel_path = str(file_path.relative_to(CONTROL_PLANE))
            if rel_path not in registered and f"/{rel_path}" not in registered:
                orphans.append(file_path)

    return orphans


def quarantine_file(file_path: Path, reason: str = "Unregistered file detected") -> QuarantineEntry:
    """Move a file to quarantine and create tracking entry."""
    # Ensure quarantine directory exists
    QUARANTINE_DIR.mkdir(parents=True, exist_ok=True)

    # Generate quarantine ID
    qrn_id = f"QRN-{uuid.uuid4().hex[:8]}"

    # Compute hash before moving
    content_hash = hash_file(file_path)
    file_size = file_path.stat().st_size

    # Create quarantine subdirectory with timestamp
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    quarantine_subdir = QUARANTINE_DIR / f"{timestamp}_{qrn_id}"
    quarantine_subdir.mkdir(parents=True, exist_ok=True)

    # Preserve original directory structure
    rel_path = file_path.relative_to(CONTROL_PLANE)
    quarantine_path = quarantine_subdir / rel_path
    quarantine_path.parent.mkdir(parents=True, exist_ok=True)

    # Move file to quarantine
    shutil.move(str(file_path), str(quarantine_path))

    # Create entry
    entry = QuarantineEntry(
        id=qrn_id,
        original_path=str(rel_path),
        quarantine_path=str(quarantine_path.relative_to(CONTROL_PLANE)),
        content_hash=content_hash,
        file_size=file_size,
        detected_at=datetime.now(timezone.utc).isoformat(),
        reason=reason,
        status="quarantined",
    )

    # Append to manifest
    with open(QUARANTINE_MANIFEST, "a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(entry)) + "\n")

    return entry


def log_quarantine_event(entries: List[QuarantineEntry]) -> str:
    """Log quarantine event to ledger."""
    ledger = LedgerClient()

    ledger_entry = LedgerEntry(
        event_type="orphan_quarantine",
        submission_id=f"QUARANTINE-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        decision="QUARANTINED",
        reason=f"Quarantined {len(entries)} unregistered file(s) for governance review",
        metadata={
            "files": [
                {
                    "id": e.id,
                    "original_path": e.original_path,
                    "content_hash": e.content_hash,
                    "file_size": e.file_size,
                }
                for e in entries
            ],
            "total_files": len(entries),
            "total_bytes": sum(e.file_size for e in entries),
        },
    )

    return ledger.write(ledger_entry)


def restore_from_quarantine(qrn_id: str, target_path: Optional[str] = None) -> bool:
    """Restore a file from quarantine."""
    if not QUARANTINE_MANIFEST.exists():
        print(f"Error: No quarantine manifest found", file=sys.stderr)
        return False

    # Find entry
    entries = []
    target_entry = None
    with open(QUARANTINE_MANIFEST, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            entry = json.loads(line)
            entries.append(entry)
            if entry.get("id") == qrn_id:
                target_entry = entry

    if not target_entry:
        print(f"Error: Quarantine entry {qrn_id} not found", file=sys.stderr)
        return False

    if target_entry["status"] != "quarantined":
        print(f"Error: Entry {qrn_id} is not quarantined (status: {target_entry['status']})", file=sys.stderr)
        return False

    quarantine_path = CONTROL_PLANE / target_entry["quarantine_path"]
    if not quarantine_path.exists():
        print(f"Error: Quarantined file not found: {quarantine_path}", file=sys.stderr)
        return False

    # Determine restore path
    restore_path = Path(target_path) if target_path else CONTROL_PLANE / target_entry["original_path"]
    restore_path.parent.mkdir(parents=True, exist_ok=True)

    # Restore file
    shutil.copy2(str(quarantine_path), str(restore_path))

    # Update entry
    target_entry["status"] = "restored"
    target_entry["restored_at"] = datetime.now(timezone.utc).isoformat()
    target_entry["restored_to"] = str(restore_path.relative_to(CONTROL_PLANE))

    # Rewrite manifest
    with open(QUARANTINE_MANIFEST, "w", encoding="utf-8") as f:
        for entry in entries:
            if entry["id"] == qrn_id:
                f.write(json.dumps(target_entry) + "\n")
            else:
                f.write(json.dumps(entry) + "\n")

    # Log restore event
    ledger = LedgerClient()
    ledger.write(LedgerEntry(
        event_type="orphan_restored",
        submission_id=qrn_id,
        decision="RESTORED",
        reason=f"Restored quarantined file to {restore_path.relative_to(CONTROL_PLANE)}",
        metadata={
            "original_path": target_entry["original_path"],
            "restored_to": target_entry["restored_to"],
            "content_hash": target_entry["content_hash"],
        },
    ))

    print(f"Restored {qrn_id} to {restore_path}")
    return True


def list_quarantine() -> List[Dict]:
    """List all quarantine entries."""
    if not QUARANTINE_MANIFEST.exists():
        return []

    entries = []
    with open(QUARANTINE_MANIFEST, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                entries.append(json.loads(line))
    return entries


def main():
    parser = argparse.ArgumentParser(
        description="Quarantine unregistered files for governance review"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview orphans without quarantining",
    )
    parser.add_argument(
        "--restore",
        metavar="QRN_ID",
        help="Restore a file from quarantine by ID",
    )
    parser.add_argument(
        "--restore-to",
        metavar="PATH",
        help="Custom path to restore to (with --restore)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List quarantine entries",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )

    args = parser.parse_args()

    # List mode
    if args.list:
        entries = list_quarantine()
        if args.json:
            print(json.dumps(entries, indent=2))
        else:
            if not entries:
                print("No quarantine entries.")
            else:
                print(f"Quarantine entries ({len(entries)}):\n")
                for e in entries:
                    status_icon = {"quarantined": "Q", "restored": "R", "deleted": "X"}.get(e["status"], "?")
                    print(f"[{status_icon}] {e['id']}: {e['original_path']}")
                    print(f"    Hash: {e['content_hash'][:16]}...")
                    print(f"    Detected: {e['detected_at']}")
                    print(f"    Status: {e['status']}")
                    if e.get("restored_to"):
                        print(f"    Restored to: {e['restored_to']}")
                    print()
        return 0

    # Restore mode
    if args.restore:
        success = restore_from_quarantine(args.restore, args.restore_to)
        return 0 if success else 1

    # Find orphans
    orphans = find_orphaned_files()

    if not orphans:
        print("No orphaned files found.")
        return 0

    # Dry run
    if args.dry_run:
        print(f"Found {len(orphans)} orphaned file(s):\n")
        for orphan in orphans:
            rel = orphan.relative_to(CONTROL_PLANE)
            size = orphan.stat().st_size
            print(f"  - {rel} ({size} bytes)")
        print(f"\nRun without --dry-run to quarantine these files.")
        return 0

    # Quarantine
    print(f"Quarantining {len(orphans)} orphaned file(s)...\n")

    entries = []
    for orphan in orphans:
        entry = quarantine_file(orphan)
        entries.append(entry)
        print(f"  [{entry.id}] {entry.original_path}")

    # Log to ledger
    ledger_id = log_quarantine_event(entries)

    print(f"\nQuarantined {len(entries)} file(s).")
    print(f"Ledger entry: {ledger_id}")
    print(f"Manifest: {QUARANTINE_MANIFEST}")
    print(f"\nTo restore: python3 scripts/quarantine_orphans.py --restore <QRN_ID>")

    if args.json:
        print(json.dumps([asdict(e) for e in entries], indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
