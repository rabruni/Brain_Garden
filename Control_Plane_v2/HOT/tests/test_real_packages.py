"""TDD tests for real Layer 0 packages.

RED: All tests FAIL initially — no archives or staging dirs exist.
GREEN: Stage each package through pkgutil pipeline, update seed_registry.

Tests verify:
- Staging dirs and archives exist for all L0 packages
- Manifest asset counts match expectations
- SHA256 hashes in manifests match files on disk
- seed_registry.json has real (non-placeholder) digests
- End-to-end bootstrap: genesis_bootstrap.py installs PKG-KERNEL-001
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
HOT_ROOT = SCRIPT_DIR.parent
CP_ROOT = HOT_ROOT.parent
STAGING = CP_ROOT / "_staging"


def sha256_file(path: Path) -> str:
    """Compute SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# === PKG-GENESIS-000 ===

class TestGenesisPackage:
    """PKG-GENESIS-000: the pre-seed containing bootstrap infrastructure."""

    PKG = "PKG-GENESIS-000"
    STAGING_DIR = STAGING / "PKG-GENESIS-000"
    ARCHIVE = STAGING / "PKG-GENESIS-000.tar.gz"

    def test_genesis_staging_dir_exists(self):
        assert self.STAGING_DIR.is_dir(), f"{self.STAGING_DIR} must exist"

    def test_genesis_manifest_exists(self):
        manifest = self.STAGING_DIR / "manifest.json"
        assert manifest.is_file(), "manifest.json must exist in staging"

    def test_genesis_has_5_assets(self):
        manifest = json.loads((self.STAGING_DIR / "manifest.json").read_text())
        assets = manifest.get("assets", [])
        assert len(assets) == 5, f"Expected 5 assets, got {len(assets)}"

    def test_genesis_asset_hashes_match_disk(self):
        manifest = json.loads((self.STAGING_DIR / "manifest.json").read_text())
        for asset in manifest["assets"]:
            file_path = self.STAGING_DIR / asset["path"]
            assert file_path.is_file(), f"Asset missing: {asset['path']}"
            expected = asset["sha256"]
            if expected.startswith("sha256:"):
                expected = expected[7:]
            actual = sha256_file(file_path)
            assert actual == expected, (
                f"Hash mismatch for {asset['path']}: "
                f"manifest={expected[:16]}... actual={actual[:16]}..."
            )

    def test_genesis_archive_exists(self):
        assert self.ARCHIVE.is_file(), f"{self.ARCHIVE} must exist"

    def test_genesis_archive_contains_all_assets(self):
        manifest = json.loads((self.STAGING_DIR / "manifest.json").read_text())
        expected_paths = {a["path"] for a in manifest["assets"]}
        with tarfile.open(self.ARCHIVE, "r:gz") as tar:
            tar_paths = set()
            for member in tar.getmembers():
                if member.isfile():
                    name = member.name
                    if name.startswith("./"):
                        name = name[2:]
                    # Skip manifest.json itself
                    if name != "manifest.json":
                        tar_paths.add(name)
        missing = expected_paths - tar_paths
        assert not missing, f"Assets missing from archive: {missing}"


# === PKG-KERNEL-001 ===

class TestKernelPackage:
    """PKG-KERNEL-001: 9 kernel files that enable package_install.py."""

    PKG = "PKG-KERNEL-001"
    STAGING_DIR = STAGING / "PKG-KERNEL-001"
    ARCHIVE = STAGING / "PKG-KERNEL-001.tar.gz"

    def test_kernel_staging_dir_exists(self):
        assert self.STAGING_DIR.is_dir(), f"{self.STAGING_DIR} must exist"

    def test_kernel_has_9_assets(self):
        manifest = json.loads((self.STAGING_DIR / "manifest.json").read_text())
        assets = manifest.get("assets", [])
        assert len(assets) == 9, f"Expected 9 assets, got {len(assets)}"

    def test_kernel_archive_exists(self):
        assert self.ARCHIVE.is_file(), f"{self.ARCHIVE} must exist"

    def test_kernel_digest_in_seed_registry(self):
        seed = json.loads(
            (HOT_ROOT / "config" / "seed_registry.json").read_text()
        )
        entry = next(
            (p for p in seed["packages"] if p["id"] == "PKG-KERNEL-001"),
            None,
        )
        assert entry is not None, "PKG-KERNEL-001 not in seed_registry"
        assert entry["digest"] != "sha256:placeholder", (
            "PKG-KERNEL-001 digest is still a placeholder"
        )


