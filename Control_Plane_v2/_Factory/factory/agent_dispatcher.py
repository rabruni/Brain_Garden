"""Agent dispatcher — Claude Code subprocess dispatch (T-005)."""
from __future__ import annotations

import json
import os
import subprocess
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from factory.models import AgentPrompt, DispatchError, DispatchRecord, ProductSpec


def _topological_sort(tasks: list[dict[str, Any]]) -> list[str]:
    """Topological sort of task IDs by depends_on. Returns sorted IDs."""
    task_ids = {t["task_id"] for t in tasks}
    deps: dict[str, list[str]] = {}
    for t in tasks:
        deps[t["task_id"]] = [d for d in t.get("depends_on", []) if d in task_ids]

    in_degree: dict[str, int] = defaultdict(int)
    successors: dict[str, list[str]] = defaultdict(list)
    for tid in task_ids:
        in_degree[tid] = 0
    for tid, dep_list in deps.items():
        for dep in dep_list:
            successors[dep].append(tid)
            in_degree[tid] += 1

    queue = sorted([tid for tid in task_ids if in_degree[tid] == 0])
    result: list[str] = []
    while queue:
        node = queue.pop(0)
        result.append(node)
        for succ in sorted(successors[node]):
            in_degree[succ] -= 1
            if in_degree[succ] == 0:
                queue.append(succ)

    # Append any remaining (cycle participants) at end
    remaining = sorted(task_ids - set(result))
    result.extend(remaining)
    return result


def _write_ledger_entry(ledger_path: Path, record: DispatchRecord) -> None:
    """Append a dispatch record to the JSONL ledger."""
    with open(ledger_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record.to_dict()) + "\n")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dispatch_single(
    prompt: AgentPrompt,
    workdir: str,
    timeout: int = 600,
    claude_path: str | None = None,
) -> DispatchRecord:
    """Dispatch a single agent via Claude Code subprocess."""
    dispatch_id = f"DSP-{uuid.uuid4().hex[:8]}"
    ts_dispatched = _now_iso()

    claude_bin = claude_path or os.environ.get("FACTORY_CLAUDE_PATH", "claude")

    cmd = [
        claude_bin,
        "--print",
        "--allowedTools", "Read,Write,Edit,Bash,Glob,Grep",
        "--workdir", workdir,
        "-p", prompt.prompt_text,
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=workdir,
        )
        ts_completed = _now_iso()

        if result.returncode != 0:
            return DispatchRecord(
                dispatch_id=dispatch_id,
                handoff_id=prompt.handoff_id,
                task_id=prompt.handoff_id,  # Will be resolved by caller
                timestamp_dispatched=ts_dispatched,
                status="FAILED",
                timestamp_completed=ts_completed,
                error=f"Process exited with code {result.returncode}: {result.stderr[:500]}",
            )

        return DispatchRecord(
            dispatch_id=dispatch_id,
            handoff_id=prompt.handoff_id,
            task_id=prompt.handoff_id,
            timestamp_dispatched=ts_dispatched,
            status="COMPLETED",
            timestamp_completed=ts_completed,
            tokens_used=None,  # MVP: token extraction stubbed
        )

    except subprocess.TimeoutExpired:
        return DispatchRecord(
            dispatch_id=dispatch_id,
            handoff_id=prompt.handoff_id,
            task_id=prompt.handoff_id,
            timestamp_dispatched=ts_dispatched,
            status="FAILED",
            timestamp_completed=_now_iso(),
            error=f"Process timed out after {timeout}s",
        )
    except FileNotFoundError:
        return DispatchRecord(
            dispatch_id=dispatch_id,
            handoff_id=prompt.handoff_id,
            task_id=prompt.handoff_id,
            timestamp_dispatched=ts_dispatched,
            status="FAILED",
            timestamp_completed=_now_iso(),
            error=f"Claude Code binary not found: {claude_bin}",
        )


def dispatch_pipeline(
    prompts: list[AgentPrompt],
    spec: ProductSpec,
    workdir: str | Path,
    ledger_path: str | Path,
    timeout: int = 600,
    claude_path: str | None = None,
) -> list[DispatchRecord]:
    """Dispatch all prompts in dependency order.

    - Topological sort by D8 dependencies
    - Failed task → dependent tasks marked BLOCKED
    - Records to JSONL ledger
    """
    work_path = Path(workdir)
    work_path.mkdir(parents=True, exist_ok=True)
    led_path = Path(ledger_path)

    # Build prompt map: handoff_id → prompt
    prompt_map = {p.handoff_id: p for p in prompts}

    # Build task info for topo sort
    task_info: list[dict[str, Any]] = []
    handoff_to_task: dict[str, str] = {}
    task_to_handoff: dict[str, str] = {}

    for prompt in prompts:
        # Find the D8 task for this handoff
        # Handoffs are H-FACTORY-NNN matching task order
        for task in spec.tasks.tasks:
            # Match by index in sorted order
            pass

    # Simpler approach: handoffs are generated in task ID order
    sorted_tasks = sorted(spec.tasks.tasks, key=lambda t: t.id)
    sorted_prompts = sorted(prompts, key=lambda p: p.handoff_id)

    for task, prompt in zip(sorted_tasks, sorted_prompts):
        handoff_to_task[prompt.handoff_id] = task.id
        task_to_handoff[task.id] = prompt.handoff_id
        task_info.append({
            "task_id": task.id,
            "depends_on": list(task.depends_on),
        })

    # Topological sort
    dispatch_order = _topological_sort(task_info)

    # Dispatch
    records: list[DispatchRecord] = []
    failed_tasks: set[str] = set()
    blocked_tasks: set[str] = set()

    for task_id in dispatch_order:
        handoff_id = task_to_handoff.get(task_id)
        if not handoff_id or handoff_id not in prompt_map:
            continue

        prompt = prompt_map[handoff_id]

        # Check if blocked by failed dependency
        task_obj = next((t for t in spec.tasks.tasks if t.id == task_id), None)
        if task_obj:
            blocked_by = [d for d in task_obj.depends_on if d in failed_tasks or d in blocked_tasks]
            if blocked_by:
                blocked_tasks.add(task_id)
                record = DispatchRecord(
                    dispatch_id=f"DSP-{uuid.uuid4().hex[:8]}",
                    handoff_id=handoff_id,
                    task_id=task_id,
                    timestamp_dispatched=_now_iso(),
                    status="BLOCKED",
                    error=f"Blocked by failed task(s): {', '.join(blocked_by)}",
                )
                _write_ledger_entry(led_path, record)
                records.append(record)
                continue

        # Dispatch
        record = _dispatch_single(prompt, str(work_path), timeout, claude_path)
        # Fix task_id
        record = DispatchRecord(
            dispatch_id=record.dispatch_id,
            handoff_id=record.handoff_id,
            task_id=task_id,
            timestamp_dispatched=record.timestamp_dispatched,
            status=record.status,
            timestamp_completed=record.timestamp_completed,
            results_path=record.results_path,
            error=record.error,
            tokens_used=record.tokens_used,
        )

        # Write DISPATCHED then result
        _write_ledger_entry(led_path, record)
        records.append(record)

        if record.status == "FAILED":
            failed_tasks.add(task_id)

    return records
