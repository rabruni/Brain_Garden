"""HO3 Memory Store -- addressable data plane for signal-based memory.

NOT a cognitive process. Two operations: READ and LOG.
No LLM calls. No background execution. Always addressable, never always-executing.

Usage:
    from ho3_memory import HO3Memory, HO3MemoryConfig

    config = HO3MemoryConfig(
        memory_dir=plane_root / "HOT" / "memory",
        gate_count_threshold=5,
        gate_session_threshold=3,
    )
    mem = HO3Memory(plane_root=plane_root, config=config)

    # LOG a signal event
    mem.log_signal("intent:tool_query", "SES-001", "EVT-abc123")

    # READ accumulated signals
    accumulators = mem.read_signals(signal_id="intent:tool_query")

    # Check bistable gate
    result = mem.check_gate("intent:tool_query")
    if result.crossed:
        # Signal ready for consolidation
        ...
"""

import json
import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kernel.ledger_client import LedgerClient, LedgerEntry


# ---------------------------------------------------------------------------
# Data Model
# ---------------------------------------------------------------------------

@dataclass
class HO3MemoryConfig:
    """Configuration for HO3 memory store.

    All thresholds are config-driven. No magic constants.
    """
    memory_dir: Path                    # HOT/memory/ under plane_root
    gate_count_threshold: int = 5       # count >= N
    gate_session_threshold: int = 3     # sessions >= M
    gate_window_hours: int = 168        # 7 days -- window for not_consolidated check
    decay_half_life_hours: float = 336  # 14 days -- time-based signal decay
    enabled: bool = False               # MVP default: OFF (opt-in)


@dataclass
class SignalAccumulator:
    """Accumulated signal state -- computed on READ, never stored.

    Derived by scanning signals.jsonl and grouping by signal_id.
    """
    signal_id: str
    count: int                  # total events for this signal_id
    last_seen: str              # ISO timestamp of most recent event
    session_ids: List[str]      # unique session IDs that contributed
    event_ids: List[str]        # all event IDs (for source references)
    decay: float                # time-based decay factor (0.0 to 1.0)


@dataclass
class GateResult:
    """Result of bistable gate check.

    Pure data -- no side effects. The gate is a pure function of
    accumulated state and config thresholds.
    """
    signal_id: str
    crossed: bool
    count: int = 0
    session_count: int = 0
    already_consolidated: bool = False
    reason: str = ""


# ---------------------------------------------------------------------------
# HO3 Memory Store
# ---------------------------------------------------------------------------

