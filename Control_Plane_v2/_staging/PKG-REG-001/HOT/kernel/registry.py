#!/usr/bin/env python3
"""
Registry operations - CRUD and lookup utilities.

Plane-Aware:
    Functions accept an optional `plane` parameter (PlaneContext).
    When provided, operations are scoped to that plane's root instead of
    the global CONTROL_PLANE singleton.

Lookup helpers (framework_exists, spec_exists, etc.) accept either:
    - registries_dir: Path  — direct path to registries/ directory
    - plane: PlaneContext    — derives registries_dir from plane.root
    - neither               — uses default REGISTRIES_DIR
"""
import csv
from pathlib import Path
from typing import Optional, List, Dict, Tuple, TYPE_CHECKING

from .paths import CONTROL_PLANE, REGISTRIES_DIR, REPO_ROOT

if TYPE_CHECKING:
    from kernel.plane import PlaneContext


def _get_plane_paths(plane: Optional["PlaneContext"] = None) -> Tuple[Path, Path]:
    """Get the control plane root and registries dir for a plane.

    Args:
        plane: Optional PlaneContext to use

    Returns:
        Tuple of (root, registries_dir)
    """
    if plane is not None:
        return plane.root, plane.root / "registries"
    return CONTROL_PLANE, REGISTRIES_DIR


def find_all_registries(plane: Optional["PlaneContext"] = None) -> List[Path]:
    """Find all CSV registries in the control plane.

    Searches:
    - registries/*.csv
    - modules/**/registries/*.csv
    - init/init_registry.csv
    - boot_os_registry.csv

    Args:
        plane: Optional PlaneContext to scope the search (uses plane.root)

    Returns:
        Sorted list of registry paths found
    """
    root, registries_dir = _get_plane_paths(plane)
    registries = []

    # Root registries
    if registries_dir.is_dir():
        registries.extend(registries_dir.glob("*.csv"))

    # Module registries
    modules_dir = root / "modules"
    if modules_dir.is_dir():
        registries.extend(modules_dir.glob("**/registries/*.csv"))

    # Init registry
    init_reg = root / "init" / "init_registry.csv"
    if init_reg.is_file():
        registries.append(init_reg)

    # Boot OS registry
    boot_reg = root / "boot_os_registry.csv"
    if boot_reg.is_file():
        registries.append(boot_reg)

    return sorted(registries)


