#!/usr/bin/env python3
"""
plane.py - Plane context and chain configuration for Control Plane v2.

Implements the 3-plane topology:
- HO3: Highest privilege, cannot be modified by lower planes (formerly HOT)
- HO2: Middle tier, can reference HO3 interfaces (formerly FIRST_ORDER)
- HO1: Lowest tier, can reference HO2 and HO3 interfaces (formerly SECOND_ORDER)

Canonical naming:
| Canonical | Legacy Alias | Description |
|-----------|--------------|-------------|
| HO3 | HOT | Higher Order 3 (highest privilege) |
| HO2 | FIRST | Higher Order 2 (middle tier) |
| HO1 | SECOND | Higher Order 1 (lowest tier) |

Per the Plane-Aware Package System design:
- No lower plane may mutate a higher plane (no-upward-trust)
- Cross-plane references are READ-ONLY (schemas/contracts only)
- All operations are plane-scoped via PlaneContext
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kernel.paths import CONTROL_PLANE


class PlaneType(str, Enum):
    """Plane type enumeration using canonical naming."""
    HO3 = "HO3"  # Highest privilege (formerly HOT)
    HO2 = "HO2"  # Middle tier (formerly FIRST_ORDER)
    HO1 = "HO1"  # Lowest tier (formerly SECOND_ORDER)

    # Legacy aliases for backward compatibility
    HOT = "HO3"
    FIRST_ORDER = "HO2"
    SECOND_ORDER = "HO1"


# Plane ordering (lower number = higher privilege)
PLANE_ORDER = {
    PlaneType.HO3: 0,
    PlaneType.HO2: 1,
    PlaneType.HO1: 2,
}

# Plane name to type mapping (supports both canonical and legacy names)
PLANE_NAME_MAP = {
    # Canonical names
    "ho3": PlaneType.HO3,
    "ho2": PlaneType.HO2,
    "ho1": PlaneType.HO1,
    # Legacy names for backward compatibility
    "hot": PlaneType.HO3,
    "first": PlaneType.HO2,
    "second": PlaneType.HO1,
}

# Migration mapping from legacy plane type strings to canonical
PLANE_TYPE_MIGRATION = {
    "HOT": "HO3",
    "FIRST_ORDER": "HO2",
    "SECOND_ORDER": "HO1",
}


def migrate_plane_type(plane_type_str: str) -> str:
    """Migrate a plane type string from legacy to canonical form.

    Args:
        plane_type_str: Plane type string (legacy or canonical)

    Returns:
        Canonical plane type string (HO3, HO2, or HO1)
    """
    return PLANE_TYPE_MIGRATION.get(plane_type_str, plane_type_str)


# Default directory classifications
DEFAULT_PRISTINE_ROOTS = [
    "frameworks", "lib", "scripts", "registries", "modules", "schemas", "policies", "specs"
]
DEFAULT_DERIVED_ROOTS = [
    "packages_store", "registries/compiled", "versions", "tmp", "_staging", "installed"
]
DEFAULT_APPEND_ONLY_ROOTS = ["ledger"]


@dataclass
class PlaneContext:
    """Context for a single plane in the control plane chain.

    Attributes:
        name: Short name (e.g., "hot", "first", "second")
        plane_type: PlaneType enum value
        root: Root path for this plane's files
        pristine_roots: Directories that are read-only except via install
        derived_roots: Directories that are freely writable
        append_only_roots: Directories that only allow appends (e.g., ledger)
        receipts_dir: Directory for install receipts
        ledger_dir: Directory for ledger files
    """
    name: str
    plane_type: PlaneType
    root: Path
    pristine_roots: List[str] = field(default_factory=lambda: DEFAULT_PRISTINE_ROOTS.copy())
    derived_roots: List[str] = field(default_factory=lambda: DEFAULT_DERIVED_ROOTS.copy())
    append_only_roots: List[str] = field(default_factory=lambda: DEFAULT_APPEND_ONLY_ROOTS.copy())
    receipts_dir: Path = field(default=None)
    ledger_dir: Path = field(default=None)

    def __post_init__(self):
        """Initialize computed paths."""
        if self.receipts_dir is None:
            self.receipts_dir = self.root / "installed"
        if self.ledger_dir is None:
            self.ledger_dir = self.root / "ledger"

    def is_path_inside(self, path: Path) -> bool:
        """Check if a path is inside this plane's root."""
        try:
            path = path.resolve()
            path.relative_to(self.root.resolve())
            return True
        except ValueError:
            return False

    def get_relative_path(self, path: Path) -> Optional[Path]:
        """Get path relative to plane root, or None if outside."""
        try:
            return path.resolve().relative_to(self.root.resolve())
        except ValueError:
            return None

    def can_reference_plane(self, other_plane_type: PlaneType) -> bool:
        """Check if this plane can reference interfaces from another plane.

        Direction rules:
        - HOT can reference FIRST_ORDER and SECOND_ORDER
        - FIRST_ORDER can reference SECOND_ORDER only
        - SECOND_ORDER cannot reference other planes

        Note: This is for external_interfaces (READ-ONLY), not deps.
        """
        my_order = PLANE_ORDER[self.plane_type]
        other_order = PLANE_ORDER[other_plane_type]
        # Can only reference planes with higher order number (lower privilege)
        return other_order > my_order

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "type": self.plane_type.value,
            "root": str(self.root),
            "pristine_roots": self.pristine_roots,
            "derived_roots": self.derived_roots,
            "append_only_roots": self.append_only_roots,
            "receipts_dir": str(self.receipts_dir),
            "ledger_dir": str(self.ledger_dir),
        }


