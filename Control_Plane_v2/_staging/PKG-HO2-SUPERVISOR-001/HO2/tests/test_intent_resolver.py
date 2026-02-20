"""Tests for intent_resolver.py — pure function intent lifecycle.

12 tests covering: transition table (8 states), intent ID format,
determinism, objective propagation, bridge mode. No LLM calls,
no file I/O, no mocks needed — pure function tests.
"""

import sys
from pathlib import Path

_staging = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_staging / "PKG-HO2-SUPERVISOR-001" / "HO2" / "kernel"))

import pytest

from intent_resolver import resolve_intent_transition, make_intent_id, TransitionDecision


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _classify(action=None, objective="do something", confidence=0.9):
    """Build a classify_result dict with optional intent_signal."""
    base = {"speech_act": "command", "ambiguity": "low"}
    if action is not None:
        base["intent_signal"] = {
            "action": action,
            "candidate_objective": objective,
            "confidence": confidence,
        }
    return base


def _active_intent(intent_id="INT-AABBCCDD-001", objective="Previous task"):
    return {"intent_id": intent_id, "objective": objective, "scope": "session"}


# ===========================================================================
# Transition Table Tests (8)
# ===========================================================================

class TestTransitionTable:
    def test_no_active_new_declares(self):
        """No active intent + action=new -> DECLARE."""
        decision = resolve_intent_transition(
            active_intents=[],
            classify_result=_classify(action="new", objective="List packages"),
            session_id="SES-AABBCCDD",
            sequence=1,
        )
        assert decision.action == "declare"
        assert decision.new_intent is not None
        assert decision.new_intent["objective"] == "List packages"
        assert decision.new_intent["intent_id"].startswith("INT-")

    def test_no_active_missing_declares(self):
        """No active intent + no intent_signal -> DECLARE (bridge)."""
        decision = resolve_intent_transition(
            active_intents=[],
            classify_result={"speech_act": "command", "ambiguity": "low"},
            session_id="SES-AABBCCDD",
            sequence=1,
        )
        assert decision.action == "declare"
        assert decision.new_intent is not None

    def test_no_active_close_noop(self):
        """No active + close -> NOOP."""
        decision = resolve_intent_transition(
            active_intents=[],
            classify_result=_classify(action="close"),
            session_id="SES-AABBCCDD",
            sequence=1,
        )
        assert decision.action == "noop"

    def test_active_continue(self):
        """1 active + continue -> CONTINUE."""
        decision = resolve_intent_transition(
            active_intents=[_active_intent()],
            classify_result=_classify(action="continue"),
            session_id="SES-AABBCCDD",
            sequence=2,
        )
        assert decision.action == "continue"
        assert decision.new_intent is None
        assert decision.closed_intent_id is None

    def test_active_new_supersedes(self):
        """1 active + new -> SUPERSEDE + DECLARE."""
        decision = resolve_intent_transition(
            active_intents=[_active_intent("INT-AABBCCDD-001")],
            classify_result=_classify(action="new", objective="New topic"),
            session_id="SES-AABBCCDD",
            sequence=2,
        )
        assert decision.action == "supersede"
        assert decision.closed_intent_id == "INT-AABBCCDD-001"
        assert decision.new_intent is not None
        assert decision.new_intent["objective"] == "New topic"

    def test_active_close(self):
        """1 active + close -> CLOSE."""
        decision = resolve_intent_transition(
            active_intents=[_active_intent("INT-AABBCCDD-001")],
            classify_result=_classify(action="close"),
            session_id="SES-AABBCCDD",
            sequence=2,
        )
        assert decision.action == "close"
        assert decision.closed_intent_id == "INT-AABBCCDD-001"

    def test_active_unclear_conflict(self):
        """1 active + unclear -> CONTINUE + CONFLICT_FLAG."""
        decision = resolve_intent_transition(
            active_intents=[_active_intent()],
            classify_result=_classify(action="unclear"),
            session_id="SES-AABBCCDD",
            sequence=2,
        )
        assert decision.action == "continue"
        assert decision.conflict_flag is not None

    def test_multiple_active_conflict(self):
        """2 active intents -> CONTINUE most recent + CONFLICT_FLAG."""
        decision = resolve_intent_transition(
            active_intents=[
                _active_intent("INT-AABBCCDD-001", "First task"),
                _active_intent("INT-AABBCCDD-002", "Second task"),
            ],
            classify_result=_classify(action="continue"),
            session_id="SES-AABBCCDD",
            sequence=3,
        )
        assert decision.action == "continue"
        assert decision.conflict_flag is not None
        assert decision.conflict_flag["active_count"] == 2


# ===========================================================================
# Utility Tests (4)
# ===========================================================================

class TestIntentUtilities:
    def test_intent_id_format(self):
        """make_intent_id produces correct format."""
        iid = make_intent_id("SES-F8805C46", 1)
        assert iid == "INT-F8805C46-001"

    def test_deterministic(self):
        """Same inputs -> same output."""
        args = (
            [_active_intent()],
            _classify(action="continue"),
            "SES-AABBCCDD",
            2,
        )
        d1 = resolve_intent_transition(*args)
        d2 = resolve_intent_transition(*args)
        assert d1.action == d2.action
        assert d1.new_intent == d2.new_intent
        assert d1.closed_intent_id == d2.closed_intent_id
        assert d1.conflict_flag == d2.conflict_flag

    def test_objective_from_classify(self):
        """candidate_objective flows into new_intent.objective."""
        decision = resolve_intent_transition(
            active_intents=[],
            classify_result=_classify(action="new", objective="Check gate status"),
            session_id="SES-AABBCCDD",
            sequence=1,
        )
        assert decision.new_intent["objective"] == "Check gate status"

    def test_active_missing_bridge(self):
        """1 active + no intent_signal -> CONTINUE (bridge mode)."""
        decision = resolve_intent_transition(
            active_intents=[_active_intent()],
            classify_result={"speech_act": "question", "ambiguity": "low"},
            session_id="SES-AABBCCDD",
            sequence=2,
        )
        assert decision.action == "continue"
        assert decision.new_intent is None
