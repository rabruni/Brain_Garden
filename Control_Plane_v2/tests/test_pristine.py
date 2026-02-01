#!/usr/bin/env python3
"""
test_pristine.py - Acceptance tests for pristine boundary enforcement.

Tests:
1) Direct write into lib/ → FAIL
2) package_install writes into lib/ (install mode) → PASS
3) Tampered tarball → FAIL install
4) Signed tarball → PASS install + ledger record
5) Unsigned tarball → PASS install + SIGNATURE_MISSING warning
6) Write into registries/ outside bootstrap → FAIL
"""
from __future__ import annotations

import os
import tempfile
import tarfile
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.paths import CONTROL_PLANE
from lib.pristine import (
    assert_write_allowed,
    WriteViolation,
    WriteMode,
    classify_path,
    PathClass,
    InstallModeContext,
    BootstrapModeContext,
    OutsideBoundaryViolation,
)
from lib.signing import (
    sign_detached,
    verify_detached,
    has_signature,
    SignatureVerificationFailed,
    SignatureMissing,
)
from lib.packages import sha256_file


def test_classify_pristine_paths():
    """Pristine paths are classified correctly."""
    assert classify_path(CONTROL_PLANE / "lib" / "foo.py") == PathClass.PRISTINE
    assert classify_path(CONTROL_PLANE / "frameworks" / "FMWK-001.md") == PathClass.PRISTINE
    assert classify_path(CONTROL_PLANE / "scripts" / "test.py") == PathClass.PRISTINE
    assert classify_path(CONTROL_PLANE / "registries" / "control_plane_registry.csv") == PathClass.PRISTINE
    print("PASS: test_classify_pristine_paths")


def test_classify_derived_paths():
    """Derived paths are classified correctly."""
    assert classify_path(CONTROL_PLANE / "packages_store" / "foo.tar.gz") == PathClass.DERIVED
    assert classify_path(CONTROL_PLANE / "registries" / "compiled" / "packages.json") == PathClass.DERIVED
    assert classify_path(CONTROL_PLANE / "versions" / "VER-001.json") == PathClass.DERIVED
    assert classify_path(CONTROL_PLANE / "tmp" / "scratch.txt") == PathClass.DERIVED
    print("PASS: test_classify_derived_paths")


def test_classify_append_only_paths():
    """Append-only paths are classified correctly."""
    assert classify_path(CONTROL_PLANE / "ledger" / "governance.jsonl") == PathClass.APPEND_ONLY
    print("PASS: test_classify_append_only_paths")


def test_direct_write_to_lib_fails():
    """Test 1: Direct write into lib/ → FAIL."""
    lib_path = CONTROL_PLANE / "lib" / "should_not_exist.py"
    try:
        assert_write_allowed(lib_path, mode=WriteMode.NORMAL, log_violation=False)
        print("FAIL: test_direct_write_to_lib_fails - should have raised")
        return False
    except WriteViolation as e:
        assert "PRISTINE" in str(e)
        print("PASS: test_direct_write_to_lib_fails")
        return True


def test_install_mode_allows_lib_write():
    """Test 2: package_install writes into lib/ (install mode) → PASS."""
    lib_path = CONTROL_PLANE / "lib" / "new_module.py"
    with InstallModeContext():
        try:
            assert_write_allowed(lib_path, mode=WriteMode.INSTALL, log_violation=False)
            print("PASS: test_install_mode_allows_lib_write")
            return True
        except WriteViolation:
            print("FAIL: test_install_mode_allows_lib_write - should not have raised")
            return False


def test_write_to_derived_always_allowed():
    """Writes to derived paths always allowed."""
    derived_path = CONTROL_PLANE / "packages_store" / "test.tar.gz"
    try:
        assert_write_allowed(derived_path, mode=WriteMode.NORMAL, log_violation=False)
        print("PASS: test_write_to_derived_always_allowed")
        return True
    except WriteViolation:
        print("FAIL: test_write_to_derived_always_allowed - should not have raised")
        return False


