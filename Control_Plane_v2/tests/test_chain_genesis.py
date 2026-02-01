#!/usr/bin/env python3
"""
test_chain_genesis.py - Tests for GENESIS entries, instance creation, and chain verification.

Tests Phase 2 multi-plane features:
- GENESIS entry enforcement
- Work-order and session instance creation
- Entry stamping with tier metadata
- Cross-chain verification
"""

import json
import sys
import tempfile
from pathlib import Path

import pytest

# Add repo root for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.ledger_client import LedgerClient, LedgerEntry, TierContext
from lib.ledger_factory import LedgerFactory, _get_parent_hash
from lib.tier_manifest import TierManifest


class TestTierContext:
    """Tests for TierContext dataclass."""

    def test_tier_context_creation(self):
        """TierContext can be created with required fields."""
        ctx = TierContext(
            tier="HO3",
            plane_root=Path("/tmp/test"),
        )
        assert ctx.tier == "HO3"
        assert ctx.plane_root == Path("/tmp/test")
        assert ctx.work_order_id is None
        assert ctx.session_id is None

    def test_tier_context_with_work_order(self):
        """TierContext can include work_order_id."""
        ctx = TierContext(
            tier="HO2",
            plane_root=Path("/tmp/test"),
            work_order_id="WO-2026-001",
        )
        assert ctx.work_order_id == "WO-2026-001"

    def test_tier_context_with_session(self):
        """TierContext can include session_id."""
        ctx = TierContext(
            tier="HO1",
            plane_root=Path("/tmp/test"),
            session_id="sess-001",
        )
        assert ctx.session_id == "sess-001"

    def test_tier_context_to_metadata(self):
        """TierContext.to_metadata returns stamping dict."""
        ctx = TierContext(
            tier="HO2",
            plane_root=Path("/tmp/test"),
            work_order_id="WO-001",
        )
        meta = ctx.to_metadata()
        assert meta["_tier"] == "HO2"
        assert meta["_plane_root"] == "/tmp/test"
        assert meta["_work_order_id"] == "WO-001"
        assert "_session_id" not in meta


class TestGenesisEntry:
    """Tests for GENESIS entry creation and validation."""

    def test_new_ledger_has_genesis(self):
        """New ledger via create_tier starts with GENESIS."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            manifest, client = LedgerFactory.create_tier("HO3", root)

            entries = client.read_all()
            assert len(entries) == 1
            assert entries[0].event_type == "GENESIS"
            assert entries[0].submission_id == "GENESIS"
            assert entries[0].decision == "CHAIN_INITIALIZED"

    def test_genesis_contains_tier_metadata(self):
        """GENESIS entry has tier, plane_root, parent_ledger."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            manifest, client = LedgerFactory.create_tier("HO2", root)

            entries = client.read_all()
            genesis = entries[0]

            assert genesis.metadata["tier"] == "HO2"
            assert genesis.metadata["plane_root"] == str(root)
            assert "created_at" in genesis.metadata

    def test_genesis_with_parent_ledger(self):
        """GENESIS includes parent_ledger when specified."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ho3_root = Path(tmpdir) / "ho3"
            ho2_root = Path(tmpdir) / "ho2"

            # Create parent first
            m3, c3 = LedgerFactory.create_tier("HO3", ho3_root)

            # Create child with parent
            m2, c2 = LedgerFactory.create_tier(
                "HO2",
                ho2_root,
                parent_ledger=str(m3.absolute_ledger_path),
            )

            entries = c2.read_all()
            genesis = entries[0]

            assert genesis.metadata["parent_ledger"] == str(m3.absolute_ledger_path)

    def test_genesis_parent_hash_links(self):
        """GENESIS parent_hash matches parent ledger's last entry."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ho3_root = Path(tmpdir) / "ho3"
            ho2_root = Path(tmpdir) / "ho2"

            # Create parent first
            m3, c3 = LedgerFactory.create_tier("HO3", ho3_root)

            # Get parent's last entry hash
            parent_entries = c3.read_all()
            expected_hash = parent_entries[-1].entry_hash

            # Create child with parent
            m2, c2 = LedgerFactory.create_tier(
                "HO2",
                ho2_root,
                parent_ledger=str(m3.absolute_ledger_path),
            )

            entries = c2.read_all()
            genesis = entries[0]

            assert genesis.metadata["parent_hash"] == expected_hash

    def test_cannot_write_genesis_twice(self):
        """write_genesis raises ValueError on non-empty ledger."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            manifest, client = LedgerFactory.create_tier("HO3", root)

            # Try to write another GENESIS
            with pytest.raises(ValueError, match="Cannot write GENESIS to non-empty ledger"):
                client.write_genesis(
                    tier="HO3",
                    plane_root=root,
                )


class TestVerifyGenesis:
    """Tests for verify_genesis method."""

    def test_verify_genesis_valid(self):
        """verify_genesis passes for valid GENESIS entry."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            manifest, client = LedgerFactory.create_tier("HO3", root)

            valid, issues = client.verify_genesis()
            assert valid is True
            assert len([i for i in issues if i.startswith("FAIL")]) == 0

    def test_verify_genesis_empty_ledger(self):
        """verify_genesis fails on empty ledger."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger_path = Path(tmpdir) / "empty.jsonl"
            ledger_path.touch()

            client = LedgerClient(ledger_path=ledger_path)
            valid, issues = client.verify_genesis()

            assert valid is False
            assert any("empty" in i.lower() for i in issues)

    def test_verify_genesis_non_genesis_first(self):
        """verify_genesis warns when first entry is not GENESIS."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a valid plane structure first
            root = Path(tmpdir).resolve()
            (root / "ledger").mkdir(parents=True)
            ledger_path = root / "ledger" / "test.jsonl"

            # Write a non-GENESIS entry directly to file (bypassing pristine check)
            entry = LedgerEntry(
                event_type="TEST",
                submission_id="TEST-001",
                decision="TEST",
                reason="Test entry",
            )
            entry.previous_hash = ""
            entry_dict = {k: v for k, v in entry.__dict__.items()}
            import json
            entry_json = json.dumps(entry_dict, ensure_ascii=False)
            ledger_path.write_text(entry_json + "\n")

            client = LedgerClient(ledger_path=ledger_path)
            valid, issues = client.verify_genesis()
            # Should pass (no FAIL) but have a warning
            assert valid is True
            assert any("not GENESIS" in i for i in issues)