def read_registry(reg_path: Path) -> Tuple[List[str], List[Dict[str, str]]]:
    """Read a registry CSV and return (headers, rows)."""
    if not reg_path.is_file():
        return [], []
    with open(reg_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        rows = list(reader)
    return headers, rows


def write_registry(reg_path: Path, headers: List[str], rows: List[Dict[str, str]]):
    """Write rows back to a registry CSV."""
    with open(reg_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def get_id_column(headers: List[str]) -> Optional[str]:
    """Find the ID column (id or ends with _id)."""
    if "id" in headers:
        return "id"
    for h in headers:
        if h.endswith("_id"):
            return h
    return None


def find_item(
    query: str,
    plane: Optional["PlaneContext"] = None,
) -> Optional[Tuple[Dict, Path, int]]:
    """Find an item by ID or NAME across all registries.

    Returns (row, registry_path, row_index) or None.

    Lookup order (per SYSTEM_CONSTITUTION.md - ID is primary key):
    1. Exact ID match (case-insensitive)
    2. Exact name match (case-insensitive)
    3. Partial name match (contains)

    Note: While ID is the primary key per constitution, we support
    name lookup for human convenience.

    Args:
        query: ID or name to search for
        plane: Optional PlaneContext to scope the search (uses plane.root)

    Returns:
        Tuple of (row, registry_path, row_index) or None if not found
    """
    registries = find_all_registries(plane=plane)
    query_lower = query.lower().strip()
    query_upper = query.upper().strip()

    # First pass: exact ID match
    for reg_path in registries:
        try:
            headers, rows = read_registry(reg_path)
            id_col = get_id_column(headers)
            if not id_col:
                continue
            for idx, row in enumerate(rows):
                if row.get(id_col, "").strip().upper() == query_upper:
                    return (row, reg_path, idx)
        except Exception:
            continue

    # Second pass: exact name match
    for reg_path in registries:
        try:
            headers, rows = read_registry(reg_path)
            for idx, row in enumerate(rows):
                name = row.get("name", "").strip()
                if name.lower() == query_lower:
                    return (row, reg_path, idx)
        except Exception:
            continue

    # Third pass: partial name match
    for reg_path in registries:
        try:
            headers, rows = read_registry(reg_path)
            for idx, row in enumerate(rows):
                name = row.get("name", "").strip()
                if query_lower in name.lower():
                    return (row, reg_path, idx)
        except Exception:
            continue

    return None


def find_registry_by_name(
    name: str,
    plane: Optional["PlaneContext"] = None,
) -> Optional[Path]:
    """Find a registry by partial name match.

    Args:
        name: Partial name to search for
        plane: Optional PlaneContext to scope the search (uses plane.root)

    Returns:
        Path to the registry, or None if not found
    """
    registries = find_all_registries(plane=plane)
    name_lower = name.lower()

    for reg in registries:
        if name_lower in reg.name.lower():
            return reg

    return None


def count_registry_stats(plane: Optional["PlaneContext"] = None) -> Dict[str, int]:
    """Count items by status across all registries.

    Args:
        plane: Optional PlaneContext to scope the count (uses plane.root)

    Returns:
        Dictionary with registry stats
    """
    stats = {
        "registries": 0,
        "total": 0,
        "selected": 0,
        "active": 0,
        "missing": 0,
        "draft": 0,
        "deprecated": 0,
    }

    registries = find_all_registries(plane=plane)
    stats["registries"] = len(registries)

    for reg_path in registries:
        try:
            _, rows = read_registry(reg_path)
            for row in rows:
                stats["total"] += 1
                selected = row.get("selected", "").strip().lower()
                status = row.get("status", "").strip().lower()

                if selected == "yes":
                    stats["selected"] += 1
                if status == "active":
                    stats["active"] += 1
                elif status == "missing":
                    stats["missing"] += 1
                elif status == "draft":
                    stats["draft"] += 1
                elif status == "deprecated":
                    stats["deprecated"] += 1
        except Exception:
            continue

    return stats


# =============================================================================
# Registry Lookup Helpers
# =============================================================================

def _resolve_registries_dir(
    registries_dir: Optional[Path] = None,
    plane: Optional["PlaneContext"] = None,
) -> Path:
    """Resolve the registries directory from available context."""
    if registries_dir is not None:
        return registries_dir
    _, reg_dir = _get_plane_paths(plane)
    return reg_dir


def framework_exists(
    framework_id: str,
    registries_dir: Optional[Path] = None,
    plane: Optional["PlaneContext"] = None,
) -> bool:
    """Check if framework exists in frameworks_registry.csv."""
    reg_path = _resolve_registries_dir(registries_dir, plane) / "frameworks_registry.csv"
    if not reg_path.is_file():
        return False
    _, rows = read_registry(reg_path)
    return any(row.get("framework_id") == framework_id for row in rows)


def spec_exists(
    spec_id: str,
    registries_dir: Optional[Path] = None,
    plane: Optional["PlaneContext"] = None,
) -> bool:
    """Check if spec exists in specs_registry.csv."""
    reg_path = _resolve_registries_dir(registries_dir, plane) / "specs_registry.csv"
    if not reg_path.is_file():
        return False
    _, rows = read_registry(reg_path)
    return any(row.get("spec_id") == spec_id for row in rows)


def get_spec_framework(
    spec_id: str,
    registries_dir: Optional[Path] = None,
    plane: Optional["PlaneContext"] = None,
) -> Optional[str]:
    """Get framework_id for a spec from specs_registry.csv."""
    reg_path = _resolve_registries_dir(registries_dir, plane) / "specs_registry.csv"
    if not reg_path.is_file():
        return None
    _, rows = read_registry(reg_path)
    for row in rows:
        if row.get("spec_id") == spec_id:
            return row.get("framework_id")
    return None


def load_registry_as_dict(reg_path: Path, key_field: str) -> Dict[str, Dict[str, str]]:
    """Load CSV registry as dict keyed by key_field for O(1) lookups."""
    if not reg_path.is_file():
        return {}
    _, rows = read_registry(reg_path)
    return {row[key_field]: row for row in rows if key_field in row}