class HO3Memory:
    """HO3 memory plane -- addressable data store.

    NOT a cognitive process. Two operations: READ and LOG.
    No LLM calls. No background execution.
    """

    def __init__(self, plane_root: Path, config: HO3MemoryConfig):
        self._plane_root = plane_root
        self.config = config

        # Ensure memory directory exists
        self.config.memory_dir.mkdir(parents=True, exist_ok=True)

        # Signal events ledger (append-only)
        self._signals_path = self.config.memory_dir / "signals.jsonl"
        self._signals_client = LedgerClient(
            ledger_path=self._signals_path,
            enable_index=False,
            rotate_bytes=0,
            rotate_daily=False,
        )

        # Overlay entries ledger (append-only)
        self._overlays_path = self.config.memory_dir / "overlays.jsonl"
        self._overlays_client = LedgerClient(
            ledger_path=self._overlays_path,
            enable_index=False,
            rotate_bytes=0,
            rotate_daily=False,
        )

    # =======================================================================
    # HO3.LOG (synchronous signal/event append)
    # =======================================================================

    def log_signal(
        self,
        signal_id: str,
        session_id: str,
        event_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Append a signal event to signals.jsonl.

        Each call creates one immutable event line. Accumulated state
        (count, session_ids, last_seen) is computed by READ, not stored.

        Args:
            signal_id: Signal identifier (e.g., "intent:tool_query")
            session_id: Session that generated the signal
            event_id: Unique event identifier (e.g., "EVT-abc12345")
            metadata: Optional additional metadata

        Returns:
            The event_id that was logged
        """
        entry_metadata = {
            "signal_id": signal_id,
            "session_id_signal": session_id,
            "ho3_event_id": event_id,
        }
        if metadata:
            entry_metadata.update(metadata)

        entry = LedgerEntry(
            event_type="HO3_SIGNAL",
            submission_id=signal_id,
            decision="LOGGED",
            reason=f"Signal event for {signal_id}",
            metadata=entry_metadata,
        )
        self._signals_client.write(entry)
        return event_id

    def log_overlay(self, overlay: Dict[str, Any]) -> str:
        """Append an overlay entry to overlays.jsonl.

        Overlays reference source_event_ids (immutable provenance chain
        back to signals.jsonl). Empty source_event_ids is FORBIDDEN.

        Args:
            overlay: Overlay dict with required keys:
                - signal_id: str
                - salience_weight: float
                - source_event_ids: list[str] (MUST be non-empty)
                - content: dict
                - window_start: str (ISO timestamp)
                - window_end: str (ISO timestamp)

        Returns:
            Generated overlay_id (e.g., "OVL-abc12345")

        Raises:
            ValueError: If source_event_ids is empty or missing
        """
        source_ids = overlay.get("source_event_ids", [])
        if not source_ids:
            raise ValueError(
                "source_event_ids must be non-empty. "
                "Every overlay must trace back to signal events. "
                "Unauditable overlays are forbidden."
            )

        overlay_id = f"OVL-{uuid.uuid4().hex[:8]}"

        entry_metadata = {
            "overlay_id": overlay_id,
            "signal_id": overlay.get("signal_id", ""),
            "salience_weight": overlay.get("salience_weight", 0.0),
            "decay_modifier": overlay.get("decay_modifier", 1.0),
            "source_event_ids": source_ids,
            "content": overlay.get("content", {}),
            "window_start": overlay.get("window_start", ""),
            "window_end": overlay.get("window_end", ""),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        entry = LedgerEntry(
            event_type="HO3_OVERLAY",
            submission_id=overlay.get("signal_id", overlay_id),
            decision="CONSOLIDATED",
            reason=f"Overlay for signal {overlay.get('signal_id', 'unknown')}",
            metadata=entry_metadata,
        )
        self._overlays_client.write(entry)
        return overlay_id

    # =======================================================================
    # HO3.READ (synchronous structured lookup)
    # =======================================================================

    def read_signals(
        self,
        signal_id: Optional[str] = None,
        min_count: int = 0,
    ) -> List[SignalAccumulator]:
        """Read accumulated signal state.

        Scans signals.jsonl, groups by signal_id, computes count,
        session_ids, last_seen, event_ids, and decay. Nothing is
        pre-aggregated -- all state derived on read.

        Args:
            signal_id: Filter to a specific signal_id (None = all)
            min_count: Only return signals with count >= min_count

        Returns:
            List of SignalAccumulator instances
        """
        entries = self._signals_client.read_all()

        # Group by signal_id
        groups: Dict[str, Dict[str, Any]] = {}
        for entry in entries:
            meta = entry.metadata
            sid = meta.get("signal_id", "")
            if not sid:
                continue
            if signal_id is not None and sid != signal_id:
                continue

            if sid not in groups:
                groups[sid] = {
                    "signal_id": sid,
                    "count": 0,
                    "last_seen": "",
                    "session_ids": set(),
                    "event_ids": [],
                }

            g = groups[sid]
            g["count"] += 1
            g["session_ids"].add(meta.get("session_id_signal", ""))
            g["event_ids"].append(meta.get("ho3_event_id", ""))

            # Track last_seen as the most recent timestamp
            ts = entry.timestamp
            if not g["last_seen"] or ts > g["last_seen"]:
                g["last_seen"] = ts

        # Convert to SignalAccumulator with decay
        now = datetime.now(timezone.utc)
        result = []
        for sid, g in groups.items():
            if g["count"] < min_count:
                continue

            # Compute decay: exp(-ln(2) / half_life * hours_since_last_seen)
            decay = 1.0
            if g["last_seen"] and self.config.decay_half_life_hours > 0:
                try:
                    last_dt = datetime.fromisoformat(g["last_seen"])
                    hours_since = (now - last_dt).total_seconds() / 3600.0
                    if hours_since > 0:
                        lam = math.log(2) / self.config.decay_half_life_hours
                        decay = math.exp(-lam * hours_since)
                except (ValueError, OverflowError):
                    decay = 1.0

            result.append(SignalAccumulator(
                signal_id=g["signal_id"],
                count=g["count"],
                last_seen=g["last_seen"],
                session_ids=sorted(g["session_ids"]),
                event_ids=g["event_ids"],
                decay=decay,
            ))

        return result

    def read_overlays(
        self,
        signal_id: Optional[str] = None,
        active_only: bool = True,
    ) -> List[Dict[str, Any]]:
        """Read overlay entries.

        Args:
            signal_id: Filter to a specific signal_id (None = all)
            active_only: If True, only return overlays with salience > 0

        Returns:
            List of overlay dicts
        """
        entries = self._overlays_client.read_all()
        result = []
        for entry in entries:
            meta = entry.metadata
            if signal_id is not None and meta.get("signal_id") != signal_id:
                continue
            if active_only and meta.get("salience_weight", 0) <= 0:
                continue
            result.append(meta)
        return result

    def read_active_biases(self) -> List[Dict[str, Any]]:
        """Read active biases for context injection.

        Returns overlays with salience > 0, suitable for injection
        into HO2's assembled context at Step 2b.

        Returns:
            List of overlay dicts with active biases
        """
        return self.read_overlays(active_only=True)

    # =======================================================================
    # Bistable Gate
    # =======================================================================

    def check_gate(self, signal_id: str) -> GateResult:
        """Check the bistable consolidation gate for a signal.

        Pure function. No LLM calls. No side effects.

        Three conditions must ALL be true for crossed=True:
        1. accumulator.count >= config.gate_count_threshold
        2. len(accumulator.session_ids) >= config.gate_session_threshold
        3. not_consolidated(signal_id, window)

        Args:
            signal_id: Signal to check

        Returns:
            GateResult with crossed status and diagnostic info
        """
        accumulators = self.read_signals(signal_id=signal_id)

        if not accumulators:
            return GateResult(
                signal_id=signal_id,
                crossed=False,
                reason="No signal events found",
            )

        acc = accumulators[0]

        # Check count threshold
        if acc.count < self.config.gate_count_threshold:
            return GateResult(
                signal_id=signal_id,
                crossed=False,
                count=acc.count,
                session_count=len(acc.session_ids),
                reason=f"Count {acc.count} < threshold {self.config.gate_count_threshold}",
            )

        # Check session threshold
        if len(acc.session_ids) < self.config.gate_session_threshold:
            return GateResult(
                signal_id=signal_id,
                crossed=False,
                count=acc.count,
                session_count=len(acc.session_ids),
                reason=f"Sessions {len(acc.session_ids)} < threshold {self.config.gate_session_threshold}",
            )

        # Check not_consolidated
        already = self._is_consolidated(signal_id)
        if already:
            return GateResult(
                signal_id=signal_id,
                crossed=False,
                count=acc.count,
                session_count=len(acc.session_ids),
                already_consolidated=True,
                reason="Already consolidated within gate window",
            )

        return GateResult(
            signal_id=signal_id,
            crossed=True,
            count=acc.count,
            session_count=len(acc.session_ids),
            reason="All thresholds met, not consolidated",
        )

    def _is_consolidated(self, signal_id: str) -> bool:
        """Check if signal was already consolidated within the gate window.

        Reads overlays.jsonl for an overlay with matching signal_id
        whose window_end is within the last gate_window_hours.

        Args:
            signal_id: Signal to check

        Returns:
            True if consolidated within window (gate stays closed)
        """
        overlays = self.read_overlays(signal_id=signal_id, active_only=False)
        if not overlays:
            return False

        now = datetime.now(timezone.utc)
        window_cutoff = now - __import__("datetime").timedelta(
            hours=self.config.gate_window_hours
        )

        for overlay in overlays:
            window_end_str = overlay.get("window_end", "")
            if not window_end_str:
                continue
            try:
                window_end = datetime.fromisoformat(window_end_str)
                if window_end >= window_cutoff:
                    return True
            except (ValueError, TypeError):
                continue

        return False


# ---------------------------------------------------------------------------
# Public exports
# ---------------------------------------------------------------------------

__all__ = [
    "HO3Memory",
    "HO3MemoryConfig",
    "SignalAccumulator",
    "GateResult",
]
