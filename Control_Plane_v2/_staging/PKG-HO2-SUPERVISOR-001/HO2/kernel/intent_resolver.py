"""Intent lifecycle resolution — pure deterministic function.

Reads classify output's intent_signal and decides the next intent
transition. NO LLM calls, NO file I/O, NO side effects. The caller
(ho2_supervisor.py) writes ledger events based on the decision.

Part of PKG-HO2-SUPERVISOR-001 (HANDOFF-31C).
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

__all__ = ["TransitionDecision", "resolve_intent_transition", "make_intent_id"]


@dataclass
class TransitionDecision:
    """Result of intent transition resolution."""
    action: str  # "declare", "continue", "supersede", "close", "noop"
    new_intent: Optional[Dict[str, Any]] = None
    closed_intent_id: Optional[str] = None
    conflict_flag: Optional[Dict[str, Any]] = None


def make_intent_id(session_id: str, sequence: int) -> str:
    """Generate intent ID: INT-<session_id_short>-<3-digit-sequence>.

    session_id format: SES-F8805C46 -> extracts F8805C46
    """
    short = session_id.split("-", 1)[1] if "-" in session_id else session_id
    return f"INT-{short}-{sequence:03d}"


def resolve_intent_transition(
    active_intents: List[Dict[str, Any]],
    classify_result: Dict[str, Any],
    session_id: str,
    sequence: int,
) -> TransitionDecision:
    """Pure deterministic function: resolve intent transition.

    Transition table:
    | Active | action          | Decision                    |
    |--------|-----------------|-----------------------------|
    | None   | new/unclear/missing | DECLARE new             |
    | None   | continue        | DECLARE new (bridge)        |
    | None   | close           | NOOP                        |
    | 1      | new             | SUPERSEDE old + DECLARE new |
    | 1      | continue        | CONTINUE                    |
    | 1      | close           | CLOSE active                |
    | 1      | unclear         | CONTINUE + CONFLICT_FLAG    |
    | 1      | missing         | CONTINUE (bridge)           |
    | 2+     | any             | CONTINUE most recent + CONFLICT |
    """
    intent_signal = classify_result.get("intent_signal")
    action = intent_signal.get("action") if intent_signal else None

    # Derive objective
    if intent_signal:
        objective = intent_signal.get("candidate_objective", "")
    else:
        speech_act = classify_result.get("speech_act", "unknown")
        objective = f"{speech_act} (bridge)"

    num_active = len(active_intents)

    # --- 2+ active intents: always conflict ---
    if num_active >= 2:
        return TransitionDecision(
            action="continue",
            conflict_flag={
                "reason": "multiple_active_intents",
                "active_count": num_active,
                "intent_ids": [i.get("intent_id") for i in active_intents],
            },
        )

    # --- No active intents ---
    if num_active == 0:
        if action == "close":
            return TransitionDecision(action="noop")
        # new, continue, unclear, missing -> DECLARE
        new_intent = _make_new_intent(session_id, sequence, objective)
        return TransitionDecision(action="declare", new_intent=new_intent)

    # --- Exactly 1 active intent ---
    active = active_intents[0]
    active_id = active.get("intent_id")

    if action == "new":
        new_intent = _make_new_intent(session_id, sequence, objective)
        return TransitionDecision(
            action="supersede",
            new_intent=new_intent,
            closed_intent_id=active_id,
        )

    if action == "close":
        return TransitionDecision(
            action="close",
            closed_intent_id=active_id,
        )

    if action == "unclear":
        return TransitionDecision(
            action="continue",
            conflict_flag={
                "reason": "unclear_intent_signal",
                "active_intent_id": active_id,
            },
        )

    # continue or missing (bridge mode) -> CONTINUE
    return TransitionDecision(action="continue")


def _make_new_intent(session_id: str, sequence: int, objective: str) -> Dict[str, Any]:
    """Build a new intent dict."""
    return {
        "intent_id": make_intent_id(session_id, sequence),
        "objective": objective,
        "scope": "session",
    }
