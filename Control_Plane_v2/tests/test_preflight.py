#!/usr/bin/env python3
"""
Tests for lib/preflight.py - Package preflight validation.

Tests failure modes:
- Undeclared file in archive → G0A FAIL
- Hash mismatch → G0A FAIL
- Path escape (../) → G0A FAIL
- Missing dependency → G1 FAIL
- Ownership conflict → OWN FAIL
- Invalid framework ref → G1 FAIL
- Unsigned without waiver → G5 FAIL
- Invalid manifest JSON → MANIFEST FAIL
"""
import json
import pytest
import tempfile
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.preflight import (
    PreflightValidator,
    PreflightResult,
    PackageDeclarationValidator,
    ChainValidator,
    OwnershipValidator,
    SignatureValidator,
    ManifestValidator,
    compute_sha256,
    load_file_ownership,
)


class TestPreflightResult:
    """Test PreflightResult dataclass."""

    def test_passed_result(self):
        """Test creating a passed result."""
        result = PreflightResult(
            gate="G0A",
            passed=True,
            message="All checks passed",
        )
        assert result.passed
        assert result.gate == "G0A"
        assert len(result.errors) == 0

    def test_failed_result(self):
        """Test creating a failed result."""
        result = PreflightResult(
            gate="G0A",
            passed=False,
            message="Validation failed",
            errors=["Error 1", "Error 2"],
        )
        assert not result.passed
        assert len(result.errors) == 2

    def test_to_dict(self):
        """Test JSON serialization."""
        result = PreflightResult(
            gate="G1",
            passed=True,
            message="OK",
            warnings=["Warning 1"],
        )
        d = result.to_dict()
        assert d["gate"] == "G1"
        assert d["passed"] is True
        assert len(d["warnings"]) == 1


class TestPackageDeclarationValidator:
    """Test G0A: Package Declaration validation."""

    def test_valid_package(self, tmp_path):
        """Test validation of a valid package."""
        # Create test file
        test_file = tmp_path / "lib" / "test.py"
        test_file.parent.mkdir(parents=True)
        test_file.write_text("# Test file")

        file_hash = compute_sha256(test_file)

        manifest = {
            "package_id": "PKG-TEST-001",
            "assets": [
                {"path": "lib/test.py", "sha256": file_hash, "classification": "library"}
            ]
        }

        workspace_files = {"lib/test.py": test_file}

        validator = PackageDeclarationValidator()
        result = validator.validate(manifest, workspace_files)

        assert result.passed
        assert result.gate == "G0A"

    def test_undeclared_file(self, tmp_path):
        """Test G0A fails when file in package not in manifest."""
        # Create test files
        test_file = tmp_path / "lib" / "test.py"
        test_file.parent.mkdir(parents=True)
        test_file.write_text("# Test file")

        extra_file = tmp_path / "lib" / "extra.py"
        extra_file.write_text("# Extra file not in manifest")

        file_hash = compute_sha256(test_file)

        manifest = {
            "package_id": "PKG-TEST-001",
            "assets": [
                {"path": "lib/test.py", "sha256": file_hash, "classification": "library"}
            ]
        }

        # Include extra file in workspace but not manifest
        workspace_files = {
            "lib/test.py": test_file,
            "lib/extra.py": extra_file,
        }

        validator = PackageDeclarationValidator()
        result = validator.validate(manifest, workspace_files)

        assert not result.passed
        assert any("UNDECLARED" in e for e in result.errors)

    def test_hash_mismatch(self, tmp_path):
        """Test G0A fails when hash doesn't match."""
        test_file = tmp_path / "lib" / "test.py"
        test_file.parent.mkdir(parents=True)
        test_file.write_text("# Test file - modified")

        # Wrong hash
        manifest = {
            "package_id": "PKG-TEST-001",
            "assets": [
                {"path": "lib/test.py", "sha256": "sha256:0000000000000000000000000000000000000000000000000000000000000000", "classification": "library"}
            ]
        }

        workspace_files = {"lib/test.py": test_file}

        validator = PackageDeclarationValidator()
        result = validator.validate(manifest, workspace_files)

        assert not result.passed
        assert any("HASH_MISMATCH" in e for e in result.errors)

    def test_path_escape(self):
        """Test G0A fails when path contains '..'."""
        manifest = {
            "package_id": "PKG-TEST-001",
            "assets": [
                {"path": "../etc/passwd", "sha256": "sha256:abcd1234" + "0" * 56, "classification": "other"}
            ]
        }

        validator = PackageDeclarationValidator()
        errors, warnings = validator.check_path_escapes(manifest["assets"])

        assert len(errors) > 0
        assert any("PATH_ESCAPE" in e for e in errors)

    def test_absolute_path_escape(self):
        """Test G0A fails when path is absolute."""
        manifest = {
            "package_id": "PKG-TEST-001",
            "assets": [
                {"path": "/etc/passwd", "sha256": "sha256:abcd1234" + "0" * 56, "classification": "other"}
            ]
        }

        validator = PackageDeclarationValidator()
        errors, warnings = validator.check_path_escapes(manifest["assets"])

        assert len(errors) > 0
        assert any("PATH_ESCAPE" in e and "absolute" in e for e in errors)

    def test_invalid_hash_format(self):
        """Test G0A fails when hash format is wrong."""
        manifest = {
            "package_id": "PKG-TEST-001",
            "assets": [
                {"path": "lib/test.py", "sha256": "md5:abcd1234", "classification": "library"},
                {"path": "lib/test2.py", "sha256": "sha256:tooshort", "classification": "library"},
            ]
        }

        validator = PackageDeclarationValidator()
        errors, warnings = validator.check_hash_format(manifest["assets"])

        assert len(errors) >= 2


