"""Admin Agent implementation.

Wraps trace.py for low-level operations and provides human-friendly
explanations of Control Plane artifacts.

Example:
    from modules.admin_agent.agent import AdminAgent, admin_turn

    agent = AdminAgent()
    print(agent.explain("FMWK-000"))

    # Or use the turn function
    result = admin_turn("Explain FMWK-000")
"""

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from modules.stdlib_evidence import hash_json, build_evidence
from modules.agent_runtime.session import Session, generate_session_id
from modules.agent_runtime.sandbox import TurnSandbox
from modules.agent_runtime.ledger_writer import LedgerWriter


class AdminAgent:
    """Read-only agent for explaining the Control Plane."""

    def __init__(self, root: Optional[Path] = None):
        """Initialize Admin Agent.

        Args:
            root: Optional Control Plane root directory
        """
        self.root = root or self._get_default_root()
        self.trace_script = self.root / "scripts" / "trace.py"

    def _get_default_root(self) -> Path:
        """Get default Control Plane root."""
        current = Path(__file__).resolve()
        while current.name != "Control_Plane_v2" and current.parent != current:
            current = current.parent
        if current.name == "Control_Plane_v2":
            return current
        return Path.cwd()

    def _run_trace(self, *args) -> Dict[str, Any]:
        """Run trace.py with arguments and return JSON result.

        Args:
            *args: Arguments to pass to trace.py

        Returns:
            Parsed JSON output
        """
        cmd = [sys.executable, str(self.trace_script), "--json", *args]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=str(self.root),
                timeout=30,
            )
            if result.stdout:
                return json.loads(result.stdout)
            return {"error": result.stderr or "No output"}
        except json.JSONDecodeError:
            return {"error": "Failed to parse trace.py output", "raw": result.stdout}
        except subprocess.TimeoutExpired:
            return {"error": "trace.py timed out"}
        except Exception as e:
            return {"error": str(e)}

    def explain(self, artifact_id: str) -> str:
        """Explain any artifact (framework, spec, package, file).

        Args:
            artifact_id: ID or path to explain (e.g., FMWK-000, lib/merkle.py)

        Returns:
            Human-readable explanation
        """
        result = self._run_trace("--explain", artifact_id)

        if "error" in result:
            return f"Error: {result['error']}"

        data_type = result.get("type", "unknown")
        data = result.get("data", {})

        if data_type == "unknown":
            return f"Unknown artifact: {artifact_id}\n\n{data.get('message', 'Not found in registries.')}"

        return self._format_explanation(data_type, data)

    def _format_explanation(self, data_type: str, data: Dict) -> str:
        """Format explanation for human consumption.

        Args:
            data_type: Type of artifact (framework, spec, package, file)
            data: Data from trace.py

        Returns:
            Formatted string
        """
        lines = []

        if data_type == "framework":
            lines.append(f"# {data.get('framework_id', 'Unknown')}: {data.get('title', 'No title')}")
            lines.append("")
            lines.append(f"**Status:** {data.get('status', 'unknown')}")
            lines.append(f"**Specs:** {len(data.get('specs', []))} | **Files:** {data.get('total_files', 0)}")
            lines.append("")

            if data.get("specs"):
                lines.append("## Specifications")
                lines.append("")
                for spec in data["specs"]:
                    lines.append(f"- **{spec.get('spec_id', '?')}**: {spec.get('title', 'No title')}")

            if data.get("packages"):
                lines.append("")
                lines.append("## Packages")
                lines.append("")
                for pkg in data["packages"]:
                    lines.append(f"- {pkg}")

        elif data_type == "spec":
            lines.append(f"# {data.get('spec_id', 'Unknown')}: {data.get('title', 'No title')}")
            lines.append("")
            lines.append(f"**Status:** {data.get('status', 'unknown')}")

            fw = data.get("framework", {})
            if fw:
                lines.append(f"**Framework:** {fw.get('framework_id', '?')} ({fw.get('title', 'No title')})")

            if data.get("files"):
                lines.append("")
                lines.append("## Files")
                lines.append("")
                for f in data["files"]:
                    lines.append(f"- `{f.get('path', '?')}` ({f.get('package', 'no package')})")

        elif data_type == "package":
            lines.append(f"# {data.get('package_id', 'Unknown')}")
            lines.append("")

            tier_status = data.get("tier_status", {})
            if tier_status:
                lines.append("## Tier Status")
                lines.append("")
                for tier, status in tier_status.items():
                    icon = "+" if status == "installed" else "x"
                    lines.append(f"- {tier}: {icon} {status}")
                lines.append(f"\n**Parity:** {'Yes' if data.get('parity') else 'No'}")

            if data.get("files"):
                lines.append("")
                lines.append(f"## Contents ({len(data['files'])} files)")
                lines.append("")
                for f in data["files"][:10]:
                    lines.append(f"- `{f.get('path', '?')}`")
                if len(data["files"]) > 10:
                    lines.append(f"- ... and {len(data['files']) - 10} more")

        elif data_type == "file":
            lines.append(f"# {data.get('path', 'Unknown')}")
            lines.append("")

            if data.get("docstring"):
                lines.append(f"> {data['docstring'].split(chr(10))[0]}")
                lines.append("")

            own = data.get("ownership", {})
            lines.append("## Ownership Chain")
            lines.append("")
            lines.append("```")
            lines.append(f"{own.get('framework_id', '?')} ({own.get('framework_title', '')})")
            lines.append(f"  -> {own.get('spec_id', '?')} ({own.get('spec_title', '')})")
            lines.append(f"     -> {data.get('path', '?')}")
            lines.append(f"        -> {own.get('package', 'no package')}")
            lines.append("```")

            hash_info = data.get("hash", {})
            if hash_info.get("recorded"):
                verified = "verified" if hash_info.get("verified") else "MISMATCH"
                lines.append(f"\n**Hash:** {hash_info['recorded'][:30]}... ({verified})")

        return "\n".join(lines)

    def list_installed(self) -> str:
        """List installed packages with details.

        Returns:
            Formatted list of packages
        """
        result = self._run_trace("--installed")

        if "error" in result:
            return f"Error: {result['error']}"

        if not result:
            return "No packages installed."

        lines = ["# Installed Packages", "", f"**Total:** {len(result)} packages", ""]
        lines.append("| Package | Version | Files | Installed |")
        lines.append("|---------|---------|-------|-----------|")

        for pkg in result:
            version = pkg.get("version", "-")
            files = pkg.get("file_count", 0)
            installed = pkg.get("installed_at", "-")[:10] if pkg.get("installed_at") else "-"
            lines.append(f"| {pkg.get('package_id', '?')} | {version} | {files} | {installed} |")

        return "\n".join(lines)

    def check_health(self) -> str:
        """Check system health and return status.

        Returns:
            Health check results
        """
        result = self._run_trace("--verify")

        if "error" in result:
            return f"Error: {result['error']}"

        passed = result.get("passed", False)
        checks = result.get("checks", [])
        message = result.get("message", "Unknown")

        lines = ["# System Health", ""]
        overall = "PASS" if passed else "FAIL"
        lines.append(f"**Overall:** {overall}")
        lines.append("")

        if checks:
            lines.append("| Check | Status |")
            lines.append("|-------|--------|")
            for check in checks:
                icon = "+" if check.get("passed") else "x"
                status = "PASS" if check.get("passed") else "FAIL"
                lines.append(f"| {check.get('name', '?')} | {icon} {status} |")

        return "\n".join(lines)

    def get_context(self) -> Dict[str, Any]:
        """Get agent context for prompt headers.

        Returns:
            Context dictionary
        """
        return {
            "role": "admin_agent",
            "tier": "ho1",
            "mode": "read_only",
            "capabilities": ["explain", "list_installed", "check_health"],
        }


