#!/usr/bin/env python3
"""
cp_plane.py - Unified CLI for plane lifecycle management.

Commands:
    create              Create a new plane root
    list                List all configured planes
    info                Show plane information
    init-chain          Initialize chain config from existing planes
    verify              Verify plane integrity
    create-work-order   Create a work-order instance under HO2
    create-session      Create a session instance under HO1
    list-instances      List instances under a base plane
    verify-chain        Verify full chain hierarchy
    summarize-up        Summarize child ledger entries to parent
    push-policy         Push policy from parent to child instances
    apply-policy        Apply a pushed policy in an instance

Usage:
    python3 scripts/cp_plane.py create --tier HO3 --root /path/to/ho3
    python3 scripts/cp_plane.py create --tier HO2 --root /path/to/ho2
    python3 scripts/cp_plane.py create --tier HO1 --root /path/to/ho1
    python3 scripts/cp_plane.py list
    python3 scripts/cp_plane.py info --root /path/to/plane
    python3 scripts/cp_plane.py init-chain --ho3 /path/ho3 --ho2 /path/ho2 --ho1 /path/ho1
    python3 scripts/cp_plane.py create-work-order --id WO-2026-001 --base ./planes/ho2
    python3 scripts/cp_plane.py create-session --id sess-001 --base ./planes/ho1
    python3 scripts/cp_plane.py list-instances --base ./planes/ho2
    python3 scripts/cp_plane.py verify-chain --root ./planes/ho2/work_orders/WO-2026-001
    python3 scripts/cp_plane.py summarize-up --parent ./planes/ho2 --recursive
    python3 scripts/cp_plane.py push-policy --policy POL-001 --version 1.0 --parent ./planes/ho2
    python3 scripts/cp_plane.py apply-policy --root ./planes/ho2/work_orders/WO-001
"""

import argparse
import json
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.ledger_factory import LedgerFactory
from lib.ledger_client import LedgerClient, LedgerEntry
from lib.tier_manifest import TierManifest, migrate_tier_name
from lib.plane import (
    PlaneType,
    PlaneContext,
    load_chain_config,
    clear_chain_config_cache,
    get_current_plane,
    migrate_plane_type,
    PLANE_NAME_MAP,
)
from lib.paths import CONTROL_PLANE
from lib.cursor import (
    CursorManager,
    compute_dedupe_key,
    compute_policy_push_dedupe_key,
    compute_policy_apply_dedupe_key,
)


# Tier to PlaneType mapping
TIER_TO_PLANE_TYPE = {
    "HO3": PlaneType.HO3,
    "HO2": PlaneType.HO2,
    "HO1": PlaneType.HO1,
    # Legacy names
    "HOT": PlaneType.HO3,
    "SECOND": PlaneType.HO2,
    "FIRST": PlaneType.HO1,
}

# Required directories for each plane
PLANE_DIRECTORIES = [
    "registries",
    "frameworks",
    "policies",
    "packages_store",
    "installed",
    "ledger",
    "schemas",
    "lib",
    "scripts",
    "modules",
    "specs",
    "versions",
    "tmp",
    "_staging",
]


def cmd_create(args) -> int:
    """Create a new plane root."""
    tier_root = Path(args.root).resolve()

    if (tier_root / "tier.json").exists():
        print(f"Error: Tier already exists at {tier_root}", file=sys.stderr)
        return 1

    # Migrate legacy tier name to canonical
    tier = migrate_tier_name(args.tier)

    # Create tier manifest and ledger
    manifest, client = LedgerFactory.create_tier(
        tier=tier,
        tier_root=tier_root,
        parent_ledger=args.parent,
        ledger_name=args.ledger_name,
    )

    # Create required directories
    for dir_name in PLANE_DIRECTORIES:
        dir_path = tier_root / dir_name
        dir_path.mkdir(parents=True, exist_ok=True)

    # Create empty registry CSV files if requested
    if args.seed_registries:
        _seed_registries(tier_root)

    print(f"Created {tier} plane at {tier_root}")
    print(f"  Manifest: {manifest.manifest_path}")
    print(f"  Ledger:   {manifest.absolute_ledger_path}")
    print(f"  Directories: {len(PLANE_DIRECTORIES)} created")
    if args.parent:
        print(f"  Parent:   {args.parent}")

    return 0


