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

from ledger_client import LedgerClient, LedgerEntry
from ledger_forensics import (
    correlate_by_wo,
    entry_session_id,
    entry_wo_id,
    extract_stages,
    order_chronologically,
    parse_ts,
    read_all_ledgers,
)


def _seed(tmp_path, ledger_rel: str, event_type: str, submission_id: str, metadata: dict, timestamp: str = "2026-02-18T00:00:00+00:00"):
    ledger_path = tmp_path / ledger_rel
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger = LedgerClient(ledger_path=ledger_path)
    with patch("kernel.pristine.assert_append_only", return_value=None):
        ledger.write(
            LedgerEntry(
                event_type=event_type,
                submission_id=submission_id,
                decision=event_type,
                reason=f"{event_type} reason",
                metadata=metadata,
                timestamp=timestamp,
            )
        )


def test_entry_session_id_from_metadata():
    e = LedgerEntry("X", "SUB", "D", "R", metadata={"session_id": "SES-1"})
    assert entry_session_id(e) == "SES-1"


def test_entry_session_id_from_provenance():
    e = LedgerEntry("X", "SUB", "D", "R", metadata={"provenance": {"session_id": "SES-2"}})
    assert entry_session_id(e) == "SES-2"


def test_entry_session_id_from_submission():
    e = LedgerEntry("X", "SES-3", "D", "R")
    assert entry_session_id(e) == "SES-3"


def test_entry_session_id_missing():
    e = LedgerEntry("X", "SUB", "D", "R")
    assert entry_session_id(e) is None


def test_entry_wo_id_from_provenance():
    e = LedgerEntry("X", "SUB", "D", "R", metadata={"provenance": {"work_order_id": "WO-1"}})
    assert entry_wo_id(e) == "WO-1"


def test_entry_wo_id_from_submission():
    e = LedgerEntry("X", "WO-2", "D", "R")
    assert entry_wo_id(e) == "WO-2"


def test_entry_wo_id_missing():
    e = LedgerEntry("X", "SUB", "D", "R")
    assert entry_wo_id(e) is None


def test_read_all_ledgers_filters_session(tmp_path):
    sid = "SES-READ001"
    _seed(tmp_path, "HO2/ledger/ho2m.jsonl", "TURN_RECORDED", sid, {"session_id": sid})
    _seed(tmp_path, "HO2/ledger/ho2m.jsonl", "TURN_RECORDED", "SES-OTHER", {"session_id": "SES-OTHER"})
    _seed(tmp_path, "HO1/ledger/ho1m.jsonl", "TOOL_CALL", f"WO-{sid}-001", {"provenance": {"session_id": sid, "work_order_id": f"WO-{sid}-001"}})
    _seed(tmp_path, "HOT/ledger/governance.jsonl", "EXCHANGE", "PRC-S", {"session_id": sid, "work_order_id": f"WO-{sid}-001"})

    grouped = read_all_ledgers(tmp_path, sid)
    assert len(grouped["ho2m"]) == 1
    assert len(grouped["ho1m"]) == 1
    assert len(grouped["governance"]) == 1


def test_read_all_ledgers_missing_files(tmp_path):
    grouped = read_all_ledgers(tmp_path, "SES-NONE")
    assert grouped == {"ho2m": [], "ho1m": [], "governance": []}


def test_correlate_by_wo_groups(tmp_path):
    sid = "SES-CORR001"
    wo = f"WO-{sid}-001"
    _seed(tmp_path, "HO2/ledger/ho2m.jsonl", "WO_PLANNED", wo, {"provenance": {"session_id": sid, "work_order_id": wo}, "wo_type": "classify"})
    _seed(tmp_path, "HO1/ledger/ho1m.jsonl", "LLM_CALL", wo, {"provenance": {"session_id": sid, "work_order_id": wo}})
    _seed(tmp_path, "HOT/ledger/governance.jsonl", "EXCHANGE", "PRC-C", {"session_id": sid, "work_order_id": wo})
    grouped = correlate_by_wo(read_all_ledgers(tmp_path, sid))
    assert wo in grouped
    assert len(grouped[wo]) == 3


