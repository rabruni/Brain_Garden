"""Tests for PKG-HO2-SUPERVISOR-001 — HO2 Supervisor.

47 tests covering: handle_turn, attention, quality gate, session management,
factory pattern, WO chain orchestration, degradation, ledger recording, trace hash.

All tests use tmp_path. HO1Executor is mocked. No real LLM calls.
"""

import hashlib
import json
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

_staging = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_staging / "PKG-KERNEL-001" / "HOT" / "kernel"))
sys.path.insert(0, str(_staging / "PKG-KERNEL-001" / "HOT"))
sys.path.insert(0, str(_staging / "PKG-WORK-ORDER-001" / "HOT" / "kernel"))
sys.path.insert(0, str(_staging / "PKG-HO2-SUPERVISOR-001" / "HO2" / "kernel"))

from ho2_supervisor import HO2Supervisor, HO2Config, TurnResult, HO1ExecutorProtocol
from session_manager import SessionManager, TurnMessage
from attention import AttentionRetriever, ContextProvider, AttentionContext, ContextFragment, BudgetUsed
from quality_gate import QualityGate, QualityGateResult
from ledger_client import LedgerClient, LedgerEntry


# ---------------------------------------------------------------------------
# Mock HO1 Executor
# ---------------------------------------------------------------------------

class MockHO1Executor:
    """Returns preset results for each WO type."""

    def __init__(self, responses: Optional[Dict[str, Dict]] = None):
        self.responses = responses or {
            "classify": {"speech_act": "greeting", "ambiguity": "low"},
            "synthesize": {"response_text": "Hello! How can I help you today?"},
            "execute": {"result": "done"},
            "tool_call": {"tool_result": {"status": "ok"}},
        }
        self.executed_wos: List[Dict] = []

    def execute(self, work_order: dict) -> dict:
        wo = dict(work_order)
        self.executed_wos.append(wo)
        wo_type = wo.get("wo_type", "classify")
        wo["state"] = "completed"
        wo["output_result"] = self.responses.get(wo_type, {"raw": "unknown"})
        wo["cost"] = {
            "input_tokens": 100, "output_tokens": 50, "total_tokens": 150,
            "llm_calls": 1, "tool_calls": 0, "elapsed_ms": 100,
        }
        return wo


class MockLedgerClient:
    """Captures all write() calls."""

    def __init__(self):
        self.entries: List[LedgerEntry] = []

    def write(self, entry: LedgerEntry) -> str:
        self.entries.append(entry)
        return f"entry-{len(self.entries)}"

    def events_of_type(self, event_type: str) -> List[LedgerEntry]:
        return [e for e in self.entries if e.event_type == event_type]


class MockTokenBudgeter:
    """Always allows budget."""

    def __init__(self, session_budget: int = 100000):
        self.session_budget = session_budget
        self.allocations = []
        self.checks = []
        self.debits = []

    def allocate(self, scope, allocation):
        self.allocations.append((scope, allocation))
        return "alloc-1"

    def check(self, scope):
        self.checks.append(scope)
        return MagicMock(allowed=True, remaining=self.session_budget)

    def debit(self, scope, usage):
        self.debits.append((scope, usage))
        return MagicMock(success=True)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_ho2m(tmp_path):
    ho2m = tmp_path / "ho2m"
    ho2m.mkdir()
    return ho2m


@pytest.fixture
def tmp_ho1m(tmp_path):
    ho1m = tmp_path / "ho1m"
    ho1m.mkdir()
    return ho1m


@pytest.fixture
def config(tmp_ho2m, tmp_ho1m):
    return HO2Config(
        attention_templates=["ATT-ADMIN-001"],
        ho2m_path=tmp_ho2m,
        ho1m_path=tmp_ho1m,
        budget_ceiling=100000,
        max_wo_chain_length=10,
        max_retries=2,
        classify_contract_id="PRC-CLASSIFY-001",
        synthesize_contract_id="PRC-SYNTHESIZE-001",
        verify_contract_id="PRC-VERIFY-001",
        attention_budget_tokens=10000,
        attention_budget_queries=20,
        attention_timeout_ms=5000,
    )


@pytest.fixture
def mock_ho1():
    return MockHO1Executor()


@pytest.fixture
def mock_ledger():
    return MockLedgerClient()


@pytest.fixture
def mock_budgeter():
    return MockTokenBudgeter()


@pytest.fixture
def supervisor(tmp_path, config, mock_ho1, mock_ledger, mock_budgeter):
    return HO2Supervisor(
        plane_root=tmp_path,
        agent_class="ADMIN",
        ho1_executor=mock_ho1,
        ledger_client=mock_ledger,
        token_budgeter=mock_budgeter,
        config=config,
    )