def _seed_registries(tier_root: Path) -> None:
    """Seed empty registry CSV files."""
    registries_dir = tier_root / "registries"

    # Create empty packages registry
    packages_registry = registries_dir / "packages_registry.csv"
    if not packages_registry.exists():
        packages_registry.write_text(
            "id,name,version,tier,status,description\n"
        )

    # Create empty frameworks registry
    frameworks_registry = registries_dir / "frameworks_registry.csv"
    if not frameworks_registry.exists():
        frameworks_registry.write_text(
            "id,name,version,status,description\n"
        )


def cmd_list(args) -> int:
    """List all configured planes."""
    try:
        planes = load_chain_config()
    except Exception as e:
        print(f"Error loading chain config: {e}", file=sys.stderr)
        return 1

    if not planes:
        print("No planes configured.")
        return 0

    if args.json:
        output = [p.to_dict() for p in planes]
        print(json.dumps(output, indent=2))
    else:
        print(f"Found {len(planes)} plane(s):\n")
        for plane in planes:
            exists = plane.root.exists()
            status = "+" if exists else "-"
            has_manifest = (plane.root / "tier.json").exists()
            manifest_status = "(manifest: OK)" if has_manifest else "(no manifest)"

            print(f"[{status}] {plane.name}: {plane.plane_type.value}")
            print(f"    Root: {plane.root}")
            print(f"    Status: {'exists' if exists else 'missing'} {manifest_status}")
            print()

    return 0


def cmd_info(args) -> int:
    """Show plane information."""
    root = Path(args.root).resolve()

    if not root.exists():
        print(f"Error: Directory not found: {root}", file=sys.stderr)
        return 1

    # Try to load tier manifest
    manifest_path = root / "tier.json"
    manifest = None
    if manifest_path.exists():
        try:
            manifest = TierManifest.load(manifest_path)
        except Exception as e:
            print(f"Warning: Could not load tier.json: {e}", file=sys.stderr)

    # Try to get plane context from config
    try:
        plane = get_current_plane(root)
    except Exception:
        plane = None

    if args.json:
        output = {
            "root": str(root),
            "manifest": manifest.to_dict() if manifest else None,
            "plane_context": plane.to_dict() if plane else None,
        }
        print(json.dumps(output, indent=2))
    else:
        print(f"Plane Info: {root}")
        print()

        if manifest:
            print(f"Tier Manifest:")
            print(f"  Tier:       {manifest.tier}")
            print(f"  Ledger:     {manifest.ledger_path}")
            print(f"  Status:     {manifest.status}")
            print(f"  Created:    {manifest.created_at}")
            if manifest.parent_ledger:
                print(f"  Parent:     {manifest.parent_ledger}")
        else:
            print("  No tier.json manifest found")

        print()

        if plane:
            print(f"Plane Context:")
            print(f"  Name:       {plane.name}")
            print(f"  Type:       {plane.plane_type.value}")
            print(f"  Pristine:   {', '.join(plane.pristine_roots[:3])}...")
            print(f"  Derived:    {', '.join(plane.derived_roots[:3])}...")
        else:
            print("  Not in chain config")

        print()

        # Directory status
        print("Directories:")
        for dir_name in ["registries", "frameworks", "policies", "ledger", "installed"]:
            dir_path = root / dir_name
            exists = dir_path.exists()
            status = "OK" if exists else "missing"
            print(f"  {dir_name}: {status}")

    return 0


