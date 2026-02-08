#!/usr/bin/env python3
"""
test_manifest_v11.py - Tests for manifest v1.1 with plane-aware fields.

Tests:
- target_plane field validation
- external_interfaces field validation
- scope field validation
- Integration with plane context
"""
import json
import sys
import tempfile
from pathlib import Path

import pytest

# Add repo root for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "HOT"))

from kernel.plane import (
    PlaneContext,
    PlaneType,
    validate_target_plane,
    validate_external_interface_direction,
)


class TestManifestV11Fields:
    """Tests for manifest v1.1 new fields."""

    def create_manifest(self, **kwargs):
        """Create a manifest with defaults."""
        manifest = {
            "schema_version": "1.1",
            "id": "PKG-T0-001",
            "name": "Test Package",
            "version": "1.0.0",
            "tier": "T0",
            "artifact_paths": ["lib/test.py"],
            "deps": [],
            "target_plane": "any",
            "scope": "local_only",
            "external_interfaces": [],
        }
        manifest.update(kwargs)
        return manifest

    def test_valid_manifest_v11(self, tmp_path):
        """Test valid v1.1 manifest structure."""
        manifest = self.create_manifest()

        assert manifest["schema_version"] == "1.1"
        assert manifest["target_plane"] == "any"
        assert manifest["scope"] == "local_only"
        assert manifest["external_interfaces"] == []

    def test_target_plane_hot(self, tmp_path):
        """Test manifest targeting HOT plane."""
        manifest = self.create_manifest(target_plane="hot")

        hot_plane = PlaneContext(
            name="hot",
            plane_type=PlaneType.HOT,
            root=tmp_path / "hot",
        )
        first_plane = PlaneContext(
            name="first",
            plane_type=PlaneType.FIRST_ORDER,
            root=tmp_path / "first",
        )

        # Should validate on HOT plane
        assert validate_target_plane(manifest["target_plane"], hot_plane) is True
        # Should NOT validate on FIRST plane
        assert validate_target_plane(manifest["target_plane"], first_plane) is False

    def test_target_plane_any(self, tmp_path):
        """Test manifest with target_plane='any'."""
        manifest = self.create_manifest(target_plane="any")

        for plane_type in [PlaneType.HOT, PlaneType.FIRST_ORDER, PlaneType.SECOND_ORDER]:
            plane = PlaneContext(
                name=plane_type.value.lower().replace("_order", ""),
                plane_type=plane_type,
                root=tmp_path,
            )
            assert validate_target_plane(manifest["target_plane"], plane) is True

    def test_external_interfaces_valid_direction(self, tmp_path):
        """Test valid external interface direction."""
        manifest = self.create_manifest(
            external_interfaces=[
                {
                    "name": "cp_status_contract",
                    "version": "1.0",
                    "source_plane": "second",
                }
            ]
        )

        # FIRST_ORDER can reference SECOND_ORDER interfaces
        first_plane = PlaneContext(
            name="first",
            plane_type=PlaneType.FIRST_ORDER,
            root=tmp_path,
        )

        for iface in manifest["external_interfaces"]:
            assert validate_external_interface_direction(
                first_plane, iface["source_plane"]
            ) is True

    def test_external_interfaces_invalid_direction(self, tmp_path):
        """Test invalid external interface direction."""
        manifest = self.create_manifest(
            external_interfaces=[
                {
                    "name": "hot_policy_contract",
                    "version": "1.0",
                    "source_plane": "hot",  # SECOND cannot reference HOT
                }
            ]
        )

        second_plane = PlaneContext(
            name="second",
            plane_type=PlaneType.SECOND_ORDER,
            root=tmp_path,
        )

        for iface in manifest["external_interfaces"]:
            assert validate_external_interface_direction(
                second_plane, iface["source_plane"]
            ) is False

    def test_external_interfaces_multiple(self, tmp_path):
        """Test multiple external interfaces."""
        manifest = self.create_manifest(
            external_interfaces=[
                {
                    "name": "first_contract",
                    "version": "1.0",
                    "source_plane": "first",
                },
                {
                    "name": "second_contract",
                    "version": "1.0",
                    "source_plane": "second",
                },
            ]
        )

        # HOT can reference both FIRST and SECOND
        hot_plane = PlaneContext(
            name="hot",
            plane_type=PlaneType.HOT,
            root=tmp_path,
        )

        for iface in manifest["external_interfaces"]:
            assert validate_external_interface_direction(
                hot_plane, iface["source_plane"]
            ) is True

    def test_scope_local_only(self, tmp_path):
        """Test scope='local_only' field."""
        manifest = self.create_manifest(
            scope="local_only",
            deps=["PKG-G0-001"],  # Local dependency
        )

        assert manifest["scope"] == "local_only"
        # With local_only scope, deps should be within same plane
        # (actual enforcement would be in validate_tier_deps.py)

    def test_schema_version_compatibility(self, tmp_path):
        """Test that v1.0 manifests work without new fields."""
        manifest_v10 = {
            "schema_version": "1.0",
            "id": "PKG-T0-001",
            "name": "Test Package",
            "version": "1.0.0",
            "tier": "T0",
            "artifact_paths": ["lib/test.py"],
            "deps": [],
        }

        # v1.0 manifest should work - missing fields default to safe values
        target_plane = manifest_v10.get("target_plane", "any")
        external_interfaces = manifest_v10.get("external_interfaces", [])

        assert target_plane == "any"  # Default
        assert external_interfaces == []  # Default


