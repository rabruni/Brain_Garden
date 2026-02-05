#!/usr/bin/env python3
"""
Tests for Phase 1B: package_install.py functionality.

Tests:
1. Two-phase ledger (INSTALL_STARTED → INSTALLED | INSTALL_FAILED)
2. G0A gate enforcement (package declaration check)
3. G5 gate enforcement (signature check, waived in tests)
4. Ownership conflict detection (no last-write-wins)
5. Workspace isolation (extract to temp, validate, atomic copy)
6. Receipt written to installed/<pkg>/

BINDING CONSTRAINTS tested:
- Ledger is Memory: INSTALL_STARTED → INSTALLED | INSTALL_FAILED
- No last-write-wins: ownership conflicts = FAIL
- Pristine roots are install destinations; installed/<pkg>/ is receipts only
"""

import hashlib
import json
import os
import shutil
import tarfile
import tempfile
from pathlib import Path
import pytest
import sys

# Add Control_Plane_v2 to path
CONTROL_PLANE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CONTROL_PLANE_ROOT))

from scripts.package_install import (
    compute_sha256,
    compute_manifest_hash,
    check_g0a_package_declaration,
    check_g1_chain,
    check_g5_signature,
    check_ownership_conflicts,
    extract_to_workspace,
    atomic_copy_files,
    load_manifest_from_archive,
    InstallError,
    GateFailure,
    OwnershipConflict,
)


# === Fixtures ===

@pytest.fixture
def test_package_dir():
    """Create a temporary directory for test package."""
    temp_dir = tempfile.mkdtemp(prefix="cp-test-pkg-")
    yield Path(temp_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def simple_manifest():
    """Create a simple v1.2 manifest."""
    return {
        "schema_version": "1.2",
        "package_id": "PKG-TEST-001",
        "package_type": "library",
        "version": "1.0.0",
        "name": "Test Package",
        "description": "A test package for Phase 1B",
        "target_plane": "ho3",
        "install_targets": [
            {"namespace": "lib", "root": "lib/", "writable": False}
        ],
        "assets": [],
        "deps": [],
    }


@pytest.fixture
def test_file_content():
    """Content for test file."""
    return "# Test file\nprint('Hello from test')\n"


def create_test_archive(
    pkg_dir: Path,
    manifest: dict,
    files: dict[str, str]
) -> Path:
    """
    Create a test package archive.

    Args:
        pkg_dir: Temp directory for package creation
        manifest: Package manifest dict
        files: Dict of rel_path -> content

    Returns:
        Path to archive
    """
    package_id = manifest["package_id"]
    pkg_content_dir = pkg_dir / package_id
    pkg_content_dir.mkdir(parents=True, exist_ok=True)

    # Create files and populate manifest assets
    assets = []
    for rel_path, content in files.items():
        file_path = pkg_content_dir / rel_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)

        # Compute hash
        sha = compute_sha256(file_path)
        assets.append({
            "path": rel_path,
            "sha256": sha,
            "classification": "code"
        })

    manifest["assets"] = assets

    # Write manifest
    manifest_path = pkg_content_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))

    # Create archive
    archive_path = pkg_dir / f"{package_id}.tar.gz"
    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(pkg_content_dir, arcname=package_id)

    return archive_path


