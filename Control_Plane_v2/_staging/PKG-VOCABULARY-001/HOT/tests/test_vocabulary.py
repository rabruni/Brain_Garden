"""TDD tests for PKG-VOCABULARY-001: G1 Chain Validation.

RED: All tests FAIL initially -- G1 is vacuous (always passes, wrong registry).
GREEN: Rewrite check_g1_chain() to validate PKG->SPEC->FMWK chains.

Tests verify:
- G1 detects missing specs (SPEC_NOT_FOUND)
- G1 detects missing frameworks (FMWK_NOT_FOUND)
- G1 passes with real registries and warns on L0 axioms (no spec_id)
- G1 validates installed packages with spec_id through the full chain
- G1 reads specs_registry.csv and frameworks_registry.csv (not control_plane_registry.csv)
"""
import json
import os
import shutil
import sys
from pathlib import Path

import pytest

# Dual-context path detection: installed root vs staging packages
_HERE = Path(__file__).resolve().parent
_HOT = _HERE.parent
_INSTALLED = (_HOT / "kernel" / "ledger_client.py").exists()

if _INSTALLED:
    # Installed layout — all packages merged under HOT/
    HOT_ROOT = _HOT
    CP_ROOT = _HOT.parent
    _paths = [_HOT / "kernel", _HOT, _HOT / "scripts"]
else:
    # Staging layout — sibling packages under _staging/
    _STAGING = _HERE.parents[2]
    HOT_ROOT = _HOT
    CP_ROOT = _STAGING.parent
    _paths = [
        _STAGING / "PKG-KERNEL-001" / "HOT" / "kernel",
        _STAGING / "PKG-KERNEL-001" / "HOT",
        _STAGING / "PKG-VOCABULARY-001" / "HOT",
    ]

for _p in _paths:
    _s = str(_p)
    if _s not in sys.path:
        sys.path.insert(0, _s)

from scripts.gate_check import check_g1_chain, GateResult


