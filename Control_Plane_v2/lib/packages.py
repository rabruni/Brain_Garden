"""Package utilities for Control Plane v2.

Provides simple, deterministic packing/unpacking of artifacts into
single-file tar.gz archives plus hash verification.
"""

from __future__ import annotations

import hashlib
import tarfile
from pathlib import Path
from typing import Iterable, Tuple, Optional


def sha256_file(path: Path) -> str:
    """Compute SHA256 for a file."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def pack(src: Path, dest: Path, base: Optional[Path] = None) -> str:
    """
    Create a .tar.gz archive from a file or directory.

    Args:
        src: file or directory to package
        dest: output archive path (will be overwritten)
        base: optional base directory to preserve relative paths in archive
              (e.g., CONTROL_PLANE). If provided and src is under base,
              arcnames are stored relative to base to support replayable installs.

    Returns:
        sha256 digest of the archive
    """
    src = src.resolve()
    dest = dest.resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)

    def rel_arcname(p: Path) -> str:
        if base:
            try:
                return str(p.resolve().relative_to(base.resolve()))
            except ValueError:
                pass
        if p.is_dir():
            return p.name
        return p.name

    with tarfile.open(dest, "w:gz", format=tarfile.PAX_FORMAT) as tar:
        if src.is_dir():
            for item in sorted(src.rglob("*")):
                arcname = rel_arcname(item)
                tar.add(item, arcname=arcname)
        else:
            tar.add(src, arcname=rel_arcname(src))

    return sha256_file(dest)


def unpack(archive: Path, dest_root: Path) -> Iterable[Path]:
    """
    Extract an archive into dest_root, preserving relative paths.

    Args:
        archive: tar.gz file
        dest_root: root directory to extract into

    Returns:
        Iterable of extracted paths (relative to dest_root)
    """
    archive = archive.resolve()
    dest_root = dest_root.resolve()
    extracted = []
    with tarfile.open(archive, "r:gz") as tar:
        members = tar.getmembers()
        tar.extractall(path=dest_root)
        for m in members:
            extracted.append(dest_root / m.name)
    return extracted


def verify(archive: Path, expected_sha: str) -> Tuple[bool, str]:
    """Verify archive hash matches expected."""
    actual = sha256_file(archive)
    return actual == expected_sha, actual
