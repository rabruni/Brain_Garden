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

from lib.paths import CONTROL_PLANE


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


def compute_sha256(file_path: Path) -> str:
    """Compute SHA256 hash in standard format: sha256:<64hex>"""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    return f"sha256:{hasher.hexdigest()}"


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
    """G1: CHAIN - Verify dependency chains exist.

    Checks:
    1. Package dependencies (deps field) reference valid packages
    2. Framework references exist in frameworks_registry
    3. Spec references exist in specs_registry
    """

    def __init__(self, plane_root: Optional[Path] = None):
        """Initialize chain validator.

        Args:
            plane_root: Plane root path (defaults to CONTROL_PLANE)
        """
        self.plane_root = plane_root or CONTROL_PLANE

    def validate(self, manifest: dict) -> PreflightResult:
        """Validate dependency chain.

        Args:
            manifest: Package manifest dict

        Returns:
            PreflightResult with validation outcome
        """
        errors = []
        warnings = []

        # Check deps field (package dependencies)
        deps = manifest.get('deps', []) or manifest.get('dependencies', [])
        for dep in deps:
            if isinstance(dep, str):
                if not dep.startswith('PKG-'):
                    errors.append(f"INVALID_DEP: '{dep}' is not a valid package ID")
                # TODO: Check if package exists in installed/
            elif isinstance(dep, dict):
                dep_id = dep.get('package_id', '')
                if dep_id and not dep_id.startswith('PKG-'):
                    errors.append(f"INVALID_DEP: '{dep_id}' is not a valid package ID")

        # Check framework_id reference
        framework_id = manifest.get('framework_id')
        if framework_id:
            if not self._framework_exists(framework_id):
                errors.append(f"FRAMEWORK_NOT_FOUND: '{framework_id}' not in frameworks_registry")

        # Check spec_id reference
        spec_id = manifest.get('spec_id')
        if spec_id:
            if not self._spec_exists(spec_id):
                errors.append(f"SPEC_NOT_FOUND: '{spec_id}' not in specs_registry")

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
        reg_path = self.plane_root / "registries" / "frameworks_registry.csv"
        if not reg_path.exists():
            return False

        with open(reg_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('framework_id') == framework_id:
                    return True
        return False

    def _spec_exists(self, spec_id: str) -> bool:
        """Check if spec exists in registry."""
        reg_path = self.plane_root / "registries" / "specs_registry.csv"
        if not reg_path.exists():
            return False

        with open(reg_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('spec_id') == spec_id:
                    return True
        return False


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
        package_id: str
    ) -> PreflightResult:
        """Check for file ownership conflicts.

        Args:
            manifest: Package manifest dict
            existing_ownership: Current ownership registry as dict
            package_id: ID of package being installed

        Returns:
            PreflightResult with validation outcome
        """
        errors = []
        warnings = []

        assets = manifest.get('assets', [])

        for asset in assets:
            path = asset['path']
            if path in existing_ownership:
                owner = existing_ownership[path].get('owner_package_id', '')
                if owner and owner != package_id:
                    errors.append(
                        f"OWNERSHIP_CONFLICT: '{path}' already owned by '{owner}', "
                        f"cannot assign to '{package_id}'"
                    )

        passed = len(errors) == 0
        message = "No ownership conflicts" if passed else f"{len(errors)} conflicts found"

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

    def __init__(self, plane_root: Optional[Path] = None):
        """Initialize preflight validator.

        Args:
            plane_root: Plane root path (defaults to CONTROL_PLANE)
        """
        self.plane_root = plane_root or CONTROL_PLANE
        self.manifest_validator = ManifestValidator()
        self.g0a = PackageDeclarationValidator()
        self.g1 = ChainValidator(plane_root)
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
        own_result = self.ownership.validate(manifest, existing_ownership, package_id)
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
