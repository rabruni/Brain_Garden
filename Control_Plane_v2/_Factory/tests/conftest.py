"""Shared fixtures for Dark Factory Orchestrator tests."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

# Real spec directory
FACTORY_SPEC_DIR = Path(__file__).resolve().parent.parent.parent / "_design" / "docs" / "templates" / "Factory_Spec_Test"


@pytest.fixture
def factory_spec_dir() -> Path:
    """Path to the real Factory_Spec_Test spec directory."""
    assert FACTORY_SPEC_DIR.is_dir(), f"Spec dir not found: {FACTORY_SPEC_DIR}"
    return FACTORY_SPEC_DIR


@pytest.fixture
def minimal_spec_dir(tmp_path: Path) -> Path:
    """Create a minimal valid spec directory for testing."""
    spec = tmp_path / "spec"
    spec.mkdir()

    (spec / "D1_CONSTITUTION.md").write_text(
        "# D1: Constitution\n\n**Version:** 1.0.0\n\n## Articles\n\n"
        "### Article 1: Test Rule\n\n"
        "**Rule:** Must do X.\n**Why:** Because Y.\n**Test:** Check Z.\n**Violations:** None.\n\n"
        "## Boundary Definitions\n\n"
        "### ALWAYS\n- Always do A\n\n"
        "### ASK FIRST\n- Ask about B\n\n"
        "### NEVER\n- Never do C\n"
    )
    (spec / "D2_SPECIFICATION.md").write_text(
        "# D2: Specification\n\n**Component:** Test Component\n**Package ID:** PKG-TEST-001\n\n"
        "## Component Purpose\n\nTest purpose.\n\n"
        "## What This Component Is NOT\n\nNot a widget.\n\n"
        "## User Scenarios\n\n"
        "#### SC-001: Basic scenario\n\n**Priority:** P1\n\n"
        "**GIVEN** a test input\n**WHEN** the user runs test\n**THEN** it passes\n\n"
        "**Testing Approach:** Unit test.\n\n"
        "#### SC-002: Another scenario\n\n**Priority:** P1\n\n"
        "**GIVEN** another input\n**WHEN** the user runs again\n**THEN** it works\n\n"
        "## Deferred Capabilities\n\n"
        "## Success Criteria\n\n- All tests pass\n"
    )
    (spec / "D3_DATA_MODEL.md").write_text(
        "# D3: Data Model\n\n## Entities\n\n"
        "### E-001: Widget (PRIVATE)\n\n"
        "**Scope:** PRIVATE\n**Description:** A widget.\n\n"
        "| Field | Type | Required | Description | Constraints |\n"
        "|-------|------|----------|-------------|-------------|\n"
        "| name | string | yes | Widget name | Non-empty |\n"
    )
    (spec / "D4_CONTRACTS.md").write_text(
        "# D4: Contracts\n\n## Inbound Contracts\n\n"
        "#### IN-001: Create Widget\n\n**Scenarios:** SC-001\n\n"
        "## Outbound Contracts\n\n"
        "#### OUT-001: Widget Report\n\n**Scenarios:** SC-001\n\n"
        "## Side-Effect Contracts\n\n"
        "## Error Contracts\n\n"
        "#### ERR-001: WIDGET_MISSING\n\n**Scenarios:** SC-002\n\n"
    )
    (spec / "D5_RESEARCH.md").write_text(
        "# D5: Research\n\n## Research Log\n\n"
        "#### RQ-001: How to build widgets?\n\n"
        "**Decision:** Use Python.\n**Rationale:** It works.\n"
    )
    (spec / "D6_GAP_ANALYSIS.md").write_text(
        "# D6: Gap Analysis\n\n## Boundary Analysis\n\n"
        "#### GAP-001: Widget API (RESOLVED)\n\n"
        "**Category:** External\n**Status:** RESOLVED\n\n"
        "## Clarification Log\n\n"
        "#### CLR-001: Widget color\n\n"
        "**Status:** RESOLVED(blue is fine)\n"
    )
    (spec / "D7_PLAN.md").write_text(
        "# D7: Plan\n\n## Summary\n\nBuild a widget.\n\n"
        "## Architecture Overview\n\nSimple.\n\n"
        "## File Creation Order\n\nwidget.py first.\n\n"
        "## Testing Strategy\n\npytest.\n"
    )
    (spec / "D8_TASKS.md").write_text(
        "# D8: Tasks\n\n## Phase 0\n\n"
        "#### T-001: Build Widget\n\n"
        "**Phase:** 0\n**Dependency:** None\n**Scope:** M\n"
        "**Scenarios Satisfied:** SC-001, SC-002\n"
        "**Contracts Implemented:** IN-001, OUT-001, ERR-001\n\n"
        "**Acceptance Criteria:**\n- Build the widget\n- Test it\n"
    )
    (spec / "D9_HOLDOUT_SCENARIOS.md").write_text(
        "# D9: Holdout Scenarios\n\n## Scenarios\n\n"
        "### HS-001: Widget creates output\n\n"
        "```yaml\ncomponent: test\nscenario: basic\npriority: P0\n```\n\n"
        "**Validates:** SC-001\n**Contracts:** IN-001, OUT-001\n\n"
        "**Setup:**\n```bash\nmkdir -p /tmp/test\n```\n\n"
        "**Execute:**\n```bash\npython3 -c \"print('ok')\"\n```\n\n"
        "**Verify:**\n```bash\ntest -f /tmp/test || true\n```\n\n"
        "**Cleanup:**\n```bash\nrm -rf /tmp/test\n```\n\n"
        "### HS-002: Widget handles errors\n\n"
        "```yaml\ncomponent: test\nscenario: error\npriority: P0\n```\n\n"
        "**Validates:** SC-002\n**Contracts:** ERR-001\n\n"
        "**Setup:**\n```bash\necho setup\n```\n\n"
        "**Execute:**\n```bash\necho execute\n```\n\n"
        "**Verify:**\n```bash\necho verify\n```\n\n"
        "**Cleanup:**\n```bash\necho cleanup\n```\n\n"
        "### HS-003: Widget is deterministic\n\n"
        "```yaml\ncomponent: test\nscenario: deterministic\npriority: P1\n```\n\n"
        "**Validates:** SC-001\n**Contracts:** OUT-001\n\n"
        "**Setup:**\n```bash\necho setup\n```\n\n"
        "**Execute:**\n```bash\necho execute\n```\n\n"
        "**Verify:**\n```bash\necho verify\n```\n\n"
        "**Cleanup:**\n```bash\necho cleanup\n```\n"
    )
    (spec / "D10_AGENT_CONTEXT.md").write_text(
        "# D10: Agent Context\n\n## Commands\n\n```bash\npython3 -m widget\n```\n\n"
        "## Tool Rules\n\nUse WidgetBuilder.\n\n"
        "## Coding Conventions\n\nPEP8.\n"
    )
    return spec


@pytest.fixture
def incomplete_spec_dir(minimal_spec_dir: Path) -> Path:
    """Spec directory with D3 removed."""
    (minimal_spec_dir / "D3_DATA_MODEL.md").unlink()
    return minimal_spec_dir


@pytest.fixture
def cyclic_spec_dir(minimal_spec_dir: Path) -> Path:
    """Spec directory with a D8 dependency cycle."""
    d8 = minimal_spec_dir / "D8_TASKS.md"
    d8.write_text(
        "# D8: Tasks\n\n## Phase 0\n\n"
        "#### T-001: Task A\n\n"
        "**Phase:** 0\n**Dependency:** T-002\n**Scope:** M\n"
        "**Scenarios Satisfied:** SC-001\n"
        "**Contracts Implemented:** IN-001\n\n"
        "#### T-002: Task B\n\n"
        "**Phase:** 0\n**Dependency:** T-001\n**Scope:** M\n"
        "**Scenarios Satisfied:** SC-002\n"
        "**Contracts Implemented:** OUT-001, ERR-001\n\n"
    )
    return minimal_spec_dir


@pytest.fixture
def open_d6_spec_dir(minimal_spec_dir: Path) -> Path:
    """Spec directory with an OPEN D6 clarification."""
    d6 = minimal_spec_dir / "D6_GAP_ANALYSIS.md"
    d6.write_text(
        "# D6: Gap Analysis\n\n## Boundary Analysis\n\n"
        "## Clarification Log\n\n"
        "#### CLR-001: Widget color\n\n"
        "**Status:** OPEN\n**Question:** What color?\n"
    )
    return minimal_spec_dir
