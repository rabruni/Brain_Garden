#!/usr/bin/env python3
"""CLI for tier ledger lifecycle management.

Usage:
    python3 scripts/ledger_tier.py create --tier FIRST --root /path/to/tier [options]
    python3 scripts/ledger_tier.py archive --manifest /path/to/tier.json
    python3 scripts/ledger_tier.py list --root /path/to/search
    python3 scripts/ledger_tier.py verify --manifest /path/to/tier.json
    python3 scripts/ledger_tier.py info --manifest /path/to/tier.json
"""

import argparse
import json
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kernel.ledger_factory import LedgerFactory
from kernel.tier_manifest import TierManifest, migrate_tier_name
from kernel.ledger_client import LedgerClient


def cmd_create(args):
    """Create a new tier."""
    tier_root = Path(args.root).resolve()

    if (tier_root / "tier.json").exists():
        print(f"Error: Tier already exists at {tier_root}", file=sys.stderr)
        return 1

    # Migrate legacy tier name to canonical
    tier = migrate_tier_name(args.tier)

    manifest, client = LedgerFactory.create_tier(
        tier=tier,
        tier_root=tier_root,
        work_order_id=args.work_order_id,
        session_id=args.session_id,
        parent_ledger=args.parent,
        ledger_name=args.ledger_name,
    )

    print(f"Created {tier} tier at {tier_root}")
    print(f"  Manifest: {manifest.manifest_path}")
    print(f"  Ledger:   {manifest.absolute_ledger_path}")
    if args.parent:
        print(f"  Parent:   {args.parent}")
    return 0


def cmd_archive(args):
    """Archive a tier."""
    manifest_path = Path(args.manifest).resolve()

    if not manifest_path.exists():
        print(f"Error: Manifest not found: {manifest_path}", file=sys.stderr)
        return 1

    manifest = LedgerFactory.archive(manifest_path)
    print(f"Archived tier: {manifest.tier_root}")
    print(f"  Status: {manifest.status}")
    return 0


def cmd_close(args):
    """Close a tier permanently."""
    manifest_path = Path(args.manifest).resolve()

    if not manifest_path.exists():
        print(f"Error: Manifest not found: {manifest_path}", file=sys.stderr)
        return 1

    manifest = LedgerFactory.close(manifest_path)
    print(f"Closed tier: {manifest.tier_root}")
    print(f"  Status: {manifest.status}")
    return 0


def cmd_list(args):
    """List all tiers under a root."""
    search_root = Path(args.root).resolve()

    if not search_root.exists():
        print(f"Error: Directory not found: {search_root}", file=sys.stderr)
        return 1

    tiers = LedgerFactory.list_tiers(search_root)

    if not tiers:
        print(f"No tiers found under {search_root}")
        return 0

    if args.json:
        output = [m.to_dict() for m in tiers]
        print(json.dumps(output, indent=2))
    else:
        print(f"Found {len(tiers)} tier(s) under {search_root}:\n")
        for m in tiers:
            status_icon = {"active": "+", "archived": "-", "closed": "x"}.get(m.status, "?")
            print(f"[{status_icon}] {m.tier}: {m.tier_root}")
            if m.work_order_id:
                print(f"    Work Order: {m.work_order_id}")
            if m.session_id:
                print(f"    Session:    {m.session_id}")
            print(f"    Status:     {m.status}")
            print()

    return 0


def cmd_verify(args):
    """Verify tier ledger integrity."""
    manifest_path = Path(args.manifest).resolve()

    if not manifest_path.exists():
        print(f"Error: Manifest not found: {manifest_path}", file=sys.stderr)
        return 1

    manifest = TierManifest.load(manifest_path)
    client = LedgerClient(ledger_path=manifest.absolute_ledger_path)

    print(f"Verifying {manifest.tier} tier: {manifest.tier_root}")
    print(f"  Ledger: {manifest.absolute_ledger_path}")

    valid, issues = client.verify_chain()
    entry_count = client.count()

    print(f"  Entries: {entry_count}")
    print(f"  Chain valid: {valid}")

    if issues:
        print(f"\nIssues ({len(issues)}):")
        for issue in issues[:10]:  # Limit output
            print(f"  - {issue}")
        if len(issues) > 10:
            print(f"  ... and {len(issues) - 10} more")

    return 0 if valid else 1


def cmd_info(args):
    """Show tier manifest info."""
    manifest_path = Path(args.manifest).resolve()

    if not manifest_path.exists():
        print(f"Error: Manifest not found: {manifest_path}", file=sys.stderr)
        return 1

    manifest = TierManifest.load(manifest_path)

    if args.json:
        print(json.dumps(manifest.to_dict(), indent=2))
    else:
        print(f"Tier Manifest: {manifest_path}")
        print(f"  Tier:         {manifest.tier}")
        print(f"  Root:         {manifest.tier_root}")
        print(f"  Ledger:       {manifest.ledger_path}")
        print(f"  Status:       {manifest.status}")
        print(f"  Created:      {manifest.created_at}")
        if manifest.parent_ledger:
            print(f"  Parent:       {manifest.parent_ledger}")
        if manifest.work_order_id:
            print(f"  Work Order:   {manifest.work_order_id}")
        if manifest.session_id:
            print(f"  Session:      {manifest.session_id}")

    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Tier ledger lifecycle management",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # create
    p_create = subparsers.add_parser("create", help="Create a new tier")
    p_create.add_argument("--tier", required=True,
                          choices=["HO3", "HO2", "HO1", "HOT", "SECOND", "FIRST"],
                          help="Tier type (canonical: HO3, HO2, HO1; legacy: HOT, SECOND, FIRST)")
    p_create.add_argument("--root", required=True, help="Tier root directory")
    p_create.add_argument("--work-order-id", help="Work order ID (SECOND tier)")
    p_create.add_argument("--session-id", help="Session ID (FIRST tier)")
    p_create.add_argument("--parent", help="Parent ledger path/URI")
    p_create.add_argument("--ledger-name", help="Custom ledger filename")
    p_create.set_defaults(func=cmd_create)

    # archive
    p_archive = subparsers.add_parser("archive", help="Archive a tier")
    p_archive.add_argument("--manifest", required=True, help="Path to tier.json")
    p_archive.set_defaults(func=cmd_archive)

    # close
    p_close = subparsers.add_parser("close", help="Close a tier permanently")
    p_close.add_argument("--manifest", required=True, help="Path to tier.json")
    p_close.set_defaults(func=cmd_close)

    # list
    p_list = subparsers.add_parser("list", help="List tiers under a root")
    p_list.add_argument("--root", required=True, help="Directory to search")
    p_list.add_argument("--json", action="store_true", help="Output as JSON")
    p_list.set_defaults(func=cmd_list)

    # verify
    p_verify = subparsers.add_parser("verify", help="Verify tier ledger integrity")
    p_verify.add_argument("--manifest", required=True, help="Path to tier.json")
    p_verify.set_defaults(func=cmd_verify)

    # info
    p_info = subparsers.add_parser("info", help="Show tier manifest info")
    p_info.add_argument("--manifest", required=True, help="Path to tier.json")
    p_info.add_argument("--json", action="store_true", help="Output as JSON")
    p_info.set_defaults(func=cmd_info)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
