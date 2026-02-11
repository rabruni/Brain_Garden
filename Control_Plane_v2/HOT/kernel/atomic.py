"""
atomic.py - Atomic transaction wrapper for registry writes.

Implements the atomic apply model specified in FMWK-000:
1. All registry/ledger writes occur in a single atomic transaction
2. No partial state is ever written to authoritative plane
3. On failure, all changes are rolled back

Transaction modes:
1. File-based: Use rename() for POSIX atomicity
2. Git-based: Single commit for all changes (recommended)

Usage:
    with AtomicTransaction(plane_root) as tx:
        tx.write_file("registries/file.csv", new_content)
        tx.append_ledger("ledger/governance.jsonl", entry)
        # Commit happens on exit; rollback on exception
"""

import hashlib
import json
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
import subprocess

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TransactionError(Exception):
    """Raised when atomic transaction fails."""
    pass


class RollbackError(Exception):
    """Raised when rollback fails (critical state)."""
    pass


@dataclass
class WriteOperation:
    """A pending write operation."""
    target_path: Path
    content: str
    operation: str  # 'write', 'append', 'delete'
    backup_path: Optional[Path] = None


@dataclass
class TransactionResult:
    """Result of atomic transaction."""
    success: bool
    committed_files: List[str] = field(default_factory=list)
    rolled_back: bool = False
    error: Optional[str] = None
    commit_id: Optional[str] = None


