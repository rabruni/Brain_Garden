#!/usr/bin/env python3
"""
Phase 4 Kernel Parity Tests

Tests for PKG-KERNEL-001 packaging, replication, and G0K gate.

Acceptance Criteria:
- AC-K1: Kernel build is deterministic (same input → same hash)
- AC-K2: Kernel manifest replicated to all tiers
- AC-K3: Ledger events written on kernel install
- AC-K4: G0K gate detects parity violations
- AC-K5: G6 gate verifies ledger chain integrity
- AC-K6: WO modifying kernel files fails unless kernel_upgrade type
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

# Add parent to path
SCRIPT_DIR = Path(__file__).resolve().parent
CONTROL_PLANE_ROOT = SCRIPT_DIR.parent          # HO3/
CP_ROOT = CONTROL_PLANE_ROOT.parent             # Control_Plane_v2/
HOT_ROOT = CP_ROOT / "HOT"
sys.path.insert(0, str(CONTROL_PLANE_ROOT))
sys.path.insert(0, str(HOT_ROOT))
sys.path.insert(0, str(HOT_ROOT / "scripts"))


# === Fixtures ===

@pytest.fixture
def plane_root():
    """Return the Control Plane root path."""
    return CONTROL_PLANE_ROOT


@pytest.fixture
def kernel_manifest_path(plane_root):
    """Return the kernel manifest path in packages_store."""
    return plane_root / "packages_store" / "PKG-KERNEL-001" / "manifest.json"


@pytest.fixture
def kernel_manifest(kernel_manifest_path):
    """Load the kernel manifest."""
    if not kernel_manifest_path.exists():
        pytest.skip("Kernel manifest not built yet")
    return json.loads(kernel_manifest_path.read_text())


@pytest.fixture
def kernel_files_config(plane_root):
    """Load kernel files configuration."""
    config_path = HOT_ROOT / "config" / "kernel_files.json"
    if not config_path.exists():
        pytest.skip("Kernel files config not found")
    return json.loads(config_path.read_text())


# === AC-K1: Deterministic Build ===

class TestDeterministicBuild:
    """Tests for kernel build determinism."""

    def test_kernel_build_produces_manifest(self, plane_root):
        """Kernel build should produce a valid manifest."""
        result = subprocess.run(
            ["python3", str(HOT_ROOT / "scripts" / "kernel_build.py"), "--json"],
            cwd=str(CP_ROOT),
            capture_output=True,
            text=True
        )
        assert result.returncode == 0, f"kernel_build.py failed: {result.stderr}"
        manifest = json.loads(result.stdout)
        assert "package_id" in manifest
        assert manifest["package_id"] == "PKG-KERNEL-001"
        assert "assets" in manifest
        assert len(manifest["assets"]) > 0

    def test_kernel_build_is_deterministic(self, plane_root):
        """Running kernel_build twice should produce same manifest_hash."""
        result1 = subprocess.run(
            ["python3", str(HOT_ROOT / "scripts" / "kernel_build.py"), "--show-hash", "--dry-run"],
            cwd=str(CP_ROOT),
            capture_output=True,
            text=True
        )
        result2 = subprocess.run(
            ["python3", str(HOT_ROOT / "scripts" / "kernel_build.py"), "--show-hash", "--dry-run"],
            cwd=str(CP_ROOT),
            capture_output=True,
            text=True
        )

        hash1 = [l for l in result1.stdout.split("\n") if l.startswith("manifest_hash=")]
        hash2 = [l for l in result2.stdout.split("\n") if l.startswith("manifest_hash=")]

        assert len(hash1) == 1, "First run did not produce manifest_hash"
        assert len(hash2) == 1, "Second run did not produce manifest_hash"
        assert hash1[0] == hash2[0], f"Hashes differ: {hash1[0]} vs {hash2[0]}"

    def test_kernel_manifest_has_required_fields(self, kernel_manifest):
        """Kernel manifest must have required fields."""
        required = ["package_id", "package_type", "version", "assets", "manifest_hash"]
        for field in required:
            assert field in kernel_manifest, f"Missing field: {field}"

        assert kernel_manifest["package_type"] == "kernel"
        assert kernel_manifest["manifest_hash"].startswith("sha256:")


# === AC-K2: Replicated Manifest ===

class TestReplicatedManifest:
    """Tests for kernel manifest replication to all tiers."""

    TIERS = ["HO3", "HO2", "HO1"]
    TIER_PATHS = {
        "HO3": CP_ROOT / "HO3" / "installed" / "PKG-KERNEL-001" / "manifest.json",
        "HO2": CP_ROOT / "HO2" / "installed" / "PKG-KERNEL-001" / "manifest.json",
        "HO1": CP_ROOT / "HO1" / "installed" / "PKG-KERNEL-001" / "manifest.json",
    }

    def test_kernel_manifest_exists_on_all_tiers(self, plane_root):
        """Kernel manifest must exist on HO3, HO2, and HO1."""
        for tier, manifest_path in self.TIER_PATHS.items():
            assert manifest_path.exists(), f"Kernel manifest missing on {tier}: {manifest_path}"

    def test_kernel_manifests_are_identical(self, plane_root):
        """Kernel manifests must be identical across all tiers."""
        manifests = {}
        for tier, manifest_path in self.TIER_PATHS.items():
            if manifest_path.exists():
                manifests[tier] = manifest_path.read_text()

        if len(manifests) < 2:
            pytest.skip("Need at least 2 tier manifests to compare")

        reference_content = list(manifests.values())[0]
        for tier, content in manifests.items():
            assert content == reference_content, f"Manifest differs on {tier}"

    def test_kernel_manifest_hashes_match(self, plane_root):
        """Kernel manifest hashes must match across all tiers."""
        hashes = {}
        for tier, manifest_path in self.TIER_PATHS.items():
            if manifest_path.exists():
                manifest = json.loads(manifest_path.read_text())
                # Compute hash from assets (same as in kernel_build.py)
                assets_json = json.dumps(manifest.get("assets", []), sort_keys=True, separators=(",", ":"))
                computed_hash = f"sha256:{hashlib.sha256(assets_json.encode()).hexdigest()}"
                hashes[tier] = computed_hash

        if len(hashes) < 2:
            pytest.skip("Need at least 2 tier manifests to compare")

        reference_hash = list(hashes.values())[0]
        for tier, h in hashes.items():
            assert h == reference_hash, f"Hash differs on {tier}: {h} vs {reference_hash}"


# === AC-K3: Ledger Events ===

class TestLedgerEvents:
    """Tests for kernel install ledger events."""

    TIER_LEDGERS = {
        "HO3": CP_ROOT / "HO3" / "ledger" / "kernel.jsonl",
        "HO2": CP_ROOT / "HO2" / "ledger" / "kernel.jsonl",
        "HO1": CP_ROOT / "HO1" / "ledger" / "kernel.jsonl",
    }

    def test_kernel_ledger_exists_on_all_tiers(self, plane_root):
        """Kernel ledger must exist on all tiers."""
        for tier, ledger_path in self.TIER_LEDGERS.items():
            assert ledger_path.exists(), f"Kernel ledger missing on {tier}: {ledger_path}"

    def test_kernel_install_event_on_all_tiers(self, plane_root):
        """KERNEL_INSTALLED event must exist on all tiers."""
        for tier, ledger_path in self.TIER_LEDGERS.items():
            if not ledger_path.exists():
                pytest.skip(f"Kernel ledger not found on {tier}")

            entries = []
            with open(ledger_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        entries.append(json.loads(line))

            kernel_installed = [e for e in entries if e.get("event_type") == "KERNEL_INSTALLED"]
            assert len(kernel_installed) >= 1, f"No KERNEL_INSTALLED event on {tier}"

    def test_kernel_ledger_has_manifest_hash(self, plane_root):
        """KERNEL_INSTALLED event must have manifest_hash in metadata."""
        for tier, ledger_path in self.TIER_LEDGERS.items():
            if not ledger_path.exists():
                continue

            entries = []
            with open(ledger_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        entries.append(json.loads(line))

            kernel_installed = [e for e in entries if e.get("event_type") == "KERNEL_INSTALLED"]
            if kernel_installed:
                latest = kernel_installed[-1]
                metadata = latest.get("metadata", {})
                assert "manifest_hash" in metadata, f"No manifest_hash in {tier} KERNEL_INSTALLED event"
                assert metadata["manifest_hash"].startswith("sha256:")


# === AC-K4: G0K Gate ===

class TestG0KGate:
    """Tests for G0K KERNEL_PARITY gate."""

    def test_g0k_passes_with_identical_manifests(self, plane_root):
        """G0K should pass when all tier manifests are identical."""
        result = subprocess.run(
            ["python3", str(HOT_ROOT / "scripts" / "g0k_gate.py"), "--enforce"],
            cwd=str(CP_ROOT),
            capture_output=True,
            text=True
        )
        assert result.returncode == 0, f"G0K failed: {result.stdout}"
        assert "PASS" in result.stdout

    def test_g0k_detects_missing_manifest(self, plane_root):
        """G0K should detect missing kernel manifest on a tier."""
        # Temporarily rename HO2 kernel manifest
        ho2_manifest = CP_ROOT / "HO2" / "installed" / "PKG-KERNEL-001" / "manifest.json"
        ho2_manifest_bak = ho2_manifest.with_suffix(".json.bak")

        if not ho2_manifest.exists():
            pytest.skip("HO2 kernel manifest not found")

        try:
            ho2_manifest.rename(ho2_manifest_bak)

            result = subprocess.run(
                ["python3", str(HOT_ROOT / "scripts" / "g0k_gate.py"), "--enforce"],
                cwd=str(CP_ROOT),
                capture_output=True,
                text=True
            )
            assert result.returncode == 1, "G0K should fail with missing manifest"
            assert "missing" in result.stdout.lower() or "FAIL" in result.stdout
        finally:
            if ho2_manifest_bak.exists():
                ho2_manifest_bak.rename(ho2_manifest)

    def test_g0k_detects_hash_mismatch(self, plane_root):
        """G0K should detect manifest hash mismatch between tiers."""
        # Temporarily modify HO1 kernel manifest
        ho1_manifest = CP_ROOT / "HO1" / "installed" / "PKG-KERNEL-001" / "manifest.json"

        if not ho1_manifest.exists():
            pytest.skip("HO1 kernel manifest not found")

        original_content = ho1_manifest.read_text()

        try:
            # Modify manifest assets to cause hash mismatch (hash is computed from assets)
            manifest = json.loads(original_content)
            if manifest.get("assets"):
                # Modify a hash in the assets to cause mismatch
                manifest["assets"][0]["sha256"] = "sha256:0000000000000000000000000000000000000000000000000000000000000000"
            ho1_manifest.write_text(json.dumps(manifest, indent=2))

            result = subprocess.run(
                ["python3", str(HOT_ROOT / "scripts" / "g0k_gate.py"), "--enforce"],
                cwd=str(CP_ROOT),
                capture_output=True,
                text=True
            )
            assert result.returncode == 1, "G0K should fail with hash mismatch"
            assert "FAIL" in result.stdout or "mismatch" in result.stdout.lower()
        finally:
            ho1_manifest.write_text(original_content)

    def test_g0k_file_verification(self, plane_root):
        """G0K should verify files match manifest hashes."""
        result = subprocess.run(
            ["python3", str(HOT_ROOT / "scripts" / "g0k_gate.py"), "--verify-files"],
            cwd=str(CP_ROOT),
            capture_output=True,
            text=True
        )
        # Should pass since files haven't been modified
        assert "PASS" in result.stdout
        assert "8/8 OK" in result.stdout or "verification" in result.stdout.lower()


# === AC-K5: G6 Ledger Verification ===

class TestG6Gate:
    """Tests for G6 LEDGER gate."""

    def test_g6_passes(self, plane_root):
        """G6 should pass with valid ledger chains."""
        result = subprocess.run(
            ["python3", str(HOT_ROOT / "scripts" / "g6_gate.py"), "--enforce"],
            cwd=str(CP_ROOT),
            capture_output=True,
            text=True
        )
        assert result.returncode == 0, f"G6 failed: {result.stdout}"
        assert "PASS" in result.stdout

    def test_g6_verifies_kernel_parity(self, plane_root):
        """G6 should verify kernel parity via ledger events."""
        result = subprocess.run(
            ["python3", str(HOT_ROOT / "scripts" / "g6_gate.py"), "--json"],
            cwd=str(CP_ROOT),
            capture_output=True,
            text=True
        )
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output["kernel_parity_valid"] is True


# === AC-K6: Kernel Modification Guard ===

class TestKernelModificationGuard:
    """Tests for preventing unauthorized kernel modifications."""

    def test_wo_with_kernel_files_and_wrong_type_fails(self, plane_root, kernel_files_config):
        """WO modifying kernel files must fail unless type is kernel_upgrade."""
        kernel_files = kernel_files_config.get("files", [])
        if not kernel_files:
            pytest.skip("No kernel files defined")

        # Create a test WO that tries to modify a kernel file with wrong type
        test_wo = {
            "work_order_id": "WO-TEST-KERNEL-001",
            "type": "code_change",  # NOT kernel_upgrade
            "plane_id": "ho3",
            "spec_id": "SPEC-CORE-001",
            "framework_id": "FMWK-000",
            "scope": {
                "allowed_files": [kernel_files[0]],  # Try to modify kernel file
                "forbidden_files": []
            },
            "acceptance": {
                "tests": ["echo test"],
                "checks": []
            }
        }

        # Test G0K with this WO
        from g0k_gate import run_g0k_gate

        result = run_g0k_gate(wo=test_wo)
        assert not result.passed, "G0K should reject WO modifying kernel files without kernel_upgrade type"
        assert "kernel" in result.message.lower()

    def test_wo_with_kernel_upgrade_type_allowed(self, plane_root, kernel_files_config):
        """WO with type=kernel_upgrade should be allowed to modify kernel files."""
        kernel_files = kernel_files_config.get("files", [])
        if not kernel_files:
            pytest.skip("No kernel files defined")

        # Create a test WO with kernel_upgrade type
        test_wo = {
            "work_order_id": "WO-TEST-KERNEL-002",
            "type": "kernel_upgrade",  # Correct type
            "plane_id": "ho3",
            "spec_id": "SPEC-CORE-001",
            "framework_id": "FMWK-000",
            "scope": {
                "allowed_files": [kernel_files[0]],
                "forbidden_files": []
            },
            "acceptance": {
                "tests": ["echo test"],
                "checks": []
            }
        }

        # Test G0K with this WO - should NOT fail on kernel file check
        from g0k_gate import run_g0k_gate

        result = run_g0k_gate(wo=test_wo)
        # G0K should pass the kernel modification check (may fail for other reasons)
        # If it fails, it should NOT be because of kernel file modification
        if not result.passed:
            assert "kernel" not in result.message.lower() or "kernel_upgrade" in result.message.lower()


# === Integration Test ===

class TestKernelPipelineIntegration:
    """Integration tests for the full kernel pipeline."""

    def test_kernel_pipeline_all_gates_pass(self, plane_root):
        """All kernel-related gates should pass after kernel install."""
        # Test G0K
        result = subprocess.run(
            ["python3", str(HOT_ROOT / "scripts" / "gate_check.py"), "--gate", "G0K", "--enforce"],
            cwd=str(CP_ROOT),
            capture_output=True,
            text=True
        )
        assert result.returncode == 0, f"G0K failed: {result.stdout}"

        # Test G6
        result = subprocess.run(
            ["python3", str(HOT_ROOT / "scripts" / "gate_check.py"), "--gate", "G6", "--enforce"],
            cwd=str(CP_ROOT),
            capture_output=True,
            text=True
        )
        assert result.returncode == 0, f"G6 failed: {result.stdout}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