def cmd_init_chain(args) -> int:
    """Initialize chain config from existing planes."""
    config_dir = CONTROL_PLANE / "config"
    config_path = config_dir / "control_plane_chain.json"

    # Validate paths
    planes_config = []

    if args.ho3:
        ho3_root = Path(args.ho3).resolve()
        if not ho3_root.exists():
            print(f"Error: HO3 path does not exist: {ho3_root}", file=sys.stderr)
            return 1
        planes_config.append({
            "name": "ho3",
            "type": "HO3",
            "root": str(ho3_root),
            "comment": "Highest privilege plane - cannot be modified by lower planes"
        })

    if args.ho2:
        ho2_root = Path(args.ho2).resolve()
        if not ho2_root.exists():
            print(f"Error: HO2 path does not exist: {ho2_root}", file=sys.stderr)
            return 1
        planes_config.append({
            "name": "ho2",
            "type": "HO2",
            "root": str(ho2_root),
            "comment": "Middle tier - can reference HO3 interfaces (read-only)"
        })

    if args.ho1:
        ho1_root = Path(args.ho1).resolve()
        if not ho1_root.exists():
            print(f"Error: HO1 path does not exist: {ho1_root}", file=sys.stderr)
            return 1
        planes_config.append({
            "name": "ho1",
            "type": "HO1",
            "root": str(ho1_root),
            "comment": "Lowest tier - can reference HO2 and HO3 interfaces (read-only)"
        })

    if not planes_config:
        print("Error: At least one plane must be specified", file=sys.stderr)
        return 1

    # Create config
    config = {
        "$schema": "../schemas/control_plane_chain.json",
        "description": "Control Plane chain configuration - defines the 3-plane topology",
        "planes": planes_config,
    }

    # Backup existing config
    if config_path.exists() and not args.force:
        backup_path = config_path.with_suffix(".json.bak")
        config_path.rename(backup_path)
        print(f"Backed up existing config to {backup_path}")

    # Write new config
    config_dir.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
        f.write("\n")

    # Clear cached config
    clear_chain_config_cache()

    print(f"Created chain config: {config_path}")
    print(f"  Planes: {len(planes_config)}")
    for p in planes_config:
        print(f"    - {p['name']} ({p['type']}): {p['root']}")

    return 0


def cmd_verify(args) -> int:
    """Verify plane integrity."""
    root = Path(args.root).resolve()

    if not root.exists():
        print(f"Error: Directory not found: {root}", file=sys.stderr)
        return 1

    issues = []

    # Check tier.json
    manifest_path = root / "tier.json"
    if not manifest_path.exists():
        issues.append("Missing tier.json manifest")
    else:
        try:
            manifest = TierManifest.load(manifest_path)
            if manifest.tier not in ("HO3", "HO2", "HO1"):
                issues.append(f"Unknown tier type: {manifest.tier}")
        except Exception as e:
            issues.append(f"Invalid tier.json: {e}")

    # Check required directories
    for dir_name in ["registries", "ledger", "installed"]:
        dir_path = root / dir_name
        if not dir_path.exists():
            issues.append(f"Missing directory: {dir_name}")

    # Check ledger
    ledger_dir = root / "ledger"
    if ledger_dir.exists():
        ledger_files = list(ledger_dir.glob("*.jsonl"))
        if not ledger_files:
            issues.append("No ledger files found in ledger/")

    if args.json:
        output = {
            "root": str(root),
            "valid": len(issues) == 0,
            "issues": issues,
        }
        print(json.dumps(output, indent=2))
    else:
        if issues:
            print(f"Plane verification FAILED: {root}")
            for issue in issues:
                print(f"  - {issue}")
            return 1
        else:
            print(f"Plane verification OK: {root}")

    return 0 if not issues else 1


def cmd_create_work_order(args) -> int:
    """Create a work-order instance under HO2."""
    base_root = Path(args.base).resolve()

    if not base_root.exists():
        print(f"Error: Base directory not found: {base_root}", file=sys.stderr)
        return 1

    try:
        manifest, client = LedgerFactory.create_work_order_instance(
            base_root=base_root,
            work_order_id=args.id,
        )
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error creating work order: {e}", file=sys.stderr)
        return 1

    # Create standard directories
    for dir_name in ["ledger", "installed", "registries"]:
        (manifest.tier_root / dir_name).mkdir(parents=True, exist_ok=True)

    print(f"Created work order {args.id}")
    print(f"  Root:     {manifest.tier_root}")
    print(f"  Manifest: {manifest.manifest_path}")
    print(f"  Ledger:   {manifest.absolute_ledger_path}")
    print(f"  Parent:   {manifest.parent_ledger}")

    return 0


