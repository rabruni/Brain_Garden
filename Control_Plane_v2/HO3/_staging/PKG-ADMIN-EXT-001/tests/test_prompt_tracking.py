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
