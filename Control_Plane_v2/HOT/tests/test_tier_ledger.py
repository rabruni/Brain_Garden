#!/usr/bin/env python3
"""
test_tier_ledger.py - Tests for multi-tier ledger capability.

Verifies:
1. Index isolation - multiple ledgers don't share indexes
2. Backward compatibility - default LedgerClient works unchanged
3. Tier creation - LedgerFactory.create_tier works
4. Archive lifecycle - archive/close status updates
5. Pristine enforcement - tier ledgers are append-only

Per tier-agnostic ledger capability spec.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kernel.ledger_client import LedgerClient, LedgerEntry
from kernel.ledger_factory import LedgerFactory
from kernel.tier_manifest import TierManifest
from kernel.pristine import classify_path, PathClass, is_tier_ledger_path


class TestIndexIsolation:
    """Test that multiple ledgers have isolated indexes."""

    def test_two_ledgers_separate_indexes(self):
        """Two ledgers should not share index directories."""
        with tempfile.TemporaryDirectory() as tmp:
            path_a = Path(tmp) / "a" / "log.jsonl"
            path_b = Path(tmp) / "b" / "log.jsonl"

            client_a = LedgerClient(ledger_path=path_a)
            client_b = LedgerClient(ledger_path=path_b)

            # Index dirs should be different
            assert client_a.index_dir != client_b.index_dir
            assert client_a.segment_index_path != client_b.segment_index_path

            # Index dirs should be relative to each ledger
            assert client_a.index_dir == path_a.parent / "idx"
            assert client_b.index_dir == path_b.parent / "idx"

    def test_no_cross_contamination(self):
        """Entries in one ledger shouldn't appear in another."""
        with tempfile.TemporaryDirectory() as tmp:
            # Create proper tiers so ledgers are append-only
            _, client_a = LedgerFactory.create_tier(
                tier="FIRST",
                tier_root=Path(tmp) / "tier-a",
                session_id="a"
            )
            _, client_b = LedgerFactory.create_tier(
                tier="FIRST",
                tier_root=Path(tmp) / "tier-b",
                session_id="b"
            )

            # Write to ledger A
            entry_a = LedgerEntry(
                event_type="test",
                submission_id="SUB-A",
                decision="OK",
                reason="Test entry A"
            )
            client_a.write(entry_a)
            client_a.flush()

            # Write to ledger B
            entry_b = LedgerEntry(
                event_type="test",
                submission_id="SUB-B",
                decision="OK",
                reason="Test entry B"
            )
            client_b.write(entry_b)
            client_b.flush()

            # Check no cross-contamination
            assert len(client_a.read_by_submission("SUB-A")) == 1
            assert len(client_a.read_by_submission("SUB-B")) == 0
            assert len(client_b.read_by_submission("SUB-B")) == 1
            assert len(client_b.read_by_submission("SUB-A")) == 0


class TestBackwardCompatibility:
    """Test that existing code continues to work."""

    def test_default_client_paths(self):
        """Default LedgerClient should use governance.jsonl paths."""
        client = LedgerClient()

        assert "governance.jsonl" in str(client.ledger_path)
        assert "ledger/idx" in str(client.index_dir)
        assert "ledger/index.jsonl" in str(client.segment_index_path)

    def test_factory_default_equals_direct(self):
        """LedgerFactory.default() should match LedgerClient()."""
        direct = LedgerClient()
        factory = LedgerFactory.default()

        assert direct.ledger_path == factory.ledger_path
        assert direct.index_dir == factory.index_dir


class TestTierCreation:
    """Test tier creation via LedgerFactory."""

    def test_create_first_tier(self):
        """Create a FIRST tier (HO1 in canonical naming) and verify structure."""
        with tempfile.TemporaryDirectory() as tmp:
            manifest, client = LedgerFactory.create_tier(
                tier="FIRST",  # Legacy name, migrates to HO1
                tier_root=Path(tmp) / "worker-001",
                session_id="sess-test-001",
                parent_ledger="../hot/governance.jsonl"
            )

            # Verify manifest (FIRST migrates to HO1)
            assert manifest.tier == "HO1"
            assert manifest.session_id == "sess-test-001"
            assert manifest.status == "active"
            assert manifest.parent_ledger == "../hot/governance.jsonl"

            # Verify files exist
            assert manifest.manifest_path.exists()
            assert client.ledger_path.exists()
            assert client.index_dir.exists()

    def test_create_second_tier(self):
        """Create a SECOND tier (HO2 in canonical naming) with work order."""
        with tempfile.TemporaryDirectory() as tmp:
            manifest, client = LedgerFactory.create_tier(
                tier="SECOND",  # Legacy name, migrates to HO2
                tier_root=Path(tmp) / "WO-2026-001",
                work_order_id="WO-2026-001"
            )

            # SECOND migrates to HO2
            assert manifest.tier == "HO2"
            assert manifest.work_order_id == "WO-2026-001"
            assert "workorder.jsonl" in str(manifest.ledger_path)  # HO2 uses workorder.jsonl

    def test_duplicate_tier_fails(self):
        """Creating tier in existing location should fail."""
        with tempfile.TemporaryDirectory() as tmp:
            tier_root = Path(tmp) / "existing"

            # Create first
            LedgerFactory.create_tier(tier="FIRST", tier_root=tier_root)

            # Second should fail
            with pytest.raises(ValueError, match="Tier already exists"):
                LedgerFactory.create_tier(tier="FIRST", tier_root=tier_root)