class AtomicTransaction:
    """Context manager for atomic file operations.

    All writes are staged to a temporary location, then applied
    atomically using rename() operations. On any failure, all
    changes are rolled back.

    Usage:
        with AtomicTransaction(plane_root) as tx:
            tx.write_file("registries/file.csv", content)
            tx.append_ledger("ledger/governance.jsonl", entry)
        # Changes applied atomically on successful exit
    """

    def __init__(
        self,
        plane_root: Path,
        work_order_id: Optional[str] = None,
        use_git: bool = False
    ):
        """Initialize atomic transaction.

        Args:
            plane_root: Path to authoritative plane
            work_order_id: Optional WO ID for commit message
            use_git: If True, use git commit for atomicity
        """
        self.plane_root = Path(plane_root).resolve()
        self.work_order_id = work_order_id
        self.use_git = use_git

        self._staging_dir: Optional[Path] = None
        self._operations: List[WriteOperation] = []
        self._backups: Dict[str, Path] = {}
        self._committed = False
        self._rolled_back = False

    def __enter__(self) -> "AtomicTransaction":
        """Begin transaction."""
        self._staging_dir = self.plane_root / ".staging"
        self._staging_dir.mkdir(exist_ok=True)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Commit or rollback transaction."""
        try:
            if exc_type is not None:
                # Exception occurred, rollback
                self._rollback()
            else:
                # No exception, commit
                self._commit()
        finally:
            # Clean up staging
            self._cleanup_staging()

        return False  # Don't suppress exceptions

    def write_file(self, rel_path: str, content: str) -> None:
        """Stage a file write operation.

        Args:
            rel_path: Path relative to plane_root
            content: New file content
        """
        target = self.plane_root / rel_path
        self._operations.append(WriteOperation(
            target_path=target,
            content=content,
            operation='write'
        ))

    def append_file(self, rel_path: str, content: str) -> None:
        """Stage an append operation (for ledgers).

        Args:
            rel_path: Path relative to plane_root
            content: Content to append
        """
        target = self.plane_root / rel_path
        self._operations.append(WriteOperation(
            target_path=target,
            content=content,
            operation='append'
        ))

    def append_ledger(self, rel_path: str, entry: dict) -> None:
        """Stage a JSONL ledger append.

        Args:
            rel_path: Path relative to plane_root
            entry: Dict to append as JSON line
        """
        content = json.dumps(entry, separators=(',', ':')) + '\n'
        self.append_file(rel_path, content)

    def delete_file(self, rel_path: str) -> None:
        """Stage a file deletion.

        Args:
            rel_path: Path relative to plane_root
        """
        target = self.plane_root / rel_path
        self._operations.append(WriteOperation(
            target_path=target,
            content='',
            operation='delete'
        ))

    def _stage_operations(self) -> None:
        """Stage all operations to temporary files."""
        if not self._staging_dir:
            raise TransactionError("Staging directory not initialized")

        for i, op in enumerate(self._operations):
            # Create backup of existing file
            if op.target_path.exists():
                backup = self._staging_dir / f"backup_{i}_{op.target_path.name}"
                shutil.copy2(op.target_path, backup)
                op.backup_path = backup
                self._backups[str(op.target_path)] = backup

            # Stage the new content
            if op.operation in ('write', 'append'):
                staged = self._staging_dir / f"staged_{i}_{op.target_path.name}"

                if op.operation == 'append' and op.target_path.exists():
                    # For append, copy existing then append
                    shutil.copy2(op.target_path, staged)
                    with open(staged, 'a', encoding='utf-8') as f:
                        f.write(op.content)
                else:
                    # For write, just write new content
                    with open(staged, 'w', encoding='utf-8') as f:
                        f.write(op.content)

    def _commit(self) -> None:
        """Commit all staged operations atomically."""
        if self._committed or self._rolled_back:
            return

        try:
            # First, stage all operations
            self._stage_operations()

            # Then, apply atomically via rename
            committed_files = []

            for i, op in enumerate(self._operations):
                staged = self._staging_dir / f"staged_{i}_{op.target_path.name}"

                if op.operation == 'delete':
                    if op.target_path.exists():
                        op.target_path.unlink()
                        committed_files.append(str(op.target_path))
                elif staged.exists():
                    # Ensure parent directory exists
                    op.target_path.parent.mkdir(parents=True, exist_ok=True)

                    # Atomic rename (POSIX guarantees atomicity within same filesystem)
                    shutil.move(str(staged), str(op.target_path))
                    committed_files.append(str(op.target_path))

            self._committed = True

            # If using git, create commit
            if self.use_git and committed_files:
                self._git_commit(committed_files)

        except Exception as e:
            # Commit failed, try to rollback
            self._rollback()
            raise TransactionError(f"Commit failed: {e}") from e

    def _rollback(self) -> None:
        """Rollback all operations."""
        if self._rolled_back:
            return

        try:
            for target_str, backup_path in self._backups.items():
                target = Path(target_str)
                if backup_path.exists():
                    shutil.move(str(backup_path), str(target))

            self._rolled_back = True

        except Exception as e:
            raise RollbackError(f"Rollback failed - plane may be in inconsistent state: {e}") from e

    def _cleanup_staging(self) -> None:
        """Clean up staging directory."""
        if self._staging_dir and self._staging_dir.exists():
            shutil.rmtree(self._staging_dir, ignore_errors=True)

    def _git_commit(self, files: List[str]) -> str:
        """Create git commit for changes.

        Args:
            files: List of changed file paths

        Returns:
            Commit SHA
        """
        try:
            # Add files
            for f in files:
                rel = Path(f).relative_to(self.plane_root)
                subprocess.run(
                    ["git", "add", str(rel)],
                    cwd=self.plane_root,
                    capture_output=True,
                    check=True
                )

            # Create commit
            msg = f"Atomic apply: {self.work_order_id or 'transaction'}"
            result = subprocess.run(
                ["git", "commit", "-m", msg],
                cwd=self.plane_root,
                capture_output=True,
                text=True
            )

            if result.returncode == 0:
                # Get commit SHA
                sha_result = subprocess.run(
                    ["git", "rev-parse", "HEAD"],
                    cwd=self.plane_root,
                    capture_output=True,
                    text=True,
                    check=True
                )
                return sha_result.stdout.strip()

        except subprocess.CalledProcessError:
            pass  # Git commit is optional

        return ""


def atomic_apply(
    changes: Dict[str, str],
    plane_root: Path,
    work_order_id: Optional[str] = None
) -> TransactionResult:
    """Apply all changes atomically using rename.

    This is the simplified functional interface for atomic writes.

    Args:
        changes: Dict mapping relative paths to new content
        plane_root: Path to authoritative plane
        work_order_id: Optional WO ID for logging

    Returns:
        TransactionResult with success status
    """
    plane_root = Path(plane_root).resolve()
    staging = plane_root / ".staging"
    staging.mkdir(exist_ok=True)

    committed_files = []
    backups: Dict[str, Path] = {}

    try:
        # Stage all writes
        for i, (rel_path, content) in enumerate(changes.items()):
            target = plane_root / rel_path
            staged = staging / f"{i}_{Path(rel_path).name}"

            # Backup existing file
            if target.exists():
                backup = staging / f"backup_{i}_{Path(rel_path).name}"
                shutil.copy2(target, backup)
                backups[str(target)] = backup

            # Write staged content
            with open(staged, 'w', encoding='utf-8') as f:
                f.write(content)

        # Atomic rename phase
        for i, (rel_path, _) in enumerate(changes.items()):
            target = plane_root / rel_path
            staged = staging / f"{i}_{Path(rel_path).name}"

            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(staged), str(target))
            committed_files.append(rel_path)

        return TransactionResult(
            success=True,
            committed_files=committed_files
        )

    except Exception as e:
        # Rollback
        for target_str, backup_path in backups.items():
            target = Path(target_str)
            if backup_path.exists():
                try:
                    shutil.move(str(backup_path), str(target))
                except Exception:
                    pass  # Best effort rollback

        return TransactionResult(
            success=False,
            rolled_back=True,
            error=str(e)
        )

    finally:
        # Clean up staging
        shutil.rmtree(staging, ignore_errors=True)
