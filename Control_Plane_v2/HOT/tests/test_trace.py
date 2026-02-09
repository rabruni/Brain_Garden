#!/usr/bin/env python3
"""
Tests for scripts/trace.py - Kernel-Native Trace Capability

Tests the --explain, --inventory, and --verify commands.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
CONTROL_PLANE_ROOT = SCRIPT_DIR.parent          # HOT/
CP_ROOT = CONTROL_PLANE_ROOT.parent             # Control_Plane_v2/
TRACE_SCRIPT = str(CP_ROOT / "HO3" / "scripts" / "trace.py")
sys.path.insert(0, str(CONTROL_PLANE_ROOT))


class TestExplainFramework:
    """Test --explain for frameworks."""

    def test_explain_fmwk_000_returns_framework_info(self):
        """FMWK-000 should return framework with specs and files."""
        result = subprocess.run(
            ["python3", TRACE_SCRIPT, "--explain", "FMWK-000", "--json"],
            cwd=str(CP_ROOT),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["type"] == "framework"
        assert data["data"]["framework_id"] == "FMWK-000"
        assert "specs" in data["data"]
        assert len(data["data"]["specs"]) > 0

    def test_explain_framework_includes_specs(self):
        """Framework explanation should list specs under it."""
        result = subprocess.run(
            ["python3", TRACE_SCRIPT, "--explain", "FMWK-000", "--json"],
            cwd=str(CP_ROOT),
            capture_output=True,
            text=True,
        )
        data = json.loads(result.stdout)
        spec_ids = [s["spec_id"] for s in data["data"]["specs"]]
        assert "SPEC-INT-001" in spec_ids
        assert "SPEC-REG-001" in spec_ids


class TestExplainFile:
    """Test --explain for files."""

    def test_explain_merkle_returns_file_info(self):
        """HOT/kernel/merkle.py should return file with ownership info."""
        result = subprocess.run(
            ["python3", TRACE_SCRIPT, "--explain", "HOT/kernel/merkle.py", "--json"],
            cwd=str(CP_ROOT),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["type"] == "file"
        assert data["data"]["path"] == "HOT/kernel/merkle.py"
        assert data["data"]["ownership"]["package"] == "PKG-KERNEL-001"

    def test_explain_file_includes_hash_verification(self):
        """File explanation should include hash verification status."""
        result = subprocess.run(
            ["python3", TRACE_SCRIPT, "--explain", "HOT/kernel/merkle.py", "--json"],
            cwd=str(CP_ROOT),
            capture_output=True,
            text=True,
        )
        data = json.loads(result.stdout)
        assert "hash" in data["data"]
        assert "verified" in data["data"]["hash"]
        assert data["data"]["hash"]["verified"] is True

    def test_explain_file_includes_functions(self):
        """Python file explanation should list functions."""
        result = subprocess.run(
            ["python3", TRACE_SCRIPT, "--explain", "HOT/kernel/merkle.py", "--json"],
            cwd=str(CP_ROOT),
            capture_output=True,
            text=True,
        )
        data = json.loads(result.stdout)
        func_names = [f["name"] for f in data["data"]["functions"]]
        assert "hash_file" in func_names
        assert "merkle_root" in func_names


class TestExplainPackage:
    """Test --explain for packages."""

    def test_explain_kernel_returns_package_info(self):
        """PKG-KERNEL-001 should return package with files and tier status."""
        result = subprocess.run(
            ["python3", TRACE_SCRIPT, "--explain", "PKG-KERNEL-001", "--json"],
            cwd=str(CP_ROOT),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["type"] == "package"
        assert data["data"]["package_id"] == "PKG-KERNEL-001"

    def test_kernel_includes_tier_status(self):
        """Kernel package should show tier installation status."""
        result = subprocess.run(
            ["python3", TRACE_SCRIPT, "--explain", "PKG-KERNEL-001", "--json"],
            cwd=str(CP_ROOT),
            capture_output=True,
            text=True,
        )
        data = json.loads(result.stdout)
        assert "tier_status" in data["data"]
        assert "HO3" in data["data"]["tier_status"]
        assert data["data"]["tier_status"]["HO3"] == "installed"

    def test_kernel_includes_files(self):
        """Kernel package should list its files."""
        result = subprocess.run(
            ["python3", TRACE_SCRIPT, "--explain", "PKG-KERNEL-001", "--json"],
            cwd=str(CP_ROOT),
            capture_output=True,
            text=True,
        )
        data = json.loads(result.stdout)
        file_paths = [f["path"] for f in data["data"]["files"]]
        assert "HOT/kernel/merkle.py" in file_paths
        assert "HOT/kernel/ledger_client.py" in file_paths

    def test_kernel_parity_status(self):
        """Kernel package should report parity status."""
        result = subprocess.run(
            ["python3", TRACE_SCRIPT, "--explain", "PKG-KERNEL-001", "--json"],
            cwd=str(CP_ROOT),
            capture_output=True,
            text=True,
        )
        data = json.loads(result.stdout)
        assert "parity" in data["data"]
        assert data["data"]["parity"] is True


class TestExplainSpec:
    """Test --explain for specs."""

    def test_explain_spec_returns_spec_info(self):
        """SPEC-INT-001 should return spec with framework and files."""
        result = subprocess.run(
            ["python3", TRACE_SCRIPT, "--explain", "SPEC-INT-001", "--json"],
            cwd=str(CP_ROOT),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["type"] == "spec"
        assert data["data"]["spec_id"] == "SPEC-INT-001"
        assert data["data"]["framework"]["framework_id"] == "FMWK-000"


class TestInventory:
    """Test --inventory command."""

    def test_inventory_returns_valid_output(self):
        """Inventory should return framework list."""
        result = subprocess.run(
            ["python3", TRACE_SCRIPT, "--inventory", "--json"],
            cwd=str(CP_ROOT),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "frameworks" in data
        assert len(data["frameworks"]) > 0

    def test_inventory_includes_total_files(self):
        """Inventory should count total files."""
        result = subprocess.run(
            ["python3", TRACE_SCRIPT, "--inventory", "--json"],
            cwd=str(CP_ROOT),
            capture_output=True,
            text=True,
        )
        data = json.loads(result.stdout)
        assert "total_files" in data
        assert data["total_files"] > 0

    def test_inventory_includes_packages(self):
        """Inventory should list packages."""
        result = subprocess.run(
            ["python3", TRACE_SCRIPT, "--inventory", "--json"],
            cwd=str(CP_ROOT),
            capture_output=True,
            text=True,
        )
        data = json.loads(result.stdout)
        assert "packages" in data


class TestVerify:
    """Test --verify command."""

    def test_verify_returns_check_results(self):
        """Verify should return list of checks."""
        result = subprocess.run(
            ["python3", TRACE_SCRIPT, "--verify", "--json"],
            cwd=str(CP_ROOT),
            capture_output=True,
            text=True,
        )
        # May pass or fail depending on repo state
        data = json.loads(result.stdout)
        assert "checks" in data
        assert len(data["checks"]) > 0

    def test_verify_includes_kernel_parity(self):
        """Verify should check kernel parity."""
        result = subprocess.run(
            ["python3", TRACE_SCRIPT, "--verify", "--json"],
            cwd=str(CP_ROOT),
            capture_output=True,
            text=True,
        )
        data = json.loads(result.stdout)
        check_names = [c["name"] for c in data["checks"]]
        assert "Kernel parity (G0K)" in check_names

    def test_verify_exit_code_matches_result(self):
        """Exit code should be 0 if passed, 1 if failed."""
        result = subprocess.run(
            ["python3", TRACE_SCRIPT, "--verify", "--json"],
            cwd=str(CP_ROOT),
            capture_output=True,
            text=True,
        )
        data = json.loads(result.stdout)
        if data["passed"]:
            assert result.returncode == 0
        else:
            assert result.returncode == 1


class TestJSONOutput:
    """Test JSON output validity."""

    @pytest.mark.parametrize("args", [
        ["--explain", "FMWK-000"],
        ["--explain", "HOT/kernel/merkle.py"],
        ["--explain", "PKG-KERNEL-001"],
        ["--inventory"],
        ["--verify"],
    ])
    def test_json_output_is_valid(self, args):
        """All commands should produce valid JSON with --json flag."""
        result = subprocess.run(
            ["python3", TRACE_SCRIPT] + args + ["--json"],
            cwd=str(CP_ROOT),
            capture_output=True,
            text=True,
        )
        try:
            json.loads(result.stdout)
        except json.JSONDecodeError:
            pytest.fail(f"Invalid JSON for {args}: {result.stdout[:200]}")


class TestMarkdownOutput:
    """Test Markdown output formatting."""

    def test_framework_markdown_has_headers(self):
        """Framework Markdown should have proper headers."""
        result = subprocess.run(
            ["python3", TRACE_SCRIPT, "--explain", "FMWK-000"],
            cwd=str(CP_ROOT),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "# FMWK-000:" in result.stdout
        assert "##" in result.stdout

    def test_file_markdown_shows_chain(self):
        """File Markdown should show ownership chain."""
        result = subprocess.run(
            ["python3", TRACE_SCRIPT, "--explain", "HOT/kernel/merkle.py"],
            cwd=str(CP_ROOT),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "Ownership Chain" in result.stdout
        assert "YOU ARE HERE" in result.stdout


class TestUnknownQuery:
    """Test handling of unknown queries."""

    def test_unknown_returns_not_found(self):
        """Unknown query should return not found message."""
        result = subprocess.run(
            ["python3", TRACE_SCRIPT, "--explain", "NONEXISTENT-999", "--json"],
            cwd=str(CP_ROOT),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["type"] == "unknown"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
