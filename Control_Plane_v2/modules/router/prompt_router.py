"""Prompt Contract based query router.

Uses stdlib_llm.complete() which:
- REQUIRES prompt_pack_id (HARD FAIL if missing)
- Logs all calls to L-LLM ledger with prompts_used[]
- Uses temperature=0 for deterministic outputs

Router provider is sourced from ROUTER_LLM_PROVIDER env var (default: "mock").
"""

import json
import os
import re
from dataclasses import dataclass
from typing import Optional, Dict, Any

from modules.stdlib_llm import complete, load_prompt, LLMError

ROUTER_PROVIDER_ENV = "ROUTER_LLM_PROVIDER"
ROUTER_PROVIDER_DEFAULT = "mock"


def get_router_provider_id() -> str:
    """Return the provider_id for router classification.

    Sources from ROUTER_LLM_PROVIDER env var, defaulting to "mock"
    so that routing is deterministic and makes no network calls
    unless explicitly configured.
    """
    return os.getenv(ROUTER_PROVIDER_ENV, ROUTER_PROVIDER_DEFAULT)


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


def _validate_output(result: dict) -> bool:
    """Validate output against schema rules."""
    if result.get("intent") not in VALID_INTENTS:
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


def classify_intent(query: str) -> IntentResult:
    """Classify query using governed prompt contract.

    Flow:
    1. Load PRM-ROUTER-001 from governed_prompts/
    2. Render template with query
    3. Call LLM (one-shot, temp=0) via stdlib_llm
    4. Parse JSON and validate
    5. (stdlib_llm automatically logs to L-LLM ledger)

    Returns:
        IntentResult with intent, confidence, and extracted args
    """
    router_pid = get_router_provider_id()

    try:
        # 1. Load governed prompt (validates PRM- prefix)
        content = load_prompt("PRM-ROUTER-001")
        template = _extract_prompt_template(content)

        # 2. Render with query variable
        prompt = _render_template(template, {"query": query})

        # 3. Call LLM via stdlib_llm (logs automatically)
        response = complete(
            prompt=prompt,
            prompt_pack_id="PRM-ROUTER-001",
            temperature=0,  # Deterministic
            max_tokens=256,
            provider_id=router_pid,
        )

        # 4. Parse and validate JSON response (strip markdown fences)
        json_text = _extract_json(response.content)
        result = json.loads(json_text)

        if not _validate_output(result):
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
