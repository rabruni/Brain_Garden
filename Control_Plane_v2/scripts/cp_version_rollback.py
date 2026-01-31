#!/usr/bin/env python3
"""
cp_version_rollback.py - Restore Control Plane from a checkpoint.

Steps:
1. Load versions/<VERSION_ID>.json metadata + registry snapshot.
2. Verify package archives exist and digests match.
3. Restore registry from snapshot.
4. Reinstall packages (overwrite as needed).
5. Regenerate MANIFEST.json.
6. Run integrity_check; fail if not healthy.
7. Record ledger entry for rollback.

Auth: requires role permitting "rollback" (CONTROL_PLANE_TOKEN or --token).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.paths import CONTROL_PLANE
from lib.packages import unpack, verify, sha256_file
from lib.integrity import IntegrityChecker
from lib.ledger_client import LedgerClient, LedgerEntry
from lib.auth import get_provider
from lib import authz
from lib.pristine import InstallModeContext


def sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def regenerate_manifest(root: Path) -> None:
    checksums = {}
    for rel in sorted(root.rglob("*")):
        if rel.is_file():
            checksums[str(rel.relative_to(root)).replace("\\", "/")] = {
                "sha256": sha_file(rel),
                "size": rel.stat().st_size,
            }
    manifest = {
        "version": "2.0.0-v2",
        "generated": datetime.now(timezone.utc).isoformat(),
        "generator": "cp_version_rollback",
        "checksums": checksums,
    }
    (root / "MANIFEST.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version-id", required=True, help="Checkpoint version ID (VER-...)")
    ap.add_argument("--token", help="Auth token (else CONTROL_PLANE_TOKEN env)")
    ap.add_argument("--force", action="store_true", help="Overwrite existing files during install")
    args = ap.parse_args()

    identity = get_provider().authenticate(args.token or None)
    authz.require(identity, "rollback")

    versions_dir = CONTROL_PLANE / "versions"
    meta_path = versions_dir / f"{args.version_id}.json"
    if not meta_path.exists():
        raise SystemExit(f"Version metadata not found: {meta_path}")

    metadata = json.loads(meta_path.read_text())
    registry_snapshot_rel = metadata.get("registry_snapshot")
    if not registry_snapshot_rel:
        raise SystemExit("Metadata missing registry_snapshot")
    registry_snapshot = CONTROL_PLANE / registry_snapshot_rel
    if not registry_snapshot.exists():
        raise SystemExit(f"Registry snapshot missing: {registry_snapshot}")

    # Verify packages
    packages = metadata.get("packages", [])
    for pkg in packages:
        source = pkg.get("source") or ""
        digest = (pkg.get("digest") or "").strip()
        if not source:
            raise SystemExit(f"Package {pkg.get('id')} missing source path")
        archive = Path(source)
        if not archive.is_absolute():
            archive = CONTROL_PLANE / source.lstrip("/")
        if not archive.exists():
            raise SystemExit(f"Archive missing: {archive}")
        if digest:
            ok, actual = verify(archive, digest)
            if not ok:
                raise SystemExit(f"Digest mismatch for {archive}: {actual} != {digest}")

    # Enter install mode for all pristine writes
    with InstallModeContext():
        # Restore registry
        target_registry = CONTROL_PLANE / "registries" / "control_plane_registry.csv"
        target_registry.write_bytes(registry_snapshot.read_bytes())

        # Reinstall packages
        for pkg in packages:
            archive = Path(pkg["source"])
            if not archive.is_absolute():
                archive = CONTROL_PLANE / archive.as_posix().lstrip("/")
            unpack(archive, CONTROL_PLANE)

        # Regenerate manifest
        regenerate_manifest(CONTROL_PLANE)

    # Integrity check
    checker = IntegrityChecker(CONTROL_PLANE)
    integrity = checker.validate()
    if not integrity.passed:
        print("ERROR: integrity check failed after rollback.")
        for issue in integrity.issues:
            print(f"- {issue.severity}: {issue.check} {issue.message}")
        success = False
    else:
        success = True

    # Ledger entry
    ledger = LedgerClient()
    decision = "ROLLED_BACK" if success else "ROLLBACK_FAILED"
    entry = LedgerEntry(
        event_type="version_rollback",
        submission_id=args.version_id,
        decision=decision,
        reason=f"Rollback to {args.version_id}",
        metadata={
            "target_registry": str(target_registry.relative_to(CONTROL_PLANE)),
            "packages": [p.get("id") for p in packages],
            "integrity_passed": success,
        },
    )
    ledger_id = ledger.write(entry)
    print(f"Ledger entry: {ledger_id}")

    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
