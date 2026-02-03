#!/usr/bin/env python3
"""
test_idempotency.py - Tests for Work Order idempotency (FMWK-000 Phase 2).

Tests:
1. Retried WO with same hash is NO-OP
2. Same WO ID with different hash fails (tampering/replay)
3. Idempotency check queries HO2 workorder.jsonl
"""

import hashlib
import json
import pytest
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add parent to path for lib imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.ledger_client import LedgerClient, LedgerEntry


def create_test_plane(tmp_path: Path) -> Path:
    """Create minimal test plane structure with tier manifests."""
    (tmp_path / 'ledger' / 'idx').mkdir(parents=True)
    (tmp_path / 'planes' / 'ho2' / 'ledger' / 'idx').mkdir(parents=True)
    (tmp_path / 'config').mkdir()
    (tmp_path / 'work_orders' / 'ho3').mkdir(parents=True)

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

    # Create trusted_keys.json
    trusted_keys = {
        "schema_version": "1.0",
        "keys": [
            {
                "key_id": "test-key-001",
                "algorithm": "Ed25519",
                "public_key_b64": "PLACEHOLDER",
                "roles": ["wo_approver"]
            }
        ]
    }
    (tmp_path / 'config' / 'trusted_keys.json').write_text(
        json.dumps(trusted_keys, indent=2)
    )

    # Create governed_roots.json
    governed_roots = {
        "schema_version": "1.0",
        "plane_id": "ho3",
        "governed_roots": ["lib/"],
        "excluded_patterns": []
    }
    (tmp_path / 'config' / 'governed_roots.json').write_text(
        json.dumps(governed_roots, indent=2)
    )

    # Initialize ledgers with index files
    (tmp_path / 'ledger' / 'governance.jsonl').touch()
    (tmp_path / 'ledger' / 'index.jsonl').touch()
    (tmp_path / 'planes' / 'ho2' / 'ledger' / 'workorder.jsonl').touch()
    (tmp_path / 'planes' / 'ho2' / 'ledger' / 'index.jsonl').touch()

    return tmp_path


def create_wo_and_approve(tmp_path: Path, wo_id: str, scope_files: list = None) -> tuple:
    """Create WO file and approve it.

    Returns:
        (wo_path, wo_data, wo_hash)
    """
    if scope_files is None:
        scope_files = ["lib/test.py"]

    wo_data = {
        "work_order_id": wo_id,
        "type": "code_change",
        "plane_id": "ho3",
        "spec_id": "SPEC-TEST-001",
        "framework_id": "FMWK-000",
        "scope": {
            "allowed_files": scope_files,
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

    # Write WO_APPROVED to HOT governance.jsonl
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
            'signature_b64': 'TEST_SIG',
            'approver_key_id': 'test-key-001',
            'approved_at': datetime.now(timezone.utc).isoformat(),
        }
    )
    client.write(entry)
    client.flush()

    return wo_path, wo_data, wo_hash


def mark_wo_completed(tmp_path: Path, wo_id: str, wo_hash: str):
    """Mark WO as completed in HO2 workorder.jsonl."""
    ledger_path = tmp_path / 'planes' / 'ho2' / 'ledger' / 'workorder.jsonl'
    client = LedgerClient(ledger_path=ledger_path)

    entry = LedgerEntry(
        event_type='WO_COMPLETED',
        submission_id=wo_id,
        decision='COMPLETED',
        reason='Test completion',
        metadata={
            'wo_id': wo_id,
            'wo_payload_hash': wo_hash,
            'status': 'COMPLETED',
            'completed_at': datetime.now(timezone.utc).isoformat(),
        }
    )
    client.write(entry)
    client.flush()


class TestIdempotentRetry:
    """Test 1: Retried WO with same hash is NO-OP."""

    def test_same_hash_is_noop(self, tmp_path):
        """Same (wo_id, wo_payload_hash) returns NO-OP."""
        plane_root = create_test_plane(tmp_path)
        wo_id = "WO-20260202-001"
        wo_path, wo_data, wo_hash = create_wo_and_approve(plane_root, wo_id)

        # Mark as completed
        mark_wo_completed(plane_root, wo_id, wo_hash)

        # Run G2 gate - should be NO-OP
        from scripts.g2_gate import run_g2_gate

        result = run_g2_gate(
            wo_id=wo_id,
            wo_file=wo_path,
            plane_root=plane_root,
            skip_signature=True
        )

        assert result.passed
        assert result.action == "NO_OP"
        assert "already" in result.message.lower() or "idempotent" in result.message.lower()

    def test_multiple_retries_all_noop(self, tmp_path):
        """Multiple retries of same WO all return NO-OP."""
        plane_root = create_test_plane(tmp_path)
        wo_id = "WO-20260202-002"
        wo_path, wo_data, wo_hash = create_wo_and_approve(plane_root, wo_id)

        # Mark as completed
        mark_wo_completed(plane_root, wo_id, wo_hash)

        from scripts.g2_gate import run_g2_gate

        # Try 3 times
        for i in range(3):
            result = run_g2_gate(
                wo_id=wo_id,
                wo_file=wo_path,
                plane_root=plane_root,
                skip_signature=True
            )

            assert result.passed
            assert result.action == "NO_OP"