def cmd_create_session(args) -> int:
    """Create a session instance under HO1."""
    base_root = Path(args.base).resolve()

    if not base_root.exists():
        print(f"Error: Base directory not found: {base_root}", file=sys.stderr)
        return 1

    try:
        manifest, client = LedgerFactory.create_session_instance(
            base_root=base_root,
            session_id=args.id,
        )
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error creating session: {e}", file=sys.stderr)
        return 1

    # Create standard directories
    for dir_name in ["ledger", "installed", "registries"]:
        (manifest.tier_root / dir_name).mkdir(parents=True, exist_ok=True)

    print(f"Created session {args.id}")
    print(f"  Root:     {manifest.tier_root}")
    print(f"  Manifest: {manifest.manifest_path}")
    print(f"  Ledger:   {manifest.absolute_ledger_path}")
    print(f"  Parent:   {manifest.parent_ledger}")

    return 0


def cmd_list_instances(args) -> int:
    """List instances under a base plane."""
    base_root = Path(args.base).resolve()

    if not base_root.exists():
        print(f"Error: Base directory not found: {base_root}", file=sys.stderr)
        return 1

    instances = LedgerFactory.list_instances(base_root)

    if args.json:
        output = [m.to_dict() for m in instances]
        print(json.dumps(output, indent=2))
    else:
        if not instances:
            print(f"No instances found under {base_root}")
            return 0

        print(f"Found {len(instances)} instance(s) under {base_root}:\n")
        for manifest in instances:
            instance_type = "work_order" if manifest.work_order_id else "session"
            instance_id = manifest.work_order_id or manifest.session_id or "unknown"
            print(f"  [{instance_type}] {instance_id}")
            print(f"    Root:   {manifest.tier_root}")
            print(f"    Status: {manifest.status}")
            print()

    return 0


def cmd_verify_chain(args) -> int:
    """Verify full chain hierarchy from a plane."""
    from lib.ledger_client import LedgerClient

    root = Path(args.root).resolve()

    if not root.exists():
        print(f"Error: Directory not found: {root}", file=sys.stderr)
        return 1

    manifest_path = root / "tier.json"
    if not manifest_path.exists():
        print(f"Error: No tier.json found at {root}", file=sys.stderr)
        return 1

    all_issues = []
    all_results = []
    current_root = root

    # Walk up the chain verifying each plane
    while current_root:
        manifest = TierManifest.load(current_root / "tier.json")
        client = LedgerClient(ledger_path=manifest.absolute_ledger_path)

        # Verify GENESIS
        genesis_valid, genesis_issues = client.verify_genesis()

        # Verify chain link to parent
        link_valid = True
        link_issues = []
        if manifest.parent_ledger:
            parent_path = (manifest.tier_root / manifest.parent_ledger).resolve()
            link_valid, link_issues = client.verify_chain_link(parent_path)

        instance_desc = ""
        if manifest.work_order_id:
            instance_desc = f" work-order {manifest.work_order_id}"
        elif manifest.session_id:
            instance_desc = f" session {manifest.session_id}"

        result = {
            "tier": manifest.tier,
            "root": str(current_root),
            "work_order_id": manifest.work_order_id,
            "session_id": manifest.session_id,
            "genesis_valid": genesis_valid,
            "genesis_issues": genesis_issues,
            "link_valid": link_valid,
            "link_issues": link_issues,
        }
        all_results.append(result)
        all_issues.extend(genesis_issues)
        all_issues.extend(link_issues)

        if not args.json:
            print(f"Verifying {manifest.tier}{instance_desc}...")
            print(f"  GENESIS: {'OK' if genesis_valid else 'FAILED'}")
            for issue in genesis_issues:
                print(f"    {issue}")
            if manifest.parent_ledger:
                print(f"  Parent link: {'OK' if link_valid else 'FAILED'}")
                for issue in link_issues:
                    print(f"    {issue}")

        # Move to parent if exists
        if manifest.parent_ledger:
            parent_path = (manifest.tier_root / manifest.parent_ledger).resolve()
            # Find the tier root for parent
            parent_tier_root = parent_path.parent.parent
            if (parent_tier_root / "tier.json").exists():
                current_root = parent_tier_root
            else:
                current_root = None
        else:
            current_root = None

    has_failures = any(i.startswith("FAIL") for i in all_issues)

    if args.json:
        output = {
            "valid": not has_failures,
            "planes": all_results,
            "all_issues": all_issues,
        }
        print(json.dumps(output, indent=2))
    else:
        print()
        if has_failures:
            print("Chain verification: FAILED")
            return 1
        else:
            print("Chain verification: PASSED")

    return 0 if not has_failures else 1


