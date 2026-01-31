#!/usr/bin/env python3
"""
test_packages.py - Tests for package utilities.

Tests:
1. Deterministic packing (P7): Same source produces identical hash twice
2. Pack/unpack round-trip integrity
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.packages import pack, unpack, sha256_file


class TestDeterministicPacking:
    """P7: Pack is deterministic."""

    def test_pack_same_source_twice_identical_hash(self):
        """Two packs of same source produce identical hashes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)

            # Create source directory with files
            src = tmp / "source"
            src.mkdir()
            (src / "file1.txt").write_text("hello world")
            (src / "file2.txt").write_text("deterministic content")
            subdir = src / "subdir"
            subdir.mkdir()
            (subdir / "nested.txt").write_text("nested file")

            # Pack twice
            out1 = tmp / "pack1.tar.gz"
            out2 = tmp / "pack2.tar.gz"

            hash1 = pack(src, out1)
            hash2 = pack(src, out2)

            assert hash1 == hash2, f"Pack not deterministic: {hash1} != {hash2}"

    def test_pack_single_file_deterministic(self):
        """Single file packing is also deterministic."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)

            # Create single file
            src = tmp / "single.txt"
            src.write_text("single file content")

            out1 = tmp / "pack1.tar.gz"
            out2 = tmp / "pack2.tar.gz"

            hash1 = pack(src, out1)
            hash2 = pack(src, out2)

            assert hash1 == hash2, f"Single file pack not deterministic: {hash1} != {hash2}"


class TestPackUnpackRoundTrip:
    """Pack/unpack integrity tests."""

    def test_roundtrip_preserves_content(self):
        """Unpack restores original file content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)

            # Create source
            src = tmp / "source"
            src.mkdir()
            (src / "test.txt").write_text("test content")

            # Pack
            archive = tmp / "archive.tar.gz"
            pack(src, archive)

            # Unpack
            dest = tmp / "dest"
            dest.mkdir()
            unpack(archive, dest)

            # Verify content
            extracted = dest / "test.txt"
            assert extracted.exists()
            assert extracted.read_text() == "test content"


def run_tests():
    """Run all tests and report results."""
    passed = 0
    failed = 0

    test_classes = [TestDeterministicPacking, TestPackUnpackRoundTrip]

    for test_class in test_classes:
        instance = test_class()
        for method_name in dir(instance):
            if not method_name.startswith("test_"):
                continue

            method = getattr(instance, method_name)
            test_name = f"{test_class.__name__}.{method_name}"

            try:
                method()
                print(f"  PASS: {test_name}")
                passed += 1
            except AssertionError as e:
                print(f"  FAIL: {test_name} - {e}")
                failed += 1
            except Exception as e:
                print(f"  ERROR: {test_name} - {e}")
                failed += 1

    print()
    print(f"Passed: {passed}, Failed: {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    print("=" * 60)
    print("PACKAGE TESTS")
    print("=" * 60)
    sys.exit(run_tests())
