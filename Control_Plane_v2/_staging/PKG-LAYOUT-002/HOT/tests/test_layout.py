"""TDD tests for PKG-LAYOUT-002 — Dynamic Paths (HO3 removed).

Updated from PKG-LAYOUT-001:
- HO3 references replaced with HO2 (3-tier model: HOT > HO2 > HO1)
- schema_version bumped to "1.1"
- Added test_ho3_is_invalid_tier regression guard

Tests verify:
- layout.json exists and has valid structure (3 tiers, no HO3)
- Layout class loads and resolves correct paths
- TierLayout and HotLayout frozen dataclasses work
- Bootstrap fallback when layout.json doesn't exist
- paths.py REGISTRIES_DIR matches LAYOUT.hot.registries
"""
import json
import os
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
HOT_ROOT = SCRIPT_DIR.parent
CP_ROOT = HOT_ROOT.parent

# Support running from staging: if CONTROL_PLANE_ROOT is set, use its HOT/
# for kernel imports (kernel/ lives in the installed environment, not staging)
_cp_root = os.getenv("CONTROL_PLANE_ROOT")
if _cp_root:
    sys.path.insert(0, str(Path(_cp_root) / "HOT"))
sys.path.insert(0, str(HOT_ROOT))


# === layout.json Structure Tests ===

class TestLayoutJsonExists:
    """layout.json must exist and have valid structure."""

    LAYOUT_PATH = HOT_ROOT / "config" / "layout.json"

    def test_layout_json_exists(self):
        """layout.json must exist in HOT/config/."""
        assert self.LAYOUT_PATH.exists(), "HOT/config/layout.json not found"

    def test_layout_json_is_valid_json(self):
        """layout.json must be parseable JSON."""
        data = json.loads(self.LAYOUT_PATH.read_text())
        assert isinstance(data, dict)

    def test_has_schema_version(self):
        """Must declare schema_version 1.1."""
        data = json.loads(self.LAYOUT_PATH.read_text())
        assert data.get("schema_version") == "1.1"

    def test_has_tiers(self):
        """Must declare exactly 3 tiers: HOT, HO2, HO1 (no HO3)."""
        data = json.loads(self.LAYOUT_PATH.read_text())
        tiers = data.get("tiers", {})
        for tier in ["HOT", "HO2", "HO1"]:
            assert tier in tiers, f"Missing tier: {tier}"
        assert "HO3" not in tiers, "HO3 must NOT be in tiers"
        assert len(tiers) == 3, f"Expected 3 tiers, got {len(tiers)}"

    def test_has_hot_dirs(self):
        """Must declare HOT directory layout."""
        data = json.loads(self.LAYOUT_PATH.read_text())
        hot_dirs = data.get("hot_dirs", {})
        for key in ["kernel", "config", "registries", "schemas", "scripts",
                     "installed", "ledger"]:
            assert key in hot_dirs, f"Missing hot_dir: {key}"

    def test_has_tier_dirs(self):
        """Must declare per-tier directory layout."""
        data = json.loads(self.LAYOUT_PATH.read_text())
        tier_dirs = data.get("tier_dirs", {})
        for key in ["registries", "installed", "ledger", "scripts", "tests"]:
            assert key in tier_dirs, f"Missing tier_dir: {key}"

    def test_has_registry_files(self):
        """Must declare registry file names."""
        data = json.loads(self.LAYOUT_PATH.read_text())
        reg_files = data.get("registry_files", {})
        for key in ["control_plane", "file_ownership", "packages_state"]:
            assert key in reg_files, f"Missing registry_file: {key}"

    def test_has_ledger_files(self):
        """Must declare ledger file names."""
        data = json.loads(self.LAYOUT_PATH.read_text())
        ledger_files = data.get("ledger_files", {})
        for key in ["governance", "packages", "index"]:
            assert key in ledger_files, f"Missing ledger_file: {key}"


# === Layout Class Tests ===

class TestLayoutClass:
    """Layout class must load layout.json and resolve paths."""

    def test_layout_module_importable(self):
        """kernel.layout must be importable."""
        from kernel import layout
        assert hasattr(layout, "Layout")

    def test_load_layout_returns_layout(self):
        """load_layout() must return a Layout instance."""
        from kernel.layout import load_layout
        lay = load_layout()
        assert lay is not None
        assert type(lay).__name__ == "Layout"

    def test_layout_singleton_exists(self):
        """Module-level LAYOUT singleton must exist."""
        from kernel.layout import LAYOUT
        assert LAYOUT is not None


