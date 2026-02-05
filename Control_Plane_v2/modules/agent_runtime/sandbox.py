"""Session-scoped sandbox for write isolation.

Executes agent turns in a write-restricted environment where only declared
outputs can be written. All other writes are blocked (fail-closed).

Example:
    from modules.agent_runtime.sandbox import TurnSandbox

    declared_outputs = [
        {"path": "output/SES-123/result.json", "role": "result"}
    ]

    with TurnSandbox("SES-123", declared_outputs) as sandbox:
        # Execute turn...
        # Only declared outputs can be written

    realized, valid = sandbox.verify_writes()
    if not valid:
        raise SandboxError("Write surface mismatch")
"""

import hashlib
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from modules.agent_runtime.exceptions import SandboxError


def hash_file(path: Path) -> str:
    """Compute SHA256 hash of file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return f"sha256:{h.hexdigest()}"


class TurnSandbox:
    """Execute a turn in a write-restricted sandbox."""

    def __init__(
        self,
        session_id: str,
        declared_outputs: List[Dict],
        root: Optional[Path] = None,
    ):
        """Initialize sandbox for session.

        Args:
            session_id: Session identifier
            declared_outputs: List of declared output dicts with "path" and "role"
            root: Optional root directory (defaults to Control Plane root)
        """
        self.session_id = session_id
        self.declared_outputs = declared_outputs or []
        self.root = root or self._get_default_root()

        # Sandbox paths
        self.sandbox_root = self.root / "tmp" / session_id
        self.output_root = self.root / "output" / session_id

        # Track original environment
        self._original_env: Dict[str, Optional[str]] = {}
        self._original_cwd: Optional[Path] = None
        self._active = False

    def _get_default_root(self) -> Path:
        """Get default Control Plane root."""
        current = Path(__file__).resolve()
        while current.name != "Control_Plane_v2" and current.parent != current:
            current = current.parent
        if current.name == "Control_Plane_v2":
            return current
        return Path.cwd()

    def __enter__(self) -> "TurnSandbox":
        """Enter sandbox: create directories, set environment."""
        # Create sandbox directories
        self.sandbox_root.mkdir(parents=True, exist_ok=True)
        self.output_root.mkdir(parents=True, exist_ok=True)

        # Save original environment
        self._original_env = {
            "TMPDIR": os.environ.get("TMPDIR"),
            "TEMP": os.environ.get("TEMP"),
            "TMP": os.environ.get("TMP"),
            "PYTHONDONTWRITEBYTECODE": os.environ.get("PYTHONDONTWRITEBYTECODE"),
        }
        self._original_cwd = Path.cwd()

        # Set sandbox environment
        os.environ["TMPDIR"] = str(self.sandbox_root)
        os.environ["TEMP"] = str(self.sandbox_root)
        os.environ["TMP"] = str(self.sandbox_root)
        os.environ["PYTHONDONTWRITEBYTECODE"] = "1"  # Prevent .pyc files

        self._active = True
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit sandbox: restore environment."""
        # Restore original environment
        for key, value in self._original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

        self._active = False

    def _enumerate_writes(self) -> List[Dict]:
        """Enumerate all files in sandbox directories.

        Returns:
            List of dicts with path, hash, size
        """
        realized = []

        for root_dir in [self.sandbox_root, self.output_root]:
            if not root_dir.exists():
                continue
            for path in root_dir.rglob("*"):
                if path.is_file():
                    # Compute relative path from Control Plane root
                    rel_path = str(path.relative_to(self.root))
                    realized.append({
                        "path": rel_path,
                        "hash": hash_file(path),
                        "size": path.stat().st_size,
                    })

        return realized

    def _normalize_path(self, path: str) -> str:
        """Normalize path for comparison."""
        # Replace session_id placeholder
        path = path.replace("<session_id>", self.session_id)
        path = path.replace("<sid>", self.session_id)
        # Remove leading slash
        path = path.lstrip("/")
        return path

    def verify_writes(self) -> Tuple[List[Dict], bool]:
        """Enumerate realized writes and compare to declared.

        Returns:
            Tuple of (realized_writes, is_valid)

        Raises:
            SandboxError: If write surface doesn't match (with details)
        """
        realized = self._enumerate_writes()

        # Normalize declared paths
        declared_paths = {
            self._normalize_path(d["path"])
            for d in self.declared_outputs
        }

        # Get realized paths
        realized_paths = {r["path"] for r in realized}

        # Check for mismatches
        undeclared = realized_paths - declared_paths
        missing = declared_paths - realized_paths

        if undeclared or missing:
            return realized, False

        return realized, True

    def verify_and_raise(self) -> List[Dict]:
        """Verify writes and raise SandboxError on mismatch.

        Returns:
            List of realized writes

        Raises:
            SandboxError: If write surface doesn't match
        """
        realized = self._enumerate_writes()

        # Normalize declared paths
        declared_paths = {
            self._normalize_path(d["path"])
            for d in self.declared_outputs
        }

        # Get realized paths
        realized_paths = {r["path"] for r in realized}

        # Check for mismatches
        undeclared = list(realized_paths - declared_paths)
        missing = list(declared_paths - realized_paths)

        if undeclared or missing:
            raise SandboxError(
                f"Write surface mismatch: {len(undeclared)} undeclared, {len(missing)} missing",
                session_id=self.session_id,
                undeclared_writes=undeclared,
                missing_writes=missing,
            )

        return realized
