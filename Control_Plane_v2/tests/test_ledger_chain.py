#!/usr/bin/env python3
"""
test_ledger_chain.py - Ledger chain integrity tests.

Tests:
1. P5: Ledger chain verifies without failures
2. New entries maintain chain integrity
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.ledger_client import LedgerClient, LedgerEntry


class TestLedgerChainIntegrity:
    """P5: Ledger chain verification tests."""

    def test_verify_chain_returns_valid(self):
        """Existing ledger chain should be valid (no FAIL issues)."""
        client = LedgerClient()
        valid, issues = client.verify_chain()

        # Filter to only FAIL issues (WARN for legacy entries is acceptable)
        fail_issues = [i for i in issues if i.startswith("FAIL")]

        assert valid, f"Ledger chain invalid: {fail_issues}"
        assert len(fail_issues) == 0, f"Chain has failures: {fail_issues}"

    def test_new_entries_maintain_chain(self):
        """New entries should maintain chain integrity."""
        import os
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmpdir:
            ledger_path = Path(tmpdir) / "ledger" / "test.jsonl"
            ledger_path.parent.mkdir(parents=True, exist_ok=True)

            # Mock assert_append_only to allow temp directory writes
            with patch("lib.pristine.assert_append_only", return_value=None):
                client = LedgerClient(ledger_path=ledger_path, enable_index=False)

                # Write several entries
                for i in range(5):
                    entry = LedgerEntry(
                        event_type="test",
                        submission_id=f"TEST-{i:03d}",
                        decision="SUCCESS",
                        reason=f"Test entry {i}",
                    )
                    client.write(entry)

                client.flush()

                # Verify chain
                valid, issues = client.verify_chain()
                assert valid, f"Chain invalid after writes: {issues}"


def run_tests():
    """Run all tests and report results."""
    passed = 0
    failed = 0

    test_classes = [TestLedgerChainIntegrity]

    for test_class in test_classes:
        instance = test_class()
        for method_name in dir(instance):
            if not method_name.startswith("test_"):
                continue

            method = getattr(instance, method_name)
            test_name = f"{test_class.__name__}.{method_name}"

            try:
                method()
                print(f"  PASS: {test_name}")
                passed += 1
            except AssertionError as e:
                print(f"  FAIL: {test_name} - {e}")
                failed += 1
            except Exception as e:
                print(f"  ERROR: {test_name} - {e}")
                failed += 1

    print()
    print(f"Passed: {passed}, Failed: {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    print("=" * 60)
    print("LEDGER CHAIN TESTS")
    print("=" * 60)
    sys.exit(run_tests())