class TestVerifyChainLink:
    """Tests for verify_chain_link method."""

    def test_verify_chain_link_valid(self):
        """verify_chain_link passes when parent_hash matches."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ho3_root = Path(tmpdir) / "ho3"
            ho2_root = Path(tmpdir) / "ho2"

            m3, c3 = LedgerFactory.create_tier("HO3", ho3_root)
            m2, c2 = LedgerFactory.create_tier(
                "HO2",
                ho2_root,
                parent_ledger=str(m3.absolute_ledger_path),
            )

            valid, issues = c2.verify_chain_link(m3.absolute_ledger_path)
            assert valid is True
            assert len([i for i in issues if i.startswith("FAIL")]) == 0

    def test_verify_chain_link_no_parent(self):
        """verify_chain_link passes for root ledger (no parent)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            manifest, client = LedgerFactory.create_tier("HO3", root)

            # Root ledger has no parent_hash
            valid, issues = client.verify_chain_link(Path("/nonexistent"))
            # Should pass with INFO about no parent
            assert valid is True
            assert any("No parent_hash" in i or "INFO" in i for i in issues)

    def test_verify_chain_link_broken(self):
        """verify_chain_link fails when parent_hash mismatches."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ho3_root = Path(tmpdir) / "ho3"
            ho2_root = Path(tmpdir) / "ho2"

            m3, c3 = LedgerFactory.create_tier("HO3", ho3_root)

            # Add another entry to parent to change the hash
            c3.write(LedgerEntry(
                event_type="TEST",
                submission_id="TEST-001",
                decision="APPROVED",
                reason="Test",
            ))
            c3.flush()

            # Get the current last hash
            current_last_hash = c3.get_last_entry_hash_value()

            # Create HO2 normally first
            m2, c2 = LedgerFactory.create_tier(
                "HO2",
                ho2_root,
                parent_ledger=str(m3.absolute_ledger_path),
            )

            # Now add another entry to parent, breaking the chain link
            c3.write(LedgerEntry(
                event_type="TEST",
                submission_id="TEST-002",
                decision="APPROVED",
                reason="This breaks the chain",
            ))
            c3.flush()

            # verify_chain_link should now fail because parent has new entries
            valid, issues = c2.verify_chain_link(m3.absolute_ledger_path)
            assert valid is False
            assert any("mismatch" in i.lower() for i in issues)


class TestInstanceCreation:
    """Tests for work-order and session instance creation."""

    def test_create_work_order_instance(self):
        """create_work_order_instance creates HO2 instance with correct structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ho2_root = Path(tmpdir).resolve() / "ho2"
            m2, c2 = LedgerFactory.create_tier("HO2", ho2_root)

            manifest, client = LedgerFactory.create_work_order_instance(
                base_root=ho2_root,
                work_order_id="WO-2026-001",
            )

            assert manifest.tier == "HO2"
            assert manifest.work_order_id == "WO-2026-001"
            assert manifest.tier_root == ho2_root / "work_orders" / "WO-2026-001"
            assert manifest.parent_ledger is not None

    def test_create_session_instance(self):
        """create_session_instance creates HO1 instance with correct structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ho1_root = Path(tmpdir).resolve() / "ho1"
            m1, c1 = LedgerFactory.create_tier("HO1", ho1_root)

            manifest, client = LedgerFactory.create_session_instance(
                base_root=ho1_root,
                session_id="sess-001",
            )

            assert manifest.tier == "HO1"
            assert manifest.session_id == "sess-001"
            assert manifest.tier_root == ho1_root / "sessions" / "sess-001"
            assert manifest.parent_ledger is not None

    def test_work_order_wrong_tier(self):
        """create_work_order_instance rejects non-HO2 base."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ho3_root = Path(tmpdir) / "ho3"
            m3, c3 = LedgerFactory.create_tier("HO3", ho3_root)

            with pytest.raises(ValueError, match="must be HO2"):
                LedgerFactory.create_work_order_instance(
                    base_root=ho3_root,
                    work_order_id="WO-001",
                )

    def test_session_wrong_tier(self):
        """create_session_instance rejects non-HO1 base."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ho2_root = Path(tmpdir) / "ho2"
            m2, c2 = LedgerFactory.create_tier("HO2", ho2_root)

            with pytest.raises(ValueError, match="must be HO1"):
                LedgerFactory.create_session_instance(
                    base_root=ho2_root,
                    session_id="sess-001",
                )

    def test_instance_ledger_has_genesis(self):
        """Instance ledger starts with GENESIS linking to parent."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ho2_root = Path(tmpdir) / "ho2"
            m2, c2 = LedgerFactory.create_tier("HO2", ho2_root)

            inst_manifest, inst_client = LedgerFactory.create_work_order_instance(
                base_root=ho2_root,
                work_order_id="WO-001",
            )

            entries = inst_client.read_all()
            assert len(entries) == 1
            assert entries[0].event_type == "GENESIS"
            assert entries[0].metadata["work_order_id"] == "WO-001"

    def test_list_instances(self):
        """list_instances shows all instances under base plane."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ho2_root = Path(tmpdir) / "ho2"
            m2, c2 = LedgerFactory.create_tier("HO2", ho2_root)

            # Create multiple work orders
            LedgerFactory.create_work_order_instance(ho2_root, "WO-001")
            LedgerFactory.create_work_order_instance(ho2_root, "WO-002")

            instances = LedgerFactory.list_instances(ho2_root)
            assert len(instances) == 2

            wo_ids = {m.work_order_id for m in instances}
            assert wo_ids == {"WO-001", "WO-002"}


class TestEntryStamping:
    """Tests for automatic entry stamping with tier metadata."""

    def test_entries_include_tier_metadata(self):
        """Entries written include _tier in metadata."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            manifest, client = LedgerFactory.create_tier("HO3", root)

            # Write a test entry
            entry = LedgerEntry(
                event_type="TEST",
                submission_id="TEST-001",
                decision="APPROVED",
                reason="Test",
            )
            client.write(entry)
            client.flush()

            entries = client.read_all()
            # Second entry (after GENESIS)
            test_entry = entries[1]
            assert test_entry.metadata.get("_tier") == "HO3"
            assert "_plane_root" in test_entry.metadata

    def test_work_order_entries_include_wo_id(self):
        """Entries in work-order instance include _work_order_id."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ho2_root = Path(tmpdir) / "ho2"
            m2, c2 = LedgerFactory.create_tier("HO2", ho2_root)

            inst_manifest, inst_client = LedgerFactory.create_work_order_instance(
                base_root=ho2_root,
                work_order_id="WO-001",
            )

            # Write a test entry to the instance
            entry = LedgerEntry(
                event_type="TEST",
                submission_id="TEST-001",
                decision="APPROVED",
                reason="Test",
            )
            inst_client.write(entry)
            inst_client.flush()

            entries = inst_client.read_all()
            test_entry = entries[1]  # After GENESIS
            assert test_entry.metadata.get("_work_order_id") == "WO-001"

    def test_session_entries_include_session_id(self):
        """Entries in session instance include _session_id."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ho1_root = Path(tmpdir) / "ho1"
            m1, c1 = LedgerFactory.create_tier("HO1", ho1_root)

            inst_manifest, inst_client = LedgerFactory.create_session_instance(
                base_root=ho1_root,
                session_id="sess-001",
            )

            # Write a test entry to the instance
            entry = LedgerEntry(
                event_type="TEST",
                submission_id="TEST-001",
                decision="APPROVED",
                reason="Test",
            )
            inst_client.write(entry)
            inst_client.flush()

            entries = inst_client.read_all()
            test_entry = entries[1]  # After GENESIS
            assert test_entry.metadata.get("_session_id") == "sess-001"


