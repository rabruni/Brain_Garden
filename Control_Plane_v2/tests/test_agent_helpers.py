#!/usr/bin/env python3
"""
Tests for lib/agent_helpers.py - Shared read-only helpers for agents.

Tests:
- EvidencePointer serialization
- InstalledPackage listing
- GateFailure querying
- Path classification
- HO2 checkpoint reading
- HO1 replay
"""
import json
import pytest
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.agent_helpers import (
    EvidencePointer,
    InstalledPackage,
    GateFailure,
    PathClassification,
    CPInspector,
    compute_file_hash,
    compute_content_hash,
)


class TestEvidencePointer:
    """Test EvidencePointer dataclass."""

    def test_to_dict(self):
        """Test JSON serialization."""
        ep = EvidencePointer(
            source="ledger",
            path="/path/to/ledger.jsonl",
            range=(10, 20),
            hash="sha256:abc123",
        )
        d = ep.to_dict()

        assert d["source"] == "ledger"
        assert d["path"] == "/path/to/ledger.jsonl"
        assert d["range"] == [10, 20]
        assert d["hash"] == "sha256:abc123"

    def test_from_dict(self):
        """Test deserialization."""
        data = {
            "source": "file",
            "path": "/path/to/file.txt",
            "range": [0, 5],
            "hash": "sha256:def456",
            "timestamp": "2026-02-03T12:00:00Z",
        }
        ep = EvidencePointer.from_dict(data)

        assert ep.source == "file"
        assert ep.range == (0, 5)

    def test_no_range(self):
        """Test evidence without range."""
        ep = EvidencePointer(
            source="file",
            path="/path/to/file",
        )
        d = ep.to_dict()
        assert d["range"] is None


class TestInstalledPackage:
    """Test InstalledPackage dataclass."""

    def test_to_dict(self):
        """Test serialization."""
        pkg = InstalledPackage(
            package_id="PKG-TEST-001",
            version="1.0.0",
            manifest_hash="sha256:abc123",
            assets_count=10,
            installed_at="2026-02-03T12:00:00Z",
            plane_id="ho3",
            package_type="standard",
        )
        d = pkg.to_dict()

        assert d["package_id"] == "PKG-TEST-001"
        assert d["version"] == "1.0.0"
        assert d["assets_count"] == 10


class TestGateFailure:
    """Test GateFailure dataclass."""

    def test_to_dict(self):
        """Test serialization with evidence."""
        failure = GateFailure(
            gate="G0A",
            timestamp="2026-02-03T12:00:00Z",
            package_id="PKG-BAD-001",
            error_message="Hash mismatch",
            evidence=[
                EvidencePointer(source="ledger", path="/ledger.jsonl"),
            ],
        )
        d = failure.to_dict()

        assert d["gate"] == "G0A"
        assert d["package_id"] == "PKG-BAD-001"
        assert len(d["evidence"]) == 1


