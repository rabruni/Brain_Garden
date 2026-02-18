"""Tests for PKG-HO3-MEMORY-001 -- HO3 Memory Store.

18 tests covering: signal logging, signal reading/accumulation,
overlay logging, overlay reading, bistable gate, decay computation,
active biases, source ledger immutability. No LLM calls. All tests
use tmp_path for isolation.
"""

import sys
import json
import math
from pathlib import Path
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import pytest

_staging = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_staging / "PKG-KERNEL-001" / "HOT" / "kernel"))
sys.path.insert(0, str(_staging / "PKG-KERNEL-001" / "HOT"))
sys.path.insert(0, str(_staging / "PKG-HO3-MEMORY-001" / "HOT" / "kernel"))


@pytest.fixture(autouse=True)
def _bypass_pristine():
    with patch("kernel.pristine.assert_append_only", return_value=None):
        yield


@pytest.fixture
def ho3(tmp_path):
    """Create an HO3Memory instance with a temp directory."""
    from ho3_memory import HO3Memory, HO3MemoryConfig
    config = HO3MemoryConfig(
        memory_dir=tmp_path / "HOT" / "memory",
        gate_count_threshold=5,
        gate_session_threshold=3,
        gate_window_hours=168,
        decay_half_life_hours=336,
        enabled=True,
    )
    return HO3Memory(plane_root=tmp_path, config=config)


# === Signal Logging Tests ===

class TestSignalLogging:
    def test_log_signal_creates_entry(self, ho3, tmp_path):
        """Call log_signal -> entry appended to signals.jsonl."""
        ho3.log_signal(
            signal_id="tool_usage:gate_check",
            session_id="SES-001",
            event_id="EVT-test001",
        )
        signals_path = tmp_path / "HOT" / "memory" / "signals.jsonl"
        assert signals_path.exists()
        lines = [l for l in signals_path.read_text().strip().split("\n") if l.strip()]
        assert len(lines) >= 1
        entry = json.loads(lines[-1])
        assert entry["metadata"].get("signal_id") == "tool_usage:gate_check"
        assert entry["metadata"].get("session_id_signal") == "SES-001"
        assert entry["metadata"].get("ho3_event_id") == "EVT-test001"

    def test_log_signal_returns_event_id(self, ho3):
        """log_signal returns the event_id that was passed in."""
        result = ho3.log_signal(
            signal_id="intent:tool_query",
            session_id="SES-002",
            event_id="EVT-abc12345",
        )
        assert result == "EVT-abc12345"


# === Signal Reading / Accumulation Tests ===

class TestSignalReading:
    def test_read_signals_accumulates_count(self, ho3):
        """Log 3 events for same signal_id -> read_signals shows count=3."""
        for i in range(3):
            ho3.log_signal("sig:test", "SES-001", f"EVT-{i:03d}")
        accumulators = ho3.read_signals(signal_id="sig:test")
        assert len(accumulators) == 1
        assert accumulators[0].count == 3

    def test_read_signals_tracks_sessions(self, ho3):
        """Log from 2 sessions -> session_ids has both."""
        ho3.log_signal("sig:test", "SES-001", "EVT-001")
        ho3.log_signal("sig:test", "SES-002", "EVT-002")
        accumulators = ho3.read_signals(signal_id="sig:test")
        assert len(accumulators) == 1
        assert set(accumulators[0].session_ids) == {"SES-001", "SES-002"}

    def test_read_signals_tracks_event_ids(self, ho3):
        """Log 3 events -> event_ids has all 3."""
        ids = ["EVT-a01", "EVT-a02", "EVT-a03"]
        for eid in ids:
            ho3.log_signal("sig:test", "SES-001", eid)
        accumulators = ho3.read_signals(signal_id="sig:test")
        assert len(accumulators) == 1
        assert set(accumulators[0].event_ids) == set(ids)

    def test_read_signals_last_seen(self, ho3):
        """Log at time T -> last_seen reflects most recent timestamp."""
        ho3.log_signal("sig:test", "SES-001", "EVT-001")
        ho3.log_signal("sig:test", "SES-001", "EVT-002")
        accumulators = ho3.read_signals(signal_id="sig:test")
        assert len(accumulators) == 1
        # last_seen should be a valid ISO timestamp
        ts = accumulators[0].last_seen
        assert ts  # non-empty
        # Should be parseable
        datetime.fromisoformat(ts)

    def test_read_signals_by_id(self, ho3):
        """Read specific signal_id -> returns only that signal."""
        ho3.log_signal("sig:alpha", "SES-001", "EVT-001")
        ho3.log_signal("sig:beta", "SES-001", "EVT-002")
        accumulators = ho3.read_signals(signal_id="sig:alpha")
        assert len(accumulators) == 1
        assert accumulators[0].signal_id == "sig:alpha"

    def test_read_signals_min_count_filter(self, ho3):
        """2 signals, counts 2 and 5, min_count=3 -> only count-5 returned."""
        for i in range(2):
            ho3.log_signal("sig:low", "SES-001", f"EVT-low-{i}")
        for i in range(5):
            ho3.log_signal("sig:high", f"SES-{i:03d}", f"EVT-high-{i}")
        accumulators = ho3.read_signals(min_count=3)
        assert len(accumulators) == 1
        assert accumulators[0].signal_id == "sig:high"
        assert accumulators[0].count == 5

    def test_read_signals_empty(self, ho3):
        """No events logged -> empty list."""
        accumulators = ho3.read_signals()
        assert accumulators == []


