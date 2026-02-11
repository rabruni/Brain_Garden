#!/usr/bin/env python3
"""
rebuild_derived.py - Rebuild derived registries from authoritative sources.

Derived registries are NEVER directly edited. They are rebuilt from:
- Curated registries (control_plane_registry.csv, specs_registry.csv, etc.)
- Ledger entries (packages.jsonl, governance.jsonl)
- Package manifests

This enforces the registry hygiene policy from FMWK-000:
- Curated registries: WO-only mutation
- Derived registries: rebuild-only

Usage:
    # Rebuild all derived registries
    python3 scripts/rebuild_derived.py

    # Rebuild specific registry
    python3 scripts/rebuild_derived.py --registry packages
    python3 scripts/rebuild_derived.py --registry file_ownership

    # Dry run (show what would be written)
    python3 scripts/rebuild_derived.py --dry-run

    # Verify derived registries match sources (no writes)
    python3 scripts/rebuild_derived.py --verify
"""

import argparse
import csv
import hashlib
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any

# Add parent to path for lib imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "HOT"))

from kernel.paths import CONTROL_PLANE


@dataclass
class RebuildResult:
    """Result of a registry rebuild."""
    registry: str
    success: bool
    message: str
    records_written: int = 0
    source_records: int = 0
    changes_detected: bool = False
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "registry": self.registry,
            "success": self.success,
            "message": self.message,
            "records_written": self.records_written,
            "source_records": self.source_records,
            "changes_detected": self.changes_detected,
            "errors": self.errors,
        }


