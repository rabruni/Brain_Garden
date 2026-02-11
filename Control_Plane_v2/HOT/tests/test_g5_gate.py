#!/usr/bin/env python3
"""
test_g5_gate.py - Tests for G5 SIGNATURE gate.

Tests the attestation creation logic:
- Changeset digest computed correctly
- Attestation contains required fields
- Signature waiver works when key not available
- Signed attestation when key is available
"""

import json
import pytest
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.g5_gate import (
    run_g5_gate,
    compute_changeset_digest,
    compute_file_hash,
    create_attestation,
    load_signing_keys,
    G5Result,
    Attestation,
)


class TestChangesetDigest:
    """Test changeset digest computation."""

    def test_empty_changeset_has_digest(self):
        """Empty changeset should produce a defined digest."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            digest, hashes = compute_changeset_digest([], workspace)

            assert digest.startswith('sha256:')
            assert len(digest) == 71  # sha256: + 64 hex chars
            assert hashes == []

    def test_single_file_changeset(self):
        """Single file changeset should produce digest."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            test_file = workspace / 'test.txt'
            test_file.write_text('hello world')

            digest, hashes = compute_changeset_digest(['test.txt'], workspace)

            assert digest.startswith('sha256:')
            assert len(hashes) == 1
            assert 'test.txt:sha256:' in hashes[0]

    def test_multiple_files_sorted(self):
        """Multiple files should be sorted for deterministic digest."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            (workspace / 'b.txt').write_text('b')
            (workspace / 'a.txt').write_text('a')
            (workspace / 'c.txt').write_text('c')

            digest, hashes = compute_changeset_digest(['b.txt', 'a.txt', 'c.txt'], workspace)

            # Should be sorted: a, b, c
            assert hashes[0].startswith('a.txt')
            assert hashes[1].startswith('b.txt')
            assert hashes[2].startswith('c.txt')

    def test_same_content_same_digest(self):
        """Same content should produce same digest."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            test_file = workspace / 'test.txt'
            test_file.write_text('hello world')

            digest1, _ = compute_changeset_digest(['test.txt'], workspace)

            # Same content
            test_file.write_text('hello world')
            digest2, _ = compute_changeset_digest(['test.txt'], workspace)

            assert digest1 == digest2

    def test_different_content_different_digest(self):
        """Different content should produce different digest."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            test_file = workspace / 'test.txt'

            test_file.write_text('hello world')
            digest1, _ = compute_changeset_digest(['test.txt'], workspace)

            test_file.write_text('different content')
            digest2, _ = compute_changeset_digest(['test.txt'], workspace)

            assert digest1 != digest2


class TestAttestation:
    """Test attestation creation."""

    def test_attestation_has_required_fields(self):
        """Attestation should have all required fields."""
        attestation = create_attestation(
            wo_id='WO-TEST-001',
            spec_id='SPEC-TEST-001',
            changeset_digest='sha256:abc123',
            signing_key=None,
            private_key=None,
            plane_root=Path('/tmp')
        )

        assert attestation.attestation_id.startswith('ATT-')
        assert attestation.wo_id == 'WO-TEST-001'
        assert attestation.spec_id == 'SPEC-TEST-001'
        assert attestation.changeset_digest == 'sha256:abc123'
        assert attestation.timestamp  # Not empty

    def test_attestation_waived_without_key(self):
        """Attestation should be waived when no signing key available."""
        attestation = create_attestation(
            wo_id='WO-TEST-001',
            spec_id='SPEC-TEST-001',
            changeset_digest='sha256:abc123',
            signing_key=None,
            private_key=None,
            plane_root=Path('/tmp')
        )

        assert attestation.signature_waived is True
        assert attestation.waiver_reason is not None
        assert attestation.signature_b64 is None

    def test_attestation_serializable(self):
        """Attestation should be JSON serializable."""
        attestation = create_attestation(
            wo_id='WO-TEST-001',
            spec_id='SPEC-TEST-001',
            changeset_digest='sha256:abc123',
            signing_key=None,
            private_key=None,
            plane_root=Path('/tmp')
        )

        attestation_dict = attestation.to_dict()
        json_str = json.dumps(attestation_dict)

        assert 'WO-TEST-001' in json_str
        assert 'changeset_digest' in json_str


class TestG5Gate:
    """Test full G5 gate execution."""

    def test_g5_passes_with_waiver(self):
        """G5 should pass even when signature is waived (Phase 3)."""
        wo = {
            'work_order_id': 'WO-TEST-001',
            'spec_id': 'SPEC-TEST-001',
            'scope': {
                'allowed_files': ['lib/paths.py']
            }
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            (workspace / 'lib').mkdir()
            (workspace / 'lib' / 'paths.py').write_text('# test')

            result = run_g5_gate(wo, ['lib/paths.py'], workspace)

            assert result.passed is True
            assert result.attestation is not None
            assert result.attestation.signature_waived is True

    def test_g5_creates_attestation_with_digest(self):
        """G5 should create attestation with changeset digest."""
        wo = {
            'work_order_id': 'WO-TEST-001',
            'spec_id': 'SPEC-TEST-001'
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            test_file = workspace / 'test.py'
            test_file.write_text('print("hello")')

            result = run_g5_gate(wo, ['test.py'], workspace)

            assert result.passed is True
            assert result.attestation is not None
            assert result.attestation.changeset_digest.startswith('sha256:')
            assert 'changeset_digest' in result.details

    def test_g5_result_serializable(self):
        """G5Result should be JSON serializable."""
        wo = {
            'work_order_id': 'WO-TEST-001',
            'spec_id': 'SPEC-TEST-001'
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            result = run_g5_gate(wo, [], workspace)
            result_dict = result.to_dict()

            json_str = json.dumps(result_dict)
            assert 'G5' in json_str

    def test_g5_reports_changed_file_count(self):
        """G5 should report number of changed files in details."""
        wo = {
            'work_order_id': 'WO-TEST-001',
            'spec_id': 'SPEC-TEST-001'
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            for i in range(5):
                (workspace / f'file{i}.py').write_text(f'# file {i}')

            changed = [f'file{i}.py' for i in range(5)]
            result = run_g5_gate(wo, changed, workspace)

            assert result.details['changed_file_count'] == 5


class TestAcceptanceCriteriaAC3:
    """AC3: G5 produces attestation with changeset_digest field."""

    def test_ac3_attestation_has_changeset_hash(self):
        """
        AC3: Successful WO produces attestation with changeset_digest field.

        This is the primary acceptance criterion for G5.
        """
        wo = {
            'work_order_id': 'WO-AC3-TEST',
            'type': 'code_change',
            'plane_id': 'ho3',
            'spec_id': 'SPEC-TEST-001',
            'framework_id': 'FMWK-000',
            'scope': {
                'allowed_files': ['lib/test.py'],
                'forbidden_files': []
            }
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            (workspace / 'lib').mkdir()
            (workspace / 'lib' / 'test.py').write_text('# test content')

            result = run_g5_gate(wo, ['lib/test.py'], workspace)

            # MUST pass
            assert result.passed is True, "G5 must pass"

            # MUST have attestation
            assert result.attestation is not None, "G5 must create attestation"

            # MUST have changeset_digest
            assert result.attestation.changeset_digest is not None, "Attestation must have changeset_digest"
            assert result.attestation.changeset_digest.startswith('sha256:'), "Digest must be sha256 format"
            assert len(result.attestation.changeset_digest) == 71, "Digest must be correct length"

            # Verify also in details
            assert 'changeset_digest' in result.details, "Details must include changeset_digest"
