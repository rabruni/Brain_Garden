"""Authentication Standard Library.

Provides token validation and secret fingerprinting utilities.
Wraps lib/auth.py for standardized access across the Control Plane.

This is a Tier 0 (T0) trust baseline library.

Example usage:
    from modules.stdlib_auth import validate_token, fingerprint_secret

    # Validate a token
    identity = validate_token("user:signature")
    print(f"User: {identity.user}, Roles: {identity.roles}")

    # Fingerprint a secret for safe logging
    fp = fingerprint_secret("my-secret-key")
    print(f"Fingerprint: {fp}")  # fp:sha256:a1b2c3d4...
"""

from modules.stdlib_auth.validator import (
    validate_token,
    require_role,
    Identity,
    AuthError,
)
from modules.stdlib_auth.fingerprint import fingerprint_secret

__all__ = [
    "validate_token",
    "require_role",
    "fingerprint_secret",
    "Identity",
    "AuthError",
]

__version__ = "0.1.0"
