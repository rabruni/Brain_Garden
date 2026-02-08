#!/usr/bin/env python3
"""
test_authz.py - Tests for authorization helper.

Verifies:
1. Empty or None identity must raise PermissionError
2. Identity without required role must raise PermissionError
3. Valid identity with correct role should pass
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kernel.authz import is_authorized, require
from kernel.auth import Identity


class TestRequire:
    """Test the require function."""

    def test_none_identity_raises(self):
        """None identity must raise PermissionError."""
        with pytest.raises(PermissionError, match="Auth required"):
            require(None, "install")

    def test_empty_roles_raises(self):
        """Identity with no roles must raise PermissionError."""
        identity = Identity(user="test-user", roles=[])
        with pytest.raises(PermissionError, match="not permitted"):
            require(identity, "install")

    def test_wrong_role_raises(self):
        """Identity with wrong role must raise PermissionError."""
        identity = Identity(user="test-user", roles=["reader"])
        with pytest.raises(PermissionError, match="not permitted"):
            require(identity, "install")  # reader can only verify

    def test_valid_role_passes(self):
        """Identity with correct role should pass."""
        identity = Identity(user="test-user", roles=["admin"])
        # Should not raise
        require(identity, "install")

    def test_maintainer_can_install(self):
        """Maintainer role can install."""
        identity = Identity(user="test-user", roles=["maintainer"])
        require(identity, "install")

    def test_auditor_can_only_verify(self):
        """Auditor role can only verify."""
        identity = Identity(user="test-user", roles=["auditor"])
        require(identity, "verify")

        with pytest.raises(PermissionError):
            require(identity, "install")


class TestIsAuthorized:
    """Test the is_authorized function."""

    def test_admin_has_all_actions(self):
        """Admin should have all actions."""
        identity = Identity(user="admin", roles=["admin"])
        assert is_authorized(identity, "install")
        assert is_authorized(identity, "uninstall")
        assert is_authorized(identity, "checkpoint")
        assert is_authorized(identity, "rollback")

    def test_reader_has_only_verify(self):
        """Reader should only have verify."""
        identity = Identity(user="reader", roles=["reader"])
        assert is_authorized(identity, "verify")
        assert not is_authorized(identity, "install")
        assert not is_authorized(identity, "pack")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
