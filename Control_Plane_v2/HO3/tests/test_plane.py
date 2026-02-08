#!/usr/bin/env python3
"""
test_plane.py - Tests for plane context and chain configuration.

Tests:
- PlaneContext creation and methods
- Chain config loading
- Plane resolution from root/CWD
- Target plane validation
- External interface direction rules
"""
import json
import os
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
    PlaneError,
    PlaneNotFoundError,
    PlaneTargetMismatch,
    CrossPlaneViolation,
    PLANE_ORDER,
    load_chain_config,
    clear_chain_config_cache,
    get_current_plane,
    get_plane_by_name,
    validate_target_plane,
    validate_external_interface_direction,
    get_all_plane_names,
)


class TestPlaneContext:
    """Tests for PlaneContext dataclass."""

    def test_create_plane_context(self, tmp_path):
        """Test creating a PlaneContext."""
        plane = PlaneContext(
            name="test",
            plane_type=PlaneType.FIRST_ORDER,
            root=tmp_path,
        )

        assert plane.name == "test"
        assert plane.plane_type == PlaneType.FIRST_ORDER
        assert plane.root == tmp_path
        assert plane.receipts_dir == tmp_path / "installed"
        assert plane.ledger_dir == tmp_path / "ledger"

    def test_is_path_inside(self, tmp_path):
        """Test is_path_inside method."""
        plane = PlaneContext(
            name="test",
            plane_type=PlaneType.FIRST_ORDER,
            root=tmp_path,
        )

        inside = tmp_path / "packages" / "test.json"
        outside = Path("/some/other/path")

        assert plane.is_path_inside(inside) is True
        assert plane.is_path_inside(outside) is False

    def test_can_reference_plane_hot(self, tmp_path):
        """Test that HOT can reference FIRST and SECOND."""
        hot = PlaneContext(
            name="hot",
            plane_type=PlaneType.HOT,
            root=tmp_path / "hot",
        )

        # HOT can reference lower privilege planes
        assert hot.can_reference_plane(PlaneType.FIRST_ORDER) is True
        assert hot.can_reference_plane(PlaneType.SECOND_ORDER) is True
        # HOT cannot reference itself
        assert hot.can_reference_plane(PlaneType.HOT) is False

    def test_can_reference_plane_first(self, tmp_path):
        """Test that FIRST can only reference SECOND."""
        first = PlaneContext(
            name="first",
            plane_type=PlaneType.FIRST_ORDER,
            root=tmp_path / "first",
        )

        # FIRST can only reference SECOND
        assert first.can_reference_plane(PlaneType.SECOND_ORDER) is True
        # FIRST cannot reference HOT or itself
        assert first.can_reference_plane(PlaneType.HOT) is False
        assert first.can_reference_plane(PlaneType.FIRST_ORDER) is False

    def test_can_reference_plane_second(self, tmp_path):
        """Test that SECOND cannot reference any other plane."""
        second = PlaneContext(
            name="second",
            plane_type=PlaneType.SECOND_ORDER,
            root=tmp_path / "second",
        )

        # SECOND cannot reference any plane
        assert second.can_reference_plane(PlaneType.HOT) is False
        assert second.can_reference_plane(PlaneType.FIRST_ORDER) is False
        assert second.can_reference_plane(PlaneType.SECOND_ORDER) is False

    def test_to_dict(self, tmp_path):
        """Test PlaneContext serialization."""
        plane = PlaneContext(
            name="test",
            plane_type=PlaneType.FIRST_ORDER,
            root=tmp_path,
        )

        d = plane.to_dict()
        assert d["name"] == "test"
        # FIRST_ORDER maps to HO2 in canonical naming
        assert d["type"] == "HO2"
        assert d["root"] == str(tmp_path)


class TestChainConfig:
    """Tests for chain configuration loading."""

    def test_load_default_config(self, tmp_path, monkeypatch):
        """Test loading default single-plane config when no file exists."""
        # Point to non-existent config
        monkeypatch.setenv("CONTROL_PLANE_CHAIN_CONFIG", str(tmp_path / "nonexistent.json"))
        clear_chain_config_cache()

        planes = load_chain_config()
        assert len(planes) == 1
        assert planes[0].name == "default"

    def test_load_custom_config(self, tmp_path, monkeypatch):
        """Test loading custom chain configuration."""
        config_path = tmp_path / "chain.json"
        config = {
            "planes": [
                {"name": "hot", "type": "HOT", "root": str(tmp_path / "hot")},
                {"name": "first", "type": "FIRST_ORDER", "root": str(tmp_path / "first")},
            ]
        }
        config_path.write_text(json.dumps(config))

        monkeypatch.setenv("CONTROL_PLANE_CHAIN_CONFIG", str(config_path))
        clear_chain_config_cache()

        planes = load_chain_config()
        assert len(planes) == 2
        assert planes[0].name == "hot"
        assert planes[0].plane_type == PlaneType.HOT
        assert planes[1].name == "first"

    def test_invalid_config_missing_name(self, tmp_path, monkeypatch):
        """Test error on invalid config (missing name)."""
        config_path = tmp_path / "chain.json"
        config = {
            "planes": [
                {"type": "HOT", "root": str(tmp_path / "hot")},
            ]
        }
        config_path.write_text(json.dumps(config))

        monkeypatch.setenv("CONTROL_PLANE_CHAIN_CONFIG", str(config_path))
        clear_chain_config_cache()

        with pytest.raises(PlaneError, match="missing 'name'"):
            load_chain_config()


