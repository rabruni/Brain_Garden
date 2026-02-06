"""Brain — KERNEL.semantic one-shot advisory call.

Uses PRM-BRAIN-001 governed prompt to analyze a user query against
system context and return structured advice (intent, handler, next step).

The brain SUGGESTS but never EXECUTES. It is purely advisory.

Example:
    from modules.brain.brain import brain_call

    resp = brain_call("what should I do next?", {"packages": [], "health": {}})
    print(resp.intent, resp.suggested_handler, resp.proposed_next_step)
"""

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from modules.stdlib_llm import complete, LLMResponse
from modules.stdlib_llm.client import LLMError, load_prompt
from modules.stdlib_llm.config import get_default_provider_id


BRAIN_PROVIDER_ENV = "BRAIN_LLM_PROVIDER"
BRAIN_PROMPT_PACK_ID = "PRM-BRAIN-001"

# Valid handler names (from decision.py INTENT_HANDLER_MAP values)
VALID_HANDLERS = {
    "list_installed", "list_frameworks", "list_specs", "explain",
    "check_health", "show_ledger", "show_session_ledger", "read_file",
    "validate_document", "summarize", "general",
}

VALID_MODES = {"tools_first", "llm_assisted"}


def get_brain_provider_id() -> str:
    """Return the provider_id for brain calls.

    Sources from BRAIN_LLM_PROVIDER env var, falling back to the
    system default provider (LLM_DEFAULT_PROVIDER or "anthropic").
    """
    return os.getenv(BRAIN_PROVIDER_ENV) or get_default_provider_id()


@dataclass
class BrainResponse:
    """Structured response from brain_call().

    The brain produces advisory output — it suggests a handler and
    next step but never triggers execution.
    """

    intent: str
    confidence: float
    suggested_handler: str
    mode: str  # "tools_first" | "llm_assisted"
    proposed_next_step: str
    provider_id: str
    raw: dict = field(default_factory=dict)
    evidence: dict = field(default_factory=dict)


def _extract_prompt_template(content: str) -> str:
    """Extract Prompt Template section from governed prompt markdown."""
    match = re.search(r"## Prompt Template\s*```\s*(.*?)\s*```", content, re.DOTALL)
    if match:
        return match.group(1).strip()
    return content


def _render_template(template: str, variables: Dict[str, Any]) -> str:
    """Render mustache-style {{variable}} template."""
    result = template
    for key, value in variables.items():
        result = result.replace(f"{{{{{key}}}}}", str(value))
    return result


def _extract_json(text: str) -> str:
    """Extract JSON from LLM response, handling markdown code fences."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        json_lines = []
        for line in lines[1:]:
            if line.strip() == "```":
                break
            json_lines.append(line)
        return "\n".join(json_lines)
    return text


def _validate_brain_output(result: dict) -> bool:
    """Validate brain output against schema rules."""
    if result.get("suggested_handler") not in VALID_HANDLERS:
        return False
    if result.get("mode") not in VALID_MODES:
        return False
    if not 0 <= result.get("confidence", -1) <= 1:
        return False
    if not result.get("proposed_next_step"):
        return False
    return True


def brain_call(
    query: str,
    system_context: dict,
    *,
    provider_id: Optional[str] = None,
) -> BrainResponse:
    """One-shot KERNEL.semantic brain call.

    1. Load PRM-BRAIN-001 governed prompt
    2. Render with query + system_context
    3. Call stdlib_llm.complete(temperature=0, provider_id=...)
    4. Parse strict JSON output
    5. Return BrainResponse (logged to L-LLM ledger by stdlib_llm)

    Args:
        query: User's natural language query
        system_context: Gathered system context (packages, health, etc.)
        provider_id: Optional provider override (defaults to get_brain_provider_id())

    Returns:
        BrainResponse with structured advisory output
    """
    pid = provider_id or get_brain_provider_id()

    try:
        # 1. Load governed prompt
        content = load_prompt(BRAIN_PROMPT_PACK_ID)
        template = _extract_prompt_template(content)

        # 2. Render with query + system_context
        context_json = json.dumps(system_context, indent=2, default=str)
        prompt = _render_template(template, {
            "query": query,
            "system_context": context_json,
        })

        # 3. Call LLM via stdlib_llm (one-shot, temp=0)
        response: LLMResponse = complete(
            prompt=prompt,
            prompt_pack_id=BRAIN_PROMPT_PACK_ID,
            temperature=0,
            max_tokens=512,
            provider_id=pid,
        )

        # 4. Parse and validate JSON response
        json_text = _extract_json(response.content)
        result = json.loads(json_text)

        if not _validate_brain_output(result):
            return BrainResponse(
                intent="general",
                confidence=0.0,
                suggested_handler="general",
                mode="llm_assisted",
                proposed_next_step="Validation failed — falling back to general handler.",
                provider_id=pid,
                raw=result,
                evidence=response.evidence,
            )

        return BrainResponse(
            intent=result.get("intent", "general"),
            confidence=result.get("confidence", 0.5),
            suggested_handler=result.get("suggested_handler", "general"),
            mode=result.get("mode", "llm_assisted"),
            proposed_next_step=result.get("proposed_next_step", ""),
            provider_id=pid,
            raw=result,
            evidence=response.evidence,
        )

    except LLMError as e:
        return BrainResponse(
            intent="general",
            confidence=0.0,
            suggested_handler="general",
            mode="llm_assisted",
            proposed_next_step=f"Brain call failed: {e.message}",
            provider_id=pid,
            evidence={"error": e.message},
        )

    except json.JSONDecodeError as e:
        return BrainResponse(
            intent="general",
            confidence=0.0,
            suggested_handler="general",
            mode="llm_assisted",
            proposed_next_step=f"Brain response parse failed: {e}",
            provider_id=pid,
            evidence={"error": str(e)},
        )
