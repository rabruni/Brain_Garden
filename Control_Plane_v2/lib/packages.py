"""Package utilities for Control Plane v2.

Provides simple, deterministic packing/unpacking of artifacts into
single-file tar.gz archives plus hash verification.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import tarfile
from pathlib import Path
from typing import Iterable, Tuple, Optional


def _deterministic_filter(tarinfo: tarfile.TarInfo) -> tarfile.TarInfo:
    """Normalize TarInfo for deterministic archives (I4-DETERMINISTIC).

    Ensures reproducible builds by zeroing variable metadata:
    - mtime: build timestamp would vary
    - uid/gid/uname/gname: builder identity would vary
    - mode: normalize to standard permissions
    """
    tarinfo.mtime = 0
    tarinfo.uid = 0
    tarinfo.gid = 0
    tarinfo.uname = ""
    tarinfo.gname = ""
    tarinfo.mode = 0o755 if tarinfo.isdir() else 0o644
    return tarinfo


from lib.hashing import sha256_file  # canonical implementation; re-exported for backward compat


def pack(src: Path, dest: Path, base: Optional[Path] = None) -> str:
    """
    Create a .tar.gz archive from a file or directory.

    Uses deterministic packing (I4-DETERMINISTIC):
    - Normalized file metadata (mtime=0, uid=0, gid=0)
    - Gzip mtime set to 0
    - Sorted file order
    - PAX format for reproducibility

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
        return str(p.relative_to(src))

    # Create tar in memory first, then gzip with mtime=0
    tar_buffer = io.BytesIO()
    with tarfile.open(fileobj=tar_buffer, mode="w", format=tarfile.PAX_FORMAT) as tar:
        if src.is_dir():
            for item in sorted(src.rglob("*")):
                arcname = rel_arcname(item)
                tar.add(item, arcname=arcname, recursive=False, filter=_deterministic_filter)
        else:
            tar.add(src, arcname=rel_arcname(src), filter=_deterministic_filter)

    # Write gzip with mtime=0 for determinism
    tar_data = tar_buffer.getvalue()
    with open(dest, "wb") as raw_f:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw_f, mtime=0) as gz:
            gz.write(tar_data)

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