class TestHotLayout:
    """HotLayout must resolve HOT-tier paths."""

    def test_hot_registries_is_path(self):
        """LAYOUT.hot.registries must be a Path."""
        from kernel.layout import LAYOUT
        assert isinstance(LAYOUT.hot.registries, Path)

    def test_hot_registries_points_to_hot_registries(self):
        """LAYOUT.hot.registries must end with HOT/registries."""
        from kernel.layout import LAYOUT
        assert str(LAYOUT.hot.registries).endswith("HOT/registries")

    def test_hot_kernel_is_path(self):
        """LAYOUT.hot.kernel must be a Path."""
        from kernel.layout import LAYOUT
        assert isinstance(LAYOUT.hot.kernel, Path)

    def test_hot_config_is_path(self):
        """LAYOUT.hot.config must be a Path."""
        from kernel.layout import LAYOUT
        assert isinstance(LAYOUT.hot.config, Path)

    def test_hot_schemas_is_path(self):
        """LAYOUT.hot.schemas must be a Path."""
        from kernel.layout import LAYOUT
        assert isinstance(LAYOUT.hot.schemas, Path)

    def test_hot_installed_is_path(self):
        """LAYOUT.hot.installed must be a Path."""
        from kernel.layout import LAYOUT
        assert isinstance(LAYOUT.hot.installed, Path)

    def test_hot_ledger_is_path(self):
        """LAYOUT.hot.ledger must be a Path."""
        from kernel.layout import LAYOUT
        assert isinstance(LAYOUT.hot.ledger, Path)


class TestTierLayout:
    """TierLayout must resolve per-tier paths."""

    def test_tier_method_exists(self):
        """LAYOUT.tier() must be callable."""
        from kernel.layout import LAYOUT
        assert callable(LAYOUT.tier)

    def test_tier_ho2_returns_tier_layout(self):
        """LAYOUT.tier('HO2') must return a TierLayout."""
        from kernel.layout import LAYOUT
        t = LAYOUT.tier("HO2")
        assert t is not None

    def test_tier_ho2_installed_is_path(self):
        """LAYOUT.tier('HO2').installed must be a Path ending with HO2/installed."""
        from kernel.layout import LAYOUT
        t = LAYOUT.tier("HO2")
        assert isinstance(t.installed, Path)
        assert str(t.installed).endswith("HO2/installed")

    def test_tier_ho2_ledger_is_path(self):
        """LAYOUT.tier('HO2').ledger must be a Path ending with HO2/ledger."""
        from kernel.layout import LAYOUT
        t = LAYOUT.tier("HO2")
        assert isinstance(t.ledger, Path)
        assert str(t.ledger).endswith("HO2/ledger")

    def test_tier_ho2_tests_is_path(self):
        """LAYOUT.tier('HO2').tests must be a Path."""
        from kernel.layout import LAYOUT
        t = LAYOUT.tier("HO2")
        assert isinstance(t.tests, Path)

    def test_tier_invalid_raises(self):
        """LAYOUT.tier() with invalid tier must raise."""
        from kernel.layout import LAYOUT
        with pytest.raises((KeyError, ValueError)):
            LAYOUT.tier("INVALID")

    def test_ho3_is_invalid_tier(self):
        """LAYOUT.tier('HO3') must raise — HO3 is dead, permanently."""
        from kernel.layout import LAYOUT
        with pytest.raises((KeyError, ValueError)):
            LAYOUT.tier("HO3")


# === Convenience Methods ===

class TestLayoutConvenience:
    """registry_file() and ledger_file() must resolve full paths."""

    def test_registry_file_resolves(self):
        """LAYOUT.registry_file('file_ownership') must resolve to .csv path."""
        from kernel.layout import LAYOUT
        path = LAYOUT.registry_file("file_ownership")
        assert isinstance(path, Path)
        assert str(path).endswith("file_ownership.csv")

    def test_registry_file_in_hot_registries(self):
        """Registry file must be under HOT/registries/."""
        from kernel.layout import LAYOUT
        path = LAYOUT.registry_file("control_plane")
        assert "HOT/registries" in str(path) or "HOT\\registries" in str(path)

    def test_ledger_file_resolves(self):
        """LAYOUT.ledger_file('HO2', 'packages') must resolve to .jsonl path."""
        from kernel.layout import LAYOUT
        path = LAYOUT.ledger_file("HO2", "packages")
        assert isinstance(path, Path)
        assert str(path).endswith("packages.jsonl")

    def test_ledger_file_invalid_key_raises(self):
        """ledger_file() with unknown key must raise."""
        from kernel.layout import LAYOUT
        with pytest.raises(KeyError):
            LAYOUT.ledger_file("HO2", "nonexistent")


# === Bootstrap Fallback ===

class TestBootstrapFallback:
    """Layout must have a fallback when layout.json doesn't exist yet."""

    def test_load_layout_with_missing_file(self, tmp_path):
        """load_layout() must return a usable Layout even without layout.json."""
        from kernel.layout import load_layout
        lay = load_layout(config_dir=tmp_path)
        assert lay is not None
        # Fallback should still provide .hot.registries
        assert lay.hot.registries is not None


# === paths.py Bridge ===

class TestPathsBridge:
    """REGISTRIES_DIR in paths.py must match LAYOUT.hot.registries."""

    def test_registries_dir_matches_layout(self):
        """paths.REGISTRIES_DIR must equal LAYOUT.hot.registries."""
        from kernel.paths import REGISTRIES_DIR
        from kernel.layout import LAYOUT
        assert REGISTRIES_DIR == LAYOUT.hot.registries, \
            f"paths.REGISTRIES_DIR={REGISTRIES_DIR} != LAYOUT={LAYOUT.hot.registries}"
