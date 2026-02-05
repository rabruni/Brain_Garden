"""Tests for stdlib_auth pipe CLI."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


CONTROL_PLANE = Path(__file__).parent.parent


def run_pipe(input_data: dict) -> dict:
    """Run stdlib_auth via pipe and return response."""
    env = os.environ.copy()
    env["CONTROL_PLANE_AUTH_PROVIDER"] = "passthrough"
    env["CONTROL_PLANE_ALLOW_PASSTHROUGH"] = "1"

    result = subprocess.run(
        [sys.executable, "-m", "modules.stdlib_auth"],
        input=json.dumps(input_data),
        capture_output=True,
        text=True,
        cwd=str(CONTROL_PLANE),
        env=env,
    )
    return json.loads(result.stdout)


class TestPipeValidateToken:
    """Tests for validate_token via pipe."""

    def test_validate_token_success(self):
        """validate_token via pipe returns identity."""
        response = run_pipe({
            "operation": "validate_token",
            "token": "user:signature",
        })
        assert response["status"] == "ok"
        assert "user" in response["result"]
        assert "roles" in response["result"]
        assert "fingerprint" in response["result"]
        assert response["result"]["fingerprint"].startswith("fp:sha256:")

    def test_validate_token_missing_token(self):
        """Missing token returns error."""
        response = run_pipe({
            "operation": "validate_token",
        })
        assert response["status"] == "error"
        assert response["error"]["code"] == "MISSING_FIELD"

    def test_validate_token_evidence(self):
        """validate_token includes evidence."""
        response = run_pipe({
            "operation": "validate_token",
            "token": "user:signature",
        })
        assert "evidence" in response
        assert "timestamp" in response["evidence"]
        assert "auth" in response["evidence"]
        assert "token_fingerprint" in response["evidence"]["auth"]


class TestPipeFingerprint:
    """Tests for fingerprint via pipe."""

    def test_fingerprint_success(self):
        """fingerprint via pipe returns hash."""
        response = run_pipe({
            "operation": "fingerprint",
            "secret": "my-secret-key",
        })
        assert response["status"] == "ok"
        assert response["result"]["fingerprint"].startswith("fp:sha256:")

    def test_fingerprint_empty(self):
        """Empty secret returns special marker."""
        response = run_pipe({
            "operation": "fingerprint",
            "secret": "",
        })
        assert response["status"] == "ok"
        assert response["result"]["fingerprint"] == "fp:sha256:empty"

    def test_fingerprint_missing_secret(self):
        """Missing secret returns error."""
        response = run_pipe({
            "operation": "fingerprint",
        })
        assert response["status"] == "error"
        assert response["error"]["code"] == "MISSING_FIELD"


class TestPipeRequireRole:
    """Tests for require_role via pipe."""

    def test_require_role_granted(self):
        """require_role granted returns success."""
        response = run_pipe({
            "operation": "require_role",
            "identity": {
                "user": "alice",
                "roles": ["admin", "reader"],
                "fingerprint": "fp:sha256:abc123",
            },
            "role": "admin",
        })
        assert response["status"] == "ok"
        assert response["result"]["granted"] is True
        assert response["result"]["role"] == "admin"

    def test_require_role_denied(self):
        """require_role denied returns error."""
        response = run_pipe({
            "operation": "require_role",
            "identity": {
                "user": "alice",
                "roles": ["reader"],
                "fingerprint": "fp:sha256:abc123",
            },
            "role": "admin",
        })
        assert response["status"] == "error"
        assert response["error"]["code"] == "ROLE_REQUIRED"

    def test_require_role_missing_identity(self):
        """Missing identity returns error."""
        response = run_pipe({
            "operation": "require_role",
            "role": "admin",
        })
        assert response["status"] == "error"
        assert response["error"]["code"] == "MISSING_FIELD"


class TestPipeUnknownOperation:
    """Tests for unknown operations."""

    def test_unknown_operation(self):
        """Unknown operation returns error."""
        response = run_pipe({
            "operation": "unknown_op",
        })
        assert response["status"] == "error"
        assert response["error"]["code"] == "UNKNOWN_OPERATION"
        assert "valid_operations" in response["error"]["details"]


class TestPipeEvidence:
    """Tests for evidence in responses."""

    def test_evidence_has_duration(self):
        """Successful operations include duration."""
        response = run_pipe({
            "operation": "fingerprint",
            "secret": "test",
        })
        assert response["status"] == "ok"
        assert "duration_ms" in response["evidence"]
        assert isinstance(response["evidence"]["duration_ms"], int)
