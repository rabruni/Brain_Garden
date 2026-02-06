"""Test prompt tracking in ledger.

Tests that LLM calls properly log prompt_pack_id to ledgers,
ensuring full audit trail for governed prompt usage.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import sys

# Add parent to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.ledger_client import LedgerClient, LedgerEntry
from modules.chat_interface.session import ChatSession, create_session


class TestSessionPromptTracking:
    """Test prompt tracking in ChatSession."""

    def test_record_prompt_adds_to_list(self):
        """Verify record_prompt adds prompt ID to tracking list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            session = ChatSession(tier="ho1", root=Path(tmpdir))
            session.start()

            session.record_prompt("PRM-TEST-001")

            assert "PRM-TEST-001" in session.get_prompts_used()

    def test_record_prompt_no_duplicates(self):
        """Verify same prompt ID is not added twice."""
        with tempfile.TemporaryDirectory() as tmpdir:
            session = ChatSession(tier="ho1", root=Path(tmpdir))
            session.start()

            session.record_prompt("PRM-TEST-001")
            session.record_prompt("PRM-TEST-001")

            assert session.get_prompts_used().count("PRM-TEST-001") == 1

    def test_record_prompt_multiple_prompts(self):
        """Verify multiple different prompts are tracked."""
        with tempfile.TemporaryDirectory() as tmpdir:
            session = ChatSession(tier="ho1", root=Path(tmpdir))
            session.start()

            session.record_prompt("PRM-TEST-001")
            session.record_prompt("PRM-TEST-002")
            session.record_prompt("PRM-TEST-003")

            prompts = session.get_prompts_used()
            assert len(prompts) == 3
            assert "PRM-TEST-001" in prompts
            assert "PRM-TEST-002" in prompts
            assert "PRM-TEST-003" in prompts

    def test_record_prompt_ignores_empty(self):
        """Verify empty/None prompt IDs are ignored."""
        with tempfile.TemporaryDirectory() as tmpdir:
            session = ChatSession(tier="ho1", root=Path(tmpdir))
            session.start()

            session.record_prompt("")
            session.record_prompt(None)

            assert len(session.get_prompts_used()) == 0

    def test_log_turn_includes_prompts_used(self):
        """Verify log_turn includes prompts_used in metadata."""
        with tempfile.TemporaryDirectory() as tmpdir:
            session = ChatSession(tier="ho1", root=Path(tmpdir))
            session.start()

            # Record a prompt
            session.record_prompt("PRM-TEST-001")

            # Log a turn
            session.log_turn(
                query="test query",
                result="test result",
                handler="test_handler",
                duration_ms=100,
            )

            # Read the ledger and verify
            ledger_path = session.get_ledger_path()
            assert ledger_path.exists()

            with open(ledger_path) as f:
                entries = [json.loads(line) for line in f if line.strip()]

            assert len(entries) == 1
            assert "prompts_used" in entries[0]["metadata"]
            assert entries[0]["metadata"]["prompts_used"] == ["PRM-TEST-001"]

    def test_log_turn_includes_actual_content(self):
        """Verify log_turn stores actual query and result text for transparency."""
        with tempfile.TemporaryDirectory() as tmpdir:
            session = ChatSession(tier="ho1", root=Path(tmpdir))
            session.start()

            # Log a turn with specific content
            session.log_turn(
                query="What packages are installed?",
                result="You have 5 packages installed.",
                handler="package_list",
                duration_ms=50,
            )

            # Read the ledger and verify actual content is stored
            ledger_path = session.get_ledger_path()
            with open(ledger_path) as f:
                entries = [json.loads(line) for line in f if line.strip()]

            assert len(entries) == 1
            metadata = entries[0]["metadata"]

            # Full transparency - actual content stored
            assert metadata["query_text"] == "What packages are installed?"
            assert metadata["result_text"] == "You have 5 packages installed."
            # Hashes also stored for integrity verification
            assert "query_hash" in metadata
            assert "result_hash" in metadata

    def test_log_turn_clears_prompts_after_logging(self):
        """Verify prompts are cleared after log_turn."""
        with tempfile.TemporaryDirectory() as tmpdir:
            session = ChatSession(tier="ho1", root=Path(tmpdir))
            session.start()

            session.record_prompt("PRM-TEST-001")
            session.log_turn(
                query="query1",
                result="result1",
                handler="handler1",
                duration_ms=100,
            )

            # After logging, prompts should be cleared
            assert len(session.get_prompts_used()) == 0

    def test_multiple_turns_track_prompts_separately(self):
        """Verify each turn tracks its own prompts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            session = ChatSession(tier="ho1", root=Path(tmpdir))
            session.start()

            # Turn 1: One prompt
            session.record_prompt("PRM-TEST-001")
            session.log_turn(
                query="query1",
                result="result1",
                handler="handler1",
                duration_ms=100,
            )

            # Turn 2: Different prompt
            session.record_prompt("PRM-TEST-002")
            session.log_turn(
                query="query2",
                result="result2",
                handler="handler2",
                duration_ms=100,
            )

            # Turn 3: No prompts
            session.log_turn(
                query="query3",
                result="result3",
                handler="handler3",
                duration_ms=100,
            )

            # Read ledger
            with open(session.get_ledger_path()) as f:
                entries = [json.loads(line) for line in f if line.strip()]

            assert len(entries) == 3
            assert entries[0]["metadata"]["prompts_used"] == ["PRM-TEST-001"]
            assert entries[1]["metadata"]["prompts_used"] == ["PRM-TEST-002"]
            assert entries[2]["metadata"]["prompts_used"] == []


class TestLLMLedgerLogging:
    """Test LLM call logging to L-LLM ledger."""

    def test_log_llm_call_creates_entry(self):
        """Verify _log_llm_call creates ledger entry with prompt_pack_id and content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger_path = Path(tmpdir) / "llm.jsonl"

            # Mock the _get_llm_ledger_path to use our temp path
            # Also mock assert_append_only to allow temp directory writes
            with patch("modules.stdlib_llm.client._get_llm_ledger_path") as mock_path:
                mock_path.return_value = ledger_path

                with patch("lib.pristine.assert_append_only", return_value=None):
                    from modules.stdlib_llm.client import _log_llm_call

                    evidence = {
                        "llm_call": {
                            "request_id": "req-123",
                            "prompt_hash": "sha256:abc123",
                            "response_hash": "sha256:def456",
                            "model": "test-model",
                            "usage": {"input_tokens": 100, "output_tokens": 50},
                            "cached": False,
                        },
                        "duration_ms": 500,
                    }

                    _log_llm_call(
                        prompt_pack_id="PRM-TEST-001",
                        evidence=evidence,
                        provider_id="mock",
                        prompt_text="What is the meaning of life?",
                        response_text="42",
                    )

                    # Read the ledger
                    assert ledger_path.exists()
                    with open(ledger_path) as f:
                        entries = [json.loads(line) for line in f if line.strip()]

                    assert len(entries) == 1
                    entry = entries[0]

                    assert entry["event_type"] == "LLM_CALL"
                    assert entry["prompts_used"] == ["PRM-TEST-001"]
                    assert entry["decision"] == "COMPLETED"
                    assert entry["metadata"]["prompt_pack_id"] == "PRM-TEST-001"
                    # Verify actual content is stored (full transparency)
                    assert entry["metadata"]["prompt_text"] == "What is the meaning of life?"
                    assert entry["metadata"]["response_text"] == "42"

    def test_complete_logs_to_llm_ledger(self):
        """Verify complete() logs to L-LLM ledger."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger_path = Path(tmpdir) / "llm.jsonl"

            # Mock the ledger path and the provider
            # Also mock assert_append_only to allow temp directory writes
            with patch("modules.stdlib_llm.client._get_llm_ledger_path") as mock_path:
                mock_path.return_value = ledger_path

                with patch("lib.pristine.assert_append_only", return_value=None):
                    # Create a mock provider
                    mock_response = MagicMock()
                    mock_response.content = "Test response"
                    mock_response.model = "mock-model"
                    mock_response.usage = {"input_tokens": 10, "output_tokens": 20}
                    mock_response.request_id = "req-456"
                    mock_response.cached = False
                    mock_response.metadata = {"provider_id": "mock"}

                    with patch("modules.stdlib_llm.client.get_provider") as mock_get_provider:
                        mock_provider = MagicMock()
                        mock_provider.complete.return_value = mock_response
                        mock_get_provider.return_value = mock_provider

                        from modules.stdlib_llm.client import complete

                        response = complete(
                            prompt="Test prompt",
                            prompt_pack_id="PRM-CLASSIFY-001",
                            provider_id="mock",
                        )

                        # Verify ledger entry was created
                        assert ledger_path.exists()
                        with open(ledger_path) as f:
                            entries = [json.loads(line) for line in f if line.strip()]

                        assert len(entries) == 1
                        assert entries[0]["prompts_used"] == ["PRM-CLASSIFY-001"]


class TestLedgerEntryPromptsUsed:
    """Test LedgerEntry prompts_used field."""

    def test_ledger_entry_prompts_used_field(self):
        """Verify LedgerEntry has prompts_used field."""
        entry = LedgerEntry(
            event_type="TEST",
            submission_id="SUB-001",
            decision="APPROVED",
            reason="Test reason",
            prompts_used=["PRM-TEST-001", "PRM-TEST-002"],
        )

        assert entry.prompts_used == ["PRM-TEST-001", "PRM-TEST-002"]

    def test_ledger_entry_prompts_used_defaults_empty(self):
        """Verify prompts_used defaults to empty list."""
        entry = LedgerEntry(
            event_type="TEST",
            submission_id="SUB-001",
            decision="APPROVED",
            reason="Test reason",
        )

        assert entry.prompts_used == []

    def test_ledger_client_writes_prompts_used(self):
        """Verify LedgerClient writes prompts_used to ledger."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger_path = Path(tmpdir) / "test.jsonl"

            # Mock assert_append_only to allow temp directory writes
            with patch("lib.pristine.assert_append_only", return_value=None):
                client = LedgerClient(ledger_path=ledger_path)

                entry = LedgerEntry(
                    event_type="TEST",
                    submission_id="SUB-001",
                    decision="APPROVED",
                    reason="Test reason",
                    prompts_used=["PRM-TEST-001"],
                )
                client.write(entry)
                client.flush()

                # Read and verify
                entries = client.read_all()
                assert len(entries) == 1
                assert entries[0].prompts_used == ["PRM-TEST-001"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
