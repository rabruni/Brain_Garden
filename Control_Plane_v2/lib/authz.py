"""Authorization helper for Control Plane v2."""
from __future__ import annotations

from typing import Iterable, Mapping

from lib.auth import Identity


# Default role → actions mapping
ROLE_ACTIONS: Mapping[str, set[str]] = {
    "admin": {"create", "install", "uninstall", "update", "remove", "pack", "verify", "hash_update", "checkpoint", "rollback"},
    "maintainer": {"install", "uninstall", "update", "remove", "pack", "verify", "checkpoint"},
    "auditor": {"verify"},
    "reader": {"verify"},
}


def is_authorized(identity: Identity, action: str) -> bool:
    """Check if any of the user's roles grants the action."""
    required = action.lower()
    for role in identity.roles:
        allowed = ROLE_ACTIONS.get(role, set())
        if required in allowed or "*" in allowed:
            return True
    return False


def require(identity: Identity | None, action: str) -> None:
    """Raise if identity missing or not allowed."""
    if identity is None:
        raise PermissionError(f"Auth required for action '{action}'")
    if not is_authorized(identity, action):
        raise PermissionError(f"Action '{action}' not permitted for roles: {identity.roles}")
