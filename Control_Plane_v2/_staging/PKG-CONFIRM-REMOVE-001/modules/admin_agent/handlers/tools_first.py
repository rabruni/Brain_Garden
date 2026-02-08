"""Tools-First Handlers.

Deterministic handlers that use trace.py and registries directly.
No LLM calls are made in these handlers.

Provides full transparency into the Control Plane:
- Read any file
- List frameworks, specs, packages
- Browse directories
- View ledger contents

Example:
    from modules.admin_agent.handlers.tools_first import list_installed

    result = list_installed(agent, {"query": "What packages?"})
"""

import csv
import json
import re
from pathlib import Path
from typing import Any, Dict

from modules.admin_agent.agent import AdminAgent


def list_installed(agent: AdminAgent, context: Dict[str, Any]) -> str:
    """List installed packages.

    Args:
        agent: AdminAgent instance
        context: Query context with extracted args

    Returns:
        Formatted package list
    """
    return agent.list_installed()


def explain(agent: AdminAgent, context: Dict[str, Any]) -> str:
    """Explain an artifact.

    Args:
        agent: AdminAgent instance
        context: Query context with extracted args

    Returns:
        Artifact explanation
    """
    artifact_id = context.get("artifact_id")
    if not artifact_id:
        # Try to extract from query
        query = context.get("query", "")
        artifact_id = _extract_artifact_id(query)

    if not artifact_id:
        return "Error: No artifact ID provided"

    return agent.explain(artifact_id)


def check_health(agent: AdminAgent, context: Dict[str, Any]) -> str:
    """Check system health.

    Args:
        agent: AdminAgent instance
        context: Query context

    Returns:
        Health check results
    """
    return agent.check_health()


def inventory(agent: AdminAgent, context: Dict[str, Any]) -> str:
    """Get system inventory.

    Args:
        agent: AdminAgent instance
        context: Query context

    Returns:
        Inventory summary
    """
    trace_result = agent._run_trace("--inventory")

    if "error" in trace_result:
        return f"Error: {trace_result['error']}"

    health = trace_result.get("health", "unknown")
    total = trace_result.get("total_files", 0)
    orphans = trace_result.get("orphans", 0)

    return f"# Inventory\n\n**Health:** {health}\n**Total files:** {total}\n**Orphans:** {orphans}"


