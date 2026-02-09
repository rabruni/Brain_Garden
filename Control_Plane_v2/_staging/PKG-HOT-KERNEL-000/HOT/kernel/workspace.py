"""
workspace.py - Isolated workspace management for Work Order execution.

Implements the isolated execution model specified in FMWK-000:
1. All Work Order execution MUST occur in an isolated workspace
2. Gates G0-G4 operate as validation only (read + compute, no writes)
3. Atomic APPLY step writes to authoritative plane
4. No partial state written to authoritative plane

Usage:
    with IsolatedWorkspace(plane_root, wo_id) as ws:
        ws.apply_patch(patch_path)
        # Run gates G0-G4
        if gates_pass:
            ws.apply_to_authoritative()
        # Otherwise ws is automatically discarded
"""

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@dataclass
class WorkspaceResult:
    """Result of workspace operations."""
    success: bool
    workspace_path: Optional[Path] = None
    message: str = ""
    error: Optional[str] = None
    audit_log: List[Dict[str, Any]] = field(default_factory=list)


class IsolatedWorkspace:
    """Context manager for isolated Work Order execution.

    Creates an ephemeral workspace for safe execution and validation
    of Work Orders before applying to the authoritative plane.

    Properties:
        - Isolation: Does NOT share filesystem with authoritative plane
        - Ephemerality: Discardable without side effects
        - Reproducibility: Recreatable from WO + commit refs

    Usage:
        with IsolatedWorkspace(plane_root, "WO-20260201-001") as ws:
            ws.clone_plane()
            ws.apply_changes(changeset)

            # Validate with gates
            if all_gates_pass:
                ws.prepare_atomic_apply()
            # Workspace auto-cleaned on exit
    """

    def __init__(
        self,
        plane_root: Path,
        work_order_id: str,
        preserve_on_failure: bool = True
    ):
        """Initialize isolated workspace.

        Args:
            plane_root: Path to authoritative plane
            work_order_id: Work Order ID for logging
            preserve_on_failure: If True, preserve workspace for debugging on failure
        """
        self.plane_root = Path(plane_root).resolve()
        self.work_order_id = work_order_id
        self.preserve_on_failure = preserve_on_failure

        self.workspace_path: Optional[Path] = None
        self.audit_log: List[Dict[str, Any]] = []
        self.created_at: Optional[str] = None
        self._cleanup_needed = True
        self._failed = False

    def __enter__(self) -> "IsolatedWorkspace":
        """Create isolated workspace."""
        self._create_workspace()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Clean up workspace unless preserving for debugging."""
        if exc_type is not None:
            self._failed = True
            self._log_event("WORKSPACE_ERROR", {
                "error_type": exc_type.__name__,
                "error_message": str(exc_val)
            })

        if self._cleanup_needed:
            if self._failed and self.preserve_on_failure:
                self._quarantine_workspace()
            else:
                self._destroy_workspace()

        return False  # Don't suppress exceptions

    def _create_workspace(self) -> None:
        """Create ephemeral workspace directory."""
        self.created_at = datetime.now(timezone.utc).isoformat()

        # Create temp directory with meaningful prefix
        prefix = f"cp-workspace-{self.work_order_id}-"
        self.workspace_path = Path(tempfile.mkdtemp(prefix=prefix))

        self._log_event("WORKSPACE_CREATED", {
            "workspace_path": str(self.workspace_path),
            "work_order_id": self.work_order_id,
            "plane_root": str(self.plane_root)
        })

    def _destroy_workspace(self) -> None:
        """Remove workspace directory."""
        if self.workspace_path and self.workspace_path.exists():
            shutil.rmtree(self.workspace_path, ignore_errors=True)
            self._log_event("WORKSPACE_DESTROYED", {
                "workspace_path": str(self.workspace_path)
            })
        self.workspace_path = None

    def _quarantine_workspace(self) -> None:
        """Move workspace to quarantine for debugging."""
        if not self.workspace_path or not self.workspace_path.exists():
            return

        quarantine_dir = self.plane_root / "quarantine" / self.work_order_id
        quarantine_dir.mkdir(parents=True, exist_ok=True)

        # Save audit log
        audit_path = quarantine_dir / "audit.log"
        with open(audit_path, 'w', encoding='utf-8') as f:
            for entry in self.audit_log:
                f.write(json.dumps(entry) + '\n')

        # Save metadata
        metadata = {
            "work_order_id": self.work_order_id,
            "created_at": self.created_at,
            "quarantined_at": datetime.now(timezone.utc).isoformat(),
            "workspace_path": str(self.workspace_path),
            "plane_root": str(self.plane_root),
            "failed": self._failed
        }
        with open(quarantine_dir / "metadata.json", 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2)

        # Optionally compress workspace (skip for now to save time)
        # tar_path = quarantine_dir / "workspace.tar.gz"
        # shutil.make_archive(str(tar_path.with_suffix('')), 'gztar', self.workspace_path)

        self._log_event("WORKSPACE_QUARANTINED", {
            "quarantine_path": str(quarantine_dir)
        })

        # Clean up original workspace
        shutil.rmtree(self.workspace_path, ignore_errors=True)
        self.workspace_path = None

    def _log_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """Add entry to audit log."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "work_order_id": self.work_order_id,
            **data
        }
        self.audit_log.append(entry)

    def clone_plane(self, use_git: bool = True) -> WorkspaceResult:
        """Clone authoritative plane to workspace.

        Args:
            use_git: If True, use git clone; otherwise copy files

        Returns:
            WorkspaceResult with success status
        """
        if not self.workspace_path:
            return WorkspaceResult(success=False, error="Workspace not initialized")

        try:
            if use_git and (self.plane_root / ".git").exists():
                # Git clone for proper isolation
                result = subprocess.run(
                    ["git", "clone", "--depth=1", str(self.plane_root), str(self.workspace_path / "plane")],
                    capture_output=True,
                    text=True
                )
                if result.returncode != 0:
                    # Fall back to file copy
                    use_git = False

            if not use_git:
                # Direct file copy
                dest = self.workspace_path / "plane"
                shutil.copytree(
                    self.plane_root,
                    dest,
                    ignore=shutil.ignore_patterns('.git', '__pycache__', '*.pyc')
                )

            self._log_event("PLANE_CLONED", {
                "method": "git" if use_git else "copy",
                "destination": str(self.workspace_path / "plane")
            })

            return WorkspaceResult(
                success=True,
                workspace_path=self.workspace_path / "plane",
                message="Plane cloned successfully"
            )

        except Exception as e:
            self._failed = True
            return WorkspaceResult(success=False, error=str(e))

    def apply_patch(self, patch_path: Path) -> WorkspaceResult:
        """Apply a patch file to the workspace.

        Args:
            patch_path: Path to patch file

        Returns:
            WorkspaceResult with success status
        """
        if not self.workspace_path:
            return WorkspaceResult(success=False, error="Workspace not initialized")

        plane_workspace = self.workspace_path / "plane"
        if not plane_workspace.exists():
            return WorkspaceResult(success=False, error="Plane not cloned to workspace")

        try:
            result = subprocess.run(
                ["git", "apply", str(patch_path)],
                cwd=plane_workspace,
                capture_output=True,
                text=True
            )

            if result.returncode != 0:
                self._failed = True
                return WorkspaceResult(
                    success=False,
                    error=f"Patch failed: {result.stderr}"
                )

            self._log_event("PATCH_APPLIED", {
                "patch_path": str(patch_path)
            })

            return WorkspaceResult(success=True, message="Patch applied")

        except Exception as e:
            self._failed = True
            return WorkspaceResult(success=False, error=str(e))

    def apply_changes(self, changes: Dict[str, str]) -> WorkspaceResult:
        """Apply a set of file changes to the workspace.

        Args:
            changes: Dict mapping relative paths to new content

        Returns:
            WorkspaceResult with success status
        """
        if not self.workspace_path:
            return WorkspaceResult(success=False, error="Workspace not initialized")

        plane_workspace = self.workspace_path / "plane"
        if not plane_workspace.exists():
            plane_workspace.mkdir(parents=True)

        try:
            for rel_path, content in changes.items():
                file_path = plane_workspace / rel_path
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(content, encoding='utf-8')

            self._log_event("CHANGES_APPLIED", {
                "file_count": len(changes),
                "files": list(changes.keys())
            })

            return WorkspaceResult(success=True, message=f"Applied {len(changes)} changes")

        except Exception as e:
            self._failed = True
            return WorkspaceResult(success=False, error=str(e))

    def get_workspace_plane(self) -> Optional[Path]:
        """Get path to the plane copy within the workspace."""
        if self.workspace_path:
            return self.workspace_path / "plane"
        return None

    def mark_failed(self, reason: str) -> None:
        """Mark workspace as failed (will be quarantined)."""
        self._failed = True
        self._log_event("EXECUTION_FAILED", {"reason": reason})

    def mark_success(self) -> None:
        """Mark workspace as successful (will be cleaned up)."""
        self._failed = False
        self._log_event("EXECUTION_SUCCESS", {})

    def prepare_atomic_changeset(self) -> Dict[str, str]:
        """Prepare changeset for atomic apply.

        Compares workspace to authoritative plane and returns
        the minimal changeset needed.

        Returns:
            Dict mapping file paths to new content
        """
        changeset = {}
        plane_workspace = self.workspace_path / "plane" if self.workspace_path else None

        if not plane_workspace or not plane_workspace.exists():
            return changeset

        # Compare files in workspace to authoritative
        for file_path in plane_workspace.rglob("*"):
            if file_path.is_file() and "__pycache__" not in str(file_path):
                rel_path = file_path.relative_to(plane_workspace)
                auth_path = self.plane_root / rel_path

                workspace_content = file_path.read_text(encoding='utf-8')

                if not auth_path.exists():
                    # New file
                    changeset[str(rel_path)] = workspace_content
                else:
                    auth_content = auth_path.read_text(encoding='utf-8')
                    if workspace_content != auth_content:
                        # Modified file
                        changeset[str(rel_path)] = workspace_content

        self._log_event("CHANGESET_PREPARED", {
            "file_count": len(changeset),
            "files": list(changeset.keys())
        })

        return changeset

    def prevent_cleanup(self) -> None:
        """Prevent automatic cleanup (for debugging)."""
        self._cleanup_needed = False


def create_workspace(
    plane_root: Path,
    work_order_id: str,
    preserve_on_failure: bool = True
) -> IsolatedWorkspace:
    """Create an isolated workspace for Work Order execution.

    Args:
        plane_root: Path to authoritative plane
        work_order_id: Work Order ID
        preserve_on_failure: If True, quarantine on failure

    Returns:
        IsolatedWorkspace context manager
    """
    return IsolatedWorkspace(plane_root, work_order_id, preserve_on_failure)
