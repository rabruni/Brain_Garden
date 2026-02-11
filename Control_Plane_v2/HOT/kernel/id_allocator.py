#!/usr/bin/env python3
"""
id_allocator.py - ID Allocation (LIB-015)

Allocates sequential IDs for new artifacts based on entity type prefix.
Scans control_plane_registry.csv to find the next available ID.

Usage:
    from kernel.id_allocator import allocate_id

    new_id = allocate_id("SCRIPT")  # Returns "SCRIPT-024" (next available)
    new_id = allocate_id("LIB")     # Returns "LIB-016" (next available)
"""

import csv
import re
from pathlib import Path
from typing import Dict, Set

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kernel.paths import REGISTRIES_DIR


def get_existing_ids() -> Set[str]:
    """Load all existing IDs from control_plane_registry.csv."""
    registry_path = REGISTRIES_DIR / "control_plane_registry.csv"

    if not registry_path.exists():
        return set()

    ids = set()
    with open(registry_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            artifact_id = row.get("id", "").strip()
            if artifact_id:
                ids.add(artifact_id)

    return ids


def extract_prefix_and_number(artifact_id: str) -> tuple:
    """Extract prefix and numeric part from an ID.

    Args:
        artifact_id: ID like "SCRIPT-006" or "LIB-003"

    Returns:
        Tuple of (prefix, number) or (None, None) if not parseable
    """
    match = re.match(r"^([A-Z]+-?)(\d+)$", artifact_id)
    if match:
        prefix = match.group(1)
        number = int(match.group(2))
        return prefix, number
    return None, None


def get_max_number_for_prefix(prefix: str, existing_ids: Set[str]) -> int:
    """Find the highest number used for a given prefix.

    Args:
        prefix: ID prefix like "SCRIPT-" or "LIB-"
        existing_ids: Set of all existing IDs

    Returns:
        Highest number found, or 0 if none exist
    """
    max_num = 0

    for artifact_id in existing_ids:
        id_prefix, id_num = extract_prefix_and_number(artifact_id)
        if id_prefix == prefix and id_num is not None:
            max_num = max(max_num, id_num)

    return max_num


def allocate_id(prefix: str) -> str:
    """Allocate the next available ID for a given prefix.

    Args:
        prefix: Entity type prefix (e.g., "SCRIPT", "LIB", "FMWK")
                Can include or exclude the trailing hyphen.

    Returns:
        Next available ID (e.g., "SCRIPT-024")

    Example:
        >>> allocate_id("SCRIPT")
        'SCRIPT-024'
        >>> allocate_id("LIB")
        'LIB-016'
    """
    # Normalize prefix to include hyphen
    if not prefix.endswith("-"):
        prefix = prefix + "-"

    existing_ids = get_existing_ids()
    max_num = get_max_number_for_prefix(prefix, existing_ids)

    next_num = max_num + 1

    # Format with 3 digits, padded with zeros
    return f"{prefix}{next_num:03d}"


def preview_allocations(prefixes: list) -> Dict[str, str]:
    """Preview what IDs would be allocated for multiple prefixes.

    Args:
        prefixes: List of prefixes to allocate

    Returns:
        Dict mapping prefix to allocated ID
    """
    existing_ids = get_existing_ids()
    result = {}

    for prefix in prefixes:
        if not prefix.endswith("-"):
            prefix_normalized = prefix + "-"
        else:
            prefix_normalized = prefix

        max_num = get_max_number_for_prefix(prefix_normalized, existing_ids)
        next_id = f"{prefix_normalized}{max_num + 1:03d}"
        result[prefix] = next_id

    return result


__all__ = [
    "allocate_id",
    "get_existing_ids",
    "preview_allocations",
]


if __name__ == "__main__":
    # Demo: show next available IDs for common types
    prefixes = ["SCRIPT", "LIB", "FMWK", "SPEC", "PROMPT", "SCHEMA", "REG"]
    print("Next available IDs:")
    print("-" * 30)
    for prefix, next_id in preview_allocations(prefixes).items():
        print(f"  {prefix}: {next_id}")
