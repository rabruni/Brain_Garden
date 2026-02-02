"""Authentication utilities (pluggable providers) for Control Plane v2.

Supports:
- passthrough (dev) provider - DISABLED by default, requires explicit opt-in
- HMAC shared-secret provider (simple, no external deps) - DEFAULT

Designed to be replaced with OAuth/OIDC/SAML adapters: implement AuthProvider.

Environment:
    CONTROL_PLANE_AUTH_PROVIDER: "hmac" (default) or "passthrough"
    CONTROL_PLANE_SHARED_SECRET: Required for HMAC provider (or use external secrets)
    CONTROL_PLANE_SECRETS_FILE: Path to external secrets file (outside plane root)
    CONTROL_PLANE_ALLOW_PASSTHROUGH: Set to "1" to enable passthrough (dev only)

External Secrets:
    To preserve the "nothing unaccounted-for inside governed roots" invariant,
    secrets are loaded from OUTSIDE the plane root:
    1. CONTROL_PLANE_SECRETS_FILE env var (explicit path)
    2. ~/.control_plane_v2/secrets.env (user home)
    3. <plane_root>/../_external_secrets/control_plane_v2/secrets.env (sibling)

    Initialize with: python3 scripts/cp_init_auth.py
"""
from __future__ import annotations

import hmac
import os
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Protocol, Optional


class AuthConfigError(Exception):
    """Raised when auth configuration is invalid."""
    pass


def _parse_env_file(path: Path) -> dict[str, str]:
    """Parse env file lines supporting both 'KEY=VALUE' and 'export KEY=VALUE'.

    Args:
        path: Path to the env file

    Returns:
        Dict of key=value pairs from the file
    """
    result: dict[str, str] = {}
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # Strip leading 'export ' if present
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key.strip()] = value.strip()
    return result


def _load_external_secrets() -> dict[str, str]:
    """Load secrets from external file. Fail-closed if missing.

    Search order:
    1. CONTROL_PLANE_SECRETS_FILE env var (explicit path)
    2. ~/.control_plane_v2/secrets.env (user home)
    3. CONTROL_PLANE.parent/_external_secrets/control_plane_v2/secrets.env (sibling)

    Returns:
        Dict of key=value pairs from secrets file

    Raises:
        AuthConfigError: If no secrets file found (fail-closed)

    Note (Issue 4 Fix):
        When CONTROL_PLANE_SECRETS_FILE is set, we MUST NOT import lib.paths
        to avoid bootstrap recursion. Only import lib.paths when searching
        default paths that need CONTROL_PLANE.
    """
    # Check explicit path first - MUST NOT import lib.paths here (Issue 4)
    explicit = os.getenv("CONTROL_PLANE_SECRETS_FILE")
    if explicit:
        path = Path(explicit).expanduser()
        if path.exists():
            return _parse_env_file(path)
        raise AuthConfigError(f"CONTROL_PLANE_SECRETS_FILE not found: {explicit}")

    # Only import CONTROL_PLANE when searching default paths (Issue 4 fix)
    from lib.paths import CONTROL_PLANE

    # Search default locations (using CONTROL_PLANE for sibling path)
    search_paths = [
        Path.home() / ".control_plane_v2" / "secrets.env",
        CONTROL_PLANE.parent / "_external_secrets" / "control_plane_v2" / "secrets.env",
    ]

    for path in search_paths:
        if path.exists():
            return _parse_env_file(path)

    # Fail-closed: no secrets found
    raise AuthConfigError(
        "No external secrets file found. Run: python3 scripts/cp_init_auth.py\n"
        f"Searched: {[str(p) for p in search_paths]}"
    )


@dataclass
class Identity:
    user: str
    roles: list[str]


class AuthProvider(Protocol):
    def authenticate(self, token: Optional[str]) -> Optional[Identity]:
        """Return Identity if token is valid, else None."""


class PassthroughAuthProvider:
    """Dev-only provider: accepts any token (including None) as admin.

    WARNING: Only enabled when CONTROL_PLANE_ALLOW_PASSTHROUGH=1.
    """

    def authenticate(self, token: Optional[str]) -> Optional[Identity]:
        return Identity(user=os.getenv("USER", "dev"), roles=["admin"])


class HmacAuthProvider:
    """
    Token format: user:signature
    signature = HMAC_SHA256(secret, user)

    Secret resolution order:
    1. Explicit secret parameter (for testing)
    2. CONTROL_PLANE_SHARED_SECRET env var
    3. External secrets file (fail-closed if missing)
    """

    def __init__(self, secret: Optional[str] = None, roles: Optional[list[str]] = None):
        if secret:
            self.secret = secret.encode()
        else:
            # Try env var first, then external secrets file
            env_secret = os.getenv("CONTROL_PLANE_SHARED_SECRET")
            if env_secret:
                self.secret = env_secret.encode()
            else:
                # Load from external secrets file (fail-closed)
                secrets = _load_external_secrets()
                external_secret = secrets.get("CONTROL_PLANE_SHARED_SECRET", "")
                if not external_secret:
                    raise AuthConfigError(
                        "CONTROL_PLANE_SHARED_SECRET not found in secrets file"
                    )
                self.secret = external_secret.encode()
        self.roles = roles or ["admin"]

    def authenticate(self, token: Optional[str]) -> Optional[Identity]:
        if not token or not self.secret:
            return None
        if ":" not in token:
            return None
        user, sig = token.split(":", 1)
        expected = hmac.new(self.secret, user.encode(), sha256).hexdigest()
        if not hmac.compare_digest(expected, sig):
            return None
        return Identity(user=user, roles=self.roles)


def get_provider() -> AuthProvider:
    """Get the configured auth provider.

    Default: HMAC (fail-closed)
    Passthrough: Only if CONTROL_PLANE_ALLOW_PASSTHROUGH=1
    """
    # Default to HMAC (fail-closed)
    provider_name = os.getenv("CONTROL_PLANE_AUTH_PROVIDER", "hmac").lower()

    if provider_name == "passthrough":
        # Passthrough requires explicit opt-in
        if os.getenv("CONTROL_PLANE_ALLOW_PASSTHROUGH") != "1":
            raise AuthConfigError(
                "Passthrough auth disabled. "
                "Set CONTROL_PLANE_ALLOW_PASSTHROUGH=1 for dev only, "
                "or use HMAC auth with CONTROL_PLANE_SHARED_SECRET."
            )
        return PassthroughAuthProvider()

    # Default: HMAC provider
    return HmacAuthProvider()
