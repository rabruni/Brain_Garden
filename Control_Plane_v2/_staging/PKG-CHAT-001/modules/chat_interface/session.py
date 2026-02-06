"""Chat Session Management.

Manages chat sessions with ledger integration for full audit trails.
Each session has a unique ID and maintains a per-session ledger.

Example:
    from modules.chat_interface.session import ChatSession

    session = ChatSession(tier="ho1")
    session.start()

    # Record a file read
    session.record_read("lib/auth.py", "sha256:abc...")

    # Log a turn
    session.log_turn(
        query="list packages",
        result="Found 5 packages",
        handler="packages.list_all",
        duration_ms=45
    )
"""

import json
import sys
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add parent to path for lib imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from lib.merkle import hash_string, hash_file


@dataclass
class FileRead:
    """Record of a file read for evidence."""
    path: str
    hash: str

    def to_dict(self) -> dict:
        return {"path": self.path, "hash": self.hash}


@dataclass
class SessionEntry:
    """A ledger entry for session logging.

    Simplified entry format that doesn't require LedgerClient.
    """
    event_type: str
    submission_id: str
    decision: str
    reason: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: f"LED-{uuid.uuid4().hex[:8]}")
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    previous_hash: str = ""
    entry_hash: str = ""

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(asdict(self), ensure_ascii=False)

    def compute_hash(self) -> str:
        """Compute entry hash."""
        content = {k: v for k, v in asdict(self).items() if k != "entry_hash"}
        json_str = json.dumps(content, sort_keys=True, ensure_ascii=False)
        return hash_string(json_str)


