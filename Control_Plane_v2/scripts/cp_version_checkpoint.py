#!/usr/bin/env python3
"""
cp_version_checkpoint.py - Create a lightweight version checkpoint.

Captures:
- control_plane_registry.csv snapshot
- MANIFEST.json hash
- Registry hash
- Merkle root (after integrity passes)
- Package list (id, source, digest, version, status/selected)
- Ledger entry recording the checkpoint

Output files:
- versions/<VERSION_ID>.json        (metadata)
- versions/<VERSION_ID>_registry.csv (registry snapshot)

Write boundary: output is DERIVED (versions/).
Auth: requires role permitting "checkpoint" (uses CONTROL_PLANE_TOKEN or --token).

Usage:
    python3 scripts/cp_version_checkpoint.py --label "Production release"
    python3 scripts/cp_version_checkpoint.py --root /path/to/plane --label "Release"
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.paths import CONTROL_PLANE
from lib.plane import get_current_plane, PlaneContext
from lib.integrity import IntegrityChecker
from lib.ledger_client import LedgerClient, LedgerEntry
from lib.auth import get_provider
from lib import authz
from lib.pristine import assert_write_allowed


def get_plane_paths(plane: PlaneContext):
    """Get plane-specific paths."""
    return {
        "root": plane.root,
        "versions_dir": plane.root / "versions",
        "registry_path": plane.root / "registries" / "control_plane_registry.csv",
        "packages_reg_path": plane.root / "registries" / "packages_registry.csv",
        "manifest_path": plane.root / "MANIFEST.json",
    }


# Legacy defaults
VERSIONS_DIR = CONTROL_PLANE / "versions"
REGISTRY_PATH = CONTROL_PLANE / "registries" / "control_plane_registry.csv"
PACKAGES_REG_PATH = CONTROL_PLANE / "registries" / "packages_registry.csv"
MANIFEST_PATH = CONTROL_PLANE / "MANIFEST.json"


from lib.hashing import sha256_file  # canonical implementation


def load_packages(packages_reg_path: Path) -> list[dict]:
    if not packages_reg_path.exists():
        return []
    rows = list(csv.DictReader(packages_reg_path.open()))
    return [
        {
            "id": r.get("id", ""),
            "source": r.get("source", ""),
            "source_type": r.get("source_type", ""),
            "digest": r.get("digest", ""),
            "version": r.get("version", ""),
            "status": r.get("status", ""),
            "selected": r.get("selected", ""),
        }
        for r in rows
    ]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", help="Human-readable label for this checkpoint")
    ap.add_argument("--token", help="Auth token (else CONTROL_PLANE_TOKEN env)")
    ap.add_argument("--root", type=Path, help="Plane root path (for multi-plane operation)")
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Verify integrity and auth without creating checkpoint"
    )
    args = ap.parse_args()

    # Resolve plane context
    plane_root = args.root.resolve() if args.root else None
    plane = get_current_plane(plane_root)
    paths = get_plane_paths(plane)
    root = paths["root"]
    versions_dir = paths["versions_dir"]
    registry_path = paths["registry_path"]
    packages_reg_path = paths["packages_reg_path"]
    manifest_path = paths["manifest_path"]

    identity = get_provider().authenticate(args.token or None)
    authz.require(identity, "checkpoint")

    checker = IntegrityChecker(root)
    integrity_result = checker.validate()
    if not integrity_result.passed:
        print("ERROR: integrity check failed; aborting checkpoint.")
        for issue in integrity_result.issues:
            print(f"- {issue.severity}: {issue.check} {issue.message}")
        return 1

    # Handle dry-run mode
    if args.dry_run:
        print("DRY-RUN: Integrity verified, auth valid. No checkpoint created.")
        print(f"  Verified artifacts: {len(integrity_result.artifacts) if hasattr(integrity_result, 'artifacts') else 'N/A'}")
        print(f"  Merkle root: {integrity_result.computed_merkle_root[:16]}...")
        print(f"  Actor: {identity.user if identity else 'unknown'}")
        return 0

    version_id = f"VER-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    versions_dir.mkdir(parents=True, exist_ok=True)

    # Snapshot registry - enforce DERIVED write boundary
    registry_snapshot_path = versions_dir / f"{version_id}_registry.csv"
    assert_write_allowed(registry_snapshot_path, plane=plane)

    registry_content = registry_path.read_bytes()
    registry_snapshot_path.write_bytes(registry_content)

    registry_hash = sha256_file(registry_snapshot_path)
    manifest_hash = sha256_file(manifest_path) if manifest_path.exists() else ""

    packages = load_packages(packages_reg_path)

    metadata = {
        "version_id": version_id,
        "label": args.label or "",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "merkle_root": integrity_result.computed_merkle_root,
        "registry_hash": registry_hash,
        "manifest_hash": manifest_hash,
        "packages": packages,
        "registry_snapshot": str(registry_snapshot_path.relative_to(root)),
        "ledger_entry_id": None,
        "actor": identity.user if identity else "",
        "plane": plane.name,
    }

    # Ledger entry - use plane-scoped ledger
    ledger_path = plane.ledger_dir / "governance.jsonl"
    ledger = LedgerClient(ledger_path=ledger_path)
    entry = LedgerEntry(
        event_type="version_checkpoint",
        submission_id=version_id,
        decision="RECORDED",
        reason=f"Checkpoint {version_id} {args.label or ''}".strip(),
        metadata={
            "registry_hash": registry_hash,
            "manifest_hash": manifest_hash,
            "merkle_root": integrity_result.computed_merkle_root,
            "packages": [p["id"] for p in packages],
            "plane": plane.name,
        },
    )
    metadata["ledger_entry_id"] = ledger.write(entry)

    meta_path = versions_dir / f"{version_id}.json"
    assert_write_allowed(meta_path, plane=plane)
    meta_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    print(f"Checkpoint created: {version_id}")
    print(f" - registry snapshot: {registry_snapshot_path}")
    print(f" - metadata: {meta_path}")
    print(f" - ledger entry: {metadata['ledger_entry_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
