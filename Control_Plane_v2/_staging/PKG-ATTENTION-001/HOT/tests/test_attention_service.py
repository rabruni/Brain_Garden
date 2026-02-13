"""
Tests for PKG-ATTENTION-001: Attention Service + Pipeline Stages.

DTT: These tests are written BEFORE implementation.
40 tests across 7 groups:
  - Template Resolution (7)
  - Required Context Merge (4)
  - Pipeline Execution (12)
  - Budget Enforcement (8)
  - Output (4)
  - Caching (3)
  - Token Estimation (2)
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import patch

import pytest

# Imports from the modules under test
from kernel.attention_stages import (
    STAGE_RUNNERS,
    ContextFragment,
    ContextProvider,
    PipelineState,
    StageOutput,
    run_custom,
    run_file_read,
    run_halting,
    run_horizontal_search,
    run_ledger_query,
    run_registry_query,
    run_structuring,
    run_tier_select,
)
from kernel.attention_service import (
    AssembledContext,
    AttentionRequest,
    AttentionService,
    BudgetTracker,
    BudgetUsed,
    ContextCache,
    StageResult,
    estimate_tokens,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def plane_root(tmp_path):
    """Create minimal plane layout for testing."""
    (tmp_path / "HOT" / "kernel").mkdir(parents=True)
    (tmp_path / "HOT" / "registries").mkdir(parents=True)
    (tmp_path / "HOT" / "attention_templates").mkdir(parents=True)
    (tmp_path / "HOT" / "ledger").mkdir(parents=True)

    # Write empty CSV registries with headers
    (tmp_path / "HOT" / "registries" / "frameworks_registry.csv").write_text(
        "framework_id,title,status,version,plane_id,created_at\n"
    )
    (tmp_path / "HOT" / "registries" / "specs_registry.csv").write_text(
        "spec_id,title,framework_id,status,version,plane_id,created_at\n"
    )
    (tmp_path / "HOT" / "registries" / "file_ownership.csv").write_text(
        "file_path,package_id,sha256,classification,installed_date,replaced_date,superseded_by\n"
    )
    return tmp_path


def make_template(plane_root, template_id, applies_to=None, pipeline=None, budget=None, fallback=None):
    """Write a template JSON file and return its path."""
    tpl = {
        "template_id": template_id,
        "version": "1.0.0",
        "pipeline": pipeline or [],
    }
    if applies_to is not None:
        tpl["applies_to"] = applies_to
    if budget is not None:
        tpl["budget"] = budget
    if fallback is not None:
        tpl["fallback"] = fallback
    path = plane_root / "HOT" / "attention_templates" / f"{template_id}.json"
    path.write_text(json.dumps(tpl))
    return path


def write_mock_ledger(plane_root, entries):
    """Write mock ledger entries as JSONL."""
    ledger_file = plane_root / "HOT" / "ledger" / "packages.jsonl"
    lines = [json.dumps(e) for e in entries]
    ledger_file.write_text("\n".join(lines) + "\n" if lines else "")


def make_request(
    agent_id="agent-1",
    agent_class="KERNEL.syntactic",
    framework_id="FMWK-000",
    tier="hot",
    work_order_id="WO-001",
    session_id="S-001",
    prompt_contract=None,
    template_override=None,
):
    """Build an AttentionRequest with sensible defaults."""
    return AttentionRequest(
        agent_id=agent_id,
        agent_class=agent_class,
        framework_id=framework_id,
        tier=tier,
        work_order_id=work_order_id,
        session_id=session_id,
        prompt_contract=prompt_contract or {},
        template_override=template_override,
    )


class MockContextProvider:
    """Replaces real I/O with test data."""

    def __init__(self, ledger_entries=None, registries=None, files=None):
        self.ledger_entries = ledger_entries or []
        self.registries = registries or {}
        self.files = files or {}
        self._query_count = 0

    def read_ledger_entries(self, event_type=None, max_entries=None, recency=None, filters=None):
        self._query_count += 1
        results = self.ledger_entries
        if event_type:
            results = [e for e in results if e.get("event_type") == event_type]
        if max_entries:
            results = results[:max_entries]
        return results

    def read_registry(self, registry_name, filters=None):
        self._query_count += 1
        rows = self.registries.get(registry_name, [])
        if filters:
            for key, val in filters.items():
                rows = [r for r in rows if r.get(key) == val]
        return rows

    def read_file(self, rel_path, max_size_bytes=None):
        content = self.files.get(rel_path)
        if content is not None and max_size_bytes is not None:
            content = content[:max_size_bytes]
        return content

    def search_text(self, query, sources, tiers):
        # Simple mock: return ledger entries with a fake relevance score
        results = []
        words = query.lower().split()
        for entry in self.ledger_entries:
            text = json.dumps(entry).lower()
            matches = sum(1 for w in words if w in text)
            if matches > 0:
                score = matches / len(words)
                results.append((json.dumps(entry), "ledger", score))
        for path, content in self.files.items():
            text = content.lower()
            matches = sum(1 for w in words if w in text)
            if matches > 0:
                score = matches / len(words)
                results.append((content, f"file:{path}", score))
        return results


# ---------------------------------------------------------------------------
# Group 1: Template Resolution (7 tests)
# ---------------------------------------------------------------------------

class TestTemplateResolution:
    """Test AttentionService.resolve_template() in isolation."""

    def test_resolve_by_agent_class(self, plane_root):
        make_template(
            plane_root, "ATT-SYNTACTIC-001",
            applies_to={"agent_class": ["KERNEL.syntactic"]},
            pipeline=[{"stage": "structuring", "type": "structuring", "config": {}}],
        )
        svc = AttentionService(plane_root)
        req = make_request(agent_class="KERNEL.syntactic")
        tpl = svc.resolve_template(req)
        assert tpl["template_id"] == "ATT-SYNTACTIC-001"

    def test_resolve_by_framework_id(self, plane_root):
        make_template(
            plane_root, "ATT-FMWK003-001",
            applies_to={"framework_id": ["FMWK-003"]},
            pipeline=[{"stage": "structuring", "type": "structuring", "config": {}}],
        )
        svc = AttentionService(plane_root)
        req = make_request(framework_id="FMWK-003")
        tpl = svc.resolve_template(req)
        assert tpl["template_id"] == "ATT-FMWK003-001"

    def test_resolve_by_tier(self, plane_root):
        make_template(
            plane_root, "ATT-HO2-001",
            applies_to={"tier": ["ho2"]},
            pipeline=[{"stage": "structuring", "type": "structuring", "config": {}}],
        )
        svc = AttentionService(plane_root)
        req = make_request(tier="ho2")
        tpl = svc.resolve_template(req)
        assert tpl["template_id"] == "ATT-HO2-001"

    def test_specificity_order(self, plane_root):
        """framework_id wins over agent_class wins over tier."""
        make_template(
            plane_root, "ATT-TIER-001",
            applies_to={"tier": ["hot"]},
            pipeline=[{"stage": "structuring", "type": "structuring", "config": {}}],
        )
        make_template(
            plane_root, "ATT-CLASS-001",
            applies_to={"agent_class": ["KERNEL.syntactic"]},
            pipeline=[{"stage": "structuring", "type": "structuring", "config": {}}],
        )
        make_template(
            plane_root, "ATT-FMWK-001",
            applies_to={"framework_id": ["FMWK-000"]},
            pipeline=[{"stage": "structuring", "type": "structuring", "config": {}}],
        )
        svc = AttentionService(plane_root)
        req = make_request(
            agent_class="KERNEL.syntactic",
            framework_id="FMWK-000",
            tier="hot",
        )
        tpl = svc.resolve_template(req)
        assert tpl["template_id"] == "ATT-FMWK-001"

    def test_no_match_uses_default(self, plane_root):
        """No matching template -> minimal default with warning."""
        svc = AttentionService(plane_root)
        req = make_request(agent_class="ADMIN", framework_id="FMWK-999", tier="ho1")
        tpl = svc.resolve_template(req)
        # Default template has a pipeline (at minimum empty or file_read-only)
        assert tpl["template_id"] == "__default__"

    def test_multiple_matches_fail_closed(self, plane_root):
        """Ambiguous match at same specificity -> error."""
        make_template(
            plane_root, "ATT-A-001",
            applies_to={"agent_class": ["KERNEL.syntactic"]},
            pipeline=[{"stage": "structuring", "type": "structuring", "config": {}}],
        )
        make_template(
            plane_root, "ATT-B-001",
            applies_to={"agent_class": ["KERNEL.syntactic"]},
            pipeline=[{"stage": "structuring", "type": "structuring", "config": {}}],
        )
        svc = AttentionService(plane_root)
        req = make_request(agent_class="KERNEL.syntactic")
        with pytest.raises(ValueError, match="[Aa]mbiguous"):
            svc.resolve_template(req)

    def test_template_override(self, plane_root):
        """Explicit template_id bypasses matching."""
        make_template(
            plane_root, "ATT-OVERRIDE-001",
            applies_to={"tier": ["ho1"]},
            pipeline=[{"stage": "structuring", "type": "structuring", "config": {}}],
        )
        svc = AttentionService(plane_root)
        req = make_request(template_override="ATT-OVERRIDE-001")
        tpl = svc.resolve_template(req)
        assert tpl["template_id"] == "ATT-OVERRIDE-001"


# ---------------------------------------------------------------------------
# Group 2: Required Context Merge (4 tests)
# ---------------------------------------------------------------------------

class TestRequiredContextMerge:
    """Test AttentionService._merge_required_context()."""

    def test_merge_ledger_queries(self, plane_root):
        """Prompt contract's ledger queries added to pipeline."""
        svc = AttentionService(plane_root)
        pipeline = [
            {"stage": "structuring", "type": "structuring", "config": {}},
        ]
        required_context = {
            "ledger_queries": [
                {"event_type": "PROMPT_RECEIVED", "max_entries": 5}
            ]
        }
        merged = svc._merge_required_context(pipeline, required_context)
        types = [s["type"] for s in merged]
        assert "ledger_query" in types
        # The ledger_query should appear before structuring
        lq_idx = next(i for i, s in enumerate(merged) if s["type"] == "ledger_query")
        st_idx = next(i for i, s in enumerate(merged) if s["type"] == "structuring")
        assert lq_idx < st_idx

    def test_merge_framework_refs(self, plane_root):
        """framework_refs become registry_query stages."""
        svc = AttentionService(plane_root)
        pipeline = [
            {"stage": "structuring", "type": "structuring", "config": {}},
        ]
        required_context = {
            "framework_refs": ["FMWK-003"]
        }
        merged = svc._merge_required_context(pipeline, required_context)
        types = [s["type"] for s in merged]
        assert "registry_query" in types

    def test_merge_file_refs(self, plane_root):
        """file_refs become file_read stages."""
        svc = AttentionService(plane_root)
        pipeline = [
            {"stage": "structuring", "type": "structuring", "config": {}},
        ]
        required_context = {
            "file_refs": ["HOT/schemas/work_order.schema.json"]
        }
        merged = svc._merge_required_context(pipeline, required_context)
        types = [s["type"] for s in merged]
        assert "file_read" in types

    def test_template_stages_take_priority(self, plane_root):
        """Existing pipeline stages not duplicated by merge."""
        svc = AttentionService(plane_root)
        pipeline = [
            {"stage": "existing_ledger", "type": "ledger_query", "config": {"event_type": "INSTALLED"}},
            {"stage": "structuring", "type": "structuring", "config": {}},
        ]
        required_context = {
            "ledger_queries": [
                {"event_type": "INSTALLED", "max_entries": 5}
            ]
        }
        merged = svc._merge_required_context(pipeline, required_context)
        ledger_stages = [s for s in merged if s["type"] == "ledger_query"]
        # Should still only have the original ledger_query, not a duplicate
        assert len(ledger_stages) == 1


