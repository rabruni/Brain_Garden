#!/usr/bin/env python3
"""
Path resolution utilities.
"""
from pathlib import Path
from .paths import REPO_ROOT, CONTROL_PLANE


def resolve_artifact_path(path_str: str) -> Path:
    """Resolve an artifact path to absolute path.

    Handles:
    - Leading slash (relative to Control Plane root)
    - Legacy Control_Plane prefix
    - Other paths (relative to Control Plane root)
    """
    if not path_str:
        return Path()

    path_str = path_str.strip()
    if path_str.startswith("/"):
        path_str = path_str[1:]

    if path_str.startswith("Control_Plane/"):
        path_str = path_str[len("Control_Plane/"):]

    if not path_str:
        return Path()

    candidate = CONTROL_PLANE / path_str
    if candidate.exists():
        return candidate

    fallback = REPO_ROOT / path_str
    if fallback.exists():
        return fallback

    return candidate if CONTROL_PLANE != REPO_ROOT else fallback
