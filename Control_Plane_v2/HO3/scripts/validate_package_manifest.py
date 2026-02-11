#!/usr/bin/env python3
"""
validate_package_manifest.py - Validate package manifest.json files.

Validates against the JSON schema and checks tier constraints.

Per FMWK-PKG-001: Package Standard v1.0

Usage:
    python3 scripts/validate_package_manifest.py --manifest packages/PKG-T0-001/manifest.json
    python3 scripts/validate_package_manifest.py --all
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Add repo root for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "HOT"))

from kernel.paths import CONTROL_PLANE

PACKAGES_DIR = CONTROL_PLANE / "packages"
SCHEMA_PATH = CONTROL_PLANE / "schemas" / "package_manifest.json"

# Tier ordering
TIER_ORDER = {"G0": 0, "T0": 1, "T1": 2, "T2": 3, "T3": 4}

# Required fields per schema
REQUIRED_FIELDS = ["schema_version", "id", "name", "version", "tier", "artifact_paths", "deps"]


def load_schema() -> Optional[Dict[str, Any]]:
    """Load JSON Schema for validation."""
    if not SCHEMA_PATH.exists():
        return None
    try:
        with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def load_manifest(manifest_path: Path) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Load manifest.json file.

    Returns:
        Tuple of (manifest dict, error message)
    """
    if not manifest_path.exists():
        return None, f"File not found: {manifest_path}"

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        return manifest, None
    except json.JSONDecodeError as e:
        return None, f"Invalid JSON: {e}"
    except IOError as e:
        return None, f"Read error: {e}"


def validate_required_fields(manifest: Dict[str, Any]) -> List[str]:
    """Validate required fields are present."""
    errors = []
    for field in REQUIRED_FIELDS:
        if field not in manifest:
            errors.append(f"Missing required field: {field}")
    return errors


def validate_schema_version(manifest: Dict[str, Any]) -> List[str]:
    """Validate schema_version is 1.0."""
    errors = []
    version = manifest.get("schema_version")
    if version != "1.0":
        errors.append(f"Invalid schema_version: {version} (expected '1.0')")
    return errors


def validate_id_format(manifest: Dict[str, Any]) -> List[str]:
    """Validate package ID format."""
    errors = []
    pkg_id = manifest.get("id", "")

    if not pkg_id:
        return errors  # Already caught in required fields

    # Standard format: PKG-XX-NNN
    pattern = r"^PKG-(G0|T0|T1|T2|T3|CANARY)-[0-9]{3}$|^PKG-CANARY$"
    if not re.match(pattern, pkg_id):
        errors.append(f"Invalid package ID format: {pkg_id} (expected PKG-<TIER>-NNN)")

    return errors


def validate_tier(manifest: Dict[str, Any]) -> List[str]:
    """Validate tier field."""
    errors = []
    tier = manifest.get("tier", "")

    if not tier:
        return errors  # Already caught in required fields

    valid_tiers = ["G0", "T0", "T1", "T2", "T3"]
    if tier not in valid_tiers:
        errors.append(f"Invalid tier: {tier} (expected one of {valid_tiers})")

    return errors


def validate_version(manifest: Dict[str, Any]) -> List[str]:
    """Validate version is semver format."""
    errors = []
    version = manifest.get("version", "")

    if not version:
        return errors  # Already caught in required fields

    # Basic semver: MAJOR.MINOR.PATCH with optional prerelease/build
    pattern = r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:[-+].*)?$"
    if not re.match(pattern, version):
        errors.append(f"Invalid version format: {version} (expected semver)")

    return errors


def validate_tier_dependencies(manifest: Dict[str, Any]) -> List[str]:
    """Validate tier dependency constraints (I1-TIER)."""
    errors = []

    tier = manifest.get("tier", "")
    deps = manifest.get("deps", [])

    if not tier or tier not in TIER_ORDER:
        return errors  # Already caught elsewhere

    pkg_order = TIER_ORDER[tier]

    # I5-GENESIS-ZERO: Genesis packages have ZERO dependencies
    if tier == "G0" and deps:
        errors.append(f"I5-GENESIS-ZERO: Genesis (G0) packages cannot have dependencies: {deps}")
        return errors

    for dep_id in deps:
        if not isinstance(dep_id, str):
            errors.append(f"Invalid dependency (not a string): {dep_id}")
            continue

        # Extract tier from dependency ID
        match = re.match(r"^PKG-(G0|T0|T1|T2|T3)-", dep_id)
        if not match:
            # Unknown format - warn but don't fail
            continue

        dep_tier = match.group(1)
        dep_order = TIER_ORDER.get(dep_tier)

        if dep_order is not None and dep_order > pkg_order:
            errors.append(
                f"I1-TIER violation: {tier} cannot depend on {dep_tier} ({dep_id})"
            )

    return errors


