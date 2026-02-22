"""End-to-end tests for the Dark Factory Orchestrator."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from factory.spec_parser import parse
from factory.spec_validator import validate
from factory.handoff_generator import generate
from factory.prompt_generator import generate_prompts
from factory.models import DispatchRecord
from factory.report_generator import generate_report, write_report


class TestE2EMinimal:
    """E2E pipeline against minimal spec."""

    def test_validate_parse_generate(self, minimal_spec_dir, tmp_path):
        spec = parse(minimal_spec_dir)
        result = validate(spec)
        assert result.status == "PASS"
        handoffs = generate(spec, tmp_path / "out")
        assert len(handoffs) >= 1
        prompts = generate_prompts(handoffs, spec, tmp_path / "out")
        assert len(prompts) >= 1
        for p in prompts:
            assert len(p.verification_questions) == 10
            assert len(p.adversarial_questions) == 3

    def test_handoff_no_d9_leakage(self, minimal_spec_dir, tmp_path):
        spec = parse(minimal_spec_dir)
        handoffs = generate(spec, tmp_path / "out")
        for h in handoffs:
            content = Path(h.output_path).read_text()
            # D9 executable content must not appear
            for hs in spec.holdouts.scenarios:
                if hs.setup and len(hs.setup.strip()) > 20:
                    assert hs.setup.strip() not in content

    def test_full_pipeline_mocked(self, minimal_spec_dir, tmp_path):
        spec = parse(minimal_spec_dir)
        result = validate(spec)
        assert result.status == "PASS"
        out = tmp_path / "out"
        handoffs = generate(spec, out)
        prompts = generate_prompts(handoffs, spec, out)
        # Mock dispatch
        dispatches = [
            DispatchRecord(
                dispatch_id="DSP-1",
                handoff_id=p.handoff_id,
                task_id="T-001",
                timestamp_dispatched="2026-01-01T00:00:00Z",
                status="COMPLETED",
                timestamp_completed="2026-01-01T00:01:00Z",
            )
            for p in prompts
        ]
        report = generate_report(spec, result, dispatches, [])
        assert report.verdict == "ACCEPT"
        json_path = write_report(report, out)
        assert json_path.exists()


class TestE2ERealSpec:
    """E2E against real Factory_Spec_Test directory."""

    def test_parse_and_validate(self, factory_spec_dir):
        spec = parse(factory_spec_dir)
        result = validate(spec)
        # Known gap: SIDE-002 uncovered
        failing = [c for c in result.checks if c.status == "FAIL"]
        assert len(failing) <= 1

    def test_generate_handoffs(self, factory_spec_dir, tmp_path):
        spec = parse(factory_spec_dir)
        handoffs = generate(spec, tmp_path / "out")
        assert len(handoffs) == 7
        # Verify index
        index = json.loads((tmp_path / "out" / "handoff_index.json").read_text())
        assert len(index["handoffs"]) == 7

    def test_generate_prompts(self, factory_spec_dir, tmp_path):
        spec = parse(factory_spec_dir)
        handoffs = generate(spec, tmp_path / "out")
        prompts = generate_prompts(handoffs, spec, tmp_path / "out")
        assert len(prompts) == 7
        for p in prompts:
            assert len(p.verification_questions) == 10
            assert len(p.adversarial_questions) == 3

    def test_no_d9_in_handoffs(self, factory_spec_dir, tmp_path):
        spec = parse(factory_spec_dir)
        handoffs = generate(spec, tmp_path / "out")
        for h in handoffs:
            content = Path(h.output_path).read_text()
            # D9 executable content must not appear
            for hs in spec.holdouts.scenarios:
                if hs.setup and len(hs.setup.strip()) > 20:
                    assert hs.setup.strip() not in content
                if hs.execute and len(hs.execute.strip()) > 20:
                    assert hs.execute.strip() not in content
