"""Unit tests for the Agent Runtime Module."""

import json
import pytest
from pathlib import Path

from modules.agent_runtime import (
    CapabilityEnforcer,
    Session,
    TurnSandbox,
    PromptBuilder,
    AgentMemory,
    LedgerWriter,
)
from modules.agent_runtime.exceptions import CapabilityViolation, SessionError
from modules.agent_runtime.session import generate_session_id


class TestCapabilityEnforcer:
    """Tests for CapabilityEnforcer class."""

    def test_check_allow(self):
        """Allowed read paths return True."""
        enforcer = CapabilityEnforcer({
            "read": ["ledger/*.jsonl", "registries/*.csv"],
            "write": [],
            "execute": [],
            "forbidden": []
        })
        assert enforcer.check("read", "ledger/governance.jsonl") is True
        assert enforcer.check("read", "registries/packages.csv") is True

    def test_check_deny(self):
        """Disallowed read paths return False."""
        enforcer = CapabilityEnforcer({
            "read": ["ledger/*.jsonl"],
            "write": [],
            "execute": [],
            "forbidden": []
        })
        assert enforcer.check("read", "lib/secret.py") is False
        assert enforcer.check("read", "config/settings.json") is False

    def test_enforce_raises(self):
        """Denied operation raises CapabilityViolation."""
        enforcer = CapabilityEnforcer({
            "read": [],
            "write": [],
            "execute": [],
            "forbidden": []
        })
        with pytest.raises(CapabilityViolation):
            enforcer.enforce("read", "any/path.txt")

    def test_forbidden_pattern_blocks(self):
        """Forbidden patterns block even matching capabilities."""
        enforcer = CapabilityEnforcer({
            "read": ["**/*"],  # Would allow everything
            "write": [],
            "execute": [],
            "forbidden": ["lib/*"]  # But lib/ is forbidden
        })
        assert enforcer.is_forbidden("lib/secret.py") is True
        with pytest.raises(CapabilityViolation):
            enforcer.enforce("read", "lib/secret.py")

    def test_write_capability(self):
        """Write capability check works."""
        enforcer = CapabilityEnforcer({
            "read": [],
            "write": ["output/*.json"],
            "execute": [],
            "forbidden": []
        })
        assert enforcer.check("write", "output/result.json") is True
        assert enforcer.check("write", "lib/file.py") is False

    def test_execute_capability(self):
        """Execute capability check works."""
        enforcer = CapabilityEnforcer({
            "read": [],
            "write": [],
            "execute": ["scripts/trace.py --explain"],
            "forbidden": []
        })
        assert enforcer.check("execute", "scripts/trace.py --explain") is True

    def test_check_declared_outputs(self):
        """check_declared_outputs validates against write capabilities."""
        enforcer = CapabilityEnforcer({
            "read": [],
            "write": ["output/*.json"],
            "execute": [],
            "forbidden": []
        })

        # Valid outputs
        enforcer.check_declared_outputs([
            {"path": "output/result.json", "role": "result"}
        ])

        # Invalid outputs
        with pytest.raises(CapabilityViolation):
            enforcer.check_declared_outputs([
                {"path": "lib/secret.py", "role": "forbidden"}
            ])


class TestSession:
    """Tests for Session class."""

    def test_session_id_format(self):
        """Session ID has correct format."""
        session = Session(tier="ho1")
        assert session.session_id.startswith("SES-")
        parts = session.session_id.split("-")
        assert len(parts) == 3  # SES-timestamp-random

    def test_generate_session_id_format(self):
        """generate_session_id produces correct format."""
        sid = generate_session_id()
        assert sid.startswith("SES-")
        assert len(sid.split("-")) == 3

    def test_unique_ids(self):
        """Generated session IDs are unique."""
        ids = {generate_session_id() for _ in range(100)}
        assert len(ids) == 100

    def test_session_creates_directories(self, tmp_path):
        """Session creates ledger directory on entry."""
        with Session(tier="ho1", root=tmp_path) as session:
            assert session.ledger_path.exists()
            assert session.exec_ledger_path.exists()
            assert session.evidence_ledger_path.exists()

    def test_session_paths(self, tmp_path):
        """Session paths are correct."""
        session = Session(tier="ho1", session_id="SES-test", root=tmp_path)
        assert session.session_path == tmp_path / "planes" / "ho1" / "sessions" / "SES-test"
        assert session.ledger_path == session.session_path / "ledger"
        assert session.tmp_path == tmp_path / "tmp" / "SES-test"
        assert session.output_path == tmp_path / "output" / "SES-test"

    def test_double_start_raises(self, tmp_path):
        """Starting session twice raises error."""
        session = Session(tier="ho1", root=tmp_path)
        session.start()
        with pytest.raises(SessionError):
            session.start()

    def test_turn_counter(self, tmp_path):
        """Turn counter increments correctly."""
        with Session(tier="ho1", root=tmp_path) as session:
            assert session.increment_turn() == 1
            assert session.increment_turn() == 2
            assert session.increment_turn() == 3