class TestChainValidator:
    """Test G1: Chain validation."""

    def test_valid_chain(self, tmp_path):
        """Test valid dependency chain."""
        # Create mock registries
        reg_dir = tmp_path / "registries"
        reg_dir.mkdir()

        frameworks_reg = reg_dir / "frameworks_registry.csv"
        frameworks_reg.write_text("framework_id,title,status\nFMWK-100,Test Framework,active\n")

        specs_reg = reg_dir / "specs_registry.csv"
        specs_reg.write_text("spec_id,framework_id,status\nSPEC-TEST-001,FMWK-100,active\n")

        manifest = {
            "package_id": "PKG-TEST-001",
            "framework_id": "FMWK-100",
            "spec_id": "SPEC-TEST-001",
            "deps": [],
        }

        validator = ChainValidator(tmp_path)
        result = validator.validate(manifest)

        assert result.passed
        assert result.gate == "G1"

    def test_missing_framework(self, tmp_path):
        """Test G1 fails when framework doesn't exist."""
        reg_dir = tmp_path / "registries"
        reg_dir.mkdir()

        frameworks_reg = reg_dir / "frameworks_registry.csv"
        frameworks_reg.write_text("framework_id,title,status\n")  # Empty registry

        manifest = {
            "package_id": "PKG-TEST-001",
            "framework_id": "FMWK-NONEXISTENT",
        }

        validator = ChainValidator(tmp_path)
        result = validator.validate(manifest)

        assert not result.passed
        assert any("FRAMEWORK_NOT_FOUND" in e for e in result.errors)

    def test_invalid_dependency_format(self):
        """Test G1 fails with invalid dependency format."""
        manifest = {
            "package_id": "PKG-TEST-001",
            "deps": ["invalid-dep", "another-bad-dep"],
        }

        validator = ChainValidator()
        result = validator.validate(manifest)

        assert not result.passed
        assert any("INVALID_DEP" in e for e in result.errors)


class TestOwnershipValidator:
    """Test ownership conflict detection."""

    def test_no_conflicts(self):
        """Test no ownership conflicts."""
        manifest = {
            "package_id": "PKG-NEW-001",
            "assets": [
                {"path": "lib/new.py"},
                {"path": "lib/other.py"},
            ]
        }

        existing = {
            "lib/existing.py": {"owner_package_id": "PKG-OLD-001"},
        }

        validator = OwnershipValidator()
        result = validator.validate(manifest, existing, "PKG-NEW-001")

        assert result.passed

    def test_ownership_conflict(self):
        """Test ownership conflict detected."""
        manifest = {
            "package_id": "PKG-NEW-001",
            "assets": [
                {"path": "lib/shared.py"},
            ]
        }

        existing = {
            "lib/shared.py": {"owner_package_id": "PKG-OLD-001"},
        }

        validator = OwnershipValidator()
        result = validator.validate(manifest, existing, "PKG-NEW-001")

        assert not result.passed
        assert any("OWNERSHIP_CONFLICT" in e for e in result.errors)

    def test_same_package_reinstall(self):
        """Test same package can reinstall (idempotent)."""
        manifest = {
            "package_id": "PKG-SAME-001",
            "assets": [
                {"path": "lib/same.py"},
            ]
        }

        existing = {
            "lib/same.py": {"owner_package_id": "PKG-SAME-001"},
        }

        validator = OwnershipValidator()
        result = validator.validate(manifest, existing, "PKG-SAME-001")

        assert result.passed


