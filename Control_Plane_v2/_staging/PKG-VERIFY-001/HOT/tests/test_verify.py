"""Tests for verify.py — the Control Plane verification harness.

DTT: tests written FIRST, before implementation.

Tests focus on:
- Parsing gate_check.py output into structured results
- Parsing pytest output into pass/fail counts
- Import smoke check logic
- JSON output format
- Exit code behavior
- E2E output parsing
- Edge cases (missing root, no API key, etc.)

All subprocess calls are mocked — tests never invoke real subprocesses.
"""

from __future__ import annotations

import json
import os
import sys
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

# Resolve staging root and add the verify.py's parent to path
_staging = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_staging / "PKG-VERIFY-001" / "HOT" / "scripts"))

import verify  # noqa: E402


# ── Fixtures ─────────────────────────────────────────────────────────

SAMPLE_GATE_OUTPUT_ALL_PASS = textwrap.dedent("""\

    GATE CHECK REPORT
    Plane: /tmp/test_root
    ============================================================

    G0B: PASS
      G0B PASSED: 116 files owned, 0 orphans

    G1: PASS
      G1 PASSED: 21 chains validated, 0 warnings

    G1-COMPLETE: PASS
      G1-COMPLETE PASSED: 21 frameworks checked

    G2: PASS
      G2 PASSED

    G3: PASS
      G3 PASSED

    G4: PASS
      G4 PASSED

    G5: PASS
      G5 PASSED

    G6: PASS
      G6 PASSED: 3 ledger files, 105 entries

    Overall: PASS (8/8 gates passed)
""")

SAMPLE_GATE_OUTPUT_WITH_FAILURE = textwrap.dedent("""\

    GATE CHECK REPORT
    Plane: /tmp/test_root
    ============================================================

    G0B: PASS
      G0B PASSED: 116 files owned, 0 orphans

    G1: FAIL
      G1 FAILED: 2 chain errors
      ERROR: Missing spec for PKG-TEST-001

    G1-COMPLETE: PASS
      G1-COMPLETE PASSED: 21 frameworks checked

    G2: PASS
      G2 PASSED

    G3: PASS
      G3 PASSED

    G4: PASS
      G4 PASSED

    G5: PASS
      G5 PASSED

    G6: PASS
      G6 PASSED: 3 ledger files, 105 entries

    Overall: FAIL (7/8 gates passed)
""")

SAMPLE_PYTEST_ALL_PASS = textwrap.dedent("""\
    ============================= test session starts ==============================
    collected 163 items
    HOT/tests/test_work_order.py::test_create PASSED
    HOT/tests/test_work_order.py::test_validate PASSED
    ============================== 163 passed in 2.34s =============================
""")

SAMPLE_PYTEST_WITH_FAILURES = textwrap.dedent("""\
    ============================= test session starts ==============================
    collected 163 items
    HOT/tests/test_work_order.py::test_create PASSED
    HOT/tests/test_work_order.py::test_bad FAILED
    ============================== 160 passed, 3 failed in 4.12s ===================
""")

SAMPLE_PYTEST_WITH_SKIPS = textwrap.dedent("""\
    ============================= test session starts ==============================
    collected 162 items
    HOT/tests/test_work_order.py::test_create PASSED
    ============================== 160 passed, 2 skipped in 3.00s ==================
""")


# ── Test Class: Gate Output Parsing ──────────────────────────────────

class TestParseGateOutput:
    def test_parse_gate_output_all_pass(self):
        """Parses gate_check output with 8 PASS lines."""
        results = verify.parse_gate_output(SAMPLE_GATE_OUTPUT_ALL_PASS)
        assert len(results) == 8
        assert all(r["passed"] for r in results)
        gate_names = [r["gate"] for r in results]
        assert "G0B" in gate_names
        assert "G1" in gate_names
        assert "G1-COMPLETE" in gate_names
        assert "G6" in gate_names

    def test_parse_gate_output_with_failure(self):
        """Parses output with G1: FAIL."""
        results = verify.parse_gate_output(SAMPLE_GATE_OUTPUT_WITH_FAILURE)
        assert len(results) == 8
        g1 = next(r for r in results if r["gate"] == "G1")
        assert g1["passed"] is False
        g0b = next(r for r in results if r["gate"] == "G0B")
        assert g0b["passed"] is True


