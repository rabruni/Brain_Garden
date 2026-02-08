"""LLM-Assisted Handlers — Governed LLM Completions.

Handlers that use stdlib_llm.complete() for all LLM operations.
Direct Anthropic SDK usage is forbidden per Phase 1 governance.

Example:
    from modules.admin_agent.handlers.llm_assisted import general

    result = general(agent, {"query": "Show me the session ledger", "session": session})
"""

import json
import os
from typing import Any, Dict

from modules.admin_agent.agent import AdminAgent
from modules.stdlib_llm import complete
from modules.stdlib_llm.client import LLMError
from modules.stdlib_llm.config import get_default_provider_id
from lib.prompt_loader import load_prompt as load_governed_prompt

LLM_ASSISTED_PROVIDER_ENV = "LLM_ASSISTED_PROVIDER"


def get_llm_assisted_provider_id() -> str:
    """Return the provider_id for LLM-assisted handlers.

    Sources from LLM_ASSISTED_PROVIDER env var, falling back to the
    system default provider (LLM_DEFAULT_PROVIDER or "anthropic").
    """
    return os.getenv(LLM_ASSISTED_PROVIDER_ENV) or get_default_provider_id()


def validate_document(
    agent: AdminAgent,
    context: Dict[str, Any],
) -> str:
    """Validate a document against framework requirements.

    Uses tools to gather framework requirements, then LLM to analyze.

    Args:
        agent: AdminAgent instance
        context: Query context with prompt_pack_id

    Returns:
        Validation results
    """
    prompt_pack_id = context.get("prompt_pack_id", "PRM-ADMIN-VALIDATE-001")
    query = context.get("query", "")
    session = context.get("session")

    # Record prompt usage in session for audit trail
    if session and hasattr(session, "record_prompt"):
        session.record_prompt(prompt_pack_id)

    # Step 1: Tools-first - gather data
    # Extract document and framework from query
    # For now, just return a placeholder
    # In production, would read the document and framework

    # Step 2: Load governed prompt
    try:
        prompt_template = load_governed_prompt(prompt_pack_id)
    except Exception as e:
        return f"Error loading prompt: {e}"

    # Step 3: Execute LLM completion
    try:
        response = complete(
            prompt=f"Validate the following query: {query}",
            prompt_pack_id=prompt_pack_id,
            provider_id=get_llm_assisted_provider_id(),
        )

        return f"# Validation Result\n\n{response.content}"

    except LLMError as e:
        return f"Error: {e.message}"


def summarize(
    agent: AdminAgent,
    context: Dict[str, Any],
) -> str:
    """Summarize artifacts or relationships.

    Uses tools to gather data, then LLM to synthesize explanation.

    Args:
        agent: AdminAgent instance
        context: Query context with prompt_pack_id

    Returns:
        Summary text
    """
    prompt_pack_id = context.get("prompt_pack_id", "PRM-ADMIN-EXPLAIN-001")
    query = context.get("query", "")
    session = context.get("session")

    # Record prompt usage in session for audit trail
    if session and hasattr(session, "record_prompt"):
        session.record_prompt(prompt_pack_id)

    # Step 1: Tools-first - gather relevant data
    gathered_data = _gather_data_for_summary(agent, query)

    # Step 2: Load governed prompt
    try:
        prompt_template = load_governed_prompt(prompt_pack_id)
    except Exception as e:
        return f"Error loading prompt: {e}"

    # Step 3: Build prompt with gathered data
    prompt = f"""Based on the following data gathered from the Control Plane:

{json.dumps(gathered_data, indent=2)}

User query: {query}

Provide a clear, concise summary that answers the user's question.
Only use information from the provided data."""

    # Step 4: Execute LLM completion
    try:
        response = complete(
            prompt=prompt,
            prompt_pack_id=prompt_pack_id,
            provider_id=get_llm_assisted_provider_id(),
        )

        return f"# Summary\n\n{response.content}"

    except LLMError as e:
        return f"Error: {e.message}"


def explain_llm(
    agent: AdminAgent,
    context: Dict[str, Any],
) -> str:
    """LLM-enhanced explanation of artifacts.

    Uses tools to gather data, then LLM to synthesize.

    Args:
        agent: AdminAgent instance
        context: Query context with artifact_id

    Returns:
        Enhanced explanation
    """
    prompt_pack_id = context.get("prompt_pack_id", "PRM-ADMIN-EXPLAIN-001")
    artifact_id = context.get("artifact_id", "")
    session = context.get("session")

    # Record prompt usage in session for audit trail
    if session and hasattr(session, "record_prompt"):
        session.record_prompt(prompt_pack_id)

    if not artifact_id:
        return "Error: No artifact ID provided"

    # Step 1: Tools-first - get artifact data via trace
    trace_result = agent._run_trace("--explain", artifact_id)

    if "error" in trace_result:
        return f"Error: {trace_result['error']}"

    # Step 2: Load governed prompt
    try:
        prompt_template = load_governed_prompt(prompt_pack_id)
    except Exception as e:
        return f"Error loading prompt: {e}"

    # Step 3: Build prompt with artifact data
    prompt = f"""Artifact: {artifact_id}
Type: {trace_result.get('type', 'unknown')}

Data from tools:
```json
{json.dumps(trace_result.get('data', {}), indent=2)}
```

Provide a clear, concise explanation of this artifact."""

    # Step 4: Execute LLM completion
    try:
        response = complete(
            prompt=prompt,
            prompt_pack_id=prompt_pack_id,
            provider_id=get_llm_assisted_provider_id(),
        )

        return f"# {artifact_id}\n\n{response.content}"

    except LLMError as e:
        return f"Error: {e.message}"