class TestTurnSandbox:
    """Tests for TurnSandbox class."""

    def test_creates_directories(self, tmp_path):
        """Sandbox creates session directories."""
        sandbox = TurnSandbox("SES-test", [], root=tmp_path)
        with sandbox:
            assert sandbox.sandbox_root.exists()
            assert sandbox.output_root.exists()

    def test_sets_environment(self, tmp_path):
        """Sandbox sets TMPDIR environment."""
        import os
        sandbox = TurnSandbox("SES-test", [], root=tmp_path)
        with sandbox:
            assert os.environ["TMPDIR"] == str(sandbox.sandbox_root)
            assert os.environ["PYTHONDONTWRITEBYTECODE"] == "1"

    def test_verify_empty_outputs(self, tmp_path):
        """Empty declared outputs with no writes is valid."""
        sandbox = TurnSandbox("SES-test", [], root=tmp_path)
        with sandbox:
            pass  # No writes
        realized, valid = sandbox.verify_writes()
        assert valid is True
        assert realized == []

    def test_verify_declared_write(self, tmp_path):
        """Declared write matches realized write."""
        declared = [{"path": f"output/SES-test/result.json", "role": "result"}]
        sandbox = TurnSandbox("SES-test", declared, root=tmp_path)
        with sandbox:
            sandbox.output_root.mkdir(parents=True, exist_ok=True)
            (sandbox.output_root / "result.json").write_text('{}')
        realized, valid = sandbox.verify_writes()
        assert valid is True

    def test_verify_undeclared_write_fails(self, tmp_path):
        """Undeclared write is detected."""
        sandbox = TurnSandbox("SES-test", [], root=tmp_path)
        with sandbox:
            sandbox.sandbox_root.mkdir(parents=True, exist_ok=True)
            (sandbox.sandbox_root / "sneaky.txt").write_text("bad")
        realized, valid = sandbox.verify_writes()
        assert valid is False


class TestPromptBuilder:
    """Tests for PromptBuilder class."""

    def test_build_header(self, tmp_path):
        """Build prompt header with all fields."""
        builder = PromptBuilder(tier="ho1", root=tmp_path)
        header = builder.build(
            session_id="SES-123",
            turn_number=1,
            declared_inputs=[],
            declared_outputs=[]
        )
        assert header["session_id"] == "SES-123"
        assert header["turn_number"] == 1
        assert header["tier"] == "ho1"
        assert "context_as_of" in header

    def test_build_with_work_order(self, tmp_path):
        """Build prompt header with work order."""
        builder = PromptBuilder(tier="ho1", root=tmp_path)
        header = builder.build(
            session_id="SES-123",
            turn_number=1,
            declared_inputs=[],
            declared_outputs=[],
            work_order_id="WO-456"
        )
        assert header["work_order_id"] == "WO-456"

    def test_format_as_markdown(self, tmp_path):
        """Format header as markdown."""
        builder = PromptBuilder(tier="ho1", root=tmp_path)
        header = builder.build(
            session_id="SES-123",
            turn_number=1,
            declared_inputs=[],
            declared_outputs=[]
        )
        md = builder.format_as_markdown(header)
        assert "# Agent Context" in md
        assert "SES-123" in md


class TestLedgerWriter:
    """Tests for LedgerWriter class."""

    def test_write_turn(self, tmp_path):
        """Write turn creates entries in both ledgers."""
        with Session(tier="ho1", root=tmp_path) as session:
            writer = LedgerWriter(session)
            writer.write_turn(
                turn_number=1,
                exec_entry={"query_hash": "sha256:abc", "result_hash": "sha256:def", "status": "ok"},
                evidence_entry={"declared_reads": [], "declared_writes": [], "external_calls": []}
            )

        # Check exec ledger
        with open(session.exec_ledger_path) as f:
            exec_entry = json.loads(f.readline())
        assert exec_entry["session_id"] == session.session_id
        assert exec_entry["turn_number"] == 1
        assert exec_entry["event_type"] == "agent_turn"

        # Check evidence ledger
        with open(session.evidence_ledger_path) as f:
            evidence_entry = json.loads(f.readline())
        assert evidence_entry["session_id"] == session.session_id
        assert evidence_entry["turn_number"] == 1
        assert evidence_entry["event_type"] == "turn_evidence"

    def test_write_with_work_order(self, tmp_path):
        """Write turn includes work_order_id."""
        with Session(tier="ho1", root=tmp_path) as session:
            writer = LedgerWriter(session)
            writer.write_turn(
                turn_number=1,
                exec_entry={"query_hash": "sha256:abc", "result_hash": "sha256:def", "status": "ok"},
                evidence_entry={"declared_reads": [], "declared_writes": [], "external_calls": []},
                work_order_id="WO-123"
            )

        with open(session.evidence_ledger_path) as f:
            entry = json.loads(f.readline())
        assert entry["work_order_id"] == "WO-123"


class TestAgentMemory:
    """Tests for AgentMemory class."""

    def test_reconstruct_context(self, tmp_path):
        """Reconstruct context returns Context object."""
        memory = AgentMemory(tier="ho1", root=tmp_path)
        context = memory.reconstruct_context()
        assert context.context_as_of is not None
        assert isinstance(context.recent_events, list)

    def test_get_recent_entries(self, tmp_path):
        """Get recent entries returns list."""
        memory = AgentMemory(tier="ho1", root=tmp_path)
        entries = memory.get_recent_entries("ho3", limit=5)
        assert isinstance(entries, list)
