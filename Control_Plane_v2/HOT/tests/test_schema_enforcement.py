"""TDD tests for PKG-VOCABULARY-001 — Schema Enforcement.

RED: These tests MUST FAIL before implementation.
GREEN: Add validate_framework() and validate_spec() to schema_validator.py.
       Update framework.schema.json and spec.schema.json.

Tests verify:
- validate_framework() accepts valid framework manifests
- validate_framework() rejects invalid ones
- validate_spec() accepts valid spec manifests
- validate_spec() rejects invalid ones
- Updated schemas allow ring, expected_specs, plane_id
"""
import json
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
HOT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(HOT_ROOT))


# === Framework Validation Tests ===

class TestValidateFramework:
    """Test validate_framework() from schema_validator.py."""

    def test_function_exists(self):
        """validate_framework must be importable."""
        from kernel.schema_validator import validate_framework
        assert callable(validate_framework)

    def test_accepts_valid_minimal_framework(self):
        """Minimal valid framework manifest should pass."""
        from kernel.schema_validator import validate_framework
        valid, errors = validate_framework({
            "framework_id": "FMWK-000",
            "title": "Test Framework",
            "status": "active",
            "version": "1.0.0",
        })
        assert valid, f"Should accept valid framework: {errors}"

    def test_accepts_full_framework(self):
        """Full framework manifest with all fields should pass."""
        from kernel.schema_validator import validate_framework
        valid, errors = validate_framework({
            "framework_id": "FMWK-000",
            "title": "Test Framework",
            "status": "active",
            "version": "1.0.0",
            "ring": "kernel",
            "plane_id": "hot",
            "expected_specs": ["SPEC-CORE-001", "SPEC-INT-001"],
            "assets": ["governance_framework.md"],
            "created_at": "2026-02-01T00:00:00Z",
        })
        assert valid, f"Should accept full framework: {errors}"

    def test_rejects_missing_framework_id(self):
        """Framework without framework_id must fail."""
        from kernel.schema_validator import validate_framework
        valid, errors = validate_framework({
            "title": "No ID", "status": "active", "version": "1.0.0",
        })
        assert not valid
        assert any("framework_id" in e for e in errors)

    def test_rejects_invalid_framework_id_pattern(self):
        """Framework ID must match FMWK-[A-Z0-9-]+."""
        from kernel.schema_validator import validate_framework
        valid, errors = validate_framework({
            "framework_id": "INVALID-000",
            "title": "Bad ID", "status": "active", "version": "1.0.0",
        })
        assert not valid
        assert any("framework_id" in e.lower() or "pattern" in e.lower() for e in errors)

    def test_rejects_invalid_status(self):
        """Status must be active/draft/deprecated."""
        from kernel.schema_validator import validate_framework
        valid, errors = validate_framework({
            "framework_id": "FMWK-TEST",
            "title": "Bad Status", "status": "deleted", "version": "1.0.0",
        })
        assert not valid
        assert any("status" in e for e in errors)

    def test_validates_ring_values(self):
        """Ring must be kernel/admin/resident if present."""
        from kernel.schema_validator import validate_framework
        valid, errors = validate_framework({
            "framework_id": "FMWK-TEST",
            "title": "Bad Ring", "status": "active", "version": "1.0.0",
            "ring": "invalid_ring",
        })
        assert not valid
        assert any("ring" in e for e in errors)

    def test_validates_expected_specs_format(self):
        """expected_specs must be list of SPEC-* strings."""
        from kernel.schema_validator import validate_framework
        valid, errors = validate_framework({
            "framework_id": "FMWK-TEST",
            "title": "Bad Specs", "status": "active", "version": "1.0.0",
            "expected_specs": ["NOT-A-SPEC"],
        })
        assert not valid
        assert any("expected_specs" in e or "SPEC-" in e for e in errors)

    def test_validates_plane_id_values(self):
        """plane_id must be hot/ho3/ho2/ho1 if present."""
        from kernel.schema_validator import validate_framework
        valid, errors = validate_framework({
            "framework_id": "FMWK-TEST",
            "title": "Bad Plane", "status": "active", "version": "1.0.0",
            "plane_id": "invalid_plane",
        })
        assert not valid
        assert any("plane" in e.lower() for e in errors)

    def test_rejects_missing_title(self):
        """Framework without title must fail."""
        from kernel.schema_validator import validate_framework
        valid, errors = validate_framework({
            "framework_id": "FMWK-TEST", "status": "active", "version": "1.0.0",
        })
        assert not valid
        assert any("title" in e for e in errors)


# === Spec Validation Tests ===