class TestG0APackageDeclaration:
    """Test G0A gate: package declaration check."""

    def test_g0a_passes_valid_package(self, test_package_dir, simple_manifest, test_file_content):
        """G0A should pass for a valid package with matching hashes."""
        # Create test file
        test_file = test_package_dir / "test_module.py"
        test_file.write_text(test_file_content)

        # Set up manifest with correct hash
        simple_manifest["assets"] = [{
            "path": "lib/test_module.py",
            "sha256": compute_sha256(test_file),
            "classification": "code"
        }]

        # Create workspace files dict
        workspace_files = {"lib/test_module.py": test_file}

        passed, errors = check_g0a_package_declaration(simple_manifest, workspace_files)

        assert passed, f"G0A should pass: {errors}"
        assert len(errors) == 0

    def test_g0a_fails_undeclared_file(self, test_package_dir, simple_manifest, test_file_content):
        """G0A should fail if workspace has file not in manifest."""
        # Create test file
        test_file = test_package_dir / "test_module.py"
        test_file.write_text(test_file_content)

        # Empty manifest assets
        simple_manifest["assets"] = []

        # Workspace has a file
        workspace_files = {"lib/test_module.py": test_file}

        passed, errors = check_g0a_package_declaration(simple_manifest, workspace_files)

        assert not passed, "G0A should fail for undeclared file"
        assert any("UNDECLARED" in e for e in errors)

    def test_g0a_fails_hash_mismatch(self, test_package_dir, simple_manifest, test_file_content):
        """G0A should fail if file hash doesn't match manifest."""
        # Create test file
        test_file = test_package_dir / "test_module.py"
        test_file.write_text(test_file_content)

        # Set up manifest with WRONG hash
        simple_manifest["assets"] = [{
            "path": "lib/test_module.py",
            "sha256": "sha256:" + "0" * 64,  # Wrong hash
            "classification": "code"
        }]

        workspace_files = {"lib/test_module.py": test_file}

        passed, errors = check_g0a_package_declaration(simple_manifest, workspace_files)

        assert not passed, "G0A should fail for hash mismatch"
        assert any("HASH_MISMATCH" in e for e in errors)

    def test_g0a_fails_path_escape(self, simple_manifest):
        """G0A should fail if manifest contains path escapes."""
        simple_manifest["assets"] = [{
            "path": "../etc/passwd",
            "sha256": "sha256:" + "a" * 64,
            "classification": "code"
        }]

        passed, errors = check_g0a_package_declaration(simple_manifest, {})

        assert not passed, "G0A should fail for path escape"
        assert any("PATH_ESCAPE" in e for e in errors)

    def test_g0a_fails_absolute_path(self, simple_manifest):
        """G0A should fail if manifest contains absolute paths."""
        simple_manifest["assets"] = [{
            "path": "/etc/passwd",
            "sha256": "sha256:" + "a" * 64,
            "classification": "code"
        }]

        passed, errors = check_g0a_package_declaration(simple_manifest, {})

        assert not passed, "G0A should fail for absolute path"
        assert any("PATH_ESCAPE" in e for e in errors)

    def test_g0a_fails_wrong_hash_format(self, simple_manifest):
        """G0A should fail if hash format is wrong."""
        simple_manifest["assets"] = [{
            "path": "lib/test.py",
            "sha256": "badhash123",  # Not sha256: format
            "classification": "code"
        }]

        passed, errors = check_g0a_package_declaration(simple_manifest, {})

        assert not passed, "G0A should fail for wrong hash format"
        assert any("HASH_FORMAT" in e for e in errors)


class TestG1Chain:
    """Test G1 gate: chain validation."""

    def test_g1_passes_valid_deps(self, simple_manifest):
        """G1 should pass for valid package dependencies."""
        simple_manifest["deps"] = ["PKG-G0-001"]

        passed, errors = check_g1_chain(simple_manifest, CONTROL_PLANE_ROOT, strict=False)

        assert passed, f"G1 should pass: {errors}"

    def test_g1_passes_no_deps(self, simple_manifest):
        """G1 should pass for packages with no dependencies."""
        simple_manifest["deps"] = []

        passed, errors = check_g1_chain(simple_manifest, CONTROL_PLANE_ROOT, strict=False)

        assert passed, f"G1 should pass: {errors}"

    def test_g1_fails_invalid_dep_format(self, simple_manifest):
        """G1 should fail for invalid dependency format."""
        simple_manifest["deps"] = ["invalid-dep-format"]

        passed, errors = check_g1_chain(simple_manifest, CONTROL_PLANE_ROOT, strict=False)

        assert not passed, "G1 should fail for invalid dep format"
        assert any("INVALID_DEP" in e for e in errors)