def _classify_query(query: str) -> str:
    """Classify query into handler type.

    Args:
        query: User query string

    Returns:
        Handler type: "explain", "list", "status", "inventory", or "general"
    """
    query_lower = query.lower()

    # Explain queries
    explain_patterns = [
        r"explain\s+",
        r"what\s+is\s+",
        r"describe\s+",
        r"tell\s+me\s+about\s+",
        r"^fmwk-",
        r"^spec-",
        r"^pkg-",
        r"\.py$",
        r"\.md$",
    ]
    for pattern in explain_patterns:
        if re.search(pattern, query_lower):
            return "explain"

    # List queries
    list_patterns = [
        r"list\s+",
        r"installed",
        r"packages\s*$",
        r"what.*installed",
    ]
    for pattern in list_patterns:
        if re.search(pattern, query_lower):
            return "list"

    # Status queries
    status_patterns = [
        r"health",
        r"status",
        r"verify",
        r"check",
        r"is\s+.*\s+ok",
    ]
    for pattern in status_patterns:
        if re.search(pattern, query_lower):
            return "status"

    # Inventory queries
    if "inventory" in query_lower:
        return "inventory"

    return "general"


def _extract_artifact_id(query: str) -> str:
    """Extract artifact ID from query.

    Args:
        query: User query string

    Returns:
        Extracted artifact ID or best guess
    """
    query = query.strip()

    # Direct ID patterns
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

    return query


def _load_capabilities() -> Dict[str, Any]:
    """Load agent capabilities from capabilities.json."""
    caps_path = Path(__file__).parent / "capabilities.json"
    if caps_path.exists():
        import json
        return json.loads(caps_path.read_text()).get("capabilities", {})
    return {}


