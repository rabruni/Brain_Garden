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
from lib.integrity import IntegrityChecker
from lib.ledger_client import LedgerClient, LedgerEntry
from lib.auth import get_provider
from lib import authz
from lib.pristine import assert_write_allowed


VERSIONS_DIR = CONTROL_PLANE / "versions"
REGISTRY_PATH = CONTROL_PLANE / "registries" / "control_plane_registry.csv"
PACKAGES_REG_PATH = CONTROL_PLANE / "registries" / "packages_registry.csv"
MANIFEST_PATH = CONTROL_PLANE / "MANIFEST.json"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def load_packages() -> list[dict]:
    if not PACKAGES_REG_PATH.exists():
        return []
    rows = list(csv.DictReader(PACKAGES_REG_PATH.open()))
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
    args = ap.parse_args()

    identity = get_provider().authenticate(args.token or None)
    authz.require(identity, "checkpoint")

    checker = IntegrityChecker(CONTROL_PLANE)
    integrity_result = checker.validate()
    if not integrity_result.passed:
        print("ERROR: integrity check failed; aborting checkpoint.")
        for issue in integrity_result.issues:
            print(f"- {issue.severity}: {issue.check} {issue.message}")
        return 1

    version_id = f"VER-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    VERSIONS_DIR.mkdir(parents=True, exist_ok=True)

    # Snapshot registry - enforce DERIVED write boundary
    registry_snapshot_path = VERSIONS_DIR / f"{version_id}_registry.csv"
    assert_write_allowed(registry_snapshot_path)

    registry_content = REGISTRY_PATH.read_bytes()
    registry_snapshot_path.write_bytes(registry_content)

    registry_hash = sha256_file(registry_snapshot_path)
    manifest_hash = sha256_file(MANIFEST_PATH) if MANIFEST_PATH.exists() else ""

    packages = load_packages()

    metadata = {
        "version_id": version_id,
        "label": args.label or "",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "merkle_root": integrity_result.computed_merkle_root,
        "registry_hash": registry_hash,
        "manifest_hash": manifest_hash,
        "packages": packages,
        "registry_snapshot": str(registry_snapshot_path.relative_to(CONTROL_PLANE)),
        "ledger_entry_id": None,
        "actor": identity.user if identity else "",
    }

    # Ledger entry
    ledger = LedgerClient()
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
        },
    )
    metadata["ledger_entry_id"] = ledger.write(entry)

    meta_path = VERSIONS_DIR / f"{version_id}.json"
    assert_write_allowed(meta_path)
    meta_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    print(f"Checkpoint created: {version_id}")
    print(f" - registry snapshot: {registry_snapshot_path}")
    print(f" - metadata: {meta_path}")
    print(f" - ledger entry: {metadata['ledger_entry_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