# === Overlay Tests ===

class TestOverlays:
    def test_log_overlay_creates_entry(self, ho3, tmp_path):
        """Call log_overlay -> entry appended to overlays.jsonl."""
        overlay = {
            "signal_id": "sig:test",
            "salience_weight": 0.8,
            "decay_modifier": 0.95,
            "source_event_ids": ["EVT-001", "EVT-002"],
            "content": {"bias": "User prefers X", "category": "tool_preference"},
            "window_start": "2026-02-10T00:00:00+00:00",
            "window_end": "2026-02-17T11:00:00+00:00",
        }
        result = ho3.log_overlay(overlay)
        assert result.startswith("OVL-")
        overlays_path = tmp_path / "HOT" / "memory" / "overlays.jsonl"
        assert overlays_path.exists()

    def test_overlay_has_source_event_ids(self, ho3):
        """Overlay entry MUST contain source_event_ids (NON-EMPTY). Mandatory test #4."""
        overlay_bad = {
            "signal_id": "sig:test",
            "salience_weight": 0.8,
            "decay_modifier": 0.95,
            "source_event_ids": [],
            "content": {"bias": "X"},
            "window_start": "2026-02-10T00:00:00+00:00",
            "window_end": "2026-02-17T11:00:00+00:00",
        }
        with pytest.raises(ValueError, match="source_event_ids"):
            ho3.log_overlay(overlay_bad)

    def test_read_overlays_all(self, ho3):
        """Log 2 overlays -> read_overlays returns both."""
        for i in range(2):
            ho3.log_overlay({
                "signal_id": f"sig:test{i}",
                "salience_weight": 0.8,
                "decay_modifier": 0.95,
                "source_event_ids": [f"EVT-{i:03d}"],
                "content": {"bias": f"bias {i}", "category": "tool_preference"},
                "window_start": "2026-02-10T00:00:00+00:00",
                "window_end": "2026-02-17T11:00:00+00:00",
            })
        overlays = ho3.read_overlays()
        assert len(overlays) == 2

    def test_read_overlays_by_signal_id(self, ho3):
        """2 overlays, different signal_ids -> filter returns 1."""
        ho3.log_overlay({
            "signal_id": "sig:alpha",
            "salience_weight": 0.8,
            "decay_modifier": 0.95,
            "source_event_ids": ["EVT-001"],
            "content": {"bias": "alpha bias"},
            "window_start": "2026-02-10T00:00:00+00:00",
            "window_end": "2026-02-17T11:00:00+00:00",
        })
        ho3.log_overlay({
            "signal_id": "sig:beta",
            "salience_weight": 0.8,
            "decay_modifier": 0.95,
            "source_event_ids": ["EVT-002"],
            "content": {"bias": "beta bias"},
            "window_start": "2026-02-10T00:00:00+00:00",
            "window_end": "2026-02-17T11:00:00+00:00",
        })
        overlays = ho3.read_overlays(signal_id="sig:alpha")
        assert len(overlays) == 1
        assert overlays[0]["signal_id"] == "sig:alpha"

    def test_read_active_biases(self, ho3):
        """Overlays with salience > 0 and recent -> returned as active biases."""
        now = datetime.now(timezone.utc)
        ho3.log_overlay({
            "signal_id": "sig:active",
            "salience_weight": 0.8,
            "decay_modifier": 0.95,
            "source_event_ids": ["EVT-001"],
            "content": {"bias": "User frequently checks gate status", "category": "tool_preference"},
            "window_start": (now - timedelta(days=7)).isoformat(),
            "window_end": now.isoformat(),
        })
        biases = ho3.read_active_biases()
        assert len(biases) >= 1
        assert biases[0]["content"]["bias"] == "User frequently checks gate status"


