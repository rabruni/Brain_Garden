"""Search Handlers.

Handler for code search operations.

Example:
    result = search_code({"search_pattern": "LedgerClient"}, "search for LedgerClient", session)
"""

import subprocess
import sys
from pathlib import Path
from typing import Any, Dict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from modules.chat_interface.registry import register
from modules.chat_interface.classifier import extract_search_pattern


@register(
    "search_code",
    description="Search for patterns in the codebase",
    category="browse",
    patterns=["search for X", "grep X", "find X in"],
)
def search_code(context: Dict[str, Any], query: str, session) -> str:
    """Search for patterns in code.

    Uses grep to find matches in the codebase.

    Args:
        context: Query context (may have search_pattern)
        query: Original query
        session: ChatSession instance

    Returns:
        Search results
    """
    pattern = context.get("search_pattern") or extract_search_pattern(query)

    if not pattern:
        return (
            "Please specify a search pattern.\n\n"
            "**Examples:**\n"
            "- `search for LedgerClient`\n"
            "- `grep 'def hash_'`\n"
            "- `find all imports`"
        )

    lines = [f"# Search: `{pattern}`", ""]

    # Search paths (skip non-code directories)
    search_dirs = ["lib", "scripts", "modules", "frameworks", "specs"]
    exclude_dirs = ["__pycache__", ".git", "node_modules", "_staging"]

    try:
        # Build grep command
        # Use grep -r for recursive search
        cmd = [
            "grep",
            "-r",  # Recursive
            "-n",  # Line numbers
            "-I",  # Skip binary files
            "--include=*.py",
            "--include=*.md",
            "--include=*.json",
            "--include=*.yaml",
            "--include=*.yml",
        ]

        # Add exclude patterns
        for d in exclude_dirs:
            cmd.append(f"--exclude-dir={d}")

        cmd.append(pattern)
        cmd.extend(search_dirs)

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(session.root),
            timeout=30,
        )

        output = result.stdout.strip()

        if not output:
            return f"No matches found for: `{pattern}`"

        # Parse and format results
        matches = output.split("\n")
        total_matches = len(matches)

        # Group by file
        by_file: Dict[str, list] = {}
        for match in matches[:100]:  # Limit to first 100
            if ":" not in match:
                continue
            parts = match.split(":", 2)
            if len(parts) >= 3:
                file_path, line_num, content = parts[0], parts[1], parts[2]
                if file_path not in by_file:
                    by_file[file_path] = []
                by_file[file_path].append((line_num, content.strip()[:80]))

        lines.append(f"**Found {total_matches} matches in {len(by_file)} files**")
        lines.append("")

        for file_path, file_matches in list(by_file.items())[:20]:
            lines.append(f"### {file_path}")
            lines.append("")
            for line_num, content in file_matches[:5]:
                lines.append(f"- Line {line_num}: `{content}`")
            if len(file_matches) > 5:
                lines.append(f"- *... and {len(file_matches) - 5} more in this file*")
            lines.append("")

        if len(by_file) > 20:
            lines.append(f"*... and {len(by_file) - 20} more files*")

        if total_matches > 100:
            lines.append(f"\n*Showing first 100 of {total_matches} matches*")

    except subprocess.TimeoutExpired:
        return f"Search timed out for: `{pattern}`"
    except FileNotFoundError:
        # grep not available, fall back to Python
        return _python_search(pattern, session)
    except Exception as e:
        return f"Search error: {e}"

    return "\n".join(lines)


def _python_search(pattern: str, session) -> str:
    """Fallback Python-based search."""
    import re

    lines = [f"# Search: `{pattern}` (Python fallback)", ""]

    try:
        regex = re.compile(pattern, re.IGNORECASE)
    except re.error:
        # Treat as literal string
        regex = re.compile(re.escape(pattern), re.IGNORECASE)

    matches = []
    search_dirs = ["lib", "scripts", "modules"]
    extensions = {".py", ".md", ".json", ".yaml", ".yml"}

    for search_dir in search_dirs:
        dir_path = session.root / search_dir
        if not dir_path.exists():
            continue

        for file_path in dir_path.rglob("*"):
            if file_path.suffix not in extensions:
                continue
            if "__pycache__" in str(file_path):
                continue

            try:
                content = file_path.read_text(errors="ignore")
                for i, line in enumerate(content.split("\n"), 1):
                    if regex.search(line):
                        rel_path = file_path.relative_to(session.root)
                        matches.append((str(rel_path), i, line.strip()[:80]))
                        if len(matches) >= 100:
                            break
            except Exception:
                continue

            if len(matches) >= 100:
                break

    if not matches:
        return f"No matches found for: `{pattern}`"

    lines.append(f"**Found {len(matches)} matches**")
    lines.append("")

    for path, line_num, content in matches[:50]:
        lines.append(f"- `{path}:{line_num}`: `{content}`")

    if len(matches) > 50:
        lines.append(f"\n*... and {len(matches) - 50} more*")

    return "\n".join(lines)
