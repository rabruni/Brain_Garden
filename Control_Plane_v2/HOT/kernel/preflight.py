#!/usr/bin/env python3
"""
lib/preflight.py - Package preflight validation for Control Plane v2.

Provides unified validation checks that are shared between:
- scripts/package_install.py (install-time validation)
- scripts/pkgutil.py preflight (pre-install validation)

This ensures preflight checks are IDENTICAL to install-time validation.

BINDING CONSTRAINTS:
- Hash format: sha256:<64hex> everywhere
- No last-write-wins: ownership conflicts = FAIL
- Fail-closed on all gate checks
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kernel.paths import CONTROL_PLANE


@dataclass
class PreflightResult:
    """Unified result from validation checks.

    Attributes:
        gate: Gate identifier (G0A, G1, OWN, G5, LOAD)
        passed: True if validation passed
        message: Human-readable summary
        errors: List of specific error messages
        warnings: List of non-fatal warnings
    """
    gate: str
    passed: bool
    message: str
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "gate": self.gate,
            "passed": self.passed,
            "message": self.message,
            "errors": self.errors,
            "warnings": self.warnings,
        }

    def __str__(self) -> str:
        """Human-readable string representation."""
        status = "PASS" if self.passed else "FAIL"
        result = f"{self.gate}: {status} - {self.message}"
        if self.errors:
            result += "\n  Errors:\n    " + "\n    ".join(self.errors[:10])
            if len(self.errors) > 10:
                result += f"\n    ... and {len(self.errors) - 10} more"
        if self.warnings:
            result += "\n  Warnings:\n    " + "\n    ".join(self.warnings[:5])
        return result


from kernel.hashing import compute_sha256  # canonical implementation; re-exported for backward compat


def load_file_ownership(plane_root: Optional[Path] = None) -> Dict[str, dict]:
    """Load file ownership registry as dict keyed by file_path.

    Args:
        plane_root: Plane root path (defaults to CONTROL_PLANE)

    Returns:
        Dict mapping file_path to ownership row dict
    """
    root = plane_root or CONTROL_PLANE
    ownership_csv = root / "registries" / "file_ownership.csv"

    if not ownership_csv.exists():
        return {}

    ownership = {}
    with open(ownership_csv, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            file_path = row.get('file_path', '').strip()
            if file_path:
                ownership[file_path] = row
    return ownership


class PackageDeclarationValidator:
    """G0A: PACKAGE DECLARATION - Verify package is internally consistent.

    Checks:
    1. Every file in workspace is declared in manifest.assets[]
    2. Every declared asset hash matches workspace file hash
    3. No path escapes (no "..", no absolute paths)
    4. Hash format is valid: sha256:<64hex>
    """

    def validate(
        self,
        manifest: dict,
        workspace_files: Dict[str, Path]
    ) -> PreflightResult:
        """Validate package declaration consistency.

        Args:
            manifest: Package manifest dict
            workspace_files: Dict mapping relative paths to workspace file paths

        Returns:
            PreflightResult with validation outcome
        """
        errors = []
        warnings = []

        assets = manifest.get('assets', [])
        assets_by_path = {a['path']: a for a in assets}

        # Check all workspace files are declared
        for rel_path, workspace_path in workspace_files.items():
            if rel_path not in assets_by_path:
                errors.append(f"UNDECLARED: '{rel_path}' in package but not in manifest")
                continue

            # Check hash
            asset = assets_by_path[rel_path]
            expected_hash = asset.get('sha256', '')
            actual_hash = compute_sha256(workspace_path)

            if expected_hash != actual_hash:
                errors.append(
                    f"HASH_MISMATCH: '{rel_path}' - "
                    f"expected {expected_hash[:20]}..., got {actual_hash[:20]}..."
                )

        # Check for path escapes and hash format in manifest
        path_errors, format_errors = self.check_path_escapes(assets)
        errors.extend(path_errors)

        hash_errors, hash_warnings = self.check_hash_format(assets)
        errors.extend(hash_errors)
        warnings.extend(hash_warnings)

        passed = len(errors) == 0
        message = f"{len(assets)} assets validated" if passed else f"{len(errors)} validation errors"

        return PreflightResult(
            gate="G0A",
            passed=passed,
            message=message,
            errors=errors,
            warnings=warnings,
        )

    @staticmethod
    def check_path_escapes(assets: List[dict]) -> Tuple[List[str], List[str]]:
        """Check for path escape attempts in asset paths.

        Returns:
            Tuple of (errors, warnings)
        """
        errors = []
        warnings = []

        for asset in assets:
            path = asset.get('path', '')
            if '..' in path:
                errors.append(f"PATH_ESCAPE: '{path}' contains '..'")
            if path.startswith('/'):
                errors.append(f"PATH_ESCAPE: '{path}' is absolute path")
            if path.startswith('./'):
                warnings.append(f"PATH_FORMAT: '{path}' has unnecessary './' prefix")

        return errors, warnings

    @staticmethod
    def check_hash_format(assets: List[dict]) -> Tuple[List[str], List[str]]:
        """Check hash format compliance.

        Returns:
            Tuple of (errors, warnings)
        """
        errors = []
        warnings = []

        for asset in assets:
            path = asset.get('path', '')
            sha = asset.get('sha256', '')

            if not sha:
                errors.append(f"HASH_MISSING: '{path}' has no sha256 hash")
            elif not sha.startswith('sha256:'):
                errors.append(f"HASH_FORMAT: '{path}' hash not in sha256:<hex> format")
            elif len(sha) != 71:  # "sha256:" (7) + 64 hex
                errors.append(f"HASH_FORMAT: '{path}' hash has wrong length ({len(sha)} != 71)")

        return errors, warnings


class ChainValidator:
    """G1: CHAIN - Verify governance chain integrity.

    Enforces:
    1. Package MUST have spec_id (registered in specs_registry)
    2. Spec MUST have framework_id (registered in frameworks_registry)
    3. Package framework_id (if set) MUST match spec's framework_id
    4. Spec pack MUST exist with manifest.yaml
    5. Package assets SHOULD be subset of spec's declared assets
    6. Package dependencies MUST be valid package IDs
    """

    def __init__(self, plane_root: Optional[Path] = None, strict: bool = True):
        """Initialize chain validator.

        Args:
            plane_root: Plane root path (defaults to CONTROL_PLANE)
            strict: If True, require spec_id and framework chain (default: True)
        """
        self.plane_root = plane_root or CONTROL_PLANE
        self.strict = strict

    def validate(self, manifest: dict) -> PreflightResult:
        """Validate governance chain.

        Args:
            manifest: Package manifest dict

        Returns:
            PreflightResult with validation outcome
        """
        errors = []
        warnings = []

        package_id = manifest.get('package_id', 'UNKNOWN')
        spec_id = manifest.get('spec_id')
        framework_id = manifest.get('framework_id')

        # 1. Check spec_id is present and registered
        if not spec_id:
            if self.strict:
                errors.append("SPEC_MISSING: Package must have 'spec_id' field")
            else:
                warnings.append("SPEC_MISSING: Package has no 'spec_id' - governance chain incomplete")
        elif not self._spec_exists(spec_id):
            errors.append(f"SPEC_NOT_FOUND: '{spec_id}' not in specs_registry.csv")
            errors.append(f"  Register first: pkgutil register-spec {spec_id}")
        else:
            # 2. Get spec's framework and verify chain
            spec_framework = self._get_spec_framework(spec_id)
            if spec_framework:
                # 3. If package has framework_id, it must match spec's
                if framework_id and framework_id != spec_framework:
                    errors.append(
                        f"FRAMEWORK_MISMATCH: Package framework_id '{framework_id}' "
                        f"doesn't match spec's framework '{spec_framework}'"
                    )
                elif not framework_id:
                    # Auto-derive from spec (warning only)
                    warnings.append(
                        f"FRAMEWORK_DERIVED: Using framework '{spec_framework}' from spec"
                    )

                # Verify framework is registered
                if not self._framework_exists(spec_framework):
                    errors.append(f"FRAMEWORK_NOT_FOUND: '{spec_framework}' not in frameworks_registry.csv")

            # 4. Check spec pack exists with manifest.yaml
            spec_pack_path = self.plane_root / "specs" / spec_id / "manifest.yaml"
            if not spec_pack_path.exists():
                warnings.append(
                    f"SPEC_PACK_MISSING: No manifest.yaml at specs/{spec_id}/"
                )
            else:
                # 5. Verify package assets are declared in spec
                self._check_assets_in_spec(manifest, spec_id, errors, warnings)

        # Check framework_id if provided but no spec
        if framework_id and not spec_id:
            if not self._framework_exists(framework_id):
                errors.append(f"FRAMEWORK_NOT_FOUND: '{framework_id}' not in frameworks_registry.csv")

        # 6. Check deps field (package dependencies)
        deps = manifest.get('deps', []) or manifest.get('dependencies', [])
        for dep in deps:
            if isinstance(dep, str):
                if not dep.startswith('PKG-'):
                    errors.append(f"INVALID_DEP: '{dep}' is not a valid package ID (must start with PKG-)")
            elif isinstance(dep, dict):
                dep_id = dep.get('package_id', '')
                if dep_id and not dep_id.startswith('PKG-'):
                    errors.append(f"INVALID_DEP: '{dep_id}' is not a valid package ID")

        passed = len(errors) == 0
        message = "Dependency chain valid" if passed else f"{len(errors)} chain errors"

        return PreflightResult(
            gate="G1",
            passed=passed,
            message=message,
            errors=errors,
            warnings=warnings,
        )

    def _framework_exists(self, framework_id: str) -> bool:
        """Check if framework exists in registry."""
        from kernel.registry import framework_exists
        return framework_exists(framework_id, registries_dir=self.plane_root / "registries")

    def _spec_exists(self, spec_id: str) -> bool:
        """Check if spec exists in registry."""
        from kernel.registry import spec_exists
        return spec_exists(spec_id, registries_dir=self.plane_root / "registries")

    def _get_spec_framework(self, spec_id: str) -> Optional[str]:
        """Get framework_id for a spec from registry."""
        from kernel.registry import get_spec_framework
        return get_spec_framework(spec_id, registries_dir=self.plane_root / "registries")

    def _check_assets_in_spec(self, manifest: dict, spec_id: str,
                              errors: List[str], warnings: List[str]) -> None:
        """Verify package assets are declared in spec's manifest.yaml."""
        spec_manifest_path = self.plane_root / "specs" / spec_id / "manifest.yaml"
        if not spec_manifest_path.exists():
            return

        # Parse spec manifest
        try:
            spec_content = spec_manifest_path.read_text()
            spec_assets = self._parse_spec_assets(spec_content)
        except Exception:
            warnings.append(f"SPEC_PARSE_ERROR: Could not parse specs/{spec_id}/manifest.yaml")
            return

        if not spec_assets:
            warnings.append(f"SPEC_NO_ASSETS: Spec {spec_id} has no declared assets")
            return

        # Check each package asset is in spec
        package_assets = manifest.get('assets', [])
        for asset in package_assets:
            path = asset.get('path', '')
            if path and path not in spec_assets:
                warnings.append(
                    f"ASSET_NOT_IN_SPEC: '{path}' not declared in spec {spec_id}"
                )

    def _parse_spec_assets(self, content: str) -> set:
        """Parse assets from spec manifest.yaml content."""
        assets = set()
        in_assets = False

        for line in content.split('\n'):
            stripped = line.strip()

            # Detect assets section
            if stripped == 'assets:':
                in_assets = True
                continue

            # Exit assets section on new top-level key
            if in_assets and stripped and not stripped.startswith('-') and ':' in stripped:
                in_assets = False
                continue

            # Collect asset paths
            if in_assets and stripped.startswith('- '):
                asset_path = stripped[2:].strip()
                if asset_path:
                    assets.add(asset_path)

        return assets


