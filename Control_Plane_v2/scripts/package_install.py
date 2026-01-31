#!/usr/bin/env python3
"""
package_install.py - Install a tar.gz package into Control Plane v2.

Usage:
    python3 scripts/package_install.py --archive PATH [--id PKG-ID] [--force]

Behavior:
    - Verifies SHA256 against packages_registry.csv when --id is provided.
    - Verifies detached signature if present (emits warning if missing).
    - Extracts archive into Control Plane root, preserving relative paths.
    - Uses INSTALL mode to allow writes to PRISTINE paths.
    - Warns if target files already exist unless --force is used.
    - Prints list of extracted files and suggests running integrity_check.
"""
from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.paths import CONTROL_PLANE
from lib.packages import unpack, verify, sha256_file
from lib.auth import get_provider
from lib import authz
from lib.package_audit import PackageContext, log_package_event
from lib.pristine import (
    InstallModeContext,
    assert_write_allowed,
    assert_inside_control_plane,
    OutsideBoundaryViolation,
    WriteMode,
)
from lib.signing import (
    has_signature,
    verify_detached,
    SignatureMissing,
    SignatureVerificationFailed,
)
from lib.provenance import (
    has_attestation,
    verify_attestation,
    log_attestation_waiver,
    AttestationMissing,
    AttestationVerificationFailed,
    AttestationDigestMismatch,
)

PKG_REG = CONTROL_PLANE / "registries" / "packages_registry.csv"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--archive", required=True, type=Path, help="tar.gz package path")
    ap.add_argument("--id", help="Package id to verify against packages_registry.csv")
    ap.add_argument("--force", action="store_true", help="Overwrite existing files")
    ap.add_argument("--session", help="Session id for audit", default="")
    ap.add_argument("--work-order", dest="work_order", help="Work order/task id", default="")
    ap.add_argument("--frameworks-active", dest="frameworks_active", help="Comma list of active frameworks", default="")
    ap.add_argument("--actor", help="Actor/user id for audit", default="")
    ap.add_argument("--token", help="Auth token (optional, else CONTROL_PLANE_TOKEN env)")
    args = ap.parse_args()

    # AuthZ
    identity = get_provider().authenticate(args.token or os.getenv("CONTROL_PLANE_TOKEN"))
    authz.require(identity, "install")

    archive = args.archive.resolve()
    if not archive.exists():
        raise SystemExit(f"Archive not found: {archive}")

    expected = None
    output_type = "extension"
    output_path = ""
    if args.id:
        rows = list(csv.DictReader(PKG_REG.open()))
        row = next((r for r in rows if r.get("id") == args.id), None)
        if not row:
            raise SystemExit(f"Package id {args.id} not found in {PKG_REG}")
        expected = (row.get("digest") or "").strip()
        if not expected:
            print(f"WARNING: registry digest empty for {args.id}")
        output_type = (row.get("output_type") or "extension").strip().lower()
        output_path = (row.get("output_path") or "").strip()

    # Verify hash if available
    if expected:
        ok, actual = verify(archive, expected)
        if not ok:
            raise SystemExit(f"Digest mismatch: registry={expected} actual={actual}")
    else:
        actual = sha256_file(archive)
        print(f"Computed SHA256: {actual}")

    # Verify signature if present
    if has_signature(archive):
        try:
            verify_detached(archive)
            print("Signature verified.")
        except SignatureVerificationFailed as e:
            raise SystemExit(f"Signature verification failed: {e}")
    else:
        allow_unsigned = os.getenv("CONTROL_PLANE_ALLOW_UNSIGNED", "0") == "1"
        if allow_unsigned:
            print("WARNING: No signature. Proceeding (CONTROL_PLANE_ALLOW_UNSIGNED=1)")
            # Log waiver to ledger for audit trail
            from lib.ledger_client import LedgerClient, LedgerEntry
            waiver_ledger = LedgerClient()
            waiver_ledger.write(LedgerEntry(
                event_type="signature_waiver",
                submission_id=args.id or archive.stem,
                decision="SIGNATURE_WAIVED",
                reason="Unsigned package installed with CONTROL_PLANE_ALLOW_UNSIGNED=1",
                metadata={"archive": str(archive), "actor": args.actor or "unknown"},
            ))
        else:
            raise SystemExit(
                "ERROR: Package unsigned. Set CONTROL_PLANE_ALLOW_UNSIGNED=1 to allow."
            )

    # Verify attestation if present (fail-closed unless waived)
    if has_attestation(archive):
        try:
            valid, att = verify_attestation(archive)
            print(f"Attestation verified: built {att.built_at} by {att.builder.tool}")
            if att.source and att.source.revision:
                print(f"  Source: {att.source.repo or 'local'}@{att.source.revision[:8]}")
        except (AttestationVerificationFailed, AttestationDigestMismatch) as e:
            raise SystemExit(f"Attestation verification failed: {e}")
    else:
        allow_unattested = os.getenv("CONTROL_PLANE_ALLOW_UNATTESTED", "0") == "1"
        if allow_unattested:
            print("WARNING: No attestation. Proceeding (CONTROL_PLANE_ALLOW_UNATTESTED=1)")
            log_attestation_waiver(
                archive,
                args.id or archive.stem,
                reason="Unattested package installed with CONTROL_PLANE_ALLOW_UNATTESTED=1",
                actor=args.actor or "unknown",
            )
        else:
            raise SystemExit(
                "ERROR: Package missing attestation. Set CONTROL_PLANE_ALLOW_UNATTESTED=1 to allow."
            )

    # Destination routing
    if output_type == "external":
        if not output_path:
            raise SystemExit("output_type=external requires output_path")
        dest_root = Path(output_path).expanduser().resolve()
    elif output_type == "module":
        dest_root = CONTROL_PLANE / "modules"
    else:
        dest_root = CONTROL_PLANE

    # Boundary check: deny writes outside CONTROL_PLANE unless explicitly allowed
    try:
        assert_inside_control_plane(dest_root)
    except OutsideBoundaryViolation as e:
        raise SystemExit(str(e))

    # Check for collisions (only for internal installs)
    if not args.force:
        import tarfile
        with tarfile.open(archive, "r:gz") as tar:
            for m in tar.getmembers():
                target = dest_root / m.name
                if target.exists():
                    raise SystemExit(f"Target exists: {target} (use --force to overwrite)")

    # Use INSTALL mode to allow writes to PRISTINE paths
    with InstallModeContext():
        # Verify each target path is allowed
        import tarfile
        with tarfile.open(archive, "r:gz") as tar:
            for m in tar.getmembers():
                target = dest_root / m.name
                assert_write_allowed(target, mode=WriteMode.INSTALL)

        extracted = unpack(archive, dest_root)

    print(f"Installed {archive} into {dest_root}")
    print("Extracted files:")
    for p in extracted:
        print(f" - {p.relative_to(dest_root)}")
    print("Next: run `python3 scripts/integrity_check.py --json` to verify.")

    ctx = PackageContext(
        package_id=args.id or archive.stem,
        action="install",
        before_hash=expected or "",
        after_hash=actual if expected else sha256_file(archive),
        frameworks_active=[s.strip() for s in args.frameworks_active.split(",") if s.strip()],
        session_id=args.session,
        work_order=args.work_order,
        actor=args.actor or (identity.user if identity else ""),
        external_path=str(dest_root) if output_type == "external" else None,
        in_registry=(output_type != "external"),
    )
    log_package_event(ctx)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