class PlaneError(Exception):
    """Base exception for plane-related errors."""
    pass


class PlaneNotFoundError(PlaneError):
    """Raised when a plane cannot be resolved."""
    pass


class CrossPlaneViolation(PlaneError):
    """Raised when a cross-plane operation violates direction rules."""

    def __init__(self, source_plane: str, target_plane: str, operation: str, message: str = ""):
        self.source_plane = source_plane
        self.target_plane = target_plane
        self.operation = operation
        self.message = message or (
            f"Cross-plane violation: {source_plane} cannot {operation} {target_plane}"
        )
        super().__init__(self.message)


class PlaneTargetMismatch(PlaneError):
    """Raised when a package's target_plane doesn't match the current plane."""

    def __init__(self, target_plane: str, current_plane: str, package_id: str = ""):
        self.target_plane = target_plane
        self.current_plane = current_plane
        self.package_id = package_id
        self.message = (
            f"Package {package_id} targets plane '{target_plane}' but current plane is '{current_plane}'"
        )
        super().__init__(self.message)


def get_chain_config_path() -> Path:
    """Get the path to the chain configuration file."""
    # First check environment variable
    env_path = os.getenv("CONTROL_PLANE_CHAIN_CONFIG")
    if env_path:
        return Path(env_path)

    # Default location
    return CONTROL_PLANE / "config" / "control_plane_chain.json"


@lru_cache(maxsize=1)
def load_chain_config() -> List[PlaneContext]:
    """Load all planes from config/control_plane_chain.json.

    Returns:
        List of PlaneContext objects for each configured plane.

    Raises:
        PlaneError: If configuration is invalid or missing.

    Note:
        Legacy plane type names (HOT, FIRST_ORDER, SECOND_ORDER) are
        automatically migrated to canonical names (HO3, HO2, HO1).
    """
    config_path = get_chain_config_path()

    if not config_path.exists():
        # Return default single-plane config if no chain config exists
        return [PlaneContext(
            name="default",
            plane_type=PlaneType.HO1,
            root=CONTROL_PLANE,
        )]

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        raise PlaneError(f"Failed to load chain config: {e}")

    planes = []
    for plane_config in config.get("planes", []):
        name = plane_config.get("name", "")
        plane_type_str = plane_config.get("type", "HO1")
        root = plane_config.get("root", "")

        if not name:
            raise PlaneError("Plane config missing 'name'")
        if not root:
            raise PlaneError(f"Plane '{name}' missing 'root'")

        # Migrate legacy type string to canonical
        plane_type_str = migrate_plane_type(plane_type_str)

        # Map type string to PlaneType
        try:
            plane_type = PlaneType(plane_type_str)
        except ValueError:
            raise PlaneError(f"Invalid plane type '{plane_type_str}' for plane '{name}'")

        plane = PlaneContext(
            name=name,
            plane_type=plane_type,
            root=Path(root).expanduser().resolve(),
            pristine_roots=plane_config.get("pristine_roots", DEFAULT_PRISTINE_ROOTS.copy()),
            derived_roots=plane_config.get("derived_roots", DEFAULT_DERIVED_ROOTS.copy()),
            append_only_roots=plane_config.get("append_only_roots", DEFAULT_APPEND_ONLY_ROOTS.copy()),
        )
        planes.append(plane)

    return planes


