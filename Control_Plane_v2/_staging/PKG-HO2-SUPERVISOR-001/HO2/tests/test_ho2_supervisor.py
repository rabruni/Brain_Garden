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

    def test_add_turn_writes_turn_recorded_event(self, supervisor, mock_ledger):
        supervisor.start_session()
        supervisor._session_mgr.add_turn("hello", "hi")
        turns = mock_ledger.events_of_type("TURN_RECORDED")
        assert len(turns) == 1

    def test_turn_recorded_contains_user_message(self, supervisor, mock_ledger):
        supervisor.start_session()
        supervisor._session_mgr.add_turn("what frameworks are installed?", "Installed packages are ...")
        turn = mock_ledger.events_of_type("TURN_RECORDED")[0]
        assert turn.metadata["user_message"] == "what frameworks are installed?"

    def test_turn_recorded_contains_response(self, supervisor, mock_ledger):
        supervisor.start_session()
        supervisor._session_mgr.add_turn("hello", "Hello! How can I assist?")
        turn = mock_ledger.events_of_type("TURN_RECORDED")[0]
        assert turn.metadata["response"] == "Hello! How can I assist?"

    def test_turn_recorded_has_turn_number(self, supervisor, mock_ledger):
        supervisor.start_session()
        supervisor._session_mgr.add_turn("first", "one")
        supervisor._session_mgr.add_turn("second", "two")
        turns = mock_ledger.events_of_type("TURN_RECORDED")
        assert turns[-1].metadata["turn_number"] == 2

    def test_turn_recorded_has_session_id(self, supervisor, mock_ledger):
        session_id = supervisor.start_session()
        supervisor._session_mgr.add_turn("hello", "hi")
        turn = mock_ledger.events_of_type("TURN_RECORDED")[0]
        assert turn.submission_id == session_id


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


# ===========================================================================
# Tool-Use Wiring Tests (7) — HANDOFF-21
# ===========================================================================

class TestToolUseWiring:
    def test_ho2_config_tools_allowed_default_empty(self, tmp_ho2m, tmp_ho1m):
        config = HO2Config(
            attention_templates=["ATT-ADMIN-001"],
            ho2m_path=tmp_ho2m,
            ho1m_path=tmp_ho1m,
        )
        assert config.tools_allowed == []

    def test_ho2_config_tools_allowed_set(self, tmp_ho2m, tmp_ho1m):
        config = HO2Config(
            attention_templates=["ATT-ADMIN-001"],
            ho2m_path=tmp_ho2m,
            ho1m_path=tmp_ho1m,
            tools_allowed=["gate_check", "list_packages"],
        )
        assert config.tools_allowed == ["gate_check", "list_packages"]

    def test_synthesize_wo_includes_tools_allowed(self, tmp_path, mock_ho1, mock_ledger, mock_budgeter, tmp_ho2m, tmp_ho1m):
        config = HO2Config(
            attention_templates=["ATT-ADMIN-001"],
            ho2m_path=tmp_ho2m,
            ho1m_path=tmp_ho1m,
            tools_allowed=["gate_check"],
        )
        sv = HO2Supervisor(tmp_path, "ADMIN", mock_ho1, mock_ledger, mock_budgeter, config)
        sv.handle_turn("hello")
        synth_wos = [w for w in mock_ho1.executed_wos if w["wo_type"] == "synthesize"]
        assert len(synth_wos) >= 1
        assert synth_wos[0]["constraints"]["tools_allowed"] == ["gate_check"]

    def test_synthesize_wo_turn_limit_raised_with_tools(self, tmp_path, mock_ho1, mock_ledger, mock_budgeter, tmp_ho2m, tmp_ho1m):
        config = HO2Config(
            attention_templates=["ATT-ADMIN-001"],
            ho2m_path=tmp_ho2m,
            ho1m_path=tmp_ho1m,
            tools_allowed=["gate_check"],
        )
        sv = HO2Supervisor(tmp_path, "ADMIN", mock_ho1, mock_ledger, mock_budgeter, config)
        sv.handle_turn("hello")
        synth_wos = [w for w in mock_ho1.executed_wos if w["wo_type"] == "synthesize"]
        assert synth_wos[0]["constraints"]["turn_limit"] == 10

    def test_classify_wo_excludes_tools_allowed(self, tmp_path, mock_ho1, mock_ledger, mock_budgeter, tmp_ho2m, tmp_ho1m):
        config = HO2Config(
            attention_templates=["ATT-ADMIN-001"],
            ho2m_path=tmp_ho2m,
            ho1m_path=tmp_ho1m,
            tools_allowed=["gate_check"],
        )
        sv = HO2Supervisor(tmp_path, "ADMIN", mock_ho1, mock_ledger, mock_budgeter, config)
        sv.handle_turn("hello")
        classify_wos = [w for w in mock_ho1.executed_wos if w["wo_type"] == "classify"]
        assert len(classify_wos) >= 1
        assert "tools_allowed" not in classify_wos[0]["constraints"]

    def test_retry_wo_includes_tools_allowed(self, tmp_path, mock_ledger, mock_budgeter, tmp_ho2m, tmp_ho1m):
        failing_ho1 = MockHO1Executor(responses={
            "classify": {"speech_act": "greeting", "ambiguity": "low"},
            "synthesize": {"response_text": ""},  # triggers retry
        })
        config = HO2Config(
            attention_templates=["ATT-ADMIN-001"],
            ho2m_path=tmp_ho2m,
            ho1m_path=tmp_ho1m,
            tools_allowed=["gate_check"],
            max_retries=1,
        )
        sv = HO2Supervisor(tmp_path, "ADMIN", failing_ho1, mock_ledger, mock_budgeter, config)
        sv.handle_turn("hello")
        synth_wos = [w for w in failing_ho1.executed_wos if w["wo_type"] == "synthesize"]
        # At least 2 synthesize WOs (original + retry)
        assert len(synth_wos) >= 2
        # Retry WO should also have tools_allowed
        assert synth_wos[-1]["constraints"]["tools_allowed"] == ["gate_check"]

    def test_tools_allowed_empty_means_no_tools(self, supervisor, mock_ho1):
        supervisor.handle_turn("hello")
        synth_wos = [w for w in mock_ho1.executed_wos if w["wo_type"] == "synthesize"]
        assert synth_wos[0]["constraints"]["tools_allowed"] == []
        assert synth_wos[0]["constraints"]["turn_limit"] == 1