class OwnershipValidator:
    """Check for ownership conflicts.

    A conflict occurs if a file is owned by a different package.
    Same package reinstalling = ok (idempotent).
    No last-write-wins allowed.
    """

    def validate(
        self,
        manifest: dict,
        existing_ownership: Dict[str, dict],
        package_id: str,
        plane_root: Optional[Path] = None,
    ) -> PreflightResult:
        """Check for file ownership conflicts.

        Dependency-aware: if the current owner of a file is listed in the
        installing package's ``dependencies`` (or ``deps``) list, the conflict
        is treated as an ownership *transfer* (warning) rather than a hard
        failure.  Non-dependency conflicts remain hard errors.

        Only direct (non-transitive) dependencies are considered.

        Args:
            manifest: Package manifest dict
            existing_ownership: Current ownership registry as dict
            package_id: ID of package being installed
            plane_root: Plane root path (unused currently, reserved)

        Returns:
            PreflightResult with validation outcome
        """
        errors = []
        warnings = []

        declared_deps = manifest.get('dependencies', []) or manifest.get('deps', [])
        if not isinstance(declared_deps, list):
            declared_deps = []

        assets = manifest.get('assets', [])

        for asset in assets:
            path = asset['path']
            if path in existing_ownership:
                owner = existing_ownership[path].get('owner_package_id', '')
                if owner and owner != package_id:
                    if owner in declared_deps:
                        warnings.append(
                            f"OWNERSHIP_TRANSFER: '{path}' from '{owner}' to '{package_id}' (declared dependency)"
                        )
                    else:
                        errors.append(
                            f"OWNERSHIP_CONFLICT: '{path}' owned by '{owner}', "
                            f"cannot assign to '{package_id}' (not in dependencies)"
                        )

        passed = len(errors) == 0
        transfer_count = sum(1 for w in warnings if 'TRANSFER' in w)
        message = (f"{transfer_count} ownership transfers"
                   if passed and transfer_count else
                   "No ownership conflicts" if passed else
                   f"{len(errors)} conflicts found")

        return PreflightResult(
            gate="OWN",
            passed=passed,
            message=message,
            errors=errors,
            warnings=warnings,
        )


