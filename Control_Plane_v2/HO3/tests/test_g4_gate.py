#!/usr/bin/env python3
"""
test_g4_gate.py - Tests for G4 ACCEPTANCE gate.

Tests the acceptance test execution logic:
- Tests that pass (exit 0) allow WO to proceed
- Tests that fail (exit non-zero) block WO
- Tests that timeout are treated as failures
- Empty test list passes
"""

import json
import pytest
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "HOT"))

from scripts.g4_gate import (
    run_g4_gate,
    run_single_test,
    run_acceptance_tests,
    G4Result,
    DEFAULT_TIMEOUT_SECONDS,
)


class TestSingleTestExecution:
    """Test individual test command execution."""

    def test_passing_command_returns_success(self):
        """Command that exits 0 should return passed=True."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            result = run_single_test("exit 0", workspace)

            assert result.passed is True
            assert result.returncode == 0
            assert result.timed_out is False

    def test_failing_command_returns_failure(self):
        """Command that exits non-zero should return passed=False."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            result = run_single_test("exit 1", workspace)

            assert result.passed is False
            assert result.returncode == 1
            assert result.timed_out is False

    def test_command_captures_stdout(self):
        """Command stdout should be captured."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            result = run_single_test("echo 'hello world'", workspace)

            assert result.passed is True
            assert 'hello world' in result.stdout

    def test_command_captures_stderr(self):
        """Command stderr should be captured."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            result = run_single_test("echo 'error message' >&2; exit 1", workspace)

            assert result.passed is False
            assert 'error message' in result.stderr

    def test_timeout_returns_failure(self):
        """Command that exceeds timeout should return timed_out=True."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            # Use 1 second timeout with sleep 5
            result = run_single_test("sleep 5", workspace, timeout_seconds=1)

            assert result.passed is False
            assert result.timed_out is True
            assert result.returncode == -1

    def test_duration_is_recorded(self):
        """Test duration should be recorded in milliseconds."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            result = run_single_test("sleep 0.1", workspace)

            assert result.duration_ms >= 100
            assert result.duration_ms < 5000  # Should not take 5 seconds


class TestAcceptanceTests:
    """Test acceptance test suite execution."""

    def test_empty_tests_passes(self):
        """WO with no tests defined should pass."""
        wo = {
            'work_order_id': 'WO-TEST-001',
            'acceptance': {
                'tests': [],
                'checks': []
            }
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            result = run_acceptance_tests(wo, workspace)

            assert result.passed is True
            assert 'No acceptance tests' in result.message

    def test_all_passing_tests_passes(self):
        """WO where all tests pass should result in G4 pass."""
        wo = {
            'work_order_id': 'WO-TEST-001',
            'acceptance': {
                'tests': ['exit 0', 'echo success'],
                'checks': []
            }
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            result = run_acceptance_tests(wo, workspace)

            assert result.passed is True
            assert len(result.test_results) == 2
            assert all(r.passed for r in result.test_results)

    def test_one_failing_test_fails_fast(self):
        """First failing test should stop execution and fail G4."""
        wo = {
            'work_order_id': 'WO-TEST-001',
            'acceptance': {
                'tests': ['exit 0', 'exit 1', 'exit 0'],  # Second test fails
                'checks': []
            }
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            result = run_acceptance_tests(wo, workspace)

            assert result.passed is False
            # Should stop at first failure (fail fast)
            assert len(result.test_results) == 2
            assert result.test_results[0].passed is True
            assert result.test_results[1].passed is False

    def test_checks_are_also_executed(self):
        """Both tests and checks arrays should be executed."""
        wo = {
            'work_order_id': 'WO-TEST-001',
            'acceptance': {
                'tests': ['echo test1'],
                'checks': ['echo check1']
            }
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            result = run_acceptance_tests(wo, workspace)

            assert result.passed is True
            assert len(result.test_results) == 2
            assert result.details['test_count'] == 1
            assert result.details['check_count'] == 1


class TestG4GateFull:
    """Test full G4 gate execution."""

    def test_nonexistent_workspace_fails(self):
        """G4 should fail if workspace doesn't exist."""
        wo = {
            'work_order_id': 'WO-TEST-001',
            'acceptance': {'tests': ['exit 0']}
        }

        result = run_g4_gate(wo, Path('/nonexistent/workspace'))

        assert result.passed is False
        assert 'Workspace' in result.message or 'not exist' in result.message.lower()

    def test_result_serializable_to_json(self):
        """G4Result should be JSON serializable."""
        wo = {
            'work_order_id': 'WO-TEST-001',
            'acceptance': {'tests': ['echo test']}
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            result = run_g4_gate(wo, workspace)
            result_dict = result.to_dict()

            # Should not raise
            json_str = json.dumps(result_dict)
            assert 'G4' in json_str

    def test_pythonpath_includes_workspace(self):
        """Workspace should be in PYTHONPATH for test execution."""
        wo = {
            'work_order_id': 'WO-TEST-001',
            'acceptance': {
                'tests': ['python3 -c "import sys; print(sys.path)"']
            }
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            result = run_g4_gate(wo, workspace)

            assert result.passed is True
            # Workspace should be in the printed path
            assert str(workspace) in result.test_results[0].stdout


class TestAcceptanceCriteriaAC2:
    """AC2: G4 fails and discards workspace when test exits non-zero."""

    def test_ac2_failing_test_rejects_wo(self):
        """
        AC2: G4 fails when acceptance test exits non-zero.

        The workspace discarding is handled by the caller (apply_work_order.py),
        but G4 must return passed=False.
        """
        wo = {
            'work_order_id': 'WO-AC2-TEST',
            'type': 'code_change',
            'plane_id': 'ho3',
            'spec_id': 'SPEC-TEST-001',
            'framework_id': 'FMWK-000',
            'scope': {
                'allowed_files': ['lib/paths.py'],
                'forbidden_files': []
            },
            'acceptance': {
                'tests': ['exit 1'],  # This test will fail
                'checks': []
            }
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            result = run_g4_gate(wo, workspace)

            # MUST fail
            assert result.passed is False, "G4 must fail when test exits non-zero"
            assert len(result.errors) > 0, "G4 must report error for failed test"
            assert 'exit' in result.errors[0].lower() or 'failed' in result.errors[0].lower()

    def test_ac2_passing_test_allows_wo(self):
        """AC2 corollary: G4 passes when all tests exit zero."""
        wo = {
            'work_order_id': 'WO-AC2-PASS',
            'acceptance': {
                'tests': ['exit 0', 'echo success'],
                'checks': []
            }
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            result = run_g4_gate(wo, workspace)

            assert result.passed is True
            assert len(result.errors) == 0