class TestAdminShellHotfix:
    def test_synthesize_budget_from_config(self, tmp_path, mock_ho1, mock_ledger, mock_budgeter, tmp_ho2m, tmp_ho1m):
        config = HO2Config(
            attention_templates=["ATT-ADMIN-001"],
            ho2m_path=tmp_ho2m,
            ho1m_path=tmp_ho1m,
            synthesize_budget=16000,
        )
        sv = HO2Supervisor(tmp_path, "ADMIN", mock_ho1, mock_ledger, mock_budgeter, config)
        sv.handle_turn("hello")
        synth_wos = [w for w in mock_ho1.executed_wos if w["wo_type"] == "synthesize"]
        assert len(synth_wos) >= 1
        assert synth_wos[0]["constraints"]["token_budget"] == 16000

    def test_retry_budget_from_config(self, tmp_path, mock_ledger, mock_budgeter, tmp_ho2m, tmp_ho1m):
        failing_ho1 = MockHO1Executor(responses={
            "classify": {"speech_act": "greeting", "ambiguity": "low"},
            "synthesize": {"response_text": ""},
        })
        config = HO2Config(
            attention_templates=["ATT-ADMIN-001"],
            ho2m_path=tmp_ho2m,
            ho1m_path=tmp_ho1m,
            max_retries=1,
            synthesize_budget=16000,
        )
        sv = HO2Supervisor(tmp_path, "ADMIN", failing_ho1, mock_ledger, mock_budgeter, config)
        sv.handle_turn("hello")
        synth_wos = [w for w in failing_ho1.executed_wos if w["wo_type"] == "synthesize"]
        assert len(synth_wos) >= 2
        assert synth_wos[0]["constraints"]["token_budget"] == 16000
        assert synth_wos[-1]["constraints"]["token_budget"] == 16000

    def test_wo_error_surfaced_before_quality_gate(self, tmp_path, mock_ledger, mock_budgeter, tmp_ho2m, tmp_ho1m):
        class FailFirstSynthesizeHO1:
            def __init__(self):
                self.executed_wos = []

            def execute(self, work_order: dict) -> dict:
                wo = dict(work_order)
                self.executed_wos.append(wo)
                wo_type = wo.get("wo_type", "classify")
                if wo_type == "classify":
                    wo["state"] = "completed"
                    wo["output_result"] = {"speech_act": "greeting", "ambiguity": "low"}
                else:
                    wo["state"] = "failed"
                    wo["error"] = "budget_exhausted: Token budget exhausted"
                    wo["output_result"] = None
                wo["cost"] = {
                    "input_tokens": 100, "output_tokens": 50, "total_tokens": 150,
                    "llm_calls": 1, "tool_calls": 0, "elapsed_ms": 100,
                }
                return wo

        config = HO2Config(
            attention_templates=["ATT-ADMIN-001"],
            ho2m_path=tmp_ho2m,
            ho1m_path=tmp_ho1m,
            max_retries=0,
        )
        sv = HO2Supervisor(tmp_path, "ADMIN", FailFirstSynthesizeHO1(), mock_ledger, mock_budgeter, config)
        result = sv.handle_turn("what frameworks are installed?")
        assert result.response.startswith("[Error: budget_exhausted:")
        assert "[Quality gate failed:" not in result.response

    def test_retry_failed_wo_error_surfaced_before_quality_gate(self, tmp_path, mock_ledger, mock_budgeter, tmp_ho2m, tmp_ho1m):
        class RetryThenFailHO1:
            def __init__(self):
                self.executed_wos = []
                self._synth_calls = 0

            def execute(self, work_order: dict) -> dict:
                wo = dict(work_order)
                self.executed_wos.append(wo)
                wo_type = wo.get("wo_type", "classify")
                if wo_type == "classify":
                    wo["state"] = "completed"
                    wo["output_result"] = {"speech_act": "greeting", "ambiguity": "low"}
                else:
                    self._synth_calls += 1
                    if self._synth_calls == 1:
                        wo["state"] = "completed"
                        wo["output_result"] = {"response_text": ""}
                    else:
                        wo["state"] = "failed"
                        wo["error"] = "budget_exhausted: Only 300 tokens remain after tool calls"
                        wo["output_result"] = None
                wo["cost"] = {
                    "input_tokens": 100, "output_tokens": 50, "total_tokens": 150,
                    "llm_calls": 1, "tool_calls": 0, "elapsed_ms": 100,
                }
                return wo

        config = HO2Config(
            attention_templates=["ATT-ADMIN-001"],
            ho2m_path=tmp_ho2m,
            ho1m_path=tmp_ho1m,
            max_retries=1,
        )
        sv = HO2Supervisor(tmp_path, "ADMIN", RetryThenFailHO1(), mock_ledger, mock_budgeter, config)
        result = sv.handle_turn("what frameworks are installed?")
        assert result.response.startswith("[Error: budget_exhausted:")
        assert "[Quality gate failed: output_result is empty]" not in result.response