# ---------------------------------------------------------------------------
# Group 3: Pipeline Execution (12 tests)
# ---------------------------------------------------------------------------

class TestPipelineExecution:
    """Test individual stages and pipeline runner."""

    def _make_state(self, budget_tracker=None):
        return PipelineState(
            tier_scope=["hot"],
            fragments=[],
            budget_tracker=budget_tracker or BudgetTracker(max_tokens=10000, max_queries=50, timeout_ms=30000),
            warnings=[],
        )

    def test_stages_run_in_order(self, plane_root):
        """Stages execute sequentially as defined."""
        mock_provider = MockContextProvider(
            ledger_entries=[{"event_type": "INSTALLED", "package_id": "PKG-TEST"}],
            files={"HOT/test.txt": "hello"},
        )
        svc = AttentionService(plane_root)
        svc.context_provider = mock_provider
        make_template(
            plane_root, "ATT-ORDER-001",
            applies_to={"agent_class": ["KERNEL.syntactic"]},
            pipeline=[
                {"stage": "select_tiers", "type": "tier_select", "config": {"tiers": ["hot"]}},
                {"stage": "query_ledger", "type": "ledger_query", "config": {"event_type": "INSTALLED", "max_entries": 5}},
                {"stage": "read_files", "type": "file_read", "config": {"paths": ["HOT/test.txt"]}},
                {"stage": "structure", "type": "structuring", "config": {"strategy": "chronological", "max_tokens": 8000}},
                {"stage": "halt", "type": "halting", "config": {"min_fragments": 1}},
            ],
            budget={"max_context_tokens": 10000, "max_queries": 50, "timeout_ms": 30000},
        )
        req = make_request(agent_class="KERNEL.syntactic")
        result = svc.assemble(req)
        trace_stages = [sr.stage for sr in result.pipeline_trace]
        assert trace_stages == ["select_tiers", "query_ledger", "read_files", "structure", "halt"]

    def test_disabled_stage_skipped(self, plane_root):
        """enabled:false stages are skipped."""
        mock_provider = MockContextProvider()
        svc = AttentionService(plane_root)
        svc.context_provider = mock_provider
        make_template(
            plane_root, "ATT-SKIP-001",
            applies_to={"agent_class": ["KERNEL.syntactic"]},
            pipeline=[
                {"stage": "disabled_stage", "type": "ledger_query", "config": {}, "enabled": False},
                {"stage": "structure", "type": "structuring", "config": {"strategy": "chronological", "max_tokens": 8000}},
            ],
            budget={"max_context_tokens": 10000, "max_queries": 50, "timeout_ms": 30000},
        )
        req = make_request(agent_class="KERNEL.syntactic")
        result = svc.assemble(req)
        statuses = {sr.stage: sr.status for sr in result.pipeline_trace}
        assert statuses["disabled_stage"] == "skipped"

    def test_ledger_query_produces_fragments(self, plane_root):
        """ledger_query returns ContextFragments."""
        provider = MockContextProvider(
            ledger_entries=[
                {"event_type": "INSTALLED", "package_id": "PKG-A"},
                {"event_type": "INSTALLED", "package_id": "PKG-B"},
            ]
        )
        state = self._make_state()
        config = {"event_type": "INSTALLED", "max_entries": 10}
        output = run_ledger_query(config, provider, state)
        assert output.status == "ok"
        assert len(output.fragments) == 2
        assert all(f.source == "ledger" for f in output.fragments)

    def test_registry_query_produces_fragments(self, plane_root):
        """registry_query returns ContextFragments."""
        provider = MockContextProvider(
            registries={
                "frameworks": [
                    {"framework_id": "FMWK-000", "title": "Governance"},
                ]
            }
        )
        state = self._make_state()
        config = {"registry": "frameworks", "filters": {"framework_id": "FMWK-000"}}
        output = run_registry_query(config, provider, state)
        assert output.status == "ok"
        assert len(output.fragments) == 1
        assert output.fragments[0].source == "registry"

    def test_file_read_produces_fragments(self, plane_root):
        """file_read returns file content as fragment."""
        provider = MockContextProvider(
            files={"HOT/schemas/test.json": '{"key": "value"}'}
        )
        state = self._make_state()
        config = {"paths": ["HOT/schemas/test.json"]}
        output = run_file_read(config, provider, state)
        assert output.status == "ok"
        assert len(output.fragments) == 1
        assert output.fragments[0].source == "file"
        assert "value" in output.fragments[0].content

    def test_file_not_found_warns(self, plane_root):
        """Missing file -> warning, not error."""
        provider = MockContextProvider(files={})
        state = self._make_state()
        config = {"paths": ["HOT/nonexistent.txt"]}
        output = run_file_read(config, provider, state)
        assert output.status == "ok"
        assert len(output.fragments) == 0
        assert len(state.warnings) > 0
        assert "nonexistent" in state.warnings[0].lower() or "not found" in state.warnings[0].lower()

    def test_horizontal_search_scores_fragments(self, plane_root):
        """Search results have relevance_score."""
        provider = MockContextProvider(
            ledger_entries=[
                {"event_type": "INSTALLED", "package_id": "PKG-KERNEL"},
                {"event_type": "REMOVED", "package_id": "PKG-OLD"},
            ],
            files={"HOT/kernel/paths.py": "def get_control_plane_root(): pass"},
        )
        state = self._make_state()
        config = {
            "query": "kernel control plane",
            "sources": ["ledger", "files"],
            "tiers": ["hot"],
            "max_results": 10,
            "relevance_threshold": 0.1,
        }
        output = run_horizontal_search(config, provider, state)
        assert output.status == "ok"
        assert len(output.fragments) > 0
        assert all(f.relevance_score is not None for f in output.fragments)

    def test_structuring_deduplicates(self, plane_root):
        """Overlapping content deduplicated."""
        state = self._make_state()
        state.fragments = [
            ContextFragment(source="ledger", source_id="e1", content="same content", token_estimate=10, relevance_score=0.9),
            ContextFragment(source="ledger", source_id="e2", content="same content", token_estimate=10, relevance_score=0.8),
            ContextFragment(source="file", source_id="f1", content="different content", token_estimate=10, relevance_score=0.7),
        ]
        provider = MockContextProvider()
        config = {"strategy": "relevance", "max_tokens": 8000}
        output = run_structuring(config, provider, state)
        # Two unique content pieces
        assert len(output.fragments) == 2

    def test_structuring_truncates_to_budget(self, plane_root):
        """Lowest-relevance fragments dropped when over max_tokens."""
        state = self._make_state()
        state.fragments = [
            ContextFragment(source="ledger", source_id="e1", content="A" * 400, token_estimate=100, relevance_score=0.9),
            ContextFragment(source="ledger", source_id="e2", content="B" * 400, token_estimate=100, relevance_score=0.5),
            ContextFragment(source="file", source_id="f1", content="C" * 400, token_estimate=100, relevance_score=0.1),
        ]
        provider = MockContextProvider()
        config = {"strategy": "relevance", "max_tokens": 200}
        output = run_structuring(config, provider, state)
        # Only highest-relevance fragments should remain
        total_tokens = sum(f.token_estimate for f in output.fragments)
        assert total_tokens <= 200
        # The highest-relevance fragment should be included
        assert any(f.source_id == "e1" for f in output.fragments)

    def test_halting_satisfied(self, plane_root):
        """Sufficient context -> pipeline stops cleanly."""
        state = self._make_state()
        state.fragments = [
            ContextFragment(source="ledger", source_id="e1", content="data " * 50, token_estimate=50, relevance_score=0.9),
        ]
        provider = MockContextProvider()
        config = {"min_fragments": 1, "min_tokens": 10}
        output = run_halting(config, provider, state)
        assert output.status == "ok"

    def test_halting_insufficient_reruns(self, plane_root):
        """Not enough context + budget remaining -> retry."""
        state = self._make_state()
        state.fragments = []  # No fragments at all
        provider = MockContextProvider()
        config = {"min_fragments": 3, "min_tokens": 100}
        output = run_halting(config, provider, state)
        assert output.status == "retry"

    def test_custom_stage_calls_handler(self, plane_root):
        """Custom stage invokes registered function."""
        called = {"count": 0}

        def my_handler(config, provider, state):
            called["count"] += 1
            return StageOutput(
                fragments=[ContextFragment(source="custom", source_id="handler", content="custom data", token_estimate=5, relevance_score=None)],
                status="ok",
            )

        provider = MockContextProvider()
        state = self._make_state()
        config = {"handler": "test_handler"}
        # Patch the handler registry
        with patch.dict("kernel.attention_stages._CUSTOM_HANDLERS", {"test_handler": my_handler}):
            output = run_custom(config, provider, state)
        assert called["count"] == 1
        assert len(output.fragments) == 1
        assert output.fragments[0].source == "custom"


