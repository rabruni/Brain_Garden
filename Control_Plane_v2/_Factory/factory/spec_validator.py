"""Spec completeness and consistency validator (T-002)."""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from factory.models import CheckResult, ProductSpec, ValidationResult


def _check_all_documents_present(spec: ProductSpec) -> CheckResult:
    """Check that all 10 D-documents were parsed (non-empty)."""
    docs = [
        ("D1", spec.constitution),
        ("D2", spec.specification),
        ("D3", spec.data_model),
        ("D4", spec.contracts),
        ("D5", spec.research),
        ("D6", spec.gap_analysis),
        ("D7", spec.plan),
        ("D8", spec.tasks),
        ("D9", spec.holdouts),
        ("D10", spec.agent_context),
    ]
    present = sum(1 for _, d in docs if d is not None)
    return CheckResult(
        check_name="all_documents_present",
        status="PASS" if present == 10 else "FAIL",
        message=f"{present}/10 documents found",
    )


def _check_d6_no_open_items(spec: ProductSpec) -> CheckResult:
    """Check D6 has zero OPEN clarifications."""
    open_items: list[str] = []
    for clr in spec.gap_analysis.clarifications:
        if clr.status == "OPEN":
            open_items.append(f"{clr.id} [{clr.title}]")
    for gap in spec.gap_analysis.gaps:
        if gap.status == "OPEN":
            open_items.append(f"{gap.id} [{gap.title}]")

    if open_items:
        return CheckResult(
            check_name="d6_no_open_items",
            status="FAIL",
            message=f"D6 has {len(open_items)} OPEN clarification(s): {', '.join(open_items)}. Resolve before proceeding.",
            details=open_items,
        )
    return CheckResult(
        check_name="d6_no_open_items",
        status="PASS",
        message="0 OPEN clarifications",
    )


def _check_d2_scenarios_covered(spec: ProductSpec) -> CheckResult:
    """Check every D2 scenario is covered by at least one D8 task."""
    all_sc = {s.id for s in spec.specification.scenarios}
    covered_sc: set[str] = set()
    for task in spec.tasks.tasks:
        covered_sc.update(task.scenarios_satisfied)

    uncovered = sorted(all_sc - covered_sc)
    if uncovered:
        return CheckResult(
            check_name="d2_scenarios_covered",
            status="FAIL",
            message=f"{len(uncovered)} scenario(s) not covered by D8",
            details=uncovered,
        )
    return CheckResult(
        check_name="d2_scenarios_covered",
        status="PASS",
        message=f"{len(all_sc)}/{len(all_sc)} scenarios covered by D8",
    )


def _check_d4_contracts_covered(spec: ProductSpec) -> CheckResult:
    """Check every D4 contract is assigned to at least one D8 task."""
    all_ct = set(spec.contracts.all_ids())
    covered_ct: set[str] = set()
    for task in spec.tasks.tasks:
        covered_ct.update(task.contracts_implemented)

    uncovered = sorted(all_ct - covered_ct)
    if uncovered:
        return CheckResult(
            check_name="d4_contracts_covered",
            status="FAIL",
            message=f"{len(uncovered)} contract(s) not assigned to D8 tasks",
            details=uncovered,
        )
    return CheckResult(
        check_name="d4_contracts_covered",
        status="PASS",
        message=f"{len(all_ct)}/{len(all_ct)} contracts assigned to D8 tasks",
    )


def _check_d9_minimum_holdouts(spec: ProductSpec) -> CheckResult:
    """Check D9 has at least 3 holdout scenarios."""
    count = len(spec.holdouts.scenarios)
    if count < 3:
        return CheckResult(
            check_name="d9_minimum_holdouts",
            status="FAIL",
            message=f"{count} holdout scenario(s) (minimum 3)",
        )
    return CheckResult(
        check_name="d9_minimum_holdouts",
        status="PASS",
        message=f"{count} holdout scenarios (>= 3)",
    )


def _check_d8_no_dependency_cycles(spec: ProductSpec) -> CheckResult:
    """Check D8 task dependency graph has no cycles (Kahn's algorithm)."""
    tasks = spec.tasks.tasks
    task_ids = {t.id for t in tasks}

    # Build adjacency and in-degree
    in_degree: dict[str, int] = defaultdict(int)
    successors: dict[str, list[str]] = defaultdict(list)

    for t in tasks:
        if t.id not in in_degree:
            in_degree[t.id] = 0
        for dep in t.depends_on:
            if dep in task_ids:
                successors[dep].append(t.id)
                in_degree[t.id] += 1

    # Kahn's
    queue = sorted([tid for tid in task_ids if in_degree[tid] == 0])
    sorted_order: list[str] = []

    while queue:
        node = queue.pop(0)
        sorted_order.append(node)
        for succ in sorted(successors[node]):
            in_degree[succ] -= 1
            if in_degree[succ] == 0:
                queue.append(succ)

    if len(sorted_order) != len(task_ids):
        # Find cycle participants
        cycle_nodes = sorted(task_ids - set(sorted_order))
        # Trace one cycle for reporting
        cycle_str = _trace_cycle(cycle_nodes, {t.id: t.depends_on for t in tasks}, task_ids)
        return CheckResult(
            check_name="d8_no_dependency_cycles",
            status="FAIL",
            message=f"Dependency cycle detected in D8: {cycle_str}",
            details=cycle_nodes,
        )

    return CheckResult(
        check_name="d8_no_dependency_cycles",
        status="PASS",
        message=f"{len(tasks)} tasks, 0 cycles",
    )


def _trace_cycle(cycle_nodes: list[str], deps: dict[str, list[str]],
                 all_ids: set[str]) -> str:
    """Trace and format one cycle from the stuck nodes."""
    if not cycle_nodes:
        return "unknown cycle"
    start = cycle_nodes[0]
    path = [start]
    current = start
    visited: set[str] = set()
    for _ in range(len(cycle_nodes) + 1):
        visited.add(current)
        next_nodes = [d for d in deps.get(current, []) if d in all_ids and d in set(cycle_nodes)]
        if not next_nodes:
            break
        nxt = next_nodes[0]
        path.append(nxt)
        if nxt in visited:
            break
        current = nxt
    return " → ".join(path)


def validate(spec: ProductSpec) -> ValidationResult:
    """Validate a parsed ProductSpec for completeness and consistency.

    Returns a ValidationResult with per-check status.
    """
    checks = [
        _check_all_documents_present(spec),
        _check_d6_no_open_items(spec),
        _check_d2_scenarios_covered(spec),
        _check_d4_contracts_covered(spec),
        _check_d9_minimum_holdouts(spec),
        _check_d8_no_dependency_cycles(spec),
    ]

    overall = "PASS" if all(c.status == "PASS" for c in checks) else "FAIL"

    summary = None
    if overall == "PASS":
        summary = {
            "documents": 10,
            "scenarios": len(spec.specification.scenarios),
            "tasks": len(spec.tasks.tasks),
            "holdouts": len(spec.holdouts.scenarios),
        }

    return ValidationResult(
        status=overall,
        spec_dir=spec.spec_dir,
        checks=checks,
        component_name=spec.component_name,
        summary=summary,
    )
