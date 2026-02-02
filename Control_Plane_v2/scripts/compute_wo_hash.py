#!/usr/bin/env python3
"""
compute_wo_hash.py - Compute deterministic hash of Work Order payload.

Implements the canonicalization algorithm specified in FMWK-000:
1. Keys sorted alphabetically (recursive)
2. No trailing whitespace
3. UTF-8 encoding
4. No BOM
5. Newline-terminated (for canonical form only)

The hash is computed BEFORE execution and is used for idempotency:
- Same (work_order_id, wo_payload_hash) = NO-OP (idempotent)
- Same work_order_id + different hash = FAIL (tampering)

Usage:
    python3 scripts/compute_wo_hash.py --wo work_orders/ho3/WO-20260201-001.json
    python3 scripts/compute_wo_hash.py --wo WO-20260201-001  # Auto-discovers path
    python3 scripts/compute_wo_hash.py --wo work_orders/ho3/WO-20260201-001.json --verify <expected_hash>
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

# Add parent to path for lib imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.paths import CONTROL_PLANE


def canonicalize_wo(wo_path: Path) -> str:
    """Return canonical JSON string for hashing.

    Canonicalization rules:
    - Keys sorted alphabetically (recursive)
    - Compact separators (',', ':')
    - UTF-8 encoding
    - No trailing whitespace

    Args:
        wo_path: Path to Work Order JSON file

    Returns:
        Canonical JSON string

    Raises:
        FileNotFoundError: If file doesn't exist
        json.JSONDecodeError: If file is not valid JSON
    """
    with open(wo_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Recursively sort keys and produce compact JSON
    return json.dumps(data, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def compute_wo_payload_hash(wo_path: Path) -> str:
    """Compute deterministic hash of Work Order payload.

    Args:
        wo_path: Path to Work Order JSON file

    Returns:
        SHA256 hex digest of canonicalized JSON
    """
    canonical = canonicalize_wo(wo_path)
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def discover_wo_path(wo_id: str, plane_root: Path = CONTROL_PLANE) -> Path:
    """Discover Work Order file path from ID.

    Searches work_orders/{ho3,ho2,ho1}/ directories.

    Args:
        wo_id: Work Order ID (e.g., WO-20260201-001)
        plane_root: Root of the control plane

    Returns:
        Path to Work Order file

    Raises:
        FileNotFoundError: If no matching file found
    """
    # Check if it's already a path
    if '/' in wo_id or wo_id.endswith('.json'):
        path = plane_root / wo_id.lstrip('/')
        if path.exists():
            return path
        raise FileNotFoundError(f"Work Order file not found: {path}")

    # Search for ID in work_orders directories
    for plane_id in ['ho3', 'ho2', 'ho1']:
        wo_path = plane_root / 'work_orders' / plane_id / f"{wo_id}.json"
        if wo_path.exists():
            return wo_path

    raise FileNotFoundError(
        f"Work Order {wo_id} not found in work_orders/{{ho3,ho2,ho1}}/\n"
        f"Expected: work_orders/<plane>/{wo_id}.json"
    )


def main():
    parser = argparse.ArgumentParser(
        description="Compute deterministic hash of Work Order payload"
    )
    parser.add_argument(
        "--wo", "-w",
        required=True,
        help="Work Order ID or path (e.g., WO-20260201-001 or work_orders/ho3/WO-20260201-001.json)"
    )
    parser.add_argument(
        "--verify", "-v",
        help="Verify computed hash matches expected hash"
    )
    parser.add_argument(
        "--show-canonical", "-c",
        action="store_true",
        help="Also show the canonicalized JSON"
    )
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output as JSON"
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=CONTROL_PLANE,
        help="Plane root path"
    )

    args = parser.parse_args()

    try:
        # Discover and validate path
        wo_path = discover_wo_path(args.wo, args.root)

        # Compute hash
        computed_hash = compute_wo_payload_hash(wo_path)
        canonical_json = canonicalize_wo(wo_path) if args.show_canonical else None

        # Verify if requested
        if args.verify:
            match = computed_hash.lower() == args.verify.lower()
            if args.json:
                output = {
                    "work_order_path": str(wo_path),
                    "wo_payload_hash": computed_hash,
                    "expected_hash": args.verify,
                    "match": match
                }
                if args.show_canonical:
                    output["canonical_json"] = canonical_json
                print(json.dumps(output, indent=2))
            else:
                print(f"Path: {wo_path}")
                print(f"Computed: {computed_hash}")
                print(f"Expected: {args.verify}")
                print(f"Match: {'YES' if match else 'NO - TAMPERING DETECTED'}")
                if args.show_canonical:
                    print(f"\nCanonical JSON:\n{canonical_json}")

            return 0 if match else 1

        # Normal output
        if args.json:
            output = {
                "work_order_path": str(wo_path),
                "wo_payload_hash": computed_hash
            }
            if args.show_canonical:
                output["canonical_json"] = canonical_json
            print(json.dumps(output, indent=2))
        else:
            print(f"wo_payload_hash={computed_hash}")
            if args.show_canonical:
                print(f"\nCanonical JSON:\n{canonical_json}")

        return 0

    except FileNotFoundError as e:
        if args.json:
            print(json.dumps({"error": str(e)}))
        else:
            print(f"Error: {e}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as e:
        if args.json:
            print(json.dumps({"error": f"Invalid JSON: {e}"}))
        else:
            print(f"Error: Invalid JSON in Work Order: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        if args.json:
            print(json.dumps({"error": str(e)}))
        else:
            print(f"Error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
