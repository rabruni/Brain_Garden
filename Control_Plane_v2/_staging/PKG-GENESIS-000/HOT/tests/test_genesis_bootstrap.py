"""TDD tests for PKG-GENESIS-000 — The Seed.

RED: These tests MUST FAIL before implementation.
GREEN: Create seed_registry.json, bootstrap_sequence.json, package_manifest_l0.json.

Tests verify:
- Layer 0 schema rejects governance concepts (framework_id, plane_id, ring)
- Layer 0 schema accepts minimal valid manifest
- Seed registry has valid structure
- Bootstrap sequence has valid structure
- genesis_bootstrap.py can parse the seed registry
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
HOT_ROOT = SCRIPT_DIR.parent
CP_ROOT = HOT_ROOT.parent
sys.path.insert(0, str(HOT_ROOT))


# === Layer 0 Schema Tests ===

class TestLayer0Schema:
    """Layer 0 schema defines axioms: file, package, hash, version only."""

    SCHEMA_PATH = HOT_ROOT / "schemas" / "package_manifest_l0.json"

    def test_l0_schema_file_exists(self):
        """Layer 0 schema must exist."""
        assert self.SCHEMA_PATH.exists(), "package_manifest_l0.json not found"

    def test_l0_schema_is_valid_json(self):
        """Schema must be parseable JSON."""
        data = json.loads(self.SCHEMA_PATH.read_text())
        assert data["type"] == "object"

    def test_l0_schema_requires_package_id(self):
        """Schema must require package_id."""
        data = json.loads(self.SCHEMA_PATH.read_text())
        assert "package_id" in data["required"]

    def test_l0_schema_requires_version(self):
        """Schema must require version."""
        data = json.loads(self.SCHEMA_PATH.read_text())
        assert "version" in data["required"]

    def test_l0_schema_requires_assets(self):
        """Schema must require assets."""
        data = json.loads(self.SCHEMA_PATH.read_text())
        assert "assets" in data["required"]

    def test_l0_schema_forbids_framework_id(self):
        """Layer 0 MUST NOT allow framework_id (Layer 1 concept)."""
        data = json.loads(self.SCHEMA_PATH.read_text())
        assert "framework_id" not in data.get("properties", {}), \
            "Layer 0 schema must NOT include framework_id"

    def test_l0_schema_forbids_plane_id(self):
        """Layer 0 MUST NOT allow plane_id (Layer 1 concept)."""
        data = json.loads(self.SCHEMA_PATH.read_text())
        assert "plane_id" not in data.get("properties", {}), \
            "Layer 0 schema must NOT include plane_id"

    def test_l0_schema_forbids_spec_id(self):
        """Layer 0 MUST NOT allow spec_id (Layer 1 concept)."""
        data = json.loads(self.SCHEMA_PATH.read_text())
        assert "spec_id" not in data.get("properties", {}), \
            "Layer 0 schema must NOT include spec_id"

    def test_l0_schema_forbids_ring(self):
        """Layer 0 MUST NOT allow ring (Layer 1 concept)."""
        data = json.loads(self.SCHEMA_PATH.read_text())
        assert "ring" not in data.get("properties", {}), \
            "Layer 0 schema must NOT include ring"

    def test_l0_schema_forbids_additional_properties(self):
        """Layer 0 must be strict — no extra fields."""
        data = json.loads(self.SCHEMA_PATH.read_text())
        assert data.get("additionalProperties") is False

    def test_l0_schema_has_schema_layer_field(self):
        """Schema must declare schema_layer: 0."""
        data = json.loads(self.SCHEMA_PATH.read_text())
        props = data.get("properties", {})
        assert "schema_layer" in props
        assert props["schema_layer"].get("const") == 0


# === Seed Registry Tests ===

class TestSeedRegistry:
    """Seed registry lists packages available for cold-boot installation."""

    SEED_PATH = HOT_ROOT / "config" / "seed_registry.json"

    def test_seed_registry_exists(self):
        """Seed registry must exist."""
        assert self.SEED_PATH.exists(), "seed_registry.json not found"

    def test_seed_registry_is_valid_json(self):
        """Seed registry must be parseable JSON."""
        data = json.loads(self.SEED_PATH.read_text())
        assert isinstance(data, dict)

    def test_seed_registry_has_schema_version(self):
        """Must declare schema_version."""
        data = json.loads(self.SEED_PATH.read_text())
        assert data.get("schema_version") == "1.0"

    def test_seed_registry_has_packages_array(self):
        """Must have a packages array."""
        data = json.loads(self.SEED_PATH.read_text())
        assert isinstance(data.get("packages"), list)
        assert len(data["packages"]) >= 1, "Must list at least 1 package"

    def test_seed_registry_packages_have_required_fields(self):
        """Each package entry must have id, version, digest."""
        data = json.loads(self.SEED_PATH.read_text())
        for pkg in data["packages"]:
            assert "id" in pkg, f"Package missing id: {pkg}"
            assert "version" in pkg, f"Package missing version: {pkg}"
            assert "digest" in pkg, f"Package missing digest: {pkg}"

    def test_seed_registry_includes_kernel_package(self):
        """Seed must include PKG-KERNEL-001 (first package to install)."""
        data = json.loads(self.SEED_PATH.read_text())
        ids = [p["id"] for p in data["packages"]]
        assert "PKG-KERNEL-001" in ids

    def test_genesis_bootstrap_can_parse_seed(self):
        """genesis_bootstrap.py must be able to load the seed registry."""
        result = subprocess.run(
            [sys.executable, str(HOT_ROOT / "scripts" / "genesis_bootstrap.py"),
             "--seed", str(self.SEED_PATH),
             "--archive", "/dev/null",
             "--id", "PKG-NONEXISTENT"],
            cwd=str(CP_ROOT),
            capture_output=True, text=True,
        )
        # Should fail because package not found, NOT because of parse error
        assert "ERROR: Invalid seed registry" not in result.stderr + result.stdout


# === Bootstrap Sequence Tests ===

class TestBootstrapSequence:
    """Bootstrap sequence defines the canonical package install order."""

    SEQ_PATH = HOT_ROOT / "config" / "bootstrap_sequence.json"

    def test_bootstrap_sequence_exists(self):
        """Bootstrap sequence must exist."""
        assert self.SEQ_PATH.exists(), "bootstrap_sequence.json not found"

    def test_bootstrap_sequence_is_valid_json(self):
        """Must be parseable JSON."""
        data = json.loads(self.SEQ_PATH.read_text())
        assert isinstance(data, dict)

    def test_bootstrap_sequence_has_layers(self):
        """Must have a layers array."""
        data = json.loads(self.SEQ_PATH.read_text())
        assert isinstance(data.get("layers"), list)
        assert len(data["layers"]) >= 3, "Must have at least 3 layers"

    def test_layer_0_comes_first(self):
        """First layer must be layer 0 (axioms)."""
        data = json.loads(self.SEQ_PATH.read_text())
        assert data["layers"][0]["layer"] == 0

    def test_layers_are_non_decreasing(self):
        """Layer numbers must be non-decreasing (0, 0, 1, 2, 2, 2)."""
        data = json.loads(self.SEQ_PATH.read_text())
        layers = [entry["layer"] for entry in data["layers"]]
        for i in range(1, len(layers)):
            assert layers[i] >= layers[i - 1], \
                f"Layer {layers[i]} at index {i} is less than {layers[i - 1]} at index {i - 1}"

    def test_each_layer_has_required_fields(self):
        """Each layer entry must have layer, name, packages, installer."""
        data = json.loads(self.SEQ_PATH.read_text())
        for entry in data["layers"]:
            assert "layer" in entry, f"Missing 'layer' in {entry.get('name', '?')}"
            assert "name" in entry, "Missing 'name' in entry"
            assert "packages" in entry, f"Missing 'packages' in {entry['name']}"
            assert "installer" in entry, f"Missing 'installer' in {entry['name']}"

    def test_layer_0_uses_genesis_bootstrap(self):
        """Layer 0 must use genesis_bootstrap.py as installer."""
        data = json.loads(self.SEQ_PATH.read_text())
        layer_0_entries = [e for e in data["layers"] if e["layer"] == 0]
        assert any(e["installer"] == "genesis_bootstrap.py" for e in layer_0_entries)

    def test_vocabulary_introduced_field_exists(self):
        """Each layer should declare vocabulary_introduced."""
        data = json.loads(self.SEQ_PATH.read_text())
        for entry in data["layers"]:
            assert "vocabulary_introduced" in entry, \
                f"Missing vocabulary_introduced in {entry['name']}"

    def test_layer_0_introduces_axiom_vocabulary(self):
        """Layer 0 must introduce file/package/hash/ledger vocabulary."""
        data = json.loads(self.SEQ_PATH.read_text())
        layer_0 = [e for e in data["layers"]
                    if e["layer"] == 0 and e.get("vocabulary_introduced")]
        assert len(layer_0) >= 1
        vocab = layer_0[0]["vocabulary_introduced"]
        for axiom in ["file", "package", "hash", "ledger"]:
            assert axiom in vocab, f"Layer 0 must introduce '{axiom}'"