# ---------------------------------------------------------------------------
# Group 4: Budget Enforcement (8 tests)
# ---------------------------------------------------------------------------

class TestBudgetEnforcement:
    """Test BudgetTracker and pipeline interruption."""

    def test_budget_max_tokens_stops_pipeline(self, plane_root):
        """Exceeding token budget stops execution — later stages are skipped."""
        mock_provider = MockContextProvider(
            ledger_entries=[{"event_type": "INSTALLED", "package_id": f"PKG-{i}"} for i in range(100)],
        )
        svc = AttentionService(plane_root)
        svc.context_provider = mock_provider
        make_template(
            plane_root, "ATT-BUDGET-001",
            applies_to={"agent_class": ["KERNEL.syntactic"]},
            pipeline=[
                {"stage": "query", "type": "ledger_query", "config": {"event_type": "INSTALLED", "max_entries": 100}},
                {"stage": "structure", "type": "structuring", "config": {"strategy": "chronological", "max_tokens": 5}},
                {"stage": "halt", "type": "halting", "config": {"min_fragments": 1}},
            ],
            budget={"max_context_tokens": 5, "max_queries": 50, "timeout_ms": 30000},
            fallback={"on_timeout": "return_partial"},
        )
        req = make_request(agent_class="KERNEL.syntactic")
        result = svc.assemble(req)
        # Budget exceeded after ledger_query → structuring and halting never ran
        trace_stages = [sr.stage for sr in result.pipeline_trace]
        assert "query" in trace_stages
        assert "structure" not in trace_stages  # Stopped before this
        assert any("budget" in w.lower() or "exceeded" in w.lower() for w in result.warnings)

    def test_budget_max_queries_stops_pipeline(self, plane_root):
        """Exceeding query budget stops execution."""
        bt = BudgetTracker(max_tokens=10000, max_queries=1, timeout_ms=30000)
        bt.add_query()
        exceeded, which = bt.check()
        assert not exceeded  # At limit, not over

        bt.add_query()
        exceeded, which = bt.check()
        assert exceeded
        assert "queries" in which

    def test_budget_timeout_stops_pipeline(self, plane_root):
        """Exceeding time budget stops execution."""
        bt = BudgetTracker(max_tokens=10000, max_queries=50, timeout_ms=1)
        time.sleep(0.01)  # 10ms > 1ms timeout
        exceeded, which = bt.check()
        assert exceeded
        assert "timeout" in which

    def test_fallback_return_partial(self, plane_root):
        """on_timeout:'return_partial' returns what we have."""
        mock_provider = MockContextProvider(
            ledger_entries=[{"event_type": "INSTALLED", "package_id": "PKG-A"}],
        )
        svc = AttentionService(plane_root)
        svc.context_provider = mock_provider
        make_template(
            plane_root, "ATT-PARTIAL-001",
            applies_to={"agent_class": ["KERNEL.syntactic"]},
            pipeline=[
                {"stage": "query", "type": "ledger_query", "config": {"event_type": "INSTALLED", "max_entries": 5}},
                {"stage": "structure", "type": "structuring", "config": {"strategy": "chronological", "max_tokens": 8000}},
            ],
            budget={"max_context_tokens": 10000, "max_queries": 50, "timeout_ms": 30000},
            fallback={"on_timeout": "return_partial"},
        )
        req = make_request(agent_class="KERNEL.syntactic")
        result = svc.assemble(req)
        # Should have something (not an error)
        assert isinstance(result, AssembledContext)

    def test_fallback_fail(self, plane_root):
        """on_timeout:'fail' returns error."""
        mock_provider = MockContextProvider(
            ledger_entries=[{"event_type": "INSTALLED", "package_id": f"PKG-{i}"} for i in range(100)],
        )
        svc = AttentionService(plane_root)
        svc.context_provider = mock_provider
        make_template(
            plane_root, "ATT-FAIL-001",
            applies_to={"agent_class": ["ADMIN"]},
            pipeline=[
                {"stage": "query", "type": "ledger_query", "config": {"event_type": "INSTALLED", "max_entries": 100}},
                {"stage": "structure", "type": "structuring", "config": {"strategy": "chronological", "max_tokens": 8000}},
            ],
            budget={"max_context_tokens": 1, "max_queries": 50, "timeout_ms": 30000},
            fallback={"on_timeout": "fail"},
        )
        req = make_request(agent_class="ADMIN")
        with pytest.raises(RuntimeError, match="[Bb]udget"):
            svc.assemble(req)

    def test_fallback_use_cached(self, plane_root):
        """on_timeout:'use_cached' returns cached context."""
        mock_provider = MockContextProvider(
            ledger_entries=[{"event_type": "INSTALLED", "package_id": "PKG-A"}],
        )
        svc = AttentionService(plane_root)
        svc.context_provider = mock_provider
        make_template(
            plane_root, "ATT-CACHED-001",
            applies_to={"agent_class": ["RESIDENT"]},
            pipeline=[
                {"stage": "query", "type": "ledger_query", "config": {"event_type": "INSTALLED", "max_entries": 5}},
                {"stage": "structure", "type": "structuring", "config": {"strategy": "chronological", "max_tokens": 8000}},
            ],
            budget={"max_context_tokens": 10000, "max_queries": 50, "timeout_ms": 30000},
            fallback={"on_timeout": "use_cached"},
        )
        req = make_request(agent_class="RESIDENT")
        # First call populates cache
        result1 = svc.assemble(req)
        assert isinstance(result1, AssembledContext)
        # Verify cache has entry
        cache_key = svc.cache._make_key(req)
        assert svc.cache.get(cache_key) is not None

    def test_fallback_on_empty_proceed(self, plane_root):
        """No context + on_empty:'proceed_empty' returns empty context."""
        mock_provider = MockContextProvider()
        svc = AttentionService(plane_root)
        svc.context_provider = mock_provider
        make_template(
            plane_root, "ATT-EMPTY-001",
            applies_to={"agent_class": ["KERNEL.semantic"]},
            pipeline=[
                {"stage": "query", "type": "ledger_query", "config": {"event_type": "NONEXISTENT"}},
                {"stage": "structure", "type": "structuring", "config": {"strategy": "chronological", "max_tokens": 8000}},
            ],
            budget={"max_context_tokens": 10000, "max_queries": 50, "timeout_ms": 30000},
            fallback={"on_empty": "proceed_empty"},
        )
        req = make_request(agent_class="KERNEL.semantic")
        result = svc.assemble(req)
        assert isinstance(result, AssembledContext)
        assert result.context_text == "" or len(result.fragments) == 0

    def test_fallback_on_empty_fail(self, plane_root):
        """No context + on_empty:'fail' returns error."""
        mock_provider = MockContextProvider()
        svc = AttentionService(plane_root)
        svc.context_provider = mock_provider
        make_template(
            plane_root, "ATT-EMPTYFAIL-001",
            applies_to={"tier": ["ho1"]},
            pipeline=[
                {"stage": "query", "type": "ledger_query", "config": {"event_type": "NONEXISTENT"}},
                {"stage": "structure", "type": "structuring", "config": {"strategy": "chronological", "max_tokens": 8000}},
            ],
            budget={"max_context_tokens": 10000, "max_queries": 50, "timeout_ms": 30000},
            fallback={"on_empty": "fail"},
        )
        req = make_request(tier="ho1")
        with pytest.raises(RuntimeError, match="[Ee]mpty|[Nn]o context"):
            svc.assemble(req)


