"""
layout.py - Centralized path configuration for Control Plane v2.

Loads HOT/config/layout.json and provides typed path resolution via
frozen dataclasses. All path lookups go through the Layout singleton:

    from kernel.layout import LAYOUT

    LAYOUT.hot.registries          # → .../HOT/registries
    LAYOUT.tier("HO3").installed   # → .../HO3/installed
    LAYOUT.registry_file("file_ownership")   # → .../HOT/registries/file_ownership.csv
    LAYOUT.ledger_file("HO3", "packages")    # → .../HO3/ledger/packages.jsonl
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional


def _find_cp_root() -> Path:
    """Find the Control_Plane_v2 root by walking up from this file."""
    current = Path(__file__).resolve()
    for parent in [current] + list(current.parents):
        if parent.name == "Control_Plane_v2":
            return parent
    return Path.cwd()


@dataclass(frozen=True)
class HotLayout:
    """Resolved paths for the HOT tier."""
    kernel: Path
    config: Path
    registries: Path
    schemas: Path
    scripts: Path
    installed: Path
    ledger: Path
    frameworks: Path


@dataclass(frozen=True)
class TierLayout:
    """Resolved paths for a non-HOT tier (HO3, HO2, HO1)."""
    root: Path
    registries: Path
    installed: Path
    ledger: Path
    packages_store: Path
    scripts: Path
    tests: Path
    spec_packs: Path


class Layout:
    """Centralized path resolver loaded from layout.json."""

    def __init__(self, cp_root: Path, config: dict):
        self._cp_root = cp_root
        self._config = config
        self._tiers: Dict[str, str] = config.get("tiers", {})
        self._tier_dirs: Dict[str, str] = config.get("tier_dirs", {})
        self._registry_files: Dict[str, str] = config.get("registry_files", {})
        self._ledger_files: Dict[str, str] = config.get("ledger_files", {})

        hot_dirs = config.get("hot_dirs", {})
        self.hot = HotLayout(
            kernel=cp_root / hot_dirs.get("kernel", "HOT/kernel"),
            config=cp_root / hot_dirs.get("config", "HOT/config"),
            registries=cp_root / hot_dirs.get("registries", "HOT/registries"),
            schemas=cp_root / hot_dirs.get("schemas", "HOT/schemas"),
            scripts=cp_root / hot_dirs.get("scripts", "HOT/scripts"),
            installed=cp_root / hot_dirs.get("installed", "HOT/installed"),
            ledger=cp_root / hot_dirs.get("ledger", "HOT/ledger"),
            frameworks=cp_root / hot_dirs.get("frameworks", "HOT"),
        )

        self._tier_cache: Dict[str, TierLayout] = {}

    def tier(self, name: str) -> TierLayout:
        """Get resolved paths for a tier (HO3, HO2, HO1).

        Args:
            name: Tier name (HOT, HO3, HO2, HO1)

        Returns:
            TierLayout with resolved paths.

        Raises:
            KeyError: If tier name is not in layout.json.
        """
        if name not in self._tiers:
            raise KeyError(f"Unknown tier: {name}")

        if name in self._tier_cache:
            return self._tier_cache[name]

        tier_root = self._cp_root / self._tiers[name]
        td = self._tier_dirs
        layout = TierLayout(
            root=tier_root,
            registries=tier_root / td.get("registries", "registries"),
            installed=tier_root / td.get("installed", "installed"),
            ledger=tier_root / td.get("ledger", "ledger"),
            packages_store=tier_root / td.get("packages_store", "packages_store"),
            scripts=tier_root / td.get("scripts", "scripts"),
            tests=tier_root / td.get("tests", "tests"),
            spec_packs=tier_root / td.get("spec_packs", "spec_packs"),
        )
        self._tier_cache[name] = layout
        return layout

    def registry_file(self, key: str) -> Path:
        """Resolve a registry file path by logical name.

        Args:
            key: Registry key (e.g., "file_ownership", "control_plane")

        Returns:
            Full path to the registry file.

        Raises:
            KeyError: If key is not in layout.json registry_files.
        """
        if key not in self._registry_files:
            raise KeyError(f"Unknown registry file: {key}")
        return self.hot.registries / self._registry_files[key]

    def ledger_file(self, tier: str, key: str) -> Path:
        """Resolve a ledger file path by tier and logical name.

        Args:
            tier: Tier name (HOT, HO3, HO2, HO1)
            key: Ledger key (e.g., "packages", "governance")

        Returns:
            Full path to the ledger file.

        Raises:
            KeyError: If tier or key is not recognized.
        """
        if key not in self._ledger_files:
            raise KeyError(f"Unknown ledger file: {key}")
        tier_layout = self.tier(tier)
        return tier_layout.ledger / self._ledger_files[key]


def _default_config() -> dict:
    """Return fallback config when layout.json doesn't exist."""
    return {
        "schema_version": "1.0",
        "tiers": {"HOT": "HOT", "HO3": "HO3", "HO2": "HO2", "HO1": "HO1"},
        "hot_dirs": {
            "kernel": "HOT/kernel", "config": "HOT/config",
            "registries": "HOT/registries", "schemas": "HOT/schemas",
            "scripts": "HOT/scripts", "installed": "HOT/installed",
            "ledger": "HOT/ledger", "frameworks": "HOT",
        },
        "tier_dirs": {
            "registries": "registries", "installed": "installed",
            "ledger": "ledger", "packages_store": "packages_store",
            "scripts": "scripts", "tests": "tests", "spec_packs": "spec_packs",
        },
        "registry_files": {
            "control_plane": "control_plane_registry.csv",
            "file_ownership": "file_ownership.csv",
            "packages_state": "packages_state.csv",
            "frameworks": "frameworks_registry.csv",
            "specs": "specs_registry.csv",
        },
        "ledger_files": {
            "governance": "governance.jsonl", "packages": "packages.jsonl",
            "kernel": "kernel.jsonl", "index": "index.jsonl",
        },
    }


def load_layout(config_dir: Optional[Path] = None) -> Layout:
    """Load layout from config directory.

    Args:
        config_dir: Directory containing layout.json.
            Defaults to HOT/config/ relative to this file.

    Returns:
        Layout instance (not cached — use LAYOUT singleton for caching).
    """
    cp_root = _find_cp_root()

    if config_dir is None:
        config_dir = cp_root / "HOT" / "config"

    layout_path = config_dir / "layout.json"

    if layout_path.exists():
        config = json.loads(layout_path.read_text())
    else:
        config = _default_config()

    return Layout(cp_root, config)


# Module-level singleton
LAYOUT = load_layout()
