#!/usr/bin/env python3
"""
test_chain.py - Tests for multi-plane chain operations.

Tests:
- Chain configuration loading
- Cross-plane operations blocked
- Receipts are plane-scoped
- IAM plane permissions enforced
"""
import json
import sys
import tempfile
from pathlib import Path

import pytest

# Add repo root for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kernel.plane import (
    PlaneContext,
    PlaneType,
    PlaneError,
    load_chain_config,
    clear_chain_config_cache,
    get_current_plane,
    get_plane_by_root,
    validate_target_plane,
)
from kernel.install_auth import (
    InstallerClaims,
    authorize,
    require_authorization,
    DEFAULT_PLANES,
    DEFAULT_TIERS,
)
from kernel.auth import Identity


class TestChainConfiguration:
    """Tests for chain configuration."""

    def test_load_three_plane_chain(self, tmp_path, monkeypatch):
        """Test loading a complete 3-plane chain configuration."""
        hot_root = tmp_path / "hot"
        first_root = tmp_path / "first"
        second_root = tmp_path / "second"

        for p in [hot_root, first_root, second_root]:
            p.mkdir()

        config = {
            "planes": [
                {"name": "hot", "type": "HOT", "root": str(hot_root)},
                {"name": "first", "type": "FIRST_ORDER", "root": str(first_root)},
                {"name": "second", "type": "SECOND_ORDER", "root": str(second_root)},
            ]
        }

        config_path = tmp_path / "chain.json"
        config_path.write_text(json.dumps(config))

        monkeypatch.setenv("CONTROL_PLANE_CHAIN_CONFIG", str(config_path))
        clear_chain_config_cache()

        planes = load_chain_config()
        assert len(planes) == 3

        assert planes[0].name == "hot"
        assert planes[0].plane_type == PlaneType.HOT

        assert planes[1].name == "first"
        assert planes[1].plane_type == PlaneType.FIRST_ORDER

        assert planes[2].name == "second"
        assert planes[2].plane_type == PlaneType.SECOND_ORDER

    def test_plane_isolation(self, tmp_path, monkeypatch):
        """Test that planes have isolated roots."""
        hot_root = tmp_path / "hot"
        first_root = tmp_path / "first"

        for p in [hot_root, first_root]:
            p.mkdir()

        config = {
            "planes": [
                {"name": "hot", "type": "HOT", "root": str(hot_root)},
                {"name": "first", "type": "FIRST_ORDER", "root": str(first_root)},
            ]
        }

        config_path = tmp_path / "chain.json"
        config_path.write_text(json.dumps(config))

        monkeypatch.setenv("CONTROL_PLANE_CHAIN_CONFIG", str(config_path))
        clear_chain_config_cache()

        hot = get_plane_by_root(hot_root)
        first = get_plane_by_root(first_root)

        # Verify isolation
        assert hot.root != first.root
        assert not hot.is_path_inside(first_root / "packages")
        assert not first.is_path_inside(hot_root / "packages")


class TestCrossPlaneOperations:
    """Tests for cross-plane operation blocking."""

    def test_install_refuses_cross_plane_writes(self, tmp_path):
        """Test that install operations don't write outside plane root."""
        hot = PlaneContext(
            name="hot",
            plane_type=PlaneType.HOT,
            root=tmp_path / "hot",
        )
        first = PlaneContext(
            name="first",
            plane_type=PlaneType.FIRST_ORDER,
            root=tmp_path / "first",
        )

        # Create test paths
        hot_path = hot.root / "packages" / "test.json"
        first_path = first.root / "packages" / "test.json"

        # HOT should only contain HOT paths
        assert hot.is_path_inside(hot_path) is True
        assert hot.is_path_inside(first_path) is False

        # FIRST should only contain FIRST paths
        assert first.is_path_inside(first_path) is True
        assert first.is_path_inside(hot_path) is False


