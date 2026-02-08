"""Prompt Contract based query router.

Uses stdlib_llm.complete() which:
- REQUIRES prompt_pack_id (HARD FAIL if missing)
- Logs all calls to L-LLM ledger with prompts_used[]
- Uses temperature=0 for deterministic outputs

Router provider is sourced from ROUTER_LLM_PROVIDER env var (default: "anthropic").
Router prompt pack is sourced from ROUTER_PROMPT_PACK env var (default: "PRM-ROUTER-001").
"""

import json
import os
import re
from dataclasses import dataclass
from typing import Optional, Dict, Any, Set

from modules.stdlib_llm import complete, load_prompt, LLMError

ROUTER_PROVIDER_ENV = "ROUTER_LLM_PROVIDER"
ROUTER_PROVIDER_DEFAULT = "anthropic"

ROUTER_PROMPT_PACK_ENV = "ROUTER_PROMPT_PACK"
ROUTER_PROMPT_PACK_DEFAULT = "PRM-ROUTER-001"


def get_router_provider_id() -> str:
    """Return the provider_id for router classification.

    Sources from ROUTER_LLM_PROVIDER env var, defaulting to "anthropic".
    Set ROUTER_LLM_PROVIDER=mock for offline/test usage.
    """
    return os.getenv(ROUTER_PROVIDER_ENV, ROUTER_PROVIDER_DEFAULT)


def get_router_prompt_pack() -> str:
    """Return the prompt pack ID for router classification.

    Sources from ROUTER_PROMPT_PACK env var, defaulting to "PRM-ROUTER-001".
    """
    return os.getenv(ROUTER_PROMPT_PACK_ENV, ROUTER_PROMPT_PACK_DEFAULT)


@dataclass
class IntentResult:
    """Classification result from router."""

    intent: str
    confidence: float
    artifact_id: Optional[str] = None
    file_path: Optional[str] = None
    reasoning: Optional[str] = None
    provider_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "intent": self.intent,
            "confidence": self.confidence,
            "artifact_id": self.artifact_id,
            "file_path": self.file_path,
            "reasoning": self.reasoning,
            "provider_id": self.provider_id,
        }


# Static fallback — used when no capabilities are provided
VALID_INTENTS = {
    "list_packages",
    "list_frameworks",
    "list_specs",
    "explain_artifact",
    "health_check",
    "show_ledger",
    "show_session",
    "read_file",
    "validate",
    "summarize",
    "general",
}

# Default capabilities text (used when no capabilities dict is provided)
_DEFAULT_CAPABILITIES_TEXT = """Available intent types:
- list_packages: Show installed packages
- list_frameworks: Show frameworks
- list_specs: Show specifications
- explain_artifact: Explain FMWK-XXX, SPEC-XXX, or PKG-XXX
- health_check: System status or verification
- show_ledger: Governance/audit logs
- show_session: Current session info
- read_file: Read a specific file
- validate: Check compliance
- summarize: Summary or comparison
- general: Doesn't fit other categories"""


def _render_template(template: str, variables: Dict[str, Any]) -> str:
    """Render mustache-style {{variable}} template."""
    result = template
    for key, value in variables.items():
        result = result.replace(f"{{{{{key}}}}}", str(value))
    return result


def _extract_prompt_template(content: str) -> str:
    """Extract Prompt Template section from markdown."""
    match = re.search(r"## Prompt Template\s*```\s*(.*?)\s*```", content, re.DOTALL)
    if match:
        return match.group(1).strip()
    return content


def _build_valid_intents(capabilities: Optional[Dict] = None) -> Set[str]:
    """Build set of valid intents from capabilities or use static fallback."""
    if capabilities and "intents" in capabilities:
        return {i["id"] for i in capabilities["intents"]} | {"general"}
    return VALID_INTENTS


def _validate_output(result: dict, valid_intents: Optional[Set[str]] = None) -> bool:
    """Validate output against schema rules."""
    intents = valid_intents or VALID_INTENTS
    if result.get("intent") not in intents:
        return False
    if not 0 <= result.get("confidence", -1) <= 1:
        return False
    if not result.get("reasoning"):
        return False
    return True


def _extract_json(text: str) -> str:
    """Extract JSON from LLM response, handling markdown code fences."""
    text = text.strip()
    # Handle ```json ... ``` wrapper
    if text.startswith("```"):
        lines = text.split("\n")
        # Skip first line (```json) and last line (```)
        json_lines = []
        for line in lines[1:]:
            if line.strip() == "```":
                break
            json_lines.append(line)
        return "\n".join(json_lines)
    return text


def classify_intent(
    query: str,
    capabilities: Optional[Dict] = None,
) -> IntentResult:
    """Classify query using governed prompt contract.

    Flow:
    1. Load prompt pack from governed_prompts/ (configurable via ROUTER_PROMPT_PACK env)
    2. Build capabilities text (from capabilities dict or default)
    3. Render template with query and capabilities
    4. Call LLM (one-shot, temp=0) via stdlib_llm
    5. Parse JSON and validate
    6. (stdlib_llm automatically logs to L-LLM ledger)

    Args:
        query: User query string
        capabilities: Optional capabilities dict from gather_capabilities()

    Returns:
        IntentResult with intent, confidence, and extracted args
    """
    router_pid = get_router_provider_id()
    prompt_pack = get_router_prompt_pack()
    valid_intents = _build_valid_intents(capabilities)

    # Build capabilities text for prompt
    if capabilities and "intents" in capabilities:
        from modules.router.capabilities import format_capabilities_for_prompt
        caps_text = format_capabilities_for_prompt(capabilities)
    else:
        caps_text = _DEFAULT_CAPABILITIES_TEXT

    try:
        # 1. Load governed prompt (validates PRM- prefix)
        content = load_prompt(prompt_pack)
        template = _extract_prompt_template(content)

        # 2. Render with query and capabilities variables
        prompt = _render_template(template, {
            "query": query,
            "capabilities": caps_text,
        })

        # 3. Call LLM via stdlib_llm (logs automatically)
        response = complete(
            prompt=prompt,
            prompt_pack_id=prompt_pack,
            temperature=0,  # Deterministic
            max_tokens=256,
            provider_id=router_pid,
        )

        # 4. Parse and validate JSON response (strip markdown fences)
        json_text = _extract_json(response.content)
        result = json.loads(json_text)

        if not _validate_output(result, valid_intents):
            return IntentResult(
                intent="general",
                confidence=0.0,
                reasoning="Validation failed: invalid intent or missing reasoning",
                provider_id=router_pid,
            )

        return IntentResult(
            intent=result.get("intent", "general"),
            confidence=result.get("confidence", 0.5),
            artifact_id=result.get("artifact_id"),
            file_path=result.get("file_path"),
            reasoning=result.get("reasoning"),
            provider_id=router_pid,
        )

    except LLMError as e:
        # LLM call failed (logged by stdlib_llm)
        return IntentResult(
            intent="general",
            confidence=0.0,
            reasoning=f"LLM error: {e.message}",
            provider_id=router_pid,
        )

    except json.JSONDecodeError as e:
        # Parse failed
        return IntentResult(
            intent="general",
            confidence=0.0,
            reasoning=f"JSON parse failed: {e}",
            provider_id=router_pid,
        )
