"""Token validation utilities.

Wraps lib/auth.py HmacAuthProvider for standardized token validation.
Does NOT duplicate authentication logic - all validation is delegated.

Example:
    from modules.stdlib_auth.validator import validate_token, require_role

    identity = validate_token("user:signature")
    require_role(identity, "admin")  # Raises AuthError if not admin
"""

from dataclasses import dataclass
from typing import List, Optional

from lib.auth import get_provider, Identity as LibIdentity
from modules.stdlib_auth.fingerprint import fingerprint_secret


class AuthError(Exception):
    """Authentication or authorization error."""

    def __init__(self, message: str, code: str = "AUTH_ERROR", details: dict = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}


@dataclass
class Identity:
    """Authenticated identity with fingerprint for logging."""

    user: str
    roles: List[str]
    fingerprint: str

    def has_role(self, role: str) -> bool:
        """Check if identity has a specific role."""
        return role in self.roles

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "user": self.user,
            "roles": self.roles,
            "fingerprint": self.fingerprint,
        }


def validate_token(token: str) -> Identity:
    """Validate a token and return Identity with fingerprint.

    Delegates to lib.auth.HmacAuthProvider.authenticate().

    Args:
        token: Authentication token in format "user:signature"

    Returns:
        Identity with user, roles, and token fingerprint

    Raises:
        AuthError: If token is invalid or authentication fails
    """
    if not token:
        raise AuthError(
            "Token required",
            code="TOKEN_REQUIRED",
        )

    try:
        provider = get_provider()
        lib_identity = provider.authenticate(token)

        if lib_identity is None:
            raise AuthError(
                "Invalid token",
                code="INVALID_TOKEN",
                details={"fingerprint": fingerprint_secret(token)},
            )

        return Identity(
            user=lib_identity.user,
            roles=lib_identity.roles,
            fingerprint=fingerprint_secret(token),
        )

    except AuthError:
        raise
    except Exception as e:
        raise AuthError(
            f"Authentication failed: {e}",
            code="AUTH_FAILED",
        )


def require_role(identity: Identity, role: str) -> None:
    """Require that identity has a specific role.

    Args:
        identity: Authenticated identity
        role: Required role name

    Raises:
        AuthError: If identity lacks the required role
    """
    if not identity.has_role(role):
        raise AuthError(
            f"Role required: {role}",
            code="ROLE_REQUIRED",
            details={
                "required_role": role,
                "user": identity.user,
                "user_roles": identity.roles,
            },
        )
