#!/usr/bin/env python3
"""
test_cross_tier_provenance.py - Tests for cross-tier linkage (FMWK-000 Phase 2).

Tests:
1. HO1 requires valid WO reference
2. Session ledger proves WO linkage
3. HOT proves completion via hash references
4. Failed WO leaves no success summary
"""

import hashlib
import json
import pytest
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add parent to path for lib imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kernel.ledger_client import LedgerClient, LedgerEntry
from kernel.ledger_factory import LedgerFactory
from kernel.tier_manifest import TierManifest


def create_test_plane_structure(tmp_path: Path) -> Path:
    """Create full test plane structure with HO3, HO2, HO1 tiers."""
    # HO3 (root)
    (tmp_path / 'ledger').mkdir(parents=True)
    (tmp_path / 'config').mkdir()

    # HO2
    ho2_root = tmp_path / 'planes' / 'ho2'
    (ho2_root / 'ledger').mkdir(parents=True)
    (ho2_root / 'work_orders').mkdir()

    # HO1
    ho1_root = tmp_path / 'planes' / 'ho1'
    (ho1_root / 'ledger').mkdir(parents=True)
    (ho1_root / 'sessions').mkdir()

    # Create tier.json files
    ho3_manifest = {
        "tier": "HO3",
        "tier_root": str(tmp_path),
        "ledger_path": "ledger/governance.jsonl",
        "parent_ledger": None,
        "status": "active",
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    (tmp_path / 'tier.json').write_text(json.dumps(ho3_manifest, indent=2))

    ho2_manifest = {
        "tier": "HO2",
        "tier_root": str(ho2_root),
        "ledger_path": "ledger/workorder.jsonl",
        "parent_ledger": "../../ledger/governance.jsonl",
        "status": "active",
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    (ho2_root / 'tier.json').write_text(json.dumps(ho2_manifest, indent=2))

    ho1_manifest = {
        "tier": "HO1",
        "tier_root": str(ho1_root),
        "ledger_path": "ledger/worker.jsonl",
        "parent_ledger": "../ho2/ledger/workorder.jsonl",
        "status": "active",
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    (ho1_root / 'tier.json').write_text(json.dumps(ho1_manifest, indent=2))

    # Initialize ledgers with GENESIS
    for ledger_path in [
        tmp_path / 'ledger' / 'governance.jsonl',
        ho2_root / 'ledger' / 'workorder.jsonl',
        ho1_root / 'ledger' / 'worker.jsonl'
    ]:
        ledger_path.touch()

    return tmp_path


class TestHO1RequiresValidWORef:
    """Test 1: HO1 session must have valid WO reference."""

    def test_session_requires_wo_instance_path(self, tmp_path):
        """Session creation requires wo_instance_ledger_path."""
        plane_root = create_test_plane_structure(tmp_path)
        ho1_root = plane_root / 'planes' / 'ho1'

        # Create session with valid WO reference
        session_id = "SESSION-20260202-001"
        wo_instance_path = "planes/ho2/work_orders/WO-20260202-001/ledger/execution.jsonl"

        manifest, client = LedgerFactory.create_session_instance_with_linkage(
            ho1_base_root=ho1_root,
            session_id=session_id,
            work_order_id="WO-20260202-001",
            wo_instance_ledger_path=wo_instance_path,
            wo_instance_hash="sha256:test123"
        )

        # Verify session created with linkage
        assert manifest.session_id == session_id
        assert manifest.tier == "HO1"

        # Read back and verify SESSION_START event
        entries = client.read_all()
        session_start = next(
            (e for e in entries if e.event_type == 'SESSION_START'),
            None
        )

        assert session_start is not None
        assert session_start.metadata.get('wo_id') == "WO-20260202-001"
        assert session_start.metadata.get('wo_instance_ledger_path') == wo_instance_path


class TestSessionLedgerProvesWOLinkage:
    """Test 2: Session ledger replay proves WO linkage."""

    def test_session_ledger_contains_wo_reference(self, tmp_path):
        """SESSION_START must contain wo_instance_ledger_path and hash."""
        plane_root = create_test_plane_structure(tmp_path)
        ho1_root = plane_root / 'planes' / 'ho1'

        session_id = "SESSION-20260202-001"
        wo_id = "WO-20260202-001"
        wo_instance_path = "planes/ho2/work_orders/WO-20260202-001/ledger/execution.jsonl"
        wo_instance_hash = "sha256:abc123def456"

        manifest, client = LedgerFactory.create_session_instance_with_linkage(
            ho1_base_root=ho1_root,
            session_id=session_id,
            work_order_id=wo_id,
            wo_instance_ledger_path=wo_instance_path,
            wo_instance_hash=wo_instance_hash
        )

        # Read session ledger
        entries = client.read_all()

        # Find SESSION_START
        session_start = next(
            (e for e in entries if e.event_type == 'SESSION_START'),
            None
        )

        # Verify linkage fields
        assert session_start is not None
        assert session_start.metadata['wo_id'] == wo_id
        assert session_start.metadata['wo_instance_ledger_path'] == wo_instance_path
        assert session_start.metadata['wo_instance_hash'] == wo_instance_hash


class TestHOTProvesCompletionViaRefs:
    """Test 3: HOT WO_ATTESTATION proves completion via hash references."""

    def test_attestation_references_ho2_hash(self, tmp_path):
        """WO_ATTESTATION must reference HO2 completion hash."""
        plane_root = create_test_plane_structure(tmp_path)

        # Create HOT governance ledger
        governance_path = plane_root / 'ledger' / 'governance.jsonl'
        client = LedgerClient(ledger_path=governance_path)

        wo_id = "WO-20260202-001"
        ho2_completion_hash = "sha256:ho2completionhash123"

        # Write WO_ATTESTATION
        entry = LedgerEntry(
            event_type='WO_ATTESTATION',
            submission_id=wo_id,
            decision='SUCCESS',
            reason='Work Order execution attested',
            metadata={
                'wo_id': wo_id,
                'result_status': 'success',
                'ho2_completion_hash': ho2_completion_hash,
                'attested_at': datetime.now(timezone.utc).isoformat(),
            }
        )
        client.write(entry)
        client.flush()

        # Read back and verify
        entries = client.read_by_event_type('WO_ATTESTATION')
        attestation = entries[0]

        assert attestation.metadata['wo_id'] == wo_id
        assert attestation.metadata['ho2_completion_hash'] == ho2_completion_hash
        assert attestation.metadata['result_status'] == 'success'


class TestFailedWONoSuccessSummary:
    """Test 4: Failed WO must not leave WO_COMPLETED with success status."""

    def test_failed_wo_has_failed_status(self, tmp_path):
        """Failed WO must record FAILED status, not success."""
        plane_root = create_test_plane_structure(tmp_path)
        ho2_root = plane_root / 'planes' / 'ho2'

        # Create HO2 workorder ledger
        ledger_path = ho2_root / 'ledger' / 'workorder.jsonl'
        client = LedgerClient(ledger_path=ledger_path)

        wo_id = "WO-20260202-FAIL"

        # Write WO_COMPLETED with FAILED status
        entry = LedgerEntry(
            event_type='WO_COMPLETED',
            submission_id=wo_id,
            decision='FAILED',
            reason='Work Order failed at G4',
            metadata={
                'wo_id': wo_id,
                'wo_payload_hash': 'sha256:test',
                'result_status': 'failed',
                'status': 'FAILED',
                'completed_at': datetime.now(timezone.utc).isoformat(),
            }
        )
        client.write(entry)
        client.flush()

        # Read back
        entries = client.read_by_event_type('WO_COMPLETED')
        completion = entries[0]

        # Verify NOT success
        assert completion.decision == 'FAILED'
        assert completion.metadata['status'] == 'FAILED'
        assert completion.metadata['result_status'] == 'failed'

    def test_successful_wo_has_success_status(self, tmp_path):
        """Successful WO must record COMPLETED/success status."""
        plane_root = create_test_plane_structure(tmp_path)
        ho2_root = plane_root / 'planes' / 'ho2'

        ledger_path = ho2_root / 'ledger' / 'workorder.jsonl'
        client = LedgerClient(ledger_path=ledger_path)

        wo_id = "WO-20260202-SUCCESS"

        # Write WO_COMPLETED with SUCCESS status
        entry = LedgerEntry(
            event_type='WO_COMPLETED',
            submission_id=wo_id,
            decision='SUCCESS',
            reason='Work Order completed successfully',
            metadata={
                'wo_id': wo_id,
                'wo_payload_hash': 'sha256:test',
                'result_status': 'success',
                'status': 'COMPLETED',
                'completed_at': datetime.now(timezone.utc).isoformat(),
            }
        )
        client.write(entry)
        client.flush()

        # Read back
        entries = client.read_by_event_type('WO_COMPLETED')
        completion = entries[0]

        # Verify success
        assert completion.decision == 'SUCCESS'
        assert completion.metadata['status'] == 'COMPLETED'


class TestCrossTierChain:
    """Test the full cross-tier provenance chain."""

    def test_full_chain_hot_to_ho1(self, tmp_path):
        """Verify full chain: HOT approval -> HO2 received -> HO1 session."""
        plane_root = create_test_plane_structure(tmp_path)

        wo_id = "WO-20260202-CHAIN"
        wo_hash = "sha256:chaintest123"

        # 1. Write WO_APPROVED in HOT
        governance_path = plane_root / 'ledger' / 'governance.jsonl'
        hot_client = LedgerClient(ledger_path=governance_path)

        approval_entry = LedgerEntry(
            event_type='WO_APPROVED',
            submission_id=wo_id,
            decision='APPROVED',
            reason='Test approval',
            metadata={
                'wo_id': wo_id,
                'wo_payload_hash': wo_hash,
                'approver_key_id': 'test-key',
            }
        )
        hot_client.write(approval_entry)
        hot_client.flush()

        # Get approval hash
        entries = hot_client.read_all()
        approval_hash = entries[-1].entry_hash

        # 2. Write WO_RECEIVED in HO2
        ho2_ledger_path = plane_root / 'planes' / 'ho2' / 'ledger' / 'workorder.jsonl'
        ho2_client = LedgerClient(ledger_path=ho2_ledger_path)

        received_entry = LedgerEntry(
            event_type='WO_RECEIVED',
            submission_id=wo_id,
            decision='ACCEPTED',
            reason='G2 passed',
            metadata={
                'wo_id': wo_id,
                'wo_payload_hash': wo_hash,
                'hot_approval_hash': approval_hash,
            }
        )
        ho2_client.write(received_entry)
        ho2_client.flush()

        # 3. Create session in HO1 with WO linkage
        ho1_root = plane_root / 'planes' / 'ho1'
        session_id = "SESSION-20260202-CHAIN"

        session_manifest, session_client = LedgerFactory.create_session_instance_with_linkage(
            ho1_base_root=ho1_root,
            session_id=session_id,
            work_order_id=wo_id,
            wo_instance_ledger_path="planes/ho2/work_orders/WO-20260202-CHAIN/ledger/execution.jsonl",
            wo_instance_hash="sha256:woinstance"
        )

        # Verify chain
        # HOT has WO_APPROVED
        hot_entries = hot_client.read_by_event_type('WO_APPROVED')
        assert len(hot_entries) == 1
        assert hot_entries[0].metadata['wo_id'] == wo_id

        # HO2 has WO_RECEIVED with HOT reference
        ho2_entries = ho2_client.read_by_event_type('WO_RECEIVED')
        assert len(ho2_entries) == 1
        assert ho2_entries[0].metadata['hot_approval_hash'] == approval_hash

        # HO1 session has WO reference
        session_entries = session_client.read_by_event_type('SESSION_START')
        assert len(session_entries) == 1
        assert session_entries[0].metadata['wo_id'] == wo_id


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