def cmd_summarize_up(args) -> int:
    """Summarize child ledger entries to parent.

    Creates SUMMARY_UP entries in the parent ledger for each child instance.
    Uses cursor tracking for idempotent incremental processing.
    """
    from datetime import datetime, timezone

    parent_root = Path(args.parent).resolve()

    if not parent_root.exists():
        print(f"Error: Parent directory not found: {parent_root}", file=sys.stderr)
        return 1

    manifest_path = parent_root / "tier.json"
    if not manifest_path.exists():
        print(f"Error: No tier.json found at {parent_root}", file=sys.stderr)
        return 1

    parent_manifest = TierManifest.load(manifest_path)
    parent_client = LedgerFactory.from_tier_root(parent_root)

    # Initialize cursor manager
    cursor_dir = parent_root / "ledger" / "cursors"
    cursor_manager = CursorManager(cursor_dir)

    # Get all child instances
    instances = LedgerFactory.list_instances(parent_root)

    if not instances:
        if not args.json:
            print(f"No instances found under {parent_root}")
        return 0

    total_summarized = 0
    total_skipped = 0
    results = []

    for inst in instances:
        inst_client = LedgerFactory.from_tier_root(inst.tier_root)
        inst_entries = inst_client.read_all()

        # Get cursor range
        from_cursor, to_cursor, was_reset = cursor_manager.get_unprocessed_range(
            inst.absolute_ledger_path,
            len(inst_entries),
            inst_client.get_last_entry_hash_value(),
        )

        if was_reset and not args.json:
            print(f"  Warning: Cursor reset for {inst.tier_root.name} (ledger changed)")

        # Check if there's anything to process
        if from_cursor >= to_cursor:
            total_skipped += 1
            results.append({
                "instance": inst.work_order_id or inst.session_id,
                "status": "skipped",
                "reason": "no_new_entries",
            })
            continue

        # Compute dedupe key
        instance_id = inst.work_order_id or inst.session_id or str(inst.tier_root)
        dedupe_key = compute_dedupe_key(
            str(inst.absolute_ledger_path),
            from_cursor,
            to_cursor,
            inst.tier,
        )

        # Check idempotency
        if parent_client.has_dedupe_key(dedupe_key):
            total_skipped += 1
            results.append({
                "instance": instance_id,
                "status": "skipped",
                "reason": "already_summarized",
            })
            continue

        # Get entries to summarize
        entries_to_summarize = inst_entries[from_cursor:to_cursor]

        # Compute summary statistics
        event_types = {}
        decisions = {}
        for e in entries_to_summarize:
            event_types[e.event_type] = event_types.get(e.event_type, 0) + 1
            decisions[e.decision] = decisions.get(e.decision, 0) + 1

        # Create SUMMARY_UP entry
        summary_entry = LedgerEntry(
            event_type="SUMMARY_UP",
            submission_id=f"SUM-{instance_id}-{from_cursor}-{to_cursor}",
            decision="SUMMARIZED",
            reason=f"Summarized {len(entries_to_summarize)} entries from {instance_id}",
            metadata={
                "_dedupe_key": dedupe_key,
                "source_ledger": str(inst.absolute_ledger_path),
                "child_tier": inst.tier,
                "child_instance_id": instance_id,
                "cursor_from": from_cursor,
                "cursor_to": to_cursor,
                "entry_count": len(entries_to_summarize),
                "event_type_counts": dict(sorted(event_types.items())),
                "decision_counts": dict(sorted(decisions.items())),
                "summarized_at": datetime.now(timezone.utc).isoformat(),
            }
        )

        parent_client.write(summary_entry)
        parent_client.flush()

        # Update cursor
        last_hash = entries_to_summarize[-1].entry_hash if entries_to_summarize else None
        cursor_manager.save(inst.absolute_ledger_path, to_cursor, last_hash)

        total_summarized += 1
        results.append({
            "instance": instance_id,
            "status": "summarized",
            "entries": len(entries_to_summarize),
            "cursor": {"from": from_cursor, "to": to_cursor},
        })

        if not args.json:
            print(f"  Summarized {len(entries_to_summarize)} entries from {instance_id}")

    if args.json:
        output = {
            "parent": str(parent_root),
            "summarized": total_summarized,
            "skipped": total_skipped,
            "results": results,
        }
        print(json.dumps(output, indent=2))
    else:
        print(f"\nSummary: {total_summarized} summarized, {total_skipped} skipped")

    return 0