# === Baseline Packages ===

class TestBaselinePackages:
    """PKG-HOT-KERNEL-000 and PKG-BASELINE-HO3-000 baseline archives."""

    def test_hot_kernel_archive_exists(self):
        archive = STAGING / "PKG-HOT-KERNEL-000.tar.gz"
        assert archive.is_file(), f"{archive} must exist"

    def test_baseline_ho3_archive_exists(self):
        archive = STAGING / "PKG-BASELINE-HO3-000.tar.gz"
        assert archive.is_file(), f"{archive} must exist"

    def test_seed_registry_no_placeholders(self):
        seed = json.loads(
            (HOT_ROOT / "config" / "seed_registry.json").read_text()
        )
        for pkg in seed["packages"]:
            assert pkg["digest"] != "sha256:placeholder", (
                f"{pkg['id']} digest is still a placeholder"
            )


# === End-to-End Bootstrap ===

class TestBootstrapEndToEnd:
    """Prove the bootstrap sequence works: genesis → kernel install."""

    def test_genesis_bootstrap_installs_kernel(self, tmp_path):
        """Extract PKG-GENESIS-000, use it to install PKG-KERNEL-001."""
        genesis_archive = STAGING / "PKG-GENESIS-000.tar.gz"
        kernel_archive = STAGING / "PKG-KERNEL-001.tar.gz"
        if not genesis_archive.is_file() or not kernel_archive.is_file():
            pytest.skip("Archives not yet built")

        # Extract genesis to tmp
        with tarfile.open(genesis_archive, "r:gz") as tar:
            tar.extractall(tmp_path)

        # Find genesis_bootstrap.py in extracted contents
        bootstrap_script = tmp_path / "HOT" / "scripts" / "genesis_bootstrap.py"
        assert bootstrap_script.is_file(), "genesis_bootstrap.py not in genesis archive"

        # Find seed_registry.json in extracted contents
        seed_registry = tmp_path / "HOT" / "config" / "seed_registry.json"
        assert seed_registry.is_file(), "seed_registry.json not in genesis archive"

        # Create a fresh target dir (simulating empty control plane)
        target = tmp_path / "install_target"
        target.mkdir()

        # Copy kernel archive to accessible location
        kernel_copy = tmp_path / "PKG-KERNEL-001.tar.gz"
        shutil.copy2(kernel_archive, kernel_copy)

        # Run genesis_bootstrap.py
        env = os.environ.copy()
        env["CONTROL_PLANE_ROOT"] = str(target)
        result = subprocess.run(
            [
                sys.executable,
                str(bootstrap_script),
                "--seed", str(seed_registry),
                "--archive", str(kernel_copy),
                "--id", "PKG-KERNEL-001",
                "--force",
            ],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, (
            f"genesis_bootstrap.py failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )

        # Verify 9 kernel files exist at correct paths
        kernel_manifest = json.loads(
            (STAGING / "PKG-KERNEL-001" / "manifest.json").read_text()
        )
        for asset in kernel_manifest["assets"]:
            installed = target / asset["path"]
            assert installed.is_file(), f"Kernel file not installed: {asset['path']}"

    def test_seed_registry_digests_match_archives(self):
        """Every digest in seed_registry matches the actual archive hash."""
        seed = json.loads(
            (HOT_ROOT / "config" / "seed_registry.json").read_text()
        )
        for pkg in seed["packages"]:
            archive = STAGING / f"{pkg['id']}.tar.gz"
            if not archive.is_file():
                pytest.fail(f"Archive missing: {archive}")
            expected = pkg["digest"]
            if expected.startswith("sha256:"):
                expected = expected[7:]
            actual = sha256_file(archive)
            assert actual == expected, (
                f"Digest mismatch for {pkg['id']}: "
                f"seed={expected[:16]}... actual={actual[:16]}..."
            )
