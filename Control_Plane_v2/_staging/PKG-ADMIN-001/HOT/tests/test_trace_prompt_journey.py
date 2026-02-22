from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

_HERE = Path(__file__).resolve().parent
_HOT = _HERE.parent

if (_HOT / "kernel" / "ledger_client.py").exists():
    _ROOT = _HOT.parent
    sys.path.insert(0, str(_HOT / "admin"))
    for p in [_HOT / "kernel", _HOT / "scripts", _HOT]:
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
else:
    _STAGING_ROOT = _HERE.parents[2]
    sys.path.insert(0, str(_STAGING_ROOT / "PKG-ADMIN-001" / "HOT" / "admin"))
    for p in [
        _STAGING_ROOT / "PKG-KERNEL-001" / "HOT" / "kernel",
        _STAGING_ROOT / "PKG-KERNEL-001" / "HOT",
    ]:
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))

import main as admin_main
from ledger_client import LedgerClient, LedgerEntry


class _CaptureDispatcher:
    def __init__(self):
        self.tools = {}

    def register_tool(self, name, handler):
        self.tools[name] = handler


def _seed(tmp_path, ledger_rel: str, event_type: str, submission_id: str, metadata: dict, reason: str = "", timestamp: str = "2026-02-18T00:00:00+00:00"):
    ledger_path = tmp_path / ledger_rel
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger = LedgerClient(ledger_path=ledger_path)
    with patch("kernel.pristine.assert_append_only", return_value=None):
        ledger.write(
            LedgerEntry(
                event_type=event_type,
                submission_id=submission_id,
                decision=event_type,
                reason=reason or f"{event_type} reason",
                metadata=metadata,
                timestamp=timestamp,
            )
        )


def _tool(tmp_path):
    dispatcher = _CaptureDispatcher()
    admin_main._register_admin_tools(dispatcher, root=tmp_path)
    return dispatcher.tools["trace_prompt_journey"]


def _seed_single_turn(tmp_path, sid: str, with_tool: bool = False):
    c_wo = f"WO-{sid}-001"
    s_wo = f"WO-{sid}-002"

    _seed(tmp_path, "HO2/ledger/ho2m.jsonl", "WO_PLANNED", c_wo, {"provenance": {"session_id": sid, "work_order_id": c_wo}, "wo_type": "classify"}, timestamp="2026-02-18T00:00:01+00:00")
    _seed(tmp_path, "HO2/ledger/ho2m.jsonl", "WO_DISPATCHED", c_wo, {"provenance": {"session_id": sid, "work_order_id": c_wo}}, timestamp="2026-02-18T00:00:02+00:00")
    _seed(tmp_path, "HOT/ledger/governance.jsonl", "EXCHANGE", "PRC-CLASSIFY-001", {"session_id": sid, "work_order_id": c_wo, "prompt": "classify prompt", "response": '{"speech_act":"command"}', "input_tokens": 11, "output_tokens": 5, "finish_reason": "stop", "latency_ms": 100}, timestamp="2026-02-18T00:00:03+00:00")
    _seed(tmp_path, "HO1/ledger/ho1m.jsonl", "WO_COMPLETED", c_wo, {"provenance": {"session_id": sid, "work_order_id": c_wo}, "output_result": {"speech_act": "command", "ambiguity": "low"}}, timestamp="2026-02-18T00:00:04+00:00")

    _seed(tmp_path, "HO2/ledger/ho2m.jsonl", "WO_PLANNED", s_wo, {"provenance": {"session_id": sid, "work_order_id": s_wo}, "wo_type": "synthesize"}, timestamp="2026-02-18T00:00:05+00:00")
    _seed(tmp_path, "HO2/ledger/ho2m.jsonl", "WO_DISPATCHED", s_wo, {"provenance": {"session_id": sid, "work_order_id": s_wo}}, timestamp="2026-02-18T00:00:06+00:00")

    _seed(tmp_path, "HOT/ledger/governance.jsonl", "EXCHANGE", "PRC-SYNTHESIZE-001", {"session_id": sid, "work_order_id": s_wo, "prompt": "synth prompt 1", "response": "tool_use", "input_tokens": 12, "output_tokens": 3, "finish_reason": "tool_use", "latency_ms": 90}, timestamp="2026-02-18T00:00:07+00:00")

    if with_tool:
        _seed(tmp_path, "HO1/ledger/ho1m.jsonl", "TOOL_CALL", s_wo, {"provenance": {"session_id": sid, "work_order_id": s_wo}, "tool_id": "list_sessions", "status": "ok", "arguments": {"limit": 5}, "result": {"status": "ok", "sessions": []}}, timestamp="2026-02-18T00:00:08+00:00")
        _seed(tmp_path, "HOT/ledger/governance.jsonl", "EXCHANGE", "PRC-SYNTHESIZE-001", {"session_id": sid, "work_order_id": s_wo, "prompt": "synth prompt 2", "response": "final response", "input_tokens": 15, "output_tokens": 20, "finish_reason": "stop", "latency_ms": 120}, timestamp="2026-02-18T00:00:09+00:00")

    _seed(tmp_path, "HO1/ledger/ho1m.jsonl", "WO_COMPLETED", s_wo, {"provenance": {"session_id": sid, "work_order_id": s_wo}, "output_result": {"response_text": "Here are latest sessions"}}, timestamp="2026-02-18T00:00:10+00:00")
    _seed(tmp_path, "HO2/ledger/ho2m.jsonl", "WO_QUALITY_GATE", sid, {"provenance": {"session_id": sid}, "wo_id": s_wo, "decision": "accept"}, reason="output passes", timestamp="2026-02-18T00:00:11+00:00")
    _seed(tmp_path, "HO2/ledger/ho2m.jsonl", "TURN_RECORDED", sid, {"provenance": {"session_id": sid}, "turn_number": 1, "user_message": "show latest sessions", "response": "Here are latest sessions"}, timestamp="2026-02-18T00:00:12+00:00")