def general(
    agent: AdminAgent,
    context: Dict[str, Any],
) -> str:
    """Handle general queries with a conversational LLM response.

    Gathers system context via _gather_general_context(), then calls
    complete() with PRM-ADMIN-GENERAL-001 to produce a helpful,
    conversational response.

    Args:
        agent: AdminAgent instance
        context: Query context with session

    Returns:
        Conversational response addressing the user's query
    """
    query = context.get("query", "")
    session = context.get("session")

    # Record prompt usage in session for audit trail
    if session and hasattr(session, "record_prompt"):
        session.record_prompt("PRM-ADMIN-GENERAL-001")

    # Step 1: Gather system context (packages, health, ledgers, sessions)
    gathered = _gather_general_context(agent, session)

    # Step 2: Load governed prompt
    prompt_pack_id = "PRM-ADMIN-GENERAL-001"
    try:
        prompt_template = load_governed_prompt(prompt_pack_id)
    except Exception:
        prompt_template = None

    # Step 3: Build prompt with context
    prompt = f"""You are the Control Plane Admin Agent, a helpful assistant for understanding
and navigating the Control Plane governance system.

The user has asked a general question. Using the context below, provide
a helpful, conversational response.

User query: {query}

## System Context

Installed packages:
```json
{json.dumps(gathered.get("packages", []), indent=2)}
```

System health:
```json
{json.dumps(gathered.get("health", {}), indent=2)}
```

Recent ledger activity:
```json
{json.dumps(gathered.get("todays_governance", [])[:5], indent=2)}
```

## Instructions

1. Answer the user's question conversationally and helpfully
2. If the question is a greeting, respond warmly and offer to help
3. If the question asks about capabilities, explain what you can do
4. Reference specific data from the context when relevant
5. Keep responses concise (under 150 words for simple queries)

IMPORTANT: Only use information from the provided context.
Do not invent or assume information not present in the data."""

    # Step 4: Call LLM for actual conversational response
    try:
        response = complete(
            prompt=prompt,
            prompt_pack_id=prompt_pack_id,
            provider_id=get_llm_assisted_provider_id(),
        )

        return response.content

    except LLMError as e:
        return f"Error: {e.message}"


def _complete_with_tools(**kwargs) -> str:
    """FORBIDDEN: Direct LLM calls are not allowed.

    This function previously called the Anthropic SDK directly, bypassing
    stdlib_llm.complete(). It has been replaced with a hard fail to enforce
    governance. All LLM usage must go through stdlib_llm.complete().

    Raises:
        LLMError: Always. Direct LLM calls are forbidden.
    """
    raise LLMError(
        "Direct LLM calls are forbidden. All LLM usage must go through "
        "stdlib_llm.complete() per Phase 1 governance.",
        code="DIRECT_LLM_FORBIDDEN",
    )


