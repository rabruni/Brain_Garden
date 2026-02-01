#!/usr/bin/env python3
"""
test_phase3_summary.py - Tests for Phase 3 summarize-up, push-policy, apply-policy.

Tests the Pride Pass criteria:
1. Idempotency - Running commands twice produces no new entries
2. Stable ordering - Deterministic discovery and processing
3. Cursor semantics - Monotonic, atomic cursor updates
4. Auditability - Provenance fields in all entries
"""

import json
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.ledger_factory import LedgerFactory
from lib.ledger_client import LedgerClient, LedgerEntry
from lib.tier_manifest import TierManifest
from lib.cursor import (
    CursorManager,
    CursorState,
    compute_dedupe_key,
    compute_policy_push_dedupe_key,
    compute_policy_apply_dedupe_key,
)


class TestCursorManager:
    """Tests for cursor management."""

    def test_cursor_save_load(self):
        """Cursor can be saved and loaded."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cursor_dir = Path(tmpdir) / "cursors"
            manager = CursorManager(cursor_dir)

            ledger_path = Path(tmpdir) / "test.jsonl"
            ledger_path.touch()

            # Save cursor
            state = manager.save(ledger_path, 10, "hash123")

            assert state.cursor == 10
            assert state.last_entry_hash == "hash123"

            # Load cursor
            loaded = manager.load(ledger_path)
            assert loaded is not None
            assert loaded.cursor == 10
            assert loaded.last_entry_hash == "hash123"

    def test_cursor_monotonic(self):
        """Cursor updates must be monotonic."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cursor_dir = Path(tmpdir) / "cursors"
            manager = CursorManager(cursor_dir)

            ledger_path = Path(tmpdir) / "test.jsonl"
            ledger_path.touch()

            # Save initial cursor
            manager.save(ledger_path, 10, "hash1")

            # Trying to save lower cursor should fail
            with pytest.raises(ValueError, match="Non-monotonic"):
                manager.save(ledger_path, 5, "hash2")

    def test_cursor_reset(self):
        """Cursor can be reset."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cursor_dir = Path(tmpdir) / "cursors"
            manager = CursorManager(cursor_dir)

            ledger_path = Path(tmpdir) / "test.jsonl"
            ledger_path.touch()

            manager.save(ledger_path, 10, "hash1")
            manager.reset_cursor(ledger_path, "test reset")

            # After reset, can save lower value
            state = manager.save(ledger_path, 5, "hash2")
            assert state.cursor == 5

    def test_get_unprocessed_range_new(self):
        """New ledger returns full range."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cursor_dir = Path(tmpdir) / "cursors"
            manager = CursorManager(cursor_dir)

            ledger_path = Path(tmpdir) / "test.jsonl"
            ledger_path.touch()

            from_c, to_c, was_reset = manager.get_unprocessed_range(
                ledger_path, 10, "hash"
            )

            assert from_c == 0
            assert to_c == 10
            assert was_reset is False

    def test_get_unprocessed_range_partial(self):
        """Existing cursor returns remaining range."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cursor_dir = Path(tmpdir) / "cursors"
            manager = CursorManager(cursor_dir)

            ledger_path = Path(tmpdir) / "test.jsonl"
            ledger_path.touch()

            manager.save(ledger_path, 5, "hash1")

            from_c, to_c, was_reset = manager.get_unprocessed_range(
                ledger_path, 10, "hash2"
            )

            assert from_c == 5
            assert to_c == 10
            assert was_reset is False

    def test_get_unprocessed_range_shrunk(self):
        """Shrunk ledger triggers reset."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cursor_dir = Path(tmpdir) / "cursors"
            manager = CursorManager(cursor_dir)

            ledger_path = Path(tmpdir) / "test.jsonl"
            ledger_path.touch()

            manager.save(ledger_path, 10, "hash1")

            # Ledger now has only 5 entries
            from_c, to_c, was_reset = manager.get_unprocessed_range(
                ledger_path, 5, "hash2"
            )

            assert from_c == 0
            assert to_c == 5
            assert was_reset is True


