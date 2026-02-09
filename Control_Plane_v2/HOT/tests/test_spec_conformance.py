"""TDD tests for PKG-SPEC-CONFORMANCE-001 — Zero Orphans.

RED: These tests MUST FAIL before implementation.
GREEN: Claim orphaned files into specs, add missing interfaces,
       deprecate redundant router specs.

Tests verify:
- Registry files claimed by SPEC-REG-001
- New config/schema files claimed by appropriate specs
- All active specs have at least 1 interface
- Redundant router specs are deprecated
- All specs have plane_id
- All spec manifests pass validate_spec()
"""
import json
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
HOT_ROOT = SCRIPT_DIR.parent
CP_ROOT = HOT_ROOT.parent
sys.path.insert(0, str(HOT_ROOT))

# All spec manifest paths
SPEC_PACKS = CP_ROOT / "HO3" / "spec_packs"
ALL_SPECS = sorted(SPEC_PACKS.glob("SPEC-*/manifest.yaml"))


def _parse_yaml_simple(path: Path) -> dict:
    """Minimal YAML parser for spec manifests."""
    data = {}
    current_list_key = None
    current_list = []
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("- "):
            if current_list_key:
                val = stripped[2:].strip()
                if ":" in val and not val.startswith('"') and not val.startswith("'"):
                    current_list.append(val)
                else:
                    current_list.append(val.strip('"').strip("'"))
            continue
        if current_list_key and current_list:
            data[current_list_key] = current_list
            current_list = []
            current_list_key = None
        if ":" in stripped:
            key, _, value = stripped.partition(":")
            value = value.strip().strip('"').strip("'")
            if not value:
                current_list_key = key.strip()
                current_list = []
            else:
                data[key.strip()] = value
    if current_list_key and current_list:
        data[current_list_key] = current_list
    return data


# === Registry Files Claimed ===

class TestRegistryFilesClaimed:
    """All registry files must be claimed by SPEC-REG-001."""

    REGISTRY_FILES = [
        "HO3/registries/file_ownership.csv",
        "HO3/registries/packages_state.csv",
        "HOT/registries/control_plane_registry.csv",
        "HOT/registries/frameworks_registry.csv",
        "HOT/registries/packages_registry.csv",
        "HOT/registries/specs_registry.csv",
    ]

    def test_registry_spec_claims_registry_files(self):
        """SPEC-REG-001 must list all registry files in its assets."""
        spec_path = SPEC_PACKS / "SPEC-REG-001" / "manifest.yaml"
        assert spec_path.exists()
        data = _parse_yaml_simple(spec_path)
        assets = data.get("assets", [])
        for reg_file in self.REGISTRY_FILES:
            assert reg_file in assets, \
                f"SPEC-REG-001 missing registry asset: {reg_file}"


class TestGenesisFilesClaimed:
    """New genesis config/schema files must be claimed by SPEC-GENESIS-001."""

    GENESIS_FILES = [
        "HOT/config/bootstrap_sequence.json",
        "HOT/config/seed_registry.json",
        "HOT/schemas/package_manifest_l0.json",
    ]

    def test_genesis_spec_claims_config_files(self):
        """SPEC-GENESIS-001 must list bootstrap config files in its assets."""
        spec_path = SPEC_PACKS / "SPEC-GENESIS-001" / "manifest.yaml"
        assert spec_path.exists()
        data = _parse_yaml_simple(spec_path)
        assets = data.get("assets", [])
        for f in self.GENESIS_FILES:
            assert f in assets, \
                f"SPEC-GENESIS-001 missing asset: {f}"


class TestNewTestFilesClaimed:
    """New HOT test files must be claimed by appropriate specs."""

    def test_test_files_are_claimed(self):
        """New test files in HOT/tests/ must be listed in a spec's assets."""
        new_tests = [
            "HOT/tests/test_genesis_bootstrap.py",
            "HOT/tests/test_schema_enforcement.py",
            "HOT/tests/test_framework_completeness.py",
            "HOT/tests/test_framework_wiring.py",
            "HOT/tests/test_spec_conformance.py",
        ]
        # Collect all spec assets
        all_assets = set()
        for spec_manifest in ALL_SPECS:
            data = _parse_yaml_simple(spec_manifest)
            all_assets.update(data.get("assets", []))

        for test_file in new_tests:
            assert test_file in all_assets, \
                f"Test file {test_file} not claimed by any spec"


# === Router Spec Deprecation ===

class TestRouterSpecDeprecation:
    """Redundant router specs must be deprecated."""

    def test_router_fix_deprecated(self):
        """SPEC-ROUTER-FIX-001 must be deprecated (router modules removed)."""
        spec_path = SPEC_PACKS / "SPEC-ROUTER-FIX-001" / "manifest.yaml"
        data = _parse_yaml_simple(spec_path)
        assert data.get("status") == "deprecated", \
            "SPEC-ROUTER-FIX-001 should be deprecated (router modules removed)"

    def test_router_pure_deprecated(self):
        """SPEC-ROUTER-PURE-001 must be deprecated (router modules removed)."""
        spec_path = SPEC_PACKS / "SPEC-ROUTER-PURE-001" / "manifest.yaml"
        data = _parse_yaml_simple(spec_path)
        assert data.get("status") == "deprecated", \
            "SPEC-ROUTER-PURE-001 should be deprecated (router modules removed)"

    def test_router_001_still_active(self):
        """SPEC-ROUTER-001 must remain active as the single router spec."""
        spec_path = SPEC_PACKS / "SPEC-ROUTER-001" / "manifest.yaml"
        data = _parse_yaml_simple(spec_path)
        assert data.get("status") == "active", \
            "SPEC-ROUTER-001 should remain active"


# === Spec Completeness Tests ===

class TestAllActiveSpecsHaveInterfaces:
    """Every active spec must have at least 1 interface."""

    @pytest.fixture(params=[p for p in ALL_SPECS])
    def active_spec(self, request):
        data = _parse_yaml_simple(request.param)
        if data.get("status") == "deprecated":
            pytest.skip("Deprecated spec")
        return data, request.param

    def test_has_interfaces(self, active_spec):
        data, path = active_spec
        spec_id = data.get("spec_id", path.parent.name)
        interfaces = data.get("interfaces", [])
        assert len(interfaces) >= 1, \
            f"{spec_id}: active spec must have at least 1 interface"


# === Spec Manifest Quality ===

class TestAllSpecsHavePlaneId:
    """Every spec must declare plane_id."""

    @pytest.fixture(params=[p for p in ALL_SPECS])
    def spec_manifest(self, request):
        return _parse_yaml_simple(request.param), request.param

    def test_has_plane_id(self, spec_manifest):
        data, path = spec_manifest
        spec_id = data.get("spec_id", path.parent.name)
        assert "plane_id" in data, f"{spec_id}: missing plane_id"


class TestSpecValidation:
    """All spec manifests must pass validate_spec()."""

    @pytest.fixture(params=[p for p in ALL_SPECS])
    def spec_manifest(self, request):
        return _parse_yaml_simple(request.param), request.param

    def test_passes_validate_spec(self, spec_manifest):
        data, path = spec_manifest
        from kernel.schema_validator import validate_spec
        valid, errors = validate_spec(data)
        spec_id = data.get("spec_id", path.parent.name)
        assert valid, f"{spec_id} failed validation: {errors}"
