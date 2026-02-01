#!/usr/bin/env python3
"""
package_install.py - Install a tar.gz package into Control Plane v2.

Usage:
    python3 scripts/package_install.py --archive PATH [--id PKG-ID] [--force] [--root /path]

Behavior:
    - Verifies SHA256 against packages_registry.csv when --id is provided.
    - Verifies detached signature if present (emits warning if missing).
    - Extracts archive into Control Plane root, preserving relative paths.
    - Uses INSTALL mode to allow writes to PRISTINE paths.
    - Warns if target files already exist unless --force is used.
    - Prints list of extracted files and suggests running integrity_check.
    - Enforces plane scoping: --root specifies plane, writes confined to that plane.
    - Validates target_plane from manifest matches current plane.

Per Plane-Aware Package System design.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import tarfile
from datetime import datetime, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.paths import CONTROL_PLANE
from lib.plane import (
    PlaneContext,
    get_current_plane,
    validate_target_plane,
    validate_external_interface_direction,
    PlaneTargetMismatch,
    CrossPlaneViolation,
)
from lib.install_auth import InstallerClaims, require_authorization
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


def load_manifest_from_archive(archive_path: Path) -> dict | None:
    """Extract and load manifest.json from archive."""
    try:
        with tarfile.open(archive_path, "r:gz") as tf:
            for member in tf.getmembers():
                if member.name.endswith("manifest.json"):
                    f = tf.extractfile(member)
                    if f:
                        return json.load(f)
    except (tarfile.TarError, json.JSONDecodeError, IOError):
        return None
    return None


def write_plane_aware_receipt(
    pkg_id: str,
    version: str,
    manifest: dict,
    archive_path: Path,
    files: list,
    plane: PlaneContext,
) -> Path:
    """Write install receipt with plane information."""
    receipt_dir = plane.receipts_dir / pkg_id
    receipt_dir.mkdir(parents=True, exist_ok=True)

    file_entries = []
    for f in files:
        file_path = plane.root / f
        if file_path.exists() and file_path.is_file():
            file_entries.append({
                "path": str(f),
                "sha256": sha256_file(file_path)
            })

    receipt = {
        "id": pkg_id,
        "version": version,
        "installed_at": datetime.now(timezone.utc).isoformat(),
        "plane_name": plane.name,
        "plane_root": str(plane.root),
        "manifest_schema_version": manifest.get("schema_version", "1.0"),
        "target_plane": manifest.get("target_plane", "any"),
        "tier": manifest.get("tier", ""),
        "archive": str(archive_path),
        "archive_digest": sha256_file(archive_path),
        "installer": "package_install",
        "files": file_entries,
    }

    receipt_path = receipt_dir / "receipt.json"
    with open(receipt_path, "w", encoding="utf-8") as f:
        json.dump(receipt, f, indent=2)

    return receipt_path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--archive", required=True, type=Path, help="tar.gz package path")
    ap.add_argument("--id", help="Package id to verify against packages_registry.csv")
    ap.add_argument("--force", action="store_true", help="Overwrite existing files")
    ap.add_argument("--root", type=Path, help="Plane root path (defaults to CONTROL_PLANE)")
    ap.add_argument("--env", default="dev", help="Environment (dev/staging/prod)")
    ap.add_argument("--session", help="Session id for audit", default="")
    ap.add_argument("--work-order", dest="work_order", help="Work order/task id", default="")
    ap.add_argument("--frameworks-active", dest="frameworks_active", help="Comma list of active frameworks", default="")
    ap.add_argument("--actor", help="Actor/user id for audit", default="")
    ap.add_argument("--token", help="Auth token (optional, else CONTROL_PLANE_TOKEN env)")
    args = ap.parse_args()

    # Resolve plane context
    plane_root = args.root.resolve() if args.root else None
    plane = get_current_plane(plane_root)

    # AuthZ with plane scoping
    identity = get_provider().authenticate(args.token or os.getenv("CONTROL_PLANE_TOKEN"))
    authz.require(identity, "install")

    # Create installer claims for plane-aware authorization
    try:
        claims = InstallerClaims.from_identity(identity, args.env)
        # Plane permission check will happen after we load the manifest
    except Exception as e:
        print(f"WARNING: Could not create installer claims: {e}")

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

    # Load manifest for plane-aware validation
    manifest = load_manifest_from_archive(archive)
    if manifest is None:
        print("WARNING: Could not load manifest from archive")
        manifest = {}

    # Validate target_plane
    target_plane = manifest.get("target_plane", "any")
    if not validate_target_plane(target_plane, plane):
        raise SystemExit(
            f"Package targets plane '{target_plane}' but current plane is '{plane.name}'. "
            f"Use --root to specify the correct plane."
        )

    # Validate external interfaces direction rules
    external_interfaces = manifest.get("external_interfaces", [])
    for iface in external_interfaces:
        source_plane = iface.get("source_plane", "")
        iface_name = iface.get("name", "unknown")
        if not validate_external_interface_direction(plane, source_plane):
            raise SystemExit(
                f"Interface '{iface_name}' from plane '{source_plane}' cannot be "
                f"referenced by plane '{plane.name}' (cross-plane direction violation)"
            )

    # Check plane authorization
    pkg_tier = manifest.get("tier", "")
    try:
        if 'claims' in dir():
            require_authorization(
                action="install",
                pkg_id=args.id or archive.stem,
                tier=pkg_tier,
                env=args.env,
                claims=claims,
                plane=plane.name,
            )
    except PermissionError as e:
        raise SystemExit(f"Authorization failed: {e}")

    # Destination routing - ALWAYS within plane root
    if output_type == "external":
        if not output_path:
            raise SystemExit("output_type=external requires output_path")
        dest_root = Path(output_path).expanduser().resolve()
        # Verify external path is still within plane for safety
        if not str(dest_root).startswith(str(plane.root)):
            print(f"WARNING: External path {dest_root} is outside plane root {plane.root}")
    elif output_type == "module":
        dest_root = plane.root / "modules"
    else:
        dest_root = plane.root

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
    print(f"Plane: {plane.name} ({plane.plane_type.value})")
    print("Extracted files:")
    for p in extracted:
        print(f" - {p.relative_to(dest_root)}")

    # Write plane-aware receipt
    if manifest:
        receipt_path = write_plane_aware_receipt(
            pkg_id=args.id or archive.stem,
            version=manifest.get("version", "0.0.0"),
            manifest=manifest,
            archive_path=archive,
            files=[str(p.relative_to(plane.root)) for p in extracted],
            plane=plane,
        )
        print(f"Receipt: {receipt_path}")

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
