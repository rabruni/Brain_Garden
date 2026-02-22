"""Tests for liveness reducer (HANDOFF-31D)."""

from pathlib import Path
import sys

_staging = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_staging / "PKG-HO2-SUPERVISOR-001" / "HO2" / "kernel"))

from liveness import LivenessState, reduce_liveness


def _entry(event_type, ts, *, submission_id=None, metadata=None, reason=""):
    return {
        "event_type": event_type,
        "timestamp": ts,
        "id": f"LED-{ts[-8:]}-{event_type}",
        "submission_id": submission_id or "",
        "reason": reason or event_type,
        "metadata": metadata or {},
    }


class TestLivenessReducer:
    def test_empty_entries(self):
        s = reduce_liveness([], [])
        assert isinstance(s, LivenessState)
        assert s.active_intents == []
        assert s.open_work_orders == []
        assert s.failed_items == []
        assert s.escalations == []

    def test_intent_declared_is_live(self):
        ho2m = [
            _entry(
                "INTENT_DECLARED",
                "2026-02-20T00:00:00+00:00",
                submission_id="SES-1",
                metadata={"intent_id": "INT-001", "scope": "session", "objective": "hello"},
            )
        ]
        s = reduce_liveness(ho2m, [])
        assert "INT-001" in s.active_intents
        assert s.intents["INT-001"]["status"] == "LIVE"

    def test_intent_closed_not_live(self):
        ho2m = [
            _entry("INTENT_DECLARED", "2026-02-20T00:00:00+00:00", metadata={"intent_id": "INT-001"}),
            _entry("INTENT_CLOSED", "2026-02-20T00:00:10+00:00", metadata={"intent_id": "INT-001"}),
        ]
        s = reduce_liveness(ho2m, [])
        assert "INT-001" not in s.active_intents
        assert s.intents["INT-001"]["status"] == "CLOSED"

    def test_intent_superseded_not_live(self):
        ho2m = [
            _entry("INTENT_DECLARED", "2026-02-20T00:00:00+00:00", metadata={"intent_id": "INT-001"}),
            _entry("INTENT_SUPERSEDED", "2026-02-20T00:00:10+00:00", metadata={"intent_id": "INT-001"}),
        ]
        s = reduce_liveness(ho2m, [])
        assert "INT-001" not in s.active_intents
        assert s.intents["INT-001"]["status"] == "SUPERSEDED"

    def test_wo_planned_is_open(self):
        ho2m = [
            _entry(
                "WO_PLANNED",
                "2026-02-20T00:00:00+00:00",
                submission_id="WO-1",
                metadata={"provenance": {"work_order_id": "WO-1"}, "wo_type": "synthesize"},
            )
        ]
        s = reduce_liveness(ho2m, [])
        assert "WO-1" in s.open_work_orders
        assert s.work_orders["WO-1"]["status"] == "OPEN"

    def test_wo_completed_not_open(self):
        ho2m = [
            _entry("WO_PLANNED", "2026-02-20T00:00:00+00:00", submission_id="WO-1",
                   metadata={"provenance": {"work_order_id": "WO-1"}}),
        ]
        ho1m = [
            _entry("WO_COMPLETED", "2026-02-20T00:00:05+00:00", submission_id="WO-1",
                   metadata={"provenance": {"work_order_id": "WO-1"}}),
        ]
        s = reduce_liveness(ho2m, ho1m)
        assert "WO-1" not in s.open_work_orders
        assert s.work_orders["WO-1"]["status"] == "COMPLETED"

    def test_wo_failed_in_failed_items(self):
        ho2m = [
            _entry("WO_PLANNED", "2026-02-20T00:00:00+00:00", submission_id="WO-1",
                   metadata={"provenance": {"work_order_id": "WO-1"}}),
            _entry("ESCALATION", "2026-02-20T00:00:05+00:00", submission_id="SES-1",
                   metadata={"wo_id": "WO-1"}, reason="gate reject"),
        ]
        s = reduce_liveness(ho2m, [])
        assert s.work_orders["WO-1"]["status"] == "FAILED"
        assert any(item["wo_id"] == "WO-1" for item in s.failed_items)

    def test_cross_ledger_join(self):
        ho2m = [
            _entry("WO_PLANNED", "2026-02-20T00:00:00+00:00", submission_id="WO-42",
                   metadata={"provenance": {"work_order_id": "WO-42"}, "wo_type": "classify"}),
        ]
        ho1m = [
            _entry("WO_COMPLETED", "2026-02-20T00:00:05+00:00", submission_id="WO-42",
                   metadata={"provenance": {"work_order_id": "WO-42"}}),
        ]
        s = reduce_liveness(ho2m, ho1m)
        assert s.work_orders["WO-42"]["status"] == "COMPLETED"
        assert s.work_orders["WO-42"]["wo_type"] == "classify"

    def test_latest_event_wins(self):
        ho2m = [
            _entry("WO_PLANNED", "2026-02-20T00:00:00+00:00", submission_id="WO-1",
                   metadata={"provenance": {"work_order_id": "WO-1"}}),
            _entry("ESCALATION", "2026-02-20T00:00:05+00:00", submission_id="SES-1",
                   metadata={"wo_id": "WO-1"}),
            _entry("WO_COMPLETED", "2026-02-20T00:00:10+00:00", submission_id="WO-1",
                   metadata={"provenance": {"work_order_id": "WO-1"}}),
        ]
        s = reduce_liveness(ho2m, [])
        assert s.work_orders["WO-1"]["status"] == "COMPLETED"

    def test_deterministic_ordering(self):
        a = [
            _entry("INTENT_DECLARED", "2026-02-20T00:00:00+00:00", metadata={"intent_id": "INT-A"}),
            _entry("INTENT_CLOSED", "2026-02-20T00:00:10+00:00", metadata={"intent_id": "INT-A"}),
        ]
        b = list(reversed(a))
        s1 = reduce_liveness(a, [])
        s2 = reduce_liveness(b, [])
        assert s1.active_intents == s2.active_intents
        assert s1.intents == s2.intents

    def test_multiple_intents(self):
        ho2m = [
            _entry("INTENT_DECLARED", "2026-02-20T00:00:00+00:00", metadata={"intent_id": "INT-1"}),
            _entry("INTENT_DECLARED", "2026-02-20T00:00:01+00:00", metadata={"intent_id": "INT-2"}),
            _entry("INTENT_CLOSED", "2026-02-20T00:00:02+00:00", metadata={"intent_id": "INT-1"}),
        ]
        s = reduce_liveness(ho2m, [])
        assert "INT-2" in s.active_intents
        assert "INT-1" not in s.active_intents
        assert len(s.intents) == 2

    def test_session_scoped(self):
        ho2m = [
            _entry("INTENT_DECLARED", "2026-02-20T00:00:00+00:00", submission_id="SES-A",
                   metadata={"provenance": {"session_id": "SES-A"}, "intent_id": "INT-A"}),
            _entry("INTENT_DECLARED", "2026-02-20T00:00:01+00:00", submission_id="SES-B",
                   metadata={"provenance": {"session_id": "SES-B"}, "intent_id": "INT-B"}),
        ]
        s = reduce_liveness(ho2m, [], session_id="SES-A")
        assert "INT-A" in s.active_intents
        assert "INT-B" not in s.active_intents
