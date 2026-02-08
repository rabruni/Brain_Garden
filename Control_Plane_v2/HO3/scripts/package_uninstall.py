#!/usr/bin/env python3
"""
package_uninstall.py - Uninstall a package by re-packing to packages_store.

Usage:
    python3 scripts/package_uninstall.py --id PKG-ID [--src-dir DIR] [--out-dir DIR]

Behavior:
    - Finds installed package in <src-dir>/<pkg_id> (default: installed/)
    - Re-packs contents to <out-dir>/<pkg_id>.tar.gz (default: packages_store/)
    - Removes installed directory
    - Package is reversibly moved, never destroyed
"""
from __future__ import annotations

import argparse
import os
import shutil
import tarfile
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "HOT"))

from kernel.paths import CONTROL_PLANE
from kernel.auth import get_provider
from lib import authz
from kernel.packages import sha256_file
from kernel.package_audit import PackageContext, log_package_event
from kernel.pristine import assert_write_allowed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True, help="Package ID to uninstall")
    ap.add_argument("--src-dir", dest="src_dir", type=Path,
                    help="Directory containing installed packages (default: installed/)")
    ap.add_argument("--out-dir", dest="out_dir", type=Path,
                    help="Directory for re-packed archives (default: packages_store/)")
    ap.add_argument("--session", help="Session id for audit", default="")
    ap.add_argument("--work-order", dest="work_order", help="Work order/task id", default="")
    ap.add_argument("--frameworks-active", dest="frameworks_active", help="Comma list of active frameworks", default="")
    ap.add_argument("--actor", help="Actor/user id for audit", default="")
    ap.add_argument("--token", help="Auth token (optional, else CONTROL_PLANE_TOKEN env)")
    args = ap.parse_args()

    # AuthZ
    identity = get_provider().authenticate(args.token or os.getenv("CONTROL_PLANE_TOKEN"))
    authz.require(identity, "uninstall")

    # Resolve directories
    installed_dir = args.src_dir.resolve() if args.src_dir else CONTROL_PLANE / "installed"
    packages_store = args.out_dir.resolve() if args.out_dir else CONTROL_PLANE / "packages_store"

    pkg_id = args.id
    installed_path = installed_dir / pkg_id

    if not installed_path.exists():
        print(f"ERROR: Not installed: {installed_path}")
        return 1

    if not installed_path.is_dir():
        print(f"ERROR: Not a directory: {installed_path}")
        return 1

    # Compute hash of installed content before removal (for audit)
    # We'll compute this after re-packing
    before_hash = ""

    # Ensure output directory exists
    packages_store.mkdir(parents=True, exist_ok=True)

    # Re-pack to packages_store
    archive_name = f"{pkg_id}.tar.gz"
    archive_path = packages_store / archive_name

    # Check write permission for output
    assert_write_allowed(archive_path)

    print(f"Re-packing: {installed_path} -> {archive_path}")

    # Create deterministic tar.gz (matching pack() behavior)
    import gzip
    import io

    def deterministic_filter(tarinfo: tarfile.TarInfo) -> tarfile.TarInfo:
        """Normalize TarInfo for deterministic archives."""
        tarinfo.mtime = 0
        tarinfo.uid = 0
        tarinfo.gid = 0
        tarinfo.uname = ""
        tarinfo.gname = ""
        tarinfo.mode = 0o755 if tarinfo.isdir() else 0o644
        return tarinfo

    # Create tar in memory first, then gzip with mtime=0
    tar_buffer = io.BytesIO()
    with tarfile.open(fileobj=tar_buffer, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for item in sorted(installed_path.rglob("*")):
            # Store paths relative to the installed package directory
            arcname = str(item.relative_to(installed_path))
            # Use recursive=False to avoid duplicate entries for directories
            tar.add(item, arcname=arcname, recursive=False, filter=deterministic_filter)

    # Write gzip with mtime=0 for determinism
    tar_data = tar_buffer.getvalue()
    with gzip.GzipFile(filename="", mode="wb", fileobj=open(archive_path, "wb"), mtime=0) as gz:
        gz.write(tar_data)

    # Compute hash of created archive
    after_hash = sha256_file(archive_path)

    # Write SHA256 sidecar
    sha_path = archive_path.with_suffix(archive_path.suffix + ".sha256")
    sha_path.write_text(after_hash, encoding="utf-8")

    # Remove installed directory
    print(f"Removing: {installed_path}")
    shutil.rmtree(installed_path)

    print(f"SUCCESS: Package returned to {archive_path}")
    print(f"SHA256: {after_hash}")

    # Log uninstall event
    ctx = PackageContext(
        package_id=pkg_id,
        action="uninstall",
        before_hash=before_hash,
        after_hash=after_hash,
        frameworks_active=[s.strip() for s in args.frameworks_active.split(",") if s.strip()],
        session_id=args.session,
        work_order=args.work_order,
        actor=args.actor or (identity.user if identity else ""),
        in_registry=True,
    )
    log_package_event(ctx)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