class SignatureValidator:
    """G5: SIGNATURE - Verify package signature policy.

    Checks:
    1. Package has signature file (if required)
    2. Signature is valid (if present)
    """

    def validate(
        self,
        archive_path: Optional[Path],
        manifest: dict,
        allow_unsigned: bool = False
    ) -> PreflightResult:
        """Validate signature policy.

        Args:
            archive_path: Path to package archive (for signature check)
            manifest: Package manifest dict
            allow_unsigned: Whether to allow unsigned packages (via env var)

        Returns:
            PreflightResult with validation outcome
        """
        errors = []
        warnings = []

        # Check if archive has signature
        has_sig = False
        if archive_path and archive_path.exists():
            sig_path = archive_path.with_suffix('.tar.gz.sig')
            has_sig = sig_path.exists()

            # Also check for signature.json inside archive
            # (deferred - would need to extract)

        if has_sig:
            # TODO: Verify signature
            # For now, just note that signature exists
            warnings.append("Signature verification not yet implemented")
        else:
            if allow_unsigned:
                warnings.append("SIGNATURE_WAIVED: Package is unsigned (allowed by policy)")
            else:
                errors.append("SIGNATURE_MISSING: Package is not signed")

        passed = len(errors) == 0
        if passed and not has_sig:
            message = "Signature waived" if allow_unsigned else "Signature policy satisfied"
        elif passed and has_sig:
            message = "Signature present"
        else:
            message = f"{len(errors)} signature errors"

        return PreflightResult(
            gate="G5",
            passed=passed,
            message=message,
            errors=errors,
            warnings=warnings,
        )


