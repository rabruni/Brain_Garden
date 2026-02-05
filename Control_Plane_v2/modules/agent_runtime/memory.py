"""Memory and context reconstruction for agents.

Reconstructs agent context from ledgers with support for HO2 checkpoint
acceleration.

Example:
    from modules.agent_runtime.memory import AgentMemory

    memory = AgentMemory(tier="ho1")
    context = memory.reconstruct_context(since=datetime(2026, 2, 1))
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class HybridCheckpoint:
    """Hybrid checkpoint: state snapshot + delta references."""

    # State snapshot (key entities)
    installed_packages: Dict[str, str] = field(default_factory=dict)  # pkg_id -> manifest_hash
    registry_hashes: Dict[str, str] = field(default_factory=dict)  # registry_name -> content_hash
    last_entry_hashes: Dict[str, str] = field(default_factory=dict)  # tier -> last_entry_hash

    # Delta references (lightweight)
    ho1_entry_count: int = 0
    ho1_range: Tuple[str, str] = ("", "")  # (first_hash, last_hash)
    checkpoint_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class Context:
    """Reconstructed context for an agent turn."""

    baseline: Optional[HybridCheckpoint] = None
    recent_events: List[Dict] = field(default_factory=list)
    context_as_of: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class AgentMemory:
    """Two-layer memory: HO2 hybrid checkpoints accelerate HO1 replay."""

    def __init__(self, tier: str = "ho1", root: Optional[Path] = None):
        """Initialize memory.

        Args:
            tier: Execution tier
            root: Optional root directory
        """
        self.tier = tier
        self.root = root or self._get_default_root()

    def _get_default_root(self) -> Path:
        """Get default Control Plane root."""
        current = Path(__file__).resolve()
        while current.name != "Control_Plane_v2" and current.parent != current:
            current = current.parent
        if current.name == "Control_Plane_v2":
            return current
        return Path.cwd()

    def _get_ledger_path(self, tier: str) -> Path:
        """Get ledger path for a tier."""
        if tier == "ho3":
            return self.root / "ledger" / "governance.jsonl"
        return self.root / "planes" / tier / "ledger" / "governance.jsonl"

    def _read_ledger_entries(
        self,
        tier: str,
        since_hash: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict]:
        """Read ledger entries, optionally since a specific hash.

        Args:
            tier: Tier to read from
            since_hash: Start reading after this hash
            limit: Maximum entries to return

        Returns:
            List of ledger entries
        """
        path = self._get_ledger_path(tier)
        if not path.exists():
            return []

        entries = []
        found_start = since_hash is None

        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if not found_start:
                    if entry.get("entry_hash") == since_hash:
                        found_start = True
                    continue

                entries.append(entry)
                if len(entries) >= limit:
                    break

        return entries

    def find_checkpoint(
        self,
        tier: str = "ho2",
        before: Optional[datetime] = None,
    ) -> Optional[HybridCheckpoint]:
        """Find latest checkpoint before a timestamp.

        Note: Full checkpoint implementation is Phase 2.
        This is a placeholder that returns None.

        Args:
            tier: Tier to search (typically ho2)
            before: Find checkpoint before this time

        Returns:
            HybridCheckpoint if found, None otherwise
        """
        # Phase 2: Implement checkpoint storage and retrieval
        return None

    def replay_ledger(
        self,
        tier: str,
        since_hash: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict]:
        """Replay ledger entries since a hash.

        Args:
            tier: Tier to replay
            since_hash: Start after this hash
            limit: Maximum entries

        Returns:
            List of entries
        """
        return self._read_ledger_entries(tier, since_hash, limit)

    def reconstruct_context(
        self,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> Context:
        """Reconstruct context from ledgers.

        Args:
            since: Start from this time (uses checkpoint if available)
            limit: Maximum events to include

        Returns:
            Reconstructed Context
        """
        # 1. Try to find a checkpoint (Phase 2)
        checkpoint = self.find_checkpoint(tier="ho2", before=since)

        # 2. Determine starting point
        since_hash = None
        if checkpoint:
            since_hash = checkpoint.last_entry_hashes.get(self.tier)

        # 3. Replay recent events
        recent_events = self.replay_ledger(
            tier=self.tier,
            since_hash=since_hash,
            limit=limit,
        )

        return Context(
            baseline=checkpoint,
            recent_events=recent_events,
            context_as_of=datetime.now(timezone.utc).isoformat(),
        )

    def get_recent_entries(
        self,
        tier: str,
        limit: int = 10,
        event_type: Optional[str] = None,
    ) -> List[Dict]:
        """Get recent entries from a tier's ledger.

        Args:
            tier: Tier to read from
            limit: Maximum entries
            event_type: Optional filter by event type

        Returns:
            List of recent entries (newest last)
        """
        entries = self._read_ledger_entries(tier, limit=1000)

        if event_type:
            entries = [e for e in entries if e.get("event_type") == event_type]

        # Return last N entries
        return entries[-limit:]
