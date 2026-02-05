"""Pipe-first integration tests for the Evidence Emission Standard Library."""

import json
import subprocess
import sys
from pathlib import Path

import pytest


# Get Control Plane root
CONTROL_PLANE_ROOT = Path(__file__).parent.parent


class TestCLIBuildEvidence:
    """Tests for CLI build_evidence operation."""

    def test_success_response(self):
        """CLI returns success envelope for valid input."""
        input_json = json.dumps({
            "operation": "build_evidence",
            "session_id": "SES-123",
            "turn_number": 1,
            "input": {"query": "test"},
            "output": {"result": "ok"}
        })
        result = subprocess.run(
            [sys.executable, "-m", "modules.stdlib_evidence"],
            input=input_json,
            capture_output=True,
            text=True,
            cwd=str(CONTROL_PLANE_ROOT)
        )
        assert result.returncode == 0
        response = json.loads(result.stdout)
        assert response["status"] == "ok"
        assert "evidence" in response
        assert "input_hash" in response["result"]
        assert "output_hash" in response["result"]

    def test_with_work_order(self):
        """CLI includes work_order_id in evidence."""
        input_json = json.dumps({
            "operation": "build_evidence",
            "session_id": "SES-123",
            "turn_number": 1,
            "input": {},
            "output": {},
            "work_order_id": "WO-456"
        })
        result = subprocess.run(
            [sys.executable, "-m", "modules.stdlib_evidence"],
            input=input_json,
            capture_output=True,
            text=True,
            cwd=str(CONTROL_PLANE_ROOT)
        )
        assert result.returncode == 0
        response = json.loads(result.stdout)
        assert response["evidence"]["work_order_id"] == "WO-456"

    def test_missing_session_id(self):
        """CLI returns error for missing session_id."""
        input_json = json.dumps({
            "operation": "build_evidence",
            "turn_number": 1,
            "input": {},
            "output": {}
        })
        result = subprocess.run(
            [sys.executable, "-m", "modules.stdlib_evidence"],
            input=input_json,
            capture_output=True,
            text=True,
            cwd=str(CONTROL_PLANE_ROOT)
        )
        assert result.returncode == 1
        response = json.loads(result.stdout)
        assert response["status"] == "error"
        assert response["error"]["code"] == "MISSING_FIELD"


class TestCLIHash:
    """Tests for CLI hash operation."""

    def test_hash_object(self):
        """CLI hashes JSON object correctly."""
        input_json = json.dumps({
            "operation": "hash",
            "data": {"key": "value"}
        })
        result = subprocess.run(
            [sys.executable, "-m", "modules.stdlib_evidence"],
            input=input_json,
            capture_output=True,
            text=True,
            cwd=str(CONTROL_PLANE_ROOT)
        )
        assert result.returncode == 0
        response = json.loads(result.stdout)
        assert response["status"] == "ok"
        assert response["result"]["hash"].startswith("sha256:")

    def test_hash_missing_data(self):
        """CLI returns error for missing data."""
        input_json = json.dumps({
            "operation": "hash"
        })
        result = subprocess.run(
            [sys.executable, "-m", "modules.stdlib_evidence"],
            input=input_json,
            capture_output=True,
            text=True,
            cwd=str(CONTROL_PLANE_ROOT)
        )
        assert result.returncode == 1
        response = json.loads(result.stdout)
        assert response["status"] == "error"


class TestCLIReference:
    """Tests for CLI reference operation."""

    def test_build_reference(self):
        """CLI builds reference correctly."""
        input_json = json.dumps({
            "operation": "reference",
            "artifact_id": "PKG-001",
            "hash": "sha256:abc123"
        })
        result = subprocess.run(
            [sys.executable, "-m", "modules.stdlib_evidence"],
            input=input_json,
            capture_output=True,
            text=True,
            cwd=str(CONTROL_PLANE_ROOT)
        )
        assert result.returncode == 0
        response = json.loads(result.stdout)
        assert response["status"] == "ok"
        assert response["result"]["reference"]["artifact_id"] == "PKG-001"


class TestCLIErrors:
    """Tests for CLI error handling."""

    def test_invalid_json(self):
        """CLI returns error envelope for invalid JSON."""
        result = subprocess.run(
            [sys.executable, "-m", "modules.stdlib_evidence"],
            input="not valid json",
            capture_output=True,
            text=True,
            cwd=str(CONTROL_PLANE_ROOT)
        )
        assert result.returncode == 1
        response = json.loads(result.stdout)
        assert response["status"] == "error"
        assert response["error"]["code"] == "INVALID_JSON"

    def test_unknown_operation(self):
        """CLI returns error for unknown operation."""
        input_json = json.dumps({
            "operation": "unknown_op"
        })
        result = subprocess.run(
            [sys.executable, "-m", "modules.stdlib_evidence"],
            input=input_json,
            capture_output=True,
            text=True,
            cwd=str(CONTROL_PLANE_ROOT)
        )
        assert result.returncode == 1
        response = json.loads(result.stdout)
        assert response["status"] == "error"
        assert response["error"]["code"] == "UNKNOWN_OPERATION"


class TestCLINoSideEffects:
    """Tests for CLI side effects."""

    def test_no_files_created(self, tmp_path):
        """CLI creates no files."""
        before_files = set(tmp_path.rglob("*"))
        subprocess.run(
            [sys.executable, "-m", "modules.stdlib_evidence"],
            input='{"operation": "build_evidence", "session_id": "SES-1", "turn_number": 1, "input": {}, "output": {}}',
            capture_output=True,
            text=True,
            cwd=str(tmp_path)
        )
        after_files = set(tmp_path.rglob("*"))
        assert before_files == after_files
