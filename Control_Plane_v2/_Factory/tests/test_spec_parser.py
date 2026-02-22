"""Tests for spec_parser.py (T-001)."""
from __future__ import annotations

from pathlib import Path

import pytest

from factory.models import ParseError, ProductSpec
from factory.spec_parser import parse


class TestParseMinimalSpec:
    """Tests against the minimal synthetic spec."""

    def test_parse_returns_product_spec(self, minimal_spec_dir: Path) -> None:
        spec = parse(minimal_spec_dir)
        assert isinstance(spec, ProductSpec)

    def test_component_name_extracted(self, minimal_spec_dir: Path) -> None:
        spec = parse(minimal_spec_dir)
        assert spec.component_name == "Test Component"

    def test_package_id_extracted(self, minimal_spec_dir: Path) -> None:
        spec = parse(minimal_spec_dir)
        assert spec.package_id == "PKG-TEST-001"

    def test_d1_articles_parsed(self, minimal_spec_dir: Path) -> None:
        spec = parse(minimal_spec_dir)
        assert len(spec.constitution.articles) >= 1
        art = spec.constitution.articles[0]
        assert "Test Rule" in art.name
        assert "Must do X" in art.rule

    def test_d1_boundaries_parsed(self, minimal_spec_dir: Path) -> None:
        spec = parse(minimal_spec_dir)
        assert "Always do A" in spec.constitution.boundaries.always
        assert "Ask about B" in spec.constitution.boundaries.ask_first
        assert "Never do C" in spec.constitution.boundaries.never

    def test_d2_scenarios_parsed(self, minimal_spec_dir: Path) -> None:
        spec = parse(minimal_spec_dir)
        assert len(spec.specification.scenarios) == 2
        sc1 = spec.specification.scenarios[0]
        assert sc1.id == "SC-001"
        assert sc1.priority == "P1"

    def test_d2_given_when_then(self, minimal_spec_dir: Path) -> None:
        spec = parse(minimal_spec_dir)
        sc1 = spec.specification.scenarios[0]
        assert "test input" in sc1.given
        assert "runs test" in sc1.when
        assert "passes" in sc1.then

    def test_d3_entities_parsed(self, minimal_spec_dir: Path) -> None:
        spec = parse(minimal_spec_dir)
        assert len(spec.data_model.entities) >= 1
        e1 = spec.data_model.entities[0]
        assert e1.id == "E-001"
        assert e1.name == "Widget"

    def test_d3_entity_fields(self, minimal_spec_dir: Path) -> None:
        spec = parse(minimal_spec_dir)
        e1 = spec.data_model.entities[0]
        assert len(e1.fields) >= 1
        assert e1.fields[0].name == "name"
        assert e1.fields[0].required is True

    def test_d4_contracts_parsed(self, minimal_spec_dir: Path) -> None:
        spec = parse(minimal_spec_dir)
        assert len(spec.contracts.inbound) >= 1
        assert spec.contracts.inbound[0].id == "IN-001"
        assert len(spec.contracts.outbound) >= 1
        assert len(spec.contracts.errors) >= 1

    def test_d4_all_ids(self, minimal_spec_dir: Path) -> None:
        spec = parse(minimal_spec_dir)
        all_ids = spec.contracts.all_ids()
        assert "IN-001" in all_ids
        assert "OUT-001" in all_ids
        assert "ERR-001" in all_ids

    def test_d5_research_parsed(self, minimal_spec_dir: Path) -> None:
        spec = parse(minimal_spec_dir)
        assert len(spec.research.questions) >= 1
        assert spec.research.questions[0].id == "RQ-001"

    def test_d6_gaps_resolved(self, minimal_spec_dir: Path) -> None:
        spec = parse(minimal_spec_dir)
        assert len(spec.gap_analysis.gaps) >= 1
        assert spec.gap_analysis.gaps[0].status == "RESOLVED"

    def test_d6_clarifications_resolved(self, minimal_spec_dir: Path) -> None:
        spec = parse(minimal_spec_dir)
        assert len(spec.gap_analysis.clarifications) >= 1
        assert spec.gap_analysis.clarifications[0].status == "RESOLVED"

    def test_d7_plan_sections(self, minimal_spec_dir: Path) -> None:
        spec = parse(minimal_spec_dir)
        assert "widget" in spec.plan.summary.lower()
        assert spec.plan.architecture

    def test_d8_tasks_parsed(self, minimal_spec_dir: Path) -> None:
        spec = parse(minimal_spec_dir)
        assert len(spec.tasks.tasks) >= 1
        t1 = spec.tasks.tasks[0]
        assert t1.id == "T-001"
        assert "SC-001" in t1.scenarios_satisfied
        assert "SC-002" in t1.scenarios_satisfied

    def test_d8_contracts_implemented(self, minimal_spec_dir: Path) -> None:
        spec = parse(minimal_spec_dir)
        t1 = spec.tasks.tasks[0]
        assert "IN-001" in t1.contracts_implemented
        assert "OUT-001" in t1.contracts_implemented

    def test_d9_holdouts_parsed(self, minimal_spec_dir: Path) -> None:
        spec = parse(minimal_spec_dir)
        assert len(spec.holdouts.scenarios) >= 3
        hs1 = spec.holdouts.scenarios[0]
        assert hs1.id == "HS-001"
        assert hs1.priority == "P0"

    def test_d9_holdout_validates(self, minimal_spec_dir: Path) -> None:
        spec = parse(minimal_spec_dir)
        hs1 = spec.holdouts.scenarios[0]
        assert "SC-001" in hs1.validates

    def test_d9_holdout_bash_blocks(self, minimal_spec_dir: Path) -> None:
        spec = parse(minimal_spec_dir)
        hs1 = spec.holdouts.scenarios[0]
        assert "mkdir" in hs1.setup
        assert "print" in hs1.execute

    def test_d10_agent_context(self, minimal_spec_dir: Path) -> None:
        spec = parse(minimal_spec_dir)
        assert "widget" in spec.agent_context.commands.lower() or "python" in spec.agent_context.commands.lower()

    def test_to_dict_roundtrip(self, minimal_spec_dir: Path) -> None:
        spec = parse(minimal_spec_dir)
        d = spec.to_dict()
        assert d["component_name"] == "Test Component"
        assert len(d["specification"]["scenarios"]) == 2