def cmd_push_policy(args) -> int:
    """Push policy from parent to child instances.

    Creates POLICY_DOWN entries in each child instance's ledger.
    """
    from datetime import datetime, timezone

    parent_root = Path(args.parent).resolve()

    if not parent_root.exists():
        print(f"Error: Parent directory not found: {parent_root}", file=sys.stderr)
        return 1

    manifest_path = parent_root / "tier.json"
    if not manifest_path.exists():
        print(f"Error: No tier.json found at {parent_root}", file=sys.stderr)
        return 1

    parent_manifest = TierManifest.load(manifest_path)

    # Get all child instances
    instances = LedgerFactory.list_instances(parent_root)

    if not instances:
        if not args.json:
            print(f"No instances found under {parent_root}")
        return 0

    total_pushed = 0
    total_skipped = 0
    results = []

    for inst in instances:
        instance_id = inst.work_order_id or inst.session_id or str(inst.tier_root)

        # Compute dedupe key for this policy push
        dedupe_key = compute_policy_push_dedupe_key(args.policy, args.version, instance_id)

        inst_client = LedgerFactory.from_tier_root(inst.tier_root)

        # Check idempotency
        if inst_client.has_dedupe_key(dedupe_key):
            total_skipped += 1
            results.append({
                "instance": instance_id,
                "status": "skipped",
                "reason": "already_pushed",
            })
            continue

        # Create POLICY_DOWN entry
        policy_entry = LedgerEntry(
            event_type="POLICY_DOWN",
            submission_id=f"POL-DOWN-{args.policy}-{instance_id}",
            decision="PUSHED",
            reason=f"Policy {args.policy} v{args.version} pushed from parent",
            metadata={
                "_dedupe_key": dedupe_key,
                "policy_id": args.policy,
                "policy_version": args.version,
                "from_parent": str(parent_root),
                "target_instance": instance_id,
                "pushed_at": datetime.now(timezone.utc).isoformat(),
            }
        )

        inst_client.write(policy_entry)
        inst_client.flush()

        total_pushed += 1
        results.append({
            "instance": instance_id,
            "status": "pushed",
        })

        if not args.json:
            print(f"  Pushed policy to {instance_id}")

    if args.json:
        output = {
            "policy_id": args.policy,
            "version": args.version,
            "pushed": total_pushed,
            "skipped": total_skipped,
            "results": results,
        }
        print(json.dumps(output, indent=2))
    else:
        print(f"\nSummary: {total_pushed} pushed, {total_skipped} skipped")

    return 0


