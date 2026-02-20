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

import hashlib
import json
import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
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

        # Gap 4: Idempotency check via artifact_id
        artifact_id = overlay.get("artifact_id")
        if artifact_id:
            existing = self._find_overlay_by_artifact_id(artifact_id)
            if existing is not None:
                existing_meta = existing["metadata"]
                # Check if deactivated
                if existing.get("deactivated", False):
                    # Re-activate via weight update
                    new_weight = overlay.get("weight", overlay.get("salience_weight", 0.0))
                    self.update_overlay_weight(
                        artifact_id=artifact_id,
                        new_weight=new_weight,
                        reason="re-activated via duplicate log_overlay",
                        event_ts=datetime.now(timezone.utc).isoformat(),
                    )
                # Return existing overlay_id (skip duplicate)
                return existing_meta.get("overlay_id", "")

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

        # Gap 2: Structured artifact fields (optional on read, persisted on write)
        structured_keys = [
            "artifact_id", "artifact_type", "labels", "weight", "scope",
            "context_line", "enabled", "expires_at_event_ts",
            "source_signal_ids", "gate_snapshot", "model",
            "prompt_pack_version", "consolidation_event_ts",
        ]
        for key in structured_keys:
            if key in overlay:
                entry_metadata[key] = overlay[key]

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
        as_of_ts: Optional[str] = None,
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
        now = datetime.fromisoformat(as_of_ts) if as_of_ts else datetime.now(timezone.utc)
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

    def read_active_biases(self, as_of_ts: Optional[str] = None) -> List[Dict[str, Any]]:
        """Read active biases for context injection.

        Returns overlays with salience > 0, suitable for injection
        into HO2's assembled context at Step 2b. Applies lifecycle
        resolution: deactivated overlays excluded, latest weight wins,
        expired overlays excluded.

        Args:
            as_of_ts: Optional ISO timestamp for deterministic expiry.
                      If None, uses datetime.now(timezone.utc).

        Returns:
            List of overlay dicts with active biases
        """
        now = datetime.fromisoformat(as_of_ts) if as_of_ts else datetime.now(timezone.utc)
        entries = self._overlays_client.read_all()

        # Phase 1: Collect all events by artifact_id
        # Events without artifact_id are legacy overlays — pass through directly
        legacy = []
        by_artifact: Dict[str, List[Dict[str, Any]]] = {}

        for entry in entries:
            meta = entry.metadata
            etype = entry.event_type
            art_id = meta.get("artifact_id")

            if etype == "HO3_OVERLAY" and not art_id:
                # Legacy overlay (no artifact_id) — include if salience > 0
                if meta.get("salience_weight", 0) > 0:
                    legacy.append(meta)
                continue

            if art_id:
                if art_id not in by_artifact:
                    by_artifact[art_id] = []
                by_artifact[art_id].append({"event_type": etype, "metadata": meta, "timestamp": entry.timestamp})

        # Phase 2: Resolve lifecycle per artifact_id
        result = list(legacy)
        for art_id, events in by_artifact.items():
            # Sort by timestamp to find latest event
            events.sort(key=lambda e: e["timestamp"])

            # Find the original OVERLAY event
            base_overlay = None
            latest_weight = None
            deactivated = False

            for evt in events:
                etype = evt["event_type"]
                meta = evt["metadata"]
                if etype == "HO3_OVERLAY":
                    base_overlay = meta
                elif etype == "HO3_OVERLAY_DEACTIVATED":
                    deactivated = True
                elif etype == "HO3_OVERLAY_WEIGHT_UPDATED":
                    deactivated = False  # weight update re-activates
                    latest_weight = meta.get("new_weight")

            if base_overlay is None:
                continue
            if deactivated:
                continue

            # Check expiry
            expires = base_overlay.get("expires_at_event_ts")
            if expires:
                try:
                    if now >= datetime.fromisoformat(expires):
                        continue
                except (ValueError, TypeError):
                    pass

            # Apply latest weight if updated
            overlay = dict(base_overlay)
            if latest_weight is not None:
                overlay["weight"] = latest_weight
                overlay["salience_weight"] = latest_weight

            # Filter salience > 0
            if overlay.get("salience_weight", 0) <= 0:
                continue

            result.append(overlay)

        return result

    # =======================================================================
    # Overlay Lifecycle (append-only)
    # =======================================================================

    def deactivate_overlay(self, artifact_id: str, reason: str, event_ts: str) -> str:
        """Append HO3_OVERLAY_DEACTIVATED event.

        Does NOT mutate the original overlay. Append-only invariant.
        read_active_biases resolves lifecycle: latest event wins.

        Args:
            artifact_id: The artifact_id of the overlay to deactivate
            reason: Why the overlay is being deactivated
            event_ts: ISO timestamp of the deactivation event

        Returns:
            The artifact_id

        Raises:
            ValueError: If no overlay exists with this artifact_id
        """
        existing = self._find_overlay_by_artifact_id(artifact_id)
        if existing is None:
            raise ValueError(
                f"No overlay found with artifact_id={artifact_id}. "
                "Cannot deactivate a nonexistent overlay."
            )

        entry = LedgerEntry(
            event_type="HO3_OVERLAY_DEACTIVATED",
            submission_id=artifact_id,
            decision="DEACTIVATED",
            reason=reason,
            metadata={
                "artifact_id": artifact_id,
                "reason": reason,
                "event_ts": event_ts,
            },
        )
        self._overlays_client.write(entry)
        return artifact_id

    def update_overlay_weight(self, artifact_id: str, new_weight: float, reason: str, event_ts: str) -> str:
        """Append HO3_OVERLAY_WEIGHT_UPDATED event.

        Does NOT mutate the original overlay. Append-only invariant.
        read_active_biases uses latest weight.

        Args:
            artifact_id: The artifact_id of the overlay to update
            new_weight: The new weight value
            reason: Why the weight is being updated
            event_ts: ISO timestamp of the update event

        Returns:
            The artifact_id

        Raises:
            ValueError: If no overlay exists with this artifact_id
        """
        existing = self._find_overlay_by_artifact_id(artifact_id)
        if existing is None:
            raise ValueError(
                f"No overlay found with artifact_id={artifact_id}. "
                "Cannot update weight of a nonexistent overlay."
            )

        entry = LedgerEntry(
            event_type="HO3_OVERLAY_WEIGHT_UPDATED",
            submission_id=artifact_id,
            decision="WEIGHT_UPDATED",
            reason=reason,
            metadata={
                "artifact_id": artifact_id,
                "new_weight": new_weight,
                "reason": reason,
                "event_ts": event_ts,
            },
        )
        self._overlays_client.write(entry)
        return artifact_id

    def _find_overlay_by_artifact_id(self, artifact_id: str) -> Optional[Dict[str, Any]]:
        """Find an overlay by artifact_id, with lifecycle resolution.

        Scans all overlay events for the given artifact_id and resolves
        the lifecycle state (active, deactivated, weight-updated).

        Args:
            artifact_id: The artifact_id to search for

        Returns:
            Dict with 'metadata' and 'deactivated' keys, or None if not found
        """
        entries = self._overlays_client.read_all()
        base_overlay = None
        deactivated = False

        for entry in entries:
            meta = entry.metadata
            if meta.get("artifact_id") != artifact_id:
                continue
            etype = entry.event_type
            if etype == "HO3_OVERLAY":
                base_overlay = meta
                deactivated = False
            elif etype == "HO3_OVERLAY_DEACTIVATED":
                deactivated = True
            elif etype == "HO3_OVERLAY_WEIGHT_UPDATED":
                deactivated = False

        if base_overlay is None:
            return None
        return {"metadata": base_overlay, "deactivated": deactivated}

    @staticmethod
    def compute_artifact_id(
        source_signal_ids: List[str],
        gate_window_key: str,
        model: str,
        prompt_pack_version: str,
    ) -> str:
        """Compute deterministic artifact_id from consolidation inputs.

        Same inputs always produce the same ID. source_signal_ids are
        sorted before hashing to ensure order-independence.

        Args:
            source_signal_ids: Signal IDs that contributed
            gate_window_key: Gate window identifier (e.g., "2026-W07")
            model: LLM model used for consolidation
            prompt_pack_version: Prompt pack version used

        Returns:
            Deterministic artifact_id in format "ART-<12 hex chars>"
        """
        canonical = "|".join(sorted(source_signal_ids)) + "|" + gate_window_key + "|" + model + "|" + prompt_pack_version
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]
        return f"ART-{digest}"

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

    def _is_consolidated(self, signal_id: str, as_of_ts: Optional[str] = None) -> bool:
        """Check if signal was already consolidated within the gate window.

        Reads overlays.jsonl for an overlay with matching signal_id
        whose window_end is within the last gate_window_hours.

        Args:
            signal_id: Signal to check
            as_of_ts: Optional ISO timestamp for deterministic check.
                      If None, uses datetime.now(timezone.utc).

        Returns:
            True if consolidated within window (gate stays closed)
        """
        overlays = self.read_overlays(signal_id=signal_id, active_only=False)
        if not overlays:
            return False

        now = datetime.fromisoformat(as_of_ts) if as_of_ts else datetime.now(timezone.utc)
        window_cutoff = now - timedelta(hours=self.config.gate_window_hours)

        for overlay in overlays:
            window_end_str = overlay.get("window_end", "")
            if not window_end_str:
                continue
            try:
                window_end = datetime.fromisoformat(window_end_str)
                if window_cutoff <= window_end <= now:
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
    "ARTIFACT_TYPES",
]

# Closed vocabulary for artifact types
ARTIFACT_TYPES = ("topic_affinity", "interaction_style", "task_pattern", "constraint")
