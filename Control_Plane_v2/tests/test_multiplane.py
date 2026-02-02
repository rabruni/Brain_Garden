#!/usr/bin/env python3
"""
test_multiplane.py - Integration tests for multi-plane operation.

Tests the three-plane topology (HO3/HO2/HO1) and plane-aware operations.
"""

import json
import os
import tempfile
import pytest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.plane import (
    PlaneType,
    PlaneContext,
    load_chain_config,
    clear_chain_config_cache,
    get_current_plane,
    get_plane_by_name,
    get_plane_by_root,
    resolve_plane_type,
    validate_target_plane,
    validate_external_interface_direction,
    PLANE_ORDER,
    PLANE_NAME_MAP,
    migrate_plane_type,
    PlaneNotFoundError,
)
from lib.tier_manifest import (
    TierManifest,
    TierType,
    migrate_tier_name,
    TIER_MIGRATION,
)
from lib.ledger_factory import LedgerFactory, DEFAULT_LEDGER_NAMES
from lib.pristine import (
    classify_path,
    PathClass,
    is_inside_control_plane,
    assert_write_allowed,
    WriteViolation,
)
from lib.registry import find_all_registries


class TestCanonicalNaming:
    """Test canonical tier/plane naming (HO3/HO2/HO1)."""

    def test_plane_type_canonical_values(self):
        """PlaneType has canonical HO3/HO2/HO1 values."""
        assert PlaneType.HO3.value == "HO3"
        assert PlaneType.HO2.value == "HO2"
        assert PlaneType.HO1.value == "HO1"

    def test_plane_type_legacy_aliases(self):
        """PlaneType legacy aliases map to canonical values."""
        assert PlaneType.HOT.value == "HO3"
        assert PlaneType.FIRST_ORDER.value == "HO2"  # FIRST_ORDER was middle tier
        assert PlaneType.SECOND_ORDER.value == "HO1"  # SECOND_ORDER was lowest tier

    def test_plane_order_canonical(self):
        """PLANE_ORDER uses canonical types."""
        assert PLANE_ORDER[PlaneType.HO3] == 0
        assert PLANE_ORDER[PlaneType.HO2] == 1
        assert PLANE_ORDER[PlaneType.HO1] == 2

    def test_plane_name_map_canonical(self):
        """PLANE_NAME_MAP supports canonical and legacy names."""
        # Canonical names
        assert PLANE_NAME_MAP["ho3"] == PlaneType.HO3
        assert PLANE_NAME_MAP["ho2"] == PlaneType.HO2
        assert PLANE_NAME_MAP["ho1"] == PlaneType.HO1
        # Legacy names (first=middle=HO2, second=lowest=HO1)
        assert PLANE_NAME_MAP["hot"] == PlaneType.HO3
        assert PLANE_NAME_MAP["first"] == PlaneType.HO2
        assert PLANE_NAME_MAP["second"] == PlaneType.HO1

    def test_migrate_plane_type(self):
        """migrate_plane_type converts legacy to canonical."""
        assert migrate_plane_type("HOT") == "HO3"
        assert migrate_plane_type("FIRST_ORDER") == "HO2"  # Middle tier
        assert migrate_plane_type("SECOND_ORDER") == "HO1"  # Lowest tier
        # Already canonical - unchanged
        assert migrate_plane_type("HO3") == "HO3"
        assert migrate_plane_type("HO2") == "HO2"
        assert migrate_plane_type("HO1") == "HO1"

    def test_migrate_tier_name(self):
        """migrate_tier_name converts legacy to canonical."""
        assert migrate_tier_name("HOT") == "HO3"
        assert migrate_tier_name("FIRST") == "HO1"  # Lowest tier (First Order)
        assert migrate_tier_name("SECOND") == "HO2"  # Middle tier (Second Order)
        assert migrate_tier_name("FIRST_ORDER") == "HO1"
        assert migrate_tier_name("SECOND_ORDER") == "HO2"
        # Already canonical
        assert migrate_tier_name("HO3") == "HO3"

    def test_default_ledger_names_canonical(self):
        """DEFAULT_LEDGER_NAMES uses canonical tier names."""
        assert "HO3" in DEFAULT_LEDGER_NAMES
        assert "HO2" in DEFAULT_LEDGER_NAMES
        assert "HO1" in DEFAULT_LEDGER_NAMES