class TestPlaneResolution:
    """Tests for plane resolution."""

    def test_get_current_plane_with_root(self, tmp_path, monkeypatch):
        """Test resolving plane from explicit root."""
        config_path = tmp_path / "chain.json"
        hot_root = tmp_path / "hot"
        hot_root.mkdir()

        config = {
            "planes": [
                {"name": "hot", "type": "HOT", "root": str(hot_root)},
            ]
        }
        config_path.write_text(json.dumps(config))

        monkeypatch.setenv("CONTROL_PLANE_CHAIN_CONFIG", str(config_path))
        clear_chain_config_cache()

        plane = get_current_plane(hot_root)
        assert plane.name == "hot"
        assert plane.plane_type == PlaneType.HOT

    def test_get_plane_by_name(self, tmp_path, monkeypatch):
        """Test getting plane by name."""
        config_path = tmp_path / "chain.json"
        config = {
            "planes": [
                {"name": "first", "type": "FIRST_ORDER", "root": str(tmp_path / "first")},
            ]
        }
        config_path.write_text(json.dumps(config))

        monkeypatch.setenv("CONTROL_PLANE_CHAIN_CONFIG", str(config_path))
        clear_chain_config_cache()

        plane = get_plane_by_name("first")
        assert plane.name == "first"

    def test_get_plane_by_name_not_found(self, tmp_path, monkeypatch):
        """Test error when plane name not found."""
        config_path = tmp_path / "chain.json"
        config = {
            "planes": [
                {"name": "first", "type": "FIRST_ORDER", "root": str(tmp_path / "first")},
            ]
        }
        config_path.write_text(json.dumps(config))

        monkeypatch.setenv("CONTROL_PLANE_CHAIN_CONFIG", str(config_path))
        clear_chain_config_cache()

        with pytest.raises(PlaneNotFoundError, match="No plane found"):
            get_plane_by_name("nonexistent")


class TestTargetPlaneValidation:
    """Tests for target_plane validation."""

    def test_validate_target_plane_any(self, tmp_path):
        """Test that target_plane='any' always matches."""
        plane = PlaneContext(
            name="first",
            plane_type=PlaneType.FIRST_ORDER,
            root=tmp_path,
        )

        assert validate_target_plane("any", plane) is True

    def test_validate_target_plane_match(self, tmp_path):
        """Test that matching target_plane validates."""
        plane = PlaneContext(
            name="first",
            plane_type=PlaneType.FIRST_ORDER,
            root=tmp_path,
        )

        assert validate_target_plane("first", plane) is True
        assert validate_target_plane("FIRST", plane) is True  # Case insensitive

    def test_validate_target_plane_mismatch(self, tmp_path):
        """Test that mismatched target_plane fails."""
        plane = PlaneContext(
            name="first",
            plane_type=PlaneType.FIRST_ORDER,
            root=tmp_path,
        )

        assert validate_target_plane("hot", plane) is False
        assert validate_target_plane("second", plane) is False


class TestExternalInterfaceDirection:
    """Tests for external interface direction validation."""

    def test_hot_can_reference_first_and_second(self, tmp_path):
        """Test HOT plane can reference FIRST and SECOND interfaces."""
        hot = PlaneContext(
            name="hot",
            plane_type=PlaneType.HOT,
            root=tmp_path,
        )

        assert validate_external_interface_direction(hot, "first") is True
        assert validate_external_interface_direction(hot, "second") is True

    def test_first_can_only_reference_second(self, tmp_path):
        """Test FIRST plane can only reference SECOND interfaces."""
        first = PlaneContext(
            name="first",
            plane_type=PlaneType.FIRST_ORDER,
            root=tmp_path,
        )

        assert validate_external_interface_direction(first, "second") is True
        assert validate_external_interface_direction(first, "hot") is False

    def test_second_cannot_reference_others(self, tmp_path):
        """Test SECOND plane cannot reference other plane interfaces."""
        second = PlaneContext(
            name="second",
            plane_type=PlaneType.SECOND_ORDER,
            root=tmp_path,
        )

        assert validate_external_interface_direction(second, "hot") is False
        assert validate_external_interface_direction(second, "first") is False

    def test_invalid_source_plane_fails(self, tmp_path):
        """Test that unknown source plane fails validation."""
        plane = PlaneContext(
            name="first",
            plane_type=PlaneType.FIRST_ORDER,
            root=tmp_path,
        )

        # Unknown plane should fail (fail closed)
        assert validate_external_interface_direction(plane, "unknown") is False


class TestPlaneOrder:
    """Tests for plane ordering."""

    def test_plane_order_values(self):
        """Test that plane order values are correct."""
        assert PLANE_ORDER[PlaneType.HOT] == 0
        assert PLANE_ORDER[PlaneType.FIRST_ORDER] == 1
        assert PLANE_ORDER[PlaneType.SECOND_ORDER] == 2

    def test_hot_is_highest_privilege(self):
        """Test that HOT has highest privilege (lowest order number)."""
        assert PLANE_ORDER[PlaneType.HOT] < PLANE_ORDER[PlaneType.FIRST_ORDER]
        assert PLANE_ORDER[PlaneType.HOT] < PLANE_ORDER[PlaneType.SECOND_ORDER]

    def test_second_is_lowest_privilege(self):
        """Test that SECOND has lowest privilege (highest order number)."""
        assert PLANE_ORDER[PlaneType.SECOND_ORDER] > PLANE_ORDER[PlaneType.HOT]
        assert PLANE_ORDER[PlaneType.SECOND_ORDER] > PLANE_ORDER[PlaneType.FIRST_ORDER]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
