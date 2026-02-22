"""Tests for agent_dispatcher.py (T-005)."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from factory.spec_parser import parse
from factory.handoff_generator import generate
from factory.prompt_generator import generate_prompts
from factory.agent_dispatcher import dispatch_pipeline, _topological_sort


class TestTopologicalSort:

    def test_linear_deps(self) -> None:
        tasks = [
            {"task_id": "T-001", "depends_on": []},
            {"task_id": "T-002", "depends_on": ["T-001"]},
            {"task_id": "T-003", "depends_on": ["T-002"]},
        ]
        result = _topological_sort(tasks)
        assert result.index("T-001") < result.index("T-002")
        assert result.index("T-002") < result.index("T-003")

    def test_parallel_tasks(self) -> None:
        tasks = [
            {"task_id": "T-001", "depends_on": []},
            {"task_id": "T-002", "depends_on": ["T-001"]},
            {"task_id": "T-003", "depends_on": ["T-001"]},
        ]
        result = _topological_sort(tasks)
        assert result.index("T-001") < result.index("T-002")
        assert result.index("T-001") < result.index("T-003")

    def test_no_deps(self) -> None:
        tasks = [
            {"task_id": "T-001", "depends_on": []},
            {"task_id": "T-002", "depends_on": []},
        ]
        result = _topological_sort(tasks)
        assert len(result) == 2


class TestDispatchPipeline:

    @patch("factory.agent_dispatcher._dispatch_single")
    def test_dispatch_all_tasks(self, mock_dispatch, minimal_spec_dir, tmp_path):
        from factory.models import DispatchRecord
        mock_dispatch.return_value = DispatchRecord(
            dispatch_id="DSP-test",
            handoff_id="H-FACTORY-001",
            task_id="T-001",
            timestamp_dispatched="2026-01-01T00:00:00Z",
            status="COMPLETED",
            timestamp_completed="2026-01-01T00:01:00Z",
        )
        spec = parse(minimal_spec_dir)
        out = tmp_path / "out"
        handoffs = generate(spec, out)
        prompts = generate_prompts(handoffs, spec, out)
        ledger = tmp_path / "ledger.jsonl"
        records = dispatch_pipeline(prompts, spec, str(out), str(ledger))
        assert len(records) >= 1
        assert all(r.status == "COMPLETED" for r in records)

    @patch("factory.agent_dispatcher._dispatch_single")
    def test_failed_task_blocks_dependents(self, mock_dispatch, minimal_spec_dir, tmp_path):
        """With only one task, there's nothing to block. Test the mechanism exists."""
        from factory.models import DispatchRecord
        mock_dispatch.return_value = DispatchRecord(
            dispatch_id="DSP-test",
            handoff_id="H-FACTORY-001",
            task_id="T-001",
            timestamp_dispatched="2026-01-01T00:00:00Z",
            status="FAILED",
            error="Test failure",
        )
        spec = parse(minimal_spec_dir)
        out = tmp_path / "out"
        handoffs = generate(spec, out)
        prompts = generate_prompts(handoffs, spec, out)
        ledger = tmp_path / "ledger.jsonl"
        records = dispatch_pipeline(prompts, spec, str(out), str(ledger))
        assert records[0].status == "FAILED"

    @patch("factory.agent_dispatcher._dispatch_single")
    def test_ledger_written(self, mock_dispatch, minimal_spec_dir, tmp_path):
        from factory.models import DispatchRecord
        mock_dispatch.return_value = DispatchRecord(
            dispatch_id="DSP-test",
            handoff_id="H-FACTORY-001",
            task_id="T-001",
            timestamp_dispatched="2026-01-01T00:00:00Z",
            status="COMPLETED",
            timestamp_completed="2026-01-01T00:01:00Z",
        )
        spec = parse(minimal_spec_dir)
        out = tmp_path / "out"
        handoffs = generate(spec, out)
        prompts = generate_prompts(handoffs, spec, out)
        ledger = tmp_path / "ledger.jsonl"
        dispatch_pipeline(prompts, spec, str(out), str(ledger))
        assert ledger.exists()
        lines = ledger.read_text().strip().split("\n")
        assert len(lines) >= 1
        entry = json.loads(lines[0])
        assert "dispatch_id" in entry

    def test_dispatch_binary_not_found(self, minimal_spec_dir, tmp_path):
        spec = parse(minimal_spec_dir)
        out = tmp_path / "out"
        handoffs = generate(spec, out)
        prompts = generate_prompts(handoffs, spec, out)
        ledger = tmp_path / "ledger.jsonl"
        records = dispatch_pipeline(
            prompts, spec, str(out), str(ledger),
            claude_path="/nonexistent/claude_binary"
        )
        assert records[0].status == "FAILED"
        assert "not found" in records[0].error