class TestTierMigration:
    """Test tier manifest migration from legacy names."""

    def test_load_tier_json_hot_to_ho3(self):
        """Loading tier.json with 'HOT' migrates to 'HO3'."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tier_root = Path(tmpdir)
            tier_json = tier_root / "tier.json"

            # Write legacy tier.json
            tier_json.write_text(json.dumps({
                "tier": "HOT",
                "tier_root": str(tier_root),
                "ledger_path": "ledger/governance.jsonl",
                "status": "active",
            }))

            # Load should migrate
            manifest = TierManifest.load(tier_json)
            assert manifest.tier == "HO3"

    def test_load_tier_json_first_to_ho1(self):
        """Loading tier.json with 'FIRST' migrates to 'HO1' (lowest tier)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tier_root = Path(tmpdir)
            tier_json = tier_root / "tier.json"

            tier_json.write_text(json.dumps({
                "tier": "FIRST",
                "tier_root": str(tier_root),
                "ledger_path": "ledger/worker.jsonl",
                "status": "active",
            }))

            manifest = TierManifest.load(tier_json)
            assert manifest.tier == "HO1"  # FIRST (First Order) is lowest tier

    def test_save_writes_canonical(self):
        """Saving tier manifest writes canonical tier name."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tier_root = Path(tmpdir)

            manifest = TierManifest(
                tier="HO3",
                tier_root=tier_root,
                ledger_path=Path("ledger/governance.jsonl"),
            )
            manifest.save()

            # Re-read raw JSON
            data = json.loads((tier_root / "tier.json").read_text())
            assert data["tier"] == "HO3"


class TestPlaneContextPlaneAware:
    """Test PlaneContext with plane parameter."""

    def test_plane_context_creation(self):
        """PlaneContext can be created with canonical types."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plane = PlaneContext(
                name="test-ho3",
                plane_type=PlaneType.HO3,
                root=root,
            )
            assert plane.plane_type == PlaneType.HO3
            assert plane.name == "test-ho3"
            assert plane.root == root

    def test_can_reference_plane_ho3(self):
        """HO3 can reference HO2 and HO1."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plane = PlaneContext(
                name="ho3",
                plane_type=PlaneType.HO3,
                root=Path(tmpdir),
            )
            assert plane.can_reference_plane(PlaneType.HO2) is True
            assert plane.can_reference_plane(PlaneType.HO1) is True
            assert plane.can_reference_plane(PlaneType.HO3) is False

    def test_can_reference_plane_ho2(self):
        """HO2 can only reference HO1."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plane = PlaneContext(
                name="ho2",
                plane_type=PlaneType.HO2,
                root=Path(tmpdir),
            )
            assert plane.can_reference_plane(PlaneType.HO1) is True
            assert plane.can_reference_plane(PlaneType.HO3) is False
            assert plane.can_reference_plane(PlaneType.HO2) is False

    def test_can_reference_plane_ho1(self):
        """HO1 cannot reference other planes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plane = PlaneContext(
                name="ho1",
                plane_type=PlaneType.HO1,
                root=Path(tmpdir),
            )
            assert plane.can_reference_plane(PlaneType.HO3) is False
            assert plane.can_reference_plane(PlaneType.HO2) is False
            assert plane.can_reference_plane(PlaneType.HO1) is False


class TestPristinePerPlane:
    """Test pristine.py with plane parameter."""

    def test_classify_path_with_plane(self):
        """classify_path uses plane.root when provided."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "frameworks").mkdir()
            (root / "packages_store").mkdir()

            plane = PlaneContext(
                name="test",
                plane_type=PlaneType.HO3,
                root=root,
            )

            # Pristine path
            fw_path = root / "frameworks" / "test.md"
            assert classify_path(fw_path, plane=plane) == PathClass.PRISTINE

            # Derived path
            pkg_path = root / "packages_store" / "test.tar.gz"
            assert classify_path(pkg_path, plane=plane) == PathClass.DERIVED

    def test_is_inside_control_plane_with_plane(self):
        """is_inside_control_plane uses plane.root when provided."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Resolve to handle /var vs /private/var on macOS
            root = Path(tmpdir).resolve()
            plane = PlaneContext(
                name="test",
                plane_type=PlaneType.HO3,
                root=root,
            )

            # Create the directory to ensure it exists for resolution
            inside_dir = root / "some"
            inside_dir.mkdir(parents=True, exist_ok=True)
            inside = inside_dir / "path"

            # Use a path clearly outside the temp directory
            outside = Path("/usr/bin/ls")

            assert is_inside_control_plane(inside, plane=plane) is True
            assert is_inside_control_plane(outside, plane=plane) is False


class TestRegistryPerPlane:
    """Test registry.py with plane parameter."""

    def test_find_all_registries_with_plane(self):
        """find_all_registries searches within plane.root."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "registries").mkdir()
            (root / "registries" / "test_registry.csv").write_text("id,name\n1,test\n")

            plane = PlaneContext(
                name="test",
                plane_type=PlaneType.HO3,
                root=root,
            )

            registries = find_all_registries(plane=plane)
            assert len(registries) == 1
            assert registries[0].name == "test_registry.csv"


