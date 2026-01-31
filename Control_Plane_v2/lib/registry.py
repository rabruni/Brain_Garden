#!/usr/bin/env python3
"""
Registry operations - CRUD and lookup utilities.
"""
import csv
from pathlib import Path
from typing import Optional, List, Dict, Tuple

from .paths import CONTROL_PLANE, REGISTRIES_DIR, REPO_ROOT


def find_all_registries() -> List[Path]:
    """Find all CSV registries in Control_Plane.

    Searches:
    - registries/*.csv
    - modules/**/registries/*.csv
    - init/init_registry.csv
    - boot_os_registry.csv
    """
    registries = []

    # Root registries
    if REGISTRIES_DIR.is_dir():
        registries.extend(REGISTRIES_DIR.glob("*.csv"))

    # Module registries
    modules_dir = CONTROL_PLANE / "modules"
    if modules_dir.is_dir():
        registries.extend(modules_dir.glob("**/registries/*.csv"))

    # Init registry
    init_reg = CONTROL_PLANE / "init" / "init_registry.csv"
    if init_reg.is_file():
        registries.append(init_reg)

    # Boot OS registry
    boot_reg = CONTROL_PLANE / "boot_os_registry.csv"
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


def find_item(query: str) -> Optional[Tuple[Dict, Path, int]]:
    """Find an item by ID or NAME across all registries.

    Returns (row, registry_path, row_index) or None.

    Lookup order (per SYSTEM_CONSTITUTION.md - ID is primary key):
    1. Exact ID match (case-insensitive)
    2. Exact name match (case-insensitive)
    3. Partial name match (contains)

    Note: While ID is the primary key per constitution, we support
    name lookup for human convenience.
    """
    registries = find_all_registries()
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


def find_registry_by_name(name: str) -> Optional[Path]:
    """Find a registry by partial name match."""
    registries = find_all_registries()
    name_lower = name.lower()

    for reg in registries:
        if name_lower in reg.name.lower():
            return reg

    return None


def count_registry_stats() -> Dict[str, int]:
    """Count items by status across all registries."""
    stats = {
        "registries": 0,
        "total": 0,
        "selected": 0,
        "active": 0,
        "missing": 0,
        "draft": 0,
        "deprecated": 0,
    }

    registries = find_all_registries()
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
