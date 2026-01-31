#!/usr/bin/env python3
"""
merkle.py - Merkle Tree Integrity Library (LIB-003)

Self-contained Merkle tree implementation for registry integrity verification.
No third-party dependencies - Python stdlib only (hashlib).

Usage:
    from lib.merkle import hash_file, hash_combine, merkle_root

    # Hash a single file
    h = hash_file(Path("some/file.py"))

    # Combine two hashes
    combined = hash_combine(hash1, hash2)

    # Compute Merkle root from list of hashes
    root = merkle_root(["hash1", "hash2", "hash3"])
"""

import hashlib
from pathlib import Path
from typing import List, Union


def hash_file(path: Union[str, Path], chunk_size: int = 8192) -> str:
    """
    Compute SHA256 hash of a file's contents.

    Args:
        path: Path to the file to hash
        chunk_size: Read buffer size (default 8KB)

    Returns:
        Lowercase hex digest of SHA256 hash

    Raises:
        FileNotFoundError: If file doesn't exist
        IsADirectoryError: If path is a directory
    """
    path = Path(path)
    sha256 = hashlib.sha256()

    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            sha256.update(chunk)

    return sha256.hexdigest()


def hash_string(content: str) -> str:
    """
    Compute SHA256 hash of a string.

    Args:
        content: String to hash

    Returns:
        Lowercase hex digest of SHA256 hash
    """
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def hash_combine(hash_a: str, hash_b: str) -> str:
    """
    Combine two hashes into one using SHA256(a + b).

    This is the fundamental operation for building Merkle trees.
    Concatenates the two hex strings and hashes the result.

    Args:
        hash_a: First hash (hex string)
        hash_b: Second hash (hex string)

    Returns:
        Combined hash as lowercase hex digest
    """
    combined = hash_a + hash_b
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()


def merkle_root(hashes: List[str]) -> str:
    """
    Compute Merkle root from a list of hashes.

    Algorithm:
    1. If empty list, return empty string
    2. If single hash, return it directly
    3. Otherwise, pair up hashes and combine
    4. For odd number of hashes, duplicate the last one
    5. Recurse until single root remains

    Args:
        hashes: List of hex hash strings

    Returns:
        Single Merkle root hash, or empty string if input is empty

    Example:
        >>> merkle_root([])
        ''
        >>> merkle_root(['a'])
        'a'
        >>> merkle_root(['a', 'b'])
        hash_combine('a', 'b')
        >>> merkle_root(['a', 'b', 'c'])  # c is duplicated
        hash_combine(hash_combine('a', 'b'), hash_combine('c', 'c'))
    """
    if not hashes:
        return ""

    if len(hashes) == 1:
        return hashes[0]

    # Build next level by pairing hashes
    next_level = []

    for i in range(0, len(hashes), 2):
        left = hashes[i]
        # For odd number, duplicate the last hash
        right = hashes[i + 1] if i + 1 < len(hashes) else hashes[i]
        next_level.append(hash_combine(left, right))

    # Recurse until we have a single root
    return merkle_root(next_level)


def verify_file_hash(path: Union[str, Path], expected_hash: str) -> bool:
    """
    Verify a file's content matches the expected hash.

    Args:
        path: Path to the file
        expected_hash: Expected SHA256 hash (hex string)

    Returns:
        True if hashes match, False otherwise
    """
    try:
        actual_hash = hash_file(path)
        return actual_hash.lower() == expected_hash.lower()
    except (FileNotFoundError, IsADirectoryError, PermissionError):
        return False


__all__ = [
    "hash_file",
    "hash_string",
    "hash_combine",
    "merkle_root",
    "verify_file_hash",
]
