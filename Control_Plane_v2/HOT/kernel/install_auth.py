#!/usr/bin/env python3
"""
install_auth.py - IAM authorization for package installation operations.

Implements InstallerClaims with plane-scoped permissions for:
- install, uninstall, recover, doctor_fix actions
- Tier-based access control (G0, T0, T1, T2, T3)
- Plane-based access control (hot, first, second)
- Package-specific allowlisting

Per Plane-Aware Package System design.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional, Set, List

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kernel.auth import Identity, get_provider
from kernel.authz import ROLE_ACTIONS


class InstallAction(str, Enum):
    """Actions that can be performed on packages."""
    INSTALL = "install"
    UNINSTALL = "uninstall"
    RECOVER = "recover"
    DOCTOR_FIX = "doctor_fix"
    VERIFY = "verify"
    PACK = "pack"
    SIGN = "sign"


# Default tiers
DEFAULT_TIERS = {"G0", "T0", "T1", "T2", "T3"}

# Default planes
DEFAULT_PLANES = {"hot", "first", "second"}


@dataclass
class InstallerClaims:
    """Authorization claims for package installation operations.

    Attributes:
        subject: User or service account identifier
        roles: List of roles (admin, maintainer, auditor, reader)
        allowed_actions: Set of permitted actions
        allowed_tiers: Set of permitted tiers (G0, T0, T1, T2, T3)
        allowed_packages: Optional allowlist of specific package IDs
        allowed_planes: Set of permitted planes (hot, first, second)
        env: Environment (dev, staging, prod)
    """
    subject: str
    roles: List[str] = field(default_factory=list)
    allowed_actions: Set[str] = field(default_factory=set)
    allowed_tiers: Set[str] = field(default_factory=lambda: DEFAULT_TIERS.copy())
    allowed_packages: Optional[Set[str]] = None
    allowed_planes: Set[str] = field(default_factory=lambda: DEFAULT_PLANES.copy())
    env: str = "dev"

    @classmethod
    def from_identity(cls, identity: Identity, env: str = "dev") -> "InstallerClaims":
        """Create InstallerClaims from an authenticated Identity.

        Maps roles to default allowed actions, tiers, and planes.

        Args:
            identity: Authenticated Identity object
            env: Environment context (dev, staging, prod)

        Returns:
            InstallerClaims with permissions derived from roles
        """
        allowed_actions = set()
        for role in identity.roles:
            role_actions = ROLE_ACTIONS.get(role, set())
            allowed_actions.update(role_actions)

        # Admin gets all planes; others get restricted based on env
        allowed_planes = DEFAULT_PLANES.copy()
        if "admin" not in identity.roles:
            if env == "prod":
                # In production, non-admins cannot touch HOT plane
                allowed_planes.discard("hot")

        # Build claims
        return cls(
            subject=identity.user,
            roles=list(identity.roles),
            allowed_actions=allowed_actions,
            allowed_tiers=DEFAULT_TIERS.copy(),
            allowed_packages=None,  # No package restrictions by default
            allowed_planes=allowed_planes,
            env=env,
        )

    @classmethod
    def from_token(cls, token: Optional[str] = None, env: str = "dev") -> "InstallerClaims":
        """Create InstallerClaims from a token string.

        Args:
            token: Auth token (or reads from CONTROL_PLANE_TOKEN env)
            env: Environment context

        Returns:
            InstallerClaims derived from token authentication

        Raises:
            PermissionError: If authentication fails
        """
        token = token or os.getenv("CONTROL_PLANE_TOKEN")
        provider = get_provider()
        identity = provider.authenticate(token)

        if identity is None:
            raise PermissionError("Authentication failed")

        return cls.from_identity(identity, env)

    def can_perform(
        self,
        action: str,
        tier: Optional[str] = None,
        plane: Optional[str] = None,
        package_id: Optional[str] = None,
    ) -> bool:
        """Check if the claims allow a specific operation.

        Args:
            action: Action to perform (install, uninstall, etc.)
            tier: Package tier (G0, T0, T1, T2, T3)
            plane: Target plane (hot, first, second)
            package_id: Specific package ID

        Returns:
            True if the operation is permitted
        """
        # Check action
        if action.lower() not in self.allowed_actions:
            return False

        # Check tier
        if tier and tier.upper() not in self.allowed_tiers:
            return False

        # Check plane
        if plane and plane.lower() not in self.allowed_planes:
            return False

        # Check package allowlist
        if self.allowed_packages is not None and package_id:
            if package_id not in self.allowed_packages:
                return False

        return True

    def require(
        self,
        action: str,
        tier: Optional[str] = None,
        plane: Optional[str] = None,
        package_id: Optional[str] = None,
    ) -> None:
        """Assert that an operation is permitted, raising if not.

        Args:
            action: Action to perform
            tier: Package tier
            plane: Target plane
            package_id: Specific package ID

        Raises:
            PermissionError: If the operation is not permitted
        """
        if not self.can_perform(action, tier, plane, package_id):
            denied_reasons = []

            if action.lower() not in self.allowed_actions:
                denied_reasons.append(f"action '{action}' not in allowed_actions")

            if tier and tier.upper() not in self.allowed_tiers:
                denied_reasons.append(f"tier '{tier}' not in allowed_tiers")

            if plane and plane.lower() not in self.allowed_planes:
                denied_reasons.append(f"plane '{plane}' not in allowed_planes")

            if self.allowed_packages is not None and package_id:
                if package_id not in self.allowed_packages:
                    denied_reasons.append(f"package '{package_id}' not in allowed_packages")

            reason = "; ".join(denied_reasons) if denied_reasons else "permission denied"
            raise PermissionError(
                f"Action '{action}' denied for subject '{self.subject}': {reason}"
            )

    def with_plane_restriction(self, planes: Set[str]) -> "InstallerClaims":
        """Create a new claims object with restricted plane access.

        Args:
            planes: Set of planes to restrict to

        Returns:
            New InstallerClaims with intersection of current and provided planes
        """
        return InstallerClaims(
            subject=self.subject,
            roles=self.roles.copy(),
            allowed_actions=self.allowed_actions.copy(),
            allowed_tiers=self.allowed_tiers.copy(),
            allowed_packages=self.allowed_packages.copy() if self.allowed_packages else None,
            allowed_planes=self.allowed_planes & planes,
            env=self.env,
        )

    def with_tier_restriction(self, tiers: Set[str]) -> "InstallerClaims":
        """Create a new claims object with restricted tier access.

        Args:
            tiers: Set of tiers to restrict to

        Returns:
            New InstallerClaims with intersection of current and provided tiers
        """
        return InstallerClaims(
            subject=self.subject,
            roles=self.roles.copy(),
            allowed_actions=self.allowed_actions.copy(),
            allowed_tiers=self.allowed_tiers & {t.upper() for t in tiers},
            allowed_packages=self.allowed_packages.copy() if self.allowed_packages else None,
            allowed_planes=self.allowed_planes.copy(),
            env=self.env,
        )

    def with_package_allowlist(self, packages: Set[str]) -> "InstallerClaims":
        """Create a new claims object with package allowlist.

        Args:
            packages: Set of allowed package IDs

        Returns:
            New InstallerClaims with package restriction
        """
        return InstallerClaims(
            subject=self.subject,
            roles=self.roles.copy(),
            allowed_actions=self.allowed_actions.copy(),
            allowed_tiers=self.allowed_tiers.copy(),
            allowed_packages=packages.copy(),
            allowed_planes=self.allowed_planes.copy(),
            env=self.env,
        )

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "subject": self.subject,
            "roles": self.roles,
            "allowed_actions": sorted(self.allowed_actions),
            "allowed_tiers": sorted(self.allowed_tiers),
            "allowed_packages": sorted(self.allowed_packages) if self.allowed_packages else None,
            "allowed_planes": sorted(self.allowed_planes),
            "env": self.env,
        }


def authorize(
    action: str,
    pkg_id: str,
    tier: str,
    env: str,
    claims: InstallerClaims,
    plane: str,
) -> bool:
    """Authorize a package operation.

    Fail if plane not in claims.allowed_planes.

    Args:
        action: Action to perform (install, uninstall, etc.)
        pkg_id: Package ID
        tier: Package tier (G0, T0, T1, T2, T3)
        env: Environment (dev, staging, prod)
        claims: InstallerClaims with permissions
        plane: Target plane (hot, first, second)

    Returns:
        True if authorized

    Note:
        This function does not raise - use claims.require() for that behavior.
    """
    # Environment check - stricter in prod
    if env == "prod" and claims.env != "prod":
        return False

    return claims.can_perform(
        action=action,
        tier=tier,
        plane=plane,
        package_id=pkg_id,
    )


def require_authorization(
    action: str,
    pkg_id: str,
    tier: str,
    env: str,
    claims: InstallerClaims,
    plane: str,
) -> None:
    """Assert authorization for a package operation.

    Args:
        action: Action to perform
        pkg_id: Package ID
        tier: Package tier
        env: Environment
        claims: InstallerClaims with permissions
        plane: Target plane

    Raises:
        PermissionError: If not authorized
    """
    claims.require(
        action=action,
        tier=tier,
        plane=plane,
        package_id=pkg_id,
    )
