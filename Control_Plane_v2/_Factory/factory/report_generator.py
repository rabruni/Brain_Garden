"""Report generator — verdict assembly (T-007)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from factory.models import (
    DispatchRecord,
    FactoryReport,
    HoldoutResult,
    ProductSpec,
    ValidationResult,
)


def _compute_verdict(
    dispatches: list[DispatchRecord],
    holdouts: list[HoldoutResult],
) -> tuple[str, str]:
    """Compute verdict: ACCEPT, REJECT, or PARTIAL.

    ACCEPT: all P0 holdouts pass + all tasks COMPLETED
    REJECT: any P0 holdout fails
    PARTIAL: mixed results
    """
    # Check P0 holdouts
    p0_holdouts = [h for h in holdouts if h.priority == "P0"]
    p0_failures = [h for h in p0_holdouts if h.status != "PASS"]

    if p0_failures:
        failing_ids = ", ".join(h.holdout_id for h in p0_failures)
        return "REJECT", f"P0 holdout(s) failed: {failing_ids}"

    # Check task dispatches
    failed_tasks = [d for d in dispatches if d.status == "FAILED"]
    blocked_tasks = [d for d in dispatches if d.status == "BLOCKED"]
    completed_tasks = [d for d in dispatches if d.status == "COMPLETED"]

    if failed_tasks or blocked_tasks:
        if completed_tasks:
            failed_ids = ", ".join(d.task_id for d in failed_tasks)
            blocked_ids = ", ".join(d.task_id for d in blocked_tasks)
            parts = []
            if failed_ids:
                parts.append(f"failed: {failed_ids}")
            if blocked_ids:
                parts.append(f"blocked: {blocked_ids}")
            return "PARTIAL", f"Some tasks completed, some {'; '.join(parts)}"
        else:
            return "REJECT", "All tasks failed or blocked"

    # All tasks completed, all P0 passed
    if not holdouts:
        if all(d.status == "COMPLETED" for d in dispatches):
            return "ACCEPT", "All tasks completed (no holdouts run)"
        return "PARTIAL", "No holdouts run and some tasks incomplete"

    # Check all holdouts
    all_passed = all(h.status == "PASS" for h in holdouts)
    if all_passed and all(d.status == "COMPLETED" for d in dispatches):
        return "ACCEPT", "All tasks completed and all holdouts passed"

    return "PARTIAL", "Mixed holdout results"


def generate_report(
    spec: ProductSpec,
    validation: ValidationResult,
    dispatches: list[DispatchRecord],
    holdouts: list[HoldoutResult],
    duration_ms: int = 0,
) -> FactoryReport:
    """Assemble a FactoryReport from pipeline results.

    Computes verdict and total tokens.
    """
    total_tokens = sum(d.tokens_used or 0 for d in dispatches)
    verdict, verdict_reason = _compute_verdict(dispatches, holdouts)

    return FactoryReport(
        spec_dir=spec.spec_dir,
        component_name=spec.component_name,
        validation=validation,
        dispatches=dispatches,
        holdouts=holdouts,
        verdict=verdict,
        verdict_reason=verdict_reason,
        total_tokens=total_tokens,
        total_duration_ms=duration_ms,
    )


def write_report(report: FactoryReport, output_dir: str | Path) -> Path:
    """Write report as JSON and human-readable markdown."""
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    # JSON report
    json_path = out_path / "factory_report.json"
    json_path.write_text(report.to_json(indent=2), encoding="utf-8")

    # Markdown summary
    md_path = out_path / "factory_report.md"
    md_lines = [
        f"# Factory Report: {report.component_name}",
        "",
        f"**Verdict:** {report.verdict}",
        f"**Reason:** {report.verdict_reason}",
        f"**Spec Directory:** {report.spec_dir}",
        f"**Total Tokens:** {report.total_tokens}",
        f"**Duration:** {report.total_duration_ms}ms",
        "",
        "## Validation",
        f"Status: {report.validation.status}",
        "",
    ]

    for check in report.validation.checks:
        md_lines.append(f"- {check.check_name}: {check.status} — {check.message}")

    md_lines.extend(["", "## Dispatches", ""])
    for d in report.dispatches:
        md_lines.append(f"- {d.task_id} ({d.handoff_id}): {d.status}")
        if d.error:
            md_lines.append(f"  - Error: {d.error}")

    md_lines.extend(["", "## Holdouts", ""])
    for h in report.holdouts:
        md_lines.append(f"- {h.holdout_id} ({h.priority}): {h.status}")
        if h.error_message:
            md_lines.append(f"  - Error: {h.error_message}")
        if h.actual_output:
            md_lines.append(f"  - Actual: {h.actual_output[:100]}")

    md_path.write_text("\n".join(md_lines), encoding="utf-8")

    return json_path
