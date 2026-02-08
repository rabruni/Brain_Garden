"""Framework capability gathering for pre-router context injection.

Reads frameworks_registry.csv, calls PRM-FMWK-CAPABILITIES-001 to extract
capabilities, caches the result. The capabilities manifest is injected into
the router classification prompt so intent labels come from frameworks.
"""

import json
import os
from pathlib import Path
from typing import Dict, Optional

from modules.stdlib_llm import complete, load_prompt, LLMError

# Module-level cache (per-process, survives across queries)
_capabilities_cache: Optional[Dict] = None

CAPABILITIES_PROMPT_PACK = "PRM-FMWK-CAPABILITIES-001"
CAPABILITIES_PROVIDER_ENV = "CAPABILITIES_LLM_PROVIDER"


def _read_frameworks_registry(root: Path = None) -> str:
    """Read frameworks_registry.csv and return as string."""
    if root is None:
        root = Path(__file__).parent.parent.parent
    registry_path = root / "registries" / "frameworks_registry.csv"
    return registry_path.read_text()


def gather_capabilities(root: Path = None, force_refresh: bool = False) -> Dict:
    """Gather framework capabilities via LLM.

    Reads frameworks_registry.csv, calls PRM-FMWK-CAPABILITIES-001,
    returns capabilities manifest. Result is cached per-process.

    Returns:
        Dict with "intents" array
    """
    global _capabilities_cache

    if _capabilities_cache is not None and not force_refresh:
        return _capabilities_cache

    provider_id = os.getenv(CAPABILITIES_PROVIDER_ENV,
                            os.getenv("ROUTER_LLM_PROVIDER", "anthropic"))

    registry_content = _read_frameworks_registry(root)

    try:
        content = load_prompt(CAPABILITIES_PROMPT_PACK)
        from modules.router.prompt_router import _extract_prompt_template, _render_template
        template = _extract_prompt_template(content)
        prompt = _render_template(template, {"frameworks_registry": registry_content})

        response = complete(
            prompt=prompt,
            prompt_pack_id=CAPABILITIES_PROMPT_PACK,
            temperature=0,
            max_tokens=1024,
            provider_id=provider_id,
        )

        from modules.router.prompt_router import _extract_json
        json_text = _extract_json(response.content)
        result = json.loads(json_text)

        _capabilities_cache = result
        return result

    except (LLMError, json.JSONDecodeError, Exception):
        # Fallback: return hardcoded defaults (same as current PRM-ROUTER-001)
        return _default_capabilities()


def _default_capabilities() -> Dict:
    """Fallback capabilities when LLM is unavailable."""
    return {
        "intents": [
            {"id": "list_packages", "handler": "list_installed", "description": "Show installed packages", "framework": "FMWK-107"},
            {"id": "list_frameworks", "handler": "list_frameworks", "description": "Show frameworks", "framework": "FMWK-000"},
            {"id": "list_specs", "handler": "list_specs", "description": "Show specifications", "framework": "FMWK-100"},
            {"id": "explain_artifact", "handler": "explain", "description": "Explain FMWK/SPEC/PKG", "framework": "FMWK-100"},
            {"id": "health_check", "handler": "check_health", "description": "System status", "framework": "FMWK-000"},
            {"id": "show_ledger", "handler": "show_ledger", "description": "Governance logs", "framework": "FMWK-200"},
            {"id": "show_session", "handler": "show_session_ledger", "description": "Session info", "framework": "FMWK-200"},
            {"id": "read_file", "handler": "read_file", "description": "Read a file", "framework": "FMWK-000"},
            {"id": "validate", "handler": "validate_document", "description": "Check compliance", "framework": "FMWK-100"},
            {"id": "summarize", "handler": "summarize", "description": "Summary or comparison", "framework": "FMWK-100"},
            {"id": "general", "handler": "general", "description": "General query", "framework": "FMWK-100"},
        ]
    }


def format_capabilities_for_prompt(capabilities: Dict) -> str:
    """Format capabilities manifest as text for prompt injection.

    Args:
        capabilities: Dict with "intents" array

    Returns:
        Formatted string for {{capabilities}} template variable
    """
    intents = capabilities.get("intents", [])
    lines = ["Available intent types:"]
    for intent in intents:
        lines.append(f"- {intent['id']}: {intent['description']}")
    return "\n".join(lines)


def clear_capabilities_cache():
    """Clear the cached capabilities (for testing)."""
    global _capabilities_cache
    _capabilities_cache = None
