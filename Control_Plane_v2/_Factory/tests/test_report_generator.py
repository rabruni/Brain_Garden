"""Tests for report_generator.py (T-007)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from factory.models import (
    CheckResult,
    DispatchRecord,
    HoldoutResult,
    ValidationResult,
)
from factory.spec_parser import parse
from factory.report_generator import generate_report, write_report


def _make_validation(status="PASS"):
    return ValidationResult(
        status=status, spec_dir="test/",
        checks=[CheckResult(check_name="test", status=status, message="ok")],
        component_name="Test",
    )


def _make_dispatch(task_id="T-001", status="COMPLETED"):
    return DispatchRecord(
        dispatch_id="DSP-1", handoff_id="H-FACTORY-001",
        task_id=task_id, timestamp_dispatched="2026-01-01T00:00:00Z",
        status=status,
    )


def _make_holdout(holdout_id="HS-001", priority="P0", status="PASS"):
    return HoldoutResult(
        holdout_id=holdout_id, priority=priority, status=status,
        validates_scenarios=["SC-001"], validates_contracts=["IN-001"],
        responsible_task="T-001",
    )


class TestGenerateReport:

    def test_accept_verdict(self, minimal_spec_dir):
        spec = parse(minimal_spec_dir)
        report = generate_report(
            spec, _make_validation(),
            [_make_dispatch()], [_make_holdout()],
        )
        assert report.verdict == "ACCEPT"

    def test_reject_on_p0_fail(self, minimal_spec_dir):
        spec = parse(minimal_spec_dir)
        report = generate_report(
            spec, _make_validation(),
            [_make_dispatch()],
            [_make_holdout(status="FAIL")],
        )
        assert report.verdict == "REJECT"

    def test_partial_on_mixed(self, minimal_spec_dir):
        spec = parse(minimal_spec_dir)
        report = generate_report(
            spec, _make_validation(),
            [_make_dispatch(), _make_dispatch(task_id="T-002", status="FAILED")],
            [_make_holdout(priority="P1")],
        )
        assert report.verdict == "PARTIAL"

    def test_to_json(self, minimal_spec_dir):
        spec = parse(minimal_spec_dir)
        report = generate_report(
            spec, _make_validation(),
            [_make_dispatch()], [_make_holdout()],
        )
        data = json.loads(report.to_json())
        assert data["verdict"] == "ACCEPT"
        assert "dispatches" in data

    def test_total_tokens(self, minimal_spec_dir):
        spec = parse(minimal_spec_dir)
        d = _make_dispatch()
        report = generate_report(
            spec, _make_validation(), [d], [],
        )
        assert report.total_tokens == 0

    def test_write_report_files(self, minimal_spec_dir, tmp_path):
        spec = parse(minimal_spec_dir)
        report = generate_report(
            spec, _make_validation(),
            [_make_dispatch()], [_make_holdout()],
        )
        json_path = write_report(report, tmp_path / "reports")
        assert json_path.exists()
        md_path = tmp_path / "reports" / "factory_report.md"
        assert md_path.exists()

    def test_markdown_contains_verdict(self, minimal_spec_dir, tmp_path):
        spec = parse(minimal_spec_dir)
        report = generate_report(
            spec, _make_validation(),
            [_make_dispatch()], [_make_holdout()],
        )
        write_report(report, tmp_path / "reports")
        md = (tmp_path / "reports" / "factory_report.md").read_text()
        assert "ACCEPT" in md

    def test_no_holdouts_accept(self, minimal_spec_dir):
        spec = parse(minimal_spec_dir)
        report = generate_report(
            spec, _make_validation(),
            [_make_dispatch()], [],
        )
        assert report.verdict == "ACCEPT"
