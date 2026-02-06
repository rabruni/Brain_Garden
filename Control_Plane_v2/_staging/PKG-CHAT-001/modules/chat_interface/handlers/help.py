"""Help Handler.

Handler for displaying available commands and help information.

Example:
    result = help_handler({}, "help", session)
"""

import sys
from pathlib import Path
from typing import Any, Dict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from modules.chat_interface.registry import register, HandlerRegistry


@register(
    "help",
    description="Show available commands and help",
    category="system",
    patterns=["help", "commands", "what can you do", "usage"],
)
def help_handler(context: Dict[str, Any], query: str, session) -> str:
    """Show help and available commands.

    Lists all registered handlers grouped by category.

    Args:
        context: Query context
        query: Original query
        session: ChatSession instance

    Returns:
        Help text
    """
    lines = ["# Available Commands", ""]

    # Group handlers by category
    by_category = HandlerRegistry.list_by_category()

    # Define category display order and descriptions
    category_info = {
        "browse": ("Browse & Read", "Explore files and directories"),
        "packages": ("Package Management", "Manage Control Plane packages"),
        "system": ("System", "System status and information"),
        "general": ("General", "Other commands"),
    }

    for category, (title, desc) in category_info.items():
        handlers = by_category.get(category, [])
        if not handlers:
            continue

        lines.append(f"## {title}")
        lines.append(f"*{desc}*")
        lines.append("")

        for handler in sorted(handlers, key=lambda h: h.name):
            capability = ""
            if handler.requires_capability:
                capability = f" [requires {handler.requires_capability}]"

            # Format patterns as examples
            examples = ""
            if handler.patterns:
                examples = f" (e.g., `{handler.patterns[0]}`)"

            lines.append(f"- **{handler.name}**: {handler.description}{capability}{examples}")

        lines.append("")

    # Add usage examples
    lines.append("## Quick Examples")
    lines.append("")
    lines.append("```")
    lines.append("# Browse directories")
    lines.append("what is in modules?")
    lines.append("ls lib")
    lines.append("")
    lines.append("# Read files")
    lines.append("read lib/auth.py")
    lines.append("show modules/chat_interface/registry.py")
    lines.append("")
    lines.append("# Search code")
    lines.append("search for LedgerClient")
    lines.append("grep 'def hash_'")
    lines.append("")
    lines.append("# Package management")
    lines.append("list packages")
    lines.append("inspect PKG-KERNEL-001")
    lines.append("")
    lines.append("# System info")
    lines.append("show ledger")
    lines.append("```")

    lines.append("")
    lines.append("---")
    lines.append(f"*Session: {session.session_id}*")

    return "\n".join(lines)