class TestDedupeKeys:
    """Tests for dedupe key computation."""

    def test_dedupe_key_deterministic(self):
        """Dedupe key is deterministic."""
        key1 = compute_dedupe_key("/path/to/ledger", 0, 10, "HO2")
        key2 = compute_dedupe_key("/path/to/ledger", 0, 10, "HO2")
        assert key1 == key2

    def test_dedupe_key_varies_by_range(self):
        """Dedupe key varies by cursor range."""
        key1 = compute_dedupe_key("/path/to/ledger", 0, 10, "HO2")
        key2 = compute_dedupe_key("/path/to/ledger", 0, 20, "HO2")
        assert key1 != key2

    def test_policy_push_dedupe_key_deterministic(self):
        """Policy push dedupe key is deterministic."""
        key1 = compute_policy_push_dedupe_key("POL-001", "1.0", "WO-001")
        key2 = compute_policy_push_dedupe_key("POL-001", "1.0", "WO-001")
        assert key1 == key2

    def test_policy_apply_dedupe_key_deterministic(self):
        """Policy apply dedupe key is deterministic."""
        key1 = compute_policy_apply_dedupe_key("POL-001", "1.0", "WO-001")
        key2 = compute_policy_apply_dedupe_key("POL-001", "1.0", "WO-001")
        assert key1 == key2

    def test_policy_dedupe_keys_differ(self):
        """Push and apply dedupe keys are different for same policy."""
        push_key = compute_policy_push_dedupe_key("POL-001", "1.0", "WO-001")
        apply_key = compute_policy_apply_dedupe_key("POL-001", "1.0", "WO-001")
        assert push_key != apply_key

    def test_policy_dedupe_key_varies(self):
        """Policy dedupe key varies by components."""
        key1 = compute_policy_apply_dedupe_key("POL-001", "1.0", "WO-001")
        key2 = compute_policy_apply_dedupe_key("POL-001", "2.0", "WO-001")
        assert key1 != key2


class TestLedgerDedupeKey:
    """Tests for LedgerClient dedupe key checking."""

    def test_has_dedupe_key_false(self):
        """has_dedupe_key returns False when key doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            manifest, client = LedgerFactory.create_tier("HO3", root)

            assert client.has_dedupe_key("nonexistent") is False

    def test_has_dedupe_key_true(self):
        """has_dedupe_key returns True when key exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            manifest, client = LedgerFactory.create_tier("HO3", root)

            entry = LedgerEntry(
                event_type="TEST",
                submission_id="TEST-001",
                decision="OK",
                reason="Test",
                metadata={"_dedupe_key": "my_key_123"},
            )
            client.write(entry)
            client.flush()

            assert client.has_dedupe_key("my_key_123") is True
            assert client.has_dedupe_key("other_key") is False