def validate_artifact_paths(manifest: Dict[str, Any]) -> List[str]:
    """Validate artifact_paths field."""
    errors = []
    paths = manifest.get("artifact_paths", [])

    if not isinstance(paths, list):
        errors.append(f"artifact_paths must be an array, got {type(paths).__name__}")
        return errors

    if len(paths) == 0:
        errors.append("artifact_paths cannot be empty")

    for i, path in enumerate(paths):
        if not isinstance(path, str):
            errors.append(f"artifact_paths[{i}]: must be string, got {type(path).__name__}")
        elif not path:
            errors.append(f"artifact_paths[{i}]: cannot be empty")

    return errors


def validate_manifest(manifest_path: Path, strict: bool = False) -> Tuple[bool, List[str], List[str]]:
    """Validate a manifest file.

    Args:
        manifest_path: Path to manifest.json
        strict: Treat warnings as errors

    Returns:
        Tuple of (valid, errors, warnings)
    """
    errors = []
    warnings = []

    # Load manifest
    manifest, load_error = load_manifest(manifest_path)
    if load_error:
        return False, [load_error], []

    # Run validations
    errors.extend(validate_required_fields(manifest))
    errors.extend(validate_schema_version(manifest))
    errors.extend(validate_id_format(manifest))
    errors.extend(validate_tier(manifest))
    errors.extend(validate_version(manifest))
    errors.extend(validate_tier_dependencies(manifest))
    errors.extend(validate_artifact_paths(manifest))

    # Optional field warnings
    if not manifest.get("description"):
        warnings.append("Missing description (recommended)")
    if not manifest.get("author"):
        warnings.append("Missing author (recommended)")
    if not manifest.get("license"):
        warnings.append("Missing license (recommended)")

    if strict:
        errors.extend(warnings)
        warnings = []

    return len(errors) == 0, errors, warnings


def validate_all_manifests(strict: bool = False) -> Tuple[int, int, int]:
    """Validate all manifests in packages/ directory.

    Returns:
        Tuple of (passed, failed, skipped)
    """
    passed = 0
    failed = 0
    skipped = 0

    if not PACKAGES_DIR.exists():
        print(f"Packages directory not found: {PACKAGES_DIR}")
        return 0, 0, 0

    for pkg_dir in sorted(PACKAGES_DIR.iterdir()):
        if not pkg_dir.is_dir():
            continue

        manifest_path = pkg_dir / "manifest.json"
        if not manifest_path.exists():
            print(f"  SKIP: {pkg_dir.name} (no manifest.json)")
            skipped += 1
            continue

        valid, errors, warnings = validate_manifest(manifest_path, strict)

        if valid:
            print(f"  PASS: {pkg_dir.name}")
            passed += 1
        else:
            print(f"  FAIL: {pkg_dir.name}")
            for err in errors:
                print(f"    ERROR: {err}")
            failed += 1

        for warn in warnings:
            print(f"    WARN: {warn}")

    return passed, failed, skipped


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Validate package manifest.json files (FMWK-PKG-001)"
    )
    parser.add_argument(
        "--manifest",
        help="Path to specific manifest.json to validate"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Validate all manifests in packages/"
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as errors"
    )

    args = parser.parse_args()

    if args.manifest:
        manifest_path = Path(args.manifest)
        if not manifest_path.is_absolute():
            manifest_path = CONTROL_PLANE / manifest_path

        print(f"Validating: {manifest_path}")
        valid, errors, warnings = validate_manifest(manifest_path, args.strict)

        if errors:
            print("\nErrors:")
            for err in errors:
                print(f"  - {err}")

        if warnings:
            print("\nWarnings:")
            for warn in warnings:
                print(f"  - {warn}")

        print()
        if valid:
            print("PASS: Manifest is valid")
            return 0
        else:
            print("FAIL: Manifest has errors")
            return 1

    elif args.all:
        print(f"Validating all manifests in: {PACKAGES_DIR}")
        print()

        passed, failed, skipped = validate_all_manifests(args.strict)

        print()
        print(f"Summary: {passed} passed, {failed} failed, {skipped} skipped")

        if failed > 0:
            print("\nFAIL: Some manifests have errors")
            return 1
        else:
            print("\nOK: All manifests valid")
            return 0

    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
