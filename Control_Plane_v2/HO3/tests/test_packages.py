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
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "HOT"))

from kernel.packages import pack, unpack, sha256_file


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

    def test_nested_directory_no_duplicates(self):
        """Nested directory pack has no duplicate entries and preserves paths."""
        import tarfile

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)

            # Create nested directory structure mimicking a real package
            src = tmp / "PKG-TEST"
            (src / "modules" / "admin_agent").mkdir(parents=True)
            (src / "lib").mkdir()
            (src / "tests").mkdir()

            (src / "manifest.json").write_text('{"package_id": "PKG-TEST"}')
            (src / "modules" / "admin_agent" / "agent.py").write_text("class Agent: pass")
            (src / "modules" / "admin_agent" / "tools.py").write_text("def tool(): pass")
            (src / "lib" / "helpers.py").write_text("def help(): pass")
            (src / "tests" / "test_agent.py").write_text("def test(): pass")

            # Pack
            archive = tmp / "test.tar.gz"
            pack(src, archive)

            # Inspect archive: no duplicate entries
            with tarfile.open(archive, "r:gz") as tf:
                names = [m.name for m in tf.getmembers()]

            assert len(names) == len(set(names)), f"Duplicate entries found: {names}"

            # Verify paths are preserved (not flattened to bare filenames)
            assert "modules/admin_agent/agent.py" in names
            assert "modules/admin_agent/tools.py" in names
            assert "lib/helpers.py" in names
            assert "tests/test_agent.py" in names
            assert "manifest.json" in names

            # Verify directory entries exist
            assert "modules" in names or "modules/" in names or \
                any(n.startswith("modules/") for n in names)

            # Round-trip: extract and verify file layout
            dest = tmp / "extracted"
            dest.mkdir()
            unpack(archive, dest)

            assert (dest / "modules" / "admin_agent" / "agent.py").read_text() == "class Agent: pass"
            assert (dest / "modules" / "admin_agent" / "tools.py").read_text() == "def tool(): pass"
            assert (dest / "lib" / "helpers.py").read_text() == "def help(): pass"
            assert (dest / "tests" / "test_agent.py").read_text() == "def test(): pass"
            assert (dest / "manifest.json").read_text() == '{"package_id": "PKG-TEST"}'


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