class TestSignatureValidator:
    """Test G5: Signature validation."""

    def test_unsigned_with_waiver(self):
        """Test unsigned package allowed with waiver."""
        manifest = {"package_id": "PKG-TEST-001"}

        validator = SignatureValidator()
        result = validator.validate(None, manifest, allow_unsigned=True)

        assert result.passed
        assert any("WAIVED" in w for w in result.warnings)

    def test_unsigned_without_waiver(self):
        """Test unsigned package fails without waiver."""
        manifest = {"package_id": "PKG-TEST-001"}

        validator = SignatureValidator()
        result = validator.validate(None, manifest, allow_unsigned=False)

        assert not result.passed
        assert any("SIGNATURE_MISSING" in e for e in result.errors)


class TestManifestValidator:
    """Test manifest structure validation."""

    def test_valid_manifest(self):
        """Test valid manifest passes."""
        manifest = {
            "package_id": "PKG-TEST-001",
            "assets": [],
        }

        validator = ManifestValidator()
        result = validator.validate(manifest, "PKG-TEST-001")

        assert result.passed

    def test_missing_package_id(self):
        """Test manifest fails without package_id."""
        manifest = {
            "assets": [],
        }

        validator = ManifestValidator()
        result = validator.validate(manifest, "PKG-TEST-001")

        assert not result.passed
        assert any("package_id" in e for e in result.errors)

    def test_package_id_mismatch(self):
        """Test manifest fails when IDs don't match."""
        manifest = {
            "package_id": "PKG-WRONG-001",
            "assets": [],
        }

        validator = ManifestValidator()
        result = validator.validate(manifest, "PKG-TEST-001")

        assert not result.passed
        assert any("MISMATCH" in e for e in result.errors)


class TestPreflightValidator:
    """Test integrated PreflightValidator."""

    def test_run_all_passes(self, tmp_path):
        """Test full preflight run with valid package."""
        # Setup
        reg_dir = tmp_path / "registries"
        reg_dir.mkdir()
        (reg_dir / "frameworks_registry.csv").write_text("framework_id,title,status\n")
        (reg_dir / "specs_registry.csv").write_text("spec_id,framework_id,status\n")

        test_file = tmp_path / "lib" / "test.py"
        test_file.parent.mkdir(parents=True)
        test_file.write_text("# Test")

        manifest = {
            "package_id": "PKG-TEST-001",
            "assets": [
                {"path": "lib/test.py", "sha256": compute_sha256(test_file), "classification": "library"}
            ],
        }

        workspace_files = {"lib/test.py": test_file}

        # Use strict=False for isolated testing without full registries
        validator = PreflightValidator(tmp_path, strict=False)
        results = validator.run_all(
            manifest=manifest,
            workspace_files=workspace_files,
            package_id="PKG-TEST-001",
            existing_ownership={},
            allow_unsigned=True,
        )

        # Should have results for MANIFEST, G0A, G1, OWN, G5
        assert len(results) >= 5
        assert all(r.passed for r in results)

    def test_format_results(self, tmp_path):
        """Test human-readable output formatting."""
        validator = PreflightValidator(tmp_path)
        results = [
            PreflightResult("MANIFEST", True, "OK"),
            PreflightResult("G0A", True, "10 assets validated"),
            PreflightResult("G1", False, "1 chain error", errors=["FRAMEWORK_NOT_FOUND: FMWK-999"]),
        ]

        output = validator.format_results(results, "PKG-TEST-001")

        assert "PKG-TEST-001" in output
        assert "PASS" in output
        assert "FAIL" in output
        assert "FRAMEWORK_NOT_FOUND" in output

    def test_to_json(self, tmp_path):
        """Test JSON output."""
        validator = PreflightValidator(tmp_path)
        results = [
            PreflightResult("G0A", True, "OK"),
        ]

        json_output = validator.to_json(results, "PKG-TEST-001")
        data = json.loads(json_output)

        assert data["package_id"] == "PKG-TEST-001"
        assert data["passed"] is True
        assert len(data["results"]) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