# ---------------------------------------------------------------------------
# Group 5: Output (4 tests)
# ---------------------------------------------------------------------------

class TestOutput:
    """Test AssembledContext output structure."""

    def _assemble_with_data(self, plane_root):
        mock_provider = MockContextProvider(
            ledger_entries=[{"event_type": "INSTALLED", "package_id": "PKG-A"}],
            files={"HOT/test.txt": "test content"},
        )
        svc = AttentionService(plane_root)
        svc.context_provider = mock_provider
        make_template(
            plane_root, "ATT-OUTPUT-001",
            applies_to={"agent_class": ["KERNEL.syntactic"]},
            pipeline=[
                {"stage": "query", "type": "ledger_query", "config": {"event_type": "INSTALLED", "max_entries": 5}},
                {"stage": "read", "type": "file_read", "config": {"paths": ["HOT/test.txt"]}},
                {"stage": "structure", "type": "structuring", "config": {"strategy": "chronological", "max_tokens": 8000}},
                {"stage": "halt", "type": "halting", "config": {"min_fragments": 1}},
            ],
            budget={"max_context_tokens": 10000, "max_queries": 50, "timeout_ms": 30000},
        )
        req = make_request(agent_class="KERNEL.syntactic")
        return svc.assemble(req)

    def test_context_hash_computed(self, plane_root):
        """SHA256 of context_text in output."""
        result = self._assemble_with_data(plane_root)
        expected_hash = hashlib.sha256(result.context_text.encode()).hexdigest()
        assert result.context_hash == expected_hash

    def test_pipeline_trace_recorded(self, plane_root):
        """Every stage produces StageResult."""
        result = self._assemble_with_data(plane_root)
        assert len(result.pipeline_trace) == 4
        for sr in result.pipeline_trace:
            assert isinstance(sr, StageResult)
            assert sr.stage != ""
            assert sr.type != ""

    def test_budget_used_reported(self, plane_root):
        """Output includes actual budget consumption."""
        result = self._assemble_with_data(plane_root)
        assert isinstance(result.budget_used, BudgetUsed)
        assert result.budget_used.tokens_assembled >= 0
        assert result.budget_used.queries_executed >= 0
        assert result.budget_used.elapsed_ms >= 0

    def test_warnings_collected(self, plane_root):
        """All warnings from all stages in output."""
        mock_provider = MockContextProvider(files={})
        svc = AttentionService(plane_root)
        svc.context_provider = mock_provider
        make_template(
            plane_root, "ATT-WARN-001",
            applies_to={"agent_class": ["ADMIN"]},
            pipeline=[
                {"stage": "read", "type": "file_read", "config": {"paths": ["HOT/missing.txt"]}},
                {"stage": "structure", "type": "structuring", "config": {"strategy": "chronological", "max_tokens": 8000}},
            ],
            budget={"max_context_tokens": 10000, "max_queries": 50, "timeout_ms": 30000},
        )
        req = make_request(agent_class="ADMIN")
        result = svc.assemble(req)
        assert len(result.warnings) > 0


