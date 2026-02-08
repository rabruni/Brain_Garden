"""Tests for lib/hashing.py - canonical SHA256 utilities."""
import hashlib
import tempfile
from pathlib import Path

import pytest
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kernel.hashing import sha256_file, compute_sha256, sha256_string


@pytest.fixture
def tmp_file(tmp_path):
    """Create a temp file with known content."""
    p = tmp_path / "test.txt"
    p.write_text("hello world\n")
    return p


def test_sha256_file_matches_known_hash(tmp_file):
    """sha256_file should match hashlib direct computation."""
    expected = hashlib.sha256(tmp_file.read_bytes()).hexdigest()
    assert sha256_file(tmp_file) == expected


def test_compute_sha256_has_prefix(tmp_file):
    """compute_sha256 should return sha256:<hex> format."""
    result = compute_sha256(tmp_file)
    assert result.startswith("sha256:")
    assert len(result) == 71  # "sha256:" (7) + 64 hex chars


def test_sha256_string_deterministic():
    """sha256_string should be deterministic."""
    h1 = sha256_string("test content")
    h2 = sha256_string("test content")
    assert h1 == h2
    assert len(h1) == 64


def test_chunk_size_does_not_affect_result(tmp_file):
    """Different chunk sizes must produce identical hashes."""
    h1 = sha256_file(tmp_file, chunk_size=1)
    h2 = sha256_file(tmp_file, chunk_size=8192)
    h3 = sha256_file(tmp_file, chunk_size=65536)
    assert h1 == h2 == h3


def test_file_not_found_raises():
    """sha256_file should raise FileNotFoundError for missing files."""
    with pytest.raises(FileNotFoundError):
        sha256_file(Path("/nonexistent/file.txt"))


def test_compute_sha256_matches_sha256_file(tmp_file):
    """compute_sha256 hex portion should match sha256_file."""
    raw = sha256_file(tmp_file)
    prefixed = compute_sha256(tmp_file)
    assert prefixed == f"sha256:{raw}"


def test_sha256_string_matches_hashlib():
    """sha256_string should match hashlib direct computation."""
    content = "governance chain"
    expected = hashlib.sha256(content.encode("utf-8")).hexdigest()
    assert sha256_string(content) == expected
