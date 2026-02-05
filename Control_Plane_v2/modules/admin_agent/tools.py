"""Admin Agent Tools - Claude Code style file operations.

Provides sandboxed read-only tools for the admin agent:
- read_file: Read file contents
- list_directory: List directory contents (glob patterns)
- grep: Search file contents

All operations respect capabilities.json read permissions.
"""

import fnmatch
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional


class ToolError(Exception):
    """Tool execution error."""
    pass


class AdminTools:
    """Sandboxed tools for admin agent."""

    def __init__(self, root: Path, capabilities: Dict[str, Any]):
        """Initialize with Control Plane root and capabilities.

        Args:
            root: Control Plane root directory
            capabilities: From capabilities.json
        """
        self.root = root
        self.read_patterns = capabilities.get("read", [])
        self.forbidden_patterns = capabilities.get("forbidden", [])

    def _is_allowed(self, rel_path: str) -> bool:
        """Check if path is allowed by capabilities.

        Args:
            rel_path: Path relative to Control Plane root

        Returns:
            True if reading is allowed
        """
        # Check forbidden first
        for pattern in self.forbidden_patterns:
            if fnmatch.fnmatch(rel_path, pattern):
                return False

        # Check allowed patterns
        for pattern in self.read_patterns:
            if fnmatch.fnmatch(rel_path, pattern):
                return True

        # Also allow reading Python files in modules/ for transparency
        if rel_path.startswith("modules/") and rel_path.endswith(".py"):
            return True

        return False

    def _resolve_path(self, path: str) -> tuple[Path, str]:
        """Resolve and validate a path.

        Args:
            path: Absolute or relative path

        Returns:
            Tuple of (absolute_path, relative_path)

        Raises:
            ToolError: If path is invalid or not allowed
        """
        # Handle absolute paths
        if path.startswith("/"):
            abs_path = Path(path)
            try:
                rel_path = str(abs_path.relative_to(self.root))
            except ValueError:
                raise ToolError(f"Path outside Control Plane root: {path}")
        else:
            rel_path = path
            abs_path = self.root / path

        # Resolve to catch .. traversal
        abs_path = abs_path.resolve()

        # Verify still under root
        try:
            rel_path = str(abs_path.relative_to(self.root))
        except ValueError:
            raise ToolError(f"Path traversal not allowed: {path}")

        # Check permissions
        if not self._is_allowed(rel_path):
            raise ToolError(f"Permission denied: {rel_path}")

        return abs_path, rel_path

    def read_file(self, path: str, limit: int = None, offset: int = 0) -> Dict[str, Any]:
        """Read file contents.

        Args:
            path: File path (absolute or relative to root)
            limit: Max lines to return (None for all)
            offset: Line offset to start from

        Returns:
            Dict with content, path, lines, etc.
        """
        abs_path, rel_path = self._resolve_path(path)

        if not abs_path.exists():
            raise ToolError(f"File not found: {rel_path}")

        if not abs_path.is_file():
            raise ToolError(f"Not a file: {rel_path}")

        try:
            content = abs_path.read_text(encoding="utf-8")
            lines = content.split("\n")
            total_lines = len(lines)

            # Apply offset and limit
            if offset > 0:
                lines = lines[offset:]
            if limit:
                lines = lines[:limit]

            return {
                "path": rel_path,
                "content": "\n".join(lines),
                "total_lines": total_lines,
                "returned_lines": len(lines),
                "offset": offset,
            }
        except UnicodeDecodeError:
            return {
                "path": rel_path,
                "content": f"<binary file, {abs_path.stat().st_size} bytes>",
                "is_binary": True,
            }
        except Exception as e:
            raise ToolError(f"Read error: {e}")

    def list_directory(self, path: str = ".", pattern: str = "*") -> Dict[str, Any]:
        """List directory contents with optional glob pattern.

        Args:
            path: Directory path
            pattern: Glob pattern (default "*")

        Returns:
            Dict with entries, count, path
        """
        abs_path, rel_path = self._resolve_path(path)

        if not abs_path.exists():
            raise ToolError(f"Directory not found: {rel_path}")

        if not abs_path.is_dir():
            raise ToolError(f"Not a directory: {rel_path}")

        entries = []
        for entry in sorted(abs_path.glob(pattern)):
            entry_rel = str(entry.relative_to(self.root))

            # Skip if not allowed
            if not self._is_allowed(entry_rel) and not entry.is_dir():
                continue

            # Skip hidden and pycache
            if entry.name.startswith(".") or entry.name == "__pycache__":
                continue

            entry_info = {
                "name": entry.name,
                "path": entry_rel,
                "is_dir": entry.is_dir(),
            }
            if entry.is_file():
                entry_info["size"] = entry.stat().st_size

            entries.append(entry_info)

        return {
            "path": rel_path,
            "pattern": pattern,
            "entries": entries,
            "count": len(entries),
        }

    def glob(self, pattern: str, path: str = ".") -> Dict[str, Any]:
        """Find files matching glob pattern.

        Args:
            pattern: Glob pattern (e.g., "**/*.jsonl")
            path: Base directory

        Returns:
            Dict with matching files
        """
        abs_path, rel_path = self._resolve_path(path)

        if not abs_path.is_dir():
            raise ToolError(f"Not a directory: {rel_path}")

        matches = []
        for entry in sorted(abs_path.glob(pattern)):
            if entry.is_file():
                entry_rel = str(entry.relative_to(self.root))
                if self._is_allowed(entry_rel):
                    matches.append({
                        "path": entry_rel,
                        "size": entry.stat().st_size,
                    })

        return {
            "pattern": pattern,
            "base_path": rel_path,
            "matches": matches,
            "count": len(matches),
        }

    def grep(self, pattern: str, path: str = ".", file_pattern: str = "*.jsonl") -> Dict[str, Any]:
        """Search for pattern in files.

        Args:
            pattern: Regex pattern to search for
            path: Directory to search in
            file_pattern: Glob pattern for files to search

        Returns:
            Dict with matches
        """
        abs_path, rel_path = self._resolve_path(path)

        if not abs_path.is_dir():
            # Single file
            return self._grep_file(abs_path, rel_path, pattern)

        matches = []
        regex = re.compile(pattern, re.IGNORECASE)

        for file_path in abs_path.glob(file_pattern):
            if not file_path.is_file():
                continue

            file_rel = str(file_path.relative_to(self.root))
            if not self._is_allowed(file_rel):
                continue

            try:
                content = file_path.read_text(encoding="utf-8")
                for i, line in enumerate(content.split("\n"), 1):
                    if regex.search(line):
                        matches.append({
                            "file": file_rel,
                            "line_number": i,
                            "content": line[:200],  # Truncate long lines
                        })
            except (UnicodeDecodeError, Exception):
                continue

        return {
            "pattern": pattern,
            "path": rel_path,
            "file_pattern": file_pattern,
            "matches": matches[:50],  # Limit results
            "total_matches": len(matches),
        }

    def _grep_file(self, abs_path: Path, rel_path: str, pattern: str) -> Dict[str, Any]:
        """Grep a single file."""
        matches = []
        regex = re.compile(pattern, re.IGNORECASE)

        try:
            content = abs_path.read_text(encoding="utf-8")
            for i, line in enumerate(content.split("\n"), 1):
                if regex.search(line):
                    matches.append({
                        "line_number": i,
                        "content": line[:200],
                    })
        except Exception as e:
            raise ToolError(f"Grep error: {e}")

        return {
            "pattern": pattern,
            "file": rel_path,
            "matches": matches,
            "total_matches": len(matches),
        }


