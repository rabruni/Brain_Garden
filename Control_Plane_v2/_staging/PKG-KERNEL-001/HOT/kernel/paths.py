#!/usr/bin/env python3
"""
Shared path utilities for Control Plane scripts.

File discovery:
    discover_workspace_files() consolidates rglob+filter patterns used
    across pkgutil preflight/delta/stage commands.

DEPRECATION NOTICE:
    The global singletons in this module (CONTROL_PLANE, REGISTRIES_DIR, etc.)
    are DEPRECATED. For multi-plane operation, use PlaneContext from lib/plane.py
    instead:

        from kernel.plane import get_current_plane

        plane = get_current_plane(args.root)  # --root argument
        root = plane.root
        registries = root / "registries"

    The singletons remain for backward compatibility but will emit deprecation
    warnings in future versions. New code should use PlaneContext exclusively.
"""
import os
from pathlib import Path
from functools import lru_cache
from typing import Dict, Optional, Set
import warnings


def _deprecation_warning(name: str) -> None:
    """Emit a deprecation warning for singleton usage.

    Note: Currently disabled to avoid noisy output during migration.
    Enable by uncommenting the warnings.warn() call below.
    """
    # Uncomment to enable deprecation warnings:
    # warnings.warn(
    #     f"{name} is deprecated. Use PlaneContext from lib/plane.py instead.",
    #     DeprecationWarning,
    #     stacklevel=3
    # )
    pass


@lru_cache(maxsize=1)
def get_repo_root() -> Path:
    """Find repository root (contains .git/).

    Cached to avoid repeated filesystem lookups.
    """
    current = Path(__file__).resolve()
    for parent in [current] + list(current.parents):
        if (parent / ".git").is_dir():
            return parent
        # Fallback: look for SYSTEM_CONSTITUTION.md
        if (parent / "SYSTEM_CONSTITUTION.md").is_file():
            return parent
    return Path.cwd()


REPO_ROOT = get_repo_root()


@lru_cache(maxsize=1)
def get_control_plane_root() -> Path:
    """Resolve the Control Plane root.

    DEPRECATED: Use get_current_plane() from lib/plane.py instead for
    multi-plane operation.

    Priority:
    0) CONTROL_PLANE_ROOT env var (highest priority)
    1) Walk parents looking for structural marker (HOT/kernel/ exists).
    2) Fallback to the repo root.
    """
    _deprecation_warning("get_control_plane_root()")
    env_root = os.getenv("CONTROL_PLANE_ROOT")
    if env_root:
        return Path(env_root).resolve()
    current = Path(__file__).resolve()
    for parent in [current] + list(current.parents):
        if (parent / "HOT" / "kernel").is_dir():
            return parent

    return REPO_ROOT


# =============================================================================
# DEPRECATED SINGLETONS
# =============================================================================
# These singletons are for backward compatibility only.
# New code should use PlaneContext from lib/plane.py:
#
#     from kernel.plane import get_current_plane
#     plane = get_current_plane(root)  # root from --root arg
#     registries_dir = plane.root / "registries"
#
# =============================================================================

CONTROL_PLANE = get_control_plane_root()
"""DEPRECATED: Global control plane root. Use PlaneContext.root instead."""

REGISTRIES_DIR = CONTROL_PLANE / "HOT" / "registries"
"""DEPRECATED: Use plane.root / 'HOT' / 'registries' instead."""

LEDGER_DIR = CONTROL_PLANE / "HOT" / "ledger"
"""DEPRECATED: Use plane.root / 'HOT' / 'ledger' instead."""


# =============================================================================
# File Discovery Constants & Helpers
# =============================================================================

PACKAGE_META_FILES: Set[str] = {"manifest.json", "signature.json", "checksums.sha256"}
"""Standard package metadata files excluded from workspace discovery."""

COMMON_EXCLUDE_PATTERNS: Set[str] = {"__pycache__", ".DS_Store"}
"""Common directory/file patterns to exclude from file discovery."""

INTEGRITY_EXCLUDE_PATTERNS: Set[str] = {
    "__pycache__", ".git", ".pytest_cache", "node_modules", "__init__.py"
}
"""Exclusion patterns used by integrity checks (orphan detection)."""


def discover_workspace_files(
    root: Path,
    exclude_names: Optional[Set[str]] = None,
    exclude_patterns: Optional[Set[str]] = None,
) -> Dict[str, Path]:
    """Discover files in a workspace directory, returning {relative_path: absolute_path}.

    Filters out directories and applies exclusions by file name and path pattern.

    Args:
        root: Root directory to scan
        exclude_names: File names to skip (e.g., PACKAGE_META_FILES)
        exclude_patterns: Path component patterns to skip (e.g., __pycache__)

    Returns:
        Dict mapping relative path strings to absolute Path objects
    """
    if exclude_names is None:
        exclude_names = PACKAGE_META_FILES
    if exclude_patterns is None:
        exclude_patterns = COMMON_EXCLUDE_PATTERNS

    workspace_files: Dict[str, Path] = {}
    for file_path in root.rglob("*"):
        if file_path.is_dir():
            continue
        if file_path.name in exclude_names:
            continue
        if exclude_patterns and any(pat in file_path.parts for pat in exclude_patterns):
            continue
        rel_path = file_path.relative_to(root)
        workspace_files[str(rel_path)] = file_path

    return workspace_files