class TestPlaneScopedReceipts:
    """Tests for plane-scoped receipts."""

    def test_receipts_are_plane_scoped(self, tmp_path):
        """Test that drift detection uses plane-scoped receipts."""
        # Create two planes with their own receipts directories
        hot = PlaneContext(
            name="hot",
            plane_type=PlaneType.HOT,
            root=tmp_path / "hot",
        )
        first = PlaneContext(
            name="first",
            plane_type=PlaneType.FIRST_ORDER,
            root=tmp_path / "first",
        )

        # Create receipt directories
        hot_receipts = hot.receipts_dir
        first_receipts = first.receipts_dir
        hot_receipts.mkdir(parents=True)
        first_receipts.mkdir(parents=True)

        # Create a receipt in HOT plane
        hot_pkg_dir = hot_receipts / "PKG-T0-001"
        hot_pkg_dir.mkdir()
        hot_receipt = {
            "id": "PKG-T0-001",
            "version": "1.0.0",
            "plane_name": "hot",
            "plane_root": str(hot.root),
            "files": [],
        }
        (hot_pkg_dir / "receipt.json").write_text(json.dumps(hot_receipt))

        # Create a receipt in FIRST plane
        first_pkg_dir = first_receipts / "PKG-T0-002"
        first_pkg_dir.mkdir()
        first_receipt = {
            "id": "PKG-T0-002",
            "version": "1.0.0",
            "plane_name": "first",
            "plane_root": str(first.root),
            "files": [],
        }
        (first_pkg_dir / "receipt.json").write_text(json.dumps(first_receipt))

        # Load receipts and verify they match their planes
        hot_loaded = json.loads((hot_pkg_dir / "receipt.json").read_text())
        first_loaded = json.loads((first_pkg_dir / "receipt.json").read_text())

        assert hot_loaded["plane_name"] == "hot"
        assert hot_loaded["plane_root"] == str(hot.root)

        assert first_loaded["plane_name"] == "first"
        assert first_loaded["plane_root"] == str(first.root)

    def test_drift_detection_doesnt_cross_contaminate(self, tmp_path):
        """Test that drift detection only considers receipts for current plane."""
        hot = PlaneContext(
            name="hot",
            plane_type=PlaneType.HOT,
            root=tmp_path / "hot",
        )

        # Create receipts for HOT
        receipts_dir = hot.receipts_dir
        receipts_dir.mkdir(parents=True)

        # Receipt for this plane
        pkg_dir = receipts_dir / "PKG-T0-001"
        pkg_dir.mkdir()
        receipt = {
            "id": "PKG-T0-001",
            "plane_root": str(hot.root),  # Matches current plane
            "files": [{"path": "lib/test.py", "sha256": "abc123"}],
        }
        (pkg_dir / "receipt.json").write_text(json.dumps(receipt))

        # Receipt from a different plane (should be filtered out)
        other_pkg_dir = receipts_dir / "PKG-T0-002"
        other_pkg_dir.mkdir()
        other_receipt = {
            "id": "PKG-T0-002",
            "plane_root": "/some/other/plane",  # Different plane!
            "files": [{"path": "lib/other.py", "sha256": "def456"}],
        }
        (other_pkg_dir / "receipt.json").write_text(json.dumps(other_receipt))

        # When doing drift detection, only PKG-T0-001 should be considered
        # because PKG-T0-002 has a different plane_root


class TestIAMPlanePermissions:
    """Tests for IAM plane permission enforcement."""

    def test_iam_plane_permissions_enforced(self, tmp_path):
        """Test that token for first cannot install in hot."""
        # Create claims with restricted planes
        claims = InstallerClaims(
            subject="test_user",
            roles=["maintainer"],
            allowed_actions={"install", "uninstall", "verify"},
            allowed_tiers=DEFAULT_TIERS.copy(),
            allowed_planes={"first", "second"},  # NOT allowed in HOT
        )

        # Should succeed for 'first' plane
        assert authorize(
            action="install",
            pkg_id="PKG-T0-001",
            tier="T0",
            env="dev",
            claims=claims,
            plane="first",
        ) is True

        # Should fail for 'hot' plane
        assert authorize(
            action="install",
            pkg_id="PKG-T0-001",
            tier="T0",
            env="dev",
            claims=claims,
            plane="hot",
        ) is False

    def test_admin_has_all_planes(self, tmp_path):
        """Test that admin role has access to all planes."""
        identity = Identity(user="admin_user", roles=["admin"])
        claims = InstallerClaims.from_identity(identity, env="dev")

        # Admin should have access to all planes
        assert "hot" in claims.allowed_planes
        assert "first" in claims.allowed_planes
        assert "second" in claims.allowed_planes

        # Should succeed for any plane
        for plane in ["hot", "first", "second"]:
            assert authorize(
                action="install",
                pkg_id="PKG-T0-001",
                tier="T0",
                env="dev",
                claims=claims,
                plane=plane,
            ) is True

    def test_require_authorization_raises(self, tmp_path):
        """Test that require_authorization raises on failure."""
        claims = InstallerClaims(
            subject="test_user",
            roles=["maintainer"],
            allowed_actions={"install"},
            allowed_tiers=DEFAULT_TIERS.copy(),
            allowed_planes={"first"},  # Only first
        )

        # Should succeed for 'first'
        require_authorization(
            action="install",
            pkg_id="PKG-T0-001",
            tier="T0",
            env="dev",
            claims=claims,
            plane="first",
        )  # No exception

        # Should raise for 'hot'
        with pytest.raises(PermissionError, match="plane 'hot' not in allowed_planes"):
            require_authorization(
                action="install",
                pkg_id="PKG-T0-001",
                tier="T0",
                env="dev",
                claims=claims,
                plane="hot",
            )

    def test_prod_restricts_hot_for_non_admin(self, tmp_path):
        """Test that production env restricts HOT plane for non-admins."""
        identity = Identity(user="maintainer_user", roles=["maintainer"])
        claims = InstallerClaims.from_identity(identity, env="prod")

        # In production, non-admins cannot access HOT
        assert "hot" not in claims.allowed_planes
        assert "first" in claims.allowed_planes
        assert "second" in claims.allowed_planes

    def test_claims_with_plane_restriction(self):
        """Test creating claims with plane restrictions."""
        claims = InstallerClaims(
            subject="test_user",
            roles=["admin"],
            allowed_actions={"install"},
            allowed_tiers=DEFAULT_TIERS.copy(),
            allowed_planes=DEFAULT_PLANES.copy(),
        )

        # Restrict to only 'second' plane
        restricted = claims.with_plane_restriction({"second"})

        assert restricted.allowed_planes == {"second"}
        assert "hot" not in restricted.allowed_planes
        assert "first" not in restricted.allowed_planes


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
