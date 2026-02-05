"""Ledger Handlers.

Handler for ledger query operations.

Example:
    result = ledger_query({}, "show ledger", session)
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from modules.chat_interface.registry import register


@register(
    "ledger_query",
    description="Query ledger entries and activity",
    category="system",
    patterns=["show ledger", "ledger entries", "recent activity", "audit log"],
)
def ledger_query(context: Dict[str, Any], query: str, session) -> str:
    """Query ledger entries.

    Shows recent entries from governance, packages, and kernel ledgers.

    Args:
        context: Query context
        query: Original query
        session: ChatSession instance

    Returns:
        Formatted ledger entries
    """
    lines = ["# Ledger Activity", ""]

    ledger_dir = session.root / "ledger"
    if not ledger_dir.exists():
        return "No ledger directory found."

    # Find ledger files (exclude index files)
    ledger_files = [
        f for f in ledger_dir.glob("*.jsonl")
        if not f.name.startswith("index")
    ]
    ledger_files = sorted(ledger_files, key=lambda p: p.stat().st_mtime, reverse=True)

    if not ledger_files:
        return "No ledger files found."

    # Group by type
    governance = [f for f in ledger_files if "governance" in f.name]
    packages = [f for f in ledger_files if "packages" in f.name]
    kernel = [f for f in ledger_files if "kernel" in f.name]

    lines.append(f"**Ledger files:** {len(ledger_files)} total")
    lines.append(f"- Governance: {len(governance)}")
    lines.append(f"- Packages: {len(packages)}")
    lines.append(f"- Kernel: {len(kernel)}")
    lines.append("")

    # Show recent governance entries
    if governance:
        lines.append("## Recent Governance Events")
        lines.append("")
        recent_file = governance[0]
        lines.append(f"*From `{recent_file.name}`*")
        lines.append("")

        try:
            with open(recent_file) as f:
                entries = [json.loads(line) for line in f if line.strip()]

            for entry in entries[-10:]:
                event_type = entry.get("event_type", entry.get("type", "event"))
                timestamp = entry.get("timestamp", "")[:19]
                submission_id = entry.get("submission_id", "")
                decision = entry.get("decision", "")

                lines.append(f"- `{timestamp}` **{event_type}**")
                if submission_id:
                    lines.append(f"  - ID: {submission_id}")
                if decision:
                    lines.append(f"  - Decision: {decision}")

        except Exception as e:
            lines.append(f"*Error reading: {e}*")

    # Show recent package events
    if packages:
        lines.append("")
        lines.append("## Recent Package Events")
        lines.append("")
        recent_file = packages[0]

        try:
            with open(recent_file) as f:
                entries = [json.loads(line) for line in f if line.strip()]

            for entry in entries[-5:]:
                event_type = entry.get("event_type", "event")
                pkg_id = entry.get("package_id", entry.get("metadata", {}).get("package_id", "?"))
                timestamp = entry.get("timestamp", "")[:19]
                lines.append(f"- `{timestamp}` **{event_type}** - {pkg_id}")

        except Exception as e:
            lines.append(f"*Error reading: {e}*")

    # Show session ledgers if any exist
    sessions_dir = session.root / "planes" / session.tier / "sessions"
    if sessions_dir.exists():
        session_count = len(list(sessions_dir.glob("SES-*")))
        if session_count > 0:
            lines.append("")
            lines.append(f"## Session Ledgers")
            lines.append("")
            lines.append(f"**Active sessions:** {session_count}")

            # Show recent sessions
            recent_sessions = sorted(
                sessions_dir.glob("SES-*"),
                key=lambda p: p.stat().st_mtime,
                reverse=True
            )[:5]

            for sess_dir in recent_sessions:
                ledger_file = sess_dir / "ledger" / "chat.jsonl"
                if ledger_file.exists():
                    try:
                        with open(ledger_file) as f:
                            count = sum(1 for _ in f)
                        lines.append(f"- `{sess_dir.name}`: {count} entries")
                    except Exception:
                        lines.append(f"- `{sess_dir.name}`: ?")

    return "\n".join(lines)


@register(
    "prompts_query",
    description="Show governed prompts used in LLM calls",
    category="system",
    patterns=["show prompts", "prompt usage", "llm calls", "which prompts used"],
)
def prompts_query(context: Dict[str, Any], query: str, session) -> str:
    """Show governed prompt usage from L-LLM ledger.

    Provides full transparency into which governed prompts were used,
    when they were called, and the associated evidence hashes.

    Args:
        context: Query context
        query: Original query
        session: ChatSession instance

    Returns:
        Formatted prompt usage report
    """
    llm_ledger = session.root / "ledger" / "llm.jsonl"

    if not llm_ledger.exists():
        return (
            "# Governed Prompt Tracking\n\n"
            "No LLM calls recorded yet.\n\n"
            "The L-LLM ledger (`ledger/llm.jsonl`) will be created when "
            "LLM completions are made using governed prompts.\n\n"
            "Available governed prompts:\n"
            "- `PRM-CLASSIFY-001` - Query classification\n"
            "- `PRM-ADMIN-EXPLAIN-001` - Artifact explanation\n"
            "- `PRM-ADMIN-VALIDATE-001` - Document validation"
        )

    lines = ["# Governed Prompt Usage Report", ""]
    lines.append("*All LLM calls must use governed prompts for transparency and audit.*")
    lines.append("")

    try:
        with open(llm_ledger) as f:
            entries = [json.loads(line) for line in f if line.strip()]

        if not entries:
            return "No LLM calls recorded yet."

        # Summary by prompt
        prompt_counts = {}
        for entry in entries:
            for prompt_id in entry.get("prompts_used", []):
                prompt_counts[prompt_id] = prompt_counts.get(prompt_id, 0) + 1

        lines.append("## Prompt Usage Summary")
        lines.append("")
        lines.append("| Governed Prompt | Times Used |")
        lines.append("|-----------------|------------|")
        for prompt_id, count in sorted(prompt_counts.items(), key=lambda x: -x[1]):
            lines.append(f"| `{prompt_id}` | {count} |")

        lines.append("")
        lines.append(f"**Total LLM calls:** {len(entries)}")
        lines.append(f"**Unique prompts used:** {len(prompt_counts)}")
        lines.append("")

        # Recent calls with full details
        lines.append("## Recent LLM Calls (Last 10)")
        lines.append("")

        for entry in entries[-10:]:
            timestamp = entry.get("timestamp", "")[:19]
            prompts = entry.get("prompts_used", [])
            prompt_id = prompts[0] if prompts else "none"
            metadata = entry.get("metadata", {})
            model = metadata.get("model", "?")
            provider = metadata.get("provider_id", "?")
            usage = metadata.get("usage", {})
            duration = metadata.get("duration_ms", 0)

            # Get actual content (full transparency)
            prompt_text = metadata.get("prompt_text", "")
            response_text = metadata.get("response_text", "")

            # Truncate for display if very long
            if len(prompt_text) > 500:
                prompt_text = prompt_text[:500] + "..."
            if len(response_text) > 500:
                response_text = response_text[:500] + "..."

            lines.append(f"### `{timestamp}`")
            lines.append(f"- **Governed Prompt:** `{prompt_id}`")
            lines.append(f"- **Model:** {model} (via {provider})")
            lines.append(f"- **Tokens:** {usage.get('input_tokens', 0)} in → {usage.get('output_tokens', 0)} out")
            lines.append(f"- **Duration:** {duration}ms")
            lines.append("")
            if prompt_text:
                lines.append("**Prompt sent:**")
                lines.append(f"```")
                lines.append(prompt_text)
                lines.append(f"```")
                lines.append("")
            if response_text:
                lines.append("**Response received:**")
                lines.append(f"```")
                lines.append(response_text)
                lines.append(f"```")
            lines.append("")
            lines.append("---")
            lines.append("")

    except Exception as e:
        return f"Error reading LLM ledger: {e}"

    return "\n".join(lines)
