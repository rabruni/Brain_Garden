#!/usr/bin/env python3
"""
test_provenance.py - Acceptance tests for provenance attestation framework.

Tests:
1) Attestation generation creates valid JSON
2) Attestation verification succeeds for valid archive
3) Attestation fails for tampered archive
4) AttestationMissing raised when no attestation
5) Signed attestation verification works

Per FMWK-ATT-001: Provenance Attestation Standard
"""
from __future__ import annotations

import json
import os
import tempfile
import tarfile
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.provenance import (
    create_attestation,
    sign_attestation,
    verify_attestation,
    verify_attestation_signature,
    has_attestation,
    get_attestation_path,
    compute_attestation_digest,
    Attestation,
    BuilderInfo,
    SourceInfo,
    AttestationError,
    AttestationMissing,
    AttestationVerificationFailed,
    AttestationDigestMismatch,
    ATTESTATION_SCHEMA_VERSION,
)


def test_attestation_dataclasses():
    """Test dataclass serialization/deserialization."""
    builder = BuilderInfo(tool="test_tool", tool_version="1.0.0")
    assert builder.to_dict() == {"tool": "test_tool", "tool_version": "1.0.0"}

    source = SourceInfo(repo="https://github.com/test/repo", revision="abc123")
    source_dict = source.to_dict()
    assert source_dict["repo"] == "https://github.com/test/repo"
    assert source_dict["revision"] == "abc123"
    assert "branch" not in source_dict  # None values excluded

    att = Attestation(
        package_id="PKG-TEST",
        package_digest_sha256="a" * 64,
        builder=builder,
        source=source,
    )
    json_str = att.to_json()
    parsed = Attestation.from_json(json_str)
    assert parsed.package_id == "PKG-TEST"
    assert parsed.package_digest_sha256 == "a" * 64
    assert parsed.builder.tool == "test_tool"
    assert parsed.source.repo == "https://github.com/test/repo"
    print("PASS: test_attestation_dataclasses")


def test_attestation_generation():
    """Test 1: Attestation generation creates valid JSON."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        # Create test archive
        test_file = tmp / "test.txt"
        test_file.write_text("hello world")

        archive = tmp / "test.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            tar.add(test_file, arcname="test.txt")

        # Generate attestation
        att_path = create_attestation(
            archive,
            "PKG-TEST",
            source_repo="https://github.com/test/repo",
            source_revision="abc123def456",
        )

        # Verify file exists
        assert att_path.exists()
        assert att_path.name == "test.tar.gz.attestation.json"

        # Verify JSON structure
        with att_path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        assert data["schema_version"] == ATTESTATION_SCHEMA_VERSION
        assert data["package_id"] == "PKG-TEST"
        assert len(data["package_digest_sha256"]) == 64
        assert "built_at" in data
        assert data["builder"]["tool"] == "control_plane_package_pack"
        assert data["source"]["repo"] == "https://github.com/test/repo"
        assert data["source"]["revision"] == "abc123def456"

        print("PASS: test_attestation_generation")


def test_attestation_verification():
    """Test 2: Attestation verification succeeds for valid archive."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        # Create test archive
        test_file = tmp / "test.txt"
        test_file.write_text("hello world")

        archive = tmp / "test.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            tar.add(test_file, arcname="test.txt")

        # Generate attestation
        create_attestation(archive, "PKG-TEST")

        # Verify attestation
        valid, att = verify_attestation(archive)
        assert valid
        assert att.package_id == "PKG-TEST"
        assert att.schema_version == ATTESTATION_SCHEMA_VERSION

        print("PASS: test_attestation_verification")


