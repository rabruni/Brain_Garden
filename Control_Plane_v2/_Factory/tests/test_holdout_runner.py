"""Tests for holdout_runner.py (T-006)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from factory.spec_parser import parse
from factory.holdout_runner import run_holdouts, _run_bash


class TestRunBash:

    def test_success(self, tmp_path):
        code, stdout, stderr = _run_bash("echo hello", str(tmp_path))
        assert code == 0
        assert "hello" in stdout

    def test_failure(self, tmp_path):
        code, stdout, stderr = _run_bash("exit 1", str(tmp_path))
        assert code == 1

    def test_empty_script(self, tmp_path):
        code, _, _ = _run_bash("", str(tmp_path))
        assert code == 0


class TestRunHoldouts:

    @patch("factory.holdout_runner._run_bash")
    def test_all_pass(self, mock_bash, minimal_spec_dir, tmp_path):
        mock_bash.return_value = (0, "ok", "")
        spec = parse(minimal_spec_dir)
        results = run_holdouts(spec, tmp_path)
        assert len(results) >= 3
        assert all(r.status == "PASS" for r in results)

    @patch("factory.holdout_runner._run_bash")
    def test_verify_fail(self, mock_bash, minimal_spec_dir, tmp_path):
        # Setup and Execute pass, Verify fails
        def side_effect(script, cwd, timeout=60):
            if "verify" in script.lower() or script == "echo verify":
                return (1, "bad output", "verify failed")
            return (0, "ok", "")
        mock_bash.side_effect = side_effect
        spec = parse(minimal_spec_dir)
        results = run_holdouts(spec, tmp_path)
        # At least one should FAIL
        fail_results = [r for r in results if r.status == "FAIL"]
        assert len(fail_results) >= 1

    @patch("factory.holdout_runner._run_bash")
    def test_p0_runs_first(self, mock_bash, minimal_spec_dir, tmp_path):
        mock_bash.return_value = (0, "ok", "")
        spec = parse(minimal_spec_dir)
        results = run_holdouts(spec, tmp_path)
        # P0 scenarios should come before P1
        p0_indices = [i for i, r in enumerate(results) if r.priority == "P0"]
        p1_indices = [i for i, r in enumerate(results) if r.priority == "P1"]
        if p0_indices and p1_indices:
            assert max(p0_indices) < min(p1_indices)

    @patch("factory.holdout_runner._run_bash")
    def test_traceability(self, mock_bash, minimal_spec_dir, tmp_path):
        mock_bash.return_value = (0, "ok", "")
        spec = parse(minimal_spec_dir)
        results = run_holdouts(spec, tmp_path)
        for r in results:
            assert r.validates_scenarios
            assert r.responsible_task

    @patch("factory.holdout_runner._run_bash")
    def test_setup_error(self, mock_bash, minimal_spec_dir, tmp_path):
        def side_effect(script, cwd, timeout=60):
            if "mkdir" in script or script.strip().startswith("mkdir"):
                return (1, "", "setup error")
            return (0, "ok", "")
        mock_bash.side_effect = side_effect
        spec = parse(minimal_spec_dir)
        results = run_holdouts(spec, tmp_path)
        error_results = [r for r in results if r.status == "ERROR"]
        assert len(error_results) >= 1

    @patch("factory.holdout_runner._run_bash")
    def test_result_to_dict(self, mock_bash, minimal_spec_dir, tmp_path):
        mock_bash.return_value = (0, "ok", "")
        spec = parse(minimal_spec_dir)
        results = run_holdouts(spec, tmp_path)
        d = results[0].to_dict()
        assert "holdout_id" in d
        assert "priority" in d
        assert "status" in d