class TestDifferentHashFails:
    """Test 2: Same WO ID with different hash fails."""

    def test_different_hash_rejected(self, tmp_path):
        """Same WO ID with different hash must be rejected."""
        plane_root = create_test_plane(tmp_path)
        wo_id = "WO-20260202-003"

        # Create and approve first version
        wo_path, wo_data, wo_hash = create_wo_and_approve(plane_root, wo_id, ["lib/v1.py"])

        # Mark first version as completed
        mark_wo_completed(plane_root, wo_id, wo_hash)

        # Modify WO file (different content = different hash)
        wo_data['scope']['allowed_files'] = ["lib/v2.py"]
        wo_path.write_text(json.dumps(wo_data, indent=2))

        # Compute new hash
        canonical = json.dumps(wo_data, sort_keys=True, separators=(',', ':'))
        new_hash = f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"

        # Approve the new version (same ID, different hash)
        ledger_path = plane_root / 'ledger' / 'governance.jsonl'
        client = LedgerClient(ledger_path=ledger_path)

        entry = LedgerEntry(
            event_type='WO_APPROVED',
            submission_id=wo_id,
            decision='APPROVED',
            reason='Second approval',
            metadata={
                'wo_id': wo_id,
                'wo_payload': wo_data,
                'wo_payload_hash': new_hash,
                'signature_b64': 'TEST_SIG_2',
                'approver_key_id': 'test-key-001',
            }
        )
        client.write(entry)
        client.flush()

        # Run G2 gate - should FAIL (replay variant)
        from scripts.g2_gate import run_g2_gate

        result = run_g2_gate(
            wo_id=wo_id,
            wo_file=wo_path,
            plane_root=plane_root,
            skip_signature=True
        )

        assert not result.passed
        assert result.action == "FAIL"
        # Should mention tampering or different hash
        assert any(word in result.message.lower() for word in ['tamper', 'different', 'mismatch', 'hash'])


class TestIdempotencyCheckQuerySource:
    """Test 3: Idempotency check queries HO2 workorder.jsonl."""

    def test_idempotency_checks_ho2_ledger(self, tmp_path):
        """Idempotency check must query HO2 workorder.jsonl."""
        plane_root = create_test_plane(tmp_path)
        wo_id = "WO-20260202-004"
        wo_path, wo_data, wo_hash = create_wo_and_approve(plane_root, wo_id)

        from scripts.g2_gate import run_g2_gate, check_idempotency_ho2

        # Before completion - should PROCEED
        action, msg, existing = check_idempotency_ho2(wo_id, wo_hash, plane_root)
        assert action == "PROCEED"

        # Mark as completed
        mark_wo_completed(plane_root, wo_id, wo_hash)

        # After completion - should NO_OP
        action, msg, existing = check_idempotency_ho2(wo_id, wo_hash, plane_root)
        assert action == "NO_OP"
        assert existing is not None

    def test_new_wo_proceeds(self, tmp_path):
        """New WO (not in HO2) should PROCEED."""
        plane_root = create_test_plane(tmp_path)
        wo_id = "WO-20260202-005"
        wo_path, wo_data, wo_hash = create_wo_and_approve(plane_root, wo_id)

        # Don't mark as completed - it's new

        from scripts.g2_gate import run_g2_gate

        result = run_g2_gate(
            wo_id=wo_id,
            wo_file=wo_path,
            plane_root=plane_root,
            skip_signature=True
        )

        assert result.passed
        assert result.action == "PROCEED"


class TestIdempotencyHashComparison:
    """Test hash comparison in idempotency check."""

    def test_hash_computed_from_canonical_json(self, tmp_path):
        """wo_payload_hash must be computed from canonical JSON."""
        plane_root = create_test_plane(tmp_path)

        wo_data = {
            "z_field": "last",
            "a_field": "first",
            "work_order_id": "WO-20260202-006",
        }

        # Canonical = sorted keys
        canonical = json.dumps(wo_data, sort_keys=True, separators=(',', ':'))
        expected_hash = f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"

        # Non-canonical = original order
        non_canonical = json.dumps(wo_data, separators=(',', ':'))
        non_canonical_hash = f"sha256:{hashlib.sha256(non_canonical.encode('utf-8')).hexdigest()}"

        # They should be different (proves we need canonical)
        assert expected_hash != non_canonical_hash

        # Our function should use canonical
        from scripts.g2_gate import compute_wo_payload_hash
        computed = compute_wo_payload_hash(wo_data)
        assert computed == expected_hash

    def test_idempotency_independent_of_execution_output(self, tmp_path):
        """Idempotency must NOT depend on execution outputs."""
        plane_root = create_test_plane(tmp_path)
        wo_id = "WO-20260202-007"
        wo_path, wo_data, wo_hash = create_wo_and_approve(plane_root, wo_id)

        # Mark as completed
        mark_wo_completed(plane_root, wo_id, wo_hash)

        # The idempotency check uses wo_payload_hash which is computed
        # from the WO file content, not from execution outputs
        from scripts.g2_gate import check_idempotency_ho2

        # Idempotency is based on (wo_id, wo_payload_hash)
        action, msg, _ = check_idempotency_ho2(wo_id, wo_hash, plane_root)
        assert action == "NO_OP"

        # A different hash (even for same id) would give different result
        different_hash = "sha256:differenthash123"
        action2, msg2, _ = check_idempotency_ho2(wo_id, different_hash, plane_root)
        assert action2 == "FAIL"  # Tampering detected


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