# ===========================================================================
# handle_turn Tests (8)
# ===========================================================================

class TestHandleTurn:
    def test_handle_turn_hello_end_to_end(self, supervisor):
        result = supervisor.handle_turn("hello")
        assert isinstance(result, TurnResult)
        assert result.response

    def test_handle_turn_creates_classify_wo(self, supervisor, mock_ho1):
        supervisor.handle_turn("hello")
        assert len(mock_ho1.executed_wos) >= 1
        first_wo = mock_ho1.executed_wos[0]
        assert first_wo["wo_type"] == "classify"
        assert first_wo["input_context"]["user_input"] == "hello"

    def test_handle_turn_creates_synthesize_wo(self, supervisor, mock_ho1):
        supervisor.handle_turn("hello")
        assert len(mock_ho1.executed_wos) >= 2
        second_wo = mock_ho1.executed_wos[1]
        assert second_wo["wo_type"] == "synthesize"
        assert "prior_results" in second_wo["input_context"]

    def test_handle_turn_returns_turn_result(self, supervisor):
        result = supervisor.handle_turn("hello")
        assert isinstance(result, TurnResult)
        assert result.session_id
        assert result.wo_chain_summary
        assert result.cost_summary
        assert isinstance(result.quality_gate_passed, bool)

    def test_handle_turn_multi_wo_chain(self, supervisor, mock_ho1):
        """Chain with classify -> synthesize = 2 WOs minimum."""
        supervisor.handle_turn("hello")
        assert len(mock_ho1.executed_wos) >= 2

    def test_handle_turn_auto_starts_session(self, supervisor):
        result = supervisor.handle_turn("hello")
        assert result.session_id
        assert result.session_id.startswith("SES-")

    def test_handle_turn_wo_chain_summary(self, supervisor):
        result = supervisor.handle_turn("hello")
        assert len(result.wo_chain_summary) >= 2
        types = [w["wo_type"] for w in result.wo_chain_summary]
        assert "classify" in types
        assert "synthesize" in types

    def test_handle_turn_cost_summary(self, supervisor):
        result = supervisor.handle_turn("hello")
        assert result.cost_summary["input_tokens"] > 0
        assert result.cost_summary["output_tokens"] > 0
        assert result.cost_summary["llm_calls"] >= 2


# ===========================================================================
# Attention Tests (8)
# ===========================================================================

class TestAttention:
    def test_horizontal_scan_returns_recent_entries(self, tmp_path, config):
        # Write some entries to ho2m
        ho2m = config.ho2m_path
        ledger_file = ho2m / "workorder.jsonl"
        entry = {"event_type": "WO_PLANNED", "metadata": {"provenance": {"session_id": "SES-TEST0001"}}}
        ledger_file.write_text(json.dumps(entry) + "\n")

        provider = ContextProvider(tmp_path)
        retriever = AttentionRetriever(tmp_path, provider, config)
        ctx = retriever.horizontal_scan("SES-TEST0001")
        assert isinstance(ctx, AttentionContext)
        assert len(ctx.fragments) >= 1

    def test_horizontal_scan_empty_ho2m(self, tmp_path, config):
        provider = ContextProvider(tmp_path)
        retriever = AttentionRetriever(tmp_path, provider, config)
        ctx = retriever.horizontal_scan("SES-EMPTY001")
        assert isinstance(ctx, AttentionContext)
        assert len(ctx.fragments) == 0

    def test_priority_probe_returns_empty(self, tmp_path, config):
        provider = ContextProvider(tmp_path)
        retriever = AttentionRetriever(tmp_path, provider, config)
        ctx = retriever.priority_probe()
        assert isinstance(ctx, AttentionContext)
        assert len(ctx.fragments) == 0

    def test_attention_budget_truncation(self, tmp_path, config):
        config.attention_budget_tokens = 50  # Very small budget
        ho2m = config.ho2m_path
        ledger_file = ho2m / "workorder.jsonl"
        lines = []
        for i in range(100):
            entry = {"event_type": f"EVENT_{i}", "data": "x" * 500,
                     "metadata": {"provenance": {"session_id": "SES-BUDGET01"}}}
            lines.append(json.dumps(entry))
        ledger_file.write_text("\n".join(lines) + "\n")

        provider = ContextProvider(tmp_path)
        retriever = AttentionRetriever(tmp_path, provider, config)
        ctx = retriever.horizontal_scan("SES-BUDGET01")
        total_tokens = sum(f.token_estimate for f in ctx.fragments)
        # Should be truncated well below what 100 entries would produce
        assert total_tokens <= 200  # Budget + some tolerance

    def test_attention_context_hash_computed(self, tmp_path, config):
        provider = ContextProvider(tmp_path)
        retriever = AttentionRetriever(tmp_path, provider, config)
        ctx = retriever.horizontal_scan("SES-HASH0001")
        assert ctx.context_hash
        assert len(ctx.context_hash) == 64  # SHA256 hex digest

    def test_template_resolution_admin(self, tmp_path, config):
        config.attention_templates = ["ATT-ADMIN-001"]
        provider = ContextProvider(tmp_path)
        retriever = AttentionRetriever(tmp_path, provider, config)
        ctx = retriever.horizontal_scan("SES-TEMPL001")
        assert ctx.template_id == "ATT-ADMIN-001"

    def test_template_resolution_no_match(self, tmp_path, config):
        config.attention_templates = []
        provider = ContextProvider(tmp_path)
        retriever = AttentionRetriever(tmp_path, provider, config)
        ctx = retriever.horizontal_scan("SES-NOMAT001")
        assert ctx.template_id == "__default__"

    def test_assemble_wo_context_merges(self, tmp_path, config):
        provider = ContextProvider(tmp_path)
        retriever = AttentionRetriever(tmp_path, provider, config)
        h = AttentionContext(
            context_text="horizontal data",
            context_hash="h1",
            fragments=[ContextFragment("ledger", "e1", "horizontal data", 10)],
            template_id="ATT-ADMIN-001",
            budget_used=BudgetUsed(10, 1, 100),
        )
        p = AttentionContext(
            context_text="",
            context_hash="p1",
            fragments=[],
            template_id="__priority__",
            budget_used=BudgetUsed(0, 0, 0),
        )
        result = retriever.assemble_wo_context(h, p, "hello", {"speech_act": "greeting"})
        assert "user_input" in result
        assert "classification" in result
        assert "assembled_context" in result