class ManifestValidator:
    """Validate manifest structure and required fields."""

    REQUIRED_FIELDS = ['package_id', 'assets']

    def validate(self, manifest: dict, package_id: str) -> PreflightResult:
        """Validate manifest structure.

        Args:
            manifest: Package manifest dict
            package_id: Expected package ID

        Returns:
            PreflightResult with validation outcome
        """
        errors = []
        warnings = []

        # Check required fields
        for field in self.REQUIRED_FIELDS:
            if field not in manifest:
                errors.append(f"MANIFEST_FIELD_MISSING: '{field}' is required")

        # Check package_id matches
        manifest_id = manifest.get('package_id', '')
        if manifest_id and manifest_id != package_id:
            errors.append(
                f"MANIFEST_ID_MISMATCH: manifest says '{manifest_id}' "
                f"but expected '{package_id}'"
            )

        # Check schema_version
        schema_version = manifest.get('schema_version', '1.0')
        if schema_version not in ('1.0', '1.1', '1.2'):
            warnings.append(f"MANIFEST_SCHEMA: Unknown schema version '{schema_version}'")

        # Check assets is a list
        assets = manifest.get('assets', [])
        if not isinstance(assets, list):
            errors.append("MANIFEST_ASSETS_FORMAT: 'assets' must be a list")

        passed = len(errors) == 0
        message = "Manifest structure valid" if passed else f"{len(errors)} manifest errors"

        return PreflightResult(
            gate="MANIFEST",
            passed=passed,
            message=message,
            errors=errors,
            warnings=warnings,
        )