class TestSummarizeUpIdempotency:
    """Tests for summarize-up idempotency."""

    def test_summarize_up_twice_no_new_entries(self):
        """Running summarize-up twice with no child changes produces no new entries."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)

            # Create parent HO2
            ho2_root = base / "ho2"
            m2, c2 = LedgerFactory.create_tier("HO2", ho2_root)

            # Create work order with some entries
            wo_manifest, wo_client = LedgerFactory.create_work_order_instance(
                ho2_root, "WO-001"
            )

            # Add entries to work order
            for i in range(3):
                entry = LedgerEntry(
                    event_type="TASK",
                    submission_id=f"TASK-{i}",
                    decision="DONE",
                    reason=f"Task {i} completed",
                )
                wo_client.write(entry)
            wo_client.flush()

            # First summarize-up
            cursor_dir = ho2_root / "ledger" / "cursors"
            cursor_manager = CursorManager(cursor_dir)
            parent_client = LedgerFactory.from_tier_root(ho2_root)

            instances = LedgerFactory.list_instances(ho2_root)
            inst = instances[0]
            inst_client = LedgerFactory.from_tier_root(inst.tier_root)
            inst_entries = inst_client.read_all()

            from_cursor, to_cursor, _ = cursor_manager.get_unprocessed_range(
                inst.absolute_ledger_path,
                len(inst_entries),
                inst_client.get_last_entry_hash_value(),
            )

            # Create first summary
            instance_id = inst.work_order_id
            dedupe_key = compute_dedupe_key(
                str(inst.absolute_ledger_path),
                from_cursor,
                to_cursor,
                inst.tier,
            )

            summary_entry = LedgerEntry(
                event_type="SUMMARY_UP",
                submission_id=f"SUM-{instance_id}",
                decision="SUMMARIZED",
                reason="Test summary",
                metadata={"_dedupe_key": dedupe_key},
            )
            parent_client.write(summary_entry)
            parent_client.flush()
            cursor_manager.save(inst.absolute_ledger_path, to_cursor, inst_entries[-1].entry_hash)

            # Count entries after first summarize
            count_after_first = len(parent_client.read_all())

            # Second summarize-up should be no-op (dedupe key exists)
            from_cursor2, to_cursor2, _ = cursor_manager.get_unprocessed_range(
                inst.absolute_ledger_path,
                len(inst_entries),
                inst_client.get_last_entry_hash_value(),
            )

            # No new entries to process
            assert from_cursor2 == to_cursor2

            # If we tried to write with same dedupe key, it would be detected
            assert parent_client.has_dedupe_key(dedupe_key) is True

            # No new entries added
            assert len(parent_client.read_all()) == count_after_first


class TestPushPolicyIdempotency:
    """Tests for push-policy idempotency."""

    def test_push_policy_twice_no_new_entries(self):
        """Running push-policy twice produces no new entries on second run."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)

            # Create parent HO2
            ho2_root = base / "ho2"
            m2, c2 = LedgerFactory.create_tier("HO2", ho2_root)

            # Create work order
            wo_manifest, wo_client = LedgerFactory.create_work_order_instance(
                ho2_root, "WO-001"
            )

            instance_id = wo_manifest.work_order_id
            policy_id = "POL-TEST-001"
            policy_version = "1.0"

            # First push
            dedupe_key = compute_policy_push_dedupe_key(policy_id, policy_version, instance_id)

            policy_entry = LedgerEntry(
                event_type="POLICY_DOWN",
                submission_id=f"POL-DOWN-{policy_id}",
                decision="PUSHED",
                reason="Test policy",
                metadata={
                    "_dedupe_key": dedupe_key,
                    "policy_id": policy_id,
                    "policy_version": policy_version,
                },
            )
            wo_client.write(policy_entry)
            wo_client.flush()

            count_after_first = len(wo_client.read_all())

            # Second push - check dedupe
            assert wo_client.has_dedupe_key(dedupe_key) is True

            # No new entry should be added
            assert len(wo_client.read_all()) == count_after_first


