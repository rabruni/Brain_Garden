"""Tests for prompt_generator.py (T-004)."""
from __future__ import annotations

from pathlib import Path

import pytest

from factory.spec_parser import parse
from factory.handoff_generator import generate
from factory.prompt_generator import generate_prompts


class TestGeneratePrompts:
    """Prompt generation tests."""

    def test_generates_prompts(self, minimal_spec_dir: Path, tmp_path: Path) -> None:
        spec = parse(minimal_spec_dir)
        handoffs = generate(spec, tmp_path / "out")
        prompts = generate_prompts(handoffs, spec, tmp_path / "out")
        assert len(prompts) >= 1

    def test_prompt_has_13_questions(self, minimal_spec_dir: Path, tmp_path: Path) -> None:
        spec = parse(minimal_spec_dir)
        handoffs = generate(spec, tmp_path / "out")
        prompts = generate_prompts(handoffs, spec, tmp_path / "out")
        p = prompts[0]
        assert len(p.verification_questions) == 10
        assert len(p.adversarial_questions) == 3

    def test_prompt_file_written(self, minimal_spec_dir: Path, tmp_path: Path) -> None:
        spec = parse(minimal_spec_dir)
        out = tmp_path / "out"
        handoffs = generate(spec, out)
        prompts = generate_prompts(handoffs, spec, out)
        for p in prompts:
            prompt_path = out / p.handoff_id / f"{p.handoff_id}_AGENT_PROMPT.md"
            assert prompt_path.exists()

    def test_expected_answers_separate(self, minimal_spec_dir: Path, tmp_path: Path) -> None:
        spec = parse(minimal_spec_dir)
        out = tmp_path / "out"
        handoffs = generate(spec, out)
        prompts = generate_prompts(handoffs, spec, out)
        for p in prompts:
            answers_path = out / p.handoff_id / f"{p.handoff_id}_EXPECTED_ANSWERS.md"
            assert answers_path.exists()
            # Expected answers NOT in prompt
            prompt_path = out / p.handoff_id / f"{p.handoff_id}_AGENT_PROMPT.md"
            prompt_text = prompt_path.read_text()
            assert "Expected Answer" not in prompt_text

    def test_prompt_has_contract_version(self, minimal_spec_dir: Path, tmp_path: Path) -> None:
        spec = parse(minimal_spec_dir)
        out = tmp_path / "out"
        handoffs = generate(spec, out)
        prompts = generate_prompts(handoffs, spec, out)
        assert prompts[0].contract_version == "1.1.0"

    def test_prompt_has_mandatory_rules(self, minimal_spec_dir: Path, tmp_path: Path) -> None:
        spec = parse(minimal_spec_dir)
        out = tmp_path / "out"
        handoffs = generate(spec, out)
        prompts = generate_prompts(handoffs, spec, out)
        assert len(prompts[0].mandatory_rules) == 10

    def test_prompt_text_contains_handoff_id(self, minimal_spec_dir: Path, tmp_path: Path) -> None:
        spec = parse(minimal_spec_dir)
        out = tmp_path / "out"
        handoffs = generate(spec, out)
        prompts = generate_prompts(handoffs, spec, out)
        for p in prompts:
            assert p.handoff_id in p.prompt_text

    def test_expected_answers_count(self, minimal_spec_dir: Path, tmp_path: Path) -> None:
        spec = parse(minimal_spec_dir)
        out = tmp_path / "out"
        handoffs = generate(spec, out)
        prompts = generate_prompts(handoffs, spec, out)
        assert len(prompts[0].expected_answers) == 13
