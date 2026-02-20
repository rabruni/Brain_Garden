"""Tests for PKG-HO3-MEMORY-001 -- HO3 Memory Store.

36 tests covering: signal logging, signal reading/accumulation,
overlay logging, overlay reading, bistable gate, decay computation,
active biases, source ledger immutability, as_of_ts replay-safe decay,
structured artifacts, overlay lifecycle, expiry filtering, idempotency.
No LLM calls. All tests use tmp_path for isolation.
"""

import sys
import json
import hashlib
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


# === as_of_ts Replay-Safe Decay Tests ===

class TestAsOfTs:
    def test_as_of_ts_deterministic_decay(self, ho3):
        """Same as_of_ts -> same decay across runs."""
        ho3.log_signal("sig:test", "SES-001", "EVT-001")
        fixed_ts = "2026-02-25T00:00:00+00:00"
        acc1 = ho3.read_signals(signal_id="sig:test", as_of_ts=fixed_ts)
        acc2 = ho3.read_signals(signal_id="sig:test", as_of_ts=fixed_ts)
        assert acc1[0].decay == acc2[0].decay

    def test_as_of_ts_none_uses_wall_clock(self, ho3):
        """as_of_ts=None -> uses datetime.now() (backward compatible)."""
        ho3.log_signal("sig:test", "SES-001", "EVT-001")
        acc = ho3.read_signals(signal_id="sig:test")
        assert len(acc) == 1
        # Decay should be close to 1.0 (just logged)
        assert acc[0].decay > 0.99

    def test_as_of_ts_in_read_active_biases(self, ho3):
        """Biases filtered by as_of_ts -- expired excluded."""
        now = datetime.now(timezone.utc)
        ho3.log_overlay({
            "signal_id": "sig:test",
            "salience_weight": 0.8,
            "source_event_ids": ["EVT-001"],
            "content": {"bias": "test"},
            "window_start": (now - timedelta(days=7)).isoformat(),
            "window_end": now.isoformat(),
            "artifact_id": "ART-expiry001",
            "artifact_type": "topic_affinity",
            "expires_at_event_ts": (now + timedelta(days=1)).isoformat(),
            "enabled": True,
        })
        # as_of_ts before expiry -> included
        biases = ho3.read_active_biases(as_of_ts=now.isoformat())
        assert len(biases) >= 1
        # as_of_ts after expiry -> excluded
        far_future = (now + timedelta(days=30)).isoformat()
        biases_future = ho3.read_active_biases(as_of_ts=far_future)
        expired_ids = [b.get("artifact_id") for b in biases_future]
        assert "ART-expiry001" not in expired_ids

    def test_as_of_ts_in_is_consolidated(self, ho3):
        """Consolidated check uses as_of_ts -- deterministic gate."""
        now = datetime.now(timezone.utc)
        # Log enough signals to cross thresholds
        for i in range(5):
            ho3.log_signal("sig:test", f"SES-{i:03d}", f"EVT-{i:03d}")
        # Log an overlay within window
        ho3.log_overlay({
            "signal_id": "sig:test",
            "salience_weight": 0.8,
            "source_event_ids": ["EVT-000"],
            "content": {"bias": "consolidated"},
            "window_start": (now - timedelta(days=5)).isoformat(),
            "window_end": now.isoformat(),
        })
        # _is_consolidated should use as_of_ts
        # as_of_ts just after window_end -> consolidated
        result = ho3._is_consolidated("sig:test", as_of_ts=now.isoformat())
        assert result is True
        # as_of_ts far in the past (before window) -> not consolidated
        past = (now - timedelta(days=365)).isoformat()
        result_past = ho3._is_consolidated("sig:test", as_of_ts=past)
        assert result_past is False


# === Structured Artifact Tests ===