class TestLedgerFactoryCanonical:
    """Test LedgerFactory with canonical tier names."""

    def test_create_tier_ho3(self):
        """LedgerFactory.create_tier works with HO3."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            manifest, client = LedgerFactory.create_tier(
                tier="HO3",
                tier_root=root,
            )

            assert manifest.tier == "HO3"
            assert (root / "tier.json").exists()
            assert manifest.ledger_path == Path("ledger/governance.jsonl")

    def test_create_tier_ho2(self):
        """LedgerFactory.create_tier works with HO2."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            manifest, client = LedgerFactory.create_tier(
                tier="HO2",
                tier_root=root,
            )

            assert manifest.tier == "HO2"
            assert manifest.ledger_path == Path("ledger/workorder.jsonl")

    def test_create_tier_ho1(self):
        """LedgerFactory.create_tier works with HO1."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            manifest, client = LedgerFactory.create_tier(
                tier="HO1",
                tier_root=root,
            )

            assert manifest.tier == "HO1"
            assert manifest.ledger_path == Path("ledger/worker.jsonl")


class TestChainConfigCanonical:
    """Test chain config loading with canonical names."""

    def test_load_chain_config_migrates_legacy(self):
        """load_chain_config migrates legacy plane types."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_dir = root / "config"
            config_dir.mkdir()

            # Write config with legacy names
            # Note: FIRST_ORDER was middle tier, SECOND_ORDER was lowest tier
            config = {
                "planes": [
                    {"name": "hot", "type": "HOT", "root": str(root / "ho3")},
                    {"name": "first", "type": "FIRST_ORDER", "root": str(root / "ho2")},
                    {"name": "second", "type": "SECOND_ORDER", "root": str(root / "ho1")},
                ]
            }
            (config_dir / "control_plane_chain.json").write_text(json.dumps(config))

            # Create plane dirs
            (root / "ho3").mkdir()
            (root / "ho2").mkdir()
            (root / "ho1").mkdir()

            # Clear cache and set env
            clear_chain_config_cache()
            old_env = os.environ.get("CONTROL_PLANE_CHAIN_CONFIG")
            os.environ["CONTROL_PLANE_CHAIN_CONFIG"] = str(config_dir / "control_plane_chain.json")

            try:
                planes = load_chain_config()
                # Should have migrated to canonical types
                assert planes[0].plane_type == PlaneType.HO3  # HOT -> HO3
                assert planes[1].plane_type == PlaneType.HO2  # FIRST_ORDER -> HO2
                assert planes[2].plane_type == PlaneType.HO1  # SECOND_ORDER -> HO1
            finally:
                clear_chain_config_cache()
                if old_env:
                    os.environ["CONTROL_PLANE_CHAIN_CONFIG"] = old_env
                else:
                    os.environ.pop("CONTROL_PLANE_CHAIN_CONFIG", None)