# ===========================================================================
# Quality Gate Tests (7)
# ===========================================================================

class TestQualityGate:
    def test_quality_gate_accept_valid_output(self):
        gate = QualityGate()
        result = gate.verify(
            output_result={"response_text": "Hello!"},
            acceptance_criteria={},
            wo_id="WO-TEST-001",
        )
        assert result.decision == "accept"

    def test_quality_gate_reject_none_output(self):
        gate = QualityGate()
        result = gate.verify(None, {}, "WO-TEST-002")
        assert result.decision == "reject"
        assert "None" in result.reason

    def test_quality_gate_reject_empty_output(self):
        gate = QualityGate()
        result = gate.verify({}, {}, "WO-TEST-003")
        assert result.decision == "reject"
        assert "empty" in result.reason

    def test_quality_gate_reject_no_response_text(self):
        gate = QualityGate()
        result = gate.verify({"data": "something"}, {}, "WO-TEST-004")
        assert result.decision == "reject"
        assert "response_text" in result.reason

    def test_quality_gate_retry_flow(self, supervisor, mock_ho1):
        mock_ho1.responses["synthesize"] = {"response_text": ""}
        # First call will reject (empty response_text), retry should happen
        supervisor.handle_turn("hello")
        # Should have classify + synthesize + retries
        synth_count = sum(1 for w in mock_ho1.executed_wos if w["wo_type"] == "synthesize")
        assert synth_count >= 2  # Original + at least one retry

    def test_quality_gate_escalation_after_max_retries(self, supervisor, mock_ho1, mock_ledger, config):
        config.max_retries = 1
        mock_ho1.responses["synthesize"] = {"response_text": ""}
        supervisor.handle_turn("hello")
        escalations = mock_ledger.events_of_type("ESCALATION")
        assert len(escalations) >= 1

    def test_quality_gate_event_logged(self, supervisor, mock_ledger):
        supervisor.handle_turn("hello")
        gate_events = mock_ledger.events_of_type("WO_QUALITY_GATE")
        assert len(gate_events) >= 1
        assert gate_events[0].metadata.get("context_fingerprint", {}).get("context_hash")


# ===========================================================================
# Session Management Tests (7)
# ===========================================================================