class TestValidateSpec:
    """Test validate_spec() from schema_validator.py."""

    def test_function_exists(self):
        """validate_spec must be importable."""
        from kernel.schema_validator import validate_spec
        assert callable(validate_spec)

    def test_accepts_valid_spec(self):
        """Valid spec manifest should pass."""
        from kernel.schema_validator import validate_spec
        valid, errors = validate_spec({
            "spec_id": "SPEC-CORE-001",
            "title": "Core Infrastructure",
            "framework_id": "FMWK-000",
            "status": "active",
            "version": "1.0.0",
            "assets": ["HOT/kernel/paths.py"],
        })
        assert valid, f"Should accept valid spec: {errors}"

    def test_rejects_missing_spec_id(self):
        """Spec without spec_id must fail."""
        from kernel.schema_validator import validate_spec
        valid, errors = validate_spec({
            "title": "No ID", "framework_id": "FMWK-000",
            "status": "active", "version": "1.0.0", "assets": ["file.py"],
        })
        assert not valid
        assert any("spec_id" in e for e in errors)

    def test_rejects_invalid_spec_id_pattern(self):
        """Spec ID must match SPEC-[A-Z0-9-]+."""
        from kernel.schema_validator import validate_spec
        valid, errors = validate_spec({
            "spec_id": "INVALID-001",
            "title": "Bad", "framework_id": "FMWK-000",
            "status": "active", "version": "1.0.0", "assets": ["file.py"],
        })
        assert not valid

    def test_rejects_missing_framework_id(self):
        """Spec without framework_id must fail."""
        from kernel.schema_validator import validate_spec
        valid, errors = validate_spec({
            "spec_id": "SPEC-TEST", "title": "No Framework",
            "status": "active", "version": "1.0.0", "assets": ["file.py"],
        })
        assert not valid
        assert any("framework_id" in e for e in errors)

    def test_rejects_empty_assets(self):
        """Spec with empty assets must fail."""
        from kernel.schema_validator import validate_spec
        valid, errors = validate_spec({
            "spec_id": "SPEC-TEST", "title": "Empty",
            "framework_id": "FMWK-000",
            "status": "active", "version": "1.0.0", "assets": [],
        })
        assert not valid
        assert any("assets" in e for e in errors)

    def test_accepts_spec_with_plane_id(self):
        """Spec with plane_id should pass."""
        from kernel.schema_validator import validate_spec
        valid, errors = validate_spec({
            "spec_id": "SPEC-TEST", "title": "With Plane",
            "framework_id": "FMWK-000", "plane_id": "ho3",
            "status": "active", "version": "1.0.0", "assets": ["file.py"],
        })
        assert valid, f"Should accept spec with plane_id: {errors}"

    def test_rejects_invalid_status(self):
        """Status must be active/draft/deprecated."""
        from kernel.schema_validator import validate_spec
        valid, errors = validate_spec({
            "spec_id": "SPEC-TEST", "title": "Bad Status",
            "framework_id": "FMWK-000",
            "status": "removed", "version": "1.0.0", "assets": ["file.py"],
        })
        assert not valid


# === Schema File Tests ===

class TestFrameworkSchemaFile:
    """Test that framework.schema.json allows new fields."""

    SCHEMA_PATH = HOT_ROOT / "schemas" / "framework.schema.json"

    def test_schema_allows_ring(self):
        """framework.schema.json must define 'ring' property."""
        data = json.loads(self.SCHEMA_PATH.read_text())
        assert "ring" in data["properties"], "Schema missing 'ring' property"

    def test_schema_allows_expected_specs(self):
        """framework.schema.json must define 'expected_specs' property."""
        data = json.loads(self.SCHEMA_PATH.read_text())
        assert "expected_specs" in data["properties"], "Schema missing 'expected_specs'"

    def test_schema_allows_plane_id(self):
        """framework.schema.json must define 'plane_id' property."""
        data = json.loads(self.SCHEMA_PATH.read_text())
        assert "plane_id" in data["properties"], "Schema missing 'plane_id'"

    def test_schema_allows_created_at(self):
        """framework.schema.json must define 'created_at' property."""
        data = json.loads(self.SCHEMA_PATH.read_text())
        assert "created_at" in data["properties"], "Schema missing 'created_at'"

    def test_ring_enum_values(self):
        """ring must be kernel/admin/resident."""
        data = json.loads(self.SCHEMA_PATH.read_text())
        ring = data["properties"]["ring"]
        assert set(ring["enum"]) == {"kernel", "admin", "resident"}


class TestSpecSchemaFile:
    """Test that spec.schema.json allows new fields."""

    SCHEMA_PATH = HOT_ROOT / "schemas" / "spec.schema.json"

    def test_schema_allows_plane_id(self):
        """spec.schema.json must define 'plane_id' property."""
        data = json.loads(self.SCHEMA_PATH.read_text())
        assert "plane_id" in data["properties"], "Schema missing 'plane_id'"
