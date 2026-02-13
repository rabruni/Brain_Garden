#!/usr/bin/env python3
"""
materialize_layout.py - Create tier directory trees from layout.json.

Reads HOT/config/layout.json and creates the directory structure for
each tier defined in the tiers map. Config-driven — tier names and
subdirectory names come from layout.json, not hardcoded.

Usage:
    python3 materialize_layout.py --root <plane_root>

If --root is omitted, uses CONTROL_PLANE_ROOT env var.

Exit codes:
    0: success (including "nothing to do")
    1: layout.json not found or invalid
    2: permission error creating directories
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def load_layout_config(plane_root: Path) -> dict:
    """Load layout.json from HOT/config/layout.json under plane_root.

    Args:
        plane_root: Path to the control plane root.

    Returns:
        Parsed layout config dict.

    Raises:
        FileNotFoundError: If layout.json does not exist.
        json.JSONDecodeError: If layout.json is invalid JSON.
    """
    layout_path = plane_root / "HOT" / "config" / "layout.json"
    if not layout_path.exists():
        raise FileNotFoundError(f"layout.json not found at {layout_path}")
    return json.loads(layout_path.read_text())


def materialize(plane_root: Path) -> int:
    """Create tier directory trees from layout.json.

    Args:
        plane_root: Path to the control plane root.

    Returns:
        0 on success, 1 on config error, 2 on permission error.
    """
    try:
        config = load_layout_config(plane_root)
    except FileNotFoundError as e:
        print(f"[materialize] ERROR: {e}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as e:
        print(f"[materialize] ERROR: Invalid JSON in layout.json: {e}", file=sys.stderr)
        return 1

    tiers = config.get("tiers", {})
    tier_dirs = config.get("tier_dirs", {})
    hot_dirs = config.get("hot_dirs", {})

    print(f"[materialize] Reading layout from HOT/config/layout.json")

    total_created = 0
    total_existed = 0

    try:
        for tier_name, tier_dir_name in tiers.items():
            tier_root = plane_root / tier_dir_name
            dirs_created = 0
            dirs_existed = 0

            # Create tier_dirs subdirectories for every tier
            for _key, subdir_name in tier_dirs.items():
                subdir_path = tier_root / subdir_name
                if subdir_path.is_dir():
                    dirs_existed += 1
                else:
                    subdir_path.mkdir(parents=True, exist_ok=True)
                    dirs_created += 1

            # For HOT tier, also create the hot_dirs directories
            if tier_name == "HOT":
                for _key, hot_dir_rel in hot_dirs.items():
                    hot_dir_path = plane_root / hot_dir_rel
                    if hot_dir_path.is_dir():
                        dirs_existed += 1
                    else:
                        hot_dir_path.mkdir(parents=True, exist_ok=True)
                        dirs_created += 1

            tier_total = dirs_created + dirs_existed
            print(f"[materialize] Tier {tier_name}: {tier_total} dirs "
                  f"({dirs_existed} exist, {dirs_created} created)")

            total_created += dirs_created
            total_existed += dirs_existed

    except PermissionError as e:
        print(f"[materialize] ERROR: Permission denied: {e}", file=sys.stderr)
        return 2

    print(f"[materialize] Done: {total_created} directories created, "
          f"{total_existed} already existed")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Materialize tier directory trees from layout.json"
    )
    parser.add_argument(
        "--root", type=Path, default=None,
        help="Plane root path (defaults to CONTROL_PLANE_ROOT env var)"
    )
    args = parser.parse_args()

    if args.root is not None:
        plane_root = args.root.resolve()
    else:
        env_root = os.getenv("CONTROL_PLANE_ROOT")
        if env_root:
            plane_root = Path(env_root).resolve()
        else:
            print("[materialize] ERROR: No --root specified and "
                  "CONTROL_PLANE_ROOT not set", file=sys.stderr)
            return 1

    return materialize(plane_root)


if __name__ == "__main__":
    raise SystemExit(main())