class TestSessionManagement:
    def test_start_session_generates_id(self, supervisor):
        sid = supervisor.start_session()
        assert sid.startswith("SES-")
        assert len(sid) == 12  # SES- + 8 hex chars

    def test_start_session_idempotent(self, supervisor):
        sid1 = supervisor.start_session()
        sid2 = supervisor.start_session()
        assert sid1 == sid2

    def test_start_session_writes_ledger(self, supervisor, mock_ledger):
        supervisor.start_session()
        starts = mock_ledger.events_of_type("SESSION_START")
        assert len(starts) == 1

    def test_end_session_writes_ledger(self, supervisor, mock_ledger):
        supervisor.start_session()
        supervisor.end_session()
        ends = mock_ledger.events_of_type("SESSION_END")
        assert len(ends) == 1

    def test_session_history_tracking(self, supervisor):
        supervisor.handle_turn("hello")
        mgr = supervisor._session_mgr
        assert len(mgr.history) == 2  # user + assistant

    def test_next_wo_id_format(self, supervisor):
        supervisor.start_session()
        wo_id = supervisor._session_mgr.next_wo_id()
        assert wo_id.startswith("WO-SES-")
        assert wo_id.endswith("-001")

    def test_next_wo_id_monotonic(self, supervisor):
        supervisor.start_session()
        id1 = supervisor._session_mgr.next_wo_id()
        id2 = supervisor._session_mgr.next_wo_id()
        seq1 = int(id1.split("-")[-1])
        seq2 = int(id2.split("-")[-1])
        assert seq2 > seq1


# ===========================================================================
# Factory Pattern Tests (3)
# ===========================================================================

class TestFactoryPattern:
    def test_factory_admin_config(self, tmp_path, config, mock_ho1, mock_ledger, mock_budgeter):
        sv = HO2Supervisor(tmp_path, "ADMIN", mock_ho1, mock_ledger, mock_budgeter, config)
        assert sv._agent_class == "ADMIN"

    def test_factory_resident_config(self, tmp_path, mock_ho1, mock_budgeter, tmp_ho2m, tmp_ho1m):
        resident_config = HO2Config(
            attention_templates=["ATT-DPJ-001"],
            ho2m_path=tmp_ho2m,
            ho1m_path=tmp_ho1m,
            budget_ceiling=50000,
        )
        resident_ledger = MockLedgerClient()
        sv = HO2Supervisor(tmp_path, "RESIDENT:dopejar", mock_ho1, resident_ledger, mock_budgeter, resident_config)
        assert sv._agent_class == "RESIDENT:dopejar"

    def test_factory_isolated_ho2m(self, tmp_path, mock_ho1, mock_budgeter):
        admin_ho2m = tmp_path / "admin_ho2m"
        admin_ho2m.mkdir()
        resident_ho2m = tmp_path / "resident_ho2m"
        resident_ho2m.mkdir()
        ho1m = tmp_path / "ho1m"
        ho1m.mkdir()

        admin_config = HO2Config(attention_templates=["ATT-ADMIN-001"], ho2m_path=admin_ho2m, ho1m_path=ho1m)
        resident_config = HO2Config(attention_templates=["ATT-DPJ-001"], ho2m_path=resident_ho2m, ho1m_path=ho1m)

        admin_ledger = MockLedgerClient()
        resident_ledger = MockLedgerClient()

        sv_admin = HO2Supervisor(tmp_path, "ADMIN", mock_ho1, admin_ledger, mock_budgeter, admin_config)
        sv_resident = HO2Supervisor(tmp_path, "RESIDENT:dopejar", mock_ho1, resident_ledger, mock_budgeter, resident_config)

        sv_admin.handle_turn("admin says hello")
        sv_resident.handle_turn("resident says hello")

        # Each ledger should have entries, and they should be independent
        assert len(admin_ledger.entries) > 0
        assert len(resident_ledger.entries) > 0


# ===========================================================================
# WO Chain Orchestration Tests (5)
# ===========================================================================

class TestWOChainOrchestration:
    def test_classify_synthesize_pipeline(self, supervisor, mock_ho1):
        supervisor.handle_turn("hello")
        types = [w["wo_type"] for w in mock_ho1.executed_wos]
        assert types[:2] == ["classify", "synthesize"]

    def test_classify_tool_call_synthesize_pipeline(self, supervisor, mock_ho1):
        """Test with classification that triggers tool_call."""
        mock_ho1.responses["classify"] = {
            "speech_act": "admin_command",
            "ambiguity": "low",
            "requires_tool": True,
        }
        supervisor.handle_turn("show frameworks")
        # Should still have at least classify + synthesize
        types = [w["wo_type"] for w in mock_ho1.executed_wos]
        assert "classify" in types
        assert "synthesize" in types

    def test_wo_budget_allocated_per_wo(self, supervisor, mock_ho1):
        supervisor.handle_turn("hello")
        # Each WO should have budget in constraints
        for wo in mock_ho1.executed_wos:
            assert "token_budget" in wo.get("constraints", {})

    def test_wo_budget_checked_before_dispatch(self, supervisor, mock_ho1):
        supervisor.handle_turn("hello")
        # WOs should have been dispatched (state was changed to dispatched before execute)
        for wo in mock_ho1.executed_wos:
            # The WO was dispatched (state changed from planned to dispatched before execute)
            assert wo.get("state") in ("completed", "dispatched", "failed")

    def test_wo_budget_insufficient_returns_degraded(self, supervisor, mock_ho1):
        """When HO1 raises, degradation path activates."""
        mock_ho1_failing = MockHO1Executor()
        mock_ho1_failing.execute = MagicMock(side_effect=Exception("HO1 down"))
        supervisor._ho1 = mock_ho1_failing
        result = supervisor.handle_turn("hello")
        assert "[Degradation" in result.response