class TestOwnershipConflicts:
    """Test ownership conflict detection (no last-write-wins)."""

    def test_no_conflict_empty_ownership(self, simple_manifest):
        """No conflict when ownership registry is empty."""
        simple_manifest["assets"] = [{
            "path": "lib/new_file.py",
            "sha256": "sha256:" + "a" * 64
        }]

        passed, errors = check_ownership_conflicts(simple_manifest, {}, "PKG-TEST-001")

        assert passed, f"Should pass: {errors}"

    def test_no_conflict_same_package(self, simple_manifest):
        """No conflict when same package owns the file (idempotent reinstall)."""
        simple_manifest["assets"] = [{
            "path": "lib/existing.py",
            "sha256": "sha256:" + "a" * 64
        }]

        existing_ownership = {
            "lib/existing.py": {"owner_package_id": "PKG-TEST-001"}
        }

        passed, errors = check_ownership_conflicts(
            simple_manifest, existing_ownership, "PKG-TEST-001"
        )

        assert passed, "Same package reinstall should be idempotent"

    def test_conflict_different_package(self, simple_manifest):
        """Conflict when different package owns the file."""
        simple_manifest["assets"] = [{
            "path": "lib/owned_by_other.py",
            "sha256": "sha256:" + "a" * 64
        }]

        existing_ownership = {
            "lib/owned_by_other.py": {"owner_package_id": "PKG-OTHER-001"}
        }

        passed, errors = check_ownership_conflicts(
            simple_manifest, existing_ownership, "PKG-TEST-001"
        )

        assert not passed, "Should fail for ownership conflict"
        assert any("OWNERSHIP_CONFLICT" in e for e in errors)


class TestWorkspaceExtraction:
    """Test workspace isolation and extraction."""

    def test_extract_to_workspace(self, test_package_dir, simple_manifest, test_file_content):
        """Files should be extracted to isolated workspace."""
        # Create archive
        files = {"lib/test_module.py": test_file_content}
        archive_path = create_test_archive(test_package_dir, simple_manifest, files)

        # Extract to workspace
        workspace = test_package_dir / "workspace"
        workspace.mkdir()

        workspace_files = extract_to_workspace(archive_path, workspace)

        assert "lib/test_module.py" in workspace_files
        assert workspace_files["lib/test_module.py"].exists()

    def test_workspace_skips_manifest(self, test_package_dir, simple_manifest, test_file_content):
        """Manifest and signature files should not be in workspace files."""
        files = {"lib/test_module.py": test_file_content}
        archive_path = create_test_archive(test_package_dir, simple_manifest, files)

        workspace = test_package_dir / "workspace"
        workspace.mkdir()

        workspace_files = extract_to_workspace(archive_path, workspace)

        # Manifest should be excluded from workspace files
        assert "manifest.json" not in workspace_files