class PreflightValidator:
    """Master validator running all preflight checks.

    Orchestrates:
    - MANIFEST: Structure validation
    - G0A: Package declaration
    - G1: Dependency chain
    - OWN: Ownership conflicts
    - G5: Signature policy
    """

    def __init__(self, plane_root: Optional[Path] = None, strict: bool = True):
        """Initialize preflight validator.

        Args:
            plane_root: Plane root path (defaults to CONTROL_PLANE)
            strict: If True, require spec_id and full governance chain (default: True)
                   Set to False for isolated testing without registries.
        """
        self.plane_root = plane_root or CONTROL_PLANE
        self.strict = strict
        self.manifest_validator = ManifestValidator()
        self.g0a = PackageDeclarationValidator()
        self.g1 = ChainValidator(plane_root, strict=strict)
        self.ownership = OwnershipValidator()
        self.g5 = SignatureValidator()

    def run_all(
        self,
        manifest: dict,
        workspace_files: Dict[str, Path],
        package_id: str,
        existing_ownership: Optional[Dict[str, dict]] = None,
        archive_path: Optional[Path] = None,
        allow_unsigned: bool = False,
    ) -> List[PreflightResult]:
        """Run all preflight checks.

        Args:
            manifest: Package manifest dict
            workspace_files: Dict mapping relative paths to workspace file paths
            package_id: Package ID being validated
            existing_ownership: Current ownership registry (loaded if not provided)
            archive_path: Path to archive (for signature check)
            allow_unsigned: Whether to allow unsigned packages

        Returns:
            List of PreflightResult for each check
        """
        results = []

        # Load ownership if not provided
        if existing_ownership is None:
            existing_ownership = load_file_ownership(self.plane_root)

        # 0. Schema validation (lightweight, no jsonschema dependency)
        from kernel.schema_validator import validate_manifest
        schema_valid, schema_errors = validate_manifest(manifest)
        schema_result = PreflightResult(
            gate="SCHEMA",
            passed=schema_valid,
            message="Schema valid" if schema_valid else f"{len(schema_errors)} schema errors",
            errors=schema_errors,
        )
        results.append(schema_result)

        # 1. Manifest structure validation
        manifest_result = self.manifest_validator.validate(manifest, package_id)
        results.append(manifest_result)

        # Stop early if manifest is invalid
        if not manifest_result.passed:
            return results

        # 2. G0A: Package declaration
        g0a_result = self.g0a.validate(manifest, workspace_files)
        results.append(g0a_result)

        # 3. G1: Chain validation
        g1_result = self.g1.validate(manifest)
        results.append(g1_result)

        # 4. Ownership check
        own_result = self.ownership.validate(manifest, existing_ownership, package_id, self.plane_root)
        results.append(own_result)

        # 5. G5: Signature policy
        g5_result = self.g5.validate(archive_path, manifest, allow_unsigned)
        results.append(g5_result)

        return results

    def run_quick(
        self,
        manifest: dict,
        package_id: str,
    ) -> List[PreflightResult]:
        """Run quick checks that don't require workspace files.

        Useful for validating manifest before extraction.

        Args:
            manifest: Package manifest dict
            package_id: Package ID being validated

        Returns:
            List of PreflightResult for quick checks
        """
        results = []

        # 1. Manifest structure validation
        manifest_result = self.manifest_validator.validate(manifest, package_id)
        results.append(manifest_result)

        if not manifest_result.passed:
            return results

        # 2. G1: Chain validation (doesn't need files)
        g1_result = self.g1.validate(manifest)
        results.append(g1_result)

        # 3. Path escape check (from manifest only)
        assets = manifest.get('assets', [])
        path_errors, path_warnings = self.g0a.check_path_escapes(assets)
        hash_errors, hash_warnings = self.g0a.check_hash_format(assets)

        quick_g0a = PreflightResult(
            gate="G0A-QUICK",
            passed=len(path_errors) == 0 and len(hash_errors) == 0,
            message="Quick G0A checks" if not path_errors and not hash_errors else "Path/hash format issues",
            errors=path_errors + hash_errors,
            warnings=path_warnings + hash_warnings,
        )
        results.append(quick_g0a)

        return results

    def format_results(
        self,
        results: List[PreflightResult],
        package_id: str,
        verbose: bool = True
    ) -> str:
        """Format results for human-readable output.

        Args:
            results: List of PreflightResult
            package_id: Package ID
            verbose: Include detailed error messages

        Returns:
            Formatted string output
        """
        lines = [
            f"PREFLIGHT: {package_id}",
            "─" * 40,
        ]

        all_passed = True
        for result in results:
            status = "PASS" if result.passed else "FAIL"
            status_indicator = "✓" if result.passed else "✗"
            if not result.passed:
                all_passed = False

            # Format gate name with padding
            gate_padded = f"{result.gate}".ljust(8)
            msg_padded = result.message.ljust(30)
            lines.append(f"{gate_padded} {msg_padded} {status_indicator} {status}")

            if verbose and result.errors:
                for error in result.errors[:5]:
                    lines.append(f"         └─ {error}")
                if len(result.errors) > 5:
                    lines.append(f"         └─ ... and {len(result.errors) - 5} more errors")

        lines.append("")
        final_status = "PASS" if all_passed else "FAIL"
        final_msg = "Ready for install" if all_passed else "Validation failed"
        lines.append(f"RESULT: {final_status} - {final_msg}")

        return "\n".join(lines)

    def to_json(self, results: List[PreflightResult], package_id: str) -> str:
        """Convert results to JSON format.

        Args:
            results: List of PreflightResult
            package_id: Package ID

        Returns:
            JSON string
        """
        all_passed = all(r.passed for r in results)
        output = {
            "package_id": package_id,
            "passed": all_passed,
            "results": [r.to_dict() for r in results],
        }
        return json.dumps(output, indent=2)
