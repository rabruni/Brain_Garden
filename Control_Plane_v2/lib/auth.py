"""Authentication utilities (pluggable providers) for Control Plane v2.

Supports:
- passthrough (dev) provider - DISABLED by default, requires explicit opt-in
- HMAC shared-secret provider (simple, no external deps) - DEFAULT

Designed to be replaced with OAuth/OIDC/SAML adapters: implement AuthProvider.

Environment:
    CONTROL_PLANE_AUTH_PROVIDER: "hmac" (default) or "passthrough"
    CONTROL_PLANE_SHARED_SECRET: Required for HMAC provider
    CONTROL_PLANE_ALLOW_PASSTHROUGH: Set to "1" to enable passthrough (dev only)
"""
from __future__ import annotations

import hmac
import os
from dataclasses import dataclass
from hashlib import sha256
from typing import Protocol, Optional


class AuthConfigError(Exception):
    """Raised when auth configuration is invalid."""
    pass


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
    Secret is read from CONTROL_PLANE_SHARED_SECRET env.
    """

    def __init__(self, secret: Optional[str] = None, roles: Optional[list[str]] = None):
        self.secret = (secret or os.getenv("CONTROL_PLANE_SHARED_SECRET") or "").encode()
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