def load_registry_policy(plane_root: Path) -> dict:
    """Load registry policy from config/registry_policy.json."""
    policy_path = plane_root / 'config' / 'registry_policy.json'
    if not policy_path.exists():
        return {"curated": [], "derived": []}

    with open(policy_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_packages_ledger(plane_root: Path) -> List[dict]:
    """Load entries from packages.jsonl ledger."""
    ledger_path = plane_root / 'ledger' / 'packages.jsonl'
    entries = []

    if ledger_path.exists():
        with open(ledger_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass

    return entries


def load_file_ownership_csv(plane_root: Path) -> List[dict]:
    """Load file_ownership.csv registry."""
    csv_path = plane_root / 'registries' / 'file_ownership.csv'
    if not csv_path.exists():
        return []

    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        return list(reader)


def load_packages_state_csv(plane_root: Path) -> List[dict]:
    """Load packages_state.csv registry."""
    csv_path = plane_root / 'registries' / 'packages_state.csv'
    if not csv_path.exists():
        return []

    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        return list(reader)


def compute_json_hash(data: Any) -> str:
    """Compute hash of JSON-serialized data."""
    json_str = json.dumps(data, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(json_str.encode('utf-8')).hexdigest()


def rebuild_packages_json(plane_root: Path, dry_run: bool = False) -> RebuildResult:
    """Rebuild registries/compiled/packages.json from sources.

    Sources:
    - packages_state.csv (primary)
    - ledger/packages.jsonl (for additional metadata)
    """
    output_path = plane_root / 'registries' / 'compiled' / 'packages.json'
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Load sources
    packages_state = load_packages_state_csv(plane_root)
    packages_ledger = load_packages_ledger(plane_root)

    # Build package index from packages_state.csv
    packages = {}
    for row in packages_state:
        pkg_id = row.get('package_id', '')
        if pkg_id:
            packages[pkg_id] = {
                'package_id': pkg_id,
                'spec_id': row.get('spec_id', ''),
                'version': row.get('version', ''),
                'status': row.get('status', 'unknown'),
                'installed_at': row.get('installed_at', ''),
                'installed_by_wo': row.get('installed_by_wo', ''),
                'content_hash': row.get('content_hash', ''),
            }

    # Enrich with ledger data if available
    for entry in packages_ledger:
        pkg_id = entry.get('metadata', {}).get('package_id', '')
        if pkg_id and pkg_id in packages:
            # Add ledger metadata
            packages[pkg_id]['ledger_entry_id'] = entry.get('id')

    # Build output structure
    output_data = {
        'schema_version': '1.0',
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'source': 'registries/packages_state.csv + ledger/packages.jsonl',
        'packages': packages,
        'package_count': len(packages),
    }

    # Check if changes detected
    changes_detected = True
    if output_path.exists():
        with open(output_path, 'r', encoding='utf-8') as f:
            existing = json.load(f)
            # Compare packages only (not generated_at)
            if existing.get('packages') == packages:
                changes_detected = False

    if dry_run:
        return RebuildResult(
            registry='packages.json',
            success=True,
            message='Dry run - no changes written',
            records_written=0,
            source_records=len(packages_state),
            changes_detected=changes_detected
        )

    # Write output
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2)

    return RebuildResult(
        registry='packages.json',
        success=True,
        message=f'Rebuilt with {len(packages)} packages',
        records_written=len(packages),
        source_records=len(packages_state),
        changes_detected=changes_detected
    )


def rebuild_file_ownership_json(plane_root: Path, dry_run: bool = False) -> RebuildResult:
    """Rebuild registries/compiled/file_ownership.json from file_ownership.csv."""
    output_path = plane_root / 'registries' / 'compiled' / 'file_ownership.json'
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Load source
    file_ownership = load_file_ownership_csv(plane_root)

    # Build file index
    files = {}
    for row in file_ownership:
        file_path = row.get('file_path', '')
        if file_path:
            files[file_path] = {
                'file_path': file_path,
                'owner_package_id': row.get('owner_package_id', ''),
                'content_hash': row.get('content_hash', ''),
                'status': row.get('status', 'active'),
                'registered_at': row.get('registered_at', ''),
                'registered_by_wo': row.get('registered_by_wo', ''),
            }

    # Build output structure
    output_data = {
        'schema_version': '1.0',
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'source': 'registries/file_ownership.csv',
        'files': files,
        'file_count': len(files),
    }

    # Check if changes detected
    changes_detected = True
    if output_path.exists():
        with open(output_path, 'r', encoding='utf-8') as f:
            existing = json.load(f)
            if existing.get('files') == files:
                changes_detected = False

    if dry_run:
        return RebuildResult(
            registry='file_ownership.json',
            success=True,
            message='Dry run - no changes written',
            records_written=0,
            source_records=len(file_ownership),
            changes_detected=changes_detected
        )

    # Write output
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2)

    return RebuildResult(
        registry='file_ownership.json',
        success=True,
        message=f'Rebuilt with {len(files)} files',
        records_written=len(files),
        source_records=len(file_ownership),
        changes_detected=changes_detected
    )


def verify_derived_registry(registry_name: str, plane_root: Path) -> RebuildResult:
    """Verify a derived registry matches its sources without writing.

    Returns success if derived registry is in sync with sources.
    """
    if registry_name == 'packages' or registry_name == 'packages.json':
        result = rebuild_packages_json(plane_root, dry_run=True)
    elif registry_name == 'file_ownership' or registry_name == 'file_ownership.json':
        result = rebuild_file_ownership_json(plane_root, dry_run=True)
    else:
        return RebuildResult(
            registry=registry_name,
            success=False,
            message=f"Unknown registry: {registry_name}",
            errors=[f"Registry '{registry_name}' not recognized"]
        )

    if result.changes_detected:
        result.success = False
        result.message = "Derived registry out of sync with sources"
        result.errors.append("Run: python3 scripts/rebuild_derived.py to sync")

    return result


def rebuild_all(plane_root: Path, dry_run: bool = False, verify: bool = False) -> List[RebuildResult]:
    """Rebuild all derived registries."""
    results = []

    # Load policy to get list of derived registries
    policy = load_registry_policy(plane_root)
    derived_registries = policy.get('derived', [
        'registries/compiled/packages.json',
        'registries/compiled/file_ownership.json'
    ])

    for reg_path in derived_registries:
        reg_name = Path(reg_path).stem

        if verify:
            result = verify_derived_registry(reg_name, plane_root)
        elif 'packages' in reg_name:
            result = rebuild_packages_json(plane_root, dry_run)
        elif 'file_ownership' in reg_name:
            result = rebuild_file_ownership_json(plane_root, dry_run)
        else:
            result = RebuildResult(
                registry=reg_name,
                success=False,
                message=f"No rebuild handler for {reg_name}",
                errors=[f"Unknown derived registry: {reg_path}"]
            )

        results.append(result)

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Rebuild derived registries from authoritative sources"
    )
    parser.add_argument(
        "--registry", "-r",
        type=str,
        choices=['packages', 'file_ownership', 'all'],
        default='all',
        help="Which registry to rebuild"
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=CONTROL_PLANE,
        help="Control plane root path"
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Show what would be written without making changes"
    )
    parser.add_argument(
        "--verify", "-v",
        action="store_true",
        help="Verify derived registries match sources (no writes)"
    )
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output as JSON"
    )

    args = parser.parse_args()

    if args.registry == 'all':
        results = rebuild_all(args.root, args.dry_run, args.verify)
    elif args.verify:
        results = [verify_derived_registry(args.registry, args.root)]
    elif args.registry == 'packages':
        results = [rebuild_packages_json(args.root, args.dry_run)]
    elif args.registry == 'file_ownership':
        results = [rebuild_file_ownership_json(args.root, args.dry_run)]
    else:
        results = []

    if args.json:
        print(json.dumps([r.to_dict() for r in results], indent=2))
    else:
        mode = "VERIFY" if args.verify else ("DRY RUN" if args.dry_run else "REBUILD")
        print(f"\nDerived Registry {mode}")
        print("=" * 50)

        all_success = True
        for result in results:
            status = "OK" if result.success else "FAIL"
            changes = " (changes detected)" if result.changes_detected else ""
            print(f"\n{result.registry}: {status}{changes}")
            print(f"  {result.message}")
            print(f"  Source records: {result.source_records}")
            if not args.verify:
                print(f"  Records written: {result.records_written}")

            if result.errors:
                for e in result.errors:
                    print(f"  ERROR: {e}")

            if not result.success:
                all_success = False

        print()
        return 0 if all_success else 1


if __name__ == "__main__":
    sys.exit(main())
