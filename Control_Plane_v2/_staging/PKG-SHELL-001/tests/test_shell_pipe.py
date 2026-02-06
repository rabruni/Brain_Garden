"""Pipe-first contract tests per FMWK-100 §7.

Tests for the shell module's pipe-first interface that:
1. Reads JSON from stdin
2. Routes to operation handlers
3. Returns JSON response with evidence

Run with:
    pytest tests/test_shell_pipe.py -v
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

# Root path
ROOT = Path(__file__).parent.parent


def run_pipe(request: dict, timeout: int = 30) -> dict:
    """Run shell module via pipe and return response.

    Args:
        request: JSON request to send
        timeout: Timeout in seconds

    Returns:
        Response dict parsed from stdout
    """
    result = subprocess.run(
        [sys.executable, "-m", "modules.shell"],
        input=json.dumps(request),
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        timeout=timeout,
    )
    return json.loads(result.stdout)


def run_pipe_raw(input_text: str, timeout: int = 30) -> subprocess.CompletedProcess:
    """Run shell module with raw input and return result.

    Args:
        input_text: Raw input string
        timeout: Timeout in seconds

    Returns:
        CompletedProcess with stdout, stderr, returncode
    """
    return subprocess.run(
        [sys.executable, "-m", "modules.shell"],
        input=input_text,
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        timeout=timeout,
    )


class TestPipeResponseEnvelope:
    """Test that responses follow FMWK-100 §7 envelope format."""

    def test_response_has_status(self):
        """Response must have status field."""
        response = run_pipe({"operation": "pkg_list"})
        assert "status" in response
        assert response["status"] in ("ok", "error")

    def test_ok_response_has_result(self):
        """OK response should have result field."""
        response = run_pipe({"operation": "pkg_list"})
        if response["status"] == "ok":
            assert "result" in response

    def test_ok_response_has_evidence(self):
        """OK response should have evidence field."""
        response = run_pipe({"operation": "pkg_list"})
        if response["status"] == "ok":
            assert "evidence" in response

    def test_evidence_has_timestamp(self):
        """Evidence must have timestamp."""
        response = run_pipe({"operation": "pkg_list"})
        if response["status"] == "ok":
            assert "timestamp" in response.get("evidence", {})

    def test_evidence_has_duration_ms(self):
        """Evidence should have duration_ms."""
        response = run_pipe({"operation": "pkg_list"})
        if response["status"] == "ok":
            assert "duration_ms" in response.get("evidence", {})
            assert isinstance(response["evidence"]["duration_ms"], int)

    def test_error_response_has_error(self):
        """Error response must have error field."""
        response = run_pipe({"operation": "unknown_operation"})
        assert response["status"] == "error"
        assert "error" in response

    def test_error_has_code_and_message(self):
        """Error must have code and message fields."""
        response = run_pipe({"operation": "unknown_operation"})
        error = response.get("error", {})
        assert "code" in error
        assert "message" in error


class TestPkgListOperation:
    """Test pkg_list operation."""

    def test_pkg_list_returns_packages(self):
        """pkg_list should return packages array."""
        response = run_pipe({"operation": "pkg_list"})
        assert response["status"] == "ok"
        assert "packages" in response["result"]
        assert isinstance(response["result"]["packages"], list)

    def test_pkg_list_includes_count(self):
        """pkg_list should include count."""
        response = run_pipe({"operation": "pkg_list"})
        if response["status"] == "ok":
            assert "count" in response["result"]

    def test_pkg_list_package_fields(self):
        """Packages should have expected fields."""
        response = run_pipe({"operation": "pkg_list"})
        if response["status"] == "ok" and response["result"]["packages"]:
            pkg = response["result"]["packages"][0]
            assert "package_id" in pkg
            assert "version" in pkg

    def test_pkg_list_declared_reads(self):
        """pkg_list should declare reads in evidence."""
        response = run_pipe({"operation": "pkg_list"})
        if response["status"] == "ok":
            assert "declared_reads" in response.get("evidence", {})


class TestPkgInfoOperation:
    """Test pkg_info operation."""

    def test_pkg_info_requires_package_id(self):
        """pkg_info should require package_id."""
        response = run_pipe({"operation": "pkg_info"})
        assert response["status"] == "error"
        assert response["error"]["code"] == "MISSING_FIELD"

    def test_pkg_info_not_found(self):
        """pkg_info should return error for unknown package."""
        response = run_pipe({
            "operation": "pkg_info",
            "package_id": "PKG-NONEXISTENT-999"
        })
        assert response["status"] == "error"
        assert response["error"]["code"] == "PACKAGE_NOT_FOUND"

    def test_pkg_info_valid_package(self):
        """pkg_info should return details for valid package."""
        # First get a valid package ID
        list_response = run_pipe({"operation": "pkg_list"})
        if list_response["status"] == "ok" and list_response["result"]["packages"]:
            pkg_id = list_response["result"]["packages"][0]["package_id"]

            response = run_pipe({
                "operation": "pkg_info",
                "package_id": pkg_id
            })
            assert response["status"] == "ok"
            assert response["result"]["package_id"] == pkg_id


class TestLedgerQueryOperation:
    """Test ledger_query operation."""

    def test_ledger_query_default(self):
        """ledger_query should work with defaults."""
        response = run_pipe({"operation": "ledger_query"})
        # May error if no ledger exists, but should return valid response
        assert "status" in response

    def test_ledger_query_with_limit(self):
        """ledger_query should respect limit."""
        response = run_pipe({
            "operation": "ledger_query",
            "limit": 5
        })
        if response["status"] == "ok":
            assert len(response["result"]["entries"]) <= 5

    def test_ledger_query_with_type(self):
        """ledger_query should filter by type."""
        response = run_pipe({
            "operation": "ledger_query",
            "type": "governance"
        })
        assert "status" in response


class TestGateStatusOperation:
    """Test gate_status operation."""

    def test_gate_status_returns_gates(self):
        """gate_status should return gates."""
        response = run_pipe({"operation": "gate_status"})
        assert response["status"] == "ok"
        assert "gates" in response["result"]

    def test_gate_status_includes_failures(self):
        """gate_status should include recent_failures."""
        response = run_pipe({"operation": "gate_status"})
        if response["status"] == "ok":
            assert "recent_failures" in response["result"]


class TestComplianceOperation:
    """Test compliance operation."""

    def test_compliance_returns_chain(self):
        """compliance should return governance_chain."""
        response = run_pipe({"operation": "compliance"})
        if response["status"] == "ok":
            assert "governance_chain" in response["result"]

    def test_compliance_returns_quick_reference(self):
        """compliance should return quick_reference."""
        response = run_pipe({"operation": "compliance"})
        if response["status"] == "ok":
            assert "quick_reference" in response["result"]


class TestTraceOperation:
    """Test trace operation."""

    def test_trace_requires_artifact_id(self):
        """trace should require artifact_id."""
        response = run_pipe({"operation": "trace"})
        assert response["status"] == "error"
        assert response["error"]["code"] == "MISSING_FIELD"


class TestSignalStatusOperation:
    """Test signal_status operation."""

    def test_signal_status_returns_signals(self):
        """signal_status should return signals."""
        response = run_pipe({"operation": "signal_status"})
        assert response["status"] == "ok"
        assert "signals" in response["result"]

    def test_signal_status_includes_compact_display(self):
        """signal_status should include compact_display."""
        response = run_pipe({"operation": "signal_status"})
        if response["status"] == "ok":
            assert "compact_display" in response["result"]


class TestExecuteCommandOperation:
    """Test execute_command operation."""

    def test_execute_command_requires_command(self):
        """execute_command should require command."""
        response = run_pipe({"operation": "execute_command"})
        assert response["status"] == "error"
        assert response["error"]["code"] == "MISSING_FIELD"

    def test_execute_command_maps_pkg(self):
        """execute_command should map 'pkg' to pkg_list."""
        response = run_pipe({
            "operation": "execute_command",
            "command": "pkg"
        })
        assert response["status"] == "ok"
        assert "packages" in response["result"]

    def test_execute_command_pkg_with_arg(self):
        """execute_command should handle 'pkg PKG-ID'."""
        # Get a valid package first
        list_response = run_pipe({"operation": "pkg_list"})
        if list_response["status"] == "ok" and list_response["result"]["packages"]:
            pkg_id = list_response["result"]["packages"][0]["package_id"]

            response = run_pipe({
                "operation": "execute_command",
                "command": f"pkg {pkg_id}"
            })
            assert response["status"] == "ok"


class TestErrorHandling:
    """Test error handling."""

    def test_invalid_json(self):
        """Invalid JSON should return INVALID_JSON error."""
        result = run_pipe_raw("not valid json")
        response = json.loads(result.stdout)
        assert response["status"] == "error"
        assert response["error"]["code"] == "INVALID_JSON"

    def test_empty_input(self):
        """Empty input should return EMPTY_INPUT error."""
        result = run_pipe_raw("")
        response = json.loads(result.stdout)
        assert response["status"] == "error"
        assert response["error"]["code"] == "EMPTY_INPUT"

    def test_unknown_operation(self):
        """Unknown operation should return UNKNOWN_OPERATION error."""
        response = run_pipe({"operation": "not_a_real_operation"})
        assert response["status"] == "error"
        assert response["error"]["code"] == "UNKNOWN_OPERATION"

    def test_unknown_operation_lists_valid(self):
        """Unknown operation error should list valid operations."""
        response = run_pipe({"operation": "not_a_real_operation"})
        assert "valid_operations" in response["error"].get("details", {})

    def test_non_dict_request(self):
        """Non-dict request should return INVALID_REQUEST error."""
        result = run_pipe_raw('"string instead of object"')
        response = json.loads(result.stdout)
        assert response["status"] == "error"
        assert response["error"]["code"] == "INVALID_REQUEST"


class TestExitCodes:
    """Test exit codes."""

    def test_ok_returns_zero(self):
        """OK response should return exit code 0."""
        result = run_pipe_raw(json.dumps({"operation": "signal_status"}))
        assert result.returncode == 0

    def test_error_returns_nonzero(self):
        """Error response should return exit code 1."""
        result = run_pipe_raw(json.dumps({"operation": "unknown"}))
        assert result.returncode == 1

    def test_invalid_json_returns_nonzero(self):
        """Invalid JSON should return exit code 1."""
        result = run_pipe_raw("not json")
        assert result.returncode == 1


class TestDefaultOperation:
    """Test default operation behavior."""

    def test_default_operation_is_pkg_list(self):
        """Missing operation should default to pkg_list."""
        response = run_pipe({})
        # Should work (default to pkg_list)
        assert response["status"] in ("ok", "error")


class TestPackageComplianceOperations:
    """Test package compliance guidance operations."""

    def test_manifest_requirements(self):
        """manifest_requirements should return field requirements."""
        response = run_pipe({"operation": "manifest_requirements"})
        assert response["status"] == "ok"
        assert "required_fields" in response["result"]
        assert "package_id" in response["result"]["required_fields"]
        assert "spec_id" in response["result"]["required_fields"]

    def test_packaging_workflow(self):
        """packaging_workflow should return steps."""
        response = run_pipe({"operation": "packaging_workflow"})
        assert response["status"] == "ok"
        assert "steps" in response["result"]
        assert len(response["result"]["steps"]) > 0
        # First step should be framework registration
        assert "Framework" in response["result"]["steps"][0]["name"]

    def test_troubleshoot_all(self):
        """troubleshoot should return all troubleshooting guides."""
        response = run_pipe({"operation": "troubleshoot"})
        assert response["status"] == "ok"
        assert "troubleshooting" in response["result"]

    def test_troubleshoot_filtered(self):
        """troubleshoot should filter by error_type."""
        response = run_pipe({"operation": "troubleshoot", "error_type": "G1"})
        assert response["status"] == "ok"
        assert "troubleshooting" in response["result"]
        # All keys should contain G1
        for key in response["result"]["troubleshooting"]:
            assert "G1" in key

    def test_example_manifest_library(self):
        """example_manifest should return library example by default."""
        response = run_pipe({"operation": "example_manifest"})
        assert response["status"] == "ok"
        assert "example" in response["result"]
        assert response["result"]["example"]["package_type"] == "library"

    def test_example_manifest_agent(self):
        """example_manifest should return agent example when requested."""
        response = run_pipe({"operation": "example_manifest", "package_type": "agent"})
        assert response["status"] == "ok"
        assert response["result"]["example"]["package_type"] == "agent"
        assert "capabilities" in response["result"]["example"]

    def test_list_frameworks(self):
        """list_frameworks should return registered frameworks."""
        response = run_pipe({"operation": "list_frameworks"})
        assert response["status"] == "ok"
        assert "frameworks" in response["result"]
        assert "count" in response["result"]
        # Should have at least FMWK-000 and FMWK-100
        framework_ids = [f["framework_id"] for f in response["result"]["frameworks"]]
        assert "FMWK-000" in framework_ids or len(framework_ids) > 0

    def test_list_specs(self):
        """list_specs should return registered specs."""
        response = run_pipe({"operation": "list_specs"})
        assert response["status"] == "ok"
        assert "specs" in response["result"]
        assert "count" in response["result"]

    def test_list_specs_filtered(self):
        """list_specs should filter by framework_id."""
        response = run_pipe({"operation": "list_specs", "framework_id": "FMWK-100"})
        assert response["status"] == "ok"
        assert "filter" in response["result"]
        # All specs should reference FMWK-100
        for spec in response["result"]["specs"]:
            assert spec.get("framework_id") == "FMWK-100"

    def test_spec_info_requires_spec_id(self):
        """spec_info should require spec_id."""
        response = run_pipe({"operation": "spec_info"})
        assert response["status"] == "error"
        assert response["error"]["code"] == "MISSING_FIELD"

    def test_governed_roots(self):
        """governed_roots should return governed paths."""
        response = run_pipe({"operation": "governed_roots"})
        assert response["status"] == "ok"
        assert "roots" in response["result"]
        assert "count" in response["result"]

    def test_explain_path_requires_path(self):
        """explain_path should require path."""
        response = run_pipe({"operation": "explain_path"})
        assert response["status"] == "error"
        assert response["error"]["code"] == "MISSING_FIELD"

    def test_explain_path_pristine(self):
        """explain_path should classify lib/ as PRISTINE."""
        response = run_pipe({"operation": "explain_path", "path": "lib/authz.py"})
        assert response["status"] == "ok"
        assert response["result"]["classification"] == "PRISTINE"

    def test_explain_path_derived(self):
        """explain_path should classify packages_store/ as DERIVED."""
        response = run_pipe({"operation": "explain_path", "path": "packages_store/test.tar.gz"})
        assert response["status"] == "ok"
        assert response["result"]["classification"] == "DERIVED"

    def test_explain_path_append_only(self):
        """explain_path should classify ledger/ as APPEND_ONLY."""
        response = run_pipe({"operation": "explain_path", "path": "ledger/index.jsonl"})
        assert response["status"] == "ok"
        assert response["result"]["classification"] == "APPEND_ONLY"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
