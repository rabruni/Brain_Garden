"""Fail-closed sandbox enforcement tests.

These tests verify that the sandbox correctly blocks undeclared writes
and enforces the write surface invariant.
"""

import os
import json
import pytest
from pathlib import Path

from modules.agent_runtime import Session, TurnSandbox
from modules.agent_runtime.exceptions import SandboxError


class TestSandboxBlocksUndeclared:
    """Tests that sandbox blocks undeclared writes."""

    def test_undeclared_write_detected(self, tmp_path):
        """Turn that writes undeclared file is detected."""
        sandbox = TurnSandbox("SES-test", declared_outputs=[], root=tmp_path)
        with sandbox:
            # Write an undeclared file
            sandbox.sandbox_root.mkdir(parents=True, exist_ok=True)
            (sandbox.sandbox_root / "sneaky.txt").write_text("bad")

        realized, valid = sandbox.verify_writes()
        assert valid is False
        assert len(realized) == 1
        assert "sneaky.txt" in realized[0]["path"]

    def test_undeclared_in_output_dir(self, tmp_path):
        """Undeclared write in output directory is detected."""
        sandbox = TurnSandbox("SES-test", declared_outputs=[], root=tmp_path)
        with sandbox:
            sandbox.output_root.mkdir(parents=True, exist_ok=True)
            (sandbox.output_root / "undeclared.json").write_text("{}")

        realized, valid = sandbox.verify_writes()
        assert valid is False

    def test_verify_and_raise(self, tmp_path):
        """verify_and_raise raises SandboxError on mismatch."""
        sandbox = TurnSandbox("SES-test", declared_outputs=[], root=tmp_path)
        with sandbox:
            sandbox.sandbox_root.mkdir(parents=True, exist_ok=True)
            (sandbox.sandbox_root / "bad.txt").write_text("undeclared")

        with pytest.raises(SandboxError) as exc_info:
            sandbox.verify_and_raise()

        assert exc_info.value.session_id == "SES-test"
        assert len(exc_info.value.undeclared_writes) > 0


class TestSandboxEnvironment:
    """Tests for sandbox environment setup."""

    def test_tmpdir_redirected(self, tmp_path):
        """TMPDIR is redirected to session sandbox."""
        sandbox = TurnSandbox("SES-test", declared_outputs=[], root=tmp_path)
        with sandbox:
            assert os.environ["TMPDIR"] == str(sandbox.sandbox_root)
            assert os.environ["TEMP"] == str(sandbox.sandbox_root)
            assert os.environ["TMP"] == str(sandbox.sandbox_root)

    def test_pycache_blocked(self, tmp_path):
        """PYTHONDONTWRITEBYTECODE is set to prevent .pyc files."""
        sandbox = TurnSandbox("SES-test", declared_outputs=[], root=tmp_path)
        with sandbox:
            assert os.environ.get("PYTHONDONTWRITEBYTECODE") == "1"

    def test_environment_restored(self, tmp_path):
        """Environment is restored after sandbox exit."""
        original_tmpdir = os.environ.get("TMPDIR")
        sandbox = TurnSandbox("SES-test", declared_outputs=[], root=tmp_path)

        with sandbox:
            pass  # Sandbox sets environment

        # After exit, should be restored (or None if wasn't set)
        if original_tmpdir is None:
            assert "TMPDIR" not in os.environ or os.environ.get("TMPDIR") != str(sandbox.sandbox_root)
        else:
            assert os.environ.get("TMPDIR") == original_tmpdir


class TestSandboxDeclaredWrites:
    """Tests for declared write handling."""

    def test_declared_write_succeeds(self, tmp_path):
        """Turn that writes only declared outputs succeeds."""
        declared = [{"path": f"output/SES-test/result.json", "role": "result"}]
        sandbox = TurnSandbox("SES-test", declared_outputs=declared, root=tmp_path)

        with sandbox:
            out_path = sandbox.output_root
            out_path.mkdir(parents=True, exist_ok=True)
            (out_path / "result.json").write_text('{"status": "ok"}')

        realized, valid = sandbox.verify_writes()
        assert valid is True
        assert len(realized) == 1

    def test_missing_declared_write_fails(self, tmp_path):
        """Turn that doesn't write declared output fails."""
        declared = [{"path": f"output/SES-test/result.json", "role": "result"}]
        sandbox = TurnSandbox("SES-test", declared_outputs=declared, root=tmp_path)

        with sandbox:
            pass  # Don't write the declared output

        realized, valid = sandbox.verify_writes()
        assert valid is False  # Missing declared write

    def test_multiple_declared_outputs(self, tmp_path):
        """Multiple declared outputs are validated."""
        declared = [
            {"path": f"output/SES-test/file1.json", "role": "result"},
            {"path": f"output/SES-test/file2.json", "role": "artifact"}
        ]
        sandbox = TurnSandbox("SES-test", declared_outputs=declared, root=tmp_path)

        with sandbox:
            out_path = sandbox.output_root
            out_path.mkdir(parents=True, exist_ok=True)
            (out_path / "file1.json").write_text("{}")
            (out_path / "file2.json").write_text("{}")

        realized, valid = sandbox.verify_writes()
        assert valid is True
        assert len(realized) == 2


class TestLedgerWriting:
    """Tests for ledger writing requirements."""

    def test_both_ledgers_created(self, tmp_path):
        """Both exec.jsonl and evidence.jsonl are created."""
        with Session(tier="ho1", root=tmp_path) as session:
            assert session.exec_ledger_path.exists()
            assert session.evidence_ledger_path.exists()

    def test_both_ledgers_written(self, tmp_path):
        """Both ledgers receive entries on turn execution."""
        from modules.agent_runtime.ledger_writer import LedgerWriter

        with Session(tier="ho1", root=tmp_path) as session:
            writer = LedgerWriter(session)
            writer.write_turn(
                turn_number=1,
                exec_entry={"query_hash": "sha256:abc", "result_hash": "sha256:def", "status": "ok"},
                evidence_entry={"declared_reads": [], "declared_writes": [], "external_calls": []}
            )

            # Verify both files have content
            assert session.exec_ledger_path.stat().st_size > 0
            assert session.evidence_ledger_path.stat().st_size > 0

    def test_evidence_has_required_fields(self, tmp_path):
        """Evidence entry has session_id, turn_number, work_order_id."""
        from modules.agent_runtime.ledger_writer import LedgerWriter

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

            assert entry["session_id"] == session.session_id
            assert entry["turn_number"] == 1
            assert entry["work_order_id"] == "WO-123"

    def test_hash_chaining(self, tmp_path):
        """Ledger entries have hash chaining."""
        from modules.agent_runtime.ledger_writer import LedgerWriter

        with Session(tier="ho1", root=tmp_path) as session:
            writer = LedgerWriter(session)

            # Write first entry
            writer.write_turn(
                turn_number=1,
                exec_entry={"query_hash": "sha256:abc", "result_hash": "sha256:def", "status": "ok"},
                evidence_entry={"declared_reads": [], "declared_writes": [], "external_calls": []}
            )

            # Write second entry
            writer.write_turn(
                turn_number=2,
                exec_entry={"query_hash": "sha256:ghi", "result_hash": "sha256:jkl", "status": "ok"},
                evidence_entry={"declared_reads": [], "declared_writes": [], "external_calls": []}
            )

            with open(session.exec_ledger_path) as f:
                entry1 = json.loads(f.readline())
                entry2 = json.loads(f.readline())

            # Second entry should have previous_hash pointing to first
            assert entry2["previous_hash"] == entry1["entry_hash"]
