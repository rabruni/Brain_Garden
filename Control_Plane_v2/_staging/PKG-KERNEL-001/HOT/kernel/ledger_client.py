"""Ledger Client for Synaptic Manager integration.

Provides append-only ledger writes for governance decisions with
cryptographic hash chaining for tamper detection (SPEC-025), plus
rotation, batching, segment Merkle rollups, optional offset indexing,
and parallel verification to keep the ledger fast as it grows.

Each entry contains:
- previous_hash: Hash of prior entry (empty for first)
- entry_hash: Hash of this entry's content

Usage:
    from kernel.ledger_client import LedgerClient, LedgerEntry

    client = LedgerClient()
    entry = LedgerEntry(
        event_type="governance_decision",
        submission_id="SUB-001",
        decision="APPROVED",
        reason="All inspection criteria met.",
        prompts_used=["PROMPT-001", "PROMPT-002"],
    )
    client.write(entry)

    # Verify chain integrity
    valid, issues = client.verify_chain()
"""

import json
import uuid
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, DefaultDict, Protocol

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kernel.merkle import hash_string, merkle_root


@dataclass
class TierContext:
    """Context for tier-aware ledger stamping.

    Attached to LedgerClient to automatically stamp entries with tier metadata.
    """
    tier: str
    plane_root: Path
    work_order_id: Optional[str] = None
    session_id: Optional[str] = None

    def to_metadata(self) -> Dict[str, Any]:
        """Convert to metadata dict for entry stamping."""
        meta = {
            "_tier": self.tier,
            "_plane_root": str(self.plane_root),
        }
        if self.work_order_id:
            meta["_work_order_id"] = self.work_order_id
        if self.session_id:
            meta["_session_id"] = self.session_id
        return meta


# Default ledger location
DEFAULT_LEDGER_PATH = Path(__file__).resolve().parent.parent / "ledger" / "governance.jsonl"
# Note: Index paths are now computed per-instance in LedgerClient.__init__
# to support multi-ledger isolation (tier-agnostic capability)

# Rotation / batching defaults
DEFAULT_ROTATE_BYTES = 256 * 1024 * 1024  # 256 MB
DEFAULT_ROTATE_DAILY = True
DEFAULT_BATCH_SIZE = 1  # legacy behavior (no buffering)
DEFAULT_BATCH_INTERVAL_SEC = 0.0  # time-based flush disabled by default
DEFAULT_VERIFY_WORKERS = 4


def _compute_entry_hash(entry_dict: dict) -> str:
    """Compute hash of entry content.

    Args:
        entry_dict: Entry as dict (entry_hash excluded from computation)

    Returns:
        SHA256 hash of JSON-serialized content
    """
    # Create copy without entry_hash (it's computed, not input)
    content = {k: v for k, v in entry_dict.items() if k != "entry_hash"}
    # Sort keys for deterministic hashing
    json_str = json.dumps(content, sort_keys=True, ensure_ascii=False)
    return hash_string(json_str)


@dataclass
class LedgerEntry:
    """Immutable ledger record with hash chaining (SPEC-025)."""

    event_type: str
    submission_id: str
    decision: str
    reason: str
    prompts_used: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: f"LED-{uuid.uuid4().hex[:8]}")
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # Chaining fields (SPEC-025)
    previous_hash: str = ""
    entry_hash: str = ""

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> "LedgerEntry":
        """Deserialize from JSON string."""
        data = json.loads(json_str)
        return cls(**data)


@dataclass
class SegmentMeta:
    """Metadata for a rotated ledger segment."""

    segment: str
    count: int
    bytes: int
    first_timestamp: str
    last_timestamp: str
    first_entry_hash: str
    last_entry_hash: str
    merkle_root: str


class LedgerProtocol(Protocol):
    """Interface for pluggable ledger backends."""

    def write(self, entry: LedgerEntry) -> str:
        ...

    def flush(self) -> None:
        ...

    def read_by_submission(self, submission_id: str) -> List[LedgerEntry]:
        ...

    def verify_chain(self) -> Tuple[bool, List[str]]:
        ...


