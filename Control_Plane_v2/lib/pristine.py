#!/usr/bin/env python3
"""
pristine.py - Write boundary enforcement for Control Plane v2.

Enforces that each plane's directory remains pristine:
- No byte may enter governed paths unless via verified, auditable transition.
- Only package_install (in INSTALL mode) may write to PRISTINE paths.
- Ledger is append-only.
- Direct writes are forbidden except to DERIVED paths.

Directory Classes:
    PRISTINE: Read-only except via governed install
    APPEND_ONLY: Only append operations allowed
    DERIVED: Mutable (staging, compiled outputs)

Modes:
    normal: Only DERIVED paths writable
    install: PRISTINE paths writable (package_install only)
    bootstrap: packages_registry.csv writable (one-time setup)

Plane-Aware:
    All functions accept an optional `plane` parameter (PlaneContext).
    When provided, operations are scoped to that plane's root instead of
    the global CONTROL_PLANE singleton.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Set, Optional, TYPE_CHECKING

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.paths import CONTROL_PLANE
from lib.ledger_client import LedgerClient, LedgerEntry
from lib.tier_manifest import TierManifest

if TYPE_CHECKING:
    from lib.plane import PlaneContext


class WriteMode(str, Enum):
    """Write operation modes."""
    NORMAL = "normal"
    INSTALL = "install"
    BOOTSTRAP = "bootstrap"


class PathClass(str, Enum):
    """Directory classification."""
    PRISTINE = "pristine"
    APPEND_ONLY = "append_only"
    DERIVED = "derived"
    EXTERNAL = "external"


# Directory classifications relative to CONTROL_PLANE
PRISTINE_PATHS: Set[str] = {
    "frameworks",
    "lib",
    "scripts",
    "registries",
    "modules",
    "schemas",
    "policies",
    "specs",
}

APPEND_ONLY_PATHS: Set[str] = {
    "ledger",
}

DERIVED_PATHS: Set[str] = {
    "packages_store",
    "registries/compiled",
    "versions",
    "tmp",
    "_staging",
    "installed",
}

# Special case: packages_registry.csv is PRISTINE but writable in BOOTSTRAP mode
BOOTSTRAP_WRITABLE: Set[str] = {
    "registries/packages_registry.csv",
}


def is_tier_ledger_path(path: Path) -> bool:
    """Check if a path is a ledger within a registered tier.

    Walks up the directory tree looking for tier.json manifest.
    If found, checks if the path is within that tier's ledger directory.

    Args:
        path: Path to check

    Returns:
        True if path is a ledger within a tier, False otherwise
    """
    # Resolve to handle symlinks and /var vs /private/var on macOS
    path = path.resolve()

    # Walk up looking for tier.json
    for parent in [path] + list(path.parents):
        manifest_path = parent / "tier.json"
        if manifest_path.exists():
            try:
                manifest = TierManifest.load(manifest_path)
                # Check if path is within the tier's ledger directory
                # Resolve both paths for consistent comparison
                ledger_dir = (manifest.tier_root / manifest.ledger_path.parent).resolve()
                try:
                    path.relative_to(ledger_dir)
                    return True
                except ValueError:
                    pass
            except Exception:
                continue
    return False


@dataclass
class WriteViolation(Exception):
    """Raised when a write violates pristine boundaries."""
    path: Path
    mode: WriteMode
    path_class: PathClass
    message: str

    def __str__(self) -> str:
        return f"WriteViolation: {self.message} (path={self.path}, mode={self.mode}, class={self.path_class})"


class OutsideBoundaryViolation(Exception):
    """Raised when a path is outside CONTROL_PLANE and CONTROL_PLANE_ALLOW_OUTSIDE is not set."""

    def __init__(self, path: Path, message: str = ""):
        self.path = path
        self.message = message or f"Path outside CONTROL_PLANE: {path}"
        super().__init__(self.message)


def _get_plane_root(plane: Optional["PlaneContext"] = None) -> Path:
    """Get the root path for a plane, or CONTROL_PLANE as fallback.

    Args:
        plane: Optional PlaneContext to use

    Returns:
        The plane's root path, or CONTROL_PLANE if not provided
    """
    if plane is not None:
        return plane.root
    return CONTROL_PLANE


def is_inside_control_plane(path: Path, plane: Optional["PlaneContext"] = None) -> bool:
    """Check if a path is inside the control plane root.

    Args:
        path: Path to check
        plane: Optional PlaneContext to scope the check (uses plane.root)

    Returns:
        True if path is inside the plane's root (or CONTROL_PLANE if no plane)
    """
    root = _get_plane_root(plane)
    if not path.is_absolute():
        path = Path.cwd() / path
    path = path.resolve()
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def assert_inside_control_plane(
    path: Path,
    log_violation: bool = True,
    plane: Optional["PlaneContext"] = None,
) -> None:
    """
    Assert that a path is inside the control plane root.

    Raises OutsideBoundaryViolation unless CONTROL_PLANE_ALLOW_OUTSIDE=1.

    Args:
        path: Path to check
        log_violation: If True, log violations to ledger
        plane: Optional PlaneContext to scope the check (uses plane.root)
    """
    root = _get_plane_root(plane)
    if not path.is_absolute():
        path = Path.cwd() / path
    path = path.resolve()

    if is_inside_control_plane(path, plane=plane):
        return  # OK

    # Check for dev escape hatch
    if os.getenv("CONTROL_PLANE_ALLOW_OUTSIDE") == "1":
        if log_violation:
            _log_event("OUTSIDE_ALLOWED", path, get_current_mode(), allowed=True, plane=plane)
        return  # Explicitly allowed

    # Violation
    if log_violation:
        _log_event("OUTSIDE_DENIED", path, get_current_mode(), allowed=False, plane=plane)

    plane_name = plane.name if plane else "CONTROL_PLANE"
    raise OutsideBoundaryViolation(
        path,
        f"Write outside {plane_name} denied: {path}. "
        f"Set CONTROL_PLANE_ALLOW_OUTSIDE=1 to allow (dev only)."
    )


def classify_path(path: Path, plane: Optional["PlaneContext"] = None) -> PathClass:
    """
    Classify a path into its directory class.

    Args:
        path: Absolute or relative path to classify
        plane: Optional PlaneContext to scope the classification (uses plane.root)

    Returns:
        PathClass indicating the directory's write rules
    """
    root = _get_plane_root(plane)

    # Normalize to absolute
    if not path.is_absolute():
        path = root / path

    # Check if path is under the plane root
    try:
        rel = path.relative_to(root)
    except ValueError:
        # Path is outside plane root - check if it's a tier ledger
        if is_tier_ledger_path(path):
            return PathClass.APPEND_ONLY
        return PathClass.EXTERNAL

    rel_str = str(rel)
    parts = rel.parts

    if not parts:
        return PathClass.PRISTINE  # Root is pristine

    # Use plane-specific directory lists if available, else defaults
    derived_paths = set(plane.derived_roots) if plane else DERIVED_PATHS
    append_only_paths = set(plane.append_only_roots) if plane else APPEND_ONLY_PATHS
    pristine_paths = set(plane.pristine_roots) if plane else PRISTINE_PATHS

    # Check derived first (more specific paths)
    for derived in derived_paths:
        if rel_str == derived or rel_str.startswith(derived + "/"):
            return PathClass.DERIVED

    # Check append-only
    for append_only in append_only_paths:
        if rel_str == append_only or rel_str.startswith(append_only + "/"):
            return PathClass.APPEND_ONLY

    # Check if this is a ledger within a nested tier (work_orders/sessions instances)
    if is_tier_ledger_path(path):
        return PathClass.APPEND_ONLY

    # Check pristine
    for pristine in pristine_paths:
        if rel_str == pristine or rel_str.startswith(pristine + "/"):
            return PathClass.PRISTINE

    # Default: treat as derived (safe fallback for unknown paths)
    return PathClass.DERIVED


def is_bootstrap_writable(path: Path, plane: Optional["PlaneContext"] = None) -> bool:
    """Check if path is writable during bootstrap mode.

    Args:
        path: Path to check
        plane: Optional PlaneContext to scope the check (uses plane.root)

    Returns:
        True if the path is writable during bootstrap mode
    """
    root = _get_plane_root(plane)
    try:
        rel = path.relative_to(root)
        return str(rel) in BOOTSTRAP_WRITABLE
    except ValueError:
        return False


def get_current_mode() -> WriteMode:
    """
    Get the current write mode from environment.

    Environment variables:
        CONTROL_PLANE_INSTALL_MODE=1 -> install mode
        CONTROL_PLANE_BOOTSTRAP=1 -> bootstrap mode
        Neither -> normal mode
    """
    if os.getenv("CONTROL_PLANE_BOOTSTRAP") == "1":
        return WriteMode.BOOTSTRAP
    if os.getenv("CONTROL_PLANE_INSTALL_MODE") == "1":
        return WriteMode.INSTALL
    return WriteMode.NORMAL


def assert_write_allowed(
    path: Path,
    mode: Optional[WriteMode] = None,
    log_violation: bool = True,
    plane: Optional["PlaneContext"] = None,
) -> None:
    """
    Assert that a write operation is allowed.

    Args:
        path: Path being written to
        mode: Write mode (defaults to environment-based detection)
        log_violation: If True, log violations to ledger
        plane: Optional PlaneContext to scope the check (uses plane.root)

    Raises:
        WriteViolation: If write is not allowed
    """
    if mode is None:
        mode = get_current_mode()

    # First: check if path is inside the plane root (fail-closed boundary)
    # This raises OutsideBoundaryViolation unless CONTROL_PLANE_ALLOW_OUTSIDE=1
    assert_inside_control_plane(path, log_violation=log_violation, plane=plane)

    path_class = classify_path(path, plane=plane)

    # External paths should not reach here (caught by assert_inside_control_plane)
    # But if CONTROL_PLANE_ALLOW_OUTSIDE=1, external writes are explicitly allowed
    if path_class == PathClass.EXTERNAL:
        return

    # Derived paths are always writable
    if path_class == PathClass.DERIVED:
        return

    # Append-only: only append operations allowed
    # (caller must ensure append semantics; we can't enforce at this level)
    if path_class == PathClass.APPEND_ONLY:
        # Allow writes to append-only paths
        # The ledger itself enforces append semantics internally
        return

    # PRISTINE paths require special handling
    if path_class == PathClass.PRISTINE:
        # Check bootstrap exception
        if mode == WriteMode.BOOTSTRAP and is_bootstrap_writable(path, plane=plane):
            _log_event("BOOTSTRAP_WRITE", path, mode, allowed=True, plane=plane)
            return

        # Check install mode
        if mode == WriteMode.INSTALL:
            _log_event("INSTALL_WRITE", path, mode, allowed=True, plane=plane)
            return

        # Violation
        violation = WriteViolation(
            path=path,
            mode=mode,
            path_class=path_class,
            message=f"Direct write to PRISTINE path forbidden. Use package_install with INSTALL mode.",
        )

        if log_violation:
            _log_event("PRISTINE_VIOLATION", path, mode, allowed=False, plane=plane)

        raise violation


def _log_event(
    event_type: str,
    path: Path,
    mode: WriteMode,
    allowed: bool,
    plane: Optional["PlaneContext"] = None,
) -> None:
    """Log a pristine boundary event to the ledger.

    Args:
        event_type: Type of event (e.g., "BOOTSTRAP_WRITE", "PRISTINE_VIOLATION")
        path: Path involved in the event
        mode: Current write mode
        allowed: Whether the operation was allowed
        plane: Optional PlaneContext for plane-scoped logging
    """
    try:
        # Use plane-scoped ledger if available
        if plane is not None:
            ledger = LedgerClient(ledger_path=plane.ledger_dir / "governance.jsonl")
        else:
            ledger = LedgerClient()
        entry = LedgerEntry(
            event_type=f"pristine_{event_type.lower()}",
            submission_id=str(path),
            decision="ALLOWED" if allowed else "DENIED",
            reason=f"{event_type}: mode={mode.value}, path={path}",
            metadata={
                "path": str(path),
                "mode": mode.value,
                "path_class": classify_path(path, plane=plane).value,
                "allowed": allowed,
                "plane": plane.name if plane else "default",
            },
        )
        ledger.write(entry)
    except Exception:
        # Don't fail on ledger errors
        pass


def assert_append_only(path: Path, plane: Optional["PlaneContext"] = None) -> None:
    """
    Assert that a path is in an append-only directory.

    Used to verify ledger operations are append-only.

    Args:
        path: Path to check
        plane: Optional PlaneContext to scope the check (uses plane.root)
    """
    path_class = classify_path(path, plane=plane)
    if path_class != PathClass.APPEND_ONLY:
        raise WriteViolation(
            path=path,
            mode=get_current_mode(),
            path_class=path_class,
            message=f"Path is not append-only: {path}",
        )


def enter_install_mode() -> str:
    """
    Enter install mode. Returns previous mode value for restoration.

    Usage:
        prev = enter_install_mode()
        try:
            # ... perform install ...
        finally:
            exit_install_mode(prev)
    """
    prev = os.getenv("CONTROL_PLANE_INSTALL_MODE", "")
    os.environ["CONTROL_PLANE_INSTALL_MODE"] = "1"
    return prev


def exit_install_mode(prev: str) -> None:
    """Exit install mode, restoring previous value."""
    if prev:
        os.environ["CONTROL_PLANE_INSTALL_MODE"] = prev
    else:
        os.environ.pop("CONTROL_PLANE_INSTALL_MODE", None)


def enter_bootstrap_mode() -> str:
    """
    Enter bootstrap mode. Returns previous mode value.

    WARNING: Bootstrap mode should only be used during initial setup.
    """
    prev = os.getenv("CONTROL_PLANE_BOOTSTRAP", "")
    os.environ["CONTROL_PLANE_BOOTSTRAP"] = "1"

    # Log bootstrap mode activation
    try:
        ledger = LedgerClient()
        entry = LedgerEntry(
            event_type="bootstrap_mode_used",
            submission_id="BOOTSTRAP",
            decision="ACTIVATED",
            reason="Bootstrap mode enabled for registry initialization",
            metadata={"warning": "Bootstrap mode allows direct registry writes"},
        )
        ledger.write(entry)
    except Exception:
        pass

    return prev


def exit_bootstrap_mode(prev: str) -> None:
    """Exit bootstrap mode, restoring previous value."""
    if prev:
        os.environ["CONTROL_PLANE_BOOTSTRAP"] = prev
    else:
        os.environ.pop("CONTROL_PLANE_BOOTSTRAP", None)


# Context managers for convenience
class InstallModeContext:
    """Context manager for install mode."""

    def __init__(self):
        self._prev = ""

    def __enter__(self):
        self._prev = enter_install_mode()
        return self

    def __exit__(self, *args):
        exit_install_mode(self._prev)


class BootstrapModeContext:
    """Context manager for bootstrap mode."""

    def __init__(self):
        self._prev = ""

    def __enter__(self):
        self._prev = enter_bootstrap_mode()
        return self

    def __exit__(self, *args):
        exit_bootstrap_mode(self._prev)
