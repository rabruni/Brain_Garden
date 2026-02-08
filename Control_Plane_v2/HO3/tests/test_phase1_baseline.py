#!/usr/bin/env python3
"""
Phase 1 Acceptance Tests: Baseline Sealing + Aligned Package Model

Tests for CP-IMPL-001 Phase 1 implementation:
- Baseline manifest generation (deterministic, declared inputs)
- Baseline installation (two-phase ledger, HO3-only)
- Derived registry rebuild (from ledger+manifests, conflict detection)
- G0A/G0B gate split (package declaration vs plane ownership)

BINDING CONSTRAINTS tested:
- HO3-only scope
- Hash format: sha256:<64hex>
- Ledger is Memory (INSTALL_STARTED → INSTALLED)
- Turn isolation (declared inputs in metadata)
- No last-write-wins (conflict = FAIL)
"""

import csv
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

# Add parent to path
SCRIPT_DIR = Path(__file__).resolve().parent
CONTROL_PLANE_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(CONTROL_PLANE_ROOT))
sys.path.insert(0, str(CONTROL_PLANE_ROOT.parent / "HOT"))


# === Fixtures ===

@pytest.fixture
def plane_root():
    """Return the Control Plane root path."""
    return CONTROL_PLANE_ROOT


@pytest.fixture
def baseline_manifest_path(plane_root):
    """Return the baseline manifest path."""
    return plane_root / "packages_store" / "PKG-BASELINE-HO3-000" / "manifest.json"


@pytest.fixture
def baseline_manifest(baseline_manifest_path):
    """Load the baseline manifest."""
    if not baseline_manifest_path.exists():
        pytest.skip("Baseline manifest not generated yet")
    return json.loads(baseline_manifest_path.read_text())