def test_attestation_tampered():
    """Test 3: Attestation fails for tampered archive."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        # Create test archive
        test_file = tmp / "test.txt"
        test_file.write_text("hello world")

        archive = tmp / "test.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            tar.add(test_file, arcname="test.txt")

        # Generate attestation
        create_attestation(archive, "PKG-TEST")

        # Tamper with archive
        archive.write_bytes(archive.read_bytes() + b"tampered")

        # Verify fails
        try:
            verify_attestation(archive)
            print("FAIL: test_attestation_tampered - should have raised")
            return False
        except AttestationDigestMismatch as e:
            assert "mismatch" in str(e).lower()
            print("PASS: test_attestation_tampered")
            return True


def test_attestation_missing():
    """Test 4: AttestationMissing raised when no attestation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        # Create test archive without attestation
        test_file = tmp / "test.txt"
        test_file.write_text("hello world")

        archive = tmp / "test.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            tar.add(test_file, arcname="test.txt")

        # Verify has_attestation returns False
        assert not has_attestation(archive)

        # Verify raises AttestationMissing
        try:
            verify_attestation(archive)
            print("FAIL: test_attestation_missing - should have raised")
            return False
        except AttestationMissing as e:
            assert "not found" in str(e).lower()
            print("PASS: test_attestation_missing")
            return True


def test_attestation_signed():
    """Test 5: Signed attestation verification works."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        # Create test archive
        test_file = tmp / "test.txt"
        test_file.write_text("hello world")

        archive = tmp / "test.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            tar.add(test_file, arcname="test.txt")

        # Generate attestation
        att_path = create_attestation(archive, "PKG-TEST")

        # Sign attestation
        os.environ["CONTROL_PLANE_SIGNING_KEY"] = "test-secret-key-12345678"

        try:
            sig_path = sign_attestation(att_path, signer="test")
            assert sig_path.exists()
            assert sig_path.name == "test.tar.gz.attestation.json.sig"

            # Verify signature
            valid = verify_attestation_signature(att_path)
            assert valid

            print("PASS: test_attestation_signed")
        finally:
            del os.environ["CONTROL_PLANE_SIGNING_KEY"]


def test_attestation_digest():
    """Test attestation digest computation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        # Create test archive
        test_file = tmp / "test.txt"
        test_file.write_text("hello world")

        archive = tmp / "test.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            tar.add(test_file, arcname="test.txt")

        # Generate attestation
        att_path = create_attestation(archive, "PKG-TEST")

        # Compute digest
        digest = compute_attestation_digest(att_path)
        assert len(digest) == 64
        assert all(c in "0123456789abcdef" for c in digest)

        print("PASS: test_attestation_digest")


def test_attestation_path_helpers():
    """Test path helper functions."""
    archive = Path("/tmp/test.tar.gz")

    att_path = get_attestation_path(archive)
    assert str(att_path) == "/tmp/test.tar.gz.attestation.json"

    print("PASS: test_attestation_path_helpers")


def test_attestation_invalid_schema():
    """Test that invalid schema version fails verification."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        # Create test archive
        test_file = tmp / "test.txt"
        test_file.write_text("hello world")

        archive = tmp / "test.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            tar.add(test_file, arcname="test.txt")

        # Create attestation with invalid schema
        from lib.packages import sha256_file
        att_data = {
            "schema_version": "99.0",  # Invalid version
            "package_id": "PKG-TEST",
            "package_digest_sha256": sha256_file(archive),
            "built_at": "2026-01-31T00:00:00+00:00",
            "builder": {"tool": "test", "tool_version": "1.0.0"},
        }

        att_path = get_attestation_path(archive)
        with att_path.open("w", encoding="utf-8") as f:
            json.dump(att_data, f)

        # Verify fails
        try:
            verify_attestation(archive)
            print("FAIL: test_attestation_invalid_schema - should have raised")
            return False
        except AttestationVerificationFailed as e:
            assert "schema" in str(e).lower()
            print("PASS: test_attestation_invalid_schema")
            return True


def run_all_tests():
    """Run all acceptance tests."""
    print("=" * 60)
    print("PROVENANCE ATTESTATION ACCEPTANCE TESTS")
    print("=" * 60)

    print("-" * 60)
    print("Dataclass Tests:")
    print("-" * 60)

    test_attestation_dataclasses()
    test_attestation_path_helpers()
    test_attestation_digest()

    print("-" * 60)
    print("Core Functionality Tests:")
    print("-" * 60)

    test_attestation_generation()
    test_attestation_verification()
    test_attestation_tampered()
    test_attestation_missing()
    test_attestation_signed()
    test_attestation_invalid_schema()

    print("=" * 60)
    print("ALL PROVENANCE TESTS COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    run_all_tests()