class TestPristineMemoryBudgetModes:
    def test_turn_recorded_on_degradation(self, supervisor, mock_ledger):
        failing_ho1 = MagicMock()
        failing_ho1.execute = MagicMock(side_effect=Exception("boom"))
        supervisor._ho1 = failing_ho1

        result = supervisor.handle_turn("hello")

        assert "[Degradation:" in result.response
        turns = mock_ledger.events_of_type("TURN_RECORDED")
        assert len(turns) == 1
        assert turns[0].metadata["user_message"] == "hello"
        assert "[Degradation:" in turns[0].metadata["response"]

    def test_turn_recorded_on_quality_gate_reject(self, tmp_path, mock_ledger, mock_budgeter, tmp_ho2m, tmp_ho1m):
        class EmptySynthesizeHO1:
            def __init__(self):
                self.executed_wos = []

            def execute(self, work_order: dict) -> dict:
                wo = dict(work_order)
                self.executed_wos.append(wo)
                if wo.get("wo_type") == "classify":
                    wo["state"] = "completed"
                    wo["output_result"] = {"speech_act": "greeting", "ambiguity": "low"}
                else:
                    wo["state"] = "completed"
                    wo["output_result"] = {"response_text": ""}
                wo["cost"] = {
                    "input_tokens": 10, "output_tokens": 10, "total_tokens": 20,
                    "llm_calls": 1, "tool_calls": 0, "elapsed_ms": 1,
                }
                return wo

        config = HO2Config(
            attention_templates=["ATT-ADMIN-001"],
            ho2m_path=tmp_ho2m,
            ho1m_path=tmp_ho1m,
            max_retries=0,
        )
        sv = HO2Supervisor(tmp_path, "ADMIN", EmptySynthesizeHO1(), mock_ledger, mock_budgeter, config)

        result = sv.handle_turn("hello")

        assert result.quality_gate_passed is False
        turns = mock_ledger.events_of_type("TURN_RECORDED")
        assert len(turns) == 1
        assert "[Quality gate failed:" in turns[0].metadata["response"]

    def test_turn_recorded_on_retry_exhausted(self, tmp_path, mock_ledger, mock_budgeter, tmp_ho2m, tmp_ho1m):
        class AlwaysEmptyHO1:
            def __init__(self):
                self.executed_wos = []

            def execute(self, work_order: dict) -> dict:
                wo = dict(work_order)
                self.executed_wos.append(wo)
                if wo.get("wo_type") == "classify":
                    wo["state"] = "completed"
                    wo["output_result"] = {"speech_act": "greeting", "ambiguity": "low"}
                else:
                    wo["state"] = "completed"
                    wo["output_result"] = {"response_text": ""}
                wo["cost"] = {
                    "input_tokens": 10, "output_tokens": 10, "total_tokens": 20,
                    "llm_calls": 1, "tool_calls": 0, "elapsed_ms": 1,
                }
                return wo

        config = HO2Config(
            attention_templates=["ATT-ADMIN-001"],
            ho2m_path=tmp_ho2m,
            ho1m_path=tmp_ho1m,
            max_retries=1,
        )
        sv = HO2Supervisor(tmp_path, "ADMIN", AlwaysEmptyHO1(), mock_ledger, mock_budgeter, config)

        result = sv.handle_turn("hello")

        assert result.quality_gate_passed is False
        turns = mock_ledger.events_of_type("TURN_RECORDED")
        assert len(turns) == 1
        assert turns[0].metadata["turn_number"] == 1

    def test_classify_budget_from_config(self, tmp_path, mock_ho1, mock_ledger, mock_budgeter, tmp_ho2m, tmp_ho1m):
        config = HO2Config(
            attention_templates=["ATT-ADMIN-001"],
            ho2m_path=tmp_ho2m,
            ho1m_path=tmp_ho1m,
            classify_budget=4321,
        )
        sv = HO2Supervisor(tmp_path, "ADMIN", mock_ho1, mock_ledger, mock_budgeter, config)

        sv.handle_turn("hello")

        classify_wos = [w for w in mock_ho1.executed_wos if w["wo_type"] == "classify"]
        assert classify_wos[0]["constraints"]["token_budget"] == 4321

    def test_budget_mode_propagated_to_wo(self, tmp_path, mock_ho1, mock_ledger, mock_budgeter, tmp_ho2m, tmp_ho1m):
        config = HO2Config(
            attention_templates=["ATT-ADMIN-001"],
            ho2m_path=tmp_ho2m,
            ho1m_path=tmp_ho1m,
            budget_mode="warn",
            followup_min_remaining=777,
        )
        sv = HO2Supervisor(tmp_path, "ADMIN", mock_ho1, mock_ledger, mock_budgeter, config)

        sv.handle_turn("hello")

        assert len(mock_ho1.executed_wos) >= 2
        for wo in mock_ho1.executed_wos[:2]:
            assert wo["constraints"]["budget_mode"] == "warn"
            assert wo["constraints"]["followup_min_remaining"] == 777


