"""LLM Standard Library.

Provides a stateless, provider-agnostic LLM client for governed completions.
All LLM calls require a governed prompt reference (prompt_pack_id).

This is a Tier 0 (T0) trust baseline library.

Key Invariants:
- prompt_pack_id is REQUIRED for all completions (ungoverned prompts = HARD FAIL)
- LLM responses are ASSISTIVE only, never authoritative
- All calls are logged with evidence (provider, model, usage)
- Secrets are never logged (only fingerprints)

Example usage:
    from modules.stdlib_llm import complete, load_prompt, LLMResponse

    # Load governed prompt and execute completion
    prompt_template = load_prompt("PRM-ADMIN-EXPLAIN-001")
    response = complete(
        prompt=prompt_template.format(artifact="FMWK-000"),
        prompt_pack_id="PRM-ADMIN-EXPLAIN-001",
    )
    print(response.content)
"""

from modules.stdlib_llm.client import complete, load_prompt, get_provider, LLMResponse
from modules.stdlib_llm.provider import LLMProvider, ProviderResponse
from modules.stdlib_llm.evidence import build_llm_evidence

__all__ = [
    "complete",
    "load_prompt",
    "get_provider",
    "build_llm_evidence",
    "LLMResponse",
    "LLMProvider",
    "ProviderResponse",
]

__version__ = "0.1.0"


class LLMError(Exception):
    """LLM operation error."""

    def __init__(self, message: str, code: str = "LLM_ERROR", details: dict = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}
