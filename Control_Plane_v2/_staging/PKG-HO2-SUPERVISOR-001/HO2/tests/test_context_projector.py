"""Tests for context projector (HANDOFF-31E-1)."""

from pathlib import Path
import sys

_staging = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_staging / "PKG-HO2-SUPERVISOR-001" / "HO2" / "kernel"))

from context_projector import ContextProjector, ProjectionConfig
from liveness import LivenessState


def _make_liveness() -> LivenessState:
    return LivenessState(
        intents={
            "INT-001": {
                "status": "LIVE",
                "objective": "Explore installed packages",
                "declared_at": "2026-02-20T00:00:00+00:00",
            },
            "INT-000": {
                "status": "CLOSED",
                "objective": "Closed objective",
                "declared_at": "2026-02-19T00:00:00+00:00",
            },
        },
        work_orders={
            "WO-OPEN-001": {"status": "DISPATCHED", "wo_type": "synthesize"},
            "WO-OPEN-002": {"status": "OPEN", "wo_type": "classify"},
        },
        active_intents=["INT-001"],
        open_work_orders=["WO-OPEN-001", "WO-OPEN-002"],
        failed_items=[{"wo_id": "WO-FAIL-001", "reason": "gate rejected", "timestamp": "2026-02-20T00:01:00+00:00"}],
    )


class TestContextProjector:
    def test_output_shape_matches_old(self):
        projector = ContextProjector(ProjectionConfig())
        out = projector.project(
            liveness=_make_liveness(),
            ho3_artifacts=[],
            user_message="hello",
            classification={"speech_act": "greeting"},
            session_id="SES-001",
        )
        assert set(out.keys()) == {"user_input", "classification", "assembled_context"}
        assert set(out["assembled_context"].keys()) == {
            "context_text",
            "context_hash",
            "fragment_count",
            "tokens_used",
        }

    def test_context_text_has_sections(self):
        projector = ContextProjector(ProjectionConfig())
        out = projector.project(_make_liveness(), [], "hello", {"speech_act": "question"}, "SES-001")
        text = out["assembled_context"]["context_text"]
        assert "## Active Intent" in text
        assert "## Failed Items" in text
        assert "## Open Work Orders" in text
        assert "## Learning Context" in text

    def test_active_intent_in_projection(self):
        projector = ContextProjector(ProjectionConfig())
        out = projector.project(_make_liveness(), [], "hello", {"speech_act": "question"}, "SES-001")
        text = out["assembled_context"]["context_text"]
        assert "Objective: Explore installed packages" in text
        assert "Status: LIVE" in text

    def test_failed_items_high_priority(self):
        projector = ContextProjector(ProjectionConfig())
        out = projector.project(_make_liveness(), [], "hello", {"speech_act": "question"}, "SES-001")
        text = out["assembled_context"]["context_text"]
        i_failed = text.find("## Failed Items")
        i_open = text.find("## Open Work Orders")
        assert i_failed != -1 and i_open != -1
        assert i_failed < i_open

    def test_open_wos_in_projection(self):
        projector = ContextProjector(ProjectionConfig())
        out = projector.project(_make_liveness(), [], "hello", {"speech_act": "question"}, "SES-001")
        text = out["assembled_context"]["context_text"]
        assert "WO-OPEN-001 (synthesize): DISPATCHED" in text
        assert "WO-OPEN-002 (classify): OPEN" in text

    def test_ho3_artifacts_injected(self):
        artifacts = [{"context_line": "User prefers concise responses"}]
        projector = ContextProjector(ProjectionConfig())
        out = projector.project(_make_liveness(), artifacts, "hello", {"speech_act": "question"}, "SES-001")
        assert "User prefers concise responses" in out["assembled_context"]["context_text"]

    def test_budget_respected(self):
        projector = ContextProjector(ProjectionConfig(projection_budget=60))
        out = projector.project(_make_liveness(), [], "hello", {"speech_act": "question"}, "SES-001")
        assert out["assembled_context"]["tokens_used"] <= 60

    def test_empty_liveness(self):
        projector = ContextProjector(ProjectionConfig())
        out = projector.project(LivenessState(), [], "hello", {"speech_act": "question"}, "SES-001")
        text = out["assembled_context"]["context_text"]
        assert "## Active Intent" in text
        assert "(none)" in text

    def test_budget_overflow_truncates(self):
        artifacts = [{"context_line": "x" * 4000}]
        projector = ContextProjector(ProjectionConfig(projection_budget=40))
        out = projector.project(_make_liveness(), artifacts, "hello", {"speech_act": "question"}, "SES-001")
        assert out["assembled_context"]["tokens_used"] <= 40

    def test_classification_preserved(self):
        classification = {"speech_act": "question", "ambiguity": "low"}
        projector = ContextProjector(ProjectionConfig())
        out = projector.project(_make_liveness(), [], "hello", classification, "SES-001")
        assert out["classification"] == classification

    def test_user_input_preserved(self):
        projector = ContextProjector(ProjectionConfig())
        out = projector.project(_make_liveness(), [], "show latest sessions", {"speech_act": "question"}, "SES-001")
        assert out["user_input"] == "show latest sessions"

    def test_deterministic(self):
        config = ProjectionConfig()
        projector = ContextProjector(config)
        liveness = _make_liveness()
        artifacts = [{"context_line": "stable"}]
        out1 = projector.project(liveness, artifacts, "hello", {"speech_act": "question"}, "SES-001")
        out2 = projector.project(liveness, artifacts, "hello", {"speech_act": "question"}, "SES-001")
        assert out1 == out2