# ===========================================================================
# HO3 Signal Wiring Tests (10) -- HANDOFF-29B
# ===========================================================================

class MockHO3Memory:
    """Mock HO3Memory for testing signal wiring.

    Tracks all log_signal and check_gate calls without touching disk.
    """

    def __init__(self, enabled=True, biases=None, gate_crossed=False):
        self.config = MagicMock()
        self.config.enabled = enabled
        self.logged_signals: List[Dict[str, Any]] = []
        self.gate_checks: List[str] = []
        self._biases = biases or []
        self._gate_crossed = gate_crossed

    def log_signal(self, signal_id: str, session_id: str, event_id: str, metadata=None) -> str:
        self.logged_signals.append({
            "signal_id": signal_id,
            "session_id": session_id,
            "event_id": event_id,
            "metadata": metadata,
        })
        return event_id

    def read_active_biases(self, as_of_ts=None) -> list:
        return list(self._biases)

    def check_gate(self, signal_id: str):
        self.gate_checks.append(signal_id)
        result = MagicMock()
        result.crossed = self._gate_crossed
        result.signal_id = signal_id
        return result


class TestHO3SignalWiring:
    """10 tests for HANDOFF-29B: HO3 signal wiring into HO2 supervisor."""

    def _make_supervisor(self, tmp_path, ho3_memory=None, ho3_enabled=False,
                         classify_response=None, tools_allowed=None):
        ho2m = tmp_path / "ho2m"
        ho2m.mkdir(exist_ok=True)
        ho1m = tmp_path / "ho1m"
        ho1m.mkdir(exist_ok=True)
        config = HO2Config(
            attention_templates=["ATT-ADMIN-001"],
            ho2m_path=ho2m,
            ho1m_path=ho1m,
            ho3_enabled=ho3_enabled,
            tools_allowed=tools_allowed or [],
        )
        responses = {
            "classify": classify_response or {"speech_act": "greeting", "ambiguity": "low"},
            "synthesize": {"response_text": "Hello! How can I help you?"},
        }
        ho1 = MockHO1Executor(responses=responses)
        ledger = MockLedgerClient()
        budgeter = MockTokenBudgeter()
        sv = HO2Supervisor(
            plane_root=tmp_path,
            agent_class="ADMIN",
            ho1_executor=ho1,
            ledger_client=ledger,
            token_budgeter=budgeter,
            config=config,
            ho3_memory=ho3_memory,
        )
        return sv, ho1, ledger

    def test_ho3_disabled_skips_all(self, tmp_path):
        """ho3_memory=None -> no signal logging, no gate check, no biases."""
        sv, ho1, ledger = self._make_supervisor(tmp_path, ho3_memory=None, ho3_enabled=False)
        result = sv.handle_turn("hello")
        assert isinstance(result, TurnResult)
        assert result.response  # Normal response still works
        assert result.consolidation_candidates == []

    def test_ho3_enabled_flag_false_skips(self, tmp_path):
        """ho3_memory provided but config.ho3_enabled=False -> skipped."""
        ho3 = MockHO3Memory(enabled=True)
        sv, ho1, ledger = self._make_supervisor(tmp_path, ho3_memory=ho3, ho3_enabled=False)
        result = sv.handle_turn("hello")
        assert len(ho3.logged_signals) == 0
        assert len(ho3.gate_checks) == 0
        assert result.consolidation_candidates == []

    def test_signal_from_classification(self, tmp_path):
        """Classify returns speech_act='tool_query' -> log_signal('intent:tool_query') called."""
        ho3 = MockHO3Memory(enabled=True)
        sv, ho1, ledger = self._make_supervisor(
            tmp_path, ho3_memory=ho3, ho3_enabled=True,
            classify_response={"speech_act": "tool_query", "ambiguity": "low"},
        )
        result = sv.handle_turn("check gates")
        # Should have logged intent:tool_query
        intent_signals = [s for s in ho3.logged_signals if s["signal_id"] == "intent:tool_query"]
        assert len(intent_signals) == 1
        assert intent_signals[0]["session_id"] == result.session_id

    def test_intent_signal_missing_classification(self, tmp_path):
        """Classify returns empty/no speech_act field -> no signal logged, no error."""
        ho3 = MockHO3Memory(enabled=True)
        sv, ho1, ledger = self._make_supervisor(
            tmp_path, ho3_memory=ho3, ho3_enabled=True,
            classify_response={"ambiguity": "high"},  # No speech_act
        )
        result = sv.handle_turn("hello")
        # No intent signal should be logged
        intent_signals = [s for s in ho3.logged_signals if s["signal_id"].startswith("intent:")]
        assert len(intent_signals) == 0
        # But the turn should still complete normally
        assert result.response

    def test_signal_logging_does_not_affect_response(self, tmp_path):
        """Response text identical with and without ho3_enabled (same LLM mock)."""
        # Without HO3
        sv_off, ho1_off, _ = self._make_supervisor(tmp_path, ho3_memory=None, ho3_enabled=False)
        result_off = sv_off.handle_turn("hello")

        # With HO3
        ho3 = MockHO3Memory(enabled=True)
        sv_on, ho1_on, _ = self._make_supervisor(tmp_path, ho3_memory=ho3, ho3_enabled=True)
        result_on = sv_on.handle_turn("hello")

        assert result_off.response == result_on.response

    def test_ho3_read_injects_biases(self, tmp_path):
        """Active biases exist -> context_line values injected into synthesize WO."""
        biases = [{"context_line": "User prefers tool queries", "weight": 0.8, "scope": "global"}]
        ho3 = MockHO3Memory(enabled=True, biases=biases)
        sv, ho1, ledger = self._make_supervisor(tmp_path, ho3_memory=ho3, ho3_enabled=True)
        sv.handle_turn("hello")
        # The synthesize WO should have ho3_biases in its input_context
        synth_wos = [w for w in ho1.executed_wos if w["wo_type"] == "synthesize"]
        assert len(synth_wos) >= 1
        assert "ho3_biases" in synth_wos[0]["input_context"]
        assert synth_wos[0]["input_context"]["ho3_biases"] == ["User prefers tool queries"]

    def test_domain_signal_logged(self, tmp_path):
        """labels.domain from classify should emit domain:<value> signal."""
        ho3 = MockHO3Memory(enabled=True)
        sv, ho1, ledger = self._make_supervisor(
            tmp_path, ho3_memory=ho3, ho3_enabled=True,
            classify_response={
                "speech_act": "question",
                "ambiguity": "low",
                "labels": {"domain": "system", "task": "inspect"},
            },
        )
        sv.handle_turn("show packages")
        assert any(s["signal_id"] == "domain:system" for s in ho3.logged_signals)

    def test_task_signal_logged(self, tmp_path):
        """labels.task from classify should emit task:<value> signal."""
        ho3 = MockHO3Memory(enabled=True)
        sv, ho1, ledger = self._make_supervisor(
            tmp_path, ho3_memory=ho3, ho3_enabled=True,
            classify_response={
                "speech_act": "question",
                "ambiguity": "low",
                "labels": {"domain": "system", "task": "inspect"},
            },
        )
        sv.handle_turn("show packages")
        assert any(s["signal_id"] == "task:inspect" for s in ho3.logged_signals)

    def test_outcome_signal_logged(self, tmp_path):
        """Successful synthesize should emit outcome:success signal."""
        ho3 = MockHO3Memory(enabled=True)
        sv, ho1, ledger = self._make_supervisor(
            tmp_path, ho3_memory=ho3, ho3_enabled=True,
            classify_response={"speech_act": "greeting", "ambiguity": "low"},
        )
        sv.handle_turn("hello")
        assert any(s["signal_id"] == "outcome:success" for s in ho3.logged_signals)

    def test_no_domain_signal_without_labels(self, tmp_path):
        """If classify has no labels, domain signal should not be logged."""
        ho3 = MockHO3Memory(enabled=True)
        sv, ho1, ledger = self._make_supervisor(
            tmp_path, ho3_memory=ho3, ho3_enabled=True,
            classify_response={"speech_act": "question", "ambiguity": "low"},
        )
        sv.handle_turn("hello")
        assert not any(s["signal_id"].startswith("domain:") for s in ho3.logged_signals)

    def test_select_biases_called_at_step2b(self, tmp_path):
        """HO2 should call select_biases instead of dump-all behavior."""
        biases = [{"context_line": "line-from-artifact", "scope": "global"}]
        ho3 = MockHO3Memory(enabled=True, biases=biases)
        sv, ho1, ledger = self._make_supervisor(
            tmp_path, ho3_memory=ho3, ho3_enabled=True,
            classify_response={
                "speech_act": "question",
                "ambiguity": "low",
                "labels": {"domain": "system", "task": "inspect"},
            },
        )
        with patch("ho2_supervisor.select_biases") as mock_select:
            mock_select.return_value = [{"context_line": "line-from-selector"}]
            sv.handle_turn("show packages")
            assert mock_select.called

    def test_context_lines_injected(self, tmp_path):
        """Selected artifacts should inject context_line strings only."""
        biases = [{"context_line": "artifact-context-line", "scope": "global"}]
        ho3 = MockHO3Memory(enabled=True, biases=biases)
        sv, ho1, ledger = self._make_supervisor(
            tmp_path, ho3_memory=ho3, ho3_enabled=True,
            classify_response={"speech_act": "question", "ambiguity": "low", "labels": {"domain": "system"}},
        )
        sv.handle_turn("show packages")
        synth_wos = [w for w in ho1.executed_wos if w["wo_type"] == "synthesize"]
        assert synth_wos
        assert synth_wos[0]["input_context"].get("ho3_biases") == ["artifact-context-line"]

    def test_gate_check_runs_post_turn(self, tmp_path):
        """Signals logged -> check_gate called for each."""
        ho3 = MockHO3Memory(enabled=True)
        sv, ho1, ledger = self._make_supervisor(
            tmp_path, ho3_memory=ho3, ho3_enabled=True,
            classify_response={"speech_act": "greeting", "ambiguity": "low"},
        )
        sv.handle_turn("hello")
        # At least one gate check should have been called for the intent signal
        assert len(ho3.gate_checks) >= 1
        assert "intent:greeting" in ho3.gate_checks

    def test_gate_false_empty_candidates(self, tmp_path):
        """Gate not crossed -> consolidation_candidates is empty list."""
        ho3 = MockHO3Memory(enabled=True, gate_crossed=False)
        sv, ho1, ledger = self._make_supervisor(
            tmp_path, ho3_memory=ho3, ho3_enabled=True,
            classify_response={"speech_act": "greeting", "ambiguity": "low"},
        )
        result = sv.handle_turn("hello")
        assert result.consolidation_candidates == []

    def test_gate_true_populates_candidates(self, tmp_path):
        """Gate crossed for signal_id X -> X in consolidation_candidates."""
        ho3 = MockHO3Memory(enabled=True, gate_crossed=True)
        sv, ho1, ledger = self._make_supervisor(
            tmp_path, ho3_memory=ho3, ho3_enabled=True,
            classify_response={"speech_act": "admin_command", "ambiguity": "low"},
        )
        result = sv.handle_turn("check gates")
        assert "intent:admin_command" in result.consolidation_candidates

    def test_turn_result_has_field(self, tmp_path):
        """TurnResult has consolidation_candidates field."""
        sv, ho1, ledger = self._make_supervisor(tmp_path, ho3_memory=None, ho3_enabled=False)
        result = sv.handle_turn("hello")
        assert hasattr(result, "consolidation_candidates")
        assert isinstance(result.consolidation_candidates, list)


