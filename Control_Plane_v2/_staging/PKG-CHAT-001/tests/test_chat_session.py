#!/usr/bin/env python3
"""Tests for chat session management."""

import json
import sys
import tempfile
from pathlib import Path

import pytest

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules.chat_interface.session import ChatSession, create_session


class TestChatSession:
    """Test session management."""

    def test_session_id_format(self):
        """Test session ID follows pattern."""
        session = ChatSession()
        assert session.session_id.startswith("SES-CHAT-")
        # SES-CHAT-YYYYMMDD-xxxxxxxx = 26 chars (with date like 20260204)
        assert len(session.session_id) == 26

    def test_session_id_unique(self):
        """Test each session gets unique ID."""
        session1 = ChatSession()
        session2 = ChatSession()
        assert session1.session_id != session2.session_id

    def test_session_start_creates_ledger(self):
        """Test session initialization creates ledger directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            session = ChatSession(tier="ho1")
            session.root = Path(tmpdir)
            session.start()

            ledger_path = session.get_ledger_path()
            assert ledger_path.parent.exists()

    def test_turn_logging(self):
        """Test turn logging to session ledger."""
        with tempfile.TemporaryDirectory() as tmpdir:
            session = ChatSession(tier="ho1")
            session.root = Path(tmpdir)
            session.start()

            # Log a turn
            entry_id = session.log_turn(
                query="test query",
                result="test result",
                handler="test_handler",
                duration_ms=42,
            )

            assert entry_id.startswith("LED-")
            assert session.turn_count == 1

            # Verify ledger entry
            ledger_path = session.get_ledger_path()
            assert ledger_path.exists()

            with open(ledger_path) as f:
                entry = json.loads(f.readline())

            assert entry["event_type"] == "CHAT_TURN"
            assert entry["metadata"]["turn_number"] == 1
            assert entry["metadata"]["handler"] == "test_handler"
            assert entry["metadata"]["duration_ms"] == 42

    def test_evidence_recording(self):
        """Test file read evidence recording."""
        with tempfile.TemporaryDirectory() as tmpdir:
            session = ChatSession(tier="ho1")
            session.root = Path(tmpdir)
            session.start()

            # Record some reads
            session.record_read("lib/auth.py", "sha256:abc123")
            session.record_read("lib/merkle.py", "sha256:def456")

            # Log turn (should include reads)
            session.log_turn(
                query="read some files",
                result="done",
                handler="browse_code",
                duration_ms=10,
            )

            # Verify reads in ledger
            ledger_path = session.get_ledger_path()
            with open(ledger_path) as f:
                entry = json.loads(f.readline())

            reads = entry["metadata"]["declared_reads"]
            assert len(reads) == 2
            assert reads[0]["path"] == "lib/auth.py"
            assert reads[1]["path"] == "lib/merkle.py"

    def test_custom_event_logging(self):
        """Test logging custom events."""
        with tempfile.TemporaryDirectory() as tmpdir:
            session = ChatSession(tier="ho1")
            session.root = Path(tmpdir)
            session.start()

            entry_id = session.log_event(
                "PACKAGE_INSTALLED",
                "PKG-TEST-001",
                {"files_installed": 5}
            )

            assert entry_id.startswith("LED-")

            ledger_path = session.get_ledger_path()
            with open(ledger_path) as f:
                entry = json.loads(f.readline())

            assert entry["event_type"] == "PACKAGE_INSTALLED"
            assert entry["metadata"]["files_installed"] == 5

    def test_context_manager(self):
        """Test session as context manager."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with ChatSession(tier="ho1") as session:
                session.root = Path(tmpdir)
                session.log_turn("q", "r", "h", 1)

            # Ledger should be flushed after context exit
            # (In real usage, ledger would be at proper path)

    def test_create_session_helper(self):
        """Test create_session convenience function."""
        session = create_session("ho2")
        assert session.tier == "ho2"
        assert session.session_id.startswith("SES-CHAT-")


class TestLedgerIntegration:
    """Test ledger integration."""

    def test_turn_entry_schema(self):
        """Test turn entries have required fields."""
        with tempfile.TemporaryDirectory() as tmpdir:
            session = ChatSession(tier="ho1")
            session.root = Path(tmpdir)
            session.start()

            session.log_turn(
                query="test",
                result="result",
                handler="test",
                duration_ms=1,
                classification={"type": "help", "confidence": 1.0}
            )

            ledger_path = session.get_ledger_path()
            with open(ledger_path) as f:
                entry = json.loads(f.readline())

            # Required fields
            assert "event_type" in entry
            assert "submission_id" in entry
            assert "timestamp" in entry
            assert "metadata" in entry

            # Metadata fields
            meta = entry["metadata"]
            assert "turn_number" in meta
            assert "query_hash" in meta
            assert "result_hash" in meta
            assert "handler" in meta
            assert "duration_ms" in meta
            assert "declared_reads" in meta

    def test_evidence_hashes(self):
        """Test evidence includes file hashes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            session = ChatSession(tier="ho1")
            session.root = Path(tmpdir)
            session.start()

            session.record_read("test.py", "sha256:abc")
            session.log_turn("q", "r", "h", 1)

            ledger_path = session.get_ledger_path()
            with open(ledger_path) as f:
                entry = json.loads(f.readline())

            reads = entry["metadata"]["declared_reads"]
            assert len(reads) == 1
            assert reads[0]["hash"] == "sha256:abc"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