def show_ledger(agent: AdminAgent, context: Dict[str, Any]) -> str:
    """Show recent ledger entries.

    Args:
        agent: AdminAgent instance
        context: Query context

    Returns:
        Formatted ledger entries
    """
    import json
    from pathlib import Path

    ledger_dir = agent.root / "ledger"
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

    lines = ["# Recent Ledger Activity", ""]

    # Group by type
    governance = [f for f in ledger_files if "governance" in f.name]
    packages = [f for f in ledger_files if "packages" in f.name]
    kernel = [f for f in ledger_files if "kernel" in f.name]
    llm = [f for f in ledger_files if f.name == "llm.jsonl"]

    lines.append(f"**Total ledger files:** {len(ledger_files)}")
    lines.append(f"- Governance: {len(governance)}")
    lines.append(f"- Packages: {len(packages)}")
    lines.append(f"- Kernel: {len(kernel)}")
    lines.append(f"- LLM Calls: {len(llm)}")
    lines.append("")

    # Show recent LLM calls with prompt tracking (most relevant for transparency)
    if llm:
        lines.append("## Recent LLM Calls (Prompt Tracking)")
        lines.append("")
        llm_file = llm[0]
        lines.append(f"*From `{llm_file.name}`*")
        lines.append("")

        try:
            with open(llm_file) as f:
                entries = [json.loads(line) for line in f if line.strip()]

            if entries:
                lines.append("| Timestamp | Prompt Used | Model | Tokens |")
                lines.append("|-----------|-------------|-------|--------|")

                for entry in entries[-10:]:
                    timestamp = entry.get("timestamp", "")[:19]
                    prompts = entry.get("prompts_used", [])
                    prompt_id = prompts[0] if prompts else "none"
                    metadata = entry.get("metadata", {})
                    model = metadata.get("model", "?")
                    usage = metadata.get("usage", {})
                    tokens = f"{usage.get('input_tokens', 0)}\u2192{usage.get('output_tokens', 0)}"
                    lines.append(f"| `{timestamp}` | `{prompt_id}` | {model} | {tokens} |")

                lines.append("")
                lines.append(f"*Total LLM calls logged: {len(entries)}*")
            else:
                lines.append("*No LLM calls recorded yet*")

        except Exception as e:
            lines.append(f"Error: {e}")

        lines.append("")

    # Show recent entries from governance ledger
    if governance:
        lines.append("## Recent Governance Events")
        lines.append("")
        recent_file = governance[0]
        lines.append(f"*From `{recent_file.name}`*")
        lines.append("")

        try:
            with open(recent_file) as f:
                entries = [json.loads(line) for line in f if line.strip()]

            for entry in entries[-5:]:
                event_type = entry.get("event_type", entry.get("type", "event"))
                timestamp = entry.get("timestamp", "")[:19]
                lines.append(f"- `{timestamp}` **{event_type}**")

                if "package_id" in entry:
                    lines.append(f"  Package: {entry['package_id']}")
                if "message" in entry:
                    lines.append(f"  {entry['message'][:60]}")

        except Exception as e:
            lines.append(f"Error: {e}")

    # Show recent package events
    if packages:
        lines.append("")
        lines.append("## Recent Package Events")
        lines.append("")
        recent_file = packages[0]

        try:
            with open(recent_file) as f:
                entries = [json.loads(line) for line in f if line.strip()]

            for entry in entries[-3:]:
                event_type = entry.get("event_type", "event")
                pkg_id = entry.get("package_id", "?")
                timestamp = entry.get("timestamp", "")[:19]
                lines.append(f"- `{timestamp}` **{event_type}** - {pkg_id}")

        except Exception as e:
            lines.append(f"Error: {e}")

    return "\n".join(lines)


def show_session_ledger(agent: AdminAgent, context: Dict[str, Any]) -> str:
    """Show ledger entries for the current session.

    Reads the exec.jsonl file from the current session and displays
    the query/response entries with their content.

    Args:
        agent: AdminAgent instance
        context: Query context with session

    Returns:
        Formatted session ledger entries
    """
    session = context.get("session")

    if not session:
        return "Error: No active session available. Session ledger can only be viewed during an active session."

    ledger_path = session.exec_ledger_path

    if not ledger_path.exists():
        return f"No ledger found for session {session.session_id}."

    lines = [f"# Session Ledger: {session.session_id}", ""]
    lines.append(f"*Tier:* {session.tier}")
    lines.append(f"*Path:* `{ledger_path}`")
    lines.append("")

    try:
        with open(ledger_path) as f:
            entries = [json.loads(line) for line in f if line.strip()]

        if not entries:
            lines.append("*No entries yet in this session.*")
            return "\n".join(lines)

        lines.append(f"**Total entries:** {len(entries)}")
        lines.append("")

        for i, entry in enumerate(entries, 1):
            event_type = entry.get("event_type", "unknown")
            turn_number = entry.get("turn_number", "?")
            timestamp = entry.get("timestamp", "")[:19]
            content = entry.get("content", "")
            status = entry.get("status", "")

            # Format based on event type
            if event_type == "user_query":
                lines.append(f"### Entry {i}: Turn {turn_number} - User Query")
                lines.append(f"*{timestamp}*")
                lines.append("")
                lines.append("```")
                # Truncate long content for display
                if len(content) > 200:
                    lines.append(content[:200] + "...")
                else:
                    lines.append(content)
                lines.append("```")
            elif event_type == "agent_response":
                lines.append(f"### Entry {i}: Turn {turn_number} - Agent Response")
                lines.append(f"*{timestamp}* (status: {status})")
                lines.append("")
                lines.append("```")
                # Truncate long content for display
                if len(content) > 500:
                    lines.append(content[:500] + "...")
                else:
                    lines.append(content)
                lines.append("```")
            else:
                # Legacy or other entry types
                lines.append(f"### Entry {i}: Turn {turn_number} - {event_type}")
                lines.append(f"*{timestamp}*")
                if status:
                    lines.append(f"Status: {status}")

            lines.append("")

    except Exception as e:
        return f"Error reading session ledger: {e}"

    return "\n".join(lines)