class TestArchiveLifecycle:
    """Test tier archive and close lifecycle."""

    def test_archive_updates_status(self):
        """Archive should update manifest status."""
        with tempfile.TemporaryDirectory() as tmp:
            manifest, _ = LedgerFactory.create_tier(
                tier="FIRST",
                tier_root=Path(tmp) / "worker"
            )

            assert manifest.status == "active"

            archived = LedgerFactory.archive(manifest.manifest_path)
            assert archived.status == "archived"

            # Reload and verify persisted
            reloaded = TierManifest.load(manifest.manifest_path)
            assert reloaded.status == "archived"

    def test_close_updates_status(self):
        """Close should update manifest status to closed."""
        with tempfile.TemporaryDirectory() as tmp:
            manifest, _ = LedgerFactory.create_tier(
                tier="FIRST",
                tier_root=Path(tmp) / "worker"
            )

            closed = LedgerFactory.close(manifest.manifest_path)
            assert closed.status == "closed"


class TestPristineEnforcement:
    """Test that tier ledgers are classified correctly."""

    def test_external_path_is_external(self):
        """Non-tier external paths should be EXTERNAL."""
        path = Path("/tmp/random/not-a-tier/file.txt")
        assert classify_path(path) == PathClass.EXTERNAL

    def test_tier_ledger_is_append_only(self):
        """Tier ledger paths should be APPEND_ONLY."""
        with tempfile.TemporaryDirectory() as tmp:
            manifest, client = LedgerFactory.create_tier(
                tier="FIRST",
                tier_root=Path(tmp) / "tier"
            )

            # Ledger file should be append-only
            assert is_tier_ledger_path(client.ledger_path)
            assert classify_path(client.ledger_path) == PathClass.APPEND_ONLY

    def test_is_tier_ledger_path_walk_up(self):
        """is_tier_ledger_path should find manifest by walking up."""
        with tempfile.TemporaryDirectory() as tmp:
            tier_root = Path(tmp) / "my-tier"
            manifest, client = LedgerFactory.create_tier(tier="FIRST", tier_root=tier_root)

            # The actual ledger file should be recognized
            assert is_tier_ledger_path(client.ledger_path)

            # Files directly in ledger directory should also be recognized
            sibling_path = tier_root / "ledger" / "another.jsonl"
            sibling_path.touch()
            assert is_tier_ledger_path(sibling_path)


class TestTierDiscovery:
    """Test tier discovery and listing."""

    def test_list_tiers(self):
        """list_tiers should find all tier manifests."""
        with tempfile.TemporaryDirectory() as tmp:
            # Create multiple tiers using legacy names (they get migrated)
            LedgerFactory.create_tier(
                tier="HOT",  # -> HO3
                tier_root=Path(tmp) / "hot"
            )
            LedgerFactory.create_tier(
                tier="SECOND",  # -> HO1 (lowest)
                tier_root=Path(tmp) / "meta" / "WO-001",
                work_order_id="WO-001"
            )
            LedgerFactory.create_tier(
                tier="FIRST",  # -> HO2 (middle)
                tier_root=Path(tmp) / "exec" / "worker-001",
                session_id="sess-001"
            )

            tiers = LedgerFactory.list_tiers(Path(tmp))
            assert len(tiers) == 3

            # Legacy names migrate to canonical: HOT->HO3, SECOND->HO2, FIRST->HO1
            tier_types = {t.tier for t in tiers}
            assert tier_types == {"HO3", "HO2", "HO1"}

    def test_find_for_path(self):
        """TierManifest.find_for_path should find enclosing tier."""
        with tempfile.TemporaryDirectory() as tmp:
            manifest, client = LedgerFactory.create_tier(
                tier="FIRST",  # -> HO1
                tier_root=Path(tmp) / "worker"
            )

            found = TierManifest.find_for_path(client.ledger_path)
            assert found is not None
            assert found.tier == "HO1"  # FIRST migrates to HO1


class TestChainVerification:
    """Test that chain verification works for tier ledgers."""

    def test_tier_chain_valid(self):
        """Entries in tier ledger should have valid chain."""
        with tempfile.TemporaryDirectory() as tmp:
            manifest, client = LedgerFactory.create_tier(
                tier="FIRST",
                tier_root=Path(tmp) / "worker"
            )

            # Write multiple entries
            for i in range(5):
                entry = LedgerEntry(
                    event_type="test",
                    submission_id=f"SUB-{i:03d}",
                    decision="OK",
                    reason=f"Test entry {i}"
                )
                client.write(entry)
            client.flush()

            # Verify chain
            valid, issues = client.verify_chain()
            assert valid, f"Chain invalid: {issues}"
            # 6 entries: 1 GENESIS + 5 test entries
            assert len(client.read_all()) == 6


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