class TestComputeHash:
    """Test hash computation functions."""

    def test_compute_file_hash(self, tmp_path):
        """Test file hash computation."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!")

        hash_val = compute_file_hash(test_file)

        assert hash_val.startswith("sha256:")
        assert len(hash_val) == 71  # sha256: + 64 hex

    def test_compute_file_hash_nonexistent(self, tmp_path):
        """Test hash of nonexistent file returns empty."""
        hash_val = compute_file_hash(tmp_path / "nonexistent.txt")
        assert hash_val == ""

    def test_compute_content_hash(self):
        """Test string content hash."""
        hash_val = compute_content_hash("test content")

        assert hash_val.startswith("sha256:")
        # Same content should produce same hash
        hash_val2 = compute_content_hash("test content")
        assert hash_val == hash_val2


class TestCPInspectorListInstalled:
    """Test CPInspector.list_installed()."""

    def test_list_installed_empty(self, tmp_path):
        """Test list_installed with no packages."""
        inspector = CPInspector(tmp_path)
        packages, evidence = inspector.list_installed("ho3")

        assert packages == []
        assert evidence.source == "file"

    def test_list_installed_with_packages(self, tmp_path):
        """Test list_installed with installed packages."""
        # Create mock installed package
        installed_dir = tmp_path / "installed" / "PKG-TEST-001"
        installed_dir.mkdir(parents=True)

        manifest = {
            "package_id": "PKG-TEST-001",
            "version": "1.2.3",
            "assets": [{"path": "lib/test.py"}],
        }
        (installed_dir / "manifest.json").write_text(json.dumps(manifest))

        receipt = {
            "manifest_hash": "sha256:abc123",
            "installed_at": "2026-02-03T12:00:00Z",
        }
        (installed_dir / "receipt.json").write_text(json.dumps(receipt))

        inspector = CPInspector(tmp_path)
        packages, evidence = inspector.list_installed("ho3")

        assert len(packages) == 1
        assert packages[0].package_id == "PKG-TEST-001"
        assert packages[0].version == "1.2.3"
        assert evidence.hash != ""


class TestCPInspectorGovernedRoots:
    """Test CPInspector.list_governed_roots()."""

    def test_list_governed_roots(self, tmp_path):
        """Test listing governed roots."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()

        config = {
            "governed_roots": ["lib/", "scripts/", "tests/"],
        }
        (config_dir / "governed_roots.json").write_text(json.dumps(config))

        inspector = CPInspector(tmp_path)
        roots, evidence = inspector.list_governed_roots()

        assert "lib/" in roots
        assert "scripts/" in roots
        assert evidence.hash != ""

    def test_list_governed_roots_missing_config(self, tmp_path):
        """Test with missing config file."""
        inspector = CPInspector(tmp_path)
        roots, evidence = inspector.list_governed_roots()

        assert roots == []
        assert evidence.hash == ""


class TestCPInspectorGateFailures:
    """Test CPInspector.last_gate_failures()."""

    def test_last_gate_failures_empty(self, tmp_path):
        """Test with no ledger."""
        inspector = CPInspector(tmp_path)
        failures, evidence = inspector.last_gate_failures()

        assert failures == []

    def test_last_gate_failures_with_data(self, tmp_path):
        """Test with ledger containing failures."""
        ledger_dir = tmp_path / "ledger"
        ledger_dir.mkdir()

        entries = [
            {"event_type": "INSTALLED", "timestamp": "2026-02-03T10:00:00Z"},
            {"event_type": "GATE_FAILED", "timestamp": "2026-02-03T11:00:00Z",
             "metadata": {"gate": "G0A", "package_id": "PKG-BAD-001"},
             "reason": "Hash mismatch"},
            {"event_type": "INSTALLED", "timestamp": "2026-02-03T12:00:00Z"},
        ]

        with open(ledger_dir / "governance.jsonl", "w") as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")

        inspector = CPInspector(tmp_path)
        failures, evidence = inspector.last_gate_failures()

        assert len(failures) == 1
        assert failures[0].gate == "G0A"
        assert "PKG-BAD-001" in str(failures[0].package_id)

    def test_last_gate_failures_filter_by_gate(self, tmp_path):
        """Test filtering by gate type."""
        ledger_dir = tmp_path / "ledger"
        ledger_dir.mkdir()

        entries = [
            {"event_type": "GATE_FAILED", "metadata": {"gate": "G0A"}},
            {"event_type": "GATE_FAILED", "metadata": {"gate": "G1"}},
            {"event_type": "GATE_FAILED", "metadata": {"gate": "G0A"}},
        ]

        with open(ledger_dir / "governance.jsonl", "w") as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")

        inspector = CPInspector(tmp_path)
        failures, evidence = inspector.last_gate_failures(gate="G1")

        assert len(failures) == 1
        assert failures[0].gate == "G1"