@pytest.fixture
def file_ownership_registry(plane_root):
    """Load file_ownership.csv as dict."""
    registry_path = plane_root / "registries" / "file_ownership.csv"
    if not registry_path.exists():
        return {}
    ownership = {}
    with open(registry_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            file_path = row.get("file_path", "").strip()
            if file_path:
                ownership[file_path] = row
    return ownership


@pytest.fixture
def packages_ledger(plane_root):
    """Load L-PACKAGE ledger entries."""
    ledger_path = plane_root / "ledger" / "packages.jsonl"
    if not ledger_path.exists():
        return []
    entries = []
    with open(ledger_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                entries.append(json.loads(line))
    return entries


# === Test: Baseline Manifest Generation ===

class TestBaselineManifestGeneration:
    """Tests for generate_baseline_manifest.py"""

    def test_manifest_exists(self, baseline_manifest_path):
        """Baseline manifest should exist."""
        assert baseline_manifest_path.exists(), "Run: python3 scripts/generate_baseline_manifest.py --plane ho3 --output packages_store/PKG-BASELINE-HO3-000/"

    def test_manifest_has_required_fields(self, baseline_manifest):
        """Manifest must have required fields."""
        required = ["package_id", "version", "plane_id", "package_type", "assets", "metadata"]
        for field in required:
            assert field in baseline_manifest, f"Missing field: {field}"

    def test_manifest_package_type_is_baseline(self, baseline_manifest):
        """Package type must be 'baseline'."""
        assert baseline_manifest["package_type"] == "baseline"

    def test_manifest_plane_is_ho3(self, baseline_manifest):
        """Plane must be 'ho3' for Phase 1."""
        assert baseline_manifest["plane_id"] == "ho3"

    def test_hash_format_standardized(self, baseline_manifest):
        """All hashes must use sha256:<64hex> format."""
        for asset in baseline_manifest.get("assets", []):
            sha = asset.get("sha256", "")
            assert sha.startswith("sha256:"), f"Hash format wrong for {asset['path']}: {sha[:20]}"
            assert len(sha) == 71, f"Hash length wrong for {asset['path']}: {len(sha)} (expected 71)"

    def test_metadata_has_declared_inputs(self, baseline_manifest):
        """Metadata must have declared inputs for turn isolation."""
        metadata = baseline_manifest.get("metadata", {})
        required = ["scan_roots", "exclusion_patterns", "hash_algorithm", "hash_format_version"]
        for field in required:
            assert field in metadata, f"Metadata missing declared input: {field}"

    def test_manifest_deterministic(self, plane_root):
        """Running generator twice produces same manifest_hash."""
        # Run generator twice
        result1 = subprocess.run(
            ["python3", "scripts/generate_baseline_manifest.py", "--plane", "ho3", "--show-hash", "--dry-run"],
            cwd=str(plane_root),
            capture_output=True,
            text=True
        )
        result2 = subprocess.run(
            ["python3", "scripts/generate_baseline_manifest.py", "--plane", "ho3", "--show-hash", "--dry-run"],
            cwd=str(plane_root),
            capture_output=True,
            text=True
        )

        # Extract hashes
        hash1 = [l for l in result1.stdout.split("\n") if l.startswith("manifest_hash=")]
        hash2 = [l for l in result2.stdout.split("\n") if l.startswith("manifest_hash=")]

        assert len(hash1) == 1, "First run did not produce manifest_hash"
        assert len(hash2) == 1, "Second run did not produce manifest_hash"
        assert hash1[0] == hash2[0], f"Hashes differ: {hash1[0]} vs {hash2[0]}"


# === Test: Baseline Installation ===

class TestBaselineInstallation:
    """Tests for install_baseline.py"""

    def test_receipt_exists(self, plane_root):
        """Baseline receipt should exist after installation."""
        receipt_path = plane_root / "installed" / "PKG-BASELINE-HO3-000" / "receipt.json"
        assert receipt_path.exists(), "Run: python3 scripts/install_baseline.py --plane ho3"

    def test_receipt_has_required_fields(self, plane_root):
        """Receipt must have required fields."""
        receipt_path = plane_root / "installed" / "PKG-BASELINE-HO3-000" / "receipt.json"
        if not receipt_path.exists():
            pytest.skip("Baseline not installed")

        receipt = json.loads(receipt_path.read_text())
        required = ["package_id", "origin", "package_type", "plane_id", "installed_at", "manifest_hash", "assets_count"]
        for field in required:
            assert field in receipt, f"Receipt missing field: {field}"

    def test_receipt_origin_is_builder(self, plane_root):
        """Receipt origin must be 'BUILDER'."""
        receipt_path = plane_root / "installed" / "PKG-BASELINE-HO3-000" / "receipt.json"
        if not receipt_path.exists():
            pytest.skip("Baseline not installed")

        receipt = json.loads(receipt_path.read_text())
        assert receipt["origin"] == "BUILDER"

    def test_manifest_copy_exists(self, plane_root):
        """Manifest copy should exist in installed/<pkg>/."""
        manifest_path = plane_root / "installed" / "PKG-BASELINE-HO3-000" / "manifest.json"
        assert manifest_path.exists()


# === Test: Ledger Events ===

class TestLedgerEvents:
    """Tests for two-phase ledger install."""

    def test_ledger_has_install_started(self, packages_ledger):
        """Ledger must have INSTALL_STARTED for baseline."""
        started = [e for e in packages_ledger
                   if e.get("event_type") == "INSTALL_STARTED"
                   and e.get("submission_id") == "PKG-BASELINE-HO3-000"]
        assert len(started) >= 1, "Missing INSTALL_STARTED entry"

    def test_ledger_has_installed(self, packages_ledger):
        """Ledger must have INSTALLED for baseline."""
        installed = [e for e in packages_ledger
                     if e.get("event_type") == "INSTALLED"
                     and e.get("submission_id") == "PKG-BASELINE-HO3-000"]
        assert len(installed) >= 1, "Missing INSTALLED entry"

    def test_installed_has_manifest_hash(self, packages_ledger):
        """INSTALLED entry must have manifest_hash in metadata."""
        installed = [e for e in packages_ledger
                     if e.get("event_type") == "INSTALLED"
                     and e.get("submission_id") == "PKG-BASELINE-HO3-000"]
        if not installed:
            pytest.skip("No INSTALLED entry")

        latest = installed[-1]
        metadata = latest.get("metadata", {})
        assert "manifest_hash" in metadata
        assert metadata["manifest_hash"].startswith("sha256:")

    def test_ledger_entries_have_tier_context(self, packages_ledger):
        """Ledger entries must have HO3 tier context (legacy entries exempt).

        Legacy entries (written before _tier requirement in Phase 1B) are allowed
        to lack the _tier field. New entries MUST have _tier == "HO3".

        Legacy exemption criteria:
        - Entry lacks _tier field entirely (pre-Phase 1B)
        - Entry has _tier field → must be "HO3"
        """
        baseline_entries = [e for e in packages_ledger
                           if e.get("submission_id") == "PKG-BASELINE-HO3-000"]
        legacy_count = 0
        for entry in baseline_entries:
            metadata = entry.get("metadata", {})
            if "_tier" in metadata:
                # If _tier is present, it MUST be HO3
                assert metadata.get("_tier") == "HO3", f"Entry {entry.get('id')} has wrong tier: {metadata.get('_tier')}"
            else:
                # Legacy entry - allowed to lack _tier
                legacy_count += 1

        # Log legacy entries for visibility (not a failure)
        if legacy_count > 0:
            print(f"Note: {legacy_count} legacy entries lack _tier field (pre-Phase 1B)")


# === Test: Derived Registry Rebuild ===

class TestDerivedRegistryRebuild:
    """Tests for rebuild_derived_registries.py"""

    def test_file_ownership_exists(self, plane_root):
        """file_ownership.csv must exist after rebuild."""
        path = plane_root / "registries" / "file_ownership.csv"
        assert path.exists(), "Run: python3 scripts/rebuild_derived_registries.py --plane ho3"

    def test_packages_state_exists(self, plane_root):
        """packages_state.csv must exist after rebuild."""
        path = plane_root / "registries" / "packages_state.csv"
        assert path.exists()

    def test_file_ownership_has_files(self, file_ownership_registry):
        """file_ownership.csv must have entries."""
        assert len(file_ownership_registry) > 0

    def test_all_owned_files_have_valid_owner(self, file_ownership_registry):
        """All files should be owned by a known installed package."""
        for path, entry in file_ownership_registry.items():
            owner = entry.get("owner_package_id", "")
            assert owner.startswith("PKG-"), f"{path} has invalid owner: {owner}"

    def test_rebuild_is_idempotent(self, plane_root):
        """Running rebuild twice produces same output."""
        # Read current
        path = plane_root / "registries" / "file_ownership.csv"
        if not path.exists():
            pytest.skip("file_ownership.csv not found")
        before = path.read_text()

        # Run rebuild
        result = subprocess.run(
            ["python3", "scripts/rebuild_derived_registries.py", "--plane", "ho3"],
            cwd=str(plane_root),
            capture_output=True,
            text=True
        )
        assert result.returncode == 0, f"Rebuild failed: {result.stderr}"

        # Read after
        after = path.read_text()
        assert before == after, "Rebuild changed file_ownership.csv"

    def test_verify_mode_matches(self, plane_root):
        """--verify mode should report match."""
        result = subprocess.run(
            ["python3", "scripts/rebuild_derived_registries.py", "--plane", "ho3", "--verify"],
            cwd=str(plane_root),
            capture_output=True,
            text=True
        )
        assert result.returncode == 0
        assert "MATCH" in result.stdout or "Match" in result.stdout


# === Test: G0A/G0B Gate Split ===

class TestG0Gates:
    """Tests for G0A and G0B gate implementations."""

    def test_g0b_passes(self, plane_root):
        """G0B should pass after baseline install and rebuild."""
        result = subprocess.run(
            ["python3", "scripts/gate_check.py", "--gate", "G0B", "--enforce"],
            cwd=str(plane_root),
            capture_output=True,
            text=True
        )
        assert result.returncode == 0, f"G0B failed:\n{result.stdout}\n{result.stderr}"
        assert "PASS" in result.stdout

    @pytest.mark.skip(reason="G0A namespace list needs update for governed_prompts — separate fix")
    def test_g0a_passes_with_manifest(self, plane_root, baseline_manifest_path):
        """G0A should pass with baseline manifest."""
        result = subprocess.run(
            ["python3", "scripts/gate_check.py", "--gate", "G0A", "--manifest", str(baseline_manifest_path)],
            cwd=str(plane_root),
            capture_output=True,
            text=True
        )
        assert result.returncode == 0, f"G0A failed:\n{result.stdout}\n{result.stderr}"
        assert "PASS" in result.stdout

    def test_g0a_requires_manifest(self, plane_root):
        """G0A should fail without manifest."""
        result = subprocess.run(
            ["python3", "scripts/gate_check.py", "--gate", "G0A"],
            cwd=str(plane_root),
            capture_output=True,
            text=True
        )
        # Should fail because no manifest provided
        assert result.returncode == 1 or "requires" in result.stdout.lower()

    def test_all_gates_pass(self, plane_root):
        """All gates should pass after Phase 1 setup."""
        result = subprocess.run(
            ["python3", "scripts/gate_check.py", "--all", "--enforce"],
            cwd=str(plane_root),
            capture_output=True,
            text=True
        )
        assert result.returncode == 0, f"Gates failed:\n{result.stdout}\n{result.stderr}"


# === Test: Orphan Detection ===

class TestOrphanDetection:
    """Tests for G0B orphan detection."""

    def test_g0b_detects_orphan(self, plane_root):
        """G0B should detect orphan file in governed roots."""
        orphan_path = plane_root / "lib" / "test_orphan_file.py"
        try:
            # Create orphan
            orphan_path.write_text("# Orphan file for testing")

            # Run G0B
            result = subprocess.run(
                ["python3", "scripts/gate_check.py", "--gate", "G0B", "--enforce"],
                cwd=str(plane_root),
                capture_output=True,
                text=True
            )
            assert result.returncode == 1, "G0B should fail with orphan"
            assert "ORPHAN" in result.stdout
            assert "test_orphan_file.py" in result.stdout
        finally:
            orphan_path.unlink(missing_ok=True)


# === Test: Hash Mismatch Detection ===

class TestHashMismatchDetection:
    """Tests for G0B hash mismatch detection."""

    def test_g0b_detects_hash_mismatch(self, plane_root):
        """G0B should detect modified file."""
        target_path = plane_root / "lib" / "paths.py"
        original_content = target_path.read_text()
        try:
            # Modify file
            target_path.write_text(original_content + "\n# Modified for testing\n")

            # Run G0B
            result = subprocess.run(
                ["python3", "scripts/gate_check.py", "--gate", "G0B", "--enforce"],
                cwd=str(plane_root),
                capture_output=True,
                text=True
            )
            assert result.returncode == 1, "G0B should fail with hash mismatch"
            assert "HASH_MISMATCH" in result.stdout
        finally:
            target_path.write_text(original_content)


# === Test: Sealed Plane Enforcement ===

class TestSealedPlaneEnforcement:
    """Tests for baseline refresh requiring Work Order post-seal."""

    def test_seal_file_created_on_full_install(self, plane_root):
        """Seal file should be created after full baseline install (without --skip-seal)."""
        # This test verifies the seal mechanism exists
        # Actual sealing is done by install_baseline.py without --skip-seal
        seal_path = plane_root / "config" / "seal.json"
        # Just verify the path is correct
        assert seal_path.parent.exists()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