def admin_turn(
    user_query: str,
    session_id: Optional[str] = None,
    turn_number: int = 1,
    root: Optional[Path] = None,
    use_router: bool = True,
) -> str:
    """Execute one admin agent turn (stateless).

    Uses the router to classify the query and map to a handler.
    Handler lookup searches both tools_first and llm_assisted modules.

    Args:
        user_query: User's question or command
        session_id: Optional session ID (generated if not provided)
        turn_number: Turn number within session
        root: Optional Control Plane root
        use_router: Whether to use the router (default: True)

    Returns:
        Agent's response string
    """
    # Initialize
    session_id = session_id or generate_session_id()
    agent = AdminAgent(root=root)
    root = agent.root

    # Create session
    session = Session(
        tier="ho1",
        session_id=session_id,
        root=root,
    )
    session.start()

    # Admin agent has no declared outputs (read-only)
    declared_outputs = []

    # Route decision tracking for evidence
    route_evidence = {}
    handler_executed = {}

    # Create ledger writer for session entries
    writer = LedgerWriter(session)

    try:
        # Write query entry BEFORE execution (original query for audit trail)
        writer.write_query(turn_number=turn_number, content=user_query)

        # No authorization extraction needed — read-only handlers execute directly
        clean_query = user_query
        a0_execute = False
        confirmation_id = None

        # Execute in sandbox
        with TurnSandbox(session_id, declared_outputs, root=root):
            if use_router:
                # Use the router for query handling
                from modules.router import route_query
                from modules.router.decision import get_route_evidence, RouteMode
                from modules.admin_agent.handlers import get_handler

                # Route the query
                route_result = route_query(clean_query)

                # Track what handler actually ran
                handler_executed = {
                    "handler": route_result.handler,
                    "mode": route_result.mode.value,
                    "executed": False,
                    "confirmation_id": confirmation_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }

                # Capture route evidence early (before handler may throw)
                route_evidence = get_route_evidence(route_result)

                # Handle based on mode
                if route_result.mode == RouteMode.DENIED:
                    handler_executed["authorization"] = "none"
                    result = f"Query denied: {route_result.reason}"
                else:
                    # Get handler — searches both tools_first and llm_assisted
                    handler = get_handler(route_result.handler)

                    if handler:
                        context = {
                            "query": clean_query,
                            "session": session,
                            **route_result.classification.extracted_args,
                        }
                        result = handler(agent, context)
                        handler_executed["executed"] = True

                        # All read-only handlers execute directly
                        handler_executed["authorization"] = "direct"
                    else:
                        # Handler not found — fail closed, record denial
                        denied_reason = (
                            f"Handler '{route_result.handler}' not found"
                        )
                        route_result.mode = RouteMode.DENIED
                        route_result.reason = denied_reason
                        handler_executed["mode"] = "denied"
                        handler_executed["authorization"] = "none"
                        result = (
                            f"Error: handler '{route_result.handler}' not found. "
                            f"No fallback — router decision is authoritative."
                        )

                # Re-capture route evidence if mode was mutated to DENIED
                if route_result.mode == RouteMode.DENIED:
                    route_evidence = get_route_evidence(route_result)
            else:
                # Legacy dispatch path — denied by default.
                # All queries must go through route_query() for authorization.
                result = (
                    "Error: Legacy dispatch (use_router=False) is disabled. "
                    "All queries must be routed through route_query()."
                )
                handler_executed = {
                    "handler": "legacy",
                    "mode": "denied",
                    "executed": False,
                    "confirmation_id": None,
                    "authorization": "none",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }

        # Write response entry AFTER execution
        writer.write_response(
            turn_number=turn_number,
            content=result,
            status="ok",
        )

        # Write evidence entry with route decision and handler execution
        evidence_entry = {
            "declared_reads": [],
            "declared_writes": [],
            "external_calls": [],
        }
        if route_evidence:
            evidence_entry["route_decision"] = route_evidence.get("route_decision", {})
        if handler_executed:
            evidence_entry["handler_executed"] = handler_executed

        writer.write_turn(
            turn_number=turn_number,
            exec_entry={
                "query_hash": hash_json({"query": user_query}),
                "result_hash": hash_json({"result": result}),
                "status": "ok",
            },
            evidence_entry=evidence_entry,
        )

        return result

    except Exception as e:
        # Write error response entry
        error_result = f"Error: {e}"
        writer.write_response(
            turn_number=turn_number,
            content=error_result,
            status="error",
        )

        # Build error evidence preserving any route/handler context
        # gathered before the exception occurred
        error_evidence = {
            "declared_reads": [],
            "declared_writes": [],
            "external_calls": [],
            "error": str(e),
        }
        if route_evidence:
            error_evidence["route_decision"] = route_evidence.get(
                "route_decision", {}
            )
        if handler_executed:
            error_evidence["handler_executed"] = handler_executed

        # Write evidence entry with error + preserved context
        writer.write_turn(
            turn_number=turn_number,
            exec_entry={
                "query_hash": hash_json({"query": user_query}),
                "result_hash": hash_json({"error": str(e)}),
                "status": "error",
            },
            evidence_entry=error_evidence,
        )
        return error_result

    finally:
        session.end()
