#!/usr/bin/env python3
"""
TDD tests for the full bootstrap sequence: CP_GEN_0 → PKG-KERNEL-001 → PKG-VOCABULARY-001 → PKG-REG-001.

Tests written BEFORE fixes — they define what "correct" looks like.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

import pytest

# _staging/ is the direct parent of tests/
STAGING_DIR = Path(__file__).resolve().parent.parent


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def extract_tar_to(tar_path: Path, dest: Path):
    with tarfile.open(tar_path, "r:gz") as tf:
        tf.extractall(dest)


# ---------------------------------------------------------------------------
# Test 1: Seed CSVs are present and parseable in PKG-KERNEL-001
# ---------------------------------------------------------------------------
class TestSeedCSVs:
    """PKG-KERNEL-001 must ship specs_registry.csv and frameworks_registry.csv."""

    def test_seed_csvs_readable(self, tmp_path):
        """Extract PKG-KERNEL-001.tar.gz, verify seed CSVs parse correctly."""
        archive = STAGING_DIR / "PKG-KERNEL-001.tar.gz"
        assert archive.exists(), f"PKG-KERNEL-001.tar.gz not found at {archive}"

        extract_tar_to(archive, tmp_path)

        # Find the CSVs (may be under PKG-KERNEL-001/ prefix or directly)
        specs_candidates = list(tmp_path.rglob("specs_registry.csv"))
        fmwk_candidates = list(tmp_path.rglob("frameworks_registry.csv"))

        assert len(specs_candidates) >= 1, "specs_registry.csv not found in archive"
        assert len(fmwk_candidates) >= 1, "frameworks_registry.csv not found in archive"

        specs_csv = specs_candidates[0]
        fmwk_csv = fmwk_candidates[0]

        # Parse specs_registry.csv
        with open(specs_csv, "r") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        spec_ids = {r["spec_id"] for r in rows}
        assert "SPEC-GENESIS-001" in spec_ids, "Missing SPEC-GENESIS-001"
        assert "SPEC-GATE-001" in spec_ids, "Missing SPEC-GATE-001"
        assert "SPEC-REG-001" in spec_ids, "Missing SPEC-REG-001"

        # Parse frameworks_registry.csv
        with open(fmwk_csv, "r") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        fmwk_ids = {r["framework_id"] for r in rows}
        assert "FMWK-000" in fmwk_ids, "Missing FMWK-000"

    def test_seed_csvs_under_hot_registries(self, tmp_path):
        """CSVs must be at HOT/registries/ path (not HO3)."""
        archive = STAGING_DIR / "PKG-KERNEL-001.tar.gz"
        extract_tar_to(archive, tmp_path)

        # Should be under HOT/registries/ (directly or under PKG-KERNEL-001/)
        hot_specs = list(tmp_path.rglob("HOT/registries/specs_registry.csv"))
        hot_fmwk = list(tmp_path.rglob("HOT/registries/frameworks_registry.csv"))

        assert len(hot_specs) >= 1, "specs_registry.csv not under HOT/registries/"
        assert len(hot_fmwk) >= 1, "frameworks_registry.csv not under HOT/registries/"


# ---------------------------------------------------------------------------
# Test 2: genesis_bootstrap.py writes file_ownership.csv
# ---------------------------------------------------------------------------
class TestGenesisWritesOwnership:
    """After genesis installs PKG-KERNEL-001, file_ownership.csv must exist."""

    def test_genesis_writes_file_ownership(self, tmp_path):
        """Run genesis_bootstrap.py to install PKG-KERNEL-001, verify file_ownership.csv."""
        # Extract CP_GEN_0 to tmp_path
        cp_gen0 = STAGING_DIR / "CP_GEN_0.tar.gz"
        if not cp_gen0.exists():
            pytest.skip("CP_GEN_0.tar.gz not yet rebuilt")

        extract_tar_to(cp_gen0, tmp_path)

        # Extract PKG-GENESIS-000
        genesis_tar = tmp_path / "PKG-GENESIS-000.tar.gz"
        assert genesis_tar.exists(), "PKG-GENESIS-000.tar.gz not in CP_GEN_0"
        extract_tar_to(genesis_tar, tmp_path)

        genesis_script = tmp_path / "HOT" / "scripts" / "genesis_bootstrap.py"
        assert genesis_script.exists(), "genesis_bootstrap.py not extracted"

        seed_json = tmp_path / "HOT" / "config" / "seed_registry.json"
        kernel_tar = tmp_path / "PKG-KERNEL-001.tar.gz"
        assert seed_json.exists(), "seed_registry.json not extracted"
        assert kernel_tar.exists(), "PKG-KERNEL-001.tar.gz not in CP_GEN_0"

        # Run genesis_bootstrap.py
        env = os.environ.copy()
        env["CONTROL_PLANE_ROOT"] = str(tmp_path)
        result = subprocess.run(
            [sys.executable, str(genesis_script),
             "--seed", str(seed_json),
             "--archive", str(kernel_tar)],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, f"genesis_bootstrap.py failed:\n{result.stdout}\n{result.stderr}"

        # Verify file_ownership.csv exists
        ownership_csv = tmp_path / "HOT" / "registries" / "file_ownership.csv"
        assert ownership_csv.exists(), (
            f"file_ownership.csv not created at {ownership_csv}\n"
            f"stdout: {result.stdout}"
        )

        # Verify it has correct columns and entries
        with open(ownership_csv, "r") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) > 0, "file_ownership.csv is empty"

        # Check required columns
        required_cols = {"file_path", "owner_package_id", "sha256", "classification", "installed_at"}
        actual_cols = set(reader.fieldnames or [])
        assert required_cols.issubset(actual_cols), (
            f"Missing columns: {required_cols - actual_cols}"
        )

        # All entries should be owned by PKG-KERNEL-001
        for row in rows:
            assert row["owner_package_id"] == "PKG-KERNEL-001", (
                f"Wrong owner for {row['file_path']}: {row['owner_package_id']}"
            )


# ---------------------------------------------------------------------------
# Test 3: atomic_copy_files respects ownership transfers
# ---------------------------------------------------------------------------
class TestAtomicCopyTransfer:
    """Files owned by a dependency can be overwritten without --force."""

    def test_atomic_copy_respects_transfer(self, tmp_path):
        """
        Scenario:
        1. PKG-A owns file.py (written in file_ownership.csv)
        2. PKG-B declares PKG-A as dependency and ships file.py
        3. Install PKG-B → overwrite should succeed without --force
        """
        # Setup: create a minimal plane with file_ownership tracking
        plane_root = tmp_path / "plane"
        registries_dir = plane_root / "HOT" / "registries"
        registries_dir.mkdir(parents=True)

        # Create the file owned by PKG-A
        target_file = plane_root / "HOT" / "kernel" / "shared.py"
        target_file.parent.mkdir(parents=True)
        target_file.write_text("# owned by PKG-A\n")

        # Write file_ownership.csv showing PKG-A owns it
        ownership_csv = registries_dir / "file_ownership.csv"
        with open(ownership_csv, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["file_path", "package_id", "sha256", "classification", "installed_at"])
            writer.writerow([
                "HOT/kernel/shared.py", "PKG-A",
                sha256_file(target_file), "library", "2026-01-01T00:00:00Z"
            ])

        # Create PKG-B archive that ships the same file and declares PKG-A as dep
        pkg_b_dir = tmp_path / "build_pkgb"
        pkg_b_assets = pkg_b_dir / "HOT" / "kernel"
        pkg_b_assets.mkdir(parents=True)
        new_content = "# now owned by PKG-B\n"
        (pkg_b_assets / "shared.py").write_text(new_content)

        manifest = {
            "package_id": "PKG-B",
            "package_type": "standard",
            "version": "1.0.0",
            "schema_version": "1.2",
            "spec_id": "SPEC-GENESIS-001",
            "plane_id": "hot",
            "assets": [{
                "path": "HOT/kernel/shared.py",
                "sha256": f"sha256:{hashlib.sha256(new_content.encode()).hexdigest()}",
                "classification": "library",
            }],
            "dependencies": ["PKG-A"],
        }
        (pkg_b_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))

        pkg_b_tar = tmp_path / "PKG-B.tar.gz"
        with tarfile.open(pkg_b_tar, "w:gz") as tf:
            tf.add(pkg_b_dir / "manifest.json", "manifest.json")
            tf.add(pkg_b_assets / "shared.py", "HOT/kernel/shared.py")

        # Now test: install PKG-B into plane_root via package_install.py
        # We need the kernel libs available, so we set up sys.path
        # For this test, we just verify the ownership validator + atomic_copy logic
        sys.path.insert(0, str(STAGING_DIR / "PKG-KERNEL-001" / "HOT"))

        from kernel.preflight import OwnershipValidator, load_file_ownership

        existing = {}
        with open(ownership_csv, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                existing[row["file_path"]] = row

        validator = OwnershipValidator()
        result = validator.validate(manifest, existing, "PKG-B", plane_root)

        # Should PASS (transfer from dep, not conflict)
        assert result.passed, f"Ownership check failed: {result.errors}"
        assert any("OWNERSHIP_TRANSFER" in w for w in result.warnings), (
            "Expected OWNERSHIP_TRANSFER warning"
        )


# ---------------------------------------------------------------------------
# Test 4: No HO3 paths in any manifest or directories
# ---------------------------------------------------------------------------
class TestHO3Eliminated:
    """No HO3 references should exist in staging packages."""

    def test_no_ho3_in_kernel_manifest(self):
        """PKG-KERNEL-001 manifest should have no HO3 paths."""
        manifest_path = STAGING_DIR / "PKG-KERNEL-001" / "manifest.json"
        manifest = json.loads(manifest_path.read_text())

        assert manifest["plane_id"] != "ho3", f"plane_id is still ho3"
        for asset in manifest["assets"]:
            assert not asset["path"].startswith("HO3/"), (
                f"HO3 path found: {asset['path']}"
            )

    def test_no_ho3_in_genesis_manifest(self):
        """PKG-GENESIS-000 manifest should have no ho3 plane_id."""
        manifest_path = STAGING_DIR / "PKG-GENESIS-000" / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        assert manifest["plane_id"] != "ho3", f"plane_id is still ho3"

    def test_no_ho3_in_reg_manifest(self):
        """PKG-REG-001 manifest should have no HO3 paths."""
        manifest_path = STAGING_DIR / "PKG-REG-001" / "manifest.json"
        manifest = json.loads(manifest_path.read_text())

        assert manifest["plane_id"] != "ho3", f"plane_id is still ho3"
        for asset in manifest["assets"]:
            assert not asset["path"].startswith("HO3/"), (
                f"HO3 path found: {asset['path']}"
            )

    def test_no_ho3_dirs_after_genesis(self, tmp_path):
        """After genesis installs PKG-KERNEL-001, no HO3 dir should exist."""
        cp_gen0 = STAGING_DIR / "CP_GEN_0.tar.gz"
        if not cp_gen0.exists():
            pytest.skip("CP_GEN_0.tar.gz not yet rebuilt")

        extract_tar_to(cp_gen0, tmp_path)
        genesis_tar = tmp_path / "PKG-GENESIS-000.tar.gz"
        extract_tar_to(genesis_tar, tmp_path)

        genesis_script = tmp_path / "HOT" / "scripts" / "genesis_bootstrap.py"
        seed_json = tmp_path / "HOT" / "config" / "seed_registry.json"
        kernel_tar = tmp_path / "PKG-KERNEL-001.tar.gz"

        env = os.environ.copy()
        env["CONTROL_PLANE_ROOT"] = str(tmp_path)
        result = subprocess.run(
            [sys.executable, str(genesis_script),
             "--seed", str(seed_json),
             "--archive", str(kernel_tar)],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, f"genesis failed:\n{result.stdout}\n{result.stderr}"

        ho3_dirs = list(tmp_path.rglob("HO3"))
        assert len(ho3_dirs) == 0, f"HO3 directories found: {ho3_dirs}"


# ---------------------------------------------------------------------------
# Test 5: Full bootstrap sequence end-to-end
# ---------------------------------------------------------------------------
class TestFullBootstrapSequence:
    """End-to-end: CP_GEN_0 → KERNEL-001 → VOCABULARY-001 → REG-001."""

    def test_full_bootstrap_sequence(self, tmp_path):
        """Complete bootstrap with no --force, no HO3, full ownership tracking."""
        cp_gen0 = STAGING_DIR / "CP_GEN_0.tar.gz"
        vocab_tar = STAGING_DIR / "PKG-VOCABULARY-001.tar.gz"
        reg_tar = STAGING_DIR / "PKG-REG-001.tar.gz"

        if not cp_gen0.exists():
            pytest.skip("CP_GEN_0.tar.gz not yet rebuilt")
        if not vocab_tar.exists():
            pytest.skip("PKG-VOCABULARY-001.tar.gz not yet rebuilt")
        if not reg_tar.exists():
            pytest.skip("PKG-REG-001.tar.gz not yet rebuilt")

        # Step 0: Extract CP_GEN_0
        extract_tar_to(cp_gen0, tmp_path)
        genesis_tar = tmp_path / "PKG-GENESIS-000.tar.gz"
        extract_tar_to(genesis_tar, tmp_path)

        genesis_script = tmp_path / "HOT" / "scripts" / "genesis_bootstrap.py"
        seed_json = tmp_path / "HOT" / "config" / "seed_registry.json"
        kernel_tar = tmp_path / "PKG-KERNEL-001.tar.gz"

        env = os.environ.copy()
        env["CONTROL_PLANE_ROOT"] = str(tmp_path)

        # Step 1: genesis installs PKG-KERNEL-001
        r1 = subprocess.run(
            [sys.executable, str(genesis_script),
             "--seed", str(seed_json),
             "--archive", str(kernel_tar)],
            env=env, capture_output=True, text=True, timeout=30,
        )
        assert r1.returncode == 0, f"Step 1 failed:\n{r1.stdout}\n{r1.stderr}"

        # Verify: kernel installed at HOT (not HO3)
        assert (tmp_path / "HOT" / "scripts" / "package_install.py").exists(), \
            "package_install.py not at HOT/scripts/"
        assert (tmp_path / "HOT" / "registries" / "file_ownership.csv").exists(), \
            "file_ownership.csv not created"
        assert (tmp_path / "HOT" / "registries" / "specs_registry.csv").exists(), \
            "specs_registry.csv not installed"

        # Step 2: package_install.py installs PKG-VOCABULARY-001
        install_script = tmp_path / "HOT" / "scripts" / "package_install.py"
        r2 = subprocess.run(
            [sys.executable, str(install_script),
             "--archive", str(vocab_tar),
             "--id", "PKG-VOCABULARY-001",
             "--root", str(tmp_path),
             "--dev"],
            env=env, capture_output=True, text=True, timeout=30,
        )
        assert r2.returncode == 0, f"Step 2 failed:\n{r2.stdout}\n{r2.stderr}"

        # Verify: gate_check.py installed
        assert (tmp_path / "HOT" / "scripts" / "gate_check.py").exists(), \
            "gate_check.py not installed by PKG-VOCABULARY-001"

        # Step 3: package_install.py installs PKG-REG-001 (ownership transfer, no --force)
        r3 = subprocess.run(
            [sys.executable, str(install_script),
             "--archive", str(reg_tar),
             "--id", "PKG-REG-001",
             "--root", str(tmp_path),
             "--dev"],
            env=env, capture_output=True, text=True, timeout=30,
        )
        assert r3.returncode == 0, (
            f"Step 3 failed (ownership transfer should work without --force):\n"
            f"{r3.stdout}\n{r3.stderr}"
        )

        # Final checks
        assert (tmp_path / "HOT" / "installed" / "PKG-REG-001" / "receipt.json").exists(), \
            "PKG-REG-001 receipt not found"

        # No HO3 directories anywhere
        ho3_dirs = list(tmp_path.rglob("HO3"))
        assert len(ho3_dirs) == 0, f"HO3 directories found: {ho3_dirs}"

        # file_ownership.csv has entries
        ownership_csv = tmp_path / "HOT" / "registries" / "file_ownership.csv"
        with open(ownership_csv, "r") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) > 0, "file_ownership.csv is empty after full bootstrap"
