#!/usr/bin/env python3
"""
validate_tier_deps.py - Validate tier dependency constraints.

Enforces I1-TIER: Lower tiers CANNOT depend on higher tiers.

Tier hierarchy: G0 < T0 < T1 < T2 < T3

Per FMWK-PKG-001: Package Standard v1.0

Usage:
    python3 scripts/validate_tier_deps.py
    python3 scripts/validate_tier_deps.py --strict
    python3 scripts/validate_tier_deps.py --manifest packages/PKG-T0-001/manifest.json
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# Add repo root for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.paths import CONTROL_PLANE

# Tier ordering (lower number = lower tier)
TIER_ORDER: Dict[str, int] = {
    "G0": 0,
    "T0": 1,
    "T1": 2,
    "T2": 3,
    "T3": 4,
}

# Valid tiers
VALID_TIERS: Set[str] = set(TIER_ORDER.keys())

# Registry paths
PKG_REGISTRY = CONTROL_PLANE / "registries" / "packages_registry.csv"
PACKAGES_DIR = CONTROL_PLANE / "packages"


class TierViolation:
    """A tier dependency violation."""

    def __init__(
        self,
        pkg_id: str,
        pkg_tier: str,
        dep_id: str,
        dep_tier: str,
        message: str
    ):
        self.pkg_id = pkg_id
        self.pkg_tier = pkg_tier
        self.dep_id = dep_id
        self.dep_tier = dep_tier
        self.message = message

    def __str__(self) -> str:
        return (
            f"{self.pkg_id} ({self.pkg_tier}) -> {self.dep_id} ({self.dep_tier}): "
            f"{self.message}"
        )


def parse_tier_from_id(pkg_id: str) -> Optional[str]:
    """Extract tier from package ID.

    Args:
        pkg_id: Package ID (e.g., PKG-T0-001)

    Returns:
        Tier string or None if invalid
    """
    if not pkg_id.startswith("PKG-"):
        return None

    parts = pkg_id.split("-")
    if len(parts) < 3:
        return None

    tier = parts[1]
    return tier if tier in VALID_TIERS else None


def get_tier_order(tier: str) -> int:
    """Get numeric order of tier.

    Args:
        tier: Tier string

    Returns:
        Tier order (0=G0, 1=T0, etc.)

    Raises:
        ValueError: If tier is invalid
    """
    if tier not in TIER_ORDER:
        raise ValueError(f"Invalid tier: {tier}")
    return TIER_ORDER[tier]


def check_tier_dependency(
    pkg_tier: str,
    dep_tier: str
) -> bool:
    """Check if dependency is valid per tier rules.

    Args:
        pkg_tier: Package's tier
        dep_tier: Dependency's tier

    Returns:
        True if dependency is allowed
    """
    pkg_order = get_tier_order(pkg_tier)
    dep_order = get_tier_order(dep_tier)

    # Packages can only depend on same or lower tiers
    return dep_order <= pkg_order


def load_manifest(manifest_path: Path) -> Optional[Dict]:
    """Load package manifest.json.

    Args:
        manifest_path: Path to manifest.json

    Returns:
        Parsed manifest dict or None
    """
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def validate_manifest(manifest_path: Path) -> Tuple[List[TierViolation], List[str]]:
    """Validate tier dependencies in a manifest.

    Args:
        manifest_path: Path to manifest.json

    Returns:
        Tuple of (violations, warnings)
    """
    violations = []
    warnings = []

    manifest = load_manifest(manifest_path)
    if manifest is None:
        warnings.append(f"Could not load manifest: {manifest_path}")
        return violations, warnings

    pkg_id = manifest.get("id", "")
    pkg_tier = manifest.get("tier", "")
    deps = manifest.get("deps", [])

    if not pkg_id:
        warnings.append(f"Manifest missing id: {manifest_path}")
        return violations, warnings

    if not pkg_tier:
        pkg_tier = parse_tier_from_id(pkg_id)
        if not pkg_tier:
            warnings.append(f"Could not determine tier for {pkg_id}")
            return violations, warnings

    if pkg_tier not in VALID_TIERS:
        warnings.append(f"Invalid tier '{pkg_tier}' for {pkg_id}")
        return violations, warnings

    # Check Genesis zero-deps constraint (I5-GENESIS-ZERO)
    if pkg_tier == "G0" and deps:
        violations.append(TierViolation(
            pkg_id=pkg_id,
            pkg_tier=pkg_tier,
            dep_id=deps[0],
            dep_tier="?",
            message="Genesis (G0) packages must have ZERO dependencies (I5-GENESIS-ZERO)"
        ))

    # Check each dependency
    for dep_id in deps:
        dep_tier = parse_tier_from_id(dep_id)

        if dep_tier is None:
            warnings.append(f"{pkg_id}: Could not determine tier for dependency {dep_id}")
            continue

        if not check_tier_dependency(pkg_tier, dep_tier):
            violations.append(TierViolation(
                pkg_id=pkg_id,
                pkg_tier=pkg_tier,
                dep_id=dep_id,
                dep_tier=dep_tier,
                message=f"Tier violation: {pkg_tier} cannot depend on {dep_tier} (I1-TIER)"
            ))

    return violations, warnings


def validate_all_manifests() -> Tuple[List[TierViolation], List[str]]:
    """Validate all package manifests in packages/ directory.

    Returns:
        Tuple of (all violations, all warnings)
    """
    all_violations = []
    all_warnings = []

    if not PACKAGES_DIR.exists():
        all_warnings.append(f"Packages directory not found: {PACKAGES_DIR}")
        return all_violations, all_warnings

    for pkg_dir in PACKAGES_DIR.iterdir():
        if not pkg_dir.is_dir():
            continue

        manifest_path = pkg_dir / "manifest.json"
        if manifest_path.exists():
            violations, warnings = validate_manifest(manifest_path)
            all_violations.extend(violations)
            all_warnings.extend(warnings)

    return all_violations, all_warnings


def validate_registry() -> Tuple[List[TierViolation], List[str]]:
    """Validate tier dependencies in packages_registry.csv.

    Returns:
        Tuple of (violations, warnings)
    """
    violations = []
    warnings = []

    if not PKG_REGISTRY.exists():
        warnings.append(f"Packages registry not found: {PKG_REGISTRY}")
        return violations, warnings

    # Load all packages to build tier map
    tier_map: Dict[str, str] = {}
    rows = []

    with open(PKG_REGISTRY, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
            pkg_id = row.get("id", "").strip()
            if not pkg_id:
                continue

            # Get tier from registry or infer from ID
            tier = row.get("tier", "").strip()
            if not tier:
                tier = parse_tier_from_id(pkg_id)

            if tier:
                tier_map[pkg_id] = tier

    # Validate each package's dependencies
    for row in rows:
        pkg_id = row.get("id", "").strip()
        if not pkg_id:
            continue

        pkg_tier = tier_map.get(pkg_id)
        if not pkg_tier:
            warnings.append(f"Could not determine tier for {pkg_id}")
            continue

        deps_str = row.get("deps", "").strip()
        if not deps_str:
            continue

        # Check Genesis zero-deps constraint
        if pkg_tier == "G0":
            violations.append(TierViolation(
                pkg_id=pkg_id,
                pkg_tier=pkg_tier,
                dep_id=deps_str.split(",")[0].strip(),
                dep_tier="?",
                message="Genesis (G0) packages must have ZERO dependencies (I5-GENESIS-ZERO)"
            ))
            continue

        # Parse dependencies (may be comma-separated)
        for dep_spec in deps_str.split(","):
            dep_spec = dep_spec.strip()
            if not dep_spec:
                continue

            # Handle version constraint (PKG-T0-001@^1.0.0)
            dep_id = dep_spec.split("@")[0].strip()

            dep_tier = tier_map.get(dep_id) or parse_tier_from_id(dep_id)

            if not dep_tier:
                warnings.append(f"{pkg_id}: Unknown dependency {dep_id}")
                continue

            if not check_tier_dependency(pkg_tier, dep_tier):
                violations.append(TierViolation(
                    pkg_id=pkg_id,
                    pkg_tier=pkg_tier,
                    dep_id=dep_id,
                    dep_tier=dep_tier,
                    message=f"Tier violation: {pkg_tier} cannot depend on {dep_tier} (I1-TIER)"
                ))

    return violations, warnings


def print_tier_matrix():
    """Print tier dependency matrix for reference."""
    print("\nTier Dependency Matrix:")
    print("From/To | G0  | T0  | T1  | T2  | T3")
    print("--------|-----|-----|-----|-----|-----")

    for from_tier in ["G0", "T0", "T1", "T2", "T3"]:
        row = f"  {from_tier}   |"
        for to_tier in ["G0", "T0", "T1", "T2", "T3"]:
            if from_tier == to_tier:
                row += "  -  |"
            elif check_tier_dependency(from_tier, to_tier):
                row += " OK  |"
            else:
                row += "  X  |"
        print(row)

    print("\nOK = Allowed, X = Forbidden, - = Same tier")


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Validate tier dependency constraints (FMWK-PKG-001)"
    )
    parser.add_argument(
        "--manifest",
        help="Validate a specific manifest.json file"
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as errors"
    )
    parser.add_argument(
        "--show-matrix",
        action="store_true",
        help="Show tier dependency matrix"
    )
    parser.add_argument(
        "--registry-only",
        action="store_true",
        help="Only validate packages_registry.csv"
    )

    args = parser.parse_args()

    if args.show_matrix:
        print_tier_matrix()
        return 0

    all_violations = []
    all_warnings = []

    if args.manifest:
        # Validate single manifest
        manifest_path = Path(args.manifest)
        if not manifest_path.is_absolute():
            manifest_path = CONTROL_PLANE / manifest_path

        print(f"Validating manifest: {manifest_path}")
        violations, warnings = validate_manifest(manifest_path)
        all_violations.extend(violations)
        all_warnings.extend(warnings)
    else:
        # Validate registry
        print(f"Validating registry: {PKG_REGISTRY}")
        violations, warnings = validate_registry()
        all_violations.extend(violations)
        all_warnings.extend(warnings)

        if not args.registry_only:
            # Also validate package manifests
            print(f"Validating manifests in: {PACKAGES_DIR}")
            violations, warnings = validate_all_manifests()
            all_violations.extend(violations)
            all_warnings.extend(warnings)

    # Print results
    print()

    if all_violations:
        print("VIOLATIONS:")
        for v in all_violations:
            print(f"  ERROR: {v}")

    if all_warnings:
        print("\nWARNINGS:")
        for w in all_warnings:
            print(f"  WARN: {w}")

    # Summary
    print()
    print(f"Tier validation complete:")
    print(f"  Violations: {len(all_violations)}")
    print(f"  Warnings: {len(all_warnings)}")

    if all_violations:
        print("\nFAIL: Tier dependency violations detected")
        return 1

    if args.strict and all_warnings:
        print("\nFAIL: Warnings present in strict mode")
        return 1

    print("\nOK: All tier dependencies valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
