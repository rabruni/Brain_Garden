"""Capability enforcement for agent runtime.

Enforces read/write/execute capabilities declared in agent package manifests.
Capabilities are glob patterns that specify which paths an agent may access.

Example:
    from modules.agent_runtime.capability import CapabilityEnforcer

    capabilities = {
        "read": ["ledger/*.jsonl", "registries/*.csv"],
        "write": ["planes/ho1/sessions/*/ledger/exec.jsonl"],
        "execute": ["scripts/trace.py --explain"],
        "forbidden": ["lib/*", "scripts/package_install.py"]
    }

    enforcer = CapabilityEnforcer(capabilities)

    if enforcer.check("read", "ledger/governance.jsonl"):
        # Allowed
        pass

    enforcer.enforce("write", "lib/secret.py")  # Raises CapabilityViolation
"""

from fnmatch import fnmatch
from typing import Dict, List, Optional

from modules.agent_runtime.exceptions import CapabilityViolation


class CapabilityEnforcer:
    """Enforce read/write/execute capabilities."""

    def __init__(self, capabilities: Dict[str, List[str]]):
        """Initialize with capabilities from package manifest.

        Args:
            capabilities: Dictionary with keys:
                - read: List of glob patterns for readable paths
                - write: List of glob patterns for writable paths
                - execute: List of allowed command patterns
                - forbidden: List of patterns that are always denied
        """
        self.read_patterns = capabilities.get("read", [])
        self.write_patterns = capabilities.get("write", [])
        self.execute_patterns = capabilities.get("execute", [])
        self.forbidden_patterns = capabilities.get("forbidden", [])

    def _matches_any(self, path: str, patterns: List[str]) -> bool:
        """Check if path matches any of the patterns.

        Supports glob patterns including:
        - * matches anything except /
        - ** matches anything including /
        - ? matches single character
        """
        path = path.lstrip("/")
        for pattern in patterns:
            pattern = pattern.lstrip("/")
            # Handle ** patterns by replacing with *
            if "**" in pattern:
                simple_pattern = pattern.replace("**", "*")
                if fnmatch(path, simple_pattern):
                    return True
                # Also try with ** meaning "any depth"
                parts = pattern.split("**")
                if len(parts) == 2:
                    prefix, suffix = parts
                    if path.startswith(prefix.rstrip("/")) and path.endswith(suffix.lstrip("/")):
                        return True
            elif fnmatch(path, pattern):
                return True
        return False

    def is_forbidden(self, path: str) -> bool:
        """Check if path matches any forbidden pattern.

        Args:
            path: Path to check

        Returns:
            True if path is forbidden
        """
        return self._matches_any(path, self.forbidden_patterns)

    def check(self, operation: str, path: str) -> bool:
        """Check if operation is allowed on path.

        Args:
            operation: One of "read", "write", "execute"
            path: Path to check

        Returns:
            True if operation is allowed, False otherwise
        """
        # Forbidden patterns override everything
        if self.is_forbidden(path):
            return False

        if operation == "read":
            return self._matches_any(path, self.read_patterns)
        elif operation == "write":
            return self._matches_any(path, self.write_patterns)
        elif operation == "execute":
            return self._matches_any(path, self.execute_patterns)
        else:
            return False

    def enforce(self, operation: str, path: str) -> None:
        """Enforce capability, raise CapabilityViolation if denied.

        Args:
            operation: One of "read", "write", "execute"
            path: Path to check

        Raises:
            CapabilityViolation: If operation is not allowed
        """
        if self.is_forbidden(path):
            raise CapabilityViolation(
                f"Path is forbidden: {path}",
                operation=operation,
                path=path,
                details={"reason": "matches_forbidden_pattern"},
            )

        if not self.check(operation, path):
            raise CapabilityViolation(
                f"Capability denied: {operation} on {path}",
                operation=operation,
                path=path,
                details={
                    "reason": "no_matching_capability",
                    "available_patterns": getattr(self, f"{operation}_patterns", []),
                },
            )

    def check_declared_outputs(self, declared_outputs: List[dict]) -> None:
        """Verify all declared outputs match write capabilities.

        Args:
            declared_outputs: List of {"path": ..., "role": ...} dicts

        Raises:
            CapabilityViolation: If any declared output is not writable
        """
        for output in declared_outputs:
            path = output.get("path", "")
            if not self.check("write", path):
                raise CapabilityViolation(
                    f"Declared output not writable: {path}",
                    operation="write",
                    path=path,
                    details={"declared_output": output},
                )