def clear_chain_config_cache() -> None:
    """Clear the cached chain configuration."""
    load_chain_config.cache_clear()


def get_plane_by_name(name: str) -> PlaneContext:
    """Get a plane context by name.

    Args:
        name: Plane name (e.g., "hot", "first", "second")

    Returns:
        PlaneContext for the named plane.

    Raises:
        PlaneNotFoundError: If no plane with the given name exists.
    """
    planes = load_chain_config()
    for plane in planes:
        if plane.name == name:
            return plane
    raise PlaneNotFoundError(f"No plane found with name '{name}'")


def get_plane_by_root(root: Path) -> PlaneContext:
    """Get a plane context by root path.

    Args:
        root: Root path to match.

    Returns:
        PlaneContext whose root matches the given path.

    Raises:
        PlaneNotFoundError: If no plane with the given root exists.
    """
    root = root.resolve()
    planes = load_chain_config()
    for plane in planes:
        if plane.root.resolve() == root:
            return plane
    raise PlaneNotFoundError(f"No plane found with root '{root}'")


def get_current_plane(root: Optional[Path] = None) -> PlaneContext:
    """Resolve the current plane from --root argument or CWD.

    Resolution order:
    1. If root is provided, find plane with matching root
    2. If CONTROL_PLANE_ROOT env var is set, use that
    3. Check if CWD is inside any configured plane
    4. Fall back to default plane (CONTROL_PLANE path)

    Args:
        root: Optional explicit root path (e.g., from --root argument)

    Returns:
        PlaneContext for the resolved plane.

    Raises:
        PlaneNotFoundError: If plane cannot be resolved.
    """
    planes = load_chain_config()

    # 1. Explicit root argument
    if root is not None:
        root = root.resolve()
        for plane in planes:
            if plane.root.resolve() == root:
                return plane
        # Root specified but not in config - create ad-hoc context
        return PlaneContext(
            name="custom",
            plane_type=PlaneType.HO1,
            root=root,
        )

    # 2. Environment variable
    env_root = os.getenv("CONTROL_PLANE_ROOT")
    if env_root:
        env_root_path = Path(env_root).expanduser().resolve()
        for plane in planes:
            if plane.root.resolve() == env_root_path:
                return plane

    # 3. Check if CWD is inside any plane
    cwd = Path.cwd().resolve()
    for plane in planes:
        if plane.is_path_inside(cwd):
            return plane

    # 4. Default: return first plane or create default
    if planes:
        return planes[0]

    return PlaneContext(
        name="default",
        plane_type=PlaneType.HO1,
        root=CONTROL_PLANE,
    )


def resolve_plane_type(name: str) -> PlaneType:
    """Resolve a plane name to its PlaneType.

    Args:
        name: Plane name (e.g., "hot", "first", "second")

    Returns:
        PlaneType for the named plane.

    Raises:
        PlaneNotFoundError: If name is not recognized.
    """
    name_lower = name.lower()
    if name_lower in PLANE_NAME_MAP:
        return PLANE_NAME_MAP[name_lower]
    raise PlaneNotFoundError(f"Unknown plane name '{name}'")


def validate_target_plane(manifest_target: str, current_plane: PlaneContext) -> bool:
    """Validate that a package's target_plane matches the current plane.

    Args:
        manifest_target: target_plane from manifest ("hot", "first", "second", or "any")
        current_plane: Current PlaneContext

    Returns:
        True if target matches current plane (or target is "any")
    """
    if manifest_target == "any":
        return True
    return manifest_target.lower() == current_plane.name.lower()


def validate_external_interface_direction(
    source_plane: PlaneContext,
    interface_source_plane: str,
) -> bool:
    """Validate that an external interface reference follows direction rules.

    External interface direction rules:
    - HOT can reference FIRST_ORDER and SECOND_ORDER interfaces
    - FIRST_ORDER can reference SECOND_ORDER interfaces only
    - SECOND_ORDER cannot reference other plane interfaces

    Args:
        source_plane: The plane containing the package
        interface_source_plane: The plane from which the interface originates

    Returns:
        True if the reference direction is valid
    """
    try:
        interface_plane_type = resolve_plane_type(interface_source_plane)
    except PlaneNotFoundError:
        # Unknown plane - fail closed
        return False

    return source_plane.can_reference_plane(interface_plane_type)


def get_all_plane_names() -> List[str]:
    """Get all configured plane names.

    Returns:
        List of plane names from the chain config.
    """
    return [plane.name for plane in load_chain_config()]