class LedgerClient:
    """Client for Synaptic Manager ledger writes.

    Provides append-only writes to an immutable ledger with
    cryptographic hash chaining for tamper detection. Optional rotation,
    batching, indices, and parallel verification improve scalability.
    """

    def __init__(
        self,
        ledger_path: Optional[Path] = None,
        rotate_bytes: int = DEFAULT_ROTATE_BYTES,
        rotate_daily: bool = DEFAULT_ROTATE_DAILY,
        batch_size: int = DEFAULT_BATCH_SIZE,
        batch_interval_sec: float = DEFAULT_BATCH_INTERVAL_SEC,
        enable_index: bool = True,
        tier_context: Optional[TierContext] = None,
    ):
        """Initialize ledger client.

        Args:
            ledger_path: Path to ledger file. Defaults to ledger/governance.jsonl
            rotate_bytes: rotate when active segment exceeds this many bytes (0 disables)
            rotate_daily: rotate when UTC day changes
            batch_size: buffer entries before flush (1 keeps legacy behavior)
            batch_interval_sec: max seconds to hold a buffer (0 disables)
            enable_index: write per-segment submission offsets and metadata
            tier_context: Optional tier context for entry stamping
        """
        self.ledger_path = ledger_path or DEFAULT_LEDGER_PATH
        self.tier_context = tier_context
        self.rotate_bytes = rotate_bytes
        self.rotate_daily = rotate_daily
        self.batch_size = max(1, batch_size)
        self.batch_interval_sec = batch_interval_sec
        self.enable_index = enable_index

        # Index paths are instance-relative for multi-ledger isolation
        self.index_dir = self.ledger_path.parent / "idx"
        self.segment_index_path = self.ledger_path.parent / "index.jsonl"

        # Runtime state
        self._buffer: List[LedgerEntry] = []
        self._buffer_bytes: int = 0
        self._last_flush_time = time.time()
        self._segment_hashes: List[str] = []
        self._segment_count: int = 0
        self._segment_bytes: int = 0
        self._current_segment_path: Optional[Path] = None
        self._last_hash: str = ""
        self._last_timestamp: str = ""
        self._first_timestamp_segment: str = ""
        self._current_offsets: DefaultDict[str, List[Tuple[int, int]]] = defaultdict(list)

        self._ensure_ledger_exists()
        self._init_state()

    def _ensure_ledger_exists(self) -> None:
        """Ensure ledger directory and file exist."""
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.ledger_path.exists():
            self.ledger_path.touch()
        if self.enable_index:
            self.index_dir.mkdir(parents=True, exist_ok=True)
            self.segment_index_path.touch(exist_ok=True)

    # ------------------------------------------------------------------
    # Initialization / segment state
    # ------------------------------------------------------------------
    def _list_segments(self) -> List[Path]:
        """List ledger segments sorted by name (legacy base file included)."""
        parent = self.ledger_path.parent
        segments = []
        # Current base file
        if self.ledger_path.exists():
            segments.append(self.ledger_path)
        # Rotated segments
        segments.extend(sorted(parent.glob(self.ledger_path.stem + "-*.jsonl")))
        # Deduplicate
        segments = sorted(set(segments))
        return segments

    def _scan_last_entry(self, path: Path) -> Tuple[str, str]:
        """Return (last_entry_hash, last_timestamp) for a segment."""
        if not path.exists():
            return ("", "")
        last_line = ""
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    last_line = line
        if not last_line:
            return ("", "")
        try:
            entry = json.loads(last_line)
            return (entry.get("entry_hash", ""), entry.get("timestamp", ""))
        except json.JSONDecodeError:
            return ("", "")

    def _init_state(self) -> None:
        """Initialize state from existing ledger segments."""
        segments = self._list_segments()
        if segments:
            self._current_segment_path = segments[-1]
            self._last_hash, self._last_timestamp = self._scan_last_entry(self._current_segment_path)
            self._segment_bytes = self._current_segment_path.stat().st_size if self._current_segment_path.exists() else 0
        else:
            self._current_segment_path = self.ledger_path
            self._last_hash = ""
            self._last_timestamp = ""
            self._segment_bytes = 0

    def _segment_name(self) -> str:
        """Compute new segment filename based on current UTC time."""
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        return f"{self.ledger_path.stem}-{ts}.jsonl"

    def _needs_rotation(self) -> bool:
        """Decide if rotation is required."""
        # Size-based
        if self.rotate_bytes and self._segment_bytes >= self.rotate_bytes:
            return True
        # Day boundary based on last timestamp
        if self.rotate_daily and self._last_timestamp:
            try:
                last_day = datetime.fromisoformat(self._last_timestamp).date()
                now_day = datetime.now(timezone.utc).date()
                if now_day > last_day:
                    return True
            except Exception:
                pass
        return False

    def _write_segment_meta(
        self,
        segment: str,
        count: int,
        bytes_: int,
        first_ts: str,
        last_ts: str,
        first_hash: str,
        last_hash: str,
        merkle: str,
    ):
        """Append segment metadata to index file."""
        if not self.enable_index:
            return
        meta = SegmentMeta(
            segment=segment,
            count=count,
            bytes=bytes_,
            first_timestamp=first_ts,
            last_timestamp=last_ts,
            first_entry_hash=first_hash,
            last_entry_hash=last_hash,
            merkle_root=merkle,
        )
        with open(self.segment_index_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(meta)) + "\n")

    def _write_submission_index(self, filename: str, offsets: DefaultDict[str, List[Tuple[int, int]]]):
        """Persist submission -> offsets index for a segment."""
        if not self.enable_index:
            return
        path = self.index_dir / filename
        data = {k: v for k, v in offsets.items()}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)

    def _segment_meta_exists(self, segment: str) -> bool:
        """Check if metadata already recorded for a segment."""
        if not self.segment_index_path.exists():
            return False
        with open(self.segment_index_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    if data.get("segment") == segment:
                        return True
                except Exception:
                    continue
        return False

    def _start_new_segment(self):
        """Finalize current segment (if any) and start a fresh one."""
        # Finalize old segment
        if self._segment_count > 0:
            self._write_segment_meta(
                segment=self._current_segment_path.name,
                count=self._segment_count,
                bytes_=self._segment_bytes,
                first_ts=self._first_timestamp_segment,
                last_ts=self._last_timestamp,
                first_hash=self._segment_hashes[0] if self._segment_hashes else "",
                last_hash=self._segment_hashes[-1] if self._segment_hashes else "",
                merkle=merkle_root(self._segment_hashes),
            )
            self._write_submission_index(self._current_segment_path.stem + ".json", self._current_offsets)

        # Reset segment tracking
        self._segment_hashes = []
        self._segment_count = 0
        self._segment_bytes = 0
        self._current_offsets = defaultdict(list)
        self._first_timestamp_segment = ""

        # Allocate new segment file
        new_path = self.ledger_path.parent / self._segment_name()
        new_path.touch()
        self._current_segment_path = new_path

    # ------------------------------------------------------------------

    def _get_last_entry_hash(self) -> str:
        """Get entry_hash of last entry in ledger.

        Returns:
            Hash of last entry, or "" if ledger is empty or has legacy entries
        """
        return self._last_hash

    def write(self, entry: LedgerEntry) -> str:
        """Append entry to ledger with hash chaining.

        If tier_context is set, automatically stamps entries with tier metadata.

        Args:
            entry: LedgerEntry to write

        Returns:
            Entry ID
        """
        # Stamp tier context into metadata if available
        if self.tier_context:
            tier_meta = self.tier_context.to_metadata()
            for key, value in tier_meta.items():
                entry.metadata.setdefault(key, value)

        self._buffer.append(entry)
        self._buffer_bytes += len(entry.to_json()) + 1

        now = time.time()
        should_flush = len(self._buffer) >= self.batch_size
        if self.batch_interval_sec > 0 and (now - self._last_flush_time) >= self.batch_interval_sec:
            should_flush = True

        if should_flush:
            self.flush()

        return entry.id

    def flush(self) -> None:
        """Flush buffered entries to disk, handling rotation and indexing."""
        if not self._buffer:
            return

        # Rotate if needed before writing buffered entries
        if self._needs_rotation():
            self._start_new_segment()

        path = self._current_segment_path or self.ledger_path
        # Lazy import to avoid circular dependency with pristine.py
        from kernel.pristine import assert_append_only
        assert_append_only(path)
        with open(path, "a", encoding="utf-8") as f:
            for entry in self._buffer:
                entry.previous_hash = self._last_hash
                entry_dict = asdict(entry)
                entry.entry_hash = _compute_entry_hash(entry_dict)

                line = entry.to_json()
                offset = f.tell()
                f.write(line + "\n")

                # Update chain state
                self._last_hash = entry.entry_hash
                self._last_timestamp = entry.timestamp
                self._segment_hashes.append(entry.entry_hash)
                self._segment_count += 1
                self._segment_bytes += len(line) + 1
                if not self._first_timestamp_segment:
                    self._first_timestamp_segment = entry.timestamp

                if self.enable_index:
                    self._current_offsets[entry.submission_id].append((offset, len(line) + 1))

        self._buffer.clear()
        self._buffer_bytes = 0
        self._last_flush_time = time.time()

    def __del__(self):
        """Best-effort flush on object destruction."""
        try:
            self.flush()
            if self.enable_index and self._segment_count > 0:
                # If meta not yet recorded for this active segment, write it now
                seg_name = (self._current_segment_path or self.ledger_path).name
                if not self._segment_meta_exists(seg_name):
                    self._write_segment_meta(
                        segment=seg_name,
                        count=self._segment_count,
                        bytes_=self._segment_bytes,
                        first_ts=self._first_timestamp_segment,
                        last_ts=self._last_timestamp,
                        first_hash=self._segment_hashes[0] if self._segment_hashes else "",
                        last_hash=self._segment_hashes[-1] if self._segment_hashes else "",
                        merkle=merkle_root(self._segment_hashes),
                    )
                    self._write_submission_index((self._current_segment_path or self.ledger_path).stem + ".json", self._current_offsets)
        except Exception:
            # Avoid raising during GC
            pass

    def read_all(self) -> List[LedgerEntry]:
        """Read all ledger entries.

        Returns:
            List of all entries in order
        """
        entries: List[LedgerEntry] = []
        segments = self._list_segments()
        for seg in segments:
            with open(seg, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entries.append(LedgerEntry.from_json(line))
                        except (json.JSONDecodeError, TypeError):
                            # Skip malformed entries
                            pass
        return entries

    def read_by_submission(self, submission_id: str) -> List[LedgerEntry]:
        """Read entries for a specific submission.

        Args:
            submission_id: Submission ID to filter by

        Returns:
            List of matching entries
        """
        return self.read_by_submission_fast(submission_id)

    def _load_submission_index(self, segment_stem: str) -> Optional[Dict[str, List[Tuple[int, int]]]]:
        """Load per-segment submission offset index if present."""
        path = self.index_dir / f"{segment_stem}.json"
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {k: [tuple(x) for x in v] for k, v in data.items()}
        except Exception:
            return None

    def read_by_submission_fast(self, submission_id: str) -> List[LedgerEntry]:
        """Read entries for a submission using per-segment offset indices when available."""
        results: List[LedgerEntry] = []
        segments = self._list_segments()
        for seg in segments:
            stem = seg.stem
            index = self._load_submission_index(stem)
            if index and submission_id in index:
                offsets = index[submission_id]
                with open(seg, "r", encoding="utf-8") as f:
                    for offset, length in offsets:
                        f.seek(offset)
                        line = f.read(length)
                        if not line:
                            continue
                        try:
                            results.append(LedgerEntry.from_json(line.strip()))
                        except Exception:
                            continue
            else:
                # Fallback scan for this segment only
                with open(seg, "r", encoding="utf-8") as f:
                    for line in f:
                        if not line.strip():
                            continue
                        try:
                            entry = LedgerEntry.from_json(line.strip())
                            if entry.submission_id == submission_id:
                                results.append(entry)
                        except Exception:
                            continue
        return results

    def count(self) -> int:
        """Count total entries in ledger."""
        return len(self.read_all())

    def verify_chain(self) -> Tuple[bool, List[str]]:
        """Verify ledger chain integrity.

        Checks:
        1. Each entry's entry_hash matches computed hash
        2. Each entry's previous_hash matches prior entry's entry_hash

        Returns:
            Tuple of (is_valid, list_of_issues)
            - is_valid: True if no FAIL issues
            - issues: List of WARN (legacy) or FAIL (tampered) messages
        """
        issues = []
        entries = self.read_all()

        prev_hash = ""
        for i, entry in enumerate(entries):
            # Skip legacy entries (no hash) - warn only
            if not entry.entry_hash:
                issues.append(f"WARN: Entry {entry.id} is legacy (no entry_hash)")
                prev_hash = ""  # Reset chain for legacy entries
                continue

            # Verify entry_hash matches computed hash
            entry_dict = asdict(entry)
            expected_hash = _compute_entry_hash(entry_dict)
            if entry.entry_hash != expected_hash:
                issues.append(f"FAIL: Entry {entry.id} content tampered (hash mismatch)")

            # Verify chain link (previous_hash matches prior entry's hash)
            if entry.previous_hash != prev_hash:
                issues.append(f"FAIL: Entry {entry.id} chain broken (previous_hash mismatch)")

            prev_hash = entry.entry_hash

        is_valid = not any(issue.startswith("FAIL") for issue in issues)
        return (is_valid, issues)

    def verify_chain_parallel(self, workers: int = DEFAULT_VERIFY_WORKERS) -> Tuple[bool, List[str]]:
        """Verify ledger integrity using per-segment parallelism."""
        segments = self._list_segments()
        if not segments:
            return True, []

        issues: List[str] = []
        results: Dict[str, Dict[str, Any]] = {}

        def verify_segment(path: Path) -> Dict[str, Any]:
            seg_issues = []
            prev_hash_local = ""
            hashes = []
            first_hash = ""
            last_hash = ""
            count = 0
            first_ts = ""
            last_ts = ""

            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = LedgerEntry.from_json(line)
                    except Exception:
                        seg_issues.append(f"FAIL: Malformed entry in {path.name}")
                        continue

                    if entry.entry_hash:
                        expected = _compute_entry_hash(asdict(entry))
                        if entry.entry_hash != expected:
                            seg_issues.append(f"FAIL: Hash mismatch {entry.id} in {path.name}")

                        if prev_hash_local and entry.previous_hash != prev_hash_local:
                            seg_issues.append(f"FAIL: Chain break {entry.id} in {path.name}")

                        prev_hash_local = entry.entry_hash
                        hashes.append(entry.entry_hash)
                        if not first_hash:
                            first_hash = entry.entry_hash
                        last_hash = entry.entry_hash
                    else:
                        seg_issues.append(f"WARN: Legacy entry {entry.id} lacks entry_hash in {path.name}")
                        prev_hash_local = ""
                        hashes = []

                    if not first_ts:
                        first_ts = entry.timestamp
                    last_ts = entry.timestamp
                    count += 1

            return {
                "path": path,
                "issues": seg_issues,
                "first_hash": first_hash,
                "last_hash": last_hash,
                "merkle": merkle_root(hashes) if hashes else "",
                "count": count,
                "first_ts": first_ts,
                "last_ts": last_ts,
            }

        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_map = {executor.submit(verify_segment, p): p for p in segments}
            for fut in as_completed(future_map):
                res = fut.result()
                results[res["path"].name] = res
                issues.extend(res["issues"])

        # Check cross-segment previous_hash continuity
        prev_last_hash = ""
        for seg in sorted(segments):
            res = results[seg.name]
            if res["count"] > 0 and prev_last_hash:
                # Read first entry for previous_hash check
                with open(seg, "r", encoding="utf-8") as f:
                    for line in f:
                        if not line.strip():
                            continue
                        try:
                            first_entry = LedgerEntry.from_json(line.strip())
                            if first_entry.previous_hash != prev_last_hash:
                                issues.append(f"FAIL: Segment link broken into {seg.name}")
                        except Exception:
                            issues.append(f"FAIL: Cannot parse first entry of {seg.name}")
                        break
            prev_last_hash = res["last_hash"] or prev_last_hash

        is_valid = not any(i.startswith("FAIL") for i in issues)
        return is_valid, issues

    def get_session_root(self, since: str = None) -> str:
        """Compute merkle root of entries.

        Args:
            since: ISO timestamp to filter from (optional)

        Returns:
            Merkle root hash, or "" if no entries with hashes
        """
        entries = self.read_all()

        if since:
            entries = [e for e in entries if e.timestamp >= since]

        # Only include entries with hashes
        hashes = [e.entry_hash for e in entries if e.entry_hash]

        if not hashes:
            return ""

        return merkle_root(hashes)

    def get_segments_root(self) -> str:
        """Compute Merkle root across segment Merkle roots (root-of-roots).

        Returns empty string if no segment metadata is present.
        """
        if not self.segment_index_path.exists():
            return ""
        roots = []
        with open(self.segment_index_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    root = data.get("merkle_root", "")
                    if root:
                        roots.append(root)
                except Exception:
                    continue
        return merkle_root(roots) if roots else ""

    def write_genesis(
        self,
        tier: str,
        plane_root: Path,
        parent_ledger: Optional[str] = None,
        parent_hash: Optional[str] = None,
        work_order_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> str:
        """Write GENESIS entry as first entry in ledger.

        GENESIS entries mark the beginning of a ledger chain and contain
        cross-chain lineage information linking to the parent ledger.

        Args:
            tier: Tier name (HOT, HO2, HO1)
            plane_root: Absolute path to plane root directory
            parent_ledger: Path/URI to parent tier's ledger (optional)
            parent_hash: Hash of last entry in parent ledger (optional)
            work_order_id: Work order ID if in a work-order instance
            session_id: Session ID if in a session instance

        Returns:
            Entry ID of the GENESIS entry

        Raises:
            ValueError: If ledger already has entries
        """
        if self.count() > 0:
            raise ValueError("Cannot write GENESIS to non-empty ledger")

        entry = LedgerEntry(
            event_type="GENESIS",
            submission_id="GENESIS",
            decision="CHAIN_INITIALIZED",
            reason=f"Ledger chain initialized for {tier} plane",
            metadata={
                "tier": tier,
                "plane_root": str(plane_root),
                "parent_ledger": parent_ledger,
                "parent_hash": parent_hash,
                "work_order_id": work_order_id,
                "session_id": session_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        return self.write(entry)

    def verify_genesis(self) -> Tuple[bool, List[str]]:
        """Verify GENESIS entry is valid first entry.

        Checks:
        1. Ledger is not empty
        2. First entry is GENESIS event_type
        3. GENESIS has required metadata fields

        Returns:
            Tuple of (is_valid, list_of_issues)
            - is_valid: True if no FAIL issues
            - issues: List of WARN/FAIL/INFO messages
        """
        entries = self.read_all()
        issues: List[str] = []

        if not entries:
            issues.append("FAIL: Ledger is empty (no GENESIS)")
            return False, issues

        first = entries[0]
        if first.event_type != "GENESIS":
            issues.append(f"WARN: First entry is {first.event_type}, not GENESIS")

        if first.event_type == "GENESIS":
            # Check required metadata
            meta = first.metadata
            if not meta.get("tier"):
                issues.append("WARN: GENESIS missing tier metadata")
            if not meta.get("plane_root"):
                issues.append("WARN: GENESIS missing plane_root metadata")
            if not meta.get("created_at"):
                issues.append("WARN: GENESIS missing created_at metadata")

        return len([i for i in issues if i.startswith("FAIL")]) == 0, issues

    def verify_chain_link(self, parent_ledger_path: Path) -> Tuple[bool, List[str]]:
        """Verify parent_hash in GENESIS matches parent ledger.

        Args:
            parent_ledger_path: Path to parent ledger file

        Returns:
            Tuple of (is_valid, list_of_issues)
            - is_valid: True if chain link is valid
            - issues: List of WARN/FAIL/INFO messages
        """
        entries = self.read_all()
        issues: List[str] = []

        if not entries or entries[0].event_type != "GENESIS":
            issues.append("FAIL: No GENESIS entry to verify")
            return False, issues

        genesis = entries[0]
        expected_parent_hash = genesis.metadata.get("parent_hash")

        if not expected_parent_hash:
            issues.append("INFO: No parent_hash in GENESIS (root ledger)")
            return True, issues

        if not parent_ledger_path.exists():
            issues.append(f"FAIL: Parent ledger not found: {parent_ledger_path}")
            return False, issues

        parent_client = LedgerClient(ledger_path=parent_ledger_path)
        parent_entries = parent_client.read_all()

        if not parent_entries:
            issues.append("FAIL: Parent ledger is empty")
            return False, issues

        actual_parent_hash = parent_entries[-1].entry_hash
        if not actual_parent_hash:
            issues.append("WARN: Parent ledger last entry has no entry_hash (legacy)")
            return True, issues

        if expected_parent_hash != actual_parent_hash:
            issues.append(
                f"FAIL: Parent hash mismatch: expected {expected_parent_hash[:16]}..., "
                f"got {actual_parent_hash[:16]}..."
            )
            return False, issues

        return True, []

    def get_last_entry_hash_value(self) -> Optional[str]:
        """Get the entry_hash of the last entry in the ledger.

        Returns:
            Hash string if ledger has entries with hashes, None otherwise
        """
        entries = self.read_all()
        if not entries:
            return None
        # Return last entry's hash
        last = entries[-1]
        return last.entry_hash if last.entry_hash else None

    def has_dedupe_key(self, dedupe_key: str) -> bool:
        """Check if an entry with the given dedupe_key exists.

        Dedupe keys are stored in metadata["_dedupe_key"].

        Args:
            dedupe_key: Dedupe key to search for

        Returns:
            True if an entry with this dedupe_key exists
        """
        entries = self.read_all()
        for entry in entries:
            if entry.metadata.get("_dedupe_key") == dedupe_key:
                return True
        return False

    def read_by_event_type(self, event_type: str) -> List[LedgerEntry]:
        """Read entries with a specific event type.

        Args:
            event_type: Event type to filter by

        Returns:
            List of matching entries in order
        """
        entries = self.read_all()
        return [e for e in entries if e.event_type == event_type]

    def read_entries_range(self, start: int, end: int) -> List[LedgerEntry]:
        """Read entries in a specific index range.

        Args:
            start: Start index (inclusive)
            end: End index (exclusive)

        Returns:
            List of entries in the range
        """
        entries = self.read_all()
        return entries[start:end]

    def read_recent(self, limit: int = 10) -> List[LedgerEntry]:
        """Read the most recent entries from the ledger.

        Args:
            limit: Maximum number of entries to return (default 10)

        Returns:
            List of most recent entries, newest last
        """
        entries = self.read_all()
        return entries[-limit:] if len(entries) > limit else entries


def get_session_ledger_path(
    tier: str,
    session_id: str,
    ledger_type: str = "exec",
    root: Optional[Path] = None
) -> Path:
    """Get path to session-specific ledger file.

    Session ledgers follow the path pattern:
    planes/<tier>/sessions/<session_id>/ledger/<type>.jsonl

    Args:
        tier: Tier name (ho1, ho2, hot)
        session_id: Session identifier (SES-...)
        ledger_type: Ledger type - "exec" or "evidence"
        root: Control plane root directory (default: parent of lib/)

    Returns:
        Path to the session ledger file
    """
    if root is None:
        root = Path(__file__).resolve().parent.parent
    return root / "planes" / tier / "sessions" / session_id / "ledger" / f"{ledger_type}.jsonl"


def create_session_ledger_client(
    tier: str,
    session_id: str,
    ledger_type: str = "exec",
    root: Optional[Path] = None,
    **kwargs
) -> LedgerClient:
    """Create a LedgerClient for a session-specific ledger.

    Creates the client configured for the session ledger path:
    planes/<tier>/sessions/<session_id>/ledger/<type>.jsonl

    Args:
        tier: Tier name (ho1, ho2, hot)
        session_id: Session identifier (SES-...)
        ledger_type: Ledger type - "exec" or "evidence"
        root: Control plane root directory
        **kwargs: Additional arguments passed to LedgerClient

    Returns:
        Configured LedgerClient instance
    """
    ledger_path = get_session_ledger_path(tier, session_id, ledger_type, root)
    tier_context = TierContext(
        tier=tier,
        plane_root=root or Path(__file__).resolve().parent.parent,
        session_id=session_id
    )
    return LedgerClient(
        ledger_path=ledger_path,
        tier_context=tier_context,
        **kwargs
    )


def read_recent_from_tier(
    tier: str,
    limit: int = 10,
    root: Optional[Path] = None
) -> List[LedgerEntry]:
    """Read recent entries from a tier's governance ledger.

    Args:
        tier: Tier name (ho1, ho2, hot or HO1, HO2, HOT)
        limit: Maximum number of entries to return
        root: Control plane root directory

    Returns:
        List of most recent entries from the tier's ledger
    """
    if root is None:
        root = Path(__file__).resolve().parent.parent

    # Normalize tier name
    tier_lower = tier.lower()

    # Determine ledger path based on tier
    if tier_lower == "hot":
        # HOT uses the main governance ledger
        ledger_path = root / "ledger" / "governance.jsonl"
    else:
        # HO1, HO2 use plane-specific ledgers
        ledger_path = root / "planes" / tier_lower / "ledger" / "governance.jsonl"

    if not ledger_path.exists():
        return []

    client = LedgerClient(ledger_path=ledger_path)
    return client.read_recent(limit)


def list_session_ledgers(
    tier: str,
    root: Optional[Path] = None
) -> List[Dict[str, Any]]:
    """List all session ledgers for a tier.

    Args:
        tier: Tier name (ho1, ho2, hot)
        root: Control plane root directory

    Returns:
        List of session info dicts with keys: session_id, exec_path, evidence_path, exists
    """
    if root is None:
        root = Path(__file__).resolve().parent.parent

    sessions_dir = root / "planes" / tier / "sessions"
    if not sessions_dir.exists():
        return []

    result = []
    for session_dir in sorted(sessions_dir.iterdir()):
        if not session_dir.is_dir():
            continue
        if not session_dir.name.startswith("SES-"):
            continue

        exec_path = session_dir / "ledger" / "exec.jsonl"
        evidence_path = session_dir / "ledger" / "evidence.jsonl"

        result.append({
            "session_id": session_dir.name,
            "exec_path": exec_path,
            "evidence_path": evidence_path,
            "exec_exists": exec_path.exists(),
            "evidence_exists": evidence_path.exists(),
        })

    return result