# ---------------------------------------------------------------------------
# Group 6: Caching (3 tests)
# ---------------------------------------------------------------------------

class TestCaching:
    """Test ContextCache class."""

    def test_cache_hit_returns_cached(self, plane_root):
        """Same key within TTL returns cached."""
        cache = ContextCache(default_ttl_seconds=60)
        key = ("ATT-TEST", "KERNEL.syntactic", "WO-001", "S-001")
        ctx = AssembledContext(
            context_text="cached",
            context_hash="abc",
            fragments=[],
            template_id="ATT-TEST",
            pipeline_trace=[],
            budget_used=BudgetUsed(tokens_assembled=10, queries_executed=1, elapsed_ms=5),
            warnings=[],
        )
        cache.put(key, ctx)
        result = cache.get(key)
        assert result is not None
        assert result.context_text == "cached"

    def test_cache_miss_runs_pipeline(self, plane_root):
        """Different key returns None (miss)."""
        cache = ContextCache(default_ttl_seconds=60)
        key1 = ("ATT-TEST", "KERNEL.syntactic", "WO-001", "S-001")
        key2 = ("ATT-OTHER", "ADMIN", "WO-002", "S-002")
        ctx = AssembledContext(
            context_text="cached",
            context_hash="abc",
            fragments=[],
            template_id="ATT-TEST",
            pipeline_trace=[],
            budget_used=BudgetUsed(tokens_assembled=10, queries_executed=1, elapsed_ms=5),
            warnings=[],
        )
        cache.put(key1, ctx)
        result = cache.get(key2)
        assert result is None

    def test_cache_ttl_expires(self, plane_root):
        """Expired entry triggers fresh run."""
        cache = ContextCache(default_ttl_seconds=0)  # 0s TTL = immediate expiry
        key = ("ATT-TEST", "KERNEL.syntactic", "WO-001", "S-001")
        ctx = AssembledContext(
            context_text="cached",
            context_hash="abc",
            fragments=[],
            template_id="ATT-TEST",
            pipeline_trace=[],
            budget_used=BudgetUsed(tokens_assembled=10, queries_executed=1, elapsed_ms=5),
            warnings=[],
        )
        cache.put(key, ctx)
        time.sleep(0.01)  # Ensure time passes
        result = cache.get(key)
        assert result is None


# ---------------------------------------------------------------------------
# Group 7: Token Estimation (2 tests)
# ---------------------------------------------------------------------------

class TestTokenEstimation:
    """Test estimate_tokens() function."""

    def test_estimate_tokens_basic(self):
        """Heuristic returns reasonable estimate."""
        text = "Hello world, this is a test string."
        result = estimate_tokens(text)
        # ~34 chars / 4 = 8 tokens
        assert result == len(text) // 4

    def test_estimate_tokens_configurable(self):
        """chars_per_token from config."""
        text = "Hello world"
        result = estimate_tokens(text, chars_per_token=2)
        assert result == len(text) // 2