def show_prompts_used(agent: AdminAgent, context: Dict[str, Any]) -> str:
    """Show governed prompts used in LLM calls.

    Provides full transparency into which governed prompts were used,
    when they were called, and the associated evidence hashes.

    Args:
        agent: AdminAgent instance
        context: Query context

    Returns:
        Formatted prompt usage report
    """
    import json
    from pathlib import Path

    llm_ledger = agent.root / "ledger" / "llm.jsonl"

    if not llm_ledger.exists():
        return "No LLM calls recorded yet. The L-LLM ledger (`ledger/llm.jsonl`) will be created when LLM completions are made."

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
            lines.append(f"- **Tokens:** {usage.get('input_tokens', 0)} in \u2192 {usage.get('output_tokens', 0)} out")
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


def _extract_artifact_id(query: str) -> str:
    """Extract artifact ID from query.

    Args:
        query: User query string

    Returns:
        Extracted artifact ID or empty string
    """
    import re

    patterns = [
        r"(FMWK-[\w-]+)",
        r"(SPEC-[\w-]+)",
        r"(PKG-[\w-]+)",
        r"(lib/[\w/]+\.py)",
        r"(scripts/[\w/]+\.py)",
        r"([\w/]+\.py)",
        r"([\w/]+\.md)",
    ]

    for pattern in patterns:
        match = re.search(pattern, query, re.IGNORECASE)
        if match:
            return match.group(1)

    # Last word as fallback
    words = query.split()
    if words:
        return words[-1]

    return ""