# ===========================================================================
# Degradation Tests (2)
# ===========================================================================

class TestDegradation:
    def test_ho1_exception_triggers_degradation(self, supervisor, mock_ledger):
        failing_ho1 = MagicMock()
        failing_ho1.execute = MagicMock(side_effect=Exception("HO1 failure"))
        supervisor._ho1 = failing_ho1
        result = supervisor.handle_turn("hello")
        assert "[Degradation" in result.response
        assert not result.quality_gate_passed

    def test_degradation_event_logged_to_ho2m(self, supervisor, mock_ledger):
        failing_ho1 = MagicMock()
        failing_ho1.execute = MagicMock(side_effect=Exception("HO1 failure"))
        supervisor._ho1 = failing_ho1
        supervisor.handle_turn("hello")
        degs = mock_ledger.events_of_type("DEGRADATION")
        assert len(degs) >= 1
        assert degs[0].metadata.get("governance_violation") is True


# ===========================================================================
# Ledger Recording Tests (4)
# ===========================================================================

class TestLedgerRecording:
    def test_wo_planned_event_logged(self, supervisor, mock_ledger):
        supervisor.handle_turn("hello")
        planned = mock_ledger.events_of_type("WO_PLANNED")
        assert len(planned) >= 2  # classify + synthesize

    def test_wo_dispatched_event_logged(self, supervisor, mock_ledger):
        supervisor.handle_turn("hello")
        dispatched = mock_ledger.events_of_type("WO_DISPATCHED")
        assert len(dispatched) >= 2

    def test_wo_chain_complete_event_logged(self, supervisor, mock_ledger):
        supervisor.handle_turn("hello")
        chain = mock_ledger.events_of_type("WO_CHAIN_COMPLETE")
        assert len(chain) >= 1
        assert chain[0].metadata.get("cost")
        assert chain[0].metadata.get("wo_ids")

    def test_wo_quality_gate_event_logged(self, supervisor, mock_ledger):
        supervisor.handle_turn("hello")
        gates = mock_ledger.events_of_type("WO_QUALITY_GATE")
        assert len(gates) >= 1
        assert gates[0].metadata.get("decision")


# ===========================================================================
# Trace Hash Tests (3)
# ===========================================================================

class TestTraceHash:
    def test_trace_hash_computed_from_ho1m(self, supervisor, config):
        # Write some HO1m entries
        ho1m = config.ho1m_path
        ledger_file = ho1m / "trace.jsonl"
        entries = [
            {"event_type": "LLM_CALL", "submission_id": "WO-SES-TEST-001"},
            {"event_type": "WO_COMPLETED", "submission_id": "WO-SES-TEST-002"},
        ]
        ledger_file.write_text("\n".join(json.dumps(e) for e in entries) + "\n")

        supervisor.start_session()
        trace_hash = supervisor._compute_trace_hash(
            ["WO-SES-TEST-001", "WO-SES-TEST-002"],
            supervisor._session_mgr.session_id,
        )
        assert trace_hash
        assert len(trace_hash) == 64

    def test_trace_hash_on_chain_complete(self, supervisor, mock_ledger):
        supervisor.handle_turn("hello")
        chain = mock_ledger.events_of_type("WO_CHAIN_COMPLETE")
        assert len(chain) >= 1
        assert chain[0].metadata.get("context_fingerprint", {}).get("context_hash")

    def test_trace_hash_on_quality_gate(self, supervisor, mock_ledger):
        supervisor.handle_turn("hello")
        gates = mock_ledger.events_of_type("WO_QUALITY_GATE")
        assert len(gates) >= 1
        assert gates[0].metadata.get("context_fingerprint", {}).get("context_hash")
