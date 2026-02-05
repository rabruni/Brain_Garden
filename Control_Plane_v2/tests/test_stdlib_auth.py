"""Tests for stdlib_auth module."""

import os
import pytest
from unittest.mock import patch

from modules.stdlib_auth import (
    validate_token,
    require_role,
    fingerprint_secret,
    Identity,
    AuthError,
)


class TestFingerprintSecret:
    """Tests for fingerprint_secret function."""

    def test_fingerprint_creates_hash(self):
        """Fingerprint returns sha256 prefix."""
        fp = fingerprint_secret("test-secret")
        assert fp.startswith("fp:sha256:")
        assert len(fp) == len("fp:sha256:") + 16

    def test_fingerprint_empty_string(self):
        """Empty string returns special marker."""
        fp = fingerprint_secret("")
        assert fp == "fp:sha256:empty"

    def test_fingerprint_deterministic(self):
        """Same input produces same fingerprint."""
        fp1 = fingerprint_secret("my-secret")
        fp2 = fingerprint_secret("my-secret")
        assert fp1 == fp2

    def test_fingerprint_different_secrets(self):
        """Different secrets produce different fingerprints."""
        fp1 = fingerprint_secret("secret-1")
        fp2 = fingerprint_secret("secret-2")
        assert fp1 != fp2


class TestIdentity:
    """Tests for Identity dataclass."""

    def test_has_role_true(self):
        """has_role returns True for existing role."""
        identity = Identity(user="alice", roles=["admin", "reader"], fingerprint="fp:...")
        assert identity.has_role("admin") is True
        assert identity.has_role("reader") is True

    def test_has_role_false(self):
        """has_role returns False for missing role."""
        identity = Identity(user="alice", roles=["reader"], fingerprint="fp:...")
        assert identity.has_role("admin") is False

    def test_to_dict(self):
        """to_dict returns proper structure."""
        identity = Identity(user="alice", roles=["admin"], fingerprint="fp:sha256:abc123")
        d = identity.to_dict()
        assert d["user"] == "alice"
        assert d["roles"] == ["admin"]
        assert d["fingerprint"] == "fp:sha256:abc123"


class TestRequireRole:
    """Tests for require_role function."""

    def test_require_role_granted(self):
        """require_role passes for valid role."""
        identity = Identity(user="alice", roles=["admin"], fingerprint="fp:...")
        # Should not raise
        require_role(identity, "admin")

    def test_require_role_denied(self):
        """require_role raises for missing role."""
        identity = Identity(user="alice", roles=["reader"], fingerprint="fp:...")
        with pytest.raises(AuthError) as exc:
            require_role(identity, "admin")
        assert exc.value.code == "ROLE_REQUIRED"
        assert "admin" in exc.value.details["required_role"]


class TestValidateToken:
    """Tests for validate_token function."""

    def test_validate_token_empty(self):
        """Empty token raises AuthError."""
        with pytest.raises(AuthError) as exc:
            validate_token("")
        assert exc.value.code == "TOKEN_REQUIRED"

    def test_validate_token_none(self):
        """None token raises AuthError."""
        with pytest.raises(AuthError) as exc:
            validate_token(None)
        assert exc.value.code == "TOKEN_REQUIRED"

    @patch.dict(os.environ, {
        "CONTROL_PLANE_AUTH_PROVIDER": "passthrough",
        "CONTROL_PLANE_ALLOW_PASSTHROUGH": "1",
    })
    def test_validate_token_passthrough(self):
        """Passthrough provider accepts any token."""
        identity = validate_token("any-token")
        assert identity.user is not None
        assert "admin" in identity.roles
        assert identity.fingerprint.startswith("fp:sha256:")

    @patch("modules.stdlib_auth.validator.get_provider")
    def test_validate_token_invalid(self, mock_get_provider):
        """Invalid token raises AuthError."""
        mock_provider = type("MockProvider", (), {
            "authenticate": lambda self, token: None
        })()
        mock_get_provider.return_value = mock_provider

        with pytest.raises(AuthError) as exc:
            validate_token("invalid:token")
        assert exc.value.code == "INVALID_TOKEN"

    @patch("modules.stdlib_auth.validator.get_provider")
    def test_validate_token_success(self, mock_get_provider):
        """Valid token returns Identity."""
        from lib.auth import Identity as LibIdentity
        mock_provider = type("MockProvider", (), {
            "authenticate": lambda self, token: LibIdentity(user="alice", roles=["admin"])
        })()
        mock_get_provider.return_value = mock_provider

        identity = validate_token("alice:valid-sig")
        assert identity.user == "alice"
        assert identity.roles == ["admin"]
        assert identity.fingerprint.startswith("fp:sha256:")


class TestAuthError:
    """Tests for AuthError exception."""

    def test_auth_error_defaults(self):
        """AuthError has sensible defaults."""
        err = AuthError("test message")
        assert err.message == "test message"
        assert err.code == "AUTH_ERROR"
        assert err.details == {}

    def test_auth_error_with_details(self):
        """AuthError captures details."""
        err = AuthError("test", code="CUSTOM", details={"key": "value"})
        assert err.code == "CUSTOM"
        assert err.details["key"] == "value"