def _extract_file_path(query: str) -> str:
    """Extract file path from query.

    Args:
        query: User query string

    Returns:
        Extracted file path or empty string
    """
    # Look for file paths with extensions
    patterns = [
        r"([\w/.-]+\.(?:py|md|json|csv|yaml|yml|txt|jsonl))",
        r"(lib/[\w/.-]+)",
        r"(scripts/[\w/.-]+)",
        r"(modules/[\w/.-]+)",
        r"(config/[\w/.-]+)",
        r"(registries/[\w/.-]+)",
        r"(frameworks/[\w/.-]+)",
        r"(ledger/[\w/.-]+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, query, re.IGNORECASE)
        if match:
            return match.group(1)

    return ""


def _extract_dir_path(query: str) -> str:
    """Extract directory path from query.

    Args:
        query: User query string

    Returns:
        Extracted directory path or empty string
    """
    patterns = [
        r"(?:in|browse|ls)\s+([\w/.-]+)",
        r"(lib|scripts|modules|config|registries|frameworks|ledger|specs|schemas|tests)/?",
    ]

    for pattern in patterns:
        match = re.search(pattern, query, re.IGNORECASE)
        if match:
            return match.group(1)

    return ""


def read_file(agent: AdminAgent, context: Dict[str, Any]) -> str:
    """Read and display a file's contents.

    Args:
        agent: AdminAgent instance
        context: Query context

    Returns:
        File contents with formatting
    """
    query = context.get("query", "")
    file_path = _extract_file_path(query)

    if not file_path:
        return "Please specify a file path. Example: 'read lib/auth.py'"

    # Resolve path relative to control plane root
    full_path = agent.root / file_path

    if not full_path.exists():
        # Try without leading slash
        full_path = agent.root / file_path.lstrip("/")

    if not full_path.exists():
        return f"File not found: {file_path}"

    if not full_path.is_file():
        return f"Not a file: {file_path}"

    # Read file
    try:
        content = full_path.read_text()
        lines = content.split("\n")
        total_lines = len(lines)

        # Truncate if too long
        max_lines = 100
        if total_lines > max_lines:
            content = "\n".join(lines[:max_lines])
            truncated = f"\n\n*... truncated ({total_lines - max_lines} more lines)*"
        else:
            truncated = ""

        # Determine language for syntax highlighting
        ext = full_path.suffix
        lang = {
            ".py": "python",
            ".json": "json",
            ".md": "markdown",
            ".csv": "csv",
            ".yaml": "yaml",
            ".yml": "yaml",
        }.get(ext, "")

        return f"# {file_path}\n\n**Lines:** {total_lines}\n\n```{lang}\n{content}\n```{truncated}"

    except Exception as e:
        return f"Error reading file: {e}"


def list_frameworks(agent: AdminAgent, context: Dict[str, Any]) -> str:
    """List all frameworks in the registry.

    Args:
        agent: AdminAgent instance
        context: Query context

    Returns:
        Formatted framework list
    """
    registry_path = agent.root / "registries" / "frameworks_registry.csv"

    if not registry_path.exists():
        return "Frameworks registry not found."

    lines = ["# Frameworks", ""]
    lines.append("| ID | Title | Status | Version |")
    lines.append("|-----|-------|--------|---------|")

    try:
        with open(registry_path) as f:
            reader = csv.DictReader(f)
            for row in reader:
                fid = row.get("framework_id", "?")
                title = row.get("title", "?")
                status = row.get("status", "?")
                version = row.get("version", "?")
                lines.append(f"| {fid} | {title} | {status} | {version} |")

    except Exception as e:
        return f"Error reading frameworks: {e}"

    return "\n".join(lines)


def list_specs(agent: AdminAgent, context: Dict[str, Any]) -> str:
    """List all specifications in the registry.

    Args:
        agent: AdminAgent instance
        context: Query context

    Returns:
        Formatted specs list
    """
    registry_path = agent.root / "registries" / "specs_registry.csv"

    if not registry_path.exists():
        return "Specs registry not found."

    lines = ["# Specifications", ""]
    lines.append("| ID | Title | Framework | Status |")
    lines.append("|-----|-------|-----------|--------|")

    try:
        with open(registry_path) as f:
            reader = csv.DictReader(f)
            for row in reader:
                sid = row.get("spec_id", "?")
                title = row.get("title", "?")
                fid = row.get("framework_id", "?")
                status = row.get("status", "?")
                lines.append(f"| {sid} | {title} | {fid} | {status} |")

    except Exception as e:
        return f"Error reading specs: {e}"

    return "\n".join(lines)


def list_files(agent: AdminAgent, context: Dict[str, Any]) -> str:
    """List files in a directory.

    Args:
        agent: AdminAgent instance
        context: Query context

    Returns:
        Directory listing
    """
    query = context.get("query", "")
    dir_path = _extract_dir_path(query)

    if not dir_path:
        # Default to listing top-level
        dir_path = "."

    full_path = agent.root / dir_path

    if not full_path.exists():
        return f"Directory not found: {dir_path}"

    if not full_path.is_dir():
        return f"Not a directory: {dir_path}"

    lines = [f"# Contents of `{dir_path}/`", ""]

    try:
        items = sorted(full_path.iterdir(), key=lambda p: (not p.is_dir(), p.name))

        dirs = []
        files = []

        for item in items:
            # Skip hidden and pycache
            if item.name.startswith(".") or item.name == "__pycache__":
                continue

            if item.is_dir():
                dirs.append(f"\U0001f4c1 {item.name}/")
            else:
                size = item.stat().st_size
                if size > 1024:
                    size_str = f"{size // 1024}KB"
                else:
                    size_str = f"{size}B"
                files.append(f"\U0001f4c4 {item.name} ({size_str})")

        if dirs:
            lines.append("**Directories:**")
            for d in dirs[:20]:
                lines.append(f"- {d}")
            if len(dirs) > 20:
                lines.append(f"- *... and {len(dirs) - 20} more*")
            lines.append("")

        if files:
            lines.append("**Files:**")
            for f in files[:30]:
                lines.append(f"- {f}")
            if len(files) > 30:
                lines.append(f"- *... and {len(files) - 30} more*")

        if not dirs and not files:
            lines.append("*Empty directory*")

    except Exception as e:
        return f"Error listing directory: {e}"

    return "\n".join(lines)
