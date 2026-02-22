"""Handoff document generator (T-003)."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from factory.models import GenerationError, Handoff, ProductSpec


_TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "templates" / "handoff_template.md"

# D9 leak detection: only HS-NNN scenario IDs (not generic "holdout" word,
# which legitimately appears in D1 governance articles about holdout isolation)
_HS_ID_PATTERN = re.compile(r"HS-\d+")


def _load_template() -> str:
    """Load the handoff markdown template."""
    if not _TEMPLATE_PATH.exists():
        raise GenerationError(f"Handoff template not found: {_TEMPLATE_PATH}")
    return _TEMPLATE_PATH.read_text(encoding="utf-8")


def _format_list(items: list[str], numbered: bool = True) -> str:
    """Format a list of items as numbered or bulleted markdown."""
    if not items:
        return "None specified."
    if numbered:
        return "\n".join(f"{i+1}. {item}" for i, item in enumerate(items))
    return "\n".join(f"- {item}" for item in items)


def _check_no_d9_leakage(text: str, spec: ProductSpec) -> None:
    """Verify no D9 holdout *execution content* leaked into output.

    D1 Article 2 prohibits D9 scenario content from being visible to builders.
    However, D2 scenarios and D1 articles legitimately reference holdout concepts
    (e.g., SC-004 describes running holdouts, D1 Article 2 governs holdout isolation).
    These references come from D2/D1, not D9 — they are architectural descriptions,
    not the actual holdout setup/execute/verify commands.

    What we check: D9 setup, execute, verify, and cleanup bash blocks should not
    appear in the generated handoff.
    """
    for hs in spec.holdouts.scenarios:
        # Check for D9 executable content (the actual secret holdout tests)
        for block_name, block_content in [
            ("setup", hs.setup),
            ("execute", hs.execute),
            ("verify", hs.verify),
            ("cleanup", hs.cleanup),
        ]:
            # Only check non-trivial blocks (>20 chars) to avoid false positives
            # on common snippets like "echo ok"
            if block_content and len(block_content.strip()) > 20 and block_content.strip() in text:
                raise GenerationError(
                    f"D9 holdout {hs.id} {block_name} content leaked into handoff. "
                    "D1 Article 2 violation."
                )


def _build_constraints(spec: ProductSpec) -> list[str]:
    """Build critical constraints from D1 articles."""
    constraints: list[str] = []
    for article in spec.constitution.articles:
        if article.rule:
            constraints.append(f"**{article.name}:** {article.rule}")
    # Add boundary NEVER items
    for item in spec.constitution.boundaries.never:
        constraints.append(f"**NEVER:** {item}")
    return constraints


def _build_test_plan(spec: ProductSpec, task_scenario_ids: list[str]) -> list[str]:
    """Build test plan from D2 scenarios mapped to this task."""
    tests: list[str] = []
    sc_map = {s.id: s for s in spec.specification.scenarios}
    for sc_id in sorted(task_scenario_ids):
        sc = sc_map.get(sc_id)
        if sc:
            tests.append(
                f"**{sc.id}: {sc.title}** — "
                f"GIVEN {sc.given}; WHEN {sc.when}; THEN {sc.then}"
            )
    return tests


def generate(spec: ProductSpec, output_dir: str | Path) -> list[Handoff]:
    """Generate handoff documents from a validated ProductSpec.

    One handoff per D8 task, following BUILDER_HANDOFF_STANDARD.md format.
    Writes files to output_dir and returns Handoff objects.

    Raises GenerationError on failure.
    """
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    template = _load_template()
    handoffs: list[Handoff] = []

    for idx, task in enumerate(sorted(spec.tasks.tasks, key=lambda t: t.id), start=1):
        handoff_id = f"H-FACTORY-{idx:03d}"
        handoff_dir = out_path / handoff_id
        handoff_dir.mkdir(parents=True, exist_ok=True)

        # Build section content
        constraints = _build_constraints(spec)
        test_plan = _build_test_plan(spec, task.scenarios_satisfied)

        # Architecture: scoped from D7
        architecture = spec.plan.architecture or spec.plan.summary or "See D7 Plan."

        # Implementation steps from D8 acceptance criteria
        impl_steps: list[str] = []
        if task.acceptance_criteria:
            for line in task.acceptance_criteria.splitlines():
                stripped = line.strip()
                m = re.match(r"^[-*]\s+(.+)$", stripped)
                if m:
                    impl_steps.append(m.group(1))
        if not impl_steps:
            impl_steps = [task.acceptance_criteria or task.description[:200]]

        # Package plan from D7
        package_plan = spec.plan.file_creation_order or "See D7 file creation order."

        # Existing code refs from D10
        existing_refs = spec.agent_context.tool_rules or "See D10."

        # Verification commands from D10
        verification_cmds: list[str] = []
        if spec.agent_context.commands:
            for line in spec.agent_context.commands.splitlines():
                stripped = line.strip()
                if stripped and not stripped.startswith("#") and not stripped.startswith("```"):
                    verification_cmds.append(stripped)

        # Files summary from D7
        files_summary = spec.plan.file_creation_order or "See D7."

        # Design principles from D1
        design_principles: list[str] = []
        for article in spec.constitution.articles:
            if article.rule:
                design_principles.append(article.rule)

        # Render template
        rendered = template.format_map({
            "handoff_id": handoff_id,
            "task_id": task.id,
            "task_title": task.title,
            "scenario_ids": ", ".join(sorted(task.scenarios_satisfied)),
            "contract_ids": ", ".join(sorted(task.contracts_implemented)),
            "mission": task.description[:500] if task.description else task.title,
            "critical_constraints": _format_list(constraints),
            "architecture": architecture,
            "implementation_steps": _format_list(impl_steps),
            "package_plan": package_plan,
            "test_plan": _format_list(test_plan, numbered=False),
            "existing_code_refs": existing_refs,
            "verification_commands": _format_list(verification_cmds, numbered=False),
            "files_summary": files_summary,
            "design_principles": _format_list(design_principles, numbered=False),
        })

        # D9 leak check (D1 Article 2)
        _check_no_d9_leakage(rendered, spec)

        # Write file
        file_path = handoff_dir / f"{handoff_id}_BUILDER_HANDOFF.md"
        file_path.write_text(rendered, encoding="utf-8")

        handoff = Handoff(
            handoff_id=handoff_id,
            task_id=task.id,
            mission=task.title,
            scenarios=sorted(task.scenarios_satisfied),
            contracts=sorted(task.contracts_implemented),
            critical_constraints=constraints,
            architecture=architecture,
            implementation_steps=impl_steps,
            package_plan=package_plan,
            test_plan=test_plan,
            existing_code_refs=[existing_refs] if existing_refs else [],
            verification_commands=verification_cmds,
            files_summary=files_summary,
            design_principles=design_principles,
            output_path=str(file_path),
        )
        handoffs.append(handoff)

    # Write handoff index
    index: dict[str, Any] = {
        "spec_dir": spec.spec_dir,
        "component_name": spec.component_name,
        "handoffs": [
            {
                "handoff_id": h.handoff_id,
                "task_id": h.task_id,
                "scenarios": h.scenarios,
                "contracts": h.contracts,
                "output_path": h.output_path,
            }
            for h in handoffs
        ],
    }
    index_path = out_path / "handoff_index.json"
    index_path.write_text(json.dumps(index, indent=2), encoding="utf-8")

    return handoffs