class TestCPInspectorExplainPath:
    """Test CPInspector.explain_path()."""

    def test_explain_pristine_path(self, tmp_path):
        """Test PRISTINE path classification."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()

        config = {"governed_roots": ["lib/", "scripts/"]}
        (config_dir / "governed_roots.json").write_text(json.dumps(config))

        inspector = CPInspector(tmp_path)
        classification, evidence = inspector.explain_path("lib/module.py")

        assert classification.classification == "PRISTINE"
        assert "lib/" in classification.governed_root
        assert "read-only" in classification.explanation.lower()

    def test_explain_derived_path(self, tmp_path):
        """Test DERIVED path classification."""
        inspector = CPInspector(tmp_path)
        classification, evidence = inspector.explain_path("_staging/package.tar.gz")

        assert classification.classification == "DERIVED"
        assert "mutable" in classification.explanation.lower()

    def test_explain_append_only_path(self, tmp_path):
        """Test APPEND_ONLY path classification."""
        inspector = CPInspector(tmp_path)
        classification, evidence = inspector.explain_path("ledger/governance.jsonl")

        assert classification.classification == "APPEND_ONLY"
        assert "append" in classification.explanation.lower()

    def test_explain_unknown_path(self, tmp_path):
        """Test unknown path classification."""
        inspector = CPInspector(tmp_path)
        classification, evidence = inspector.explain_path("random/path/file.txt")

        assert classification.classification == "UNKNOWN"


class TestCPInspectorRegistryStats:
    """Test CPInspector.get_registry_stats()."""

    def test_registry_stats(self, tmp_path):
        """Test registry statistics."""
        reg_dir = tmp_path / "registries"
        reg_dir.mkdir()

        # Create mock registries
        (reg_dir / "packages.csv").write_text("id,status\nPKG-1,active\nPKG-2,active\n")
        (reg_dir / "specs.csv").write_text("id,status\nSPEC-1,active\n")

        inspector = CPInspector(tmp_path)
        stats, evidence = inspector.get_registry_stats()

        assert stats["registries"] == 2
        assert stats["total_items"] == 3
        assert stats["by_status"]["active"] == 3


class TestCPInspectorHO2Checkpoint:
    """Test CPInspector.read_ho2_checkpoint()."""

    def test_read_checkpoint_not_found(self, tmp_path):
        """Test with no checkpoint."""
        inspector = CPInspector(tmp_path)
        checkpoint, evidence = inspector.read_ho2_checkpoint("SESSION-001")

        assert checkpoint is None

    def test_read_checkpoint_found(self, tmp_path):
        """Test with valid checkpoint."""
        ho2_dir = tmp_path / "planes" / "ho2" / "ledger"
        ho2_dir.mkdir(parents=True)

        entry = {
            "event_type": "SESSION_CHECKPOINT",
            "metadata": {"session_id": "SESSION-001"},
            "entry_hash": "sha256:abc123",
        }
        (ho2_dir / "workorder.jsonl").write_text(json.dumps(entry) + "\n")

        inspector = CPInspector(tmp_path)
        checkpoint, evidence = inspector.read_ho2_checkpoint("SESSION-001")

        assert checkpoint is not None
        assert checkpoint["metadata"]["session_id"] == "SESSION-001"


class TestCPInspectorReplayHO1:
    """Test CPInspector.replay_ho1()."""

    def test_replay_empty(self, tmp_path):
        """Test replay with no session."""
        inspector = CPInspector(tmp_path)
        entries, evidence = inspector.replay_ho1("SESSION-NONEXISTENT")

        assert entries == []

    def test_replay_session(self, tmp_path):
        """Test replay with session data."""
        ho1_dir = tmp_path / "planes" / "ho1" / "ledger"
        ho1_dir.mkdir(parents=True)

        session_entries = [
            {"event_type": "SESSION_START", "metadata": {"session_id": "SESSION-001"}},
            {"event_type": "TASK_BEGIN", "metadata": {"session_id": "SESSION-001"}},
            {"event_type": "SESSION_END", "metadata": {"session_id": "SESSION-001"}},
        ]

        with open(ho1_dir / "worker.jsonl", "w") as f:
            for entry in session_entries:
                f.write(json.dumps(entry) + "\n")

        inspector = CPInspector(tmp_path)
        entries, evidence = inspector.replay_ho1("SESSION-001")

        assert len(entries) == 3
        assert entries[0]["event_type"] == "SESSION_START"
        assert evidence.range is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