# ── Test Class: Pytest Output Parsing ────────────────────────────────

class TestParsePytestOutput:
    def test_parse_pytest_output_all_pass(self):
        """Parses '163 passed' from pytest output."""
        result = verify.parse_pytest_output(SAMPLE_PYTEST_ALL_PASS, returncode=0)
        assert result["total"] == 163
        assert result["passed"] == 163
        assert result["failed"] == 0
        assert result["skipped"] == 0

    def test_parse_pytest_output_with_failures(self):
        """Parses '160 passed, 3 failed'."""
        result = verify.parse_pytest_output(SAMPLE_PYTEST_WITH_FAILURES, returncode=1)
        assert result["passed"] == 160
        assert result["failed"] == 3
        assert result["total"] == 163

    def test_parse_pytest_output_with_skips(self):
        """Parses '160 passed, 2 skipped'."""
        result = verify.parse_pytest_output(SAMPLE_PYTEST_WITH_SKIPS, returncode=0)
        assert result["passed"] == 160
        assert result["skipped"] == 2
        assert result["total"] == 162


# ── Test Class: Test Discovery ───────────────────────────────────────

class TestDiscoverTestFiles:
    def test_discover_test_files(self, tmp_path: Path):
        """Discovers test_*.py under mock root."""
        # Create test files in installed layout
        for tier_dir in ["HOT", "HO1", "HO2"]:
            test_dir = tmp_path / tier_dir / "tests"
            test_dir.mkdir(parents=True, exist_ok=True)
            (test_dir / f"test_{tier_dir.lower()}.py").write_text("# test")

        # Also create a nested test
        nested = tmp_path / "HOT" / "admin" / "tests"
        nested.mkdir(parents=True, exist_ok=True)
        (nested / "test_admin.py").write_text("# test")

        found = verify.discover_test_files(str(tmp_path))
        assert len(found) >= 3
        # All returned paths should be test files
        for f in found:
            assert Path(f).name.startswith("test_")

    def test_discover_no_tests(self, tmp_path: Path):
        """Empty root with no test files."""
        (tmp_path / "HOT").mkdir()
        found = verify.discover_test_files(str(tmp_path))
        assert found == []


# ── Test Class: Import Smoke Module List ─────────────────────────────

class TestImportSmokeModuleList:
    def test_import_smoke_module_list(self):
        """Verifies the canonical module list contains all 10 expected modules."""
        expected = {
            "shell", "session_host_v2", "ho2_supervisor", "ho1_executor",
            "llm_gateway", "work_order", "contract_loader", "token_budgeter",
            "ledger_client", "anthropic_provider",
        }
        actual = set(verify.IMPORT_SMOKE_MODULES)
        assert actual == expected


# ── Test Class: E2E Output Parsing ───────────────────────────────────

class TestE2EOutputParsing:
    def test_e2e_output_success(self):
        """Parses output with real LLM response."""
        output = "admin> Hello! I'm the Admin assistant. How can I help?"
        result = verify.parse_e2e_output(output)
        assert result["passed"] is True

    def test_e2e_output_quality_gate_fail(self):
        """Parses 'Quality gate failed' in output."""
        output = "Quality gate failed: missing field X"
        result = verify.parse_e2e_output(output)
        assert result["passed"] is False
        assert "quality gate" in result["reason"].lower()

    def test_e2e_output_empty(self):
        """No assistant response in output."""
        result = verify.parse_e2e_output("")
        assert result["passed"] is False
        assert "empty" in result["reason"].lower()


# ── Test Class: E2E Skip Conditions ──────────────────────────────────

class TestE2ESkipConditions:
    def test_e2e_skipped_no_flag(self):
        """--e2e not specified -> reports SKIPPED."""
        result = verify.check_e2e_skip(e2e_requested=False, api_key_set=True)
        assert result["status"] == "SKIPPED"
        assert "--e2e not specified" in result["reason"]

    def test_e2e_skipped_no_api_key(self):
        """--e2e but no ANTHROPIC_API_KEY -> reports SKIPPED."""
        result = verify.check_e2e_skip(e2e_requested=True, api_key_set=False)
        assert result["status"] == "SKIPPED"
        assert "ANTHROPIC_API_KEY" in result["reason"]