def test_order_chronologically(tmp_path):
    sid = "SES-ORD001"
    wo = f"WO-{sid}-001"
    _seed(tmp_path, "HOT/ledger/governance.jsonl", "EXCHANGE", "PRC", {"session_id": sid, "work_order_id": wo}, "2026-02-18T00:00:03+00:00")
    _seed(tmp_path, "HO2/ledger/ho2m.jsonl", "WO_PLANNED", wo, {"provenance": {"session_id": sid, "work_order_id": wo}, "wo_type": "classify"}, "2026-02-18T00:00:01+00:00")
    _seed(tmp_path, "HO1/ledger/ho1m.jsonl", "LLM_CALL", wo, {"provenance": {"session_id": sid, "work_order_id": wo}}, "2026-02-18T00:00:02+00:00")
    grouped = correlate_by_wo(read_all_ledgers(tmp_path, sid))
    ordered = order_chronologically(grouped[wo])
    assert [x["entry"].event_type for x in ordered] == ["WO_PLANNED", "LLM_CALL", "EXCHANGE"]


def test_extract_stages_classify_wo(tmp_path):
    sid = "SES-STAGE001"
    wo = f"WO-{sid}-001"
    _seed(tmp_path, "HO2/ledger/ho2m.jsonl", "WO_PLANNED", wo, {"provenance": {"session_id": sid, "work_order_id": wo}, "wo_type": "classify"}, "2026-02-18T00:00:01+00:00")
    _seed(tmp_path, "HO2/ledger/ho2m.jsonl", "WO_DISPATCHED", wo, {"provenance": {"session_id": sid, "work_order_id": wo}}, "2026-02-18T00:00:02+00:00")
    _seed(tmp_path, "HOT/ledger/governance.jsonl", "EXCHANGE", "PRC-C", {"session_id": sid, "work_order_id": wo, "prompt": "P", "response": "R", "input_tokens": 1, "output_tokens": 1}, "2026-02-18T00:00:03+00:00")
    _seed(tmp_path, "HO1/ledger/ho1m.jsonl", "WO_COMPLETED", wo, {"provenance": {"session_id": sid, "work_order_id": wo}}, "2026-02-18T00:00:04+00:00")
    grouped = correlate_by_wo(read_all_ledgers(tmp_path, sid))
    stages = extract_stages(grouped[wo])
    names = [s["stage"] for s in stages]
    assert names == ["wo_planned", "wo_dispatched", "prompt_sent", "llm_response", "wo_completed"]


def test_extract_stages_synthesize_with_tools(tmp_path):
    sid = "SES-STAGE002"
    wo = f"WO-{sid}-002"
    _seed(tmp_path, "HO2/ledger/ho2m.jsonl", "WO_PLANNED", wo, {"provenance": {"session_id": sid, "work_order_id": wo}, "wo_type": "synthesize"}, "2026-02-18T00:00:01+00:00")
    _seed(tmp_path, "HOT/ledger/governance.jsonl", "EXCHANGE", "PRC-S", {"session_id": sid, "work_order_id": wo, "prompt": "P1", "response": "R1"}, "2026-02-18T00:00:02+00:00")
    _seed(tmp_path, "HO1/ledger/ho1m.jsonl", "TOOL_CALL", wo, {"provenance": {"session_id": sid, "work_order_id": wo}, "tool_id": "list_sessions", "arguments": {"limit": 5}, "result": {"status": "ok"}}, "2026-02-18T00:00:03+00:00")
    _seed(tmp_path, "HOT/ledger/governance.jsonl", "EXCHANGE", "PRC-S", {"session_id": sid, "work_order_id": wo, "prompt": "P2", "response": "R2"}, "2026-02-18T00:00:04+00:00")
    grouped = correlate_by_wo(read_all_ledgers(tmp_path, sid))
    stages = extract_stages(grouped[wo])
    names = [s["stage"] for s in stages]
    assert names.count("tool_call") == 1
    assert names.count("prompt_sent") == 2
    assert names.count("llm_response") == 2


def test_extract_stages_evidence_ids(tmp_path):
    sid = "SES-STAGE003"
    wo = f"WO-{sid}-001"
    _seed(tmp_path, "HO2/ledger/ho2m.jsonl", "WO_PLANNED", wo, {"provenance": {"session_id": sid, "work_order_id": wo}, "wo_type": "classify"})
    grouped = correlate_by_wo(read_all_ledgers(tmp_path, sid))
    stages = extract_stages(grouped[wo])
    assert all("evidence_id" in s for s in stages)