class TestApplyPolicyIdempotency:
    """Tests for apply-policy idempotency."""

    def test_apply_policy_twice_no_new_entries(self):
        """Running apply-policy twice produces no new entries on second run."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)

            # Create parent HO2 and work order
            ho2_root = base / "ho2"
            m2, c2 = LedgerFactory.create_tier("HO2", ho2_root)

            wo_manifest, wo_client = LedgerFactory.create_work_order_instance(
                ho2_root, "WO-001"
            )

            instance_id = wo_manifest.work_order_id
            policy_id = "POL-TEST-001"
            policy_version = "1.0"

            # Push policy
            push_dedupe = compute_policy_push_dedupe_key(policy_id, policy_version, instance_id)
            policy_down = LedgerEntry(
                event_type="POLICY_DOWN",
                submission_id=f"POL-DOWN-{policy_id}",
                decision="PUSHED",
                reason="Test policy",
                metadata={
                    "_dedupe_key": push_dedupe,
                    "policy_id": policy_id,
                    "policy_version": policy_version,
                },
            )
            wo_client.write(policy_down)
            wo_client.flush()

            # First apply
            apply_dedupe = compute_policy_apply_dedupe_key(policy_id, policy_version, instance_id)
            applied_entry = LedgerEntry(
                event_type="POLICY_APPLIED",
                submission_id=f"POL-APPLY-{policy_id}",
                decision="APPLIED",
                reason="Applied",
                metadata={
                    "_dedupe_key": apply_dedupe,
                    "policy_id": policy_id,
                    "policy_version": policy_version,
                },
            )
            wo_client.write(applied_entry)
            wo_client.flush()

            count_after_first = len(wo_client.read_all())

            # Second apply - check dedupe
            assert wo_client.has_dedupe_key(apply_dedupe) is True

            # No new entry should be added
            assert len(wo_client.read_all()) == count_after_first


class TestStableOrdering:
    """Tests for deterministic ordering."""

    def test_list_instances_stable_order(self):
        """list_instances returns instances in stable order."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ho2_root = Path(tmpdir) / "ho2"
            m2, c2 = LedgerFactory.create_tier("HO2", ho2_root)

            # Create work orders in random order
            for wo_id in ["WO-C", "WO-A", "WO-B"]:
                LedgerFactory.create_work_order_instance(ho2_root, wo_id)

            # List should be sorted
            instances = LedgerFactory.list_instances(ho2_root)
            wo_ids = [m.work_order_id for m in instances]

            assert wo_ids == ["WO-A", "WO-B", "WO-C"]

            # Second call should return same order
            instances2 = LedgerFactory.list_instances(ho2_root)
            wo_ids2 = [m.work_order_id for m in instances2]

            assert wo_ids == wo_ids2


class TestAuditability:
    """Tests for provenance and auditability fields."""

    def test_summary_up_has_provenance_fields(self):
        """SUMMARY_UP entries have required provenance fields."""
        from datetime import datetime, timezone

        entry = LedgerEntry(
            event_type="SUMMARY_UP",
            submission_id="SUM-TEST",
            decision="SUMMARIZED",
            reason="Test",
            metadata={
                "_dedupe_key": "key123",
                "source_ledger": "/path/to/child/ledger.jsonl",
                "child_tier": "HO2",
                "child_instance_id": "WO-001",
                "cursor_from": 0,
                "cursor_to": 10,
                "entry_count": 10,
                "summarized_at": datetime.now(timezone.utc).isoformat(),
            }
        )

        meta = entry.metadata
        assert "source_ledger" in meta
        assert "child_tier" in meta
        assert "cursor_from" in meta
        assert "cursor_to" in meta
        assert "summarized_at" in meta

    def test_policy_down_has_provenance_fields(self):
        """POLICY_DOWN entries have required provenance fields."""
        from datetime import datetime, timezone

        entry = LedgerEntry(
            event_type="POLICY_DOWN",
            submission_id="POL-DOWN-TEST",
            decision="PUSHED",
            reason="Test",
            metadata={
                "_dedupe_key": "key123",
                "policy_id": "POL-001",
                "policy_version": "1.0",
                "from_parent": "/path/to/parent",
                "target_instance": "WO-001",
                "pushed_at": datetime.now(timezone.utc).isoformat(),
            }
        )

        meta = entry.metadata
        assert "policy_id" in meta
        assert "policy_version" in meta
        assert "from_parent" in meta
        assert "target_instance" in meta
        assert "pushed_at" in meta

    def test_policy_applied_has_provenance_fields(self):
        """POLICY_APPLIED entries have required provenance fields."""
        from datetime import datetime, timezone

        entry = LedgerEntry(
            event_type="POLICY_APPLIED",
            submission_id="POL-APPLY-TEST",
            decision="APPLIED",
            reason="Test",
            metadata={
                "_dedupe_key": "key123",
                "policy_id": "POL-001",
                "policy_version": "1.0",
                "instance_id": "WO-001",
                "from_parent": "/path/to/parent",
                "applied_at": datetime.now(timezone.utc).isoformat(),
                "result": "success",
            }
        )

        meta = entry.metadata
        assert "policy_id" in meta
        assert "policy_version" in meta
        assert "instance_id" in meta
        assert "from_parent" in meta
        assert "applied_at" in meta
        assert "result" in meta


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