class TestManifestTargetPlaneMismatch:
    """Tests for target_plane mismatch scenarios."""

    def test_install_refuses_cross_plane(self, tmp_path):
        """Test that installation is blocked on plane mismatch."""
        manifest = {
            "schema_version": "1.1",
            "id": "PKG-T0-001",
            "target_plane": "hot",  # Targets HOT
        }

        # Try to install on FIRST plane
        first_plane = PlaneContext(
            name="first",
            plane_type=PlaneType.FIRST_ORDER,
            root=tmp_path,
        )

        # This should fail
        assert validate_target_plane(manifest["target_plane"], first_plane) is False

    def test_install_succeeds_matching_plane(self, tmp_path):
        """Test that installation succeeds on matching plane."""
        manifest = {
            "schema_version": "1.1",
            "id": "PKG-T0-001",
            "target_plane": "first",
        }

        first_plane = PlaneContext(
            name="first",
            plane_type=PlaneType.FIRST_ORDER,
            root=tmp_path,
        )

        assert validate_target_plane(manifest["target_plane"], first_plane) is True


class TestExternalInterfaceDirectionRules:
    """Tests for external interface direction enforcement."""

    def test_validate_tier_deps_rejects_illegal_direction(self, tmp_path):
        """Test that illegal interface directions are rejected."""
        # SECOND_ORDER trying to reference HOT interface
        second_plane = PlaneContext(
            name="second",
            plane_type=PlaneType.SECOND_ORDER,
            root=tmp_path,
        )

        # SECOND cannot reference HOT
        assert validate_external_interface_direction(second_plane, "hot") is False

        # SECOND cannot reference FIRST
        assert validate_external_interface_direction(second_plane, "first") is False

    def test_direction_matrix(self, tmp_path):
        """Test complete direction matrix."""
        # Create all plane contexts
        hot = PlaneContext(name="hot", plane_type=PlaneType.HOT, root=tmp_path / "hot")
        first = PlaneContext(name="first", plane_type=PlaneType.FIRST_ORDER, root=tmp_path / "first")
        second = PlaneContext(name="second", plane_type=PlaneType.SECOND_ORDER, root=tmp_path / "second")

        # HOT -> FIRST: OK
        assert validate_external_interface_direction(hot, "first") is True
        # HOT -> SECOND: OK
        assert validate_external_interface_direction(hot, "second") is True

        # FIRST -> HOT: FAIL
        assert validate_external_interface_direction(first, "hot") is False
        # FIRST -> SECOND: OK
        assert validate_external_interface_direction(first, "second") is True

        # SECOND -> HOT: FAIL
        assert validate_external_interface_direction(second, "hot") is False
        # SECOND -> FIRST: FAIL
        assert validate_external_interface_direction(second, "first") is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
