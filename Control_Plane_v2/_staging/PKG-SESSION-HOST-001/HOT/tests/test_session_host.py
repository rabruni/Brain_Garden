"""Tests for Session Host + Tool Dispatcher.

DTT: tests written before implementation.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

_staging = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_staging / "PKG-KERNEL-001" / "HOT" / "kernel"))
sys.path.insert(0, str(_staging / "PKG-PROMPT-ROUTER-001" / "HOT" / "kernel"))
sys.path.insert(0, str(_staging / "PKG-SESSION-HOST-001" / "HOT" / "kernel"))

from ledger_client import LedgerClient  # noqa: E402
from prompt_router import RouteOutcome  # noqa: E402
from session_host import AgentConfig, SessionHost  # noqa: E402
from tool_dispatch import ToolDispatcher  # noqa: E402


@pytest.fixture(autouse=True)
def _bypass_pristine():
    with patch("kernel.pristine.assert_append_only", return_value=None):
        yield


def _make_ledger(tmp_path: Path) -> LedgerClient:
    ledger_path = tmp_path / "ledger" / "governance.jsonl"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    return LedgerClient(ledger_path=ledger_path)


class FakeAttention:
    def __init__(self, context_text: str = "context-block"):
        self.context_text = context_text
        self.calls = []

    def assemble(self, request):
        self.calls.append(request)
        return SimpleNamespace(
            context_text=self.context_text,
            context_hash="ctx-hash",
            fragments=[],
            template_id="ATT-ADMIN-001",
            pipeline_trace=[],
            budget_used=SimpleNamespace(tokens_assembled=100, queries_executed=2, elapsed_ms=5),
            warnings=[],
        )


class FakeRouter:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def route(self, request):
        self.calls.append(request)
        if not self._responses:
            raise AssertionError("No queued router responses")
        return self._responses.pop(0)


class FakeResponse(SimpleNamespace):
    pass


def _resp(
    content: str,
    outcome=RouteOutcome.SUCCESS,
    input_tokens: int = 10,
    output_tokens: int = 20,
    exchange_entry_id: str = "LED-exchange-1",
):
    return FakeResponse(
        content=content,
        outcome=outcome,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        exchange_entry_id=exchange_entry_id,
        dispatch_entry_id="LED-dispatch-1",
        error_code=None,
        error_message=None,
    )


def _base_config() -> AgentConfig:
    return AgentConfig(
        agent_id="admin-001",
        agent_class="ADMIN",
        framework_id="FMWK-005",
        tier="hot",
        system_prompt="You are ADMIN.",
        attention={
            "template_id": "ATT-ADMIN-001",
            "prompt_contract": {
                "contract_id": "PRC-ADMIN-001",
                "prompt_pack_id": "PRM-ADMIN-001",
                "boundary": {"max_tokens": 1024, "temperature": 0.0},
            },
        },
        tools=[
            {
                "tool_id": "echo",
                "description": "Echo a message",
                "handler": "tools.echo",
                "parameters": {
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                },
            }
        ],
        budget={"session_token_limit": 1000, "turn_limit": 5, "timeout_seconds": 3600},
        permissions={"read": ["HOT/*"], "write": ["HO2/*"], "forbidden": ["HOT/kernel/*"]},
    )


def _make_host(tmp_path: Path, router: FakeRouter, attention: FakeAttention | None = None, config: AgentConfig | None = None, dev_mode: bool = True, now_fn=None):
    ledger = _make_ledger(tmp_path)
    attention = attention or FakeAttention()
    config = config or _base_config()
    dispatcher = ToolDispatcher(
        plane_root=tmp_path,
        tool_configs=config.tools,
        permissions=config.permissions,
    )
    dispatcher.register_tool("echo", lambda args: {"echo": args.get("text", "")})
    host = SessionHost(
        plane_root=tmp_path,
        agent_config=config,
        attention_service=attention,
        router=router,
        tool_dispatcher=dispatcher,
        ledger_client=ledger,
        dev_mode=dev_mode,
        now_fn=now_fn,
    )
    return host, ledger, dispatcher, attention


class TestSessionLifecycle:
    def test_start_session_returns_session_id(self, tmp_path: Path):
        host, _, _, _ = _make_host(tmp_path, FakeRouter([_resp("ok")]))
        session_id = host.start_session()
        assert session_id.startswith("SES-")

    def test_start_session_logs_to_ledger(self, tmp_path: Path):
        host, ledger, _, _ = _make_host(tmp_path, FakeRouter([_resp("ok")]))
        host.start_session()
        entries = ledger.read_by_event_type("SESSION_START")
        assert len(entries) == 1
        assert entries[0].metadata["agent_id"] == "admin-001"

    def test_end_session_logs_to_ledger(self, tmp_path: Path):
        host, ledger, _, _ = _make_host(tmp_path, FakeRouter([_resp("ok")]))
        host.start_session()
        host.end_session()
        entries = ledger.read_by_event_type("SESSION_END")
        assert len(entries) == 1

    def test_end_session_reports_budget(self, tmp_path: Path):
        host, ledger, _, _ = _make_host(tmp_path, FakeRouter([_resp("ok")]))
        host.start_session()
        host.process_turn("hello")
        host.end_session()
        end = ledger.read_by_event_type("SESSION_END")[0]
        assert "total_input_tokens" in end.metadata
        assert "total_output_tokens" in end.metadata


class TestTurnProcessing:
    def test_process_turn_calls_attention(self, tmp_path: Path):
        attention = FakeAttention("ctx")
        host, _, _, _ = _make_host(tmp_path, FakeRouter([_resp("ok")]), attention=attention)
        host.start_session()
        host.process_turn("hello")
        assert len(attention.calls) == 1

    def test_process_turn_builds_prompt_with_context(self, tmp_path: Path):
        attention = FakeAttention("context payload")
        router = FakeRouter([_resp("ok")])
        host, _, _, _ = _make_host(tmp_path, router, attention=attention)
        host.start_session()
        host.process_turn("hello")
        assert "context payload" in router.calls[0].prompt

    def test_process_turn_includes_system_prompt(self, tmp_path: Path):
        router = FakeRouter([_resp("ok")])
        host, _, _, _ = _make_host(tmp_path, router)
        host.start_session()
        host.process_turn("hello")
        assert "You are ADMIN." in router.calls[0].prompt

    def test_process_turn_includes_conversation_history(self, tmp_path: Path):
        router = FakeRouter([_resp("first"), _resp("second")])
        host, _, _, _ = _make_host(tmp_path, router)
        host.start_session()
        host.process_turn("first question")
        host.process_turn("second question")
        assert "first question" in router.calls[1].prompt
        assert "first" in router.calls[1].prompt

    def test_process_turn_sends_through_router(self, tmp_path: Path):
        router = FakeRouter([_resp("ok")])
        host, _, _, _ = _make_host(tmp_path, router)
        host.start_session()
        host.process_turn("hello")
        assert len(router.calls) == 1

    def test_process_turn_returns_response_text(self, tmp_path: Path):
        host, _, _, _ = _make_host(tmp_path, FakeRouter([_resp("assistant answer")]))
        host.start_session()
        result = host.process_turn("hello")
        assert result.response == "assistant answer"

    def test_process_turn_updates_history(self, tmp_path: Path):
        host, _, _, _ = _make_host(tmp_path, FakeRouter([_resp("assistant")]))
        host.start_session()
        host.process_turn("hello")
        assert len(host.history) == 2
        assert host.history[0].role == "user"
        assert host.history[1].role == "assistant"

    def test_process_turn_with_empty_context(self, tmp_path: Path):
        host, _, _, _ = _make_host(tmp_path, FakeRouter([_resp("ok")]), attention=FakeAttention(""))
        host.start_session()
        result = host.process_turn("hello")
        assert result.response == "ok"


class TestToolDispatchIntegration:
    def test_tool_definitions_sent_to_api(self, tmp_path: Path):
        router = FakeRouter([_resp("ok")])
        host, _, _, _ = _make_host(tmp_path, router)
        host.start_session()
        host.process_turn("hello")
        assert router.calls[0].structured_output["type"] == "tools"

    def test_tool_call_dispatched(self, tmp_path: Path):
        tool_req = json.dumps({"tool_use": {"tool_id": "echo", "arguments": {"text": "hi"}}})
        router = FakeRouter([_resp(tool_req), _resp("final")])
        host, _, _, _ = _make_host(tmp_path, router)
        host.start_session()
        result = host.process_turn("run tool")
        assert result.response == "final"
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0]["tool_id"] == "echo"

    def test_tool_result_sent_back(self, tmp_path: Path):
        tool_req = json.dumps({"tool_use": {"tool_id": "echo", "arguments": {"text": "x"}}})
        router = FakeRouter([_resp(tool_req), _resp("done")])
        host, _, _, _ = _make_host(tmp_path, router)
        host.start_session()
        host.process_turn("call")
        assert len(router.calls) == 2
        assert "tool_result" in router.calls[1].prompt

    def test_forbidden_tool_rejected(self, tmp_path: Path):
        tool_req = json.dumps({"tool_use": {"tool_id": "unknown", "arguments": {}}})
        router = FakeRouter([_resp(tool_req), _resp("fallback")])
        host, _, _, _ = _make_host(tmp_path, router)
        host.start_session()
        result = host.process_turn("call")
        assert result.response == "fallback"
        assert result.tool_calls[0]["status"] == "error"

    def test_tool_permission_check(self, tmp_path: Path):
        cfg = _base_config()
        cfg.permissions = {"read": [], "write": [], "forbidden": ["*"]}
        router = FakeRouter([_resp(json.dumps({"tool_use": {"tool_id": "echo", "arguments": {"text": "x"}}})), _resp("done")])
        host, _, _, _ = _make_host(tmp_path, router, config=cfg)
        host.start_session()
        result = host.process_turn("call")
        assert result.tool_calls[0]["status"] == "error"

    def test_multiple_tool_calls(self, tmp_path: Path):
        tool_req = json.dumps({"tool_use": [
            {"tool_id": "echo", "arguments": {"text": "a"}},
            {"tool_id": "echo", "arguments": {"text": "b"}},
        ]})
        router = FakeRouter([_resp(tool_req), _resp("final")])
        host, _, _, _ = _make_host(tmp_path, router)
        host.start_session()
        result = host.process_turn("multi")
        assert len(result.tool_calls) == 2

    def test_tool_error_handled(self, tmp_path: Path):
        router = FakeRouter([_resp(json.dumps({"tool_use": {"tool_id": "boom", "arguments": {}}})), _resp("final")])
        host, _, dispatcher, _ = _make_host(tmp_path, router)
        dispatcher.register_tool("boom", lambda args: (_ for _ in ()).throw(RuntimeError("tool crashed")))
        host.start_session()
        result = host.process_turn("run")
        assert result.tool_calls[0]["status"] == "error"

    def test_tool_result_logged(self, tmp_path: Path):
        router = FakeRouter([_resp(json.dumps({"tool_use": {"tool_id": "echo", "arguments": {"text": "z"}}})), _resp("done")])
        host, ledger, _, _ = _make_host(tmp_path, router)
        host.start_session()
        host.process_turn("tool")
        entries = ledger.read_by_event_type("TOOL_CALL")
        assert len(entries) == 1


class TestBudgetAndBoundaries:
    def test_budget_tracked_per_session(self, tmp_path: Path):
        router = FakeRouter([_resp("a", input_tokens=5, output_tokens=7), _resp("b", input_tokens=6, output_tokens=8)])
        host, _, _, _ = _make_host(tmp_path, router)
        host.start_session()
        host.process_turn("1")
        host.process_turn("2")
        assert host.total_input_tokens == 11
        assert host.total_output_tokens == 15

    def test_turn_limit_enforced(self, tmp_path: Path):
        cfg = _base_config()
        cfg.budget["turn_limit"] = 1
        host, _, _, _ = _make_host(tmp_path, FakeRouter([_resp("first")]), config=cfg)
        host.start_session()
        host.process_turn("hello")
        with pytest.raises(RuntimeError, match="turn limit"):
            host.process_turn("again")

    def test_timeout_enforced(self, tmp_path: Path):
        cfg = _base_config()
        cfg.budget["timeout_seconds"] = 1
        now_vals = iter([0.0, 0.0, 2.0, 2.0])
        host, _, _, _ = _make_host(tmp_path, FakeRouter([_resp("ok")]), config=cfg, now_fn=lambda: next(now_vals))
        host.start_session()
        with pytest.raises(RuntimeError, match="timeout"):
            host.process_turn("late")

    def test_dev_mode_bypasses_auth(self, tmp_path: Path):
        router = FakeRouter([_resp("ok")])
        host, _, _, _ = _make_host(tmp_path, router, dev_mode=True)
        host.start_session()
        host.process_turn("hello")
        assert router.calls[0].auth_token is None

    def test_config_loaded_from_file(self, tmp_path: Path):
        cfg = {
            "agent_id": "admin-001",
            "agent_class": "ADMIN",
            "framework_id": "FMWK-005",
            "tier": "hot",
            "system_prompt": "sys",
            "attention": {"template_id": "ATT", "prompt_contract": {"contract_id": "PRC-1", "prompt_pack_id": "PRM-1", "boundary": {"max_tokens": 1, "temperature": 0.0}}},
            "tools": [],
            "budget": {"session_token_limit": 1, "turn_limit": 1, "timeout_seconds": 1},
            "permissions": {"read": [], "write": [], "forbidden": []},
        }
        cfg_path = tmp_path / "agent.json"
        cfg_path.write_text(json.dumps(cfg))
        loaded = AgentConfig.from_file(cfg_path)
        assert loaded.agent_id == "admin-001"
        assert loaded.attention["prompt_contract"]["contract_id"] == "PRC-1"


class TestToolDispatcher:
    def test_register_and_execute(self, tmp_path: Path):
        disp = ToolDispatcher(tmp_path, [{"tool_id": "echo", "parameters": {"type": "object"}}], {"read": ["*"], "write": ["*"], "forbidden": []})
        disp.register_tool("echo", lambda args: {"ok": args["x"]})
        result = disp.execute("echo", {"x": 1})
        assert result.status == "ok"
        assert result.output == {"ok": 1}

    def test_unknown_tool(self, tmp_path: Path):
        disp = ToolDispatcher(tmp_path, [], {"read": ["*"], "write": ["*"], "forbidden": []})
        result = disp.execute("missing", {})
        assert result.status == "error"

    def test_get_api_tools(self, tmp_path: Path):
        disp = ToolDispatcher(tmp_path, [{"tool_id": "echo", "description": "d", "parameters": {"type": "object"}}], {"read": ["*"], "write": ["*"], "forbidden": []})
        tools = disp.get_api_tools()
        assert len(tools) == 1
        assert tools[0]["name"] == "echo"