# ===========================================================================
# HO3 Consolidation Tests (4) -- HANDOFF-29C
# ===========================================================================

class MockHO3MemoryForConsolidation:
    """Extended mock for consolidation testing with gate re-check."""

    def __init__(self, enabled=True, gate_crossed=True, event_ids=None):
        self.config = MagicMock()
        self.config.enabled = enabled
        self.logged_signals: List[Dict[str, Any]] = []
        self.gate_checks: List[str] = []
        self.logged_overlays: List[Dict[str, Any]] = []
        self._gate_crossed = gate_crossed
        self._gate_check_count = 0
        self._event_ids = event_ids or ["EVT-001", "EVT-002", "EVT-003"]

    def log_signal(self, signal_id, session_id, event_id, metadata=None):
        self.logged_signals.append({"signal_id": signal_id, "session_id": session_id, "event_id": event_id})
        return event_id

    def read_active_biases(self, as_of_ts=None):
        return []

    def check_gate(self, signal_id):
        self.gate_checks.append(signal_id)
        self._gate_check_count += 1
        result = MagicMock()
        result.crossed = self._gate_crossed
        result.signal_id = signal_id
        return result

    def read_signals(self, signal_id=None, min_count=0):
        acc = MagicMock()
        acc.signal_id = signal_id or "intent:test"
        acc.count = 5
        acc.session_ids = ["SES-1", "SES-2", "SES-3"]
        acc.event_ids = list(self._event_ids)
        acc.last_seen = "2026-02-17T10:00:00+00:00"
        acc.decay = 1.0
        return [acc]

    def log_overlay(self, overlay):
        source_ids = overlay.get("source_event_ids", [])
        if not source_ids:
            raise ValueError("source_event_ids must be non-empty")
        self.logged_overlays.append(overlay)
        return f"OVL-test{len(self.logged_overlays)}"