class TestGetParentHash:
    """Tests for _get_parent_hash helper."""

    def test_get_parent_hash_returns_last_hash(self):
        """_get_parent_hash returns last entry's hash."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            manifest, client = LedgerFactory.create_tier("HO3", root)

            entries = client.read_all()
            expected_hash = entries[-1].entry_hash

            result = _get_parent_hash(str(manifest.absolute_ledger_path))
            assert result == expected_hash

    def test_get_parent_hash_nonexistent(self):
        """_get_parent_hash returns None for nonexistent file."""
        result = _get_parent_hash("/nonexistent/ledger.jsonl")
        assert result is None


class TestGetLastEntryHashValue:
    """Tests for get_last_entry_hash_value method."""

    def test_get_last_entry_hash_value(self):
        """get_last_entry_hash_value returns the hash."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            manifest, client = LedgerFactory.create_tier("HO3", root)

            result = client.get_last_entry_hash_value()
            entries = client.read_all()
            assert result == entries[-1].entry_hash

    def test_get_last_entry_hash_value_empty(self):
        """get_last_entry_hash_value returns None for empty ledger."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger_path = Path(tmpdir) / "empty.jsonl"
            ledger_path.touch()

            client = LedgerClient(ledger_path=ledger_path)
            result = client.get_last_entry_hash_value()
            assert result is None


class TestChainHierarchy:
    """Tests for full chain hierarchy."""

    def test_three_level_chain(self):
        """Full HO3 -> HO2 -> HO1 chain can be created."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)

            # Create HO3
            m3, c3 = LedgerFactory.create_tier("HO3", base / "ho3")

            # Create HO2 with parent
            m2, c2 = LedgerFactory.create_tier(
                "HO2",
                base / "ho2",
                parent_ledger=str(m3.absolute_ledger_path),
            )

            # Create HO1 with parent
            m1, c1 = LedgerFactory.create_tier(
                "HO1",
                base / "ho1",
                parent_ledger=str(m2.absolute_ledger_path),
            )

            # Verify chain links
            valid3, _ = c3.verify_genesis()
            valid2, _ = c2.verify_genesis()
            valid1, _ = c1.verify_genesis()

            assert valid3 and valid2 and valid1

            # Verify parent links
            link_valid2, _ = c2.verify_chain_link(m3.absolute_ledger_path)
            link_valid1, _ = c1.verify_chain_link(m2.absolute_ledger_path)

            assert link_valid2
            assert link_valid1

    def test_work_order_chain(self):
        """Work order links to parent HO2."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ho2_root = Path(tmpdir) / "ho2"
            m2, c2 = LedgerFactory.create_tier("HO2", ho2_root)

            wo_manifest, wo_client = LedgerFactory.create_work_order_instance(
                ho2_root, "WO-001"
            )

            # Verify work order links to HO2
            parent_path = (wo_manifest.tier_root / wo_manifest.parent_ledger).resolve()
            valid, issues = wo_client.verify_chain_link(parent_path)

            assert valid, f"Chain link failed: {issues}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