class TestStructuredArtifacts:
    def _make_structured_overlay(self, **overrides):
        now = datetime.now(timezone.utc)
        base = {
            "signal_id": "sig:test",
            "salience_weight": 0.8,
            "decay_modifier": 0.95,
            "source_event_ids": ["EVT-001", "EVT-002"],
            "content": {"bias": "User prefers X", "category": "topic_affinity"},
            "window_start": (now - timedelta(days=7)).isoformat(),
            "window_end": now.isoformat(),
            "artifact_id": "ART-abc123def0",
            "artifact_type": "topic_affinity",
            "labels": {"domain": ["system"], "task": ["inspect"]},
            "weight": 0.7,
            "scope": "agent",
            "context_line": "User frequently explores package structure",
            "enabled": True,
            "expires_at_event_ts": None,
            "source_signal_ids": ["domain:system", "tool:read_file"],
            "gate_snapshot": {"count": 12, "sessions": 3},
            "model": "claude-sonnet-4-20250514",
            "prompt_pack_version": "PRM-CONSOLIDATE-001",
            "consolidation_event_ts": now.isoformat(),
        }
        base.update(overrides)
        return base

    def test_structured_artifact_all_fields(self, ho3, tmp_path):
        """log_overlay with all structured fields -> all fields stored."""
        overlay = self._make_structured_overlay()
        ovl_id = ho3.log_overlay(overlay)
        assert ovl_id.startswith("OVL-")
        overlays = ho3.read_overlays()
        assert len(overlays) == 1
        stored = overlays[0]
        assert stored.get("artifact_id") == "ART-abc123def0"
        assert stored.get("artifact_type") == "topic_affinity"
        assert stored.get("labels") == {"domain": ["system"], "task": ["inspect"]}
        assert stored.get("weight") == 0.7
        assert stored.get("scope") == "agent"
        assert stored.get("context_line") == "User frequently explores package structure"
        assert stored.get("enabled") is True
        assert stored.get("source_signal_ids") == ["domain:system", "tool:read_file"]
        assert stored.get("gate_snapshot") == {"count": 12, "sessions": 3}
        assert stored.get("model") == "claude-sonnet-4-20250514"
        assert stored.get("prompt_pack_version") == "PRM-CONSOLIDATE-001"

    def test_structured_artifact_backward_read(self, ho3):
        """Old overlay (no structured fields) still readable."""
        now = datetime.now(timezone.utc)
        ho3.log_overlay({
            "signal_id": "sig:legacy",
            "salience_weight": 0.5,
            "source_event_ids": ["EVT-old"],
            "content": {"bias": "legacy bias"},
            "window_start": (now - timedelta(days=7)).isoformat(),
            "window_end": now.isoformat(),
        })
        biases = ho3.read_active_biases()
        assert len(biases) >= 1
        # Old overlay has no artifact_id
        assert biases[0].get("artifact_id") is None

    def test_artifact_type_stored(self, ho3):
        """artifact_type in overlay -> value persisted."""
        overlay = self._make_structured_overlay(artifact_type="constraint")
        ho3.log_overlay(overlay)
        stored = ho3.read_overlays()[0]
        assert stored.get("artifact_type") == "constraint"

    def test_labels_stored(self, ho3):
        """labels dict in overlay -> labels persisted."""
        labels = {"domain": ["config", "system"], "task": ["modify"]}
        overlay = self._make_structured_overlay(labels=labels)
        ho3.log_overlay(overlay)
        stored = ho3.read_overlays()[0]
        assert stored.get("labels") == labels


# === Overlay Lifecycle Tests ===

class TestOverlayLifecycle:
    def _log_structured(self, ho3, artifact_id="ART-lifecycle01", weight=0.8, enabled=True):
        now = datetime.now(timezone.utc)
        return ho3.log_overlay({
            "signal_id": "sig:test",
            "salience_weight": weight,
            "source_event_ids": ["EVT-001"],
            "content": {"bias": "test lifecycle"},
            "window_start": (now - timedelta(days=7)).isoformat(),
            "window_end": now.isoformat(),
            "artifact_id": artifact_id,
            "artifact_type": "topic_affinity",
            "enabled": enabled,
            "weight": weight,
        })

    def test_deactivate_overlay(self, ho3):
        """Deactivate -> not returned by read_active_biases."""
        self._log_structured(ho3, artifact_id="ART-deact001")
        biases_before = ho3.read_active_biases()
        art_ids_before = [b.get("artifact_id") for b in biases_before]
        assert "ART-deact001" in art_ids_before

        ho3.deactivate_overlay(
            artifact_id="ART-deact001",
            reason="no longer relevant",
            event_ts=datetime.now(timezone.utc).isoformat(),
        )
        biases_after = ho3.read_active_biases()
        art_ids_after = [b.get("artifact_id") for b in biases_after]
        assert "ART-deact001" not in art_ids_after

    def test_deactivate_nonexistent_raises(self, ho3):
        """Deactivate unknown artifact_id -> ValueError."""
        with pytest.raises(ValueError, match="artifact_id"):
            ho3.deactivate_overlay(
                artifact_id="ART-doesnotexist",
                reason="test",
                event_ts=datetime.now(timezone.utc).isoformat(),
            )

    def test_update_weight(self, ho3):
        """Update weight -> latest weight returned."""
        self._log_structured(ho3, artifact_id="ART-weight01", weight=0.5)
        ho3.update_overlay_weight(
            artifact_id="ART-weight01",
            new_weight=0.9,
            reason="signal strengthened",
            event_ts=datetime.now(timezone.utc).isoformat(),
        )
        biases = ho3.read_active_biases()
        match = [b for b in biases if b.get("artifact_id") == "ART-weight01"]
        assert len(match) == 1
        assert match[0].get("weight") == 0.9


# === Expiry Tests ===