class TestConsolidationDispatch:
    """4 tests for HANDOFF-29C: consolidation dispatch + tool signal extraction."""

    def _make_supervisor_with_consolidation(self, tmp_path, ho3_memory, classify_response=None):
        ho2m = tmp_path / "ho2m_consol"
        ho2m.mkdir(exist_ok=True)
        ho1m = tmp_path / "ho1m_consol"
        ho1m.mkdir(exist_ok=True)
        config = HO2Config(
            attention_templates=["ATT-ADMIN-001"],
            ho2m_path=ho2m,
            ho1m_path=ho1m,
            ho3_enabled=True,
            consolidation_budget=4000,
            consolidation_contract_id="PRC-CONSOLIDATE-001",
        )
        consolidation_response = {
            "bias": "User frequently uses tool queries",
            "category": "tool_preference",
            "salience_weight": 0.8,
            "decay_modifier": 0.95,
        }
        responses = {
            "classify": classify_response or {"speech_act": "greeting", "ambiguity": "low"},
            "synthesize": {"response_text": "Hello!"},
            "consolidate": consolidation_response,
        }
        ho1 = MockHO1Executor(responses=responses)
        ledger = MockLedgerClient()
        budgeter = MockTokenBudgeter()
        sv = HO2Supervisor(
            plane_root=tmp_path,
            agent_class="ADMIN",
            ho1_executor=ho1,
            ledger_client=ledger,
            token_budgeter=budgeter,
            config=config,
            ho3_memory=ho3_memory,
        )
        return sv, ho1, ledger

    def test_consolidation_dispatches_wo(self, tmp_path):
        """run_consolidation(['sig1']) -> dispatches WO with wo_type='consolidate'."""
        ho3 = MockHO3MemoryForConsolidation(enabled=True, gate_crossed=True)
        sv, ho1, ledger = self._make_supervisor_with_consolidation(tmp_path, ho3)
        sv.start_session()
        results = sv.run_consolidation(["intent:test"])
        # Should have dispatched a consolidation WO
        consolidate_wos = [w for w in ho1.executed_wos if w["wo_type"] == "consolidate"]
        assert len(consolidate_wos) == 1
        assert consolidate_wos[0]["constraints"]["prompt_contract_id"] == "PRC-CONSOLIDATE-001"
        assert consolidate_wos[0]["constraints"]["domain_tags"] == ["consolidation"]

    def test_consolidation_idempotent(self, tmp_path):
        """run_consolidation twice for same signal+window -> second is no-op."""
        ho3 = MockHO3MemoryForConsolidation(enabled=True, gate_crossed=True)
        sv, ho1, ledger = self._make_supervisor_with_consolidation(tmp_path, ho3)
        sv.start_session()
        # First call: gate crossed, consolidation runs
        results1 = sv.run_consolidation(["intent:test"])
        assert len(results1) == 1

        # After first consolidation, gate should return False
        ho3._gate_crossed = False
        results2 = sv.run_consolidation(["intent:test"])
        assert len(results2) == 0

    def test_consolidation_overlay_has_source_ids(self, tmp_path):
        """Consolidation writes overlay -> source_event_ids populated."""
        ho3 = MockHO3MemoryForConsolidation(
            enabled=True, gate_crossed=True,
            event_ids=["EVT-a01", "EVT-a02", "EVT-a03"],
        )
        sv, ho1, ledger = self._make_supervisor_with_consolidation(tmp_path, ho3)
        sv.start_session()
        sv.run_consolidation(["intent:test"])
        # Overlay should have been written
        assert len(ho3.logged_overlays) == 1
        overlay = ho3.logged_overlays[0]
        assert len(overlay["source_event_ids"]) > 0
        assert "EVT-a01" in overlay["source_event_ids"]

    def test_tool_signal_from_wo_chain(self, tmp_path):
        """WO chain has cost.tool_ids_used=['gate_check'] -> log_signal('tool:gate_check') called."""
        ho3 = MockHO3MemoryForConsolidation(enabled=True, gate_crossed=False)
        ho2m = tmp_path / "ho2m_tool"
        ho2m.mkdir(exist_ok=True)
        ho1m = tmp_path / "ho1m_tool"
        ho1m.mkdir(exist_ok=True)
        config = HO2Config(
            attention_templates=["ATT-ADMIN-001"],
            ho2m_path=ho2m,
            ho1m_path=ho1m,
            ho3_enabled=True,
            tools_allowed=["gate_check"],
        )
        # Mock HO1 that includes tool_ids_used in cost
        class ToolTrackingHO1:
            def __init__(self):
                self.executed_wos = []

            def execute(self, work_order):
                wo = dict(work_order)
                self.executed_wos.append(wo)
                wo_type = wo.get("wo_type", "classify")
                if wo_type == "classify":
                    wo["state"] = "completed"
                    wo["output_result"] = {"speech_act": "greeting", "ambiguity": "low"}
                    wo["cost"] = {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150,
                                  "llm_calls": 1, "tool_calls": 0, "elapsed_ms": 100}
                else:
                    wo["state"] = "completed"
                    wo["output_result"] = {"response_text": "Hello!"}
                    wo["cost"] = {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150,
                                  "llm_calls": 1, "tool_calls": 1, "elapsed_ms": 100,
                                  "tool_ids_used": ["gate_check"]}
                return wo

        ho1 = ToolTrackingHO1()
        ledger = MockLedgerClient()
        budgeter = MockTokenBudgeter()
        sv = HO2Supervisor(
            plane_root=tmp_path,
            agent_class="ADMIN",
            ho1_executor=ho1,
            ledger_client=ledger,
            token_budgeter=budgeter,
            config=config,
            ho3_memory=ho3,
        )
        sv.handle_turn("hello")
        # Should have logged tool:gate_check signal
        tool_signals = [s for s in ho3.logged_signals if s["signal_id"] == "tool:gate_check"]
        assert len(tool_signals) == 1


