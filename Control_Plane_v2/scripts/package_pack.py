#!/usr/bin/env python3
"""
package_pack.py - Build a single-file tar.gz package.

Usage:
    python3 scripts/package_pack.py --src PATH [--out PATH] [--id PKG-ID] [--sign]

Behavior:
    - Packs file/dir at --src into a .tar.gz (default: packages_store/<name>.tar.gz)
    - Computes SHA256 and writes alongside as <archive>.sha256
    - If CONTROL_PLANE_SIGNING_KEY set or --sign, creates detached signature
    - If --id provided, updates registries/packages_registry.csv for that id
    - Output restricted to packages_store (DERIVED path)
"""
from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.paths import CONTROL_PLANE
from lib.auth import get_provider
from lib import authz
from lib.packages import pack, sha256_file
from lib.package_audit import PackageContext, log_package_event
from lib.pristine import assert_write_allowed
from lib.signing import sign_detached, SignatureError
from lib.provenance import (
    create_attestation,
    sign_attestation,
    compute_attestation_digest,
    AttestationError,
)


PKG_REG = CONTROL_PLANE / "registries" / "packages_registry.csv"
STORE_DIR = CONTROL_PLANE / "packages_store"


def update_registry(
    pkg_id: str,
    archive_path: Path,
    digest: str,
    attestation_path: Path = None,
    attestation_digest: str = None,
    attestation_sig_path: Path = None,
) -> None:
    rows = list(csv.DictReader(PKG_REG.open()))
    headers = rows[0].keys() if rows else []
    updated = False
    # Store path relative to CONTROL_PLANE for portability
    try:
        rel_path = archive_path.relative_to(CONTROL_PLANE)
    except ValueError:
        rel_path = archive_path  # Keep absolute if outside CP (shouldn't happen)
    for r in rows:
        if r.get("id") == pkg_id:
            r["source"] = str(rel_path)
            r["source_type"] = "tar"
            r["digest"] = digest
            # Update attestation fields if provided
            if attestation_path:
                try:
                    att_rel = attestation_path.relative_to(CONTROL_PLANE)
                except ValueError:
                    att_rel = attestation_path
                r["attestation_path"] = str(att_rel)
            if attestation_digest:
                r["attestation_digest"] = attestation_digest
            if attestation_sig_path:
                try:
                    att_sig_rel = attestation_sig_path.relative_to(CONTROL_PLANE)
                except ValueError:
                    att_sig_rel = attestation_sig_path
                r["attestation_signature_path"] = str(att_sig_rel)
            updated = True
    if not updated:
        raise SystemExit(f"Package id {pkg_id} not found in {PKG_REG}")
    with PKG_REG.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=headers)
        w.writeheader(); w.writerows(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, type=Path, help="File or directory to package")
    ap.add_argument("--out", type=Path, help="Output archive path")
    ap.add_argument("--id", help="Package ID to update in packages_registry.csv")
    ap.add_argument("--sign", action="store_true", help="Create detached signature")
    ap.add_argument("--attest", action="store_true", help="Generate provenance attestation")
    ap.add_argument("--source-repo", dest="source_repo", help="Source repository URL for attestation")
    ap.add_argument("--source-revision", dest="source_revision", help="Source commit SHA for attestation")
    ap.add_argument("--source-branch", dest="source_branch", help="Source branch for attestation")
    ap.add_argument("--session", help="Session id for audit", default="")
    ap.add_argument("--work-order", dest="work_order", help="Work order/task id", default="")
    ap.add_argument("--frameworks-active", dest="frameworks_active", help="Comma list of active frameworks", default="")
    ap.add_argument("--actor", help="Actor/user id for audit", default="")
    ap.add_argument("--token", help="Auth token (optional, else CONTROL_PLANE_TOKEN env)")
    args = ap.parse_args()

    src = args.src.resolve()
    if not src.exists():
        raise SystemExit(f"Source not found: {src}")

    # AuthZ
    identity = get_provider().authenticate(args.token or os.getenv("CONTROL_PLANE_TOKEN"))
    authz.require(identity, "pack")

    out = args.out
    if out is None:
        STORE_DIR.mkdir(parents=True, exist_ok=True)
        name = src.stem if src.is_file() else src.name
        out = STORE_DIR / f"{name}.tar.gz"
    out = out.resolve()

    # Enforce: output must be in DERIVED path (packages_store)
    assert_write_allowed(out)

    digest = pack(src, out, base=CONTROL_PLANE)
    sha_path = out.with_suffix(out.suffix + ".sha256")
    assert_write_allowed(sha_path)
    sha_path.write_text(digest, encoding="utf-8")

    # Signing: if key available or --sign requested
    sig_path = None
    if args.sign or os.getenv("CONTROL_PLANE_SIGNING_KEY"):
        try:
            sig_path = sign_detached(out, signer=args.actor or (identity.user if identity else ""))
            print(f"Signed: {sig_path}")
        except SignatureError as e:
            print(f"WARNING: Signing failed: {e}")

    # Attestation: if --attest or CONTROL_PLANE_ATTEST_PACKAGES=1
    attestation_path = None
    attestation_sig_path = None
    attestation_digest = None
    if args.attest or os.getenv("CONTROL_PLANE_ATTEST_PACKAGES") == "1":
        try:
            pkg_id = args.id or out.stem
            attestation_path = create_attestation(
                out,
                pkg_id,
                source_repo=args.source_repo,
                source_revision=args.source_revision,
                source_branch=args.source_branch,
            )
            attestation_digest = compute_attestation_digest(attestation_path)
            print(f"Attestation: {attestation_path}")

            # Sign attestation if signing key available
            if args.sign or os.getenv("CONTROL_PLANE_SIGNING_KEY"):
                try:
                    attestation_sig_path = sign_attestation(
                        attestation_path,
                        signer=args.actor or (identity.user if identity else ""),
                    )
                    print(f"Attestation signed: {attestation_sig_path}")
                except AttestationError as e:
                    print(f"WARNING: Attestation signing failed: {e}")
        except AttestationError as e:
            print(f"WARNING: Attestation failed: {e}")

    if args.id:
        update_registry(
            args.id,
            out,
            digest,
            attestation_path=attestation_path,
            attestation_digest=attestation_digest,
            attestation_sig_path=attestation_sig_path,
        )
        ctx = PackageContext(
            package_id=args.id,
            action="pack",
            before_hash="",
            after_hash=digest,
            frameworks_active=[s.strip() for s in args.frameworks_active.split(",") if s.strip()],
            session_id=args.session,
            work_order=args.work_order,
            actor=args.actor or (identity.user if identity else ""),
            in_registry=True,
        )
        log_package_event(ctx)

    print(f"Packed {src} -> {out}")
    print(f"SHA256: {digest}")
    if args.id:
        print(f"Updated registry for {args.id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