# ── Test Class: JSON Output Format ───────────────────────────────────

class TestJSONOutputFormat:
    def test_json_output_format(self):
        """--json flag produces valid JSON with required keys."""
        report = verify.build_report(
            root="/tmp/test_root",
            gate_results=[{"gate": "G0B", "passed": True}],
            test_results={"total": 10, "passed": 10, "failed": 0, "skipped": 0, "status": "PASS"},
            import_results={"total": 10, "ok": 10, "failed": 0, "status": "PASS", "details": []},
            e2e_result={"status": "SKIPPED", "reason": "--e2e not specified"},
        )
        # Must have all required keys
        assert "result" in report
        assert "levels" in report
        assert "root" in report
        assert "timestamp" in report
        assert report["levels"]["gates"]["status"] == "PASS"
        assert report["levels"]["tests"]["status"] == "PASS"
        assert report["levels"]["imports"]["status"] == "PASS"
        assert report["levels"]["e2e"]["status"] == "SKIPPED"


# ── Test Class: Exit Codes ───────────────────────────────────────────

class TestExitCodes:
    def test_exit_code_all_pass(self):
        """All levels pass -> exit code 0."""
        code = verify.compute_exit_code(
            gate_passed=True, tests_passed=True, imports_passed=True, e2e_result={"status": "SKIPPED"}
        )
        assert code == 0

    def test_exit_code_gate_failure(self):
        """Gate fails -> exit code 1."""
        code = verify.compute_exit_code(
            gate_passed=False, tests_passed=True, imports_passed=True, e2e_result={"status": "SKIPPED"}
        )
        assert code == 1

    def test_exit_code_test_failure(self):
        """pytest has failures -> exit code 1."""
        code = verify.compute_exit_code(
            gate_passed=True, tests_passed=False, imports_passed=True, e2e_result={"status": "SKIPPED"}
        )
        assert code == 1


# ── Test Class: Root Validation ──────────────────────────────────────

class TestRootValidation:
    def test_missing_root(self, tmp_path: Path):
        """--root points to nonexistent dir -> exit code 2."""
        result = verify.validate_root(str(tmp_path / "nonexistent"))
        assert result["valid"] is False
        assert result["exit_code"] == 2

    def test_invalid_root_no_gate_check(self, tmp_path: Path):
        """--root exists but no gate_check.py -> exit code 2."""
        (tmp_path / "HOT").mkdir()
        result = verify.validate_root(str(tmp_path))
        assert result["valid"] is False
        assert result["exit_code"] == 2
        assert "gate_check" in result["message"].lower()

    def test_valid_root(self, tmp_path: Path):
        """--root with gate_check.py -> valid."""
        scripts = tmp_path / "HOT" / "scripts"
        scripts.mkdir(parents=True)
        (scripts / "gate_check.py").write_text("# gate check")
        result = verify.validate_root(str(tmp_path))
        assert result["valid"] is True


# ── Test Class: Gates-Only Flag ──────────────────────────────────────

class TestGatesOnlyFlag:
    def test_gates_only_flag(self):
        """--gates-only skips tests and imports."""
        levels = verify.determine_levels(gates_only=True, e2e=False)
        assert levels["gates"] is True
        assert levels["tests"] is False
        assert levels["imports"] is False
        assert levels["e2e"] is False

    def test_default_levels(self):
        """Default runs gates + tests + imports, not e2e."""
        levels = verify.determine_levels(gates_only=False, e2e=False)
        assert levels["gates"] is True
        assert levels["tests"] is True
        assert levels["imports"] is True
        assert levels["e2e"] is False

    def test_e2e_levels(self):
        """--e2e enables all 4 levels."""
        levels = verify.determine_levels(gates_only=False, e2e=True)
        assert levels["gates"] is True
        assert levels["tests"] is True
        assert levels["imports"] is True
        assert levels["e2e"] is True
