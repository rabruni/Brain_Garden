"""Session management for agent runtime.

Manages agent session lifecycle including ID generation, directory creation,
and ledger initialization.

Example:
    from modules.agent_runtime.session import Session

    with Session(tier="ho1") as session:
        print(session.session_id)  # SES-20260203-abc123
        print(session.ledger_path)  # planes/ho1/sessions/SES-.../ledger/
"""

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from modules.agent_runtime.exceptions import SessionError


def generate_session_id(user: Optional[str] = None) -> str:
    """Generate a unique session ID.

    Format: SES-<YYYYMMDD>-<user>-<random8>
    If no user provided: SES-<YYYYMMDD>-<random8>

    Args:
        user: Optional username from authenticated Identity

    Returns:
        Session ID string (auditable, tied to user if authenticated)
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    random_part = uuid.uuid4().hex[:8]

    if user:
        # Sanitize user (alphanumeric and underscore only)
        safe_user = "".join(c if c.isalnum() or c == "_" else "_" for c in user)[:16]
        return f"SES-{timestamp}-{safe_user}-{random_part}"

    return f"SES-{timestamp}-{random_part}"


class Session:
    """Manage agent session lifecycle."""

    def __init__(
        self,
        tier: str = "ho1",
        session_id: Optional[str] = None,
        work_order_id: Optional[str] = None,
        root: Optional[Path] = None,
    ):
        """Create new session.

        Args:
            tier: Execution tier (ho1, ho2, ho3)
            session_id: Optional pre-generated session ID
            work_order_id: Optional work order reference
            root: Optional root directory (defaults to Control Plane root)
        """
        self._session_id = session_id or generate_session_id()
        self.tier = tier
        self.work_order_id = work_order_id
        self.root = root or self._get_default_root()
        self.turn_count = 0
        self._started = False

    def _get_default_root(self) -> Path:
        """Get default Control Plane root."""
        # Walk up to find Control_Plane_v2
        current = Path(__file__).resolve()
        while current.name != "Control_Plane_v2" and current.parent != current:
            current = current.parent
        if current.name == "Control_Plane_v2":
            return current
        raise SessionError("Could not find Control_Plane_v2 root")

    @property
    def session_id(self) -> str:
        """Get session ID."""
        return self._session_id

    @property
    def session_path(self) -> Path:
        """Get path to session directory."""
        return self.root / "planes" / self.tier / "sessions" / self._session_id

    @property
    def ledger_path(self) -> Path:
        """Get path to session ledger directory."""
        return self.session_path / "ledger"

    @property
    def exec_ledger_path(self) -> Path:
        """Get path to L-EXEC ledger."""
        return self.ledger_path / "exec.jsonl"

    @property
    def evidence_ledger_path(self) -> Path:
        """Get path to L-EVIDENCE ledger."""
        return self.ledger_path / "evidence.jsonl"

    @property
    def tmp_path(self) -> Path:
        """Get path to session temp directory."""
        return self.root / "tmp" / self._session_id

    @property
    def output_path(self) -> Path:
        """Get path to session output directory."""
        return self.root / "output" / self._session_id

    def start(self) -> "Session":
        """Start session, create directories and ledgers.

        Returns:
            Self for chaining
        """
        if self._started:
            raise SessionError(
                f"Session already started: {self._session_id}",
                session_id=self._session_id,
            )

        # Create directories
        self.ledger_path.mkdir(parents=True, exist_ok=True)
        self.tmp_path.mkdir(parents=True, exist_ok=True)
        self.output_path.mkdir(parents=True, exist_ok=True)

        # Initialize ledger files (empty, ready for writes)
        self.exec_ledger_path.touch(exist_ok=True)
        self.evidence_ledger_path.touch(exist_ok=True)

        self._started = True
        return self

    def end(self) -> None:
        """End session, finalize ledgers."""
        self._started = False

    def increment_turn(self) -> int:
        """Increment and return turn number.

        Returns:
            New turn number (1-indexed)
        """
        self.turn_count += 1
        return self.turn_count

    def __enter__(self) -> "Session":
        """Context manager entry."""
        return self.start()

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.end()
