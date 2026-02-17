"""Session lifecycle management for HO2 cognitive dispatch.

Absorbed from PKG-SESSION-HOST-001. Session ID generation,
start/end lifecycle events, in-memory turn history, WO sequence.
"""

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import sys
from pathlib import Path

_staging = Path(__file__).resolve().parents[3]
_kernel_dir = _staging / "PKG-KERNEL-001" / "HOT" / "kernel"
if _kernel_dir.exists():
    sys.path.insert(0, str(_kernel_dir))
    sys.path.insert(0, str(_kernel_dir.parent))

try:
    from ledger_client import LedgerClient, LedgerEntry
except ImportError:
    from kernel.ledger_client import LedgerClient, LedgerEntry


@dataclass
class TurnMessage:
    """A single turn in the conversation."""
    role: str
    content: str


class SessionManager:
    """Manages session lifecycle, history, and WO sequencing."""

    def __init__(
        self,
        ledger_client: LedgerClient,
        agent_class: str,
        agent_id: str,
    ):
        self._ledger = ledger_client
        self._agent_class = agent_class
        self._agent_id = agent_id
        self._session_id: Optional[str] = None
        self._history: List[TurnMessage] = []
        self._wo_seq: int = 0
        self._turn_count: int = 0

    def start_session(self) -> str:
        """Generate session ID and write SESSION_START to HO2m.
        Idempotent: returns same ID if already started."""
        if self._session_id is not None:
            return self._session_id
        self._session_id = f"SES-{uuid.uuid4().hex[:8].upper()}"
        self._ledger.write(
            LedgerEntry(
                event_type="SESSION_START",
                submission_id=self._session_id,
                decision="STARTED",
                reason="Session started",
                metadata={
                    "provenance": {
                        "agent_id": self._agent_id,
                        "agent_class": self._agent_class,
                        "session_id": self._session_id,
                    },
                },
            )
        )
        return self._session_id

    def end_session(self, turn_count: int, total_cost: Dict[str, Any]) -> None:
        """Write SESSION_END to HO2m with summary."""
        if not self._session_id:
            return
        self._ledger.write(
            LedgerEntry(
                event_type="SESSION_END",
                submission_id=self._session_id,
                decision="ENDED",
                reason="Session ended",
                metadata={
                    "provenance": {
                        "agent_id": self._agent_id,
                        "agent_class": self._agent_class,
                        "session_id": self._session_id,
                    },
                    "turn_count": turn_count,
                    "total_cost": total_cost,
                },
            )
        )

    def add_turn(self, user_message: str, response: str) -> None:
        """Track turn in history and persist it in the ledger."""
        self._history.append(TurnMessage(role="user", content=user_message))
        self._history.append(TurnMessage(role="assistant", content=response))
        self._turn_count += 1
        session_id = self._session_id or "unknown"
        self._ledger.write(
            LedgerEntry(
                event_type="TURN_RECORDED",
                submission_id=session_id,
                decision="RECORDED",
                reason=f"Turn {self._turn_count} recorded",
                metadata={
                    "provenance": {
                        "agent_id": self._agent_id,
                        "agent_class": self._agent_class,
                        "session_id": session_id,
                    },
                    "turn_number": self._turn_count,
                    "user_message": user_message,
                    "response": response,
                },
            )
        )

    @property
    def history(self) -> List[TurnMessage]:
        return list(self._history)

    @property
    def session_id(self) -> Optional[str]:
        return self._session_id

    @property
    def turn_count(self) -> int:
        return self._turn_count

    def next_wo_id(self) -> str:
        """Generate next WO ID: WO-{session_id}-{seq:03d}."""
        self._wo_seq += 1
        return f"WO-{self._session_id}-{self._wo_seq:03d}"