class TestThreePlanesIntegration:
    """Integration tests for 3-plane operation."""

    def test_three_planes_created(self):
        """Three separate planes can be created with independent manifests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)

            # Create HO3
            ho3_root = base / "ho3"
            m3, c3 = LedgerFactory.create_tier("HO3", ho3_root)

            # Create HO2 with parent
            ho2_root = base / "ho2"
            m2, c2 = LedgerFactory.create_tier(
                "HO2",
                ho2_root,
                parent_ledger=str(m3.absolute_ledger_path),
            )

            # Create HO1 with parent
            ho1_root = base / "ho1"
            m1, c1 = LedgerFactory.create_tier(
                "HO1",
                ho1_root,
                parent_ledger=str(m2.absolute_ledger_path),
            )

            # Verify all three exist
            assert m3.tier == "HO3"
            assert m2.tier == "HO2"
            assert m1.tier == "HO1"

            # Verify parent chain
            assert m3.parent_ledger is None
            assert m2.parent_ledger == str(m3.absolute_ledger_path)
            assert m1.parent_ledger == str(m2.absolute_ledger_path)

    def test_each_plane_has_independent_ledger(self):
        """Each plane has its own ledger file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)

            m3, c3 = LedgerFactory.create_tier("HO3", base / "ho3")
            m2, c2 = LedgerFactory.create_tier("HO2", base / "ho2")
            m1, c1 = LedgerFactory.create_tier("HO1", base / "ho1")

            # All ledgers should be different paths
            ledgers = {
                m3.absolute_ledger_path,
                m2.absolute_ledger_path,
                m1.absolute_ledger_path,
            }
            assert len(ledgers) == 3


class TestBackwardCompatibility:
    """Test backward compatibility with HOT-only mode."""

    def test_single_plane_default(self):
        """Without chain config, get_current_plane returns a default plane."""
        # Clear any existing config
        clear_chain_config_cache()
        old_env = os.environ.get("CONTROL_PLANE_CHAIN_CONFIG")
        os.environ.pop("CONTROL_PLANE_CHAIN_CONFIG", None)

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                # Point to non-existent config
                os.environ["CONTROL_PLANE_CHAIN_CONFIG"] = str(Path(tmpdir) / "nonexistent.json")
                clear_chain_config_cache()

                plane = get_current_plane()
                # Should return a default plane
                assert plane is not None
                assert plane.name == "default"
        finally:
            clear_chain_config_cache()
            if old_env:
                os.environ["CONTROL_PLANE_CHAIN_CONFIG"] = old_env
            else:
                os.environ.pop("CONTROL_PLANE_CHAIN_CONFIG", None)

    def test_resolve_plane_type_legacy_names(self):
        """resolve_plane_type handles legacy names."""
        assert resolve_plane_type("hot") == PlaneType.HO3
        assert resolve_plane_type("first") == PlaneType.HO2  # first was middle tier
        assert resolve_plane_type("second") == PlaneType.HO1  # second was lowest tier

    def test_validate_target_plane_with_legacy_names(self):
        """validate_target_plane works with legacy plane names."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plane = PlaneContext(
                name="ho3",
                plane_type=PlaneType.HO3,
                root=Path(tmpdir),
            )

            # Should match "ho3" name
            assert validate_target_plane("ho3", plane) is True
            # "any" should always match
            assert validate_target_plane("any", plane) is True
            # Different plane should not match
            assert validate_target_plane("ho2", plane) is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
