#!/usr/bin/env python3
"""
Shared path utilities for Control Plane scripts.

DEPRECATION NOTICE:
    The global singletons in this module (CONTROL_PLANE, REGISTRIES_DIR, etc.)
    are DEPRECATED. For multi-plane operation, use PlaneContext from lib/plane.py
    instead:

        from lib.plane import get_current_plane

        plane = get_current_plane(args.root)  # --root argument
        root = plane.root
        registries = root / "registries"

    The singletons remain for backward compatibility but will emit deprecation
    warnings in future versions. New code should use PlaneContext exclusively.
"""
from pathlib import Path
from functools import lru_cache
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
    1) If this file lives under a Control_Plane_v2 tree, return that.
    2) Else if a Control_Plane tree exists under the repo root, return it.
    3) Fallback to the repo root.
    """
    _deprecation_warning("get_control_plane_root()")
    current = Path(__file__).resolve()
    for parent in [current] + list(current.parents):
        if parent.name == "Control_Plane_v2":
            return parent

    candidate = REPO_ROOT / "Control_Plane_v2"
    if (candidate / "scripts").is_dir() and (candidate / "registries").is_dir():
        return candidate

    candidate = REPO_ROOT / "Control_Plane"
    if (candidate / "scripts").is_dir() and (candidate / "registries").is_dir():
        return candidate

    return REPO_ROOT


# =============================================================================
# DEPRECATED SINGLETONS
# =============================================================================
# These singletons are for backward compatibility only.
# New code should use PlaneContext from lib/plane.py:
#
#     from lib.plane import get_current_plane
#     plane = get_current_plane(root)  # root from --root arg
#     registries_dir = plane.root / "registries"
#
# =============================================================================

CONTROL_PLANE = get_control_plane_root()
"""DEPRECATED: Global control plane root. Use PlaneContext.root instead."""

REGISTRIES_DIR = CONTROL_PLANE / "registries"
"""DEPRECATED: Use plane.root / 'registries' instead."""

SCRIPTS_DIR = CONTROL_PLANE / "scripts"
"""DEPRECATED: Use plane.root / 'scripts' instead."""

SPECS_DIR = CONTROL_PLANE / "specs"
"""DEPRECATED: Use plane.root / 'specs' instead."""

FRAMEWORKS_DIR = CONTROL_PLANE / "frameworks"
"""DEPRECATED: Use plane.root / 'frameworks' instead."""

MODULES_DIR = CONTROL_PLANE / "modules"
"""DEPRECATED: Use plane.root / 'modules' instead."""

LEDGER_DIR = CONTROL_PLANE / "ledger"
"""DEPRECATED: Use plane.ledger_dir instead."""

GENERATED_DIR = CONTROL_PLANE / "generated"
"""DEPRECATED: Use plane.root / 'generated' instead."""
