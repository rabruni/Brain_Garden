"""Tests for projection overlay writer (HANDOFF-31D)."""

from pathlib import Path
import sys
from unittest.mock import patch

_staging = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_staging / "PKG-KERNEL-001" / "HOT" / "kernel"))
sys.path.insert(0, str(_staging / "PKG-KERNEL-001" / "HOT"))
sys.path.insert(0, str(_staging / "PKG-HO2-SUPERVISOR-001" / "HO2" / "kernel"))

from kernel.ledger_client import LedgerClient
from liveness import LivenessState
from overlay_writer import write_projection


import pytest


@pytest.fixture(autouse=True)
def _allow_append_only_external_paths():
    with patch("kernel.pristine.assert_append_only", lambda *args, **kwargs: None):
        yield


class TestOverlayWriter:
    def test_projection_written(self, tmp_path):
        ledger_path = tmp_path / "HO2" / "ledger" / "ho2_context_authority.jsonl"
        ledger = LedgerClient(ledger_path=ledger_path)
        liveness = LivenessState()
        write_projection(
            liveness=liveness,
            session_id="SES-001",
            turn_id="TURN-001",
            token_budget=10000,
            overlay_ledger=ledger,
        )
        entries = ledger.read_all()
        assert len(entries) == 1
        assert entries[0].event_type == "PROJECTION_COMPUTED"

    def test_projection_metadata(self, tmp_path):
        ledger_path = tmp_path / "HO2" / "ledger" / "ho2_context_authority.jsonl"
        ledger = LedgerClient(ledger_path=ledger_path)
        liveness = LivenessState(
            intents={"INT-1": {"status": "LIVE", "objective": "obj", "scope": "session"}},
            work_orders={"WO-1": {"status": "OPEN", "wo_type": "synthesize"}},
            active_intents=["INT-1"],
            open_work_orders=["WO-1"],
        )
        result = write_projection(liveness, "SES-1", "TURN-001", 999, ledger)
        assert result["session_id"] == "SES-1"
        assert result["turn_id"] == "TURN-001"
        assert result["intent_count"] == 1
        assert result["open_wo_count"] == 1

    def test_projection_budget_recorded(self, tmp_path):
        ledger_path = tmp_path / "HO2" / "ledger" / "ho2_context_authority.jsonl"
        ledger = LedgerClient(ledger_path=ledger_path)
        meta = write_projection(LivenessState(), "SES-1", "TURN-001", 4321, ledger)
        assert meta["token_budget"] == 4321
        entry = ledger.read_all()[0]
        assert entry.metadata["token_budget"] == 4321

    def test_empty_liveness_writes(self, tmp_path):
        ledger_path = tmp_path / "HO2" / "ledger" / "ho2_context_authority.jsonl"
        ledger = LedgerClient(ledger_path=ledger_path)
        meta = write_projection(LivenessState(), "SES-1", "TURN-001", 100, ledger)
        assert meta["active_intents"] == []
        assert meta["open_work_orders"] == []
        assert meta["failed_items"] == []
        assert meta["escalations"] == []
