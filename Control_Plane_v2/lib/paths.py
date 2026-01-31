#!/usr/bin/env python3
"""
Shared path utilities for Control Plane scripts.
"""
from pathlib import Path
from functools import lru_cache


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

    Priority:
    1) If this file lives under a Control_Plane_v2 tree, return that.
    2) Else if a Control_Plane tree exists under the repo root, return it.
    3) Fallback to the repo root.
    """
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


CONTROL_PLANE = get_control_plane_root()
REGISTRIES_DIR = CONTROL_PLANE / "registries"
SCRIPTS_DIR = CONTROL_PLANE / "scripts"
SPECS_DIR = CONTROL_PLANE / "specs"
FRAMEWORKS_DIR = CONTROL_PLANE / "frameworks"
MODULES_DIR = CONTROL_PLANE / "modules"
LEDGER_DIR = CONTROL_PLANE / "ledger"
GENERATED_DIR = CONTROL_PLANE / "generated"
