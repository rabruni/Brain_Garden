"""Tests for spec_validator.py (T-002)."""
from __future__ import annotations

from pathlib import Path

import pytest

from factory.spec_parser import parse
from factory.spec_validator import validate


class TestValidateMinimalSpec:
    """Validation against the minimal synthetic spec (should PASS)."""

    def test_validate_passes(self, minimal_spec_dir: Path) -> None:
        spec = parse(minimal_spec_dir)
        result = validate(spec)
        assert result.status == "PASS"

    def test_all_checks_pass(self, minimal_spec_dir: Path) -> None:
        spec = parse(minimal_spec_dir)
        result = validate(spec)
        for check in result.checks:
            assert check.status == "PASS", f"{check.check_name}: {check.message}"

    def test_summary_present_on_pass(self, minimal_spec_dir: Path) -> None:
        spec = parse(minimal_spec_dir)
        result = validate(spec)
        assert result.summary is not None
        assert result.summary["documents"] == 10
        assert result.summary["scenarios"] == 2

    def test_to_dict_structure(self, minimal_spec_dir: Path) -> None:
        spec = parse(minimal_spec_dir)
        result = validate(spec)
        d = result.to_dict()
        assert d["status"] == "PASS"
        assert len(d["checks"]) == 6


class TestValidateOpenD6:
    """Validation with OPEN D6 clarifications (should FAIL)."""

    def test_open_d6_fails(self, open_d6_spec_dir: Path) -> None:
        spec = parse(open_d6_spec_dir)
        result = validate(spec)
        assert result.status == "FAIL"

    def test_open_d6_names_clarification(self, open_d6_spec_dir: Path) -> None:
        spec = parse(open_d6_spec_dir)
        result = validate(spec)
        d6_check = next(c for c in result.checks if c.check_name == "d6_no_open_items")
        assert d6_check.status == "FAIL"
        assert "CLR-001" in d6_check.message

    def test_open_d6_no_summary(self, open_d6_spec_dir: Path) -> None:
        spec = parse(open_d6_spec_dir)
        result = validate(spec)
        assert result.summary is None


class TestValidateCycles:
    """Validation with D8 dependency cycles (should FAIL)."""

    def test_cycle_detected(self, cyclic_spec_dir: Path) -> None:
        spec = parse(cyclic_spec_dir)
        result = validate(spec)
        assert result.status == "FAIL"

    def test_cycle_names_tasks(self, cyclic_spec_dir: Path) -> None:
        spec = parse(cyclic_spec_dir)
        result = validate(spec)
        cycle_check = next(c for c in result.checks if c.check_name == "d8_no_dependency_cycles")
        assert cycle_check.status == "FAIL"
        assert "T-001" in cycle_check.message
        assert "T-002" in cycle_check.message

    def test_cycle_check_details(self, cyclic_spec_dir: Path) -> None:
        spec = parse(cyclic_spec_dir)
        result = validate(spec)
        cycle_check = next(c for c in result.checks if c.check_name == "d8_no_dependency_cycles")
        assert "T-001" in cycle_check.details
        assert "T-002" in cycle_check.details


class TestValidateUncoveredScenarios:
    """Validation with uncovered D2 scenarios."""

    def test_uncovered_scenario_fails(self, minimal_spec_dir: Path) -> None:
        # Add SC-003 to D2 but don't cover in D8
        d2 = minimal_spec_dir / "D2_SPECIFICATION.md"
        text = d2.read_text()
        text += "\n#### SC-003: Uncovered scenario\n\n**Priority:** P1\n\n**GIVEN** x\n**WHEN** y\n**THEN** z\n"
        d2.write_text(text)
        spec = parse(minimal_spec_dir)
        result = validate(spec)
        assert result.status == "FAIL"
        sc_check = next(c for c in result.checks if c.check_name == "d2_scenarios_covered")
        assert "SC-003" in sc_check.details


class TestValidateUncoveredContracts:
    """Validation with uncovered D4 contracts."""

    def test_uncovered_contract_fails(self, minimal_spec_dir: Path) -> None:
        # Add a contract not implemented by any D8 task
        d4 = minimal_spec_dir / "D4_CONTRACTS.md"
        text = d4.read_text()
        text += "\n#### SIDE-001: Orphan Side Effect\n\n**Scenarios:** SC-001\n"
        d4.write_text(text)
        spec = parse(minimal_spec_dir)
        result = validate(spec)
        assert result.status == "FAIL"
        ct_check = next(c for c in result.checks if c.check_name == "d4_contracts_covered")
        assert "SIDE-001" in ct_check.details


class TestValidateMinimumHoldouts:
    """Validation with fewer than 3 holdout scenarios."""

    def test_too_few_holdouts_fails(self, minimal_spec_dir: Path) -> None:
        d9 = minimal_spec_dir / "D9_HOLDOUT_SCENARIOS.md"
        d9.write_text(
            "# D9: Holdout Scenarios\n\n## Scenarios\n\n"
            "### HS-001: Only one\n\n"
            "```yaml\npriority: P0\n```\n"
            "**Validates:** SC-001\n**Contracts:** IN-001\n\n"
            "**Setup:**\n```bash\necho ok\n```\n"
            "**Execute:**\n```bash\necho ok\n```\n"
            "**Verify:**\n```bash\necho ok\n```\n"
            "**Cleanup:**\n```bash\necho ok\n```\n"
        )
        spec = parse(minimal_spec_dir)
        result = validate(spec)
        assert result.status == "FAIL"
        hs_check = next(c for c in result.checks if c.check_name == "d9_minimum_holdouts")
        assert hs_check.status == "FAIL"


class TestValidateRealSpec:
    """Validation against the real Factory_Spec_Test directory."""

    def test_factory_spec_known_gap(self, factory_spec_dir: Path) -> None:
        """Factory_Spec_Test has a known gap: SIDE-002 not assigned to any D8 task.
        The validator correctly catches this. All other checks pass."""
        spec = parse(factory_spec_dir)
        result = validate(spec)
        # Overall FAIL due to uncovered SIDE-002
        assert result.status == "FAIL"
        failing = [c for c in result.checks if c.status == "FAIL"]
        assert len(failing) == 1
        assert failing[0].check_name == "d4_contracts_covered"
        assert "SIDE-002" in failing[0].details

    def test_factory_spec_all_other_checks_pass(self, factory_spec_dir: Path) -> None:
        spec = parse(factory_spec_dir)
        result = validate(spec)
        for check in result.checks:
            if check.check_name != "d4_contracts_covered":
                assert check.status == "PASS", f"{check.check_name}: {check.message}"