def _gather_general_context(agent: AdminAgent, session=None) -> dict:
    """Gather comprehensive context data for LLM queries.

    Args:
        agent: AdminAgent instance
        session: Optional session object for session-specific data

    Returns:
        Context dictionary with packages, health, ledgers, session data
    """
    context = {}

    # Get installed packages
    packages_result = agent._run_trace("--installed")
    if isinstance(packages_result, list):
        context["packages"] = packages_result
    else:
        context["packages"] = []

    # Get health status with details
    health_result = agent._run_trace("--verify")
    if isinstance(health_result, dict):
        context["health"] = health_result
    else:
        context["health"] = {"status": "unknown"}

    # Session info
    if session:
        context["session"] = {
            "session_id": session.session_id,
            "tier": session.tier,
            "session_path": str(session.session_path),
            "ledger_path": str(session.ledger_path),
            "exec_ledger_path": str(session.exec_ledger_path),
            "evidence_ledger_path": str(session.evidence_ledger_path),
        }

        # Read current session ledger (full content, no truncation)
        session_ledger_entries = []
        if session.exec_ledger_path.exists():
            try:
                with open(session.exec_ledger_path) as f:
                    for line in f:
                        if line.strip():
                            entry = json.loads(line)
                            session_ledger_entries.append({
                                "turn": entry.get("turn_number"),
                                "type": entry.get("event_type"),
                                "content": entry.get("content", ""),
                                "timestamp": entry.get("timestamp"),
                                "status": entry.get("status"),
                            })
            except Exception:
                pass
        context["session_ledger"] = session_ledger_entries

    # Get recent LLM calls with details
    llm_entries = []
    llm_ledger = agent.root / "ledger" / "llm.jsonl"
    if llm_ledger.exists():
        try:
            with open(llm_ledger) as f:
                all_entries = [json.loads(line) for line in f if line.strip()]
            # Last 10 entries
            for entry in all_entries[-10:]:
                llm_entries.append({
                    "timestamp": entry.get("timestamp"),
                    "prompt_used": entry.get("prompts_used", ["unknown"])[0],
                    "model": entry.get("metadata", {}).get("model", "unknown"),
                })
        except Exception:
            pass
    context["llm_calls"] = llm_entries

    # Get all ledger files summary
    from datetime import datetime
    ledger_dir = agent.root / "ledger"

    context["ledger_directory"] = str(ledger_dir)
    context["available_ledgers"] = {
        "directory": str(ledger_dir),
        "governance": sorted([f.name for f in ledger_dir.glob("governance-*.jsonl")]),
        "packages": sorted([f.name for f in ledger_dir.glob("packages-*.jsonl")]),
        "kernel": sorted([f.name for f in ledger_dir.glob("kernel-*.jsonl")]),
        "llm": "llm.jsonl" if (ledger_dir / "llm.jsonl").exists() else None,
        "index": "index.jsonl" if (ledger_dir / "index.jsonl").exists() else None,
    }

    # Get today's governance events (full content)
    today = datetime.now().strftime("%Y%m%d")
    governance_events = []
    for gfile in sorted(ledger_dir.glob(f"governance-{today}*.jsonl")):
        try:
            with open(gfile) as f:
                for line in f:
                    if line.strip():
                        entry = json.loads(line)
                        governance_events.append({
                            "timestamp": entry.get("timestamp"),
                            "event_type": entry.get("event_type", entry.get("type")),
                            "package_id": entry.get("package_id"),
                            "message": entry.get("message", ""),
                            "file": gfile.name,
                        })
        except Exception:
            pass
    context["todays_governance"] = governance_events

    # Get recent package events
    package_events = []
    for pfile in sorted(ledger_dir.glob("packages-*.jsonl"), reverse=True)[:3]:
        try:
            with open(pfile) as f:
                for line in f:
                    if line.strip():
                        entry = json.loads(line)
                        package_events.append({
                            "timestamp": entry.get("timestamp"),
                            "event_type": entry.get("event_type"),
                            "package_id": entry.get("package_id"),
                            "file": pfile.name,
                        })
        except Exception:
            pass
    context["package_events"] = package_events

    # Get kernel events
    kernel_events = []
    for kfile in sorted(ledger_dir.glob("kernel-*.jsonl"), reverse=True)[:2]:
        try:
            with open(kfile) as f:
                for line in f:
                    if line.strip():
                        entry = json.loads(line)
                        kernel_events.append({
                            "timestamp": entry.get("timestamp"),
                            "event_type": entry.get("event_type"),
                            "tier": entry.get("tier"),
                            "file": kfile.name,
                        })
        except Exception:
            pass
    context["kernel_events"] = kernel_events

    # List recent sessions
    sessions_dir = agent.root / "planes" / "ho1" / "sessions"
    recent_sessions = []
    if sessions_dir.exists():
        for sess_dir in sorted(sessions_dir.iterdir(), reverse=True)[:10]:
            if sess_dir.is_dir() and sess_dir.name.startswith("SES-"):
                recent_sessions.append(sess_dir.name)
    context["recent_sessions"] = recent_sessions

    return context


def _gather_data_for_summary(agent: AdminAgent, query: str) -> dict:
    """Gather relevant data for summary based on query.

    Args:
        agent: AdminAgent instance
        query: User query

    Returns:
        Gathered data dict
    """
    data = {}
    query_lower = query.lower()

    # Check what kind of summary is needed
    if "framework" in query_lower:
        # Get frameworks list
        data["frameworks"] = []
        try:
            import csv
            from pathlib import Path
            registry_path = agent.root / "registries" / "frameworks_registry.csv"
            if registry_path.exists():
                with open(registry_path) as f:
                    reader = csv.DictReader(f)
                    data["frameworks"] = list(reader)
        except Exception:
            pass

    if "package" in query_lower or "installed" in query_lower:
        # Get installed packages
        result = agent._run_trace("--installed")
        if "error" not in result:
            data["packages"] = result

    if "spec" in query_lower:
        # Get specs list
        data["specs"] = []
        try:
            import csv
            from pathlib import Path
            registry_path = agent.root / "registries" / "specs_registry.csv"
            if registry_path.exists():
                with open(registry_path) as f:
                    reader = csv.DictReader(f)
                    data["specs"] = list(reader)
        except Exception:
            pass

    return data