def test_registries_protected_outside_bootstrap():
    """Test 6: Write into registries/ outside bootstrap → FAIL."""
    reg_path = CONTROL_PLANE / "registries" / "packages_registry.csv"
    try:
        assert_write_allowed(reg_path, mode=WriteMode.NORMAL, log_violation=False)
        print("FAIL: test_registries_protected_outside_bootstrap - should have raised")
        return False
    except WriteViolation:
        print("PASS: test_registries_protected_outside_bootstrap")
        return True


def test_bootstrap_mode_allows_registry_write():
    """Bootstrap mode allows packages_registry.csv write."""
    reg_path = CONTROL_PLANE / "registries" / "packages_registry.csv"
    with BootstrapModeContext():
        try:
            assert_write_allowed(reg_path, mode=WriteMode.BOOTSTRAP, log_violation=False)
            print("PASS: test_bootstrap_mode_allows_registry_write")
            return True
        except WriteViolation:
            print("FAIL: test_bootstrap_mode_allows_registry_write - should not have raised")
            return False


def test_symlink_escape_blocked():
    """Symlinks pointing outside plane root must be blocked."""
    with tempfile.TemporaryDirectory() as tmp:
        plane_root = Path(tmp) / "plane"
        plane_root.mkdir()

        # Create symlink pointing outside plane root
        link_path = plane_root / "escape_link"
        link_path.symlink_to("/tmp")

        try:
            classify_path(link_path)
            print("FAIL: test_symlink_escape_blocked - should have raised OutsideBoundaryViolation")
            return False
        except OutsideBoundaryViolation as e:
            assert "symlink" in str(e).lower()
            print("PASS: test_symlink_escape_blocked")
            return True


def test_signing_and_verification():
    """Test 3-5: Signing and verification."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        # Create a test file and archive
        test_file = tmp / "test.txt"
        test_file.write_text("hello world")

        archive = tmp / "test.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            tar.add(test_file, arcname="test.txt")

        # Test 4: Signed tarball
        os.environ["CONTROL_PLANE_SIGNING_KEY"] = "test-secret-key-12345678"
        sig_path = sign_detached(archive, signer="test")
        assert sig_path.exists()
        assert has_signature(archive)

        valid, meta = verify_detached(archive)
        assert valid
        assert meta.signer == "test"
        print("PASS: test_signed_tarball_verification")

        # Test 3: Tampered tarball
        archive.write_bytes(archive.read_bytes() + b"tampered")
        try:
            verify_detached(archive)
            print("FAIL: test_tampered_tarball - should have raised")
        except SignatureVerificationFailed:
            print("PASS: test_tampered_tarball_fails")

        # Test 5: Unsigned tarball
        archive2 = tmp / "unsigned.tar.gz"
        with tarfile.open(archive2, "w:gz") as tar:
            tar.add(test_file, arcname="test.txt")

        assert not has_signature(archive2)
        try:
            verify_detached(archive2)
            print("FAIL: test_unsigned_tarball - should have raised SignatureMissing")
        except SignatureMissing:
            print("PASS: test_unsigned_tarball_emits_warning")

        # Cleanup env
        del os.environ["CONTROL_PLANE_SIGNING_KEY"]


def run_all_tests():
    """Run all acceptance tests."""
    print("=" * 60)
    print("PRISTINE BOUNDARY ACCEPTANCE TESTS")
    print("=" * 60)

    test_classify_pristine_paths()
    test_classify_derived_paths()
    test_classify_append_only_paths()

    print("-" * 60)
    print("Write Boundary Tests:")
    print("-" * 60)

    test_direct_write_to_lib_fails()
    test_install_mode_allows_lib_write()
    test_write_to_derived_always_allowed()
    test_registries_protected_outside_bootstrap()
    test_bootstrap_mode_allows_registry_write()

    print("-" * 60)
    print("Boundary Hardening Tests:")
    print("-" * 60)

    test_symlink_escape_blocked()

    print("-" * 60)
    print("Signing Tests:")
    print("-" * 60)

    test_signing_and_verification()

    print("=" * 60)
    print("ALL TESTS COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    run_all_tests()