# ===========================================================================
# Intent Lifecycle Integration Tests (4) -- HANDOFF-31C
# ===========================================================================

class TestIntentLifecycleIntegration:
    """4 integration tests for intent lifecycle in handle_turn."""

    def _make_intent_supervisor(self, tmp_path, classify_response=None):
        ho2m = tmp_path / "ho2m_intent"
        ho2m.mkdir(exist_ok=True)
        ho1m = tmp_path / "ho1m_intent"
        ho1m.mkdir(exist_ok=True)
        config = HO2Config(
            attention_templates=["ATT-ADMIN-001"],
            ho2m_path=ho2m,
            ho1m_path=ho1m,
        )
        responses = {
            "classify": classify_response or {"speech_act": "greeting", "ambiguity": "low"},
            "synthesize": {"response_text": "Hello!"},
        }
        ho1 = MockHO1Executor(responses=responses)
        ledger = MockLedgerClient()
        budgeter = MockTokenBudgeter()
        sv = HO2Supervisor(
            plane_root=tmp_path,
            agent_class="ADMIN",
            ho1_executor=ho1,
            ledger_client=ledger,
            token_budgeter=budgeter,
            config=config,
        )
        return sv, ho1, ledger

    def test_intent_declared_on_first_turn(self, tmp_path):
        """First handle_turn -> INTENT_DECLARED in ho2m."""
        sv, ho1, ledger = self._make_intent_supervisor(tmp_path)
        sv.handle_turn("hello")
        declared = ledger.events_of_type("INTENT_DECLARED")
        assert len(declared) == 1
        assert declared[0].metadata["intent_id"].startswith("INT-")
        assert declared[0].metadata["scope"] == "session"

    def test_intent_superseded_on_topic_switch(self, tmp_path):
        """Turn with action=new when active -> SUPERSEDED + DECLARED."""
        # First turn: declares an intent (bridge mode, no intent_signal)
        sv, ho1, ledger = self._make_intent_supervisor(tmp_path)
        sv.handle_turn("hello")
        first_declared = ledger.events_of_type("INTENT_DECLARED")
        assert len(first_declared) == 1

        # Second turn: new topic with intent_signal.action=new
        ho1.responses["classify"] = {
            "speech_act": "command", "ambiguity": "low",
            "intent_signal": {"action": "new", "candidate_objective": "Check gates", "confidence": 0.9},
        }
        sv.handle_turn("check the gates")
        superseded = ledger.events_of_type("INTENT_SUPERSEDED")
        assert len(superseded) == 1
        all_declared = ledger.events_of_type("INTENT_DECLARED")
        assert len(all_declared) == 2  # first + new

    def test_intent_closed_on_farewell(self, tmp_path):
        """Turn with close -> INTENT_CLOSED in ho2m."""
        sv, ho1, ledger = self._make_intent_supervisor(tmp_path)
        sv.handle_turn("hello")  # declares intent

        ho1.responses["classify"] = {
            "speech_act": "farewell", "ambiguity": "low",
            "intent_signal": {"action": "close", "candidate_objective": "done", "confidence": 0.9},
        }
        sv.handle_turn("goodbye")
        closed = ledger.events_of_type("INTENT_CLOSED")
        assert len(closed) == 1

    def test_no_intent_events_on_continue(self, tmp_path):
        """Turn with continue -> no new INTENT_* events beyond initial declare."""
        sv, ho1, ledger = self._make_intent_supervisor(tmp_path)
        sv.handle_turn("hello")  # declares intent
        declared_count = len(ledger.events_of_type("INTENT_DECLARED"))

        ho1.responses["classify"] = {
            "speech_act": "question", "ambiguity": "low",
            "intent_signal": {"action": "continue", "candidate_objective": "still chatting", "confidence": 0.8},
        }
        sv.handle_turn("tell me more")
        # No new DECLARED, SUPERSEDED, or CLOSED
        assert len(ledger.events_of_type("INTENT_DECLARED")) == declared_count
        assert len(ledger.events_of_type("INTENT_SUPERSEDED")) == 0
        assert len(ledger.events_of_type("INTENT_CLOSED")) == 0
