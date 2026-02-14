"""TDD tests for materialize_layout.py — Tier directory materializer.

Tests verify:
- HO2/ and HO1/ root directories are created
- All 7 tier_dirs subdirectories created under each tier
- HOT/ directories already exist and are not errored on
- Idempotent: running twice is safe
- Config-driven: reads layout.json, not hardcoded
- No data files created in tier directories
- Proper error handling for missing layout.json
- Exit codes and output reporting
- Respects --root / CONTROL_PLANE_ROOT
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
HOT_ROOT = SCRIPT_DIR.parent
CP_ROOT = HOT_ROOT.parent

# Path to the materializer script
MATERIALIZE_SCRIPT = HOT_ROOT / "scripts" / "materialize_layout.py"

# The 7 tier_dirs from layout.json
TIER_SUBDIRS = ["registries", "installed", "ledger", "packages_store",
                "scripts", "tests", "spec_packs"]


def _setup_minimal_plane(tmp_path: Path) -> Path:
    """Create a minimal plane root with layout.json for testing.

    Returns the plane root path.
    """
    plane_root = tmp_path / "plane"
    config_dir = plane_root / "HOT" / "config"
    config_dir.mkdir(parents=True)

    layout = {
        "schema_version": "1.1",
        "tiers": {
            "HOT": "HOT",
            "HO2": "HO2",
            "HO1": "HO1"
        },
        "hot_dirs": {
            "kernel": "HOT/kernel",
            "config": "HOT/config",
            "registries": "HOT/registries",
            "schemas": "HOT/schemas",
            "scripts": "HOT/scripts",
            "installed": "HOT/installed",
            "ledger": "HOT/ledger",
            "frameworks": "HOT"
        },
        "tier_dirs": {
            "registries": "registries",
            "installed": "installed",
            "ledger": "ledger",
            "packages_store": "packages_store",
            "scripts": "scripts",
            "tests": "tests",
            "spec_packs": "spec_packs"
        },
        "registry_files": {
            "control_plane": "control_plane_registry.csv",
            "file_ownership": "file_ownership.csv",
            "packages_state": "packages_state.csv",
            "frameworks": "frameworks_registry.csv",
            "specs": "specs_registry.csv"
        },
        "ledger_files": {
            "governance": "governance.jsonl",
            "packages": "packages.jsonl",
            "kernel": "kernel.jsonl",
            "index": "index.jsonl"
        }
    }
    (config_dir / "layout.json").write_text(json.dumps(layout, indent=2))
    return plane_root


def _run_materializer(plane_root: Path) -> subprocess.CompletedProcess:
    """Run materialize_layout.py against a plane root."""
    return subprocess.run(
        [sys.executable, str(MATERIALIZE_SCRIPT), "--root", str(plane_root)],
        capture_output=True, text=True, timeout=30,
    )


class TestMaterializeCreatesRoots:
    """Materializer must create tier root directories."""

    def test_materialize_creates_ho2_root(self, tmp_path):
        """HO2/ directory must be created."""
        plane_root = _setup_minimal_plane(tmp_path)
        _run_materializer(plane_root)
        assert (plane_root / "HO2").is_dir(), "HO2/ not created"

    def test_materialize_creates_ho1_root(self, tmp_path):
        """HO1/ directory must be created."""
        plane_root = _setup_minimal_plane(tmp_path)
        _run_materializer(plane_root)
        assert (plane_root / "HO1").is_dir(), "HO1/ not created"


class TestMaterializeCreatesSubdirs:
    """Materializer must create all 7 tier_dirs under each tier."""

    def test_materialize_creates_ho2_subdirs(self, tmp_path):
        """HO2/ must have all 7 tier_dirs subdirectories."""
        plane_root = _setup_minimal_plane(tmp_path)
        _run_materializer(plane_root)
        for subdir in TIER_SUBDIRS:
            assert (plane_root / "HO2" / subdir).is_dir(), \
                f"HO2/{subdir} not created"

    def test_materialize_creates_ho1_subdirs(self, tmp_path):
        """HO1/ must have all 7 tier_dirs subdirectories."""
        plane_root = _setup_minimal_plane(tmp_path)
        _run_materializer(plane_root)
        for subdir in TIER_SUBDIRS:
            assert (plane_root / "HO1" / subdir).is_dir(), \
                f"HO1/{subdir} not created"


class TestMaterializeIdempotent:
    """Materializer must be safe to run multiple times."""

    def test_materialize_hot_already_exists(self, tmp_path):
        """HOT/ dirs already present must not cause errors."""
        plane_root = _setup_minimal_plane(tmp_path)
        # Pre-create HOT dirs (simulating bootstrap)
        for d in ["kernel", "config", "registries", "schemas",
                   "scripts", "installed", "ledger"]:
            (plane_root / "HOT" / d).mkdir(parents=True, exist_ok=True)

        result = _run_materializer(plane_root)
        assert result.returncode == 0, f"Failed: {result.stderr}"
        assert "exist" in result.stdout.lower() or "already" in result.stdout.lower(), \
            "Should report already-existing dirs"

    def test_materialize_idempotent(self, tmp_path):
        """Running materializer twice must produce same result, no errors."""
        plane_root = _setup_minimal_plane(tmp_path)
        r1 = _run_materializer(plane_root)
        assert r1.returncode == 0, f"First run failed: {r1.stderr}"

        r2 = _run_materializer(plane_root)
        assert r2.returncode == 0, f"Second run failed: {r2.stderr}"

        # Both runs should complete without error
        for tier in ["HO2", "HO1"]:
            for subdir in TIER_SUBDIRS:
                assert (plane_root / tier / subdir).is_dir()


class TestMaterializeConfigDriven:
    """Materializer must read layout.json, not hardcode tier names."""

    def test_materialize_reads_layout_json(self, tmp_path):
        """Materializer uses tier names from layout.json, not hardcoded.

        Verify by providing a custom layout.json with only 2 tiers.
        """
        plane_root = tmp_path / "plane"
        config_dir = plane_root / "HOT" / "config"
        config_dir.mkdir(parents=True)

        # Custom layout with only 2 tiers: HOT and CUSTOM
        custom_layout = {
            "schema_version": "1.1",
            "tiers": {"HOT": "HOT", "CUSTOM": "CUSTOM"},
            "hot_dirs": {
                "kernel": "HOT/kernel", "config": "HOT/config",
                "registries": "HOT/registries", "schemas": "HOT/schemas",
                "scripts": "HOT/scripts", "installed": "HOT/installed",
                "ledger": "HOT/ledger", "frameworks": "HOT"
            },
            "tier_dirs": {
                "registries": "registries", "installed": "installed",
                "ledger": "ledger", "packages_store": "packages_store",
                "scripts": "scripts", "tests": "tests",
                "spec_packs": "spec_packs"
            },
            "registry_files": {},
            "ledger_files": {}
        }
        (config_dir / "layout.json").write_text(json.dumps(custom_layout, indent=2))

        result = _run_materializer(plane_root)
        assert result.returncode == 0, f"Failed: {result.stderr}"

        # CUSTOM tier should exist
        assert (plane_root / "CUSTOM").is_dir(), "CUSTOM tier not created"
        assert (plane_root / "CUSTOM" / "registries").is_dir()

        # HO2 and HO1 should NOT exist (not in this layout)
        assert not (plane_root / "HO2").exists(), "HO2 should not exist in custom layout"
        assert not (plane_root / "HO1").exists(), "HO1 should not exist in custom layout"


class TestMaterializeNoDataFiles:
    """Materializer must NOT create any data files."""

    def test_materialize_no_data_files_created(self, tmp_path):
        """After materialize, tier registries/ and ledger/ must be empty."""
        plane_root = _setup_minimal_plane(tmp_path)
        _run_materializer(plane_root)

        # HO2/registries/ must be empty (no CSV files)
        ho2_reg = plane_root / "HO2" / "registries"
        assert ho2_reg.is_dir()
        assert list(ho2_reg.iterdir()) == [], \
            f"HO2/registries/ should be empty, found: {list(ho2_reg.iterdir())}"

        # HO1/ledger/ must be empty (no JSONL files)
        ho1_ledger = plane_root / "HO1" / "ledger"
        assert ho1_ledger.is_dir()
        assert list(ho1_ledger.iterdir()) == [], \
            f"HO1/ledger/ should be empty, found: {list(ho1_ledger.iterdir())}"


class TestMaterializeErrorHandling:
    """Materializer must handle errors properly."""

    def test_materialize_missing_layout_json(self, tmp_path):
        """Missing layout.json must produce exit code 1."""
        plane_root = tmp_path / "empty_plane"
        plane_root.mkdir()
        result = _run_materializer(plane_root)
        assert result.returncode == 1, \
            f"Expected exit code 1, got {result.returncode}. stderr: {result.stderr}"


class TestMaterializeOutput:
    """Materializer must report what it did."""

    def test_materialize_exit_code_zero(self, tmp_path):
        """Successful run must return exit code 0."""
        plane_root = _setup_minimal_plane(tmp_path)
        result = _run_materializer(plane_root)
        assert result.returncode == 0, f"Expected exit 0, got {result.returncode}: {result.stderr}"

    def test_materialize_output_reports_counts(self, tmp_path):
        """stdout must contain created/existed counts."""
        plane_root = _setup_minimal_plane(tmp_path)
        result = _run_materializer(plane_root)
        assert result.returncode == 0
        out = result.stdout.lower()
        assert "created" in out, f"Output should mention 'created': {result.stdout}"

    def test_materialize_respects_control_plane_root(self, tmp_path):
        """Materializer uses --root arg or CONTROL_PLANE_ROOT env var."""
        plane_root = _setup_minimal_plane(tmp_path)

        # Test with --root (already used by _run_materializer)
        result = _run_materializer(plane_root)
        assert result.returncode == 0

        # Test with env var
        plane_root2 = _setup_minimal_plane(tmp_path / "env_test")
        env = os.environ.copy()
        env["CONTROL_PLANE_ROOT"] = str(plane_root2)
        result2 = subprocess.run(
            [sys.executable, str(MATERIALIZE_SCRIPT)],
            capture_output=True, text=True, timeout=30, env=env,
        )
        assert result2.returncode == 0, f"Env var failed: {result2.stderr}"
        assert (plane_root2 / "HO2").is_dir(), "HO2 not created via env var"