class TestExpiryFiltering:
    def test_expiry_filter(self, ho3):
        """Expired artifact excluded by as_of_ts."""
        now = datetime.now(timezone.utc)
        ho3.log_overlay({
            "signal_id": "sig:expire",
            "salience_weight": 0.8,
            "source_event_ids": ["EVT-001"],
            "content": {"bias": "will expire"},
            "window_start": (now - timedelta(days=7)).isoformat(),
            "window_end": now.isoformat(),
            "artifact_id": "ART-expire01",
            "artifact_type": "topic_affinity",
            "enabled": True,
            "expires_at_event_ts": (now - timedelta(hours=1)).isoformat(),
        })
        biases = ho3.read_active_biases(as_of_ts=now.isoformat())
        art_ids = [b.get("artifact_id") for b in biases]
        assert "ART-expire01" not in art_ids

    def test_expiry_not_expired(self, ho3):
        """Non-expired artifact still returned."""
        now = datetime.now(timezone.utc)
        ho3.log_overlay({
            "signal_id": "sig:fresh",
            "salience_weight": 0.8,
            "source_event_ids": ["EVT-001"],
            "content": {"bias": "still fresh"},
            "window_start": (now - timedelta(days=7)).isoformat(),
            "window_end": now.isoformat(),
            "artifact_id": "ART-fresh01",
            "artifact_type": "topic_affinity",
            "enabled": True,
            "expires_at_event_ts": (now + timedelta(days=30)).isoformat(),
        })
        biases = ho3.read_active_biases(as_of_ts=now.isoformat())
        art_ids = [b.get("artifact_id") for b in biases]
        assert "ART-fresh01" in art_ids


# === Idempotency Tests ===

class TestIdempotency:
    def test_idempotency_skip_duplicate(self, ho3):
        """Same artifact_id -> no duplicate."""
        now = datetime.now(timezone.utc)
        overlay = {
            "signal_id": "sig:test",
            "salience_weight": 0.8,
            "source_event_ids": ["EVT-001"],
            "content": {"bias": "test"},
            "window_start": (now - timedelta(days=7)).isoformat(),
            "window_end": now.isoformat(),
            "artifact_id": "ART-idem001",
            "artifact_type": "topic_affinity",
            "enabled": True,
        }
        id1 = ho3.log_overlay(overlay)
        id2 = ho3.log_overlay(overlay.copy())
        # Second call should return existing overlay_id, not create new
        assert id1 == id2
        overlays = ho3.read_overlays(active_only=False)
        art_matches = [o for o in overlays if o.get("artifact_id") == "ART-idem001"
                       and o.get("overlay_id", "").startswith("OVL-")]
        # Only one HO3_OVERLAY event for this artifact_id
        assert len(art_matches) == 1

    def test_idempotency_reactivate(self, ho3):
        """Same artifact_id after deactivate -> weight update (re-activated)."""
        now = datetime.now(timezone.utc)
        overlay = {
            "signal_id": "sig:test",
            "salience_weight": 0.8,
            "source_event_ids": ["EVT-001"],
            "content": {"bias": "test"},
            "window_start": (now - timedelta(days=7)).isoformat(),
            "window_end": now.isoformat(),
            "artifact_id": "ART-react001",
            "artifact_type": "topic_affinity",
            "enabled": True,
            "weight": 0.6,
        }
        ho3.log_overlay(overlay)
        ho3.deactivate_overlay("ART-react001", "obsolete", now.isoformat())
        # Re-log same artifact_id -> should re-activate
        overlay2 = overlay.copy()
        overlay2["weight"] = 0.9
        ho3.log_overlay(overlay2)
        biases = ho3.read_active_biases()
        match = [b for b in biases if b.get("artifact_id") == "ART-react001"]
        assert len(match) == 1
        assert match[0].get("weight") == 0.9

    def test_compute_artifact_id_deterministic(self, ho3):
        """Same inputs -> same ID."""
        from ho3_memory import HO3Memory
        id1 = HO3Memory.compute_artifact_id(
            source_signal_ids=["domain:system", "tool:read_file"],
            gate_window_key="2026-W07",
            model="claude-sonnet-4-20250514",
            prompt_pack_version="PRM-CONSOLIDATE-001",
        )
        id2 = HO3Memory.compute_artifact_id(
            source_signal_ids=["tool:read_file", "domain:system"],  # different order
            gate_window_key="2026-W07",
            model="claude-sonnet-4-20250514",
            prompt_pack_version="PRM-CONSOLIDATE-001",
        )
        assert id1 == id2
        assert id1.startswith("ART-")
        assert len(id1) == 16  # ART- + 12 hex chars


# === Lifecycle Resolution Tests ===

class TestLifecycleResolution:
    def test_lifecycle_resolution_latest_wins(self, ho3):
        """Multiple events -> last event determines state."""
        now = datetime.now(timezone.utc)
        # Create overlay
        ho3.log_overlay({
            "signal_id": "sig:test",
            "salience_weight": 0.5,
            "source_event_ids": ["EVT-001"],
            "content": {"bias": "original"},
            "window_start": (now - timedelta(days=7)).isoformat(),
            "window_end": now.isoformat(),
            "artifact_id": "ART-resolve01",
            "artifact_type": "topic_affinity",
            "enabled": True,
            "weight": 0.5,
        })
        # Update weight
        ho3.update_overlay_weight("ART-resolve01", 0.9, "boosted", now.isoformat())
        # Deactivate
        ho3.deactivate_overlay("ART-resolve01", "done", now.isoformat())
        # After deactivation, should not appear in active biases
        biases = ho3.read_active_biases()
        art_ids = [b.get("artifact_id") for b in biases]
        assert "ART-resolve01" not in art_ids
