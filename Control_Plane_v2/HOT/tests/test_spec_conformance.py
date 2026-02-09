"""TDD tests for Spec Conformance — Kernel Core Strip.

Tests verify:
- Registry files claimed by SPEC-REG-001
- New config/schema files claimed by appropriate specs
- 14 dead spec dirs are removed
- Exactly 11 specs, 4 frameworks, 8 schemas remain
- No surviving spec has HO3/tests/ in its assets
- All active specs have at least 1 interface
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


# === Dead Spec Removal ===

DEAD_SPECS = [
    "SPEC-ADMIN-001", "SPEC-CORE-SCRIPTS-001", "SPEC-DOC-001",
    "SPEC-EVIDENCE-001", "SPEC-FMWK-001", "SPEC-FMWK-CAPS-001",
    "SPEC-INSPECT-001", "SPEC-PROMPT-001", "SPEC-RATE-MGMT-001",
    "SPEC-ROUTER-001", "SPEC-ROUTER-FIX-001", "SPEC-ROUTER-PURE-001",
    "SPEC-RUNTIME-001", "SPEC-TEST-001",
]

SURVIVING_SPECS = [
    "SPEC-CORE-001", "SPEC-GATE-001", "SPEC-GENESIS-001",
    "SPEC-INT-001", "SPEC-LEDGER-001", "SPEC-PKG-001",
    "SPEC-PLANE-001", "SPEC-POLICY-001", "SPEC-REG-001",
    "SPEC-SEC-001", "SPEC-VER-001",
]


class TestRemovedSpecsGone:
    """14 dead spec dirs must not exist."""

    @pytest.mark.parametrize("spec_id", DEAD_SPECS)
    def test_dead_spec_dir_removed(self, spec_id):
        spec_dir = SPEC_PACKS / spec_id
        assert not spec_dir.exists(), f"{spec_id} is dead — dir must be deleted"


class TestGovernanceHealth:
    """After strip, exact counts must match target state."""

    def test_exactly_11_specs(self):
        spec_dirs = sorted(d.name for d in SPEC_PACKS.iterdir() if d.is_dir() and d.name.startswith("SPEC-"))
        assert spec_dirs == sorted(SURVIVING_SPECS), \
            f"Expected 11 specs {sorted(SURVIVING_SPECS)}, got {spec_dirs}"

    def test_exactly_4_frameworks(self):
        fmwk_dirs = sorted(d.name.split("_")[0] for d in HOT_ROOT.iterdir()
                           if d.is_dir() and d.name.startswith("FMWK-"))
        assert fmwk_dirs == ["FMWK-000", "FMWK-001", "FMWK-002", "FMWK-007"], \
            f"Expected 4 frameworks, got {fmwk_dirs}"

    def test_exactly_8_schemas(self):
        schemas = sorted(f.name for f in (HOT_ROOT / "schemas").glob("*.json"))
        expected = sorted([
            "attention_envelope.json", "framework.schema.json",
            "package_manifest.json", "package_manifest_l0.json",
            "spec.schema.json", "stdlib_llm_request.json",
            "stdlib_llm_response.json", "work_order.schema.json",
        ])
        assert schemas == expected, f"Expected 8 schemas {expected}, got {schemas}"


class TestSpecAssetPaths:
    """No surviving spec should reference HO3/tests/ in its assets."""

    @pytest.fixture(params=[SPEC_PACKS / s / "manifest.yaml" for s in SURVIVING_SPECS])
    def spec_data(self, request):
        if not request.param.exists():
            pytest.skip(f"{request.param} not found yet")
        return _parse_yaml_simple(request.param), request.param

    def test_no_ho3_test_paths(self, spec_data):
        data, path = spec_data
        assets = data.get("assets", [])
        ho3_tests = [a for a in assets if a.startswith("HO3/tests/")]
        assert not ho3_tests, \
            f"{path.parent.name}: still references HO3/tests/ paths: {ho3_tests}"


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
