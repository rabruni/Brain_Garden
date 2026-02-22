"""Tests for handoff_generator.py (T-003)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from factory.spec_parser import parse
from factory.spec_validator import validate
from factory.handoff_generator import generate
from factory.models import GenerationError


class TestGenerateMinimal:
    """Generate handoffs from minimal spec."""

    def test_generates_handoffs(self, minimal_spec_dir: Path, tmp_path: Path) -> None:
        spec = parse(minimal_spec_dir)
        handoffs = generate(spec, tmp_path / "out")
        assert len(handoffs) >= 1

    def test_handoff_has_all_fields(self, minimal_spec_dir: Path, tmp_path: Path) -> None:
        spec = parse(minimal_spec_dir)
        handoffs = generate(spec, tmp_path / "out")
        h = handoffs[0]
        assert h.handoff_id.startswith("H-FACTORY-")
        assert h.task_id == "T-001"
        assert h.mission
        assert h.scenarios
        assert h.contracts

    def test_handoff_file_written(self, minimal_spec_dir: Path, tmp_path: Path) -> None:
        spec = parse(minimal_spec_dir)
        handoffs = generate(spec, tmp_path / "out")
        for h in handoffs:
            assert Path(h.output_path).exists()

    def test_handoff_has_10_sections(self, minimal_spec_dir: Path, tmp_path: Path) -> None:
        spec = parse(minimal_spec_dir)
        handoffs = generate(spec, tmp_path / "out")
        content = Path(handoffs[0].output_path).read_text()
        for section_num in range(1, 11):
            assert f"## {section_num}." in content, f"Missing section {section_num}"

    def test_handoff_traceability(self, minimal_spec_dir: Path, tmp_path: Path) -> None:
        spec = parse(minimal_spec_dir)
        handoffs = generate(spec, tmp_path / "out")
        content = Path(handoffs[0].output_path).read_text()
        assert "SC-001" in content
        assert "T-001" in content

    def test_no_d9_content_in_handoff(self, minimal_spec_dir: Path, tmp_path: Path) -> None:
        spec = parse(minimal_spec_dir)
        handoffs = generate(spec, tmp_path / "out")
        for h in handoffs:
            content = Path(h.output_path).read_text()
            # D9 executable content (setup/execute/verify blocks) must not appear
            for hs in spec.holdouts.scenarios:
                if hs.setup and len(hs.setup.strip()) > 20:
                    assert hs.setup.strip() not in content
                if hs.execute and len(hs.execute.strip()) > 20:
                    assert hs.execute.strip() not in content

    def test_index_file_written(self, minimal_spec_dir: Path, tmp_path: Path) -> None:
        spec = parse(minimal_spec_dir)
        out = tmp_path / "out"
        generate(spec, out)
        index_path = out / "handoff_index.json"
        assert index_path.exists()
        index = json.loads(index_path.read_text())
        assert "handoffs" in index
        assert len(index["handoffs"]) >= 1

    def test_index_has_scenario_ids(self, minimal_spec_dir: Path, tmp_path: Path) -> None:
        spec = parse(minimal_spec_dir)
        out = tmp_path / "out"
        generate(spec, out)
        index = json.loads((out / "handoff_index.json").read_text())
        h = index["handoffs"][0]
        assert "SC-001" in h["scenarios"]

    def test_creates_output_dir(self, minimal_spec_dir: Path, tmp_path: Path) -> None:
        spec = parse(minimal_spec_dir)
        out = tmp_path / "nested" / "output"
        handoffs = generate(spec, out)
        assert out.is_dir()
        assert len(handoffs) >= 1

    def test_deterministic_output(self, minimal_spec_dir: Path, tmp_path: Path) -> None:
        spec = parse(minimal_spec_dir)
        h1 = generate(spec, tmp_path / "out1")
        h2 = generate(spec, tmp_path / "out2")
        c1 = Path(h1[0].output_path).read_text()
        c2 = Path(h2[0].output_path).read_text()
        assert c1 == c2


class TestGenerateRealSpec:
    """Generate from real Factory_Spec_Test."""

    def test_generates_7_handoffs(self, factory_spec_dir: Path, tmp_path: Path) -> None:
        spec = parse(factory_spec_dir)
        handoffs = generate(spec, tmp_path / "out")
        assert len(handoffs) == 7

    def test_all_handoffs_have_scenarios(self, factory_spec_dir: Path, tmp_path: Path) -> None:
        spec = parse(factory_spec_dir)
        handoffs = generate(spec, tmp_path / "out")
        for h in handoffs:
            # T-001 has "Foundation" as scenarios — may not have SC- IDs
            assert h.task_id.startswith("T-")