@dataclass
class ChatSession:
    """Chat session with ledger integration.

    Attributes:
        session_id: Unique session identifier (SES-CHAT-YYYYMMDD-xxxxxxxx)
        tier: Tier name (ho1, ho2, ho3)
        turn_count: Number of turns processed
        root: Control Plane root directory
    """

    tier: str = "ho1"
    session_id: str = field(default_factory=str)
    turn_count: int = 0
    root: Path = field(default_factory=lambda: Path(__file__).resolve().parent.parent.parent)

    # Private state
    _ledger_path: Optional[Path] = field(default=None, repr=False)
    _last_hash: str = field(default="", repr=False)
    _reads: List[FileRead] = field(default_factory=list, repr=False)
    _started: bool = field(default=False, repr=False)
    _prompts_used: List[str] = field(default_factory=list, repr=False)

    def __post_init__(self):
        """Generate session ID if not provided."""
        if not self.session_id:
            self.session_id = self._generate_id()

    def _generate_id(self) -> str:
        """Generate unique session ID."""
        date = datetime.now(timezone.utc).strftime("%Y%m%d")
        rand = uuid.uuid4().hex[:8]
        return f"SES-CHAT-{date}-{rand}"

    def start(self) -> "ChatSession":
        """Initialize session ledger.

        Creates the session ledger directory. Uses a simple file-based
        approach to avoid pristine boundary checks for session paths.

        Returns:
            Self for chaining
        """
        if self._started:
            return self

        self._ledger_path = self._get_ledger_path()
        self._ledger_path.parent.mkdir(parents=True, exist_ok=True)

        self._started = True
        return self

    def _get_ledger_path(self) -> Path:
        """Get path to session ledger file."""
        return (
            self.root / "planes" / self.tier / "sessions"
            / self.session_id / "ledger" / "chat.jsonl"
        )

    def _write_entry(self, entry: SessionEntry) -> str:
        """Write an entry to the session ledger.

        Uses simple file append to avoid pristine boundary checks.
        Maintains hash chaining for integrity.

        Args:
            entry: Entry to write

        Returns:
            Entry ID
        """
        if not self._ledger_path:
            self.start()

        # Set previous hash and compute entry hash
        entry.previous_hash = self._last_hash
        entry.entry_hash = entry.compute_hash()

        # Append to ledger file
        with open(self._ledger_path, "a", encoding="utf-8") as f:
            f.write(entry.to_json() + "\n")

        # Update chain state
        self._last_hash = entry.entry_hash

        return entry.id

    def record_read(self, path: str, file_hash: Optional[str] = None) -> None:
        """Record a file read for evidence.

        Args:
            path: Relative path to file
            file_hash: SHA256 hash (computed if not provided)
        """
        if file_hash is None:
            full_path = self.root / path
            if full_path.exists():
                file_hash = f"sha256:{hash_file(full_path)}"
            else:
                file_hash = "sha256:not_found"

        self._reads.append(FileRead(path=path, hash=file_hash))

    def record_prompt(self, prompt_id: str) -> None:
        """Record a governed prompt used in this turn.

        Args:
            prompt_id: Prompt pack identifier (e.g., PRM-ADMIN-EXPLAIN-001)
        """
        if prompt_id and prompt_id not in self._prompts_used:
            self._prompts_used.append(prompt_id)

    def get_prompts_used(self) -> List[str]:
        """Get list of prompts used in current turn.

        Returns:
            List of prompt IDs used (not yet cleared)
        """
        return list(self._prompts_used)

    def log_turn(
        self,
        query: str,
        result: str,
        handler: str,
        duration_ms: int,
        classification: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Log a turn to the session ledger.

        Args:
            query: Original query string
            result: Handler result
            handler: Handler name that processed the query
            duration_ms: Processing time in milliseconds
            classification: Optional classification details

        Returns:
            Entry ID
        """
        if not self._started:
            self.start()

        self.turn_count += 1

        entry = SessionEntry(
            event_type="CHAT_TURN",
            submission_id=f"{self.session_id}-T{self.turn_count:03d}",
            decision="EXECUTED",
            reason="Query processed successfully",
            metadata={
                "turn_number": self.turn_count,
                # Actual content for full transparency
                "query_text": query,
                "result_text": result,
                # Hashes for integrity verification
                "query_hash": f"sha256:{hash_string(query)}",
                "result_hash": f"sha256:{hash_string(result)}",
                # Execution metadata
                "handler": handler,
                "duration_ms": duration_ms,
                "declared_reads": [r.to_dict() for r in self._reads],
                "classification": classification,
                "prompts_used": list(self._prompts_used),
            }
        )

        entry_id = self._write_entry(entry)

        # Clear reads and prompts for next turn
        self._reads.clear()
        self._prompts_used.clear()

        return entry_id

    def log_event(
        self,
        event_type: str,
        subject: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Log a custom event to the session ledger.

        Args:
            event_type: Event type (e.g., PACKAGE_INSTALLED)
            subject: Event subject (e.g., package ID)
            metadata: Additional metadata

        Returns:
            Entry ID
        """
        if not self._started:
            self.start()

        entry = SessionEntry(
            event_type=event_type,
            submission_id=f"{self.session_id}-{event_type}-{self.turn_count:03d}",
            decision="LOGGED",
            reason=f"Event: {event_type} for {subject}",
            metadata=metadata or {},
        )

        return self._write_entry(entry)

    def get_ledger_path(self) -> Path:
        """Get path to session ledger."""
        return self._get_ledger_path()

    def get_session_root(self) -> Optional[str]:
        """Get Merkle root of session ledger.

        Computes Merkle root from all entry hashes in the session ledger.
        """
        if not self._ledger_path or not self._ledger_path.exists():
            return None

        hashes = []
        with open(self._ledger_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        entry = json.loads(line)
                        if entry.get("entry_hash"):
                            hashes.append(entry["entry_hash"])
                    except json.JSONDecodeError:
                        pass

        if not hashes:
            return None

        # Import here to avoid circular dependency
        from lib.merkle import merkle_root
        return merkle_root(hashes)

    def flush(self) -> None:
        """Flush ledger to disk.

        No-op since we write entries immediately.
        """
        pass

    def __enter__(self) -> "ChatSession":
        """Context manager entry."""
        return self.start()

    def __exit__(self, *args) -> None:
        """Context manager exit - flush ledger."""
        self.flush()


def create_session(tier: str = "ho1") -> ChatSession:
    """Create and start a new chat session.

    Args:
        tier: Tier name (ho1, ho2, ho3)

    Returns:
        Started ChatSession instance
    """
    session = ChatSession(tier=tier)
    session.start()
    return session
