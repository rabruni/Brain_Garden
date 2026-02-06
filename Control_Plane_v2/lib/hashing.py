"""
hashing.py - Canonical SHA256 hashing utilities.

Single source of truth for all SHA256 computation in the Control Plane.
Stdlib only — no internal imports.

Usage:
    from lib.hashing import sha256_file, compute_sha256, sha256_string

    # Raw hex digest
    h = sha256_file(Path("some/file.py"))

    # Governance format: sha256:<hex>
    h = compute_sha256(Path("some/file.py"))

    # Hash a string
    h = sha256_string("content")
"""

import hashlib
from pathlib import Path
from typing import Union


def sha256_file(path: Union[str, Path], chunk_size: int = 65536) -> str:
    """Compute SHA256 hash of a file's contents.

    Args:
        path: Path to the file to hash
        chunk_size: Read buffer size (default 64KB)

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


def compute_sha256(file_path: Union[str, Path], chunk_size: int = 65536) -> str:
    """Compute SHA256 hash in governance format: sha256:<64hex>.

    Args:
        file_path: Path to the file to hash
        chunk_size: Read buffer size (default 64KB)

    Returns:
        Hash string in format "sha256:<hexdigest>"
    """
    return f"sha256:{sha256_file(file_path, chunk_size)}"


def sha256_string(content: str) -> str:
    """Compute SHA256 hash of a UTF-8 string.

    Args:
        content: String to hash

    Returns:
        Lowercase hex digest of SHA256 hash
    """
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


__all__ = [
    "sha256_file",
    "compute_sha256",
    "sha256_string",
]
