"""Tests for HO2 bias selection policy (HANDOFF-29.1C)."""

from copy import deepcopy
from pathlib import Path
import sys

_staging = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_staging / "PKG-HO2-SUPERVISOR-001" / "HO2" / "kernel"))

from bias_selector import select_biases


def _artifact(
    artifact_id: str,
    *,
    scope: str = "session",
    domain=None,
    task=None,
    weight: float = 0.5,
    decay_modifier: float = 1.0,
    context_line: str = "default context line",
    enabled: bool = True,
    expires_at_event_ts=None,
    consolidation_event_ts: str = "2026-02-18T00:00:00+00:00",
):
    labels = {"domain": domain or [], "task": task or []}
    return {
        "artifact_id": artifact_id,
        "scope": scope,
        "labels": labels,
        "weight": weight,
        "decay_modifier": decay_modifier,
        "context_line": context_line,
        "enabled": enabled,
        "expires_at_event_ts": expires_at_event_ts,
        "consolidation_event_ts": consolidation_event_ts,
    }


class TestBiasSelector:
    def test_filter_disabled(self):
        artifacts = [
            _artifact("a1", enabled=False, scope="global"),
            _artifact("a2", scope="global"),
        ]
        selected = select_biases(artifacts, {}, 2000, "2026-02-20T00:00:00+00:00")
        assert [a["artifact_id"] for a in selected] == ["a2"]

    def test_filter_expired(self):
        artifacts = [
            _artifact("expired", scope="global", expires_at_event_ts="2026-02-10T00:00:00+00:00"),
            _artifact("active", scope="global", expires_at_event_ts="2026-02-25T00:00:00+00:00"),
        ]
        selected = select_biases(artifacts, {}, 2000, "2026-02-20T00:00:00+00:00")
        assert [a["artifact_id"] for a in selected] == ["active"]

    def test_filter_not_expired(self):
        artifacts = [
            _artifact("a1", scope="global", expires_at_event_ts="2026-02-21T00:00:00+00:00"),
        ]
        selected = select_biases(artifacts, {}, 2000, "2026-02-20T00:00:00+00:00")
        assert [a["artifact_id"] for a in selected] == ["a1"]

    def test_scope_match_domain(self):
        artifacts = [
            _artifact("a1", scope="session", domain=["system", "config"]),
            _artifact("a2", scope="session", domain=["docs"]),
        ]
        selected = select_biases(artifacts, {"domain": "system"}, 2000, "2026-02-20T00:00:00+00:00")
        assert [a["artifact_id"] for a in selected] == ["a1"]

    def test_scope_match_task(self):
        artifacts = [
            _artifact("a1", scope="session", task=["inspect"]),
            _artifact("a2", scope="session", task=["modify"]),
        ]
        selected = select_biases(artifacts, {"task": "inspect"}, 2000, "2026-02-20T00:00:00+00:00")
        assert [a["artifact_id"] for a in selected] == ["a1"]

    def test_scope_no_match(self):
        artifacts = [
            _artifact("a1", scope="session", domain=["docs"], task=["plan"]),
        ]
        selected = select_biases(artifacts, {"domain": "system", "task": "inspect"}, 2000, "2026-02-20T00:00:00+00:00")
        assert selected == []

    def test_scope_global_always_included(self):
        artifacts = [
            _artifact("global", scope="global", domain=["docs"]),
            _artifact("local", scope="session", domain=["docs"]),
        ]
        selected = select_biases(artifacts, {"domain": "system"}, 2000, "2026-02-20T00:00:00+00:00")
        assert [a["artifact_id"] for a in selected] == ["global"]

    def test_rank_by_weight(self):
        artifacts = [
            _artifact("high", scope="global", weight=0.9),
            _artifact("low", scope="global", weight=0.4),
        ]
        selected = select_biases(artifacts, {}, 2000, "2026-02-20T00:00:00+00:00")
        assert [a["artifact_id"] for a in selected] == ["high", "low"]

    def test_budget_limit(self):
        long_line = "x" * 80  # ~20 tokens by len/4 estimate
        artifacts = [
            _artifact("a1", scope="global", weight=0.9, context_line=long_line),
            _artifact("a2", scope="global", weight=0.8, context_line=long_line),
            _artifact("a3", scope="global", weight=0.7, context_line=long_line),
        ]
        selected = select_biases(artifacts, {}, 45, "2026-02-20T00:00:00+00:00")
        assert [a["artifact_id"] for a in selected] == ["a1", "a2"]

    def test_empty_turn_labels_global_only(self):
        artifacts = [
            _artifact("global", scope="global"),
            _artifact("session", scope="session", domain=["system"]),
        ]
        selected = select_biases(artifacts, {}, 2000, "2026-02-20T00:00:00+00:00")
        assert [a["artifact_id"] for a in selected] == ["global"]

    def test_deterministic(self):
        artifacts = [
            _artifact("a1", scope="global", weight=0.9),
            _artifact("a2", scope="global", weight=0.8),
        ]
        s1 = select_biases(deepcopy(artifacts), {}, 2000, "2026-02-20T00:00:00+00:00")
        s2 = select_biases(deepcopy(artifacts), {}, 2000, "2026-02-20T00:00:00+00:00")
        assert s1 == s2

    def test_backward_compat_no_labels_field(self):
        legacy = {
            "artifact_id": "legacy",
            "scope": "session",
            "weight": 0.7,
            "decay_modifier": 1.0,
            "context_line": "legacy bias",
            "enabled": True,
            "expires_at_event_ts": None,
            "consolidation_event_ts": "2026-02-18T00:00:00+00:00",
        }
        selected = select_biases([legacy], {}, 2000, "2026-02-20T00:00:00+00:00")
        assert [a["artifact_id"] for a in selected] == ["legacy"]