# === Bistable Gate Tests ===

class TestBistableGate:
    def test_gate_false_below_count(self, ho3):
        """count=2, threshold=5 -> gate not crossed. Mandatory test #1 (partial)."""
        for i in range(2):
            ho3.log_signal("sig:test", f"SES-{i:03d}", f"EVT-{i:03d}")
        gate_result = ho3.check_gate("sig:test")
        assert gate_result.crossed is False

    def test_gate_false_below_sessions(self, ho3):
        """count=10, sessions=1, threshold_sessions=3 -> gate not crossed."""
        for i in range(10):
            ho3.log_signal("sig:test", "SES-001", f"EVT-{i:03d}")
        gate_result = ho3.check_gate("sig:test")
        assert gate_result.crossed is False

    def test_gate_true_thresholds_met(self, ho3):
        """count=5, sessions=3, not consolidated -> gate crossed."""
        sessions = ["SES-001", "SES-002", "SES-003"]
        evt = 0
        for sess in sessions:
            ho3.log_signal("sig:test", sess, f"EVT-{evt:03d}")
            evt += 1
        # Add 2 more from existing sessions to reach count=5
        ho3.log_signal("sig:test", "SES-001", f"EVT-{evt:03d}")
        evt += 1
        ho3.log_signal("sig:test", "SES-002", f"EVT-{evt:03d}")

        gate_result = ho3.check_gate("sig:test")
        assert gate_result.crossed is True

    def test_gate_false_already_consolidated(self, ho3):
        """Thresholds met BUT overlay exists within window -> gate not crossed. Mandatory test #3 (partial)."""
        # Log enough signals to cross thresholds
        sessions = ["SES-001", "SES-002", "SES-003"]
        evt = 0
        for sess in sessions:
            ho3.log_signal("sig:test", sess, f"EVT-{evt:03d}")
            evt += 1
        ho3.log_signal("sig:test", "SES-001", f"EVT-{evt:03d}")
        evt += 1
        ho3.log_signal("sig:test", "SES-002", f"EVT-{evt:03d}")

        # Now log an overlay for this signal within the window
        now = datetime.now(timezone.utc)
        ho3.log_overlay({
            "signal_id": "sig:test",
            "salience_weight": 0.8,
            "decay_modifier": 0.95,
            "source_event_ids": ["EVT-000", "EVT-001"],
            "content": {"bias": "Already consolidated"},
            "window_start": (now - timedelta(days=5)).isoformat(),
            "window_end": now.isoformat(),
        })

        gate_result = ho3.check_gate("sig:test")
        assert gate_result.crossed is False
        assert gate_result.already_consolidated is True


# === Immutability Test ===

class TestImmutability:
    def test_source_ledger_immutability(self, ho3, tmp_path):
        """Log 3 signals, read, log 1 more -> first 3 events unchanged."""
        for i in range(3):
            ho3.log_signal("sig:test", "SES-001", f"EVT-{i:03d}")

        signals_path = tmp_path / "HOT" / "memory" / "signals.jsonl"
        lines_before = signals_path.read_text().strip().split("\n")
        assert len(lines_before) == 3

        # Log one more
        ho3.log_signal("sig:test", "SES-001", "EVT-003")

        lines_after = signals_path.read_text().strip().split("\n")
        assert len(lines_after) == 4

        # First 3 lines must be identical (append-only, no mutation)
        for i in range(3):
            assert lines_before[i] == lines_after[i], f"Line {i} was mutated"
