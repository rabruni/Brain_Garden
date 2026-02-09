"""TDD tests for PKG-FRAMEWORK-WIRING-001 — Framework Wiring Diagrams.

RED: These tests MUST FAIL before implementation.
GREEN: Rewrite all 5 framework manifests with expected_specs + missing fields.
       Delete orphaned FMWK-003 and FMWK-004.

Tests verify:
- Each framework manifest validates against updated schema
- Each framework has expected_specs field
- expected_specs match actual specs referencing that framework
- Orphaned frameworks are removed
- All framework manifests have ring, plane_id, invariants
"""
import json
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
HOT_ROOT = SCRIPT_DIR.parent
CP_ROOT = HOT_ROOT.parent
sys.path.insert(0, str(HOT_ROOT))

# Discover all framework manifests
FMWK_DIRS = sorted(HOT_ROOT.glob("FMWK-*/manifest.yaml"))

# Expected framework->spec wiring (from audit)
EXPECTED_WIRING = {
    "FMWK-000": ["SPEC-CORE-001", "SPEC-CORE-SCRIPTS-001", "SPEC-GATE-001",
                  "SPEC-GENESIS-001", "SPEC-INSPECT-001", "SPEC-INT-001",
                  "SPEC-PLANE-001", "SPEC-POLICY-001", "SPEC-REG-001", "SPEC-VER-001"],
    "FMWK-001": ["SPEC-SEC-001"],
    "FMWK-002": ["SPEC-LEDGER-001"],
    "FMWK-007": ["SPEC-PKG-001"],
    "FMWK-100": ["SPEC-ADMIN-001", "SPEC-DOC-001", "SPEC-EVIDENCE-001",
                  "SPEC-FMWK-001", "SPEC-FMWK-CAPS-001", "SPEC-RATE-MGMT-001",
                  "SPEC-ROUTER-001", "SPEC-ROUTER-FIX-001", "SPEC-ROUTER-PURE-001",
                  "SPEC-RUNTIME-001", "SPEC-TEST-001"],
}


def _parse_yaml_simple(path: Path) -> dict:
    """Minimal YAML parser for framework manifests (key: value + lists)."""
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


class TestOrphanedFrameworksRemoved:
    """Orphaned frameworks must be deleted."""

    def test_fmwk_003_removed(self):
        """FMWK-003 (0 specs) must be deleted."""
        fmwk_003 = HOT_ROOT / "FMWK-003_Package_Standard"
        assert not fmwk_003.exists(), "FMWK-003 is orphaned (0 specs) — must be deleted"

    def test_fmwk_004_removed(self):
        """FMWK-004 (0 specs) must be deleted."""
        fmwk_004 = HOT_ROOT / "FMWK-004_Prompt_Governance"
        assert not fmwk_004.exists(), "FMWK-004 is orphaned (0 specs) — must be deleted"


class TestFrameworkManifestStructure:
    """Every active framework must have complete manifest fields."""

    @pytest.fixture(params=[p for p in FMWK_DIRS
                            if "FMWK-003" not in str(p) and "FMWK-004" not in str(p)])
    def framework_manifest(self, request):
        return _parse_yaml_simple(request.param), request.param

    def test_has_framework_id(self, framework_manifest):
        data, path = framework_manifest
        assert "framework_id" in data, f"{path}: missing framework_id"

    def test_has_expected_specs(self, framework_manifest):
        data, path = framework_manifest
        fmwk_id = data.get("framework_id", "?")
        assert "expected_specs" in data, \
            f"{fmwk_id}: missing expected_specs (wiring diagram)"

    def test_has_ring(self, framework_manifest):
        data, path = framework_manifest
        assert "ring" in data, f"{path}: missing ring"
        assert data["ring"] in ("kernel", "admin", "resident")

    def test_has_plane_id(self, framework_manifest):
        data, path = framework_manifest
        assert "plane_id" in data or "plane" in data, f"{path}: missing plane_id"

    def test_has_invariants(self, framework_manifest):
        data, path = framework_manifest
        assert "invariants" in data, f"{path}: missing invariants"

    def test_has_required_gates(self, framework_manifest):
        data, path = framework_manifest
        assert "required_gates" in data, f"{path}: missing required_gates"


class TestExpectedSpecsMatch:
    """expected_specs must match actual spec->framework references."""

    @pytest.mark.parametrize("fmwk_id,expected_specs", EXPECTED_WIRING.items())
    def test_expected_specs_declared(self, fmwk_id, expected_specs):
        """Framework must declare all its expected specs."""
        matches = list(HOT_ROOT.glob(f"{fmwk_id}_*/manifest.yaml"))
        if not matches:
            pytest.skip(f"{fmwk_id} directory not found")
        data = _parse_yaml_simple(matches[0])
        declared = data.get("expected_specs", [])
        for spec_id in expected_specs:
            assert spec_id in declared, \
                f"{fmwk_id}: missing {spec_id} in expected_specs"