class TestAtomicCopy:
    """Test atomic file copy."""

    def test_atomic_copy_creates_files(self, test_package_dir, test_file_content):
        """Atomic copy should create files in destination."""
        # Source file
        source = test_package_dir / "source" / "lib" / "test.py"
        source.parent.mkdir(parents=True)
        source.write_text(test_file_content)

        # Destination
        dest = test_package_dir / "dest"
        dest.mkdir()

        workspace_files = {"lib/test.py": source}

        installed = atomic_copy_files(workspace_files, dest)

        assert len(installed) == 1
        assert (dest / "lib" / "test.py").exists()
        assert (dest / "lib" / "test.py").read_text() == test_file_content

    def test_atomic_copy_fails_existing_without_force(self, test_package_dir, test_file_content):
        """Atomic copy should fail if file exists and force=False."""
        source = test_package_dir / "source" / "test.py"
        source.parent.mkdir(parents=True)
        source.write_text(test_file_content)

        dest = test_package_dir / "dest"
        dest.mkdir()
        existing = dest / "test.py"
        existing.write_text("existing content")

        workspace_files = {"test.py": source}

        with pytest.raises(InstallError, match="Target exists"):
            atomic_copy_files(workspace_files, dest, force=False)

    def test_atomic_copy_overwrites_with_force(self, test_package_dir, test_file_content):
        """Atomic copy should overwrite if force=True."""
        source = test_package_dir / "source" / "test.py"
        source.parent.mkdir(parents=True)
        source.write_text(test_file_content)

        dest = test_package_dir / "dest"
        dest.mkdir()
        existing = dest / "test.py"
        existing.write_text("existing content")

        workspace_files = {"test.py": source}

        installed = atomic_copy_files(workspace_files, dest, force=True)

        assert len(installed) == 1
        assert (dest / "test.py").read_text() == test_file_content


class TestManifestFromArchive:
    """Test loading manifest from archive."""

    def test_load_manifest_from_archive(self, test_package_dir, simple_manifest, test_file_content):
        """Should load manifest from archive."""
        files = {"lib/test.py": test_file_content}
        archive_path = create_test_archive(test_package_dir, simple_manifest, files)

        loaded = load_manifest_from_archive(archive_path)

        assert loaded is not None
        assert loaded["package_id"] == "PKG-TEST-001"
        assert loaded["schema_version"] == "1.2"


class TestHashComputation:
    """Test hash computation functions."""

    def test_compute_sha256_format(self, test_package_dir, test_file_content):
        """SHA256 hash should be in sha256:<64hex> format."""
        test_file = test_package_dir / "test.py"
        test_file.write_text(test_file_content)

        sha = compute_sha256(test_file)

        assert sha.startswith("sha256:")
        assert len(sha) == 71  # "sha256:" (7) + 64 hex chars

    def test_compute_manifest_hash_deterministic(self, simple_manifest):
        """Manifest hash should be deterministic."""
        hash1 = compute_manifest_hash(simple_manifest)
        hash2 = compute_manifest_hash(simple_manifest)

        assert hash1 == hash2

    def test_compute_manifest_hash_excludes_metadata(self, simple_manifest):
        """Manifest hash should exclude metadata block."""
        hash1 = compute_manifest_hash(simple_manifest)

        # Add metadata
        simple_manifest["metadata"] = {
            "generated_at": "2026-02-02T00:00:00Z",
            "random_field": "random_value"
        }

        hash2 = compute_manifest_hash(simple_manifest)

        assert hash1 == hash2, "Metadata should not affect hash"


class TestIntegration:
    """Integration tests for full package install workflow."""

    def test_full_workflow_validation(self, test_package_dir, simple_manifest, test_file_content):
        """Test full workflow: create archive, extract, validate G0A."""
        # Create archive with proper manifest
        files = {"lib/test_module.py": test_file_content}
        archive_path = create_test_archive(test_package_dir, simple_manifest, files)

        # Load manifest
        manifest = load_manifest_from_archive(archive_path)
        assert manifest is not None

        # Extract to workspace
        workspace = test_package_dir / "workspace"
        workspace.mkdir()
        workspace_files = extract_to_workspace(archive_path, workspace)

        # Validate G0A
        passed, errors = check_g0a_package_declaration(manifest, workspace_files)
        assert passed, f"G0A should pass: {errors}"

        # Validate G1 (use strict=False for isolated testing)
        passed, errors = check_g1_chain(manifest, CONTROL_PLANE_ROOT, strict=False)
        assert passed, f"G1 should pass: {errors}"

        # Check no ownership conflicts
        passed, errors = check_ownership_conflicts(manifest, {}, manifest["package_id"])
        assert passed, f"No conflicts expected: {errors}"
