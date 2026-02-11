#!/usr/bin/env python3
"""
test_g2_gate.py - Tests for G2 WORK_ORDER gate (FMWK-000 Phase 2).

Tests:
1. HO2 rejects unapproved WO
2. Tampered WO rejected (hash mismatch)
3. Idempotent retry (same hash = NO-OP)
4. Replay variant rejected (same ID, different hash)
5. Scope validation
"""

import base64
import hashlib
import json
import os
import pytest
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# Add parent to path for lib imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kernel.ledger_client import LedgerClient, LedgerEntry


def create_test_plane(tmp_path: Path) -> Path:
    """Create minimal test plane structure with tier manifests."""
    # Create directories
    (tmp_path / 'ledger' / 'idx').mkdir(parents=True, exist_ok=True)
    (tmp_path / 'planes' / 'ho2' / 'ledger' / 'idx').mkdir(parents=True, exist_ok=True)
    (tmp_path / 'config').mkdir(parents=True, exist_ok=True)
    (tmp_path / 'work_orders' / 'ho3').mkdir(parents=True, exist_ok=True)
    (tmp_path / 'registries').mkdir(parents=True, exist_ok=True)
    (tmp_path / 'specs').mkdir(parents=True, exist_ok=True)

    # Create tier.json for HO3
    ho3_manifest = {
        "tier": "HO3",
        "tier_root": str(tmp_path),
        "ledger_path": "ledger/governance.jsonl",
        "parent_ledger": None,
        "status": "active",
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    (tmp_path / 'tier.json').write_text(json.dumps(ho3_manifest, indent=2))

    # Create tier.json for HO2
    ho2_manifest = {
        "tier": "HO2",
        "tier_root": str(tmp_path / 'planes' / 'ho2'),
        "ledger_path": "ledger/workorder.jsonl",
        "parent_ledger": "../../ledger/governance.jsonl",
        "status": "active",
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    (tmp_path / 'planes' / 'ho2' / 'tier.json').write_text(json.dumps(ho2_manifest, indent=2))

    # Create minimal governed_roots.json
    governed_roots = {
        "schema_version": "1.0",
        "plane_id": "ho3",
        "governed_roots": ["lib/", "scripts/"],
        "excluded_patterns": ["**/__pycache__/**"]
    }
    (tmp_path / 'config' / 'governed_roots.json').write_text(
        json.dumps(governed_roots, indent=2)
    )

    # Create trusted_keys.json with placeholder
    trusted_keys = {
        "schema_version": "1.0",
        "keys": [
            {
                "key_id": "test-key-001",
                "algorithm": "Ed25519",
                "public_key_b64": "PLACEHOLDER_FOR_TESTING",
                "roles": ["wo_approver"]
            }
        ]
    }
    (tmp_path / 'config' / 'trusted_keys.json').write_text(
        json.dumps(trusted_keys, indent=2)
    )

    # Create empty ledgers with index
    (tmp_path / 'ledger' / 'governance.jsonl').touch()
    (tmp_path / 'ledger' / 'index.jsonl').touch()
    (tmp_path / 'planes' / 'ho2' / 'ledger' / 'workorder.jsonl').touch()
    (tmp_path / 'planes' / 'ho2' / 'ledger' / 'index.jsonl').touch()

    return tmp_path


def create_test_wo(tmp_path: Path, wo_id: str = "WO-20260202-001") -> tuple:
    """Create a test Work Order file.

    Returns:
        (wo_path, wo_data, wo_hash)
    """
    wo_data = {
        "work_order_id": wo_id,
        "type": "code_change",
        "plane_id": "ho3",
        "spec_id": "SPEC-TEST-001",
        "framework_id": "FMWK-000",
        "scope": {
            "allowed_files": ["lib/test.py"],
            "forbidden_files": []
        },
        "acceptance": {
            "tests": ["echo test"],
            "checks": []
        }
    }

    wo_path = tmp_path / 'work_orders' / 'ho3' / f'{wo_id}.json'
    wo_path.write_text(json.dumps(wo_data, indent=2))

    # Compute hash
    canonical = json.dumps(wo_data, sort_keys=True, separators=(',', ':'))
    wo_hash = f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"

    return wo_path, wo_data, wo_hash


def write_wo_approved(tmp_path: Path, wo_id: str, wo_data: dict, wo_hash: str):
    """Write WO_APPROVED event to governance.jsonl."""
    ledger_path = tmp_path / 'ledger' / 'governance.jsonl'
    client = LedgerClient(ledger_path=ledger_path)

    entry = LedgerEntry(
        event_type='WO_APPROVED',
        submission_id=wo_id,
        decision='APPROVED',
        reason='Test approval',
        metadata={
            'wo_id': wo_id,
            'wo_payload': wo_data,
            'wo_payload_hash': wo_hash,
            'signature_b64': 'TEST_SIGNATURE',
            'approver_key_id': 'test-key-001',
            'approved_at': datetime.now(timezone.utc).isoformat(),
        }
    )

    client.write(entry)
    client.flush()


def write_wo_completed(tmp_path: Path, wo_id: str, wo_hash: str, status: str = 'COMPLETED'):
    """Write WO_COMPLETED event to HO2 workorder.jsonl."""
    ledger_path = tmp_path / 'planes' / 'ho2' / 'ledger' / 'workorder.jsonl'
    client = LedgerClient(ledger_path=ledger_path)

    entry = LedgerEntry(
        event_type='WO_COMPLETED',
        submission_id=wo_id,
        decision=status,
        reason=f'Test completion with status: {status}',
        metadata={
            'wo_id': wo_id,
            'wo_payload_hash': wo_hash,
            'status': status,
            'completed_at': datetime.now(timezone.utc).isoformat(),
        }
    )

    client.write(entry)
    client.flush()


class TestG2UnapprovedWO:
    """Test 1: HO2 rejects unapproved WO."""

    def test_ho2_rejects_unapproved_wo(self, tmp_path):
        """HO2 must reject WO execution if no WO_APPROVED in HOT governance.jsonl."""
        plane_root = create_test_plane(tmp_path)
        wo_path, wo_data, wo_hash = create_test_wo(plane_root)

        # Import and run G2 gate
        from scripts.g2_gate import run_g2_gate

        result = run_g2_gate(
            wo_id=wo_data['work_order_id'],
            wo_file=wo_path,
            plane_root=plane_root,
            skip_signature=True
        )

        # Should fail - no approval
        assert not result.passed
        assert "wo_approved" in result.message.lower() or "not approved" in result.message.lower()
        assert result.action == "FAIL"


class TestG2TamperedWO:
    """Test 2: Tampered WO rejected (hash mismatch)."""

    def test_tampered_wo_rejected(self, tmp_path):
        """WO with modified payload after approval must be rejected."""
        plane_root = create_test_plane(tmp_path)
        wo_path, wo_data, wo_hash = create_test_wo(plane_root)

        # Approve the original WO
        write_wo_approved(plane_root, wo_data['work_order_id'], wo_data, wo_hash)

        # Modify the WO file after approval (tamper)
        wo_data['scope']['allowed_files'].append('lib/tampered.py')
        wo_path.write_text(json.dumps(wo_data, indent=2))

        from scripts.g2_gate import run_g2_gate

        result = run_g2_gate(
            wo_id=wo_data['work_order_id'],
            wo_file=wo_path,
            plane_root=plane_root,
            skip_signature=True
        )

        # Should fail - hash mismatch
        assert not result.passed
        assert "tamper" in result.message.lower() or "mismatch" in result.message.lower()


class TestG2Idempotency:
    """Test 3: Idempotent retry (same hash = NO-OP)."""

    def test_retried_wo_idempotent(self, tmp_path):
        """Retrying same (wo_id, wo_payload_hash) must be idempotent."""
        plane_root = create_test_plane(tmp_path)
        wo_path, wo_data, wo_hash = create_test_wo(plane_root)

        # Approve the WO
        write_wo_approved(plane_root, wo_data['work_order_id'], wo_data, wo_hash)

        # Mark it as completed (simulating first successful execution)
        write_wo_completed(plane_root, wo_data['work_order_id'], wo_hash)

        from scripts.g2_gate import run_g2_gate

        # Try to execute again
        result = run_g2_gate(
            wo_id=wo_data['work_order_id'],
            wo_file=wo_path,
            plane_root=plane_root,
            skip_signature=True
        )

        # Should pass but be NO-OP
        assert result.passed
        assert result.action == "NO_OP"
        assert "idempotent" in result.message.lower() or "already" in result.message.lower()


class TestG2ReplayVariant:
    """Test 4: Replay variant rejected (same ID, different hash)."""

    def test_replay_variant_rejected(self, tmp_path):
        """Same WO ID with different hash must be rejected."""
        plane_root = create_test_plane(tmp_path)
        wo_path, wo_data, wo_hash = create_test_wo(plane_root)

        # Approve the original WO
        write_wo_approved(plane_root, wo_data['work_order_id'], wo_data, wo_hash)

        # Mark as completed with original hash
        write_wo_completed(plane_root, wo_data['work_order_id'], wo_hash)

        # Now modify the WO (different hash) but keep same ID
        wo_data['scope']['allowed_files'].append('lib/new.py')
        wo_path.write_text(json.dumps(wo_data, indent=2))

        # Compute new hash
        canonical = json.dumps(wo_data, sort_keys=True, separators=(',', ':'))
        new_hash = f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"

        # Approve with new hash (simulating a different approval)
        write_wo_approved(plane_root, wo_data['work_order_id'], wo_data, new_hash)

        from scripts.g2_gate import run_g2_gate

        # Try to execute - should fail due to replay variant
        result = run_g2_gate(
            wo_id=wo_data['work_order_id'],
            wo_file=wo_path,
            plane_root=plane_root,
            skip_signature=True
        )

        # Should fail - different hash for same ID that was already applied
        assert not result.passed
        assert result.action == "FAIL"
        assert "tamper" in result.message.lower() or "different" in result.message.lower() or "hash" in result.message.lower()


class TestG2ScopeValidation:
    """Test 5: Scope validation."""

    def test_scope_validation_passes(self, tmp_path):
        """Valid scope should pass validation."""
        plane_root = create_test_plane(tmp_path)
        wo_path, wo_data, wo_hash = create_test_wo(plane_root)

        # Approve the WO
        write_wo_approved(plane_root, wo_data['work_order_id'], wo_data, wo_hash)

        from scripts.g2_gate import run_g2_gate

        result = run_g2_gate(
            wo_id=wo_data['work_order_id'],
            wo_file=wo_path,
            plane_root=plane_root,
            skip_signature=True
        )

        # Should pass (scope check skipped if spec has no assets defined)
        assert result.passed
        assert result.action == "PROCEED"


class TestG2ApprovalExists:
    """Test that approval flow works correctly."""

    def test_approved_wo_passes_g2(self, tmp_path):
        """Approved WO with valid hash should pass G2."""
        plane_root = create_test_plane(tmp_path)
        wo_path, wo_data, wo_hash = create_test_wo(plane_root)

        # Approve the WO
        write_wo_approved(plane_root, wo_data['work_order_id'], wo_data, wo_hash)

        from scripts.g2_gate import run_g2_gate

        result = run_g2_gate(
            wo_id=wo_data['work_order_id'],
            wo_file=wo_path,
            plane_root=plane_root,
            skip_signature=True
        )

        # Should pass
        assert result.passed
        assert result.action == "PROCEED"
        assert result.details.get('hash_verified') == True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