def test_journey_requires_session_id(tmp_path):
    result = _tool(tmp_path)({})
    assert result["status"] == "error"


def test_journey_empty_session(tmp_path):
    result = _tool(tmp_path)({"session_id": "SES-EMPTY"})
    assert result["status"] == "ok"
    assert result["turns"] == []
    assert result["wo_count"] == 0


def test_journey_single_turn_no_tools(tmp_path):
    sid = "SES-TRACE001"
    _seed_single_turn(tmp_path, sid, with_tool=False)
    result = _tool(tmp_path)({"session_id": sid})
    assert result["status"] == "ok"
    assert result["wo_count"] == 2
    assert result["llm_call_count"] == 2
    assert result["tool_call_count"] == 0


def test_journey_single_turn_with_tool(tmp_path):
    sid = "SES-TRACE002"
    _seed_single_turn(tmp_path, sid, with_tool=True)
    result = _tool(tmp_path)({"session_id": sid})
    assert result["status"] == "ok"
    assert result["wo_count"] == 2
    assert result["llm_call_count"] == 3
    assert result["tool_call_count"] == 1


def test_journey_multi_turn(tmp_path):
    sid = "SES-TRACE003"
    _seed_single_turn(tmp_path, sid, with_tool=False)
    _seed_single_turn(tmp_path, sid, with_tool=True)
    result = _tool(tmp_path)({"session_id": sid})
    assert len(result["turns"]) >= 1


def test_journey_includes_prompt_text(tmp_path):
    sid = "SES-TRACE004"
    _seed_single_turn(tmp_path, sid, with_tool=False)
    result = _tool(tmp_path)({"session_id": sid, "include_prompts": True})
    stages = result["turns"][0]["wo_chain"][0]["stages"]
    prompt_stage = next(s for s in stages if s["stage"] == "prompt_sent")
    assert "prompt_text" in prompt_stage


def test_journey_excludes_prompt_text(tmp_path):
    sid = "SES-TRACE005"
    _seed_single_turn(tmp_path, sid, with_tool=False)
    result = _tool(tmp_path)({"session_id": sid, "include_prompts": False})
    stages = result["turns"][0]["wo_chain"][0]["stages"]
    prompt_stage = next(s for s in stages if s["stage"] == "prompt_sent")
    assert "prompt_text" not in prompt_stage


def test_journey_includes_tool_payload(tmp_path):
    sid = "SES-TRACE006"
    _seed_single_turn(tmp_path, sid, with_tool=True)
    result = _tool(tmp_path)({"session_id": sid, "include_tool_payloads": True})
    stages = result["turns"][0]["wo_chain"][1]["stages"]
    tool_stage = next(s for s in stages if s["stage"] == "tool_call")
    assert "arguments" in tool_stage
    assert "result" in tool_stage


def test_journey_excludes_tool_payload(tmp_path):
    sid = "SES-TRACE007"
    _seed_single_turn(tmp_path, sid, with_tool=True)
    result = _tool(tmp_path)({"session_id": sid, "include_tool_payloads": False})
    stages = result["turns"][0]["wo_chain"][1]["stages"]
    tool_stage = next(s for s in stages if s["stage"] == "tool_call")
    assert "arguments" not in tool_stage
    assert "result" not in tool_stage


def test_journey_filter_by_wo_id(tmp_path):
    sid = "SES-TRACE008"
    _seed_single_turn(tmp_path, sid, with_tool=True)
    wo_id = f"WO-{sid}-002"
    result = _tool(tmp_path)({"session_id": sid, "wo_id": wo_id})
    all_wos = [wo["wo_id"] for turn in result["turns"] for wo in turn["wo_chain"]]
    assert all_wos == [wo_id]


def test_journey_max_bytes_truncation(tmp_path):
    sid = "SES-TRACE009"
    _seed_single_turn(tmp_path, sid, with_tool=True)
    result = _tool(tmp_path)({"session_id": sid, "max_bytes": 1000})
    assert result["truncated"] is True
    assert "truncation_marker" in result


def test_journey_quality_gate_included(tmp_path):
    sid = "SES-TRACE010"
    _seed_single_turn(tmp_path, sid, with_tool=False)
    result = _tool(tmp_path)({"session_id": sid})
    assert "quality_gate" in result["turns"][0]
    assert "evidence_id" in result["turns"][0]["quality_gate"]
