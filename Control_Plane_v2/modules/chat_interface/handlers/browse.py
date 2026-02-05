"""Browse Handlers.

Handlers for file and directory browsing operations.
These provide full transparency into the Control Plane codebase.

Example:
    result = browse_dir({"dir_path": "modules"}, "what is in modules?", session)
"""

import sys
from pathlib import Path
from typing import Any, Dict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from modules.chat_interface.registry import register
from modules.chat_interface.classifier import extract_dir_path, extract_file_path
from lib.merkle import hash_file


@register(
    "browse_dir",
    description="List contents of a directory",
    category="browse",
    patterns=["what is in X", "list files in X", "ls X", "browse X"],
)
def browse_dir(context: Dict[str, Any], query: str, session) -> str:
    """List directory contents.

    Args:
        context: Query context with extracted args (may have dir_path)
        query: Original query string
        session: ChatSession instance

    Returns:
        Formatted directory listing
    """
    dir_path = context.get("dir_path") or extract_dir_path(query)

    if not dir_path:
        # Default to listing top-level
        dir_path = "."

    # Clean up path
    dir_path = dir_path.strip("/").strip()

    # Resolve path relative to control plane root
    full_path = session.root / dir_path

    if not full_path.exists():
        return f"Directory not found: `{dir_path}`\n\nTry: `ls modules`, `ls lib`, `ls config`"

    if not full_path.is_dir():
        return f"Not a directory: `{dir_path}`\n\nUse `read {dir_path}` to view file contents."

    lines = [f"# Contents of `{dir_path}/`", ""]

    try:
        items = sorted(full_path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))

        dirs = []
        files = []

        for item in items:
            # Skip hidden and pycache
            if item.name.startswith(".") or item.name == "__pycache__":
                continue

            if item.is_dir():
                dirs.append(item.name)
            else:
                size = item.stat().st_size
                if size >= 1024 * 1024:
                    size_str = f"{size / 1024 / 1024:.1f}MB"
                elif size >= 1024:
                    size_str = f"{size / 1024:.1f}KB"
                else:
                    size_str = f"{size}B"
                files.append((item.name, size_str))

        if dirs:
            lines.append("**Directories:**")
            for d in dirs[:30]:
                lines.append(f"- {d}/")
            if len(dirs) > 30:
                lines.append(f"- *... and {len(dirs) - 30} more*")
            lines.append("")

        if files:
            lines.append("**Files:**")
            for f, size in files[:50]:
                lines.append(f"- {f} ({size})")
            if len(files) > 50:
                lines.append(f"- *... and {len(files) - 50} more*")

        if not dirs and not files:
            lines.append("*Empty directory*")

        # Record as evidence
        session.record_read(dir_path, f"sha256:dir_listing_{len(dirs)}d_{len(files)}f")

    except PermissionError:
        return f"Permission denied: `{dir_path}`"
    except Exception as e:
        return f"Error listing directory: {e}"

    return "\n".join(lines)


@register(
    "browse_code",
    description="Read and display a file's contents",
    category="browse",
    patterns=["read X", "show X", "cat X", "view X"],
)
def browse_code(context: Dict[str, Any], query: str, session) -> str:
    """Read and display file contents.

    Args:
        context: Query context with extracted args (may have file_path)
        query: Original query string
        session: ChatSession instance

    Returns:
        File contents with formatting
    """
    file_path = context.get("file_path") or extract_file_path(query)

    if not file_path:
        return (
            "Please specify a file path.\n\n"
            "**Examples:**\n"
            "- `read lib/auth.py`\n"
            "- `show modules/chat_interface/registry.py`\n"
            "- `cat config/control_plane_chain.json`"
        )

    # Clean up path
    file_path = file_path.strip("/").strip()

    # Resolve path relative to control plane root
    full_path = session.root / file_path

    if not full_path.exists():
        # Try without leading components
        alternatives = [
            session.root / file_path.lstrip("/"),
            session.root / "lib" / file_path,
            session.root / "scripts" / file_path,
            session.root / "modules" / file_path,
        ]
        for alt in alternatives:
            if alt.exists():
                full_path = alt
                file_path = str(alt.relative_to(session.root))
                break
        else:
            return f"File not found: `{file_path}`"

    if not full_path.is_file():
        return f"Not a file: `{file_path}`\n\nUse `ls {file_path}` to list directory contents."

    # Check file size
    file_size = full_path.stat().st_size
    if file_size > 100 * 1024:  # 100KB
        return (
            f"File too large to display: `{file_path}` ({file_size / 1024:.1f}KB)\n\n"
            f"This file exceeds the 100KB limit for inline display."
        )

    try:
        content = full_path.read_text(encoding="utf-8", errors="replace")
        lines = content.split("\n")
        total_lines = len(lines)

        # Truncate if too many lines
        max_lines = 150
        if total_lines > max_lines:
            content = "\n".join(lines[:max_lines])
            truncated = f"\n\n*... truncated ({total_lines - max_lines} more lines)*"
        else:
            truncated = ""

        # Determine language for syntax highlighting
        ext = full_path.suffix.lower()
        lang_map = {
            ".py": "python",
            ".json": "json",
            ".jsonl": "json",
            ".md": "markdown",
            ".csv": "csv",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".txt": "",
            ".sh": "bash",
            ".js": "javascript",
            ".ts": "typescript",
        }
        lang = lang_map.get(ext, "")

        # Record as evidence
        file_hash = hash_file(full_path)
        session.record_read(file_path, f"sha256:{file_hash}")

        return f"# {file_path}\n\n**Lines:** {total_lines} | **Size:** {file_size}B\n\n```{lang}\n{content}\n```{truncated}"

    except UnicodeDecodeError:
        return f"Cannot display binary file: `{file_path}`"
    except Exception as e:
        return f"Error reading file: {e}"