class TestG1ChainValidation:
    """G1 must validate PKG -> SPEC -> FMWK chain for every installed package."""

    def test_g1_detects_missing_spec(self, tmp_path):
        """A package with spec_id pointing to a nonexistent spec must FAIL G1."""
        # Set up minimal plane with registries
        hot_reg = tmp_path / "HOT" / "registries"
        hot_reg.mkdir(parents=True)

        # Empty specs registry (no specs at all)
        (hot_reg / "specs_registry.csv").write_text(
            "spec_id,title,framework_id,status,version,plane_id,created_at\n"
        )
        (hot_reg / "frameworks_registry.csv").write_text(
            "framework_id,title,status,version,plane_id,created_at\n"
        )

        # Create a fake installed package referencing a nonexistent spec
        pkg_dir = tmp_path / "HOT" / "installed" / "PKG-FAKE-001"
        pkg_dir.mkdir(parents=True)
        (pkg_dir / "manifest.json").write_text(json.dumps({
            "package_id": "PKG-FAKE-001",
            "spec_id": "SPEC-FAKE-999",
            "version": "1.0.0",
            "assets": []
        }))

        result = check_g1_chain(tmp_path)

        assert not result.passed, "G1 must FAIL when spec_id is not in specs_registry"
        assert any("SPEC_NOT_FOUND" in e for e in result.errors), (
            f"Expected SPEC_NOT_FOUND error, got: {result.errors}"
        )

    def test_g1_detects_missing_framework(self, tmp_path):
        """A spec pointing to a nonexistent framework must FAIL G1."""
        hot_reg = tmp_path / "HOT" / "registries"
        hot_reg.mkdir(parents=True)

        # Spec exists but points to nonexistent framework
        (hot_reg / "specs_registry.csv").write_text(
            "spec_id,title,framework_id,status,version,plane_id,created_at\n"
            "SPEC-GOOD-001,Good Spec,FMWK-FAKE-999,active,1.0.0,hot,2026-01-01T00:00:00Z\n"
        )
        # Empty frameworks registry
        (hot_reg / "frameworks_registry.csv").write_text(
            "framework_id,title,status,version,plane_id,created_at\n"
        )

        # Package referencing the spec
        pkg_dir = tmp_path / "HOT" / "installed" / "PKG-GOOD-001"
        pkg_dir.mkdir(parents=True)
        (pkg_dir / "manifest.json").write_text(json.dumps({
            "package_id": "PKG-GOOD-001",
            "spec_id": "SPEC-GOOD-001",
            "version": "1.0.0",
            "assets": []
        }))

        result = check_g1_chain(tmp_path)

        assert not result.passed, "G1 must FAIL when framework_id is not in frameworks_registry"
        assert any("FMWK_NOT_FOUND" in e for e in result.errors), (
            f"Expected FMWK_NOT_FOUND error, got: {result.errors}"
        )

    @pytest.mark.skipif(not _INSTALLED, reason="requires installed/merged root")
    def test_g1_passes_with_real_registries(self):
        """G1 must PASS against the real plane with L0 packages (warnings only)."""
        result = check_g1_chain(CP_ROOT)

        assert result.passed, f"G1 must pass with real registries, got: {result.errors}"
        assert result.details is not None, "G1 must provide details"
        assert result.details.get("specs_loaded", 0) > 0, "G1 must load specs_registry"
        assert result.details.get("frameworks_loaded", 0) > 0, "G1 must load frameworks_registry"

    def test_g1_warns_on_no_spec_id(self, tmp_path):
        """Packages with no spec_id should produce warnings, not errors."""
        hot_reg = tmp_path / "HOT" / "registries"
        hot_reg.mkdir(parents=True)
        (hot_reg / "specs_registry.csv").write_text(
            "spec_id,title,framework_id,status,version,plane_id,created_at\n"
        )
        (hot_reg / "frameworks_registry.csv").write_text(
            "framework_id,title,status,version,plane_id,created_at\n"
        )
        pkg_dir = tmp_path / "HOT" / "installed" / "PKG-NO-SPEC-001"
        pkg_dir.mkdir(parents=True)
        (pkg_dir / "manifest.json").write_text(json.dumps({
            "package_id": "PKG-NO-SPEC-001",
            "version": "1.0.0",
            "assets": []
        }))
        result = check_g1_chain(tmp_path)
        assert result.passed, f"G1 should pass, got errors: {result.errors}"
        no_spec_warnings = [w for w in result.warnings if "NO_SPEC" in w]
        assert len(no_spec_warnings) == 1, (
            f"Expected 1 NO_SPEC warning, got {len(no_spec_warnings)}: {no_spec_warnings}"
        )

    def test_g1_validates_full_chain(self, tmp_path):
        """A package with valid spec_id -> framework_id chain must be validated."""
        hot_reg = tmp_path / "HOT" / "registries"
        hot_reg.mkdir(parents=True)

        (hot_reg / "specs_registry.csv").write_text(
            "spec_id,title,framework_id,status,version,plane_id,created_at\n"
            "SPEC-GATE-001,Gate Operations,FMWK-000,active,1.0.0,hot,2026-02-01T00:00:00Z\n"
        )
        (hot_reg / "frameworks_registry.csv").write_text(
            "framework_id,title,status,version,plane_id,created_at\n"
            "FMWK-000,Control Plane Governance,active,2.0.0,hot,2026-02-01T00:00:00Z\n"
        )

        # Package with valid chain
        pkg_dir = tmp_path / "HOT" / "installed" / "PKG-VOCABULARY-001"
        pkg_dir.mkdir(parents=True)
        (pkg_dir / "manifest.json").write_text(json.dumps({
            "package_id": "PKG-VOCABULARY-001",
            "spec_id": "SPEC-GATE-001",
            "version": "1.0.0",
            "assets": []
        }))

        result = check_g1_chain(tmp_path)

        assert result.passed, f"G1 must pass for valid chain, got: {result.errors}"
        assert result.details is not None
        assert result.details.get("chains_validated", 0) == 1, (
            f"Expected 1 chain validated, got: {result.details}"
        )


class TestG1RegistrySources:
    """G1 must read the correct registries, not the wrong ones."""

    @pytest.mark.skipif(not _INSTALLED, reason="requires installed/merged root")
    def test_g1_reads_specs_registry(self):
        """G1 must load specs_registry.csv and report how many specs were loaded."""
        result = check_g1_chain(CP_ROOT)

        assert result.details is not None, "G1 must provide details dict"
        specs_loaded = result.details.get("specs_loaded", 0)
        # We have 11 specs in specs_registry.csv
        assert specs_loaded >= 11, (
            f"G1 must load specs from specs_registry.csv (expected >=11, got {specs_loaded})"
        )

    @pytest.mark.skipif(not _INSTALLED, reason="requires installed/merged root")
    def test_g1_reads_frameworks_registry(self):
        """G1 must load frameworks_registry.csv and report how many frameworks were loaded."""
        result = check_g1_chain(CP_ROOT)

        assert result.details is not None, "G1 must provide details dict"
        fmwks_loaded = result.details.get("frameworks_loaded", 0)
        # We have 4 frameworks in frameworks_registry.csv
        assert fmwks_loaded >= 4, (
            f"G1 must load frameworks from frameworks_registry.csv (expected >=4, got {fmwks_loaded})"
        )