# Tool definitions for Anthropic API
TOOL_DEFINITIONS = [
    {
        "name": "read_file",
        "description": "Read the contents of a file. Use this to view any file in the Control Plane.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file (relative to Control Plane root or absolute)"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of lines to return (optional)"
                },
                "offset": {
                    "type": "integer",
                    "description": "Line number to start from (optional, 0-indexed)"
                }
            },
            "required": ["path"]
        }
    },
    {
        "name": "list_directory",
        "description": "List contents of a directory.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory path (default: current directory)"
                },
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern to filter entries (default: *)"
                }
            },
            "required": []
        }
    },
    {
        "name": "glob",
        "description": "Find files matching a glob pattern. Use ** for recursive matching.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern (e.g., '**/*.jsonl', 'ledger/*.jsonl')"
                },
                "path": {
                    "type": "string",
                    "description": "Base directory to search from (default: root)"
                }
            },
            "required": ["pattern"]
        }
    },
    {
        "name": "grep",
        "description": "Search for a pattern in files. Returns matching lines.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Regex pattern to search for"
                },
                "path": {
                    "type": "string",
                    "description": "Directory or file to search in"
                },
                "file_pattern": {
                    "type": "string",
                    "description": "Glob pattern for files to search (default: *.jsonl)"
                }
            },
            "required": ["pattern"]
        }
    }
]


def execute_tool(tools: AdminTools, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a tool by name.

    Args:
        tools: AdminTools instance
        name: Tool name
        args: Tool arguments

    Returns:
        Tool result dict
    """
    if name == "read_file":
        return tools.read_file(
            path=args["path"],
            limit=args.get("limit"),
            offset=args.get("offset", 0)
        )
    elif name == "list_directory":
        return tools.list_directory(
            path=args.get("path", "."),
            pattern=args.get("pattern", "*")
        )
    elif name == "glob":
        return tools.glob(
            pattern=args["pattern"],
            path=args.get("path", ".")
        )
    elif name == "grep":
        return tools.grep(
            pattern=args["pattern"],
            path=args.get("path", "."),
            file_pattern=args.get("file_pattern", "*.jsonl")
        )
    else:
        raise ToolError(f"Unknown tool: {name}")