class TestParseErrorCases:
    """Tests for parser error handling."""

    def test_missing_directory(self, tmp_path: Path) -> None:
        with pytest.raises(ParseError, match="does not exist"):
            parse(tmp_path / "nonexistent")

    def test_missing_document(self, incomplete_spec_dir: Path) -> None:
        with pytest.raises(ParseError, match="D3_DATA_MODEL.md"):
            parse(incomplete_spec_dir)

    def test_empty_document(self, minimal_spec_dir: Path) -> None:
        """Empty doc should not crash — just produce empty structures."""
        (minimal_spec_dir / "D5_RESEARCH.md").write_text("")
        spec = parse(minimal_spec_dir)
        assert spec.research.questions == []


class TestParseRealSpec:
    """Tests against the real Factory_Spec_Test directory."""

    def test_parse_factory_spec_test(self, factory_spec_dir: Path) -> None:
        spec = parse(factory_spec_dir)
        assert spec.component_name == "Dark Factory Orchestrator"

    def test_factory_spec_scenarios(self, factory_spec_dir: Path) -> None:
        spec = parse(factory_spec_dir)
        sc_ids = [s.id for s in spec.specification.scenarios]
        assert "SC-001" in sc_ids
        assert "SC-010" in sc_ids
        assert len(sc_ids) >= 10

    def test_factory_spec_tasks(self, factory_spec_dir: Path) -> None:
        spec = parse(factory_spec_dir)
        task_ids = [t.id for t in spec.tasks.tasks]
        assert "T-001" in task_ids
        assert "T-007" in task_ids

    def test_factory_spec_holdouts(self, factory_spec_dir: Path) -> None:
        spec = parse(factory_spec_dir)
        hs_ids = [h.id for h in spec.holdouts.scenarios]
        assert "HS-001" in hs_ids
        assert len(hs_ids) >= 6

    def test_factory_spec_contracts(self, factory_spec_dir: Path) -> None:
        spec = parse(factory_spec_dir)
        all_ids = spec.contracts.all_ids()
        assert "IN-001" in all_ids
        assert "OUT-001" in all_ids

    def test_factory_spec_d6_no_open(self, factory_spec_dir: Path) -> None:
        spec = parse(factory_spec_dir)
        for clr in spec.gap_analysis.clarifications:
            assert clr.status != "OPEN", f"{clr.id} is OPEN"

    def test_factory_spec_d8_dependencies(self, factory_spec_dir: Path) -> None:
        spec = parse(factory_spec_dir)
        t002 = next(t for t in spec.tasks.tasks if t.id == "T-002")
        assert "T-001" in t002.depends_on