def cmd_apply_policy(args) -> int:
    """Apply a pushed policy in an instance.

    Looks for unapplied POLICY_DOWN entries and creates POLICY_APPLIED entries.
    """
    from datetime import datetime, timezone

    root = Path(args.root).resolve()

    if not root.exists():
        print(f"Error: Directory not found: {root}", file=sys.stderr)
        return 1

    manifest_path = root / "tier.json"
    if not manifest_path.exists():
        print(f"Error: No tier.json found at {root}", file=sys.stderr)
        return 1

    manifest = TierManifest.load(manifest_path)
    instance_id = manifest.work_order_id or manifest.session_id or str(root)
    client = LedgerFactory.from_tier_root(root)

    # Find all POLICY_DOWN entries
    entries = client.read_all()
    policy_downs = [e for e in entries if e.event_type == "POLICY_DOWN"]

    if not policy_downs:
        if not args.json:
            print(f"No policies to apply in {root}")
        return 0

    # Find already applied policies
    applied = {
        e.metadata.get("policy_id") + ":" + e.metadata.get("policy_version", "")
        for e in entries if e.event_type == "POLICY_APPLIED"
    }

    total_applied = 0
    total_skipped = 0
    results = []

    for policy_entry in policy_downs:
        policy_id = policy_entry.metadata.get("policy_id", "unknown")
        policy_version = policy_entry.metadata.get("policy_version", "unknown")
        policy_key = f"{policy_id}:{policy_version}"

        # Check if already applied
        if policy_key in applied:
            total_skipped += 1
            results.append({
                "policy_id": policy_id,
                "version": policy_version,
                "status": "skipped",
                "reason": "already_applied",
            })
            continue

        # Compute dedupe key
        dedupe_key = compute_policy_apply_dedupe_key(policy_id, policy_version, instance_id)

        # Double-check idempotency via dedupe key
        if client.has_dedupe_key(dedupe_key):
            total_skipped += 1
            results.append({
                "policy_id": policy_id,
                "version": policy_version,
                "status": "skipped",
                "reason": "dedupe_key_exists",
            })
            continue

        # Create POLICY_APPLIED entry
        applied_entry = LedgerEntry(
            event_type="POLICY_APPLIED",
            submission_id=f"POL-APPLY-{policy_id}-{instance_id}",
            decision="APPLIED",
            reason=f"Policy {policy_id} v{policy_version} applied successfully",
            metadata={
                "_dedupe_key": dedupe_key,
                "policy_id": policy_id,
                "policy_version": policy_version,
                "instance_id": instance_id,
                "from_parent": policy_entry.metadata.get("from_parent"),
                "applied_at": datetime.now(timezone.utc).isoformat(),
                "result": "success",
            }
        )

        client.write(applied_entry)
        client.flush()

        total_applied += 1
        results.append({
            "policy_id": policy_id,
            "version": policy_version,
            "status": "applied",
        })

        if not args.json:
            print(f"  Applied policy {policy_id} v{policy_version}")

    if args.json:
        output = {
            "instance": instance_id,
            "applied": total_applied,
            "skipped": total_skipped,
            "results": results,
        }
        print(json.dumps(output, indent=2))
    else:
        print(f"\nSummary: {total_applied} applied, {total_skipped} skipped")

    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Plane lifecycle management",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # create
    p_create = subparsers.add_parser("create", help="Create a new plane root")
    p_create.add_argument(
        "--tier",
        required=True,
        choices=["HO3", "HO2", "HO1", "HOT", "SECOND", "FIRST"],
        help="Tier type (canonical: HO3, HO2, HO1; legacy: HOT, SECOND, FIRST)"
    )
    p_create.add_argument("--root", required=True, help="Plane root directory")
    p_create.add_argument("--parent", help="Parent ledger path/URI")
    p_create.add_argument("--ledger-name", help="Custom ledger filename")
    p_create.add_argument(
        "--seed-registries",
        action="store_true",
        help="Create empty registry CSV files"
    )
    p_create.set_defaults(func=cmd_create)

    # list
    p_list = subparsers.add_parser("list", help="List all configured planes")
    p_list.add_argument("--json", action="store_true", help="Output as JSON")
    p_list.set_defaults(func=cmd_list)

    # info
    p_info = subparsers.add_parser("info", help="Show plane information")
    p_info.add_argument("--root", required=True, help="Plane root directory")
    p_info.add_argument("--json", action="store_true", help="Output as JSON")
    p_info.set_defaults(func=cmd_info)

    # init-chain
    p_init = subparsers.add_parser("init-chain", help="Initialize chain config from existing planes")
    p_init.add_argument("--ho3", help="HO3 (highest privilege) plane root")
    p_init.add_argument("--ho2", help="HO2 (middle tier) plane root")
    p_init.add_argument("--ho1", help="HO1 (lowest tier) plane root")
    p_init.add_argument("--force", action="store_true", help="Overwrite existing config without backup")
    p_init.set_defaults(func=cmd_init_chain)

    # verify
    p_verify = subparsers.add_parser("verify", help="Verify plane integrity")
    p_verify.add_argument("--root", required=True, help="Plane root directory")
    p_verify.add_argument("--json", action="store_true", help="Output as JSON")
    p_verify.set_defaults(func=cmd_verify)

    # create-work-order
    p_wo = subparsers.add_parser("create-work-order", help="Create a work-order instance under HO2")
    p_wo.add_argument("--id", required=True, help="Work order ID (e.g., WO-2026-001)")
    p_wo.add_argument("--base", required=True, help="Base HO2 plane root")
    p_wo.set_defaults(func=cmd_create_work_order)

    # create-session
    p_sess = subparsers.add_parser("create-session", help="Create a session instance under HO1")
    p_sess.add_argument("--id", required=True, help="Session ID (e.g., sess-001)")
    p_sess.add_argument("--base", required=True, help="Base HO1 plane root")
    p_sess.set_defaults(func=cmd_create_session)

    # list-instances
    p_list_inst = subparsers.add_parser("list-instances", help="List instances under a base plane")
    p_list_inst.add_argument("--base", required=True, help="Base plane root")
    p_list_inst.add_argument("--json", action="store_true", help="Output as JSON")
    p_list_inst.set_defaults(func=cmd_list_instances)

    # verify-chain
    p_verify_chain = subparsers.add_parser("verify-chain", help="Verify full chain hierarchy")
    p_verify_chain.add_argument("--root", required=True, help="Plane root to verify from")
    p_verify_chain.add_argument("--json", action="store_true", help="Output as JSON")
    p_verify_chain.set_defaults(func=cmd_verify_chain)

    # summarize-up
    p_summarize = subparsers.add_parser(
        "summarize-up",
        help="Summarize child ledger entries to parent",
        description="""
Summarizes entries from child instance ledgers into the parent ledger.
Uses cursor tracking for incremental, idempotent processing.

Example:
    cp_plane.py summarize-up --parent ./planes/ho2

The command:
1. Finds all work_orders/sessions under the parent
2. For each instance, reads new entries since last cursor
3. Creates a SUMMARY_UP entry in the parent ledger
4. Updates the cursor atomically

Running twice with no new child entries produces no new entries (idempotent).
""",
    )
    p_summarize.add_argument("--parent", required=True, help="Parent plane root")
    p_summarize.add_argument("--recursive", action="store_true", help="Recursively summarize nested instances")
    p_summarize.add_argument("--json", action="store_true", help="Output as JSON")
    p_summarize.set_defaults(func=cmd_summarize_up)

    # push-policy
    p_push = subparsers.add_parser(
        "push-policy",
        help="Push policy from parent to child instances",
        description="""
Pushes a policy configuration from parent to all child instances.
Creates POLICY_DOWN entries in each child's ledger.

Example:
    cp_plane.py push-policy --policy POL-ATTENTION-001 --version 1.0 --parent ./planes/ho2

The command:
1. Finds all work_orders/sessions under the parent
2. For each instance, creates a POLICY_DOWN entry if not already pushed
3. Idempotent: running twice does nothing on second run
""",
    )
    p_push.add_argument("--policy", required=True, help="Policy ID (e.g., POL-ATTENTION-001)")
    p_push.add_argument("--version", required=True, help="Policy version (e.g., 1.0)")
    p_push.add_argument("--parent", required=True, help="Parent plane root")
    p_push.add_argument("--json", action="store_true", help="Output as JSON")
    p_push.set_defaults(func=cmd_push_policy)

    # apply-policy
    p_apply = subparsers.add_parser(
        "apply-policy",
        help="Apply a pushed policy in an instance",
        description="""
Applies any unapplied policies in an instance.
Creates POLICY_APPLIED entries for each applied policy.

Example:
    cp_plane.py apply-policy --root ./planes/ho2/work_orders/WO-001

The command:
1. Finds all POLICY_DOWN entries in the instance ledger
2. For each policy not yet applied, creates a POLICY_APPLIED entry
3. Idempotent: running twice does nothing on second run
""",
    )
    p_apply.add_argument("--root", required=True, help="Instance root to apply policies in")
    p_apply.add_argument("--json", action="store_true", help="Output as JSON")
    p_apply.set_defaults(func=cmd_apply_policy)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
